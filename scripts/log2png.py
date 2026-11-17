#!/usr/bin/env python3
"""log2png.py - render text (a log excerpt or a command + its output) as a terminal-style
image for the slides.

  python3 scripts/log2png.py <in.txt> <out.png> [title]
Lines with UVM_ERROR/FAIL are red, PASS green, the command prompt cyan.
"""
import sys
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def main():
    src, out = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "bash"
    lines = open(src).read().rstrip("\n").split("\n")
    lines = [l.expandtabs(4) for l in lines]
    fs = 15
    font = ImageFont.truetype(FONT, fs)
    bold = ImageFont.truetype(FONT.replace(".ttf", "-Bold.ttf"), fs)
    cw = font.getbbox("M")[2]
    lh = int(fs * 1.38)
    width = max(80, min(170, max(len(l) for l in lines))) * cw + 40
    height = len(lines) * lh + 70
    img = Image.new("RGB", (width, height), "#1e1f29")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, 32], fill="#2d2f3b")
    for i, c in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([14 + i * 22, 10, 26 + i * 22, 22], fill=c)
    d.text((width // 2, 16), title, fill="#c8c8d0", font=font, anchor="mm")
    yy = 46
    for l in lines:
        col, f = "#e6e6e6", font
        if l.startswith("$ ") or l.startswith("rosh@"):
            col, f = "#8be9fd", bold
        elif "UVM_ERROR" in l or "FAIL" in l or "Error" in l:
            col = "#ff6e6e"
        elif "AHB_RESULT: PASS" in l or " PASS" in l:
            col, f = "#50fa7b", bold
        elif "WARNING" in l or "expected" in l.lower():
            col = "#f1fa8c"
        elif "[COV]" in l:
            col = "#bd93f9"
        d.text((20, yy), l[:170], fill=col, font=f)
        yy += lh
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
