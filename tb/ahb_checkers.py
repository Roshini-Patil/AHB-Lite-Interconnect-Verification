"""ahb_checkers.py - the "assertions" of the testbench.

SystemVerilog would write these as SVA properties (assert property ...). Here each check
is evaluated once per clock on the sampled values; a violation calls tb_error() with a
tag, which makes the test FAIL. Two components:

AhbProtocolChecker  - one per port (3 master-side + 3 slave-side), protocol rules
AhbArbChecker       - one per env, arbitration rules on every slave port
"""
from pyuvm import uvm_component, ConfigDB

from ahb_defs import (NM, NS, PW, IDLE, BUSY, NONSEQ, SEQ, INCR, SINGLE, TRANS_NAME,
                      beats_of, is_wrap, next_addr, dec)
from ahb_report import tb_error, tb_info
from ahb_coverage import COV


# ===================================================================================
class AhbProtocolChecker(uvm_component):
    """Protocol assertions on ONE port.  Tags (= SVA names in the slides):
      A_WDATA_STABLE   HWDATA stable while a write data phase is waited (HREADY low)
      A_ADDR_HOLD      address/control stable while a NONSEQ/SEQ is waited
      A_SEQ_IN_BURST   SEQ/BUSY only inside a burst: never after IDLE, NONSEQ first
      A_BURST_CTRL     HBURST/HSIZE/HWRITE constant inside a burst
      A_BURST_ADDR     SEQ address = previous + size (INCR) or wrapped (WRAP)
      A_1KB            incrementing burst never crosses a 1 KB boundary
      A_BURST_LEN      fixed-length burst not cut short (unless ERROR or reset)
      A_ERR_2CYCLE     ERROR = 2 cycles: (HRESP=1,HREADY=0) then (HRESP=1,HREADY=1)
    """

    def build_phase(self):
        self.view = ConfigDB().get(self, "", "view")
        self.where = f"{'master' if self.view.side == 'm' else 'slave'}{self.view.idx}"

    def reset_state(self):
        self.p = None
        self.in_burst = False
        self.la = None              # last accepted NONSEQ/SEQ: (addr, size, burst, write)
        self.remain = 0
        self.burst_err = False
        self.dactive = False
        self.dwrite = False
        self.last_tr = None

    def fail(self, tag, msg):
        tb_error(tag, f"{self.where}: {msg}")

    async def run_phase(self):
        self.reset_state()
        while True:
            s = await self.view.next()
            if not s.rstn:
                self.reset_state()
                continue
            p = self.p
            if p is not None:
                self.check_pair(p, s)
            if s.HREADY:
                self.on_accept(s)
            self.p = s

    def check_pair(self, p, s):
        # A_WDATA_STABLE
        if self.dactive and self.dwrite and not p.HREADY and s.HWDATA != p.HWDATA:
            self.fail("A_WDATA_STABLE", f"HWDATA {p.HWDATA:08x}->{s.HWDATA:08x} while HREADY low")
        # A_ERR_2CYCLE (both halves)
        if p.HRESP and not p.HREADY and not (s.HRESP and s.HREADY):
            self.fail("A_ERR_2CYCLE", "ERROR 1st cycle not followed by HRESP=1,HREADY=1")
        if s.HRESP and s.HREADY and not (p.HRESP and not p.HREADY):
            self.fail("A_ERR_2CYCLE", "HRESP=ERROR with HREADY=1 without the 1st (HREADY=0) cycle")
        # A_ADDR_HOLD
        if p.HSEL and p.HTRANS in (NONSEQ, SEQ) and not p.HREADY and not p.HRESP:
            if (s.HTRANS, s.HADDR, s.HWRITE, s.HSIZE, s.HBURST) != \
               (p.HTRANS, p.HADDR, p.HWRITE, p.HSIZE, p.HBURST):
                self.fail("A_ADDR_HOLD", f"address phase changed during wait: "
                          f"{TRANS_NAME[p.HTRANS]}@{p.HADDR:08x} -> {TRANS_NAME[s.HTRANS]}@{s.HADDR:08x}")

    def on_accept(self, s):
        """Called on every clock where HREADY=1 (a transfer boundary)."""
        if self.dactive and s.HRESP:
            self.burst_err = True                       # the burst got an ERROR
        self.dactive = False
        tr = s.HTRANS if s.HSEL else IDLE
        # ---- coverage of HTRANS transitions (accepted phases only) ----
        if s.HSEL and self.last_tr is not None:
            key = f"{TRANS_NAME[self.last_tr]}->{TRANS_NAME[tr]}"
            if key in COV.groups["htrans_transitions"].hits:
                COV.hit("htrans_transitions", key)
        if s.HSEL:
            self.last_tr = tr

        if tr in (SEQ, BUSY):
            if not self.in_burst:
                self.fail("A_SEQ_IN_BURST", f"{TRANS_NAME[tr]} at {s.HADDR:08x} without a preceding "
                          f"NONSEQ (e.g. SEQ after IDLE / after last beat)")
            elif self.la is not None:
                a, sz, b, wr = self.la
                if (s.HBURST, s.HSIZE, s.HWRITE) != (b, sz, wr):
                    self.fail("A_BURST_CTRL", f"control changed inside burst at {s.HADDR:08x}")
                exp = next_addr(a, sz, b)
                if s.HADDR != exp:
                    self.fail("A_BURST_ADDR", f"{TRANS_NAME[tr]} addr {s.HADDR:08x}, expected {exp:08x}")
                if not is_wrap(b) and (s.HADDR >> 10) != (a >> 10):
                    self.fail("A_1KB", f"incrementing burst crosses 1KB boundary {a:08x}->{s.HADDR:08x}")
            if tr == SEQ:
                self.la = (s.HADDR, s.HSIZE, s.HBURST, s.HWRITE)
                if self.remain > 0:
                    self.remain -= 1
                    if self.remain == 0:
                        self.in_burst = False           # fixed burst complete
        elif tr == NONSEQ or tr == IDLE:
            if self.in_burst and self.remain > 0 and not self.burst_err:
                self.fail("A_BURST_LEN", f"fixed burst cut short, {self.remain} beat(s) missing "
                          f"({'new NONSEQ' if tr == NONSEQ else 'IDLE/deselect'} at {s.HADDR:08x})")
            self.in_burst = False
            self.remain = 0
            if tr == NONSEQ:
                n = beats_of(s.HBURST)
                self.la = (s.HADDR, s.HSIZE, s.HBURST, s.HWRITE)
                self.remain = n - 1 if n > 1 else 0
                self.in_burst = (n != 1)                # INCR (n=0) or fixed > 1 beat
                self.burst_err = False
        if s.HSEL and tr >= NONSEQ:
            self.dactive = True
            self.dwrite = bool(s.HWRITE)


