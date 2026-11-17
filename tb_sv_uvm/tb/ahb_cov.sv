// Functional coverage sampled on every MASTER-side beat
class ahb_cov extends uvm_subscriber #(ahb_beat);
  `uvm_component_utils(ahb_cov)
  ahb_beat b;
  covergroup cg;
    cp_trans: coverpoint b.trans { bins nonseq = {2}; bins seq = {3}; }
    cp_burst: coverpoint b.burst { bins single = {0}; bins incr = {1}; bins wrap4 = {2}; bins incr4 = {3};
                                   bins wrap8 = {4}; bins incr8 = {5}; bins wrap16 = {6}; bins incr16 = {7}; }
    cp_size : coverpoint b.size  { bins byte_ = {0}; bins half = {1}; bins word = {2}; }
    cp_wr   : coverpoint b.write;
    cp_err  : coverpoint b.err;
    cp_pid  : coverpoint b.pid;
    cp_lock : coverpoint b.lock;
    cp_cw   : coverpoint b.cwait { bins none = {0}; bins c1 = {1}; bins c2_3 = {[2:3]}; bins c4_7 = {[4:7]}; bins c8up = {[8:$]}; }
    cp_sw   : coverpoint b.swait { bins none = {0}; bins s1 = {1}; bins s2_3 = {[2:3]}; bins s4up = {[4:$]}; }
    x_burst_size : cross cp_burst, cp_size;
    x_err_master : cross cp_err, cp_pid;
    x_lock_cont  : cross cp_lock, cp_cw;
  endgroup
  function new(string name, uvm_component parent); super.new(name, parent); cg = new(); endfunction
  function void write(ahb_beat t); b = t; cg.sample(); endfunction
endclass
