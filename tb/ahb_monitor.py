"""ahb_monitor.py - passive monitor, the SAME class on master-side and slave-side ports.

AHB is pipelined: a transfer has an ADDRESS phase (HSEL=1, HTRANS=NONSEQ/SEQ, accepted
on the clock where HREADY=1) and then a DATA phase that ends on the next clock where
HREADY=1. The monitor remembers the accepted address phase ("pend") and finishes the
beat when the data phase completes, then broadcasts it on its analysis port.
"""
from pyuvm import uvm_component, uvm_analysis_port, ConfigDB

from ahb_item import AhbBeat
from ahb_defs import NONSEQ


class AhbMonitor(uvm_component):
    def build_phase(self):
        self.ap = uvm_analysis_port("ap", self)
        self.view = ConfigDB().get(self, "", "view")
        self.pid = ConfigDB().get(self, "", "pid")
        self.side = self.view.side
        self.n_beats = 0

    async def run_phase(self):
        pend = None
        while True:
            s = await self.view.next()
            if not s.rstn:                     # reset: forget the beat in flight
                pend = None
                continue
            if pend is not None and not s.HREADY:
                pend.wait += 1                 # data phase stretched (slave or contention)
            if s.HREADY:
                if pend is not None:           # data phase ends on this clock
                    pend.data = s.HWDATA if pend.write else s.HRDATA
                    pend.err = s.HRESP
                    if pend.err:
                        pend.wait -= 1         # 1st ERROR cycle is not a wait state
                    pend.t_done = s.t
                    self.ap.write(pend)
                    self.n_beats += 1
                    pend = None
                if s.HSEL and s.HTRANS >= NONSEQ:     # address phase accepted on this clock
                    b = AhbBeat("beat")
                    b.side, b.pid = self.side, self.pid
                    b.addr, b.write, b.size = s.HADDR, s.HWRITE, s.HSIZE
                    b.burst, b.trans, b.lock = s.HBURST, s.HTRANS, s.HMASTLOCK
                    b.t_addr = s.t
                    pend = b
