"""ahb_master.py - master agent: sequencer + pipelined driver + monitor + protocol checker.

The driver turns one AhbItem (a burst) into cycles on the bus. It is PIPELINED like a
real AHB master: while beat i is in its data phase, beat i+1 is already on the address
bus.
  ai = index of the next beat to put on the ADDRESS bus
  di = index of the beat currently in the DATA phase (-1 = none)
Rules implemented (AMBA AHB-Lite):
  * address/control are held stable while HREADY is low (wait state)
  * HWDATA for beat di is driven during its data phase and held while HREADY is low
  * BUSY may be inserted between beats of a burst (address = next beat, not a transfer)
  * an item of burst=SINGLE with length>1 is a train of back-to-back SINGLE transfers,
    each one a NONSEQ (no IDLE in between), like a CPU doing consecutive word accesses
  * ERROR is 2 cycles: on the 1st (HREADY=0,HRESP=1) the master cancels the rest of the
    burst by driving IDLE (default) or continues it (+ERR_CONTINUE)
  * reset in the middle of a burst: the burst is abandoned, bus goes IDLE
"""
import random
from pyuvm import (uvm_driver, uvm_sequencer, uvm_agent, uvm_active_passive_enum,
                   ConfigDB)

from ahb_defs import IDLE, BUSY, NONSEQ, SEQ, SINGLE, next_addr
from ahb_monitor import AhbMonitor
from ahb_checkers import AhbProtocolChecker


class AhbMasterDriver(uvm_driver):
    def build_phase(self):
        self.view = ConfigDB().get(self, "", "view")
        self.err_continue = ConfigDB().get(self, "", "err_continue", False)

    def idle_bus(self):
        self.view.drive_addr(1, 0, 0, 2, 0, IDLE, 0)
        self.view.drive_wdata(0)

    async def run_phase(self):
        self.idle_bus()
        while True:                                  # wait until reset is released
            s = await self.view.next()
            if s.rstn:
                break
        while True:
            item = await self.seq_item_port.get_next_item()
            await self.drive(item)
            self.seq_item_port.item_done()

    async def drive(self, t):
        v = self.view
        t.rdata, t.got_error, t.aborted = [], 0, 0
        for _ in range(t.idle_gap):
            self.idle_bus()
            await v.next()
        if t.prio is not None:                       # dynamic priority: set at burst start
            v.drive_prio(t.prio)
        ai, di, a = 0, -1, t.addr
        cancel = False
        prev_busy = False
        hold = None                                  # address phase held during wait states
        while (ai < t.length and not cancel) or di >= 0:
            launching = ai < t.length and not cancel
            if hold is not None and launching:
                is_busy = hold                       # HREADY was low: repeat the same phase
            else:
                is_busy = (launching and ai > 0 and not prev_busy and t.burst != SINGLE
                           and random.randrange(100) < t.busy_pct)
            if launching:
                tr = BUSY if is_busy else (NONSEQ if (ai == 0 or t.burst == SINGLE) else SEQ)
                v.drive_addr(1, a, t.write, t.size, t.burst, tr, t.lock)
            else:
                v.drive_addr(1, 0, 0, 2, 0, IDLE, 0)
            if di >= 0 and t.write:
                v.drive_wdata(t.wdata[di])
            s = await v.next()
            if not s.rstn:                           # reset in the middle of a burst
                self.idle_bus()
                t.aborted = 1
                while not (await v.next()).rstn:
                    pass
                return
            if not s.HREADY and s.HRESP and not self.err_continue:
                cancel = True                        # 1st ERROR cycle: drop the rest
            if s.HREADY:
                hold = None
                if di >= 0:
                    if not t.write:
                        t.rdata.append(s.HRDATA)
                    if s.HRESP:
                        t.got_error = 1
                        if not self.err_continue:
                            cancel = True
                if launching and not is_busy:
                    di, ai = ai, ai + 1
                    a = next_addr(a, t.size, t.burst)
                else:
                    di = -1
                prev_busy = launching and is_busy
            else:
                hold = is_busy if launching else None
        self.idle_bus()


class AhbMasterAgent(uvm_agent):
    def build_phase(self):
        self.mon = AhbMonitor("mon", self)
        self.chk = AhbProtocolChecker("chk", self)
        self.sqr = uvm_sequencer("sqr", self)
        self.drv = AhbMasterDriver("drv", self)

    def connect_phase(self):
        self.drv.seq_item_port.connect(self.sqr.seq_item_export)
