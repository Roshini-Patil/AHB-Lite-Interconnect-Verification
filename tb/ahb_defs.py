"""ahb_defs.py - shared constants and helper functions (Python version of ahb_defs_pkg.sv).

Nothing here touches the simulator. Every other file imports from here, so the
address map, burst rules and byte-lane rules are written ONCE.
"""

NM = 3          # number of AHB masters  (DUT parameter MASTERS)
NS = 3          # number of AHB slaves   (DUT parameter SLAVES)
PW = 2          # priority width = $clog2(NM); legal priorities 0..NM-1, larger = more urgent

# HTRANS encodings (AMBA AHB-Lite, table 3-1)
IDLE, BUSY, NONSEQ, SEQ = 0, 1, 2, 3
TRANS_NAME = {IDLE: "IDLE", BUSY: "BUSY", NONSEQ: "NONSEQ", SEQ: "SEQ"}

# HBURST encodings (table 3-2)
SINGLE, INCR, WRAP4, INCR4, WRAP8, INCR8, WRAP16, INCR16 = range(8)
BURST_NAME = ["SINGLE", "INCR", "WRAP4", "INCR4", "WRAP8", "INCR8", "WRAP16", "INCR16"]

# HSIZE encodings: 0 = byte, 1 = halfword, 2 = word (32-bit bus -> max 2)
SIZE_NAME = ["BYTE", "HALF", "WORD"]

# Address map used in the wrapper: slave j answers when HADDR[31:28] == j
SLAVE_SHIFT = 28


def beats_of(burst):
    """Number of beats of a burst type. INCR (undefined length) returns 0."""
    return {SINGLE: 1, INCR: 0, WRAP4: 4, INCR4: 4, WRAP8: 8, INCR8: 8, WRAP16: 16, INCR16: 16}[burst]


def is_wrap(burst):
    return burst in (WRAP4, WRAP8, WRAP16)


def next_addr(a, size, burst):
    """Address of the next beat.
    Incrementing burst: a + bytes.
    Wrapping burst: the address wraps inside a block of (beats x bytes), e.g. WRAP4 of words
    wraps inside a 16-byte block: 0x38 -> 0x3C -> 0x30 -> 0x34."""
    nbytes = 1 << size
    if is_wrap(burst):
        total = beats_of(burst) * nbytes
        return (a & ~(total - 1)) | ((a + nbytes) & (total - 1))
    return (a + nbytes) & 0xFFFF_FFFF


def lane_mask(a, size):
    """Which byte lanes of the 32-bit data bus carry this transfer (little-endian)."""
    if size == 0:
        return 0xFF << (8 * (a & 3))
    if size == 1:
        return 0xFFFF << (8 * (a & 2))
    return 0xFFFF_FFFF


def dec(a):
    """Address decoder: which slave owns address a; -1 = no slave (unmapped)."""
    s = (a >> SLAVE_SHIFT) & 0xF
    return s if s < NS else -1


def dflt(s, a):
    """Value a never-written word returns. Unique per slave, so a read that is routed
    to the wrong slave returns a visibly wrong value."""
    return ((0xC0 + s) << 24) | (a & 0x00FF_FFFC)


def crosses_1kb(a, size, nbeats):
    """True if an incrementing burst starting at a would cross a 1 KB boundary."""
    return (a & 0x3FF) + nbeats * (1 << size) > 1024
