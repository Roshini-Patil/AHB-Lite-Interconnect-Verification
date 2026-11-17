class ahb_test extends uvm_test;
  `uvm_component_utils(ahb_test)
  ahb_env env;
  virtual ahb_ctrl_if cvif;
  virtual rst_if      rvif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    int wmax, ep;
    super.build_phase(phase);
    env = ahb_env::type_id::create("env", this);
    if (!uvm_config_db#(virtual ahb_ctrl_if)::get(this, "", "cvif", cvif)) `uvm_fatal("NOVIF", "cvif")
    if (!uvm_config_db#(virtual rst_if)::get(this, "", "rvif", rvif))      `uvm_fatal("NOVIF", "rvif")
    // FACTORY example: negative test swaps the item type for one that violates the 1KB rule
    if ($test$plusargs("NEG_1KB")) set_type_override_by_type(ahb_item::get_type(), ahb_item_bad::get_type());
    // CONFIG_DB example: knobs for the reactive slaves
    if ($value$plusargs("WAIT_MAX=%d", wmax)) uvm_config_db#(int)::set(this, "env.sagt*", "wait_max", wmax);
    if ($value$plusargs("ERR_PCT=%d",  ep))   uvm_config_db#(int)::set(this, "env.sagt*", "err_pct",  ep);
  endfunction

  task prio_driver(string pm);
    case (pm)
      "equal":   for (int i = 0; i < NM; i++) cvif.prio[i] = 3'd1;
      "fixed":   begin cvif.prio[0] = 3'd3; cvif.prio[1] = 3'd2; cvif.prio[2] = 3'd1; end
      "dynamic": forever begin
                   for (int i = 0; i < NM; i++) cvif.prio[i] = 3'($urandom_range(0, 3));
                   #($urandom_range(100, 400) * 1ns);
                 end
      default: `uvm_fatal("PRIO", "PRIO must be equal|fixed|dynamic")
    endcase
  endtask

  task run_phase(uvm_phase phase);
    ahb_vseq vs;
    string mode = "random", pm = "fixed";
    int n = 20;
    phase.raise_objection(this);
    void'($value$plusargs("VSEQ=%s", mode));
    void'($value$plusargs("N=%d", n));
    void'($value$plusargs("PRIO=%s", pm));
    vs = ahb_vseq::type_id::create("vs");
    vs.mode = mode; vs.n = n;
    fork prio_driver(pm); join_none
    if ($test$plusargs("RESET_MID")) fork
      begin #(300ns); rvif.pulse(3); env.sb.flush(); end
    join_none
    vs.start(env.vsqr);
    #(300ns);                                   // drain
    phase.drop_objection(this);
  endtask
endclass
