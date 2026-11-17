"""ahb_scoreboard.py - scoreboard + coverage subscriber.

Scoreboard checks (tags):
  SB_ROUTE    every master beat must appear on the slave its address decodes to, with
              the same address/control/data (nothing lost, duplicated or corrupted)
  SB_DATA     per-slave memory model: a read returns the last value written (byte lanes)
  SB_RESP     ERROR seen on one side but not the other
  SB_NOSLAVE  unmapped address must get ERROR (ERROR_ON_NO_SLAVE=1)
  SB_MASK     masked slave must get ERROR (ERROR_ON_SLAVE_MASK=1) and never reach the slave
  SB_LOST / SB_ORPHAN   leftovers at the end of the test
ORDER: the memory model is updated in SLAVE-SIDE order (the order in which the slave
monitor saw the beats), so two masters writing the same address are judged by what
the slave really received.

Wait split: a master beat waits W_m cycles; the slave-side copy of the same beat waits
W_s cycles (wait states inserted by the slave). Contention/interconnect wait = W_m - W_s.
"""
from collections import deque
from pyuvm import uvm_component, uvm_subscriber, uvm_analysis_port, ConfigDB

from ahb_defs import NM, NS, BURST_NAME, SIZE_NAME, NONSEQ, dec, lane_mask, dflt
from ahb_report import tb_error, tb_info
from ahb_coverage import COV, cw_bin, sw_bin


class AhbScoreboard(uvm_component):
    def build_phase(self):
        self.m_imp = uvm_subscriber.uvm_AnalysisImp("m_imp", self, self.write_m)
        self.s_imp = uvm_subscriber.uvm_AnalysisImp("s_imp", self, self.write_s)
        self.cov_ap = uvm_analysis_port("cov_ap", self)
        self.masked = ConfigDB().get(self, "", "masked", {})     # {master: set(slaves)}
        self.mq = [deque() for _ in range(NM)]
        self.sq = [deque() for _ in range(NS)]
        self.mem = [dict() for _ in range(NS)]
        self.n = dict(ok_wr=0, ok_rd=0, slv_err=0, noslave_err=0, mask_err=0, pairs=[0] * NS)
        self.max_cwait = 0

    def flush(self):
        """Called by the test after a reset in the middle of traffic."""
        for q in self.mq + self.sq:
            q.clear()

    # ---------------- inputs ----------------
    def write_m(self, b):
        s = dec(b.addr)
        if s < 0:
            self.n["noslave_err"] += 1
            if not b.err:
                tb_error("SB_NOSLAVE", f"master{b.pid} unmapped addr {b.addr:08x} got OKAY")
            else:
                COV.hit("x_error_master", f"no_slavexm{b.pid}")
            self.cov_ap.write(b)
            return
        if s in self.masked.get(b.pid, ()):
            self.n["mask_err"] += 1
            if not b.err:
                tb_error("SB_MASK", f"master{b.pid} access to masked slave{s} @{b.addr:08x} got OKAY")
            else:
                COV.hit("x_error_master", f"slave_maskxm{b.pid}")
            self.cov_ap.write(b)
            return
        self.mq[b.pid].append(b)
        self.try_match()

    def write_s(self, b):
        if dec(b.addr) != b.pid:
            tb_error("SB_ROUTE", f"slave{b.pid} received addr {b.addr:08x} that decodes to slave{dec(b.addr)}")
        self.sq[b.pid].append(b)
        self.try_match()

    # ---------------- matching ----------------
    def try_match(self):
        progress = True
        while progress:
            progress = False
            for s in range(NS):
                if not self.sq[s]:
                    continue
                sb = self.sq[s][0]
                for m in range(NM):
                    if not self.mq[m]:
                        continue
                    mb = self.mq[m][0]
                    if dec(mb.addr) == s and (mb.addr, mb.write, mb.size) == (sb.addr, sb.write, sb.size):
                        if m in [mm for mm, ss in self.masked.items() if s in ss]:
                            tb_error("SB_MASK", f"masked master{m} reached slave{s}")
                        self.check_pair(m, s, mb, sb)
                        self.mq[m].popleft()
                        self.sq[s].popleft()
                        progress = True
                        break

    def check_pair(self, m, s, mb, sb):
        self.n["pairs"][s] += 1
        mb.swait = sb.wait
        mb.cwait = max(0, mb.wait - sb.wait)
        self.max_cwait = max(self.max_cwait, mb.cwait)
        if mb.data != sb.data:
            tb_error("SB_ROUTE", f"m{m}->s{s} {'WR' if sb.write else 'RD'} @{sb.addr:08x}: "
                     f"data {mb.data:08x} at master vs {sb.data:08x} at slave")
        if mb.err != sb.err:
            tb_error("SB_RESP", f"m{m}->s{s} @{sb.addr:08x}: HRESP master={mb.err} slave={sb.err}")
        if sb.err:
            self.n["slv_err"] += 1
            COV.hit("x_error_master", f"slave_errxm{m}")
        else:
            k = sb.addr & ~3
            mk = lane_mask(sb.addr, sb.size)
            cur = self.mem[s].get(k, dflt(s, k))
            if sb.write:
                self.mem[s][k] = (cur & ~mk) | (sb.data & mk)
                self.n["ok_wr"] += 1
            elif (sb.data & mk) != (cur & mk):
                tb_error("SB_DATA", f"slave{s} read {sb.data & mk:08x} @{sb.addr:08x} expected "
                         f"{cur & mk:08x} (master {m})")
            else:
                self.n["ok_rd"] += 1
        self.cov_ap.write(mb)

    # ---------------- end of test ----------------
    def check_phase(self):
        for m in range(NM):
            for b in self.mq[m]:
                tb_error("SB_LOST", f"master{m} beat {b.addr:08x} wr={b.write} err={b.err} never seen at a slave")
        for s in range(NS):
            for b in self.sq[s]:
                tb_error("SB_ORPHAN", f"slave{s} beat {b.addr:08x} has no master beat")

    def report_phase(self):
        n = self.n
        tb_info("SB", f"writes_ok={n['ok_wr']} reads_ok={n['ok_rd']} slave_err={n['slv_err']} "
                f"no_slave_err={n['noslave_err']} mask_err={n['mask_err']} "
                f"pairs/slave={','.join(map(str, n['pairs']))} max_contention_wait={self.max_cwait}")


class AhbCov(uvm_subscriber):
    """Coverage of master-side beats (after the scoreboard has split the waits)."""

    def end_of_elaboration_phase(self):
        self.n = 0

    def write(self, b):
        self.n += 1
        COV.hit("htrans", "NONSEQ" if b.trans == NONSEQ else "SEQ")
        COV.hit("hburst", BURST_NAME[b.burst])
        if b.size < 3:
            COV.hit("hsize", SIZE_NAME[b.size])
            COV.hit("x_burst_size", f"{BURST_NAME[b.burst]}x{SIZE_NAME[b.size]}")
        COV.hit("hwrite", "WRITE" if b.write else "READ")
        if dec(b.addr) >= 0 and not b.err:
            COV.hit("contention_wait", cw_bin(b.cwait))
            COV.hit("slave_wait", sw_bin(b.swait))
            COV.hit("x_lock_contention", f"{'locked' if b.lock else 'unlocked'}x"
                                         f"{'waited' if b.cwait > 0 else 'no_wait'}")
