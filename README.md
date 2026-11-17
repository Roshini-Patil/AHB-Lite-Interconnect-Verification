# F0X — Verification of a Multi-Master AHB-Lite Interconnect

**FFVD Project 1 · PES University, Dept. of ECE · Team F0X**
Roshini (lead) · Pallavi · Pranav · Nivedith

UVM-style verification of the open-source **RoaLogic `ahb3lite_interconnect`** (3 masters × 3 slaves), covering multi-master arbitration and burst transfers, using **open-source tools only**.

---

## 1. Design under test

| Item | Value |
|---|---|
| RTL | RoaLogic `ahb3lite_interconnect`, commit `4ad2737` (`ahb3lite_pkg` `ce28676`) |
| Configuration | 3 master ports × 3 slave ports (crossbar / multi-layer switch) |
| Address map | Slave *j* when `HADDR[31:28] = j`; `HADDR[31:28] ≥ 3` → no slave → ERROR (`ERROR_ON_NO_SLAVE = 1`) |
| Mask build | Master 2 may not access slave 0 → ERROR (`ERROR_ON_SLAVE_MASK = 1`) |
| Arbitration | Per slave port: highest `mst_priority` wins; ties → round-robin. Switch only when the current master's port raises `can_switch` (IDLE, SINGLE, last beat of a fixed burst; never while `HMASTLOCK`; INCR only after IDLE) |
| Size | 4 RTL files, ~1300 lines; Verilator compile: 0 errors, 0 warnings |

## 2. Tool flow (Cadence lab → open-source)

| Lab (Cadence) | This project |
|---|---|
| `irun` / `xrun -sv -uvm` | **Verilator 5.038** (SV RTL → C++ model) + **cocotb 2.0.1** (Python ↔ simulator via VPI) |
| UVM 1.2 SystemVerilog classes | **pyuvm** @ `12351ba6e3a76115f0e257bbe8ebd98446f51f2e` (UVM in Python) |
| Virtual interface + clocking block | PortView object: sample at falling edge, drive after rising edge |
| `uvm_config_db` / factory override | `ConfigDB().set/get`, `uvm_factory().set_type_override_by_type` |
| SVA `assert property` | Per-cycle Python checkers with named tags (`A_*`, `ARB_*`, `SB_*`) |
| Covergroups + IMC merge | CoverGroup bins → JSON per run → merged by our script |
| SimVision | VCD → **GTKWave** (or `scripts/vcd2png.py`) |
| `-svseed N` | `+seed N` (seeds Python `random`; runs are repeatable) |
| Genus (synthesis) | Not used; open-source equivalent would be **Yosys** |

The original SystemVerilog UVM testbench is kept in `tb_sv_uvm/` for the lab simulator. The RTL is unmodified; a thin wrapper (`ahb_ic_wrap`) only flattens array ports.

## 3. Testbench architecture

- **3 active master agents**: sequencer, pipelined driver, monitor, protocol checker.
- **3 reactive slave agents**: responder (random wait states, random 2-cycle ERRORs, byte-lane memory), monitor, checker.
- **Virtual sequencer** holding the 3 master sequencers.
- **Scoreboard**: routing, per-slave memory model (updated in slave-observed order), wait split (slave wait vs contention wait).
- **Arbitration checker** on all slave ports, including a cycle-accurate reference model of the RTL arbiter.
- **Coverage collector**.

### Checks

| Layer | Tags |
|---|---|
| Protocol (all 6 ports) | `A_WDATA_STABLE`, `A_ADDR_HOLD`, `A_SEQ_IN_BURST`, `A_BURST_ADDR`, `A_BURST_CTRL`, `A_1KB`, `A_BURST_LEN`, `A_ERR_2CYCLE` |
| Arbitration | `ONE_MASTER`, `ARB_MID_BURST`, `ARB_INTERLEAVE`, `ARB_PRIORITY`, `ARB_STARVATION` (≤ NM−1 = 2), `ARB_MODEL` |
| Scoreboard | `SB_ROUTE`, `SB_DATA`, `SB_RESP`, `SB_NOSLAVE`, `SB_MASK`, `SB_LOST`, `SB_ORPHAN` |

## 4. Results (as recorded in the project deck / logs)

