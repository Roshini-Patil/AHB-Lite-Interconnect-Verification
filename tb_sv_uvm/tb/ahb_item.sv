// ---- one burst requested by a master ----
class ahb_item extends uvm_sequence_item;
  rand bit [31:0]   addr;
  rand bit          write;
  rand bit [2:0]    burst;      // 0 SINGLE 1 INCR 2 WRAP4 3 INCR4 4 WRAP8 5 INCR8 6 WRAP16 7 INCR16
  rand bit [2:0]    size;       // 0 byte 1 halfword 2 word
  rand bit          lock;
  rand bit          busy_en;    // allow BUSY cycles inside the burst
  rand int unsigned len;        // number of beats
  rand int unsigned idle_gap;   // idle cycles before this burst
  rand bit [31:0]   wdata[];
  bit [31:0]        rdata[$];
  bit               got_error;

  `uvm_object_utils(ahb_item)
  function new(string name = "ahb_item"); super.new(name); endfunction

  constraint c_len  { (burst == 0) -> len == 1;
                      (burst == 1) -> len inside {[1:8]};
                      (burst inside {2,3}) -> len == 4;
                      (burst inside {4,5}) -> len == 8;
                      (burst inside {6,7}) -> len == 16; }
  constraint c_size { size inside {[0:2]}; }
  constraint c_align{ (addr & ((32'd1 << size) - 1)) == 0; }
  constraint c_map  { soft addr[31:28] inside {[0:2]}; addr[27:12] == 0; }
  constraint c_1kb  { (burst inside {1,3,5,7}) -> (addr[9:0] + len * (32'd1 << size)) <= 1024; }
  constraint c_data { wdata.size() == len; }
  constraint c_idle { idle_gap inside {[0:3]}; }
  constraint c_lock { soft lock == 0; }

  function string convert2string();
    return $sformatf("%s addr=%h burst=%0d size=%0d len=%0d lock=%0b",
                     write ? "WR" : "RD", addr, burst, size, len, lock);
  endfunction
endclass

// ---- NEGATIVE TEST item: deliberately crosses a 1KB boundary (to show assertion failing) ----
class ahb_item_bad extends ahb_item;
  `uvm_object_utils(ahb_item_bad)
  function new(string name = "ahb_item_bad"); super.new(name); endfunction
  constraint c_1kb { burst inside {3,5,7}; (addr[9:0] + len * (32'd1 << size)) > 1024; }
endclass

// ---- one transfer (beat) as seen by a monitor ----
class ahb_beat extends uvm_object;
  int          pid;                // port number
  bit [31:0]   addr, data;
  bit          write, lock, err;
  bit [2:0]    size, burst;
  bit [1:0]    trans;
  int          cwait;              // stall cycles caused by CONTENTION (nobody owed us a wait)
  int          swait;              // stall cycles caused by the SLAVE (data phase wait)
  time         t;
  `uvm_object_utils(ahb_beat)
  function new(string name = "ahb_beat"); super.new(name); endfunction
endclass
