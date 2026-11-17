// REACTIVE slave: no sequencer. It reacts to whatever the DUT drives:
// random wait states, random 2-cycle ERROR, and a byte-lane memory model.
class ahb_slave_responder extends uvm_component;
  `uvm_component_utils(ahb_slave_responder)
  virtual ahb_if vif;
  int pid = 0, wait_max = 3, err_pct = 0;
  bit [31:0] mem [bit [31:0]];

  bit [31:0] d_addr; bit d_wr, d_valid, d_err, in_err2; bit [2:0] d_sz; int wl;

  function new(string name, uvm_component parent); super.new(name, parent); endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db#(virtual ahb_if)::get(this, "", "vif", vif)) `uvm_fatal("NOVIF", "slave vif not set")
    void'(uvm_config_db#(int)::get(this, "", "pid", pid));
    void'(uvm_config_db#(int)::get(this, "", "wait_max", wait_max));
    void'(uvm_config_db#(int)::get(this, "", "err_pct", err_pct));
  endfunction

  function bit [31:0] rd(bit [31:0] a);
    bit [31:0] k = a & ~32'd3;
    return mem.exists(k) ? mem[k] : dflt(pid, k);
  endfunction

  // decide what to drive for the NEXT cycle
  task present();
    if (wl > 0) begin
      vif.scb.HREADYOUT <= 0; vif.scb.HRESP <= 0;
    end else if (d_err) begin
      vif.scb.HREADYOUT <= 0; vif.scb.HRESP <= 1; in_err2 = 1;      // ERROR cycle 1
    end else begin
      vif.scb.HREADYOUT <= 1; vif.scb.HRESP <= 0;
      if (!d_wr) vif.scb.HRDATA <= rd(d_addr);
    end
  endtask

  task run_phase(uvm_phase phase);
    bit [31:0] m;
    d_valid = 0; d_err = 0; in_err2 = 0; wl = 0;
    vif.scb.HREADYOUT <= 1; vif.scb.HRESP <= 0; vif.scb.HRDATA <= 0;
    forever begin
      @(vif.scb);
      if (!vif.HRESETn) begin
        d_valid = 0; d_err = 0; in_err2 = 0; wl = 0;
        vif.scb.HREADYOUT <= 1; vif.scb.HRESP <= 0; continue;
      end
      if (vif.scb.HREADY) begin
        if (d_valid && d_wr && !d_err) begin                       // finish previous write
          m = lane_mask(d_addr, d_sz);
          mem[d_addr & ~32'd3] = (rd(d_addr) & ~m) | (vif.scb.HWDATA & m);
        end
        in_err2 = 0;
        d_valid = vif.scb.HSEL && vif.scb.HTRANS[1];               // new address phase?
        if (d_valid) begin
          d_addr = vif.scb.HADDR; d_wr = vif.scb.HWRITE; d_sz = vif.scb.HSIZE;
          d_err  = ($urandom_range(99) < err_pct);
          wl     = $urandom_range(wait_max);
          present();
        end else begin
          d_err = 0; vif.scb.HREADYOUT <= 1; vif.scb.HRESP <= 0;
        end
      end else begin                                               // HREADY low: still waiting / in ERROR
        if (in_err2) begin
          vif.scb.HREADYOUT <= 1; vif.scb.HRESP <= 1; in_err2 = 0; // ERROR cycle 2
        end else begin
          if (wl > 0) wl--;
          present();
        end
      end
    end
  endtask
endclass

class ahb_slave_agent extends uvm_agent;
  `uvm_component_utils(ahb_slave_agent)
  ahb_monitor         mon;
  ahb_slave_responder rsp;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    mon = ahb_monitor::type_id::create("mon", this);
    rsp = ahb_slave_responder::type_id::create("rsp", this);
  endfunction
endclass
