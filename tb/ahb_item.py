"""ahb_item.py - transaction classes (Python version of ahb_item.sv).

AhbItem  : one BURST requested by a sequence (what the driver executes).
AhbBeat  : one TRANSFER (beat) as observed by a monitor.

SystemVerilog has a constraint solver (rand + constraint blocks). Python does not, so
randomize() below picks values in an order that satisfies every constraint directly.
Each constraint of the SV class is marked with its SV name (c_len, c_size, ...).
cocotb seeds Python's `random` from the run seed, so a seed always reproduces a run.
"""
import random
from pyuvm import uvm_sequence_item, uvm_object

from ahb_defs import (NS, SINGLE, INCR, beats_of, is_wrap, crosses_1kb, BURST_NAME,
                      SLAVE_SHIFT)


class AhbItem(uvm_sequence_item):
    def __init__(self, name="ahb_item"):
        super().__init__(name)
        self.addr = 0
        self.write = 0
        self.burst = SINGLE       # 0 SINGLE 1 INCR 2 WRAP4 3 INCR4 4 WRAP8 5 INCR8 6 WRAP16 7 INCR16
        self.size = 2             # 0 byte 1 half 2 word
        self.lock = 0
        self.busy_pct = 0         # chance (%) of a BUSY cycle before each SEQ beat
        self.length = 1           # number of beats
        self.idle_gap = 0         # IDLE cycles before the burst starts
        self.prio = None          # per-burst priority (dynamic-priority mode), None = keep
        self.wdata = []
        # filled in by the driver
        self.rdata = []
        self.got_error = 0
        self.aborted = 0          # cut short by a reset

    # ------------------------------------------------------------------
    def randomize(self, slave=None, burst=None, write=None, hot=False, size=None, train=False):
        self.burst = random.randrange(8) if burst is None else burst
        self.write = random.randrange(2) if write is None else write
        self.size = random.randrange(3) if size is None else size            # c_size
        # c_len
        self.length = beats_of(self.burst) or random.randint(1, 8)
        if train and self.burst == SINGLE:
            self.length = random.randint(1, 4)    # back-to-back SINGLEs (each one a NONSEQ)
        # c_map: soft addr[31:28] in 0..NS-1, addr[27:12] == 0
        s = random.randrange(NS) if slave is None else slave
        nbytes = 1 << self.size
        while True:
            off = random.randrange(0, 64 if hot else 4096)                    # hot: few addresses
            off &= ~(nbytes - 1)                                              # c_align
            if is_wrap(self.burst) or not crosses_1kb(off, self.size, self.length):
                break                                                         # c_1kb
        self.addr = (s << SLAVE_SHIFT) | off
        self.wdata = [random.getrandbits(32) for _ in range(self.length)]     # c_data
        self.idle_gap = random.randint(0, 3)                                  # c_idle
        self.lock = 0                                                         # c_lock (soft)
        return True

    def __str__(self):
        return (f"{'WR' if self.write else 'RD'} addr={self.addr:08x} {BURST_NAME[self.burst]} "
                f"size={self.size} len={self.length} lock={self.lock}")


class AhbItemBad1KB(AhbItem):
    """NEGATIVE-TEST item: an incrementing burst that DOES cross a 1 KB boundary.
    A test installs it with a FACTORY override; the sequence code is unchanged."""

    def randomize(self, slave=None, burst=None, write=None, hot=False, size=None, train=False):
        super().randomize(slave=slave, burst=random.choice([3, 5, 7]), write=write, size=2)
        s = self.addr >> SLAVE_SHIFT
        self.addr = (s << SLAVE_SHIFT) | (0x400 - 8)       # 2 beats before the 1KB line
        return True


class AhbBeat(uvm_object):
    """One completed transfer seen by a monitor."""

    def __init__(self, name="ahb_beat"):
        super().__init__(name)
        self.side = "m"           # 'm' master-side monitor, 's' slave-side monitor
        self.pid = 0              # port number
        self.addr = 0
        self.data = 0
        self.write = 0
        self.size = 0
        self.burst = 0
        self.trans = 0
        self.lock = 0
        self.err = 0
        self.wait = 0             # data-phase wait cycles seen on this port
        self.cwait = 0            # contention part of the wait (filled by scoreboard)
        self.swait = 0            # slave part of the wait (filled by scoreboard)
        self.t_addr = 0
        self.t_done = 0

    def __str__(self):
        return (f"{self.side}{self.pid} {'WR' if self.write else 'RD'} {self.addr:08x} "
                f"data={self.data:08x} err={self.err} wait={self.wait}")
