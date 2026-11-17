#!/usr/bin/env python3
"""vcd2png.py - draw selected signals of a Verilator VCD as a waveform picture.

GTKWave is the usual viewer (gtkwave sim/runs/<test>/dump.vcd); this script makes the
same kind of picture for slides without a GUI.

  python3 scripts/vcd2png.py <dump.vcd> <out.png> <t_start_ns> <t_end_ns> <sigspec> [<sigspec> ...]
  sigspec = label=vector[hi:lo]            e.g.  "m0.HTRANS=mst_HTRANS[1:0]"
            label=vector[hi:lo]:enum       enum = htrans | hburst | hex | dec   (default: bit or hex)
"""
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ENUMS = {
    "htrans": {0: "IDLE", 1: "BUSY", 2: "NONSEQ", 3: "SEQ"},
    "hburst": {0: "SINGLE", 1: "INCR", 2: "WRAP4", 3: "INCR4", 4: "WRAP8", 5: "INCR8", 6: "WRAP16", 7: "INCR16"},
}


def parse_vcd(path, wanted):
    """Return {name: [(time_ps, int_value), ...]} for wanted top-level names."""
    ids, scope, timescale_ps = {}, [], 1
    changes = {n: [] for n in wanted}
    t = 0
    with open(path) as f:
        header = True
        for line in f:
            line = line.strip()
            if header:
                if line.startswith("$timescale"):
                    ts = line
                    if "$end" not in ts:
                        ts += next(f).strip()
                    m = re.search(r"(\d+)\s*(fs|ps|ns|us)", ts)
                    timescale_ps = int(m.group(1)) * {"fs": 1e-3, "ps": 1, "ns": 1e3, "us": 1e6}[m.group(2)]
                elif line.startswith("$scope"):
                    scope.append(line.split()[2])
                elif line.startswith("$upscope"):
                    scope.pop()
                elif line.startswith("$var"):
                    p = line.split()
                    code, name = p[3], p[4]
                    if len(scope) <= 2 and name in wanted and name not in ids.values():
                        ids.setdefault(code, name)
                elif line.startswith("$enddefinitions"):
                    header = False
                continue
            if not line:
                continue
            c = line[0]
            if c == "#":
                t = int(line[1:]) * timescale_ps
            elif c in "01xzXZ":
                code = line[1:]
                if code in ids:
                    changes[ids[code]].append((t, 1 if c == "1" else 0))
            elif c in "bB":
                val, code = line[1:].split()
                if code in ids:
                    v = int(val.replace("x", "0").replace("z", "0").replace("X", "0").replace("Z", "0"), 2)
                    changes[ids[code]].append((t, v))
    return changes


def value_at(ch, t):
    v = 0
    for tt, vv in ch:
        if tt > t:
            break
        v = vv
    return v


def main():
    vcd, out, t0, t1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    specs = []
    for s in sys.argv[5:]:
        label, rest = s.split("=", 1)
        enum = None
        if rest.count(":") == 2 or (":" in rest and "]" in rest and rest.rsplit(":", 1)[1].isalpha()):
            rest, enum = rest.rsplit(":", 1)
        m = re.match(r"(\w+)(?:\[(\d+):(\d+)\])?$", rest)
        name, hi, lo = m.group(1), m.group(2), m.group(3)
        hi = int(hi) if hi is not None else None
        lo = int(lo) if lo is not None else None
        specs.append((label, name, hi, lo, enum))
    ch = parse_vcd(vcd, {s[1] for s in specs})
    t0p, t1p = t0 * 1000, t1 * 1000
    clk_period = 10000
    n = len(specs) + 1
    fig, ax = plt.subplots(figsize=(16, 0.42 * n + 1.0), dpi=150)
    bg, fg, grid = "#101418", "#4fe36b", "#2a3138"
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    rowh = 1.0

    def y(i):
        return (n - 1 - i) * rowh

    # clock row
    xs, ys = [], []
    t = (t0p // clk_period) * clk_period
    while t <= t1p:
        for (dt, v) in ((0, 0), (clk_period / 2, 1)):
            xs += [t + dt, t + dt]
            ys += [ys[-1] if ys else 0, v]
        t += clk_period
    ax.plot([x / 1000 for x in xs], [y(0) + 0.15 + 0.6 * v for v in ys], color="#e0e0e0", lw=1)
    ax.text(t0 - (t1 - t0) * 0.005, y(0) + 0.45, "HCLK", color="#e0e0e0", ha="right", va="center",
            fontsize=8, family="monospace")
    # vertical grid on rising edges
    t = (t0p // clk_period) * clk_period + clk_period / 2
    while t <= t1p:
        ax.axvline(t / 1000, color=grid, lw=0.6, zorder=0)
        t += clk_period
    for i, (label, name, hi, lo, enum) in enumerate(specs, start=1):
        seq = ch.get(name, [])
        def sl(v):
            if hi is None:
                return v
            return (v >> lo) & ((1 << (hi - lo + 1)) - 1)
        width = 1 if (hi is not None and hi == lo) else (hi - lo + 1 if hi is not None else 32)
        pts = [(t0p, sl(value_at(seq, t0p)))] + [(tt, sl(vv)) for tt, vv in seq if t0p < tt <= t1p]
        # merge identical consecutive values
        segs = []
        for tt, vv in pts:
            if not segs or segs[-1][1] != vv:
                segs.append([tt, vv])
        yy = y(i)
        ax.text(t0 - (t1 - t0) * 0.005, yy + 0.45, label, color="#e0e0e0", ha="right", va="center",
                fontsize=8, family="monospace")
        for k, (ts, v) in enumerate(segs):
            te = segs[k + 1][0] if k + 1 < len(segs) else t1p
            a, b = ts / 1000, te / 1000
            if width == 1 and enum is None:
                lvl = yy + 0.15 + 0.6 * v
                ax.plot([a, b], [lvl, lvl], color=fg, lw=1.3)
                if k + 1 < len(segs):
                    ax.plot([b, b], [yy + 0.15, yy + 0.75], color=fg, lw=1.3)
            else:
                d = min(0.6, (b - a) * 0.15)
                top, bot, mid = yy + 0.8, yy + 0.1, yy + 0.45
                col = "#ffd166" if (enum == "htrans" and v == 1) else fg
                if enum == "htrans" and v == 0:
                    col = "#5d7a66"
                ax.plot([a, a + d, b - d, b], [mid, top, top, mid], color=col, lw=1)
                ax.plot([a, a + d, b - d, b], [mid, bot, bot, mid], color=col, lw=1)
                if enum in ENUMS:
                    txt = ENUMS[enum].get(v, str(v))
                elif enum == "dec":
                    txt = str(v)
                else:
                    txt = f"{v:x}"
                if (b - a) > (t1 - t0) / 70:
                    ax.text((a + b) / 2, mid, txt, color="#ffffff", ha="center", va="center",
                            fontsize=6.5 if len(txt) > 6 else 7.5, family="monospace", clip_on=True)
    ax.set_xlim(t0, t1)
    ax.set_ylim(-0.2, n * rowh)
    ax.set_yticks([])
    ax.tick_params(colors="#aaaaaa", labelsize=7)
    for sp in ax.spines.values():
        sp.set_color(grid)
    ax.set_xlabel("time (ns)", color="#aaaaaa", fontsize=8)
    plt.subplots_adjust(left=0.11, right=0.995, top=0.97, bottom=0.12 if n < 12 else 0.06)
    fig.savefig(out, facecolor=bg)
    print("wrote", out)


if __name__ == "__main__":
    main()
