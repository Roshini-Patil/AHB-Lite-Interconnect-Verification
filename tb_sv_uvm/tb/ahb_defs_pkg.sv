// Shared constants + helper functions (compiled FIRST, no UVM inside)
package ahb_defs_pkg;
  localparam int NM = 3;   // number of masters
  localparam int NS = 3;   // number of slaves

  // number of beats of a burst; 0 means INCR (undefined length)
  function automatic int unsigned beats_of(bit [2:0] b);
    case (b)
      3'd0: return 1;
      3'd2, 3'd3: return 4;
      3'd4, 3'd5: return 8;
      3'd6, 3'd7: return 16;
      default: return 0;
    endcase
  endfunction

  function automatic bit is_wrap(bit [2:0] b);
    return (b == 3'd2 || b == 3'd4 || b == 3'd6);
  endfunction

  function automatic bit [31:0] next_addr(bit [31:0] a, bit [2:0] sz, bit [2:0] b);
    bit [31:0] bytes = 32'd1 << sz;
    bit [31:0] total = beats_of(b) * bytes;
    if (is_wrap(b)) return (a & ~(total - 1)) | ((a + bytes) & (total - 1));
    else            return a + bytes;
  endfunction

  // which byte lanes a transfer uses
  function automatic bit [31:0] lane_mask(bit [31:0] a, bit [2:0] sz);
    case (sz)
      3'd0:    return 32'h0000_00FF << (8 * a[1:0]);
      3'd1:    return 32'h0000_FFFF << (8 * a[1:0]);
      default: return 32'hFFFF_FFFF;
    endcase
  endfunction

  // address map: slave i lives at i<<28 ; anything >= NS<<28 is "no slave"
  function automatic int dec(bit [31:0] a);
    if (a[31:28] < NS) return int'(a[31:28]);
    else               return -1;
  endfunction

  // value a never-written memory location returns (unique per slave)
  function automatic bit [31:0] dflt(int s, bit [31:0] a);
    return {8'hC0 + 8'(s), a[23:2], 2'b00};
  endfunction
endpackage
