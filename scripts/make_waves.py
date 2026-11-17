#!/usr/bin/env python3
"""make_waves.py - re-run chosen scenarios with VCD dumping, find the interesting moment
in each VCD automatically, and render a waveform PNG (scripts/vcd2png.py).

  python3 scripts/make_waves.py <out_dir>
Every picture can be reproduced in GTKWave:  gtkwave sim/runs/<tag>/dump.vcd
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vcd2png import parse_vcd, value_at

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "SS" / "waves"


def m(i):
    return [f"m{i}.HTRANS=mst_HTRANS[{2*i+1}:{2*i}]:htrans", f"m{i}.HBURST=mst_HBURST[{3*i+2}:{3*i}]:hburst",
            f"m{i}.HADDR=mst_HADDR[{32*i+31}:{32*i}]", f"m{i}.HREADY=mst_HREADY[{i}:{i}]"]


def s(j, gnt=True):
    l = [f"s{j}.HTRANS=slv_HTRANS[{2*j+1}:{2*j}]:htrans", f"s{j}.HADDR=slv_HADDR[{32*j+31}:{32*j}]",
         f"s{j}.HREADYOUT=slv_HREADYOUT[{j}:{j}]"]
    if gnt:
        l += [f"s{j}.grant(dbg)=dbg_gnt[{2*j+1}:{2*j}]:dec", f"s{j}.request(dbg)=dbg_req[{3*j+2}:{3*j}]"]
    return l


def run(tag, test, seed, args, cfg="main"):
    subprocess.run(["./run.sh", test, str(seed)] + args.split() + ["--cfg", cfg, "--tag", tag, "--waves"],
                   cwd=ROOT, capture_output=True)
    return ROOT / "sim" / "runs" / tag / "dump.vcd"


def field(v, lo, w):
    return (v >> lo) & ((1 << w) - 1)


def find(vcd, names, cond, start=60):
    """First mid-cycle time (ns) >= start where cond(values) is true."""
    ch = parse_vcd(vcd, set(names))
    end = max((c[-1][0] for c in ch.values() if c), default=0) // 1000
    t = start
    while t < end:
        vals = {n: value_at(ch[n], t * 1000 + 5000) for n in names}
        if cond(vals, t):
            return t
        t += 10
    return None


def draw(vcd, name, t0, t1, specs):
    out = OUT / f"{name}.png"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "vcd2png.py"), str(vcd), str(out),
                    str(t0), str(t1)] + specs, check=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 1. parallel access: m0->s0 and m1->s1 transfer in the same cycle
    v = run("w_parallel", "parallel2", 1, "+PRIO=fixed +WAIT_MAX=1")
    t = find(v, ["slv_HTRANS", "slv_HREADY"], lambda x, t: field(x["slv_HTRANS"], 0, 2) >= 2 and
             field(x["slv_HTRANS"], 4, 2) >= 2 and field(x["slv_HREADY"], 0, 1) and field(x["slv_HREADY"], 2, 1))
    draw(v, "01_parallel_access", t - 40, t + 160, m(0) + m(1) + s(0, False) + s(2, False))
    # 2. arbitration switch at the last beat of a fixed burst (priority, contention on slave 0)
    v = run("w_contention", "burst_all", 2, "+PRIO=fixed +WAIT_MAX=1")
    t = find(v, ["dbg_gnt", "slv_HBURST", "dbg_req"], lambda x, t: t > 200 and field(x["slv_HBURST"], 0, 3) in (3, 5)
             and bin(field(x["dbg_req"], 0, 3)).count("1") >= 2)
    draw(v, "02_switch_after_fixed_burst", t - 30, t + 230, m(0) + m(1) + s(0)
         + ["s0.can_switch(dbg)=dbg_canswitch[0:0]"])
    # 3. round robin at equal priority: back-to-back SINGLEs
    v = run("w_rr", "rr", 1, "+PRIO=equal")
    t = find(v, ["dbg_req"], lambda x, t: field(x["dbg_req"], 0, 3) == 7)
    draw(v, "03_round_robin_equal_prio", t - 20, t + 260,
         [f"m{i}.HTRANS=mst_HTRANS[{2*i+1}:{2*i}]:htrans" for i in range(3)]
         + [f"m{i}.HREADY=mst_HREADY[{i}:{i}]" for i in range(3)] + s(0)
         + [f"m{i}.priority=mst_priority[{2*i+1}:{2*i}]:dec" for i in range(3)])
    # 4. locked burst: other masters wait until the locked sequence ends
    v = run("w_lock", "lock", 1, "+PRIO=equal +WAIT_MAX=1")
    t = find(v, ["mst_HMASTLOCK", "dbg_req"], lambda x, t: field(x["mst_HMASTLOCK"], 0, 1)
             and bin(field(x["dbg_req"], 0, 3)).count("1") >= 2)
    draw(v, "04_locked_burst", t - 30, t + 230, m(0)[:3] + ["m0.HMASTLOCK=mst_HMASTLOCK[0:0]"]
         + m(1)[:1] + ["m1.HREADY=mst_HREADY[1:1]"] + m(2)[:1] + ["m2.HREADY=mst_HREADY[2:2]"]
         + s(0) + ["s0.HMASTLOCK=slv_HMASTLOCK[0:0]"])
    # 5. slave ERROR (2 cycles) in the middle of a burst -> rest of burst cancelled
    v = run("w_error", "error", 1, "+ERR_PCT=15 +WAIT_MAX=2")
    t = find(v, ["slv_HRESP", "slv_HREADYOUT", "slv_HBURST"], lambda x, t: field(x["slv_HRESP"], 0, 1)
             and not field(x["slv_HREADYOUT"], 0, 1) and field(x["slv_HBURST"], 0, 3) not in (0,))
    draw(v, "05_slave_error_2cycle", t - 60, t + 80, m(1) + [f"m1.HRESP=mst_HRESP[1:1]"]
         + s(0, False) + ["s0.HRESP=slv_HRESP[0:0]"])
    # 6. ERROR_ON_NO_SLAVE: interconnect answers an unmapped address itself
    t = find(v, ["mst_HRESP", "mst_HADDR"], lambda x, t: field(x["mst_HRESP"], 0, 1))
    draw(v, "06_error_on_no_slave", t - 50, t + 70, m(0) + ["m0.HRESP=mst_HRESP[0:0]"]
         + [f"s{j}.HSEL=slv_HSEL[{j}:{j}]" for j in range(3)])
    # 7. ERROR_ON_SLAVE_MASK (mask build): master 2 may not use slave 0
    v = run("w_mask", "mask", 1, "+PRIO=dynamic", cfg="mask")
    t = find(v, ["mst_HRESP"], lambda x, t: field(x["mst_HRESP"], 2, 1))
    draw(v, "07_error_on_slave_mask", t - 50, t + 70, m(2) + ["m2.HRESP=mst_HRESP[2:2]",
         "s0.HSEL=slv_HSEL[0:0]", "s0.grant(dbg)=dbg_gnt[1:0]:dec"])
    # 8. reset in the middle of a burst
    v = run("w_reset", "longburst", 11, "+RESET_MID")
    t = find(v, ["HRESETn"], lambda x, t: not x["HRESETn"], start=100)
    draw(v, "08_reset_mid_burst", t - 80, t + 120, ["HRESETn=HRESETn[0:0]"] + m(0) + m(2)[:2] + s(0))
    # 9. wait states from the slave, HWDATA held stable
    v = run("w_wait", "parallel", 1, "+PRIO=fixed +WAIT_MAX=3")
    t = find(v, ["slv_HREADYOUT", "slv_HWRITE", "slv_HTRANS"], lambda x, t: t > 150 and
             not field(x["slv_HREADYOUT"], 0, 1) and field(x["slv_HWRITE"], 0, 1))
    draw(v, "09_slave_wait_states", t - 40, t + 140, m(0) + ["m0.HWDATA=mst_HWDATA[31:0]"]
         + s(0, False) + ["s0.HWDATA=slv_HWDATA[31:0]"])
    # 10. WRAP burst address wrapping
    v = run("w_wrap", "burst_all", 1, "+PRIO=fixed +WAIT_MAX=0")
    t = find(v, ["mst_HBURST", "mst_HTRANS"], lambda x, t: field(x["mst_HBURST"], 0, 3) == 4
             and field(x["mst_HTRANS"], 0, 2) == 2)
    draw(v, "10_wrap8_burst", t - 20, t + 130, m(0) + ["m0.HSIZE=mst_HSIZE[2:0]:dec"] + s(0, False))
    # 11+12. the DUT bug: BUSY inside a fixed burst -> mid-burst switch; and the fixed RTL
    for cfg, name in (("main", "11_dut_bug_busy_original"), ("fix", "12_dut_bug_busy_fixed_rtl")):
        v = run(f"w_busy_{cfg}", "busy", 1, "+PRIO=equal", cfg=cfg)
        t = 160 if cfg == "main" else 160
        draw(v, name, 160, 480, m(1) + ["m1.burst_cnt(dbg)=dbg_burst_cnt[7:4]:dec",
                                         "m1.can_switch(dbg)=dbg_mst_canswitch[1:1]"]
             + m(2)[:1] + s(0) + ["s0.HBURST=slv_HBURST[2:0]:hburst"])


if __name__ == "__main__":
    main()
