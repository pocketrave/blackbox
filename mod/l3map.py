"""L3 clip launcher: (column k 0..7, row n 0..9) -> UI record (row, col, pat); host players.

Stock variation j (0..15) of stock column c is record (row 3 - j%4, col c, pat j//4), the order
v019 shows top to bottom. L3 columns 1-4 rows 1-10 = variations 1-10 of stock columns 1-4;
L3 columns 5-8 rows 1-6 = variations 11-16 of stock columns 1-4; rows 7-10 = the hidden
records (row c, col 4, pat 0..3).
Host of L3 column k: cell (row 0, col k) for k < 4, cell (row 1, col k-4) for k >= 4.
"""
import struct

REC_BASE, ROW, COL, PAT = 0x1C00, 0x370, 0xB0, 0x2C


def variation(c, j):
    return (3 - j % 4, c, j // 4)


def record(k, n):
    assert 0 <= k < 8 and 0 <= n < 10
    if k < 4:
        return variation(k, n)
    c = k - 4
    if n < 6:
        return variation(c, 10 + n)
    return (c, 4, n - 6)


def offset(k, n):
    r, c, p = record(k, n)
    return REC_BASE + r * ROW + c * COL + p * PAT


def table():
    return b"".join(struct.pack("<H", offset(k, n)) for k in range(8) for n in range(10))


def host(k):
    row, col = (0, k) if k < 4 else (1, k - 4)
    return (1 << 16 | row << 8 | col, REC_BASE + row * ROW + col * COL)


def hosts():
    return b"".join(struct.pack("<II", *host(k)) for k in range(8))
def inv_table():
    out = bytearray([0xFF] * 32)
    for k in range(8):
        code, _ = host(k)
        row, col = (code >> 8) & 0xFF, code & 0xFF
        for n in range(10):
            r, c, p = record(k, n)
            if (r, c) == (row, col):
                out[k * 4 + p] = n
    return bytes(out)


def eng_offsets():
    out = b""
    for k in range(8):
        code, _ = host(k)
        out += struct.pack("<H", 12 * (((code >> 8) & 0xFF) * 5 + (code & 0xFF)))
    return out

def descs():
    """UI cell descriptor of host H(k): 0x100 | row<<4 | col (layer 1 = sequences)."""
    out = b""
    for k in range(8):
        code, _ = host(k)
        out += struct.pack("<H", 0x100 | ((code >> 8) & 0xF) << 4 | (code & 0xF))
    return out
def qtable():
    """v037 per-clip Quant: [k*10 + n] = u32 (row*5 + col) << 16 | offset of the clip cell's pattern-0 record
    (Quant Size 0x46 is a Seq-tab setting, stored on pattern 0 of the cell)."""
    out = b""
    for k in range(8):
        for n in range(10):
            r, c, p = record(k, n)
            out += struct.pack("<I", (r * 5 + c) << 16 | (REC_BASE + r * ROW + c * COL))
    return out


def inv80():
    """[(row*5 + col)*4 + pat] = k*10 + n of the L3 clip stored in that record."""
    out = bytearray([0xFF] * 80)
    for k in range(8):
        for n in range(10):
            r, c, p = record(k, n)
            out[(r * 5 + c) * 4 + p] = k * 10 + n
    return bytes(out)
