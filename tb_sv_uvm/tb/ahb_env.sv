class ahb_vsqr extends uvm_sequencer;
  `uvm_component_utils(ahb_vsqr)
  ahb_sequencer msqr [NM];
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
endclass

class ahb_env extends uvm_env;
  `uvm_component_utils(ahb_env)
  ahb_master_agent magt [NM];
  ahb_slave_agent  sagt [NS];
  ahb_scoreboard   sb;
  ahb_cov          cov;
  ahb_vsqr         vsqr;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    for (int i = 0; i < NM; i++) begin
      uvm_config_db#(int)::set(this, $sformatf("magt%0d*", i), "pid", i);
      magt[i] = ahb_master_agent::type_id::create($sformatf("magt%0d", i), this);
    end
    for (int j = 0; j < NS; j++) begin
      uvm_config_db#(int)::set(this, $sformatf("sagt%0d*", j), "pid", j);
      sagt[j] = ahb_slave_agent::type_id::create($sformatf("sagt%0d", j), this);
    end
    sb   = ahb_scoreboard::type_id::create("sb", this);
    cov  = ahb_cov::type_id::create("cov", this);
    vsqr = ahb_vsqr::type_id::create("vsqr", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    for (int i = 0; i < NM; i++) begin
      magt[i].mon.ap.connect(sb.m_imp);
      magt[i].mon.ap.connect(cov.analysis_export);
      vsqr.msqr[i] = magt[i].sqr;
    end
    for (int j = 0; j < NS; j++) sagt[j].mon.ap.connect(sb.s_imp);
  endfunction
endclass
