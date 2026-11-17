"""ahb_bus.py - how the Python testbench touches the DUT wires.

In SystemVerilog UVM the driver/monitor get a *virtual interface* through config_db.
Here they get a PortView object through ConfigDB instead. A PortView is "one AHB
port" (master port m, or slave port s) on top of the flat vectors of ahb_ic_wrap.

Timing rule (same idea as the SV clocking block, default input #1step output #1):
  * SAMPLE at the FALLING edge: by mid-cycle every combinational path has settled,
    so what we read is exactly what the flops will capture at the next rising edge.
  * DRIVE just AFTER the RISING edge: components only *stage* new values; the Hub
    writes all staged values right after the rising edge, so the DUT flops have
    already captured the old values (no race).
"""
import cocotb
from cocotb.triggers import RisingEdge, FallingEdge
from cocotb.simtime import get_sim_time

from ahb_defs import NM, NS, PW

# signals the TESTBENCH drives  -> (vector name, field width)
DRIVEN = {
    "HRESETn": 1,
    "mst_priority": PW, "mst_HSEL": 1, "mst_HADDR": 32, "mst_HWDATA": 32, "mst_HWRITE": 1,
    "mst_HSIZE": 3, "mst_HBURST": 3, "mst_HPROT": 4, "mst_HTRANS": 2, "mst_HMASTLOCK": 1,
    "slv_HRDATA": 32, "slv_HREADYOUT": 1, "slv_HRESP": 1,
}
# signals the DUT drives (we only read them)
SAMPLED = [
    "mst_HRDATA", "mst_HREADY", "mst_HRESP",
    "slv_HSEL", "slv_HADDR", "slv_HWDATA", "slv_HWRITE", "slv_HSIZE", "slv_HBURST",
    "slv_HPROT", "slv_HTRANS", "slv_HMASTLOCK", "slv_HREADY",
    "dbg_gnt", "dbg_req", "dbg_prio", "dbg_canswitch", "dbg_mst_canswitch", "dbg_burst_cnt",
]


def _to_int(v):
    try:
        return v.to_unsigned()
    except AttributeError:
        return int(v)


class Hub:
    """One per simulation. Owns the flat vectors, applies staged writes, caches samples."""

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.HCLK
        self.handles = {n: getattr(dut, n) for n in list(DRIVEN) + SAMPLED}
        self.drv = {n: 0 for n in DRIVEN}
        self.dirty = set(DRIVEN)
        self.snap = {}
        self.snap_t = None
        self.cycle = 0

    # ---- driving ----
    def put(self, name, idx, width, val):
        mask = ((1 << width) - 1) << (idx * width)
        new = (self.drv[name] & ~mask) | ((val & ((1 << width) - 1)) << (idx * width))
        if new != self.drv[name]:
            self.drv[name] = new
            self.dirty.add(name)

    def apply_now(self):
        for n in self.dirty:
            self.handles[n].value = self.drv[n]
        self.dirty.clear()

    async def apply_loop(self):
        self.apply_now()
        while True:
            await RisingEdge(self.clk)
            self.cycle += 1
            self.apply_now()

    # ---- sampling ----
    def sample(self):
        t = get_sim_time("step")
        if t != self.snap_t:
            self.snap = {n: _to_int(h.value) for n, h in self.handles.items()}
            self.snap_t = t
        return self.snap

    def get(self, name, idx=0, width=1):
        return (self.snap[name] >> (idx * width)) & ((1 << width) - 1)

    async def next_sample(self):
        await FallingEdge(self.clk)
        return self.sample()

    def now_ns(self):
        return get_sim_time("ns")


class Sample:
    """Plain record of one port in one cycle (what a clocking block would give you)."""
    __slots__ = ("rstn", "HSEL", "HADDR", "HWDATA", "HRDATA", "HWRITE", "HSIZE", "HBURST",
                 "HPROT", "HTRANS", "HMASTLOCK", "HREADY", "HREADYOUT", "HRESP", "t")


class PortView:
    """'Virtual interface' for one AHB port. side = 'm' (master port m) or 's' (slave port s)."""

    def __init__(self, hub, side, idx):
        self.hub, self.side, self.idx = hub, side, idx

    async def next(self):
        await self.hub.next_sample()
        return self.read()

    def read(self):
        h, i = self.hub, self.idx
        h.sample()
        r = Sample()
        r.rstn = h.get("HRESETn")
        r.t = h.now_ns()
        if self.side == "m":
            r.HSEL = h.get("mst_HSEL", i, 1);      r.HADDR = h.get("mst_HADDR", i, 32)
            r.HWDATA = h.get("mst_HWDATA", i, 32); r.HRDATA = h.get("mst_HRDATA", i, 32)
            r.HWRITE = h.get("mst_HWRITE", i, 1);  r.HSIZE = h.get("mst_HSIZE", i, 3)
            r.HBURST = h.get("mst_HBURST", i, 3);  r.HPROT = h.get("mst_HPROT", i, 4)
            r.HTRANS = h.get("mst_HTRANS", i, 2);  r.HMASTLOCK = h.get("mst_HMASTLOCK", i, 1)
            r.HREADY = h.get("mst_HREADY", i, 1);  r.HREADYOUT = r.HREADY
            r.HRESP = h.get("mst_HRESP", i, 1)
        else:
            r.HSEL = h.get("slv_HSEL", i, 1);      r.HADDR = h.get("slv_HADDR", i, 32)
            r.HWDATA = h.get("slv_HWDATA", i, 32); r.HRDATA = h.get("slv_HRDATA", i, 32)
            r.HWRITE = h.get("slv_HWRITE", i, 1);  r.HSIZE = h.get("slv_HSIZE", i, 3)
            r.HBURST = h.get("slv_HBURST", i, 3);  r.HPROT = h.get("slv_HPROT", i, 4)
            r.HTRANS = h.get("slv_HTRANS", i, 2);  r.HMASTLOCK = h.get("slv_HMASTLOCK", i, 1)
            r.HREADY = h.get("slv_HREADY", i, 1)   # HREADY the slave sees
            r.HREADYOUT = h.get("slv_HREADYOUT", i, 1)
            r.HRESP = h.get("slv_HRESP", i, 1)
        return r

    # ---- master-side drive helpers (staged, applied after next rising edge) ----
    def drive_addr(self, sel, addr, write, size, burst, trans, lock, prot=0b0011):
        h, i = self.hub, self.idx
        h.put("mst_HSEL", i, 1, sel);     h.put("mst_HADDR", i, 32, addr)
        h.put("mst_HWRITE", i, 1, write); h.put("mst_HSIZE", i, 3, size)
        h.put("mst_HBURST", i, 3, burst); h.put("mst_HTRANS", i, 2, trans)
        h.put("mst_HMASTLOCK", i, 1, lock); h.put("mst_HPROT", i, 4, prot)

    def drive_wdata(self, d):
        self.hub.put("mst_HWDATA", self.idx, 32, d)

    def drive_prio(self, p):
        self.hub.put("mst_priority", self.idx, PW, p)

    # ---- slave-side drive helpers ----
    def drive_resp(self, ready, resp, rdata=None):
        h, i = self.hub, self.idx
        h.put("slv_HREADYOUT", i, 1, ready)
        h.put("slv_HRESP", i, 1, resp)
        if rdata is not None:
            h.put("slv_HRDATA", i, 32, rdata)
