// ============================================================================
// ahb_ic_wrap.sv : flat-port wrapper around RoaLogic ahb3lite_interconnect
// ----------------------------------------------------------------------------
// Why a wrapper?  The DUT uses UNPACKED array ports (mst_HADDR[MASTERS]).
// cocotb + Verilator reach top-level signals most reliably as flat vectors,
// so this wrapper packs every port into one vector:  master m, bits
// [m*W +: W].  It adds NO logic; it only renames wires.
//
// Configuration (3 masters x 3 slaves, 32-bit address/data):
//   slave j decodes HADDR[31:28] == j   (base = j<<28, mask = 0xF000_0000)
//   HADDR[31:28] >= 3  ->  no slave     (ERROR_ON_NO_SLAVE = 1 for every master)
//   `MASK_CFG defined  ->  master 2 may NOT access slave 0 and gets an ERROR
//                          (SLAVE_MASK / ERROR_ON_SLAVE_MASK test)
//
// dbg_* outputs are WHITE-BOX probes (like an SVA "bind"): they copy internal
// arbiter signals out so the Python checkers and the waveform can see who owns
// each slave.  They drive nothing back into the DUT.
// ============================================================================
`timescale 1ns/1ps
module ahb_ic_wrap #(
  parameter int NM = 3,          // masters
  parameter int NS = 3,          // slaves
  parameter int PW = 2           // priority width = $clog2(NM)
)(
  input  logic                HCLK,
  input  logic                HRESETn,
  // ---------------- master side (AHB masters drive these) ----------------
  input  logic [NM*PW-1:0]    mst_priority,
  input  logic [NM-1:0]       mst_HSEL,
  input  logic [NM*32-1:0]    mst_HADDR,
  input  logic [NM*32-1:0]    mst_HWDATA,
  output logic [NM*32-1:0]    mst_HRDATA,
  input  logic [NM-1:0]       mst_HWRITE,
  input  logic [NM*3-1:0]     mst_HSIZE,
  input  logic [NM*3-1:0]     mst_HBURST,
  input  logic [NM*4-1:0]     mst_HPROT,
  input  logic [NM*2-1:0]     mst_HTRANS,
  input  logic [NM-1:0]       mst_HMASTLOCK,
  output logic [NM-1:0]       mst_HREADY,     // = HREADYOUT, looped back (1 master per port)
  output logic [NM-1:0]       mst_HRESP,
  // ---------------- slave side (AHB slaves respond on these) -------------
  output logic [NS-1:0]       slv_HSEL,
  output logic [NS*32-1:0]    slv_HADDR,
  output logic [NS*32-1:0]    slv_HWDATA,
  input  logic [NS*32-1:0]    slv_HRDATA,
  output logic [NS-1:0]       slv_HWRITE,
  output logic [NS*3-1:0]     slv_HSIZE,
  output logic [NS*3-1:0]     slv_HBURST,
  output logic [NS*4-1:0]     slv_HPROT,
  output logic [NS*2-1:0]     slv_HTRANS,
  output logic [NS-1:0]       slv_HMASTLOCK,
  output logic [NS-1:0]       slv_HREADY,     // HREADY that the slave sees (DUT slv_HREADYOUT)
  input  logic [NS-1:0]       slv_HREADYOUT,  // slave's own ready (DUT slv_HREADY)
  input  logic [NS-1:0]       slv_HRESP,
  // ---------------- white-box debug probes -------------------------------
  output logic [NS*PW-1:0]    dbg_gnt,        // granted master index per slave port
  output logic [NS*NM-1:0]    dbg_req,        // request vector seen by each slave port
  output logic [NS*NM*PW-1:0] dbg_prio,       // priority of each master as seen by each slave port
  output logic [NS-1:0]       dbg_canswitch,  // slave port may switch master this cycle
  output logic [NM-1:0]       dbg_mst_canswitch,
  output logic [NM*4-1:0]     dbg_burst_cnt   // master-port burst counter
);
  import ahb3lite_pkg::*;

  // unpacked arrays that match the DUT port types
  logic [PW-1:0] u_prio [NM];
  logic          u_mHSEL[NM], u_mHWRITE[NM], u_mLOCK[NM], u_mRDY[NM], u_mRESP[NM];
  logic [31:0]   u_mHADDR[NM], u_mHWDATA[NM], u_mHRDATA[NM];
  logic [2:0]    u_mHSIZE[NM], u_mHBURST[NM];
  logic [3:0]    u_mHPROT[NM];
  logic [1:0]    u_mHTRANS[NM];

  logic [31:0]   u_base[NS], u_mask[NS];
  logic          u_sHSEL[NS], u_sHWRITE[NS], u_sLOCK[NS], u_sRDYO[NS], u_sRDY[NS], u_sRESP[NS];
  logic [31:0]   u_sHADDR[NS], u_sHWDATA[NS], u_sHRDATA[NS];
  logic [2:0]    u_sHSIZE[NS], u_sHBURST[NS];
  logic [3:0]    u_sHPROT[NS];
  logic [1:0]    u_sHTRANS[NS];

  for (genvar m = 0; m < NM; m++) begin : g_m
    assign u_prio[m]    = mst_priority[m*PW +: PW];
    assign u_mHSEL[m]   = mst_HSEL[m];
    assign u_mHADDR[m]  = mst_HADDR[m*32 +: 32];
    assign u_mHWDATA[m] = mst_HWDATA[m*32 +: 32];
    assign u_mHWRITE[m] = mst_HWRITE[m];
    assign u_mHSIZE[m]  = mst_HSIZE[m*3 +: 3];
    assign u_mHBURST[m] = mst_HBURST[m*3 +: 3];
    assign u_mHPROT[m]  = mst_HPROT[m*4 +: 4];
    assign u_mHTRANS[m] = mst_HTRANS[m*2 +: 2];
    assign u_mLOCK[m]   = mst_HMASTLOCK[m];
    assign mst_HRDATA[m*32 +: 32] = u_mHRDATA[m];
    assign mst_HREADY[m] = u_mRDY[m];
    assign mst_HRESP[m]  = u_mRESP[m];
    assign dbg_mst_canswitch[m]    = u_ic.frommst_canswitch[m];
    assign dbg_burst_cnt[m*4 +: 4] = u_ic.gen_master_ports[m].master_port.burst_cnt;
  end

  for (genvar s = 0; s < NS; s++) begin : g_s
    assign u_base[s] = 32'(s) << 28;
    assign u_mask[s] = 32'hF000_0000;
    assign slv_HSEL[s]          = u_sHSEL[s];
    assign slv_HADDR[s*32 +: 32]  = u_sHADDR[s];
    assign slv_HWDATA[s*32 +: 32] = u_sHWDATA[s];
    assign u_sHRDATA[s]         = slv_HRDATA[s*32 +: 32];
    assign slv_HWRITE[s]        = u_sHWRITE[s];
    assign slv_HSIZE[s*3 +: 3]  = u_sHSIZE[s];
    assign slv_HBURST[s*3 +: 3] = u_sHBURST[s];
    assign slv_HPROT[s*4 +: 4]  = u_sHPROT[s];
    assign slv_HTRANS[s*2 +: 2] = u_sHTRANS[s];
    assign slv_HMASTLOCK[s]     = u_sLOCK[s];
    assign slv_HREADY[s]        = u_sRDYO[s];
    assign u_sRDY[s]            = slv_HREADYOUT[s];
    assign u_sRESP[s]           = slv_HRESP[s];
    assign dbg_gnt[s*PW +: PW]  = u_ic.gen_slave_ports[s].slave_port.granted_master_idx;
    assign dbg_req[s*NM +: NM]  = u_ic.toslvHSEL[s];
    assign dbg_prio[s*NM*PW +: NM*PW] = u_ic.toslvpriority[s];
    assign dbg_canswitch[s]     = u_ic.gen_slave_ports[s].slave_port.can_switch_master;
  end

`ifdef MASK_CFG
  localparam bit [NS-1:0] SMASK [NM] = '{3'b111, 3'b111, 3'b110};  // [2] = master 2: slave 0 masked
  localparam bit [NS-1:0] EMASK [NM] = '{3'b000, 3'b000, 3'b001};  // ... and gets an ERROR for it