| Metric | Value |
|---|---|
| Sign-off runs | **51 / 51 PASS** (0 scoreboard errors, 0 assertion failures) |
| Functional coverage | **100 %**, 93 / 93 bins, merged over 51 runs |
| Beats checked | 24,690 master beats over 57,241 clock cycles |
| Full regression | 60 runs = 51 sign-off + 3 bug-reproduction + 3 fixed-RTL + 3 negative; all matched expectation |
| Example run | `contention`, seed 3, `+PRIO=dynamic`: 395 = 395 beats, 59 grant changes, longest wait 142 cycles (contention) |

Coverage holes found and closed: *switch after SINGLE* (added back-to-back SINGLEs), *NO_SLAVE error on masters 1 & 2* (rotated unmapped accesses).

> **Provenance:** these numbers come from the runs in the earlier project chat and are what the slides show. Re-running on your own machine should give the same values for the same seeds; record your own values (see `F0X_Run_Guide.pdf`, Part H).

## 5. The RTL bug

**File:** `rtl/ahb3lite_interconnect_master_port.sv`

`burst_cnt` decrements on **every** non-NONSEQ cycle, including **BUSY**. BUSY carries no data, so each BUSY inside a fixed burst (INCR4/8/16, WRAP4/8/16) makes the counter reach 0 early. `can_switch` then goes high before the last beat, and the slave port hands the slave to another master **mid-burst**. Later the first master resumes with an orphan SEQ.

Detected by `ARB_MID_BURST`, `A_BURST_LEN`, `A_SEQ_IN_BURST` (6 different tags in total).

**Fix (one line, in `rtl_fix/` — original left untouched):**

```systemverilog
else if (mst_HTRANS == HTRANS_SEQ)
    burst_cnt <= burst_cnt - 1;
```

**Proof (same seeds 1–3):**

| | Original RTL | Fixed RTL |
|---|---|---|
| Fixed bursts, no BUSY | PASS | PASS |
| Fixed bursts + BUSY | **FAIL** (229 / 211 / 198 errors) | **PASS** |

## 6. Negative tests (checkers can fail)

| Plusarg | Injected fault | Expected tag |
|---|---|---|
| `+NEG_1KB` | Factory override: bursts cross 1 KB | `A_1KB` |
| `+INJECT=data` | Slave flips a read-data bit | `SB_DATA` |
| `+INJECT=err1` | 1-cycle ERROR instead of 2 | `A_ERR_2CYCLE` |

All three FAIL as intended.

## 7. Folder layout

```
F0X/
├── rtl/          original RoaLogic RTL (unmodified)
├── rtl_fix/      copy with the 1-line burst_cnt fix
├── tb/           pyuvm + cocotb testbench
├── tb_sv_uvm/    original SystemVerilog UVM testbench (for Xcelium/irun)
├── scripts/      coverage merge, vcd2png, regression helpers
├── run.sh        one command per run:  ./run.sh <test> <seed> [+plusargs] [--cfg fix|mask]
├── SS/           screenshots, waveforms, logs, coverage
├── docs/         AHB_Interconnect_Verification.pptx (20 slides + speaker notes), viva_guide.md
└── DIY/          step-by-step lab manual 00–10 + commands/
```

## 8. How to run (WSL Ubuntu)

Setup (Verilator 5.038 from source, venv with cocotb 2.0.1 + pyuvm, GTKWave):

```bash
bash ~/setup_f0x.sh            # see F0X_Run_Guide.pdf for details
cd ~/F0X
```

Key runs (check exact options in `DIY/05`, `DIY/08`, `DIY/09`):

```bash
./run.sh contention 3 +PRIO=dynamic          # sign-off example -> AHB_RESULT PASS
./run.sh busy 1 +PRIO=equal                  # original RTL     -> FAIL (bug)
./run.sh busy 1 +PRIO=equal --cfg fix        # fixed RTL        -> PASS
diff -r rtl rtl_fix                          # shows the 1-line fix
```

Pass criterion: the line `AHB_RESULT PASS` with 0 errors.

## 9. Limitations

- Functional coverage only, no code coverage.
- Arbitration expectations (starvation bound, priority rules) are derived from reading the RTL; there is no separate written spec for this IP.
- No synthesis was done (Genus/Yosys not used).
