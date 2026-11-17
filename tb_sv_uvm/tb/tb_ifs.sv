import ahb_defs_pkg::*;

// reset generator that the test can pulse in the middle of a burst
interface rst_if (input logic clk);
  logic rstn;
  initial begin rstn = 0; repeat (5) @(posedge clk); rstn = 1; end
  task automatic pulse(int n);
    rstn = 0; repeat (n) @(posedge clk); rstn = 1;
  endtask
endinterface

// mstpriority control (driven by the test, goes to the DUT)
interface ahb_ctrl_if;
  logic [NM-1:0][2:0] prio;
  initial for (int i = 0; i < NM; i++) prio[i] = 3'd1;
endinterface
