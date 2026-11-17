`timescale 1ns/1ps
module tb_top;
  import uvm_pkg::*;
  `include "uvm_macros.svh"
  import ahb_defs_pkg::*;
  import ahb_pkg::*;

  logic clk = 0;
  always #5 clk = ~clk;

  rst_if      rif (clk);
  ahb_ctrl_if cif ();
  ahb_if      mif [NM] (clk, rif.rstn);      // master-side ports
  ahb_if      sif [NS] (clk, rif.rstn);      // slave-side ports

  // ---------- flat buses that go to the DUT ----------
  wire [NM-1:0]        mst_HSEL, mst_HWRITE, mst_HMASTLOCK, mst_HREADYOUT, mst_HRESP;
  wire [NM-1:0][31:0]  mst_HADDR, mst_HWDATA, mst_HRDATA;
  wire [NM-1:0][2:0]   mst_HSIZE, mst_HBURST, mst_priority;
  wire [NM-1:0][3:0]   mst_HPROT;
  wire [NM-1:0][1:0]   mst_HTRANS;
  wire [NS-1:0]        slv_HSEL, slv_HWRITE, slv_HMASTLOCK, slv_HREADY, slv_HREADYOUT, slv_HRESP;
  wire [NS-1:0][31:0]  slv_HADDR, slv_HWDATA, slv_HRDATA, slv_addr_base, slv_addr_mask;
  wire [NS-1:0][2:0]   slv_HSIZE, slv_HBURST;
  wire [NS-1:0][3:0]   slv_HPROT;
  wire [NS-1:0][1:0]   slv_HTRANS;

  assign mst_priority = cif.prio;

  for (genvar i = 0; i < NM; i++) begin : g_m
    assign mst_HSEL[i]      = mif[i].HSEL;      assign mst_HADDR[i]  = mif[i].HADDR;
    assign mst_HWDATA[i]    = mif[i].HWDATA;    assign mst_HWRITE[i] = mif[i].HWRITE;
    assign mst_HSIZE[i]     = mif[i].HSIZE;     assign mst_HBURST[i] = mif[i].HBURST;
    assign mst_HPROT[i]     = mif[i].HPROT;     assign mst_HTRANS[i] = mif[i].HTRANS;
    assign mst_HMASTLOCK[i] = mif[i].HMASTLOCK;
    assign mif[i].HRDATA    = mst_HRDATA[i];
    assign mif[i].HREADY    = mst_HREADYOUT[i];
    assign mif[i].HRESP     = mst_HRESP[i];
  end
  for (genvar j = 0; j < NS; j++) begin : g_s
    assign sif[j].HSEL      = slv_HSEL[j];      assign sif[j].HADDR  = slv_HADDR[j];
    assign sif[j].HWDATA    = slv_HWDATA[j];    assign sif[j].HWRITE = slv_HWRITE[j];
    assign sif[j].HSIZE     = slv_HSIZE[j];     assign sif[j].HBURST = slv_HBURST[j];
    assign sif[j].HPROT     = slv_HPROT[j];     assign sif[j].HTRANS = slv_HTRANS[j];
    assign sif[j].HMASTLOCK = slv_HMASTLOCK[j];
    assign slv_HRDATA[j]    = sif[j].HRDATA;
    assign slv_HREADY[j]    = sif[j].HREADYOUT;       // slave's ready output -> interconnect
    assign slv_HRESP[j]     = sif[j].HRESP;
    assign sif[j].HREADY    = slv_HREADYOUT[j];       // CHECK: ready the slave sees (see guide, step 5)
    assign slv_addr_base[j] = 32'(j) << 28;
    assign slv_addr_mask[j] = 32'hF000_0000;
  end

  // ================== DUT : CHECK EVERY PORT NAME AGAINST THE RTL FILE ==================
  ahb3lite_interconnect #(
    .HADDR_SIZE(32), .HDATA_SIZE(32), .MASTERS(NM), .SLAVES(NS),
    .ERROR_ON_NO_SLAVE(1)
  ) dut (
    .HRESETn(rif.rstn), .HCLK(clk),
    .mst_priority(mst_priority),
    .mst_HSEL(mst_HSEL), .mst_HADDR(mst_HADDR), .mst_HWDATA(mst_HWDATA), .mst_HRDATA(mst_HRDATA),
    .mst_HWRITE(mst_HWRITE), .mst_HSIZE(mst_HSIZE), .mst_HBURST(mst_HBURST), .mst_HPROT(mst_HPROT),
    .mst_HTRANS(mst_HTRANS), .mst_HMASTLOCK(mst_HMASTLOCK),
    .mst_HREADYOUT(mst_HREADYOUT), .mst_HREADY(mst_HREADYOUT), .mst_HRESP(mst_HRESP),
    .slv_addr_mask(slv_addr_mask), .slv_addr_base(slv_addr_base),
    .slv_HSEL(slv_HSEL), .slv_HADDR(slv_HADDR), .slv_HWDATA(slv_HWDATA), .slv_HRDATA(slv_HRDATA),
    .slv_HWRITE(slv_HWRITE), .slv_HSIZE(slv_HSIZE), .slv_HBURST(slv_HBURST), .slv_HPROT(slv_HPROT),
    .slv_HTRANS(slv_HTRANS), .slv_HMASTLOCK(slv_HMASTLOCK),
    .slv_HREADYOUT(slv_HREADYOUT), .slv_HREADY(slv_HREADY), .slv_HRESP(slv_HRESP)
  );

  ahb_arb_checker #(NM, NS, 3) arb (
    .clk(clk), .rst_n(rif.rstn),
    .hsel(mst_HSEL), .hlock(mst_HMASTLOCK), .hready(mst_HREADYOUT),
    .haddr(mst_HADDR), .htrans(mst_HTRANS), .hburst(mst_HBURST), .prio(mst_priority));

  initial begin
    uvm_config_db#(virtual ahb_ctrl_if)::set(null, "uvm_test_top", "cvif", cif);
    uvm_config_db#(virtual rst_if)::set(null, "uvm_test_top", "rvif", rif);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.magt0*", "vif", mif[0]);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.magt1*", "vif", mif[1]);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.magt2*", "vif", mif[2]);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.sagt0*", "vif", sif[0]);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.sagt1*", "vif", sif[1]);
    uvm_config_db#(virtual ahb_if)::set(null, "uvm_test_top.env.sagt2*", "vif", sif[2]);
    run_test();
  end

  initial begin #3ms; $display("AHB_FAIL: global timeout - sim hung"); $finish; end
endmodule
