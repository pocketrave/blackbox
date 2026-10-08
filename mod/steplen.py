"""v058: Step Len (0x85) and Quant Size (0x46) go down to 1/128 (1/64T, then 1/128 appended to both lists).

Both enums index a float table of beats (x 960 = ticks) that has no bounds check at its 13 + 2 read sites:
  - Step Len  floats 0x080ECA6C [15] (32 .. 0.0625), followed by its label table 0x080ECAA8 (read only by 0x85's
    registration);
  - Quant     floats 0x080ECC70 [13] (8 .. 0.0625), followed by its label table 0x080ECCA4 (0x45, 0x46 and 0x48's
    registrations).
The two words after each float table become the new entries (1/64T = 1/24 beat, 1/128 = 1/32 beat), so every read
site sees the longer table without a relocation (a relocated copy would carry stock bytes into the public patch).
The label tables they overwrite are replaced by the mod's own 17 texts: the registrar's epilogue (the Step 1 cave)
points the four descriptors at them and sets the counts 0x85 = 17, 0x46 = 15 (0x45 / 0x48 keep 13).
One engine clamp knows the old count: Step Len + modulation is clamped to 14 at 0x0805CB30."""
import struct

import thumb as T

LABELS = ("8 bars", "4 bars", "2 bars", "1 bar", "1/2", "1/2T", "1/4", "1/4T", "1/8", "1/8T", "1/16", "1/16T",
          "1/32", "1/32T", "1/64", "1/64T", "1/128")
QUANT_FIRST = 2                                   # the Quant list is the Step Len list from "2 bars"
STEP_COUNT, QUANT_COUNT, QUANT_OLD = 17, 15, 13
NEW_FLOATS = struct.pack("<2I", 0x3D2AAAAB, 0x3D000000)  # 1/24 (1/64T), 1/32 (1/128) beat

STEP_FLOATS, STEP_LABELS = 0x080ECA6C, 0x080ECAA8
QUANT_FLOATS, QUANT_LABELS = 0x080ECC70, 0x080ECCA4
DESC, DESCP = 28, 0x2401F4FC                   # descriptor size; the descriptor array's pointer
P_STEPLEN, P_QUANTSIZE, P_QUANT, P_48 = 0x85, 0x45, 0x46, 0x48

CLAMP_SITES = ((0x0805CB30, bytes.fromhex("0e2b"), bytes([STEP_COUNT - 1, 0x2B])),   # cmp r3,#14 -> #16
               (0x0805CB34, bytes.fromhex("0e23"), bytes([STEP_COUNT - 1, 0x23])))   # movge r3,#14 -> #16


def float_sites(stock):
    """(va, stock bytes, new bytes) for the two words after each float table (stock: the first two label pointers)."""
    out = []
    for floats, labels, n in ((STEP_FLOATS, STEP_LABELS, 15), (QUANT_FLOATS, QUANT_LABELS, QUANT_OLD)):
        assert floats + 4 * n == labels
        out.append((labels, bytes(stock[labels - 0x08040000:labels - 0x08040000 + 8]), NEW_FLOATS))
    return out


def strings():
    """The 17 texts, packed in reverse order (no 16-byte run of the stock 8-byte slots). -> (blob, [offset per label])."""
    blob, offs = b"", [0] * len(LABELS)
    for i in range(len(LABELS) - 1, -1, -1):
        offs[i] = len(blob)
        blob += LABELS[i].encode() + b"\x00"
    return blob, offs


def table(strings_va, offs):
    """17 label pointers; the Quant list is this table + 8."""
    return b"".join(struct.pack("<I", strings_va + o) for o in offs)


def descfix(va, L, table_va):
    """bl from the registrar's epilogue: point the descriptors (at [DESCP] + id * 28) of 0x85 / 0x45 / 0x46 / 0x48 at
    the mod's labels and set the counts. r0-r3 only."""
    c = T.ldr_imm32(3, DESCP)
    c += T.ldr_imm(3, 3, 0)
    for pid, tab, cnt in ((P_STEPLEN, table_va, STEP_COUNT), (P_QUANTSIZE, table_va + 4 * QUANT_FIRST, QUANT_OLD),
                          (P_QUANT, table_va + 4 * QUANT_FIRST, QUANT_COUNT), (P_48, table_va + 4 * QUANT_FIRST, QUANT_OLD)):
        c += T.ldr_imm32(0, pid * DESC)
        c += T.add_reg(0, 3)
        c += T.ldr_imm32(1, tab)
        c += T.movs_imm8(2, cnt)
        c += T.str_imm(1, 0, 8)
        c += T.str_imm(2, 0, 0xC)
    c += T.bx(14)
    return c
