"""ahb_env.py - environment: 3 master agents, 3 slave agents, scoreboard, coverage,
arbitration checker and the virtual sequencer.

          +-----------+                      +-----------+
 vseq --> | magt0..2  |---(DUT: interconnect)| sagt0..2  |  reactive slaves
          | sqr drv   |                      | rsp       |
          | mon chk   |                      | mon chk   |
          +-----+-----+                      +-----+-----+
                | m_imp                            | s_imp
                +---------> scoreboard <-----------+
                               | cov_ap
                               v
                             coverage        arb checker watches all slave ports
"""
from pyuvm import uvm_env, uvm_sequencer, ConfigDB

from ahb_defs import NM, NS
from ahb_bus import PortView
from ahb_master import AhbMasterAgent
from ahb_slave import AhbSlaveAgent
from ahb_scoreboard import AhbScoreboard, AhbCov
from ahb_checkers import AhbArbChecker


class AhbVsqr(uvm_sequencer):
    """Virtual sequencer: holds handles to the 3 master sequencers (it drives nothing)."""

    def build_phase(self):
        self.msqr = [None] * NM


class AhbEnv(uvm_env):
    def build_phase(self):
        hub = ConfigDB().get(self, "", "hub")
        self.magt, self.sagt = [], []
        for i in range(NM):
            ConfigDB().set(self, f"magt{i}*", "view", PortView(hub, "m", i))
            ConfigDB().set(self, f"magt{i}*", "pid", i)
            self.magt.append(AhbMasterAgent(f"magt{i}", self))
        for j in range(NS):
            ConfigDB().set(self, f"sagt{j}*", "view", PortView(hub, "s", j))
            ConfigDB().set(self, f"sagt{j}*", "pid", j)
            self.sagt.append(AhbSlaveAgent(f"sagt{j}", self))
        self.sb = AhbScoreboard("sb", self)
        self.cov = AhbCov("cov", self)
        self.arb = AhbArbChecker("arb", self)
        self.vsqr = AhbVsqr("vsqr", self)

    def connect_phase(self):
        for i in range(NM):
            self.magt[i].mon.ap.connect(self.sb.m_imp)
            self.vsqr.msqr[i] = self.magt[i].sqr
        for j in range(NS):
            self.sagt[j].mon.ap.connect(self.sb.s_imp)
        self.sb.cov_ap.connect(self.cov.analysis_export)
