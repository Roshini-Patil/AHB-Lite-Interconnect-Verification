typedef uvm_sequencer #(ahb_item) ahb_sequencer;

class ahb_master_driver extends uvm_driver #(ahb_item);
  `uvm_component_utils(ahb_master_driver)
  virtual ahb_if vif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db#(virtual ahb_if)::get(this, "", "vif", vif)) `uvm_fatal("NOVIF", "driver vif not set")
  endfunction

  task idle_bus();
    vif.mcb.HSEL <= 1; vif.mcb.HTRANS <= 2'b00; vif.mcb.HADDR <= 0; vif.mcb.HWRITE <= 0;
    vif.mcb.HSIZE <= 3'd2; vif.mcb.HBURST <= 0; vif.mcb.HPROT <= 4'b0011;
    vif.mcb.HMASTLOCK <= 0; vif.mcb.HWDATA <= 0;
  endtask

  task run_phase(uvm_phase phase);
    idle_bus();
    wait (vif.HRESETn === 1'b1);
    forever begin
      seq_item_port.get_next_item(req);
      drive(req);
      seq_item_port.item_done();
    end
  endtask

  // Pipelined AHB master: address phase of beat i overlaps data phase of beat i-1
  task drive(ahb_item t);
    int ai = 0, di = -1;               // ai = next beat to launch, di = beat in data phase
    bit [31:0] a = t.addr;
    bit cancel = 0, launching = 0, is_busy = 0, prev_busy = 0;
    t.rdata.delete(); t.got_error = 0;
    repeat (t.idle_gap) begin idle_bus(); @(vif.mcb); end
    while ((ai < t.len && !cancel) || di >= 0) begin
      launching = (ai < t.len) && !cancel;
      is_busy   = 0;
      if (launching) begin
        is_busy = t.busy_en && ai > 0 && !prev_busy && ($urandom_range(3) == 0);
        vif.mcb.HTRANS <= is_busy ? 2'b01 : (ai == 0 ? 2'b10 : 2'b11);   // BUSY / NONSEQ / SEQ
        vif.mcb.HADDR <= a;  vif.mcb.HWRITE <= t.write; vif.mcb.HSIZE <= t.size;
        vif.mcb.HBURST <= t.burst; vif.mcb.HMASTLOCK <= t.lock;
      end else begin
        vif.mcb.HTRANS <= 2'b00; vif.mcb.HMASTLOCK <= 0;
      end
      if (di >= 0 && t.write) vif.mcb.HWDATA <= t.wdata[di];
      @(vif.mcb);
      if (!vif.HRESETn) begin                       // reset in the middle of a burst
        idle_bus(); t.got_error = 1; wait (vif.HRESETn === 1'b1); break;
      end
      if (!vif.mcb.HREADY && vif.mcb.HRESP) cancel = 1;   // 1st cycle of ERROR: cancel rest of burst
      if (vif.mcb.HREADY) begin
        if (di >= 0) begin
          if (!t.write) t.rdata.push_back(vif.mcb.HRDATA);
          if (vif.mcb.HRESP) begin t.got_error = 1; cancel = 1; end
        end
        if (launching && !is_busy) begin di = ai; ai++; a = next_addr(a, t.size, t.burst); end
        else di = -1;
        prev_busy = launching && is_busy;
      end
    end
    idle_bus();
  endtask
endclass

class ahb_master_agent extends uvm_agent;
  `uvm_component_utils(ahb_master_agent)
  ahb_sequencer      sqr;
  ahb_master_driver  drv;
  ahb_monitor        mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    mon = ahb_monitor::type_id::create("mon", this);
    if (get_is_active() == UVM_ACTIVE) begin
      sqr = ahb_sequencer::type_id::create("sqr", this);
      drv = ahb_master_driver::type_id::create("drv", this);
    end
  endfunction
  function void connect_phase(uvm_phase phase);
    if (get_is_active() == UVM_ACTIVE) drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass
