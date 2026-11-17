#!/usr/bin/env python3
"""regress.py - run the whole regression, print a PASS/FAIL table, merge coverage.

  python3 scripts/regress.py            (about 3-4 minutes)

Every run is listed with: test, seed, plusargs, DUT config, expected result.
  expect=PASS   sign-off run on the ORIGINAL RoaLogic RTL (counts for coverage)
  expect=FAIL   negative test (fault injected on purpose) or the known DUT bug:
                the run must FAIL, otherwise the checker is broken
  cfg=fix       same test on the RTL with the one-line burst-counter fix
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNS = []
def add(test, seeds, args="", cfg="main", expect="PASS", group="signoff"):
    for s in seeds:
        RUNS.append(dict(test=test, seed=s, args=args, cfg=cfg, expect=expect, group=group))

add("parallel",   [1, 2, 3], "+PRIO=fixed +WAIT_MAX=3")
add("parallel",   [4, 5], "+PRIO=equal +BUSY_PCT=20")          # BUSY without contention
add("parallel2",  [1, 2], "+PRIO=fixed")
add("contention", [1, 2, 3, 4, 5], "+PRIO=dynamic +WAIT_MAX=4")
add("contention", [6, 7], "+PRIO=fixed +WAIT_MAX=2")
add("contention", [8, 9], "+PRIO=equal +WAIT_MAX=2")
add("rr",         [1, 2, 3, 4, 5], "+PRIO=equal")
add("lock",       [1, 2, 3], "+PRIO=dynamic +WAIT_MAX=3")
add("lock",       [4], "+PRIO=equal")
add("longburst",  [1, 2, 3], "+PRIO=fixed")
add("burst_all",  [1, 2, 3], "+PRIO=dynamic +WAIT_MAX=3")
add("rw_same",    [1, 2, 3], "+PRIO=equal")
add("error",      [1, 2, 3], "+ERR_PCT=15 +WAIT_MAX=4")
add("error",      [4], "+ERR_PCT=15 +ERR_CONTINUE")
add("random",     [1, 2, 3, 4, 5], "+PRIO=dynamic +WAIT_MAX=4 +ERR_PCT=5")
add("longburst",  [11], "+RESET_MID")
add("random",     [12], "+PRIO=dynamic +RESET_MID")
add("busy",       [1, 2, 3], "+PRIO=equal +BUSY_PCT=0")         # fixed bursts, no BUSY
add("mask",       [1, 2, 3], "+PRIO=dynamic", cfg="mask")
# ---- the DUT bug: BUSY inside a fixed burst under contention ----
add("busy",       [1, 2, 3], "+PRIO=equal", expect="FAIL", group="dut_bug")
add("busy",       [1, 2, 3], "+PRIO=equal", cfg="fix", group="dut_fix")
# ---- negative tests: prove the checkers can fail ----
add("random",     [7], "+NEG_1KB", expect="FAIL", group="negative")
add("random",     [7], "+INJECT=data", expect="FAIL", group="negative")
add("error",      [7], "+ERR_PCT=15 +INJECT=err1", expect="FAIL", group="negative")


def tag_of(r):
    t = f"{r['test']}_{r['seed']}"
    extra = {"dut_bug": "_bug", "dut_fix": "_fix", "negative": ""}.get(r["group"], "")
    if r["group"] == "negative":
        extra = "_" + r["args"].split()[-1].strip("+").replace("=", "_").lower()
    if r["group"] == "signoff":
        if "+RESET_MID" in r["args"]:
            extra = "_resetmid"
        elif "BUSY_PCT=20" in r["args"]:
            extra = "_busy20"
        elif r["test"] == "busy":
            extra = "_nobusy"
        elif "ERR_CONTINUE" in r["args"]:
            extra = "_errcont"
    return f"rg_{t}{extra}"


def main():
    out = ROOT / "sim" / "regress"
    out.mkdir(parents=True, exist_ok=True)
    for cfg in sorted({r["cfg"] for r in RUNS}):
        subprocess.run(["./run.sh", "build", "--cfg", cfg], cwd=ROOT, capture_output=True)
    rows, t0 = [], time.time()
    for r in RUNS:
        tag = tag_of(r)
        cmd = ["./run.sh", r["test"], str(r["seed"])] + r["args"].split() + ["--cfg", r["cfg"], "--tag", tag]
        t1 = time.time()
        subprocess.run(cmd, cwd=ROOT, capture_output=True)
        dt = time.time() - t1
        cj = ROOT / "sim" / "runs" / tag / "coverage.json"
        meta = json.load(open(cj))["meta"] if cj.exists() else {}
        res = meta.get("result", "CRASH")
        ok = (res == r["expect"])
        rows.append(dict(r, tag=tag, result=res, ok=ok, secs=round(dt, 1),
                         cycles=meta.get("cycles", 0), beats=meta.get("master_beats", 0),
                         errors=sum(meta.get("errors", {}).values()),
                         error_tags=",".join(sorted(meta.get("errors", {}))),
                         max_cwait=meta.get("max_cwait", 0),
                         passed_over=meta.get("arb", {}).get("max_passed_over", 0)))
        print(f"{tag:34s} {r['cfg']:5s} {r['args']:42s} {res:5s} expect={r['expect']:4s} "
              f"{'OK ' if ok else 'BAD'} {dt:5.1f}s", flush=True)
    total = time.time() - t0
    # ---- summary table ----
    lines = ["| # | run | cfg | plusargs | cycles | beats | result | expected | verdict |",
             "|---|-----|-----|----------|-------:|------:|--------|----------|---------|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['tag'][3:]} | {r['cfg']} | `{r['args']}` | {r['cycles']} | {r['beats']} | "
                     f"{r['result']} | {r['expect']} | {'OK' if r['ok'] else '**MISMATCH**'} |")
    so = [r for r in rows if r["group"] == "signoff"]
    lines += ["", f"Sign-off runs: {len(so)}, passed {sum(r['result'] == 'PASS' for r in so)}; "
              f"all runs as expected: {all(r['ok'] for r in rows)}; wall time {total:.0f}s; "
              f"total cycles {sum(r['cycles'] for r in rows)}, master beats {sum(r['beats'] for r in rows)}"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    json.dump(rows, open(out / "summary.json", "w"), indent=1)
    print("\n".join(lines[-1:]))
    # ---- merged coverage over the sign-off runs only ----
    dirs = [str(ROOT / "sim" / "runs" / r["tag"]) for r in so]
    subprocess.run([sys.executable, str(ROOT / "scripts" / "cov_report.py"), str(out / "coverage")] + dirs)


if __name__ == "__main__":
    main()
