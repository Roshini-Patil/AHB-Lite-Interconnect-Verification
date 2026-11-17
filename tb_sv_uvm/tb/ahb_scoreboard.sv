`uvm_analysis_imp_decl(_m)
`uvm_analysis_imp_decl(_s)

// Scoreboard:
//  * ROUTING : every master beat must show up, unchanged, on the slave its address decodes to
//  * DATA    : per-slave memory model (byte lanes) -> reads return last value written
//  * ORDER   : model is updated in SLAVE-SIDE order, so 2 masters writing same address is judged by the slave monitor
class ahb_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(ahb_scoreboard)
  uvm_analysis_imp_m #(ahb_beat, ahb_scoreboard) m_imp;
  uvm_analysis_imp_s #(ahb_beat, ahb_scoreboard) s_imp;

  ahb_beat   mq [NM][$];
  ahb_beat   sq [NS][$];
  bit [31:0] mem [NS][bit [31:0]];
  bit        exp_noslave_err = 1;     // ERROR_ON_NO_SLAVE enabled in DUT
  bit        allow_ic_err    = 0;     // allow interconnect-generated ERRORs (slave-mask tests)
  int        n_ok, n_slv_err, n_noslave, n_ic_err, n_pairs[NS];

  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    m_imp = new("m_imp", this); s_imp = new("s_imp", this);
    if ($test$plusargs("ALLOW_IC_ERR")) allow_ic_err = 1;
  endfunction

  function void flush();                // call after a mid-test reset
    for (int m = 0; m < NM; m++) mq[m].delete();
    for (int s = 0; s < NS; s++) sq[s].delete();
  endfunction

  function void write_m(ahb_beat b);
    int s = dec(b.addr);
    if (s < 0) begin
      n_noslave++;
      if (exp_noslave_err && !b.err) `uvm_error("SB_NOSLAVE", $sformatf("unmapped addr %h got OKAY", b.addr))
      return;
    end
    mq[b.pid].push_back(b);
    try_match();
  endfunction

  function void write_s(ahb_beat b);
    sq[b.pid].push_back(b);
    try_match();
  endfunction

  function void try_match();
    ahb_beat sb, mb;
    bit progress = 1;
    while (progress) begin
      progress = 0;
      for (int s = 0; s < NS && !progress; s++) begin
        if (sq[s].size() == 0) continue;
        sb = sq[s][0];
        for (int m = 0; m < NM && !progress; m++) begin
          if (mq[m].size() == 0) continue;
          mb = mq[m][0];
          if (dec(mb.addr) == s && mb.addr == sb.addr && mb.write == sb.write &&
              mb.size == sb.size && mb.data == sb.data && mb.err == sb.err) begin
            check_pair(m, s, mb, sb);
            mq[m].pop_front(); sq[s].pop_front();
            progress = 1;
          end
        end
      end
    end
  endfunction

  function void check_pair(int m, int s, ahb_beat mb, ahb_beat sb);
    bit [31:0] k = sb.addr & ~32'd3;
    bit [31:0] mk = lane_mask(sb.addr, sb.size);
    bit [31:0] cur = mem[s].exists(k) ? mem[s][k] : dflt(s, k);
    n_pairs[s]++;
    if (sb.err) begin n_slv_err++; return; end
    if (sb.write) begin mem[s][k] = (cur & ~mk) | (sb.data & mk); n_ok++; end
    else if ((sb.data & mk) !== (cur & mk))
      `uvm_error("SB_DATA", $sformatf("slave%0d read %h @%h expected %h (master %0d)", s, sb.data & mk, sb.addr, cur & mk, m))
    else n_ok++;
  endfunction

  function void check_phase(uvm_phase phase);
    for (int m = 0; m < NM; m++)
      for (int i = 0; i < mq[m].size(); i++)
        if (mq[m][i].err) begin
          n_ic_err++;
          if (!allow_ic_err) `uvm_error("SB_ICERR", $sformatf("master%0d addr %h got ERROR but no slave saw it", m, mq[m][i].addr))
        end else
          `uvm_error("SB_LOST", $sformatf("master%0d beat addr=%h wr=%0b never matched at slave (lost/misrouted/corrupted)", m, mq[m][i].addr, mq[m][i].write))
    for (int s = 0; s < NS; s++)
      for (int i = 0; i < sq[s].size(); i++)
        `uvm_error("SB_ORPHAN", $sformatf("slave%0d beat addr=%h has no master beat", s, sq[s][i].addr))
  endfunction

  function void report_phase(uvm_phase phase);
    uvm_report_server rs = uvm_report_server::get_server();
    `uvm_info("SB", $sformatf("ok=%0d slave_err=%0d no_slave_err=%0d ic_err=%0d pairs/slave=%0d,%0d,%0d",
              n_ok, n_slv_err, n_noslave, n_ic_err, n_pairs[0], n_pairs[1], n_pairs[2]), UVM_LOW)
    if (rs.get_severity_count(UVM_ERROR) + rs.get_severity_count(UVM_FATAL) == 0)
      $display("AHB_RESULT: PASS");
    else
      $display("AHB_RESULT: FAIL");
  endfunction
endclass
