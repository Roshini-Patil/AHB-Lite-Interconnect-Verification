"""ahb_seqs.py - sequences (Python version of ahb_seqs.sv).

AhbRandSeq : runs on ONE master sequencer; N random bursts with knobs.
AhbVseq    : VIRTUAL sequence on the virtual sequencer; starts AhbRandSeq on several
             masters at the same time (cocotb.start_soon = SV fork) to create each
             scenario, then waits for all of them (SV join).
"""
import random
import cocotb
from pyuvm import uvm_sequence

from ahb_defs import NM, SINGLE, INCR, INCR4, INCR8, INCR16, WRAP4, WRAP8, WRAP16
from ahb_item import AhbItem
from ahb_coverage import COV


class AhbRandSeq(uvm_sequence):
    def __init__(self, name="ahb_rand_seq"):
        super().__init__(name)
        self.n = 10
        self.slave = None          # fixed slave, None = random
        self.bursts = None         # list of allowed bursts, None = all 8
        self.write = None
        self.lock_pct = 0
        self.hot = False           # few addresses -> masters collide on the same words
        self.busy_pct = 0
        self.dynamic_prio = False
        self.train = False         # back-to-back SINGLE transfers

    async def body(self):
        for _ in range(self.n):
            req = AhbItem.create("req")            # FACTORY create: a test may override the type
            await self.start_item(req)
            req.randomize(slave=self.slave,
                          burst=None if self.bursts is None else random.choice(self.bursts),
                          write=self.write, hot=self.hot, train=self.train)
            req.lock = int(random.randrange(100) < self.lock_pct)
            req.busy_pct = self.busy_pct
            if self.dynamic_prio:
                req.prio = random.randrange(NM)
            await self.finish_item(req)
            if req.got_error:                       # coverage: what happened after an ERROR
                if req.length == 1:
                    COV.hit("error_rest_of_burst", "error_on_last_beat")
                else:
                    COV.hit("error_rest_of_burst", "cancelled_after_error")


FIXED = [WRAP4, INCR4, WRAP8, INCR8, WRAP16, INCR16]


class AhbVseq(uvm_sequence):
    def __init__(self, name="ahb_vseq"):
        super().__init__(name)
        self.mode = "random"
        self.n = 20
        self.dynamic_prio = False
        self.busy_pct = 0

    async def run_on(self, m, slave=None, n=None, bursts=None, lock_pct=0, hot=False,
                     write=None, busy_pct=None, train=False):
        s = AhbRandSeq(f"s{m}")
        s.n = self.n if n is None else n
        s.slave, s.bursts, s.lock_pct, s.hot, s.write = slave, bursts, lock_pct, hot, write
        s.busy_pct = (self.busy_pct or 0) if busy_pct is None else busy_pct
        s.dynamic_prio = self.dynamic_prio
        s.train = train
        await s.start(self.sequencer.msqr[m])

    async def fork_join(self, *coros):
        tasks = [cocotb.start_soon(c) for c in coros]
        for t in tasks:
            await t

    async def body(self):
        r, n = self.run_on, self.n
        md = self.mode
        if md == "parallel":        # every master on its own slave -> no contention expected
            await self.fork_join(r(0, 0), r(1, 1), r(2, 2))
        elif md == "parallel2":     # requirement wording: 2 masters, 2 different slaves
            await self.fork_join(r(0, 0), r(1, 2))
        elif md == "contention":    # all 3 masters hammer slave 0, same few addresses
            await self.fork_join(r(0, 0, hot=True), r(1, 0, hot=True), r(2, 0, hot=True))
        elif md == "rr":            # SINGLE transfers only: a switch point after every beat
            await self.fork_join(*[r(m, 0, bursts=[SINGLE], hot=True, train=True) for m in range(NM)])
        elif md == "lock":          # master 0 does LOCKED INCR8 bursts while others compete
            await self.fork_join(r(0, 0, bursts=[INCR8], lock_pct=100, hot=True),
                                 r(1, 0, hot=True), r(2, 0, hot=True))
        elif md == "longburst":     # INCR16 / INCR (undefined length) / INCR16 on one slave
            await self.fork_join(r(0, 0, bursts=[INCR16]), r(1, 0, bursts=[INCR]),
                                 r(2, 0, bursts=[INCR16]))
        elif md == "burst_all":     # every burst type in turn on master 0 while others compete
            for b in range(8):
                await self.fork_join(r(0, 0, n=3, bursts=[b], hot=True), r(1, 0, n=3, hot=True),
                                     r(2, 1, n=3))
        elif md == "rw_same":       # 2 writers + 1 reader on the same words (write ordering)
            await self.fork_join(r(0, 0, bursts=[SINGLE], hot=True, write=1),
                                 r(1, 0, bursts=[SINGLE], hot=True, write=1),
                                 r(2, 0, bursts=[SINGLE], hot=True, write=0))
        elif md == "error":         # master 0 -> unmapped addresses, others normal (+ERR_PCT)
            await self.fork_join(r(0, 3, n=max(5, n // 2)), r(1, 0), r(2, 1))
            # second phase: the other two masters also hit unmapped space (error x master)
            await self.fork_join(r(0, 1, n=5), r(1, 3, n=4), r(2, 3, n=4))
        elif md == "mask":          # (MASK build) master 2 may not use slave 0
            await self.fork_join(r(0, 0, hot=True), r(1, None), r(2, None))
        elif md == "busy":          # fixed bursts with BUSY cycles, contended slave
            bp = 30 if self.busy_pct is None else self.busy_pct
            await self.fork_join(*[r(m, 0, bursts=FIXED, hot=True, busy_pct=bp) for m in range(NM)])
        elif md == "random":
            await self.fork_join(r(0), r(1), r(2))
        else:
            raise ValueError(f"unknown VSEQ={md}")
