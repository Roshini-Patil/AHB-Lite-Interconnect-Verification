"""test_ahb.py - the UVM test (Python version of ahb_tests.sv).

One test class; the scenario is picked with plusargs, exactly like the SV testbench:
  +VSEQ=parallel|parallel2|contention|rr|lock|longburst|burst_all|rw_same|error|mask|busy|random
  +N=n            bursts per master                 (default 20)
  +PRIO=fixed|equal|dynamic                         (default fixed: m0=2 > m1=1 > m2=0)
  +WAIT_MAX=n     max slave wait states per beat    (default 3)
  +ERR_PCT=n      % of transfers the slaves answer with ERROR (default 0)
  +BUSY_PCT=n     % chance of BUSY before each SEQ beat (default 0)
  +RESET_MID      pulse HRESETn in the middle of traffic
  +NEG_1KB        negative test: factory override -> bursts that cross 1KB (must FAIL)
  +ERR_CONTINUE   masters continue a burst after an ERROR instead of cancelling it
  +INJECT=data|err1  negative test: slave corrupts read data / gives a 1-cycle ERROR (must FAIL)
"""
import json
import os
import random

import cocotb
import pyuvm
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from pyuvm import uvm_test, uvm_factory, ConfigDB

from ahb_defs import NM, SEQ, BUSY
from ahb_bus import Hub
from ahb_env import AhbEnv
from ahb_item import AhbItem, AhbItemBad1KB
from ahb_seqs import AhbVseq
from ahb_report import ERRORS, total_errors, tb_info, tb_error
from ahb_coverage import COV

MAX_CYCLES = 200_000            # watchdog: a hung bus must not run forever


def plusarg(name, default=None, conv=str):
    v = cocotb.plusargs.get(name, None)
    if v is None:
        return default
    return True if v is True else conv(v)


@pyuvm.test()
class AhbTest(uvm_test):
    def build_phase(self):
        self.dut = cocotb.top
        self.hub = Hub(self.dut)
        self.mode = plusarg("VSEQ", "random")
        self.n = plusarg("N", 20, int)
        self.prio_mode = plusarg("PRIO", "fixed")
        self.mask_build = os.environ.get("AHB_CFG", "main") == "mask"
        ConfigDB().set(None, "*", "hub", self.hub)
        # CONFIG_DB: knobs for the reactive slaves and the drivers
        ConfigDB().set(self, "env.sagt*", "wait_max", plusarg("WAIT_MAX", 3, int))
        ConfigDB().set(self, "env.sagt*", "err_pct", plusarg("ERR_PCT", 0, int))
        ConfigDB().set(self, "env.sagt*", "inject", plusarg("INJECT", ""))
        ConfigDB().set(self, "env.magt*", "err_continue", bool(plusarg("ERR_CONTINUE", False)))
        ConfigDB().set(self, "env.sb", "masked", {2: {0}} if self.mask_build else {})
        # FACTORY: negative test swaps the item type, sequences are untouched
        if plusarg("NEG_1KB", False):
            uvm_factory().set_type_override_by_type(AhbItem, AhbItemBad1KB)
        self.env = AhbEnv("env", self)

    async def run_phase(self):
        self.raise_objection()
        h = self.hub
        tb_info("TEST", f"VSEQ={self.mode} N={self.n} PRIO={self.prio_mode} seed={os.environ.get("AHB_SEED")} "
                f"cfg={'mask' if self.mask_build else 'main'} plusargs={dict(cocotb.plusargs)}")
        Clock(self.dut.HCLK, 10, unit="ns").start(start_high=False)
        h.put("HRESETn", 0, 1, 0)
        self.set_prio()
        cocotb.start_soon(h.apply_loop())
        for _ in range(5):
            await FallingEdge(self.dut.HCLK)
        h.put("HRESETn", 0, 1, 1)                     # release reset (applied after next edge)
        COV.hit("priority_mode", self.prio_mode)
        if plusarg("RESET_MID", False):
            cocotb.start_soon(self.reset_mid())
        wd = cocotb.start_soon(self.watchdog())
        vs = AhbVseq("vs")
        vs.mode, vs.n = self.mode, self.n
        vs.dynamic_prio = self.prio_mode == "dynamic"
        vs.busy_pct = plusarg("BUSY_PCT", None, int)
        await vs.start(self.env.vsqr)
        await ClockCycles(self.dut.HCLK, 30)          # drain
        wd.cancel()
        self.cycles = h.cycle
        self.drop_objection()

    def set_prio(self):
        pm = self.prio_mode
        for m in range(NM):
            p = {"fixed": NM - 1 - m, "equal": 1, "dynamic": random.randrange(NM)}[pm]
            self.hub.put("mst_priority", m, 2, p)

    async def reset_mid(self):
        """Assert reset while a burst is in flight, hold 3 cycles, release, flush scoreboard."""
        h = self.hub
        await ClockCycles(self.dut.HCLK, 60)
        while True:                                   # wait for a SEQ beat on any master
            await FallingEdge(self.dut.HCLK)
            if any(h.get("mst_HTRANS", m, 2) in (SEQ, BUSY) for m in range(NM)):
                break
        tb_info("RESET", "asserting HRESETn in the middle of a burst")
        COV.hit("reset", "reset_mid_burst")
        h.put("HRESETn", 0, 1, 0)
        for _ in range(3):
            await FallingEdge(self.dut.HCLK)
        h.put("HRESETn", 0, 1, 1)
        await FallingEdge(self.dut.HCLK)
        self.env.sb.flush()
        tb_info("RESET", "reset released, scoreboard queues flushed")

    async def watchdog(self):
        await ClockCycles(self.dut.HCLK, MAX_CYCLES)
        tb_error("WATCHDOG", f"simulation still running after {MAX_CYCLES} cycles - bus hung?")
        self.drop_objection()

    def report_phase(self):
        nb = sum(a.mon.n_beats for a in self.env.magt)
        sb = sum(a.mon.n_beats for a in self.env.sagt)
        tb_info("SUMMARY", f"cycles={getattr(self, 'cycles', self.hub.cycle)} master_beats={nb} slave_beats={sb}")
        for g, pct in COV.summary().items():
            tb_info("COV", f"{g:22s} {pct:5.1f}%")
        res = "PASS" if total_errors() == 0 else "FAIL"
        if ERRORS:
            for tag, c in sorted(ERRORS.items()):
                tb_info("ERRORS", f"{tag:16s} {c}")
        print(f"AHB_RESULT: {res}   errors={total_errors()}", flush=True)
        meta = dict(test=self.mode, seed=os.environ.get("AHB_SEED"), prio=self.prio_mode,
                    plusargs={k: (v if v is not True else 1) for k, v in cocotb.plusargs.items()},
                    cfg="mask" if self.mask_build else "main", result=res,
                    errors=dict(ERRORS), cycles=getattr(self, "cycles", self.hub.cycle),
                    master_beats=nb, slave_beats=sb,
                    sb=self.env.sb.n, max_cwait=self.env.sb.max_cwait, arb=self.env.arb.stats)
        COV.dump(os.environ.get("AHB_COV_FILE", "coverage.json"), meta)
