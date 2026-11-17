#!/usr/bin/env python3
"""cov_report.py - merge the coverage.json of every regression run (like `imc -merge`)
and write a text report plus charts.

  python3 scripts/cov_report.py <out_dir> <run_dir> [<run_dir> ...]
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    merged, nruns = {}, 0
    for d in sys.argv[2:]:
        for f in Path(d).glob("**/coverage.json"):
            j = json.load(open(f))
            if j["meta"].get("plusargs", {}).get("NEG_1KB"):
                continue                       # negative test does not count for coverage
            nruns += 1
            for g, bins in j["groups"].items():
                mg = merged.setdefault(g, {})
                for b, c in bins.items():
                    mg[b] = mg.get(b, 0) + c
    rows, tot_b, tot_h = [], 0, 0
    lines = [f"Merged functional coverage over {nruns} runs", ""]
    for g, bins in merged.items():
        hit = sum(1 for c in bins.values() if c)
        tot_b += len(bins); tot_h += hit
        pct = 100 * hit / len(bins)
        rows.append((g, pct, hit, len(bins)))
        lines.append(f"{g:24s} {pct:6.1f}%  ({hit}/{len(bins)} bins)")
        holes = [b for b, c in bins.items() if not c]
        if holes:
            lines.append(f"{'':24s}   holes: {', '.join(holes)}")
    overall = 100 * tot_h / tot_b
    lines += ["", f"OVERALL (bins hit / bins declared): {overall:.1f}%  ({tot_h}/{tot_b})"]
    (out / "coverage_report.txt").write_text("\n".join(lines) + "\n")
    json.dump(merged, open(out / "coverage_merged.json", "w"), indent=1)
    print("\n".join(lines))

    # ---- bar chart of all groups ----
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=150)
    names = [r[0] for r in rows][::-1]
    pcts = [r[1] for r in rows][::-1]
    cols = ["#2e7d32" if p >= 100 else "#f9a825" if p >= 80 else "#c62828" for p in pcts]
    ax.barh(names, pcts, color=cols)
    for i, (p, r) in enumerate(zip(pcts, rows[::-1])):
        ax.text(min(p, 100) + 0.8, i, f"{p:.0f}%  ({r[2]}/{r[3]})", va="center", fontsize=8)
    ax.set_xlim(0, 118)
    ax.axvline(100, color="#555", lw=0.8, ls="--")
    ax.set_xlabel("bins hit (%)")
    ax.set_title(f"Functional coverage, merged over {nruns} runs - overall {overall:.1f}%", fontsize=11)
    ax.tick_params(axis="y", labelsize=8)
    plt.tight_layout()
    fig.savefig(out / "coverage_groups.png")
    plt.close(fig)

    # ---- detail charts for the interesting groups ----
    for g in ["hburst", "x_burst_size", "contention_wait", "slave_wait", "switch_point",
              "priority_relation", "x_error_master", "htrans_transitions", "masters_requesting",
              "x_nreq_priority"]:
        if g not in merged:
            continue
        bins = merged[g]
        fig, ax = plt.subplots(figsize=(10 if len(bins) > 10 else 7, 3.6), dpi=150)
        ks = list(bins)
        vs = [bins[k] for k in ks]
        ax.bar(range(len(ks)), vs, color=["#1565c0" if v else "#c62828" for v in vs])
        ax.set_xticks(range(len(ks)))
        ax.set_xticklabels(ks, rotation=60 if len(ks) > 6 else 0, ha="right" if len(ks) > 6 else "center",
                           fontsize=7)
        ax.set_yscale("log")
        ax.set_ylabel("hits (log)")
        ax.set_title(f"{g}: {sum(1 for v in vs if v)}/{len(vs)} bins hit", fontsize=10)
        plt.tight_layout()
        fig.savefig(out / f"cov_{g}.png")
        plt.close(fig)


if __name__ == "__main__":
    main()