`else
  localparam bit [NS-1:0] SMASK [NM] = '{3'b111, 3'b111, 3'b111};
  localparam bit [NS-1:0] EMASK [NM] = '{3'b000, 3'b000, 3'b000};
`endif
  localparam bit          ENOSLV[NM] = '{1'b1, 1'b1, 1'b1};

  ahb3lite_interconnect #(
    .HADDR_SIZE(32), .HDATA_SIZE(32), .MASTERS(NM), .SLAVES(NS),
    .SLAVE_MASK(SMASK), .ERROR_ON_SLAVE_MASK(EMASK), .ERROR_ON_NO_SLAVE(ENOSLV)
  ) u_ic (
    .HRESETn(HRESETn), .HCLK(HCLK),
    .mst_priority(u_prio),
    .mst_HSEL(u_mHSEL), .mst_HADDR(u_mHADDR), .mst_HWDATA(u_mHWDATA), .mst_HRDATA(u_mHRDATA),
    .mst_HWRITE(u_mHWRITE), .mst_HSIZE(u_mHSIZE), .mst_HBURST(u_mHBURST), .mst_HPROT(u_mHPROT),
    .mst_HTRANS(u_mHTRANS), .mst_HMASTLOCK(u_mLOCK),
    .mst_HREADYOUT(u_mRDY), .mst_HREADY(u_mRDY), .mst_HRESP(u_mRESP),
    .slv_addr_mask(u_mask), .slv_addr_base(u_base),
    .slv_HSEL(u_sHSEL), .slv_HADDR(u_sHADDR), .slv_HWDATA(u_sHWDATA), .slv_HRDATA(u_sHRDATA),
    .slv_HWRITE(u_sHWRITE), .slv_HSIZE(u_sHSIZE), .slv_HBURST(u_sHBURST), .slv_HPROT(u_sHPROT),
    .slv_HTRANS(u_sHTRANS), .slv_HMASTLOCK(u_sLOCK),
    .slv_HREADYOUT(u_sRDYO), .slv_HREADY(u_sRDY), .slv_HRESP(u_sRESP)
  );
endmodule
