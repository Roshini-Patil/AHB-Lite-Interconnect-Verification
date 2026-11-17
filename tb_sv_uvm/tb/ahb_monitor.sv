// Passive monitor: same class used on master-side and slave-side ports.
class ahb_monitor extends uvm_monitor;
  `uvm_component_utils(ahb_monitor)
  virtual ahb_if vif;
  int pid = 0;
  uvm_analysis_port #(ahb_beat) ap;

  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    ap = new("ap", this);
    if (!uvm_config_db#(virtual ahb_if)::get(this, "", "vif", vif)) `uvm_fatal("NOVIF", "monitor vif not set")
    void'(uvm_config_db#(int)::get(this, "", "pid", pid));
  endfunction

  task run_phase(uvm_phase phase);
    ahb_beat b;
    bit pend = 0;
    int cw = 0, sw = 0;
    forever begin
      @(vif.mon);
      if (!vif.HRESETn) begin pend = 0; cw = 0; sw = 0; continue; end
      if (pend && !vif.mon.HREADY) sw++;
      if (!pend && vif.mon.HSEL && vif.mon.HTRANS[1] && !vif.mon.HREADY) cw++;
      if (vif.mon.HREADY) begin
        if (pend) begin                         // data phase of previous beat ends now
          b.data  = b.write ? vif.mon.HWDATA : vif.mon.HRDATA;
          b.err   = vif.mon.HRESP;
          b.swait = sw; sw = 0;
          b.t     = $time;
          ap.write(b);
          pend = 0;
        end
        if (vif.mon.HSEL && vif.mon.HTRANS[1]) begin   // address phase accepted now
          b = ahb_beat::type_id::create("b");
          b.pid = pid; b.addr = vif.mon.HADDR; b.write = vif.mon.HWRITE;
          b.size = vif.mon.HSIZE; b.burst = vif.mon.HBURST; b.trans = vif.mon.HTRANS;
          b.lock = vif.mon.HMASTLOCK; b.cwait = cw;
          cw = 0; sw = 0; pend = 1;
        end
      end
    end
  endtask
endclass
