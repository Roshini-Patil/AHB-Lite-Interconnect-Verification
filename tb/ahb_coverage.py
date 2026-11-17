"""ahb_coverage.py - functional coverage (Python version of the SV covergroups).

SystemVerilog has covergroup/coverpoint/bins/cross built in. Here a tiny class does the
same job: every bin is DECLARED up front (so an un-hit bin shows up as a hole), sampling
increments a counter, and at the end the hits are written to JSON. scripts/cov_report.py
merges the JSON files of all regression runs (like `imc -merge`) and draws the charts.
"""
import itertools
import json

from ahb_defs import NM, BURST_NAME, SIZE_NAME


class CoverGroup:
    def __init__(self, name, bins):
        self.name = name
        self.hits = {b: 0 for b in bins}

    def sample(self, b):
        if b not in self.hits:
            raise KeyError(f"coverage {self.name}: undeclared bin {b}")
        self.hits[b] += 1

    def pct(self):
        return 100.0 * sum(1 for v in self.hits.values() if v) / len(self.hits)


def _cross(*axes):
    return ["x".join(map(str, c)) for c in itertools.product(*axes)]


MASTERS = [f"m{i}" for i in range(NM)]
CW_BINS = ["c0", "c1", "c2_3", "c4_7", "c8up"]          # contention (interconnect) waits
SW_BINS = ["s0", "s1", "s2_3", "s4up"]                  # slave waits


def cw_bin(n):
    return "c0" if n <= 0 else "c1" if n == 1 else "c2_3" if n <= 3 else "c4_7" if n <= 7 else "c8up"


def sw_bin(n):
    return "s0" if n <= 0 else "s1" if n == 1 else "s2_3" if n <= 3 else "s4up"


class _CovDB:
    def __init__(self):
        self.reset()

    def reset(self):
        g = {}
        def add(name, bins):
            g[name] = CoverGroup(name, bins)
        # ---- per master-side beat ----
        add("htrans", ["NONSEQ", "SEQ"])
        add("hburst", list(BURST_NAME))
        add("hsize", list(SIZE_NAME))
        add("hwrite", ["READ", "WRITE"])
        add("x_burst_size", _cross(BURST_NAME, SIZE_NAME))
        add("contention_wait", CW_BINS)
        add("slave_wait", SW_BINS)
        add("x_lock_contention", _cross(["unlocked", "locked"], ["no_wait", "waited"]))
        # ---- errors ----
        # slave_mask errors exist only for master 2 (the only master with a masked slave)
        add("x_error_master", _cross(["slave_err", "no_slave"], MASTERS) + ["slave_maskxm2"])
        add("error_rest_of_burst", ["cancelled_after_error", "error_on_last_beat"])
        # ---- HTRANS transitions, both sides (SV: cg_trans) ----
        add("htrans_transitions", ["IDLE->NONSEQ", "NONSEQ->SEQ", "SEQ->SEQ", "SEQ->BUSY",
                                   "BUSY->SEQ", "SEQ->IDLE", "NONSEQ->IDLE", "NONSEQ->NONSEQ",
                                   "SEQ->NONSEQ"])
        # ---- arbitration (sampled by the arbitration checker) ----
        add("masters_requesting", ["1", "2", "3"])
        add("switch_point", ["after_idle", "after_single", "after_last_beat", "first_grant"])
        add("priority_relation", ["winner_higher", "equal", "alone"])
        add("x_nreq_priority", ["1xalone", "2xwinner_higher", "2xequal", "3xwinner_higher", "3xequal"])
        add("x_locked_contention", ["locked_alone", "locked_while_others_wait"])
        add("parallel_access", ["2_slaves_same_cycle", "3_slaves_same_cycle"])
        add("priority_mode", ["fixed", "equal", "dynamic"])
        # ---- reset ----
        add("reset", ["reset_mid_burst"])
        self.groups = g

    def hit(self, group, b):
        self.groups[group].sample(b)

    def summary(self):
        return {n: round(c.pct(), 1) for n, c in self.groups.items()}

    def dump(self, path, meta):
        out = {"meta": meta, "groups": {n: c.hits for n, c in self.groups.items()}}
        with open(path, "w") as f:
            json.dump(out, f, indent=1)


COV = _CovDB()          # one coverage database per simulation (like a singleton)
