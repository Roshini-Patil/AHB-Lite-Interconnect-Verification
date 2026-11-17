// Arbitration checker: watches the 3 MASTER ports (same wires that go into the DUT).
// Protocol rules: only one master accepted per slave per cycle, no switch mid-burst / while locked / during open INCR,
// higher priority must win at a switch, equal priority must not starve (round-robin).
// NOTE: arbitration "typically completes in 1 clock" - if you see false failures, check against the DUT timing diagram.
module ahb_arb_checker #(parameter int NM = 3, NS = 3, PW = 3) (
  input logic clk, rst_n,
  input logic [NM-1:0]         hsel, hlock, hready,
  input logic [NM-1:0][31:0]   haddr,
  input logic [NM-1:0][1:0]    htrans,
  input logic [NM-1:0][2:0]    hburst,
  input logic [NM-1:0][PW-1:0] prio);
  import ahb_defs_pkg::*;

  int  owner[NS], remain[NS];
  bit  locked[NS], inc_open[NS], idle_seen[NS], last_single[NS];
  int  waitgr[NM];
  bit  eqall[NM];
  int  fails = 0;

  int cv_nreq, cv_sw, cv_prio;
  bit cv_lockcont;
  covergroup cg_acc;                       // sampled on every accepted beat
    cp_nreq : coverpoint cv_nreq { bins one = {1}; bins two = {2}; bins three = {3}; }
    cp_prio : coverpoint cv_prio { bins higher = {0}; bins lower = {1}; bins equal = {2}; bins alone = {3}; }
    cp_lc   : coverpoint cv_lockcont;
    x_nreq_prio : cross cp_nreq, cp_prio;
    x_lock_cont : cross cp_lc, cp_nreq;
  endgroup
  covergroup cg_sw;                        // sampled on every master switch
    cp_swpt : coverpoint cv_sw { bins after_idle = {0}; bins after_single = {1}; bins after_last_beat = {2}; }
    cp_prio : coverpoint cv_prio { bins higher = {0}; bins lower = {1}; bins equal = {2}; }
    x_sw_prio : cross cp_swpt, cp_prio;
  endgroup
  cg_acc cga = new();
  cg_sw  cgs = new();

  function automatic void fail(input string msg);
    fails++;
    $error("AHB_FAIL: [ARB] %s", msg);
  endfunction

  always @(posedge clk) begin
    if (!rst_n) begin
      for (int s = 0; s < NS; s++) begin owner[s] = -1; remain[s] = 0; locked[s] = 0; inc_open[s] = 0; idle_seen[s] = 0; last_single[s] = 0; end
      for (int m = 0; m < NM; m++) begin waitgr[m] = 0; eqall[m] = 1; end
    end else begin
      for (int s = 0; s < NS; s++) begin
        int nacc, who, nreq, rel;
        bit [NM-1:0] req;
        nacc = 0; who = -1; nreq = 0; req = '0;
        if (owner[s] >= 0) begin
          if (htrans[owner[s]] == 2'b00 && hready[owner[s]]) begin remain[s] = 0; inc_open[s] = 0; idle_seen[s] = 1; end
          if (!hlock[owner[s]]) locked[s] = 0;
        end
        for (int m = 0; m < NM; m++)
          if (hsel[m] && htrans[m][1] && dec(haddr[m]) == s) begin
            req[m] = 1; nreq++;
            if (hready[m]) begin nacc++; who = m; end
          end
        if (nacc > 1) fail($sformatf("%0d masters accepted on slave %0d in same cycle", nacc, s));
        if (nacc == 1) begin
          rel = 3;                                        // alone
          if (nreq > 1) begin
            rel = 2;
            for (int m = 0; m < NM; m++) if (req[m] && m != who) begin
              if (prio[m] > prio[who]) rel = 1;           // someone higher is waiting (owner holding)
              else if (prio[m] < prio[who] && rel != 1) rel = 0;
            end
          end
          if (owner[s] != who) begin                      // ---- a switch ----
            if (owner[s] >= 0 && (remain[s] != 0 || locked[s] || inc_open[s]))
              fail($sformatf("slave %0d switched master %0d->%0d mid-burst/locked/INCR-open", s, owner[s], who));
            for (int m = 0; m < NM; m++)
              if (req[m] && m != who && prio[m] > prio[who])
                fail($sformatf("slave %0d: master %0d (prio %0d) won over higher-priority master %0d (prio %0d)", s, who, prio[who], m, prio[m]));
            cv_sw = (owner[s] < 0 || idle_seen[s]) ? 0 : (last_single[s] ? 1 : 2);
            cv_prio = rel; if (rel != 3) cgs.sample();
          end
          cv_nreq = nreq; cv_prio = rel; cv_lockcont = (hlock[who] && nreq > 1); cga.sample();
          // starvation / round-robin fairness: waiting master passed over by new bursts of others
          if (htrans[who] == 2'b10)
            for (int m = 0; m < NM; m++) if (req[m] && !hready[m] && m != who) begin
              waitgr[m]++;
              if (prio[m] != prio[who]) eqall[m] = 0;
              if (waitgr[m] > NM && eqall[m]) begin
                fail($sformatf("master %0d starved on slave %0d: passed over %0d times at equal priority", m, s, waitgr[m]));
                waitgr[m] = 0;
              end
            end
          waitgr[who] = 0; eqall[who] = 1;
          owner[s] = who; locked[s] = hlock[who]; idle_seen[s] = 0;
          if (htrans[who] == 2'b10) begin
            remain[s]    = (beats_of(hburst[who]) > 0) ? int'(beats_of(hburst[who])) - 1 : 0;
            inc_open[s]  = (hburst[who] == 3'd1);
            last_single[s] = (hburst[who] == 3'd0);
          end else if (htrans[who] == 2'b11 && remain[s] > 0) remain[s]--;
        end
      end
      for (int m = 0; m < NM; m++)
        if (!(hsel[m] && htrans[m][1] && !hready[m])) begin waitgr[m] = 0; eqall[m] = 1; end
    end
  end
  final $display("AHB_ARB_CHECKER: fails=%0d", fails);
endmodule