# ===================================================================================
class AhbArbChecker(uvm_component):
    """Arbitration checks on every slave port.  Tags:
      ARB_MODEL        granted master != reference model of the RTL arbiter
                       (priority first, then round-robin per priority level)
      ARB_PRIORITY     a master won while a HIGHER-priority master was requesting
      ARB_MID_BURST    grant moved while the owner was mid fixed-burst / locked / INCR open
      ARB_INTERLEAVE   slave saw beats of two masters inside one burst (black-box view)
      ARB_STARVATION   equal-priority master passed over more than NM-1 times
      ONE_MASTER       two masters completed a transfer on the same slave in one cycle
    White-box probes used: dbg_gnt / dbg_req / dbg_prio / dbg_canswitch (see wrapper).
    """
    RR_BOUND = NM - 1     # from RTL nxt_master(): round-robin pointer per priority level

    def build_phase(self):
        self.hub = ConfigDB().get(self, "", "hub")
        self.stats = {"max_passed_over": 0, "max_wait_cycles": 0, "grant_changes": 0,
                      "parallel_cycles": 0}

    def reset_state(self):
        self.model_gnt = [0] * NS
        self.last_gr = [[1 if lvl == 0 else 0 for lvl in range(NM)] for _ in range(NS)]  # reset 'h1
        self.prev = None
        self.ten = [dict(owner=None, remain=0, incr=False, locked=False, idle=False,
                         single=False) for _ in range(NS)]
        self.passed = [[0] * NM for _ in range(NS)]
        self.eq = [[True] * NM for _ in range(NS)]
        self.waitc = [[0] * NM for _ in range(NS)]
        self.mpend = [None] * NM

    # -------- helpers to read the sampled vectors --------
    def rd(self, s):
        h = self.hub
        req = h.get("dbg_req", s, NM)
        pr = h.get("dbg_prio", s, NM * PW)
        return dict(
            gnt=h.get("dbg_gnt", s, PW),
            req=[(req >> m) & 1 for m in range(NM)],
            prio=[(pr >> (m * PW)) & ((1 << PW) - 1) for m in range(NM)],
            cs=h.get("dbg_canswitch", s),
            srdy=h.get("slv_HREADYOUT", s),       # slave's ready = slave-port HREADY in RTL
            hsel=h.get("slv_HSEL", s), hready=h.get("slv_HREADY", s),
            htrans=h.get("slv_HTRANS", s, 2), hburst=h.get("slv_HBURST", s, 3),
            hlock=h.get("slv_HMASTLOCK", s), hresp=h.get("slv_HRESP", s))

    def rr_next(self, s, c):
        """Reference model of ahb3lite_interconnect_slave_port: who gets slave s next."""
        reqs = [m for m in range(NM) if c["req"][m]]
        lvl = max((c["prio"][m] for m in reqs), default=0)
        pm = [m for m in reqs if c["prio"][m] == lvl]
        last = self.last_gr[s][lvl]
        nxt = c["gnt"]                                    # default: keep current master
        for n in range(1, NM + 1):
            k = (last + n) % NM
            if k in pm:
                nxt = k
                break
        return nxt, lvl

    async def run_phase(self):
        self.reset_state()
        while True:
            await self.hub.next_sample()
            if not self.hub.get("HRESETn"):
                self.reset_state()
                continue
            cur = [self.rd(s) for s in range(NS)]
            naccept = 0
            for s in range(NS):
                naccept += self.check_slave(s, cur[s], None if self.prev is None else self.prev[s])
            if naccept >= 2:
                self.stats["parallel_cycles"] += 1
                COV.hit("parallel_access", "2_slaves_same_cycle" if naccept == 2 else "3_slaves_same_cycle")
            self.check_one_master()
            self.prev = cur

    def check_slave(self, s, c, p):
        t = self.ten[s]
        # ---- 1. reference model (white box) ----
        if c["gnt"] != self.model_gnt[s]:
            tb_error("ARB_MODEL", f"slave{s}: granted master {c['gnt']}, model expects {self.model_gnt[s]}")
            self.model_gnt[s] = c["gnt"]
        # ---- 2. grant changed at the last edge: check the decision ----
        if p is not None and c["gnt"] != p["gnt"]:
            self.stats["grant_changes"] += 1
            w = c["gnt"]
            reqs = [m for m in range(NM) if p["req"][m]]
            top = max((p["prio"][m] for m in reqs), default=0)
            if w not in reqs:
                tb_error("ARB_PRIORITY", f"slave{s}: master {w} granted without requesting")
            elif p["prio"][w] < top:
                tb_error("ARB_PRIORITY", f"slave{s}: master {w} (prio {p['prio'][w]}) won over a "
                         f"higher-priority request (prio {top}), req={p['req']} prio={p['prio']}")
            if t["owner"] is not None and (t["remain"] > 0 or t["locked"] or t["incr"]):
                why = (f"{t['remain']} beat(s) left" if t["remain"] > 0 else
                       "HMASTLOCK" if t["locked"] else "INCR still open")
                tb_error("ARB_MID_BURST", f"slave{s}: grant moved {t['owner']}->{w} while {why}")
            # coverage: priority relation at a switch
            others = [m for m in reqs if m != w]
            rel = "alone" if not others else ("equal" if any(p["prio"][m] == p["prio"][w] for m in others)
                                              else "winner_higher")
            COV.hit("priority_relation", rel)
            nreq = str(max(1, len(reqs)))
            if f"{nreq}x{rel}" in COV.groups["x_nreq_priority"].hits:
                COV.hit("x_nreq_priority", f"{nreq}x{rel}")
            # starvation bookkeeping: everyone still waiting was passed over once more
            for m in others:
                self.passed[s][m] += 1
                if p["prio"][m] != p["prio"][w]:
                    self.eq[s][m] = False
                self.stats["max_passed_over"] = max(self.stats["max_passed_over"], self.passed[s][m])
                if self.eq[s][m] and self.passed[s][m] > self.RR_BOUND:
                    tb_error("ARB_STARVATION", f"slave{s}: master {m} passed over {self.passed[s][m]} "
                             f"times at equal priority (RTL round-robin bound = {self.RR_BOUND})")
        for m in range(NM):                               # waiting time per master
            if c["req"][m] and c["gnt"] != m:
                self.waitc[s][m] += 1
                self.stats["max_wait_cycles"] = max(self.stats["max_wait_cycles"], self.waitc[s][m])
            else:
                self.waitc[s][m] = 0
                if not c["req"][m] or c["gnt"] == m:
                    self.passed[s][m] = 0
                    self.eq[s][m] = True
        # ---- 3. advance the reference model for the next edge ----
        if c["srdy"] and c["cs"]:
            nxt, lvl = self.rr_next(s, c)
            self.model_gnt[s] = nxt
            self.last_gr[s][lvl] = nxt
        # ---- 4. slave-side (black box) burst tenure ----
        accepted = 0
        if c["hresp"] and not c["srdy"]:                  # ERROR from the slave cancels the burst
            t["remain"], t["incr"] = 0, False
        if c["hready"]:
            if c["hsel"] and c["htrans"] >= NONSEQ:
                accepted = 1
                w = c["gnt"]
                if w != t["owner"]:
                    if t["owner"] is not None and (t["remain"] > 0 or t["locked"] or t["incr"]):
                        tb_error("ARB_INTERLEAVE", f"slave{s}: master {w} transfer while master "
                                 f"{t['owner']}'s burst/lock was open")
                    if t["owner"] is None:
                        COV.hit("switch_point", "first_grant")
                    elif t["idle"]:
                        COV.hit("switch_point", "after_idle")
                    elif t["single"]:
                        COV.hit("switch_point", "after_single")
                    else:
                        COV.hit("switch_point", "after_last_beat")
                if c["htrans"] == NONSEQ:
                    n = beats_of(c["hburst"])
                    t.update(owner=w, remain=n - 1 if n > 1 else 0, incr=(c["hburst"] == INCR),
                             locked=bool(c["hlock"]), idle=False, single=(c["hburst"] == SINGLE))
                    nreq = sum(c["req"])
                    COV.hit("masters_requesting", str(max(1, min(3, nreq))))
                    if c["hlock"]:
                        COV.hit("x_locked_contention",
                                "locked_while_others_wait" if nreq > 1 else "locked_alone")
                else:
                    t["owner"] = w
                    if c["htrans"] == SEQ and t["remain"] > 0:
                        t["remain"] -= 1
                    t["locked"] = bool(c["hlock"])
            elif not c["hsel"] or c["htrans"] == IDLE:
                t["incr"] = False
                t["idle"] = True
                t["locked"] = bool(c["hsel"] and c["hlock"])
        return accepted

    def check_one_master(self):
        """Black box, master side: per slave, at most one master may finish a transfer per cycle."""
        h = self.hub
        done = [0] * NS
        for m in range(NM):
            rdy = h.get("mst_HREADY", m)
            if rdy:
                if self.mpend[m] is not None and not h.get("mst_HRESP", m):
                    done[self.mpend[m]] += 1
                tr = h.get("mst_HTRANS", m, 2)
                a = h.get("mst_HADDR", m, 32)
                s = dec(a)
                self.mpend[m] = s if (h.get("mst_HSEL", m) and tr >= NONSEQ and s >= 0) else None
        for s in range(NS):
            if done[s] > 1:
                tb_error("ONE_MASTER", f"{done[s]} masters completed a transfer on slave{s} in one cycle")

    def report_phase(self):
        st = self.stats
        tb_info("ARB", f"grant_changes={st['grant_changes']} parallel_cycles={st['parallel_cycles']} "
                f"max_passed_over={st['max_passed_over']} (RTL bound {self.RR_BOUND}) "
                f"max_wait_cycles={st['max_wait_cycles']}")
