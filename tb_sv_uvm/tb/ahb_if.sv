// One AHB-Lite port. Used for the 3 master-side ports AND the 3 slave-side ports.
// Contains protocol assertions + HTRANS coverage, so BOTH sides are checked.
interface ahb_if (input logic HCLK, input logic HRESETn);
  import ahb_defs_pkg::*;

  logic        HSEL, HWRITE, HMASTLOCK, HREADY, HREADYOUT, HRESP;
  logic [31:0] HADDR, HWDATA, HRDATA;
  logic [2:0]  HSIZE, HBURST;
  logic [3:0]  HPROT;
  logic [1:0]  HTRANS;

  clocking mcb @(posedge HCLK);          // master driver view
    default input #1step output #1;
    output HSEL, HADDR, HWDATA, HWRITE, HSIZE, HBURST, HPROT, HTRANS, HMASTLOCK;
    input  HRDATA, HREADY, HRESP;
  endclocking

  clocking scb @(posedge HCLK);          // slave responder view
    default input #1step output #1;
    input  HSEL, HADDR, HWDATA, HWRITE, HSIZE, HBURST, HTRANS, HMASTLOCK, HREADY;
    output HRDATA, HREADYOUT, HRESP;
  endclocking

  clocking mon @(posedge HCLK);          // passive monitor view
    default input #1step;
    input HSEL, HADDR, HWDATA, HRDATA, HWRITE, HSIZE, HBURST, HTRANS, HMASTLOCK, HREADY, HRESP;
  endclocking

  // ---------- helper state (last accepted address phase) ----------
  logic [31:0] last_addr;
  logic [2:0]  last_burst, last_size;
  logic        dphase_write;
  always @(posedge HCLK or negedge HRESETn)
    if (!HRESETn) dphase_write <= 1'b0;
    else if (HREADY) begin
      dphase_write <= HSEL && HTRANS[1] && HWRITE;
      if (HSEL && HTRANS[1]) begin
        last_addr <= HADDR; last_burst <= HBURST; last_size <= HSIZE;
      end
    end

  // ---------- assertions ----------
  a_wdata_stable: assert property (@(posedge HCLK) disable iff (!HRESETn)
      (dphase_write && !HREADY) |=> $stable(HWDATA))
    else $error("AHB_FAIL: HWDATA changed while HREADY low (%m)");

  a_no_seq_after_idle: assert property (@(posedge HCLK) disable iff (!HRESETn)
      (HSEL && HREADY && HTRANS == 2'b00) |=> (HTRANS != 2'b11))
    else $error("AHB_FAIL: SEQ directly after IDLE (%m)");

  a_err_two_cycles: assert property (@(posedge HCLK) disable iff (!HRESETn)
      (HRESP && !HREADY) |=> (HRESP && HREADY))
    else $error("AHB_FAIL: ERROR response is not exactly 2 cycles (%m)");

  a_err_starts_low: assert property (@(posedge HCLK) disable iff (!HRESETn)
      $rose(HRESP) |-> !HREADY)
    else $error("AHB_FAIL: HRESP rose while HREADY high (%m)");

  // SEQ beat must follow the previous accepted beat (address increments / wraps correctly)
  always @(posedge HCLK) if (HRESETn && HSEL && HREADY && HTRANS == 2'b11) begin
    if (HADDR !== next_addr(last_addr, last_size, last_burst))
      $error("AHB_FAIL: bad burst address %h (expected %h) (%m)", HADDR,
             next_addr(last_addr, last_size, last_burst));
    if (!is_wrap(last_burst) && HADDR[31:10] !== last_addr[31:10])
      $error("AHB_FAIL: burst crosses 1KB boundary at %h (%m)", HADDR);
  end

  // ---------- HTRANS transition coverage ----------
  covergroup cg_trans @(posedge HCLK iff (HRESETn && HREADY && HSEL));
    cp_tr: coverpoint HTRANS {
      bins idle_to_nonseq   = (2'b00 => 2'b10);
      bins nonseq_to_seq    = (2'b10 => 2'b11);
      bins seq_to_seq       = (2'b11 => 2'b11);
      bins seq_to_busy      = (2'b11 => 2'b01);
      bins busy_to_seq      = (2'b01 => 2'b11);
      bins seq_to_idle      = (2'b11 => 2'b00);
      bins nonseq_to_idle   = (2'b10 => 2'b00);
      bins nonseq_to_nonseq = (2'b10 => 2'b10);
    }
  endgroup
  cg_trans cg_t = new();
endinterface
