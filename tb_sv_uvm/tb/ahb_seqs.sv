// ---- one master: N random bursts, with knobs ----
class ahb_rand_seq extends uvm_sequence #(ahb_item);
  `uvm_object_utils(ahb_rand_seq)
  int n = 10, fixed_slave = -1, burst_sel = -1, write_sel = -1, lock_pct = 0;
  bit hot = 0;                                  // hot = few addresses -> masters collide on same addresses
  function new(string name = "ahb_rand_seq"); super.new(name); endfunction
  task body();
    repeat (n) begin
      req = ahb_item::type_id::create("req");   // factory: can be overridden by a test
      start_item(req);
      if (!req.randomize() with {
            if (fixed_slave >= 0) addr[31:28] == fixed_slave;
            if (burst_sel  >= 0) burst == burst_sel;
            if (write_sel  >= 0) write == write_sel;
            if (hot) addr[11:0] inside {[0:63]};
          }) `uvm_fatal("RAND", "randomize failed")
      req.lock = ($urandom_range(99) < lock_pct);
      finish_item(req);
    end
  endtask
endclass

// ---- virtual sequence: coordinates all 3 masters ----
class ahb_vseq extends uvm_sequence;
  `uvm_object_utils(ahb_vseq)
  `uvm_declare_p_sequencer(ahb_vsqr)
  string mode = "random";
  int n = 20;
  function new(string name = "ahb_vseq"); super.new(name); endfunction

  task run_on(int m, int slave, int count, int burst = -1, int lock_pct = 0, bit hot = 0, int wr = -1);
    ahb_rand_seq s = ahb_rand_seq::type_id::create($sformatf("s%0d", m));
    s.n = count; s.fixed_slave = slave; s.burst_sel = burst; s.lock_pct = lock_pct; s.hot = hot; s.write_sel = wr;
    s.start(p_sequencer.msqr[m]);
  endtask

  task body();
    case (mode)
      "parallel":   fork run_on(0, 0, n); run_on(1, 1, n); run_on(2, 2, n); join            // 3 masters, 3 different slaves
      "contention": fork run_on(0, 0, n, -1, 0, 1); run_on(1, 0, n, -1, 0, 1); run_on(2, 0, n, -1, 0, 1); join
      "rr":         fork run_on(0, 0, n, 0, 0, 1); run_on(1, 0, n, 0, 0, 1); run_on(2, 0, n, 0, 0, 1); join   // SINGLEs: many switch points
      "lock":       fork run_on(0, 0, n, 5, 100, 1); run_on(1, 0, n, -1, 0, 1); run_on(2, 0, n, -1, 0, 1); join
      "longburst":  fork run_on(0, 0, n, 7); run_on(1, 0, n, 1); run_on(2, 0, n, 7); join   // INCR16 / INCR (for reset-mid-burst)
      "burst_all":  for (int b = 0; b < 8; b++) fork run_on(0, 0, 3, b, 0, 1); run_on(1, 0, 3, -1, 0, 1); run_on(2, 1, 3); join
      "error":      fork run_on(0, 3, 5); run_on(1, 0, n); run_on(2, 1, n); join            // slave 3 = no slave -> ERROR_ON_NO_SLAVE
      "random":     fork run_on(0, -1, n); run_on(1, -1, n); run_on(2, -1, n); join
      "rw_same":    fork run_on(0, 0, n, 0, 0, 1, 1); run_on(1, 0, n, 0, 0, 1, 1); run_on(2, 0, n, 0, 0, 1, 0); join // 2 writers + reader, same addresses
      default: `uvm_fatal("VSEQ", $sformatf("unknown VSEQ=%s", mode))
    endcase
  endtask
endclass
