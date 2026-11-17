"""ahb_slave.py - REACTIVE slave agent (Python version of ahb_slave.sv).

A reactive slave has no sequence telling it what to do. It watches the bus and answers
whatever address phase the interconnect sends it:
  * random number of wait states (HREADYOUT=0) per transfer, 0..wait_max
  * random ERROR response with probability err_pct, always TWO cycles:
        cycle 1: HREADYOUT=0, HRESP=1     cycle 2: HREADYOUT=1, HRESP=1
  * a memory with byte lanes, so BYTE/HALF/WORD writes only change their own lanes
Knobs come from ConfigDB (set by the test from +WAIT_MAX / +ERR_PCT).
"""
import random
from pyuvm import uvm_component, uvm_agent, ConfigDB

from ahb_defs import NONSEQ, lane_mask, dflt
from ahb_monitor import AhbMonitor
from ahb_checkers import AhbProtocolChecker


class AhbSlaveResponder(uvm_component):
    def build_phase(self):
        self.view = ConfigDB().get(self, "", "view")
        self.pid = ConfigDB().get(self, "", "pid")
        self.wait_max = ConfigDB().get(self, "", "wait_max", 3)
        self.err_pct = ConfigDB().get(self, "", "err_pct", 0)
        self.inject = ConfigDB().get(self, "", "inject", "")   # negative tests only
        self.mem = {}
        self.n_err = 0

    def rd(self, a):
        k = a & ~3
        return self.mem.get(k, dflt(self.pid, k))

    def present(self):
        """Decide HREADYOUT/HRESP/HRDATA for the NEXT cycle."""
        if self.wl > 0:
            self.view.drive_resp(0, 0)                     # wait state
        elif self.d_err:
            self.view.drive_resp(0, 1)                     # ERROR cycle 1
            self.in_err2 = True
        else:
            d = None if self.d_wr else self.rd(self.d_addr)
            if self.inject == "data" and d is not None and random.randrange(20) == 0:
                d ^= 0x0000_0100                           # FAULT: flip one read-data bit
            self.view.drive_resp(1, 0, d)

    def clear(self):
        self.d_valid = self.d_err = self.in_err2 = False
        self.d_wr, self.d_addr, self.d_sz, self.wl = 0, 0, 0, 0

    async def run_phase(self):
        self.clear()
        self.view.drive_resp(1, 0, 0)
        while True:
            s = await self.view.next()
            if not s.rstn:
                self.clear()
                self.view.drive_resp(1, 0)
                continue
            if s.HREADY:                                  # a transfer boundary
                if self.d_valid and self.d_wr and not self.d_err:   # finish previous write
                    m = lane_mask(self.d_addr, self.d_sz)
                    k = self.d_addr & ~3
                    self.mem[k] = (self.rd(self.d_addr) & ~m) | (s.HWDATA & m)
                self.in_err2 = False
                self.d_valid = bool(s.HSEL and s.HTRANS >= NONSEQ)  # new address phase?
                if self.d_valid:
                    self.d_addr, self.d_wr, self.d_sz = s.HADDR, s.HWRITE, s.HSIZE
                    self.d_err = random.randrange(100) < self.err_pct
                    self.n_err += self.d_err
                    self.wl = random.randint(0, self.wait_max)
                    self.present()
                else:
                    self.d_err = False
                    self.view.drive_resp(1, 0)
            else:                                         # HREADY low: waiting or in ERROR
                if self.in_err2:
                    if self.inject == "err1":                 # FAULT: 1-cycle ERROR
                        self.view.drive_resp(1, 0)
                    else:
                        self.view.drive_resp(1, 1)            # ERROR cycle 2
                    self.in_err2 = False
                else:
                    if self.wl > 0:
                        self.wl -= 1
                    self.present()


class AhbSlaveAgent(uvm_agent):
    def build_phase(self):
        self.mon = AhbMonitor("mon", self)
        self.chk = AhbProtocolChecker("chk", self)
        self.rsp = AhbSlaveResponder("rsp", self)
