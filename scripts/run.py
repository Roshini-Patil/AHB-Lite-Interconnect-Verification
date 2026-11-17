#!/usr/bin/env python3
"""run.py - build the DUT with Verilator and run one cocotb/pyuvm test.

  python3 scripts/run.py build [--cfg main|mask]
  python3 scripts/run.py <vseq> <seed> [+PLUSARG ...] [--cfg mask] [--waves] [--tag name]

Open-source flow:  Verilator (SV -> C++ simulator)  +  cocotb (Python <-> simulator, VPI)
                   +  pyuvm (UVM classes in Python).
Equivalent of the lab command:  irun -sv -uvm -f rtl.f -f tb.f +UVM_TESTNAME=... -svseed N
"""
import os
import sys
import shutil
from pathlib import Path

from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parent.parent
RTL = ["ahb3lite_pkg.sv", "ahb3lite_interconnect_slave_priority.sv",
       "ahb3lite_interconnect_slave_port.sv", "ahb3lite_interconnect_master_port.sv",
       "ahb3lite_interconnect.sv"]
SOURCES = [ROOT / "rtl" / f for f in RTL] + [ROOT / "tb" / "ahb_ic_wrap.sv"]


def build_dir(cfg):
    return ROOT / "sim" / f"build_{cfg}"


def sources(cfg):
    if cfg != "fix":
        return SOURCES
    # same RTL, except the master port with the one-line burst-counter fix
    return [ROOT / "rtl_fix" / f if f == "ahb3lite_interconnect_master_port.sv" else ROOT / "rtl" / f
            for f in RTL] + [ROOT / "tb" / "ahb_ic_wrap.sv"]


def build(cfg):
    defines = {"ALTERA_RESERVED_QIS": 1}          # use the module version of the priority tree
    if cfg == "mask":
        defines["MASK_CFG"] = 1
    r = get_runner("verilator")
    r.build(sources=sources(cfg), hdl_toplevel="ahb_ic_wrap", build_dir=build_dir(cfg),
            defines=defines, timescale=("1ns", "1ps"), waves=True, always=True,
            build_args=["--timing", "-Wno-fatal", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC",
                        "--trace-depth", "4", "-j", "2"])


def test(vseq, seed, plusargs, cfg, waves, tag):
    name = tag or f"{vseq}_{seed}"
    tdir = ROOT / "sim" / "runs" / name
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "tb"))          # runner exports sys.path as PYTHONPATH
    r = get_runner("verilator")
    r.test(test_module="test_ahb", hdl_toplevel="ahb_ic_wrap", hdl_toplevel_lang="verilog", build_dir=build_dir(cfg),
           test_dir=tdir, seed=seed, waves=waves,
           plusargs=[f"+VSEQ={vseq}"] + plusargs,
           extra_env={"AHB_CFG": cfg, "AHB_SEED": str(seed),
                      "AHB_COV_FILE": str(tdir / "coverage.json"),
                      "COCOTB_LOG_LEVEL": "INFO"})


def main(argv):
    cfg = "main"
    if "--cfg" in argv:
        i = argv.index("--cfg"); cfg = argv[i + 1]; del argv[i:i + 2]
    waves = "--waves" in argv
    argv = [a for a in argv if a != "--waves"]
    tag = None
    if "--tag" in argv:
        i = argv.index("--tag"); tag = argv[i + 1]; del argv[i:i + 2]
    if argv[0] == "build":
        build(cfg)
        return
    vseq, seed = argv[0], int(argv[1]) if len(argv) > 1 else 1
    test(vseq, seed, argv[2:], cfg, waves, tag)


if __name__ == "__main__":
    main(sys.argv[1:])
