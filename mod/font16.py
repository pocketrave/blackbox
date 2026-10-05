"""v018: doubled (2x) text drawn with a native 12x16 font (Spleen 8x16) at 1x.

Stock draws most text with the 6x8 font doubled: each set bit is a 2x2 block (4 SetPixel calls).
The two 2x per-glyph routines are replaced at their entry by caves that draw a 12x16 glyph at 1x
from a table appended after the last cave. The 12x16 footprint per character is unchanged, so
text widths, heights and every layout stay identical. The font descriptor 0x240000D0 (6x8) and
the 1x text path are untouched.

  G1 0x0808ED4C (DrawText, unclipped): r0 x, r1 y, r2 font*, r3 char, [sp] colour byte, [sp+4] surface
  G2 0x0808EED4 (DrawText2, clipped):  r0 x, r1 y, r2 clip rect*, r3 font*, [sp] char, [sp+4] colour, [sp+8] surface
  y points up: glyph row r is drawn at y + 15 - r, column c at x + c.
  Clip (G2, signed): rect.x <= px < rect.x + w and rect.y <= py < rect.y + h.
"""
import json
import os
import struct

import thumb as T

G1_SITE, G2_SITE = 0x0808ED4C, 0x0808EED4
ENTRY_ORIG = bytes.fromhex("2de9f04f")        # push.w {r4-r11, lr} at both entries
SETPIXEL = 0x0808F524                         # (surface, x, y, colour)
FONT_KEY = "spleen16"


GLYPH_127 = (           # UI marker (down triangle), 6x8 pixel art doubled to 12x16; drawn here, not read from stock
    "######",
    "######",
    "######",
    ".####.",
    ".####.",
    "..##..",
    "..##..",
    "......",
)


def _glyph127_rows():
    rows = [0] * 16
    for r, line in enumerate(GLYPH_127):
        for c, ch in enumerate(line):
            if ch == "#":
                for dy in (0, 1):
                    for dx in (0, 1):
                        rows[2 * r + dy] |= 0x8000 >> (2 * c + dx)
    return rows


def table():
    """96 glyphs x 16 little-endian u16 rows, bit 15 = leftmost pixel (3072 bytes)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "spleen16.json")
    with open(path) as f:
        rows = list(json.load(f)[FONT_KEY])
    assert len(rows) == 96 * 16
    rows[95 * 16:96 * 16] = _glyph127_rows()
    return b"".join(struct.pack("<H", r) for r in rows)


def _glyph_loop(c, va, L, clip):
    """Rows/columns loop. r4 = row ptr, r6 = y of the current row, r5 = current x.
    Frame slots: [sp] x0, [sp+4] colour, [sp+8] surface, [sp+12] rows left, and for the
    clipped variant [sp+16] x min, [sp+20] x end, [sp+24] y min, [sp+28] y end."""
    L["row"] = va + len(c)
    c += T.ldrh_imm(7, 4, 0)
    c += T.adds_imm8(4, 2)
    c += T.ldr_sp(5, 0)
    L["col"] = va + len(c)
    c += T.lsls_imm(3, 7, 16)                 # current bit (15) -> N
    c += T.b_cond(va + len(c), "pl", L.get("skip", va))
    if clip:
        for off, cond, reg in ((16, "lt", 5), (20, "ge", 5), (24, "lt", 6), (28, "ge", 6)):
            c += T.ldr_sp(3, off)
            c += T.cmp_reg(reg, 3)
            c += T.b_cond(va + len(c), cond, L.get("skip", va))
    c += T.ldr_sp(0, 8)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(2, 6)
    c += T.ldr_sp(3, 4)
    c += T.bl(va + len(c), SETPIXEL)
    L["skip"] = va + len(c)
    c += T.adds_imm8(5, 1)
    c += T.lsls_imm(7, 7, 1)
    c += T.lsls_imm(3, 7, 16)                 # any ink left in this row?
    c += T.b_cond(va + len(c), "ne", L.get("col", va))
    c += T.subs_imm8(6, 1)
    c += T.ldr_sp(3, 12)
    c += T.subs_imm8(3, 1)
    c += T.str_sp(3, 12)
    c += T.b_cond(va + len(c), "ne", L.get("row", va))
    return c


def g1(va, L, table_va):
    FR = 20                                   # 20 pushed + 20 locals = 40: 8-byte aligned at each bl
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)
    c += T.subs_imm8(3, 32)
    c += T.cmp_imm(3, 95)
    c += T.b_cond(va + len(c), "hi", L.get("done", va))
    c += T.str_sp(0, 0)                       # x0
    c += T.add_rd_sp(2, 20 + FR)
    c += T.ldrb_imm(2, 2, 0)
    c += T.str_sp(2, 4)                       # colour byte
    c += T.ldr_sp(2, 24 + FR)
    c += T.str_sp(2, 8)                       # surface
    c += T.movs_imm8(2, 16)
    c += T.str_sp(2, 12)
    c += T.lsls_imm(3, 3, 5)                  # glyph * 32 bytes
    c += T.ldr_imm32(4, table_va)
    c += T.add_reg(4, 3)
    c += T.mov_reg(6, 1)
    c += T.adds_imm8(6, 15)                   # top row
    c = _glyph_loop(c, va, L, clip=False)
    L["done"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def g2(va, L, table_va):
    FR = 36                                   # 20 pushed + 36 locals = 56: 8-byte aligned at each bl
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)
    c += T.str_sp(0, 0)                       # x0
    c += T.ldr_imm(3, 2, 0)
    c += T.str_sp(3, 16)                      # x min
    c += T.ldr_imm(4, 2, 8)
    c += T.add_reg(4, 3)
    c += T.str_sp(4, 20)                      # x end
    c += T.ldr_imm(3, 2, 4)
    c += T.str_sp(3, 24)                      # y min
    c += T.ldr_imm(4, 2, 12)
    c += T.add_reg(4, 3)
    c += T.str_sp(4, 28)                      # y end
    c += T.add_rd_sp(3, 20 + FR)
    c += T.ldrb_imm(3, 3, 0)                  # char
    c += T.subs_imm8(3, 32)
    c += T.cmp_imm(3, 95)
    c += T.b_cond(va + len(c), "hi", L.get("done", va))
    c += T.add_rd_sp(2, 24 + FR)
    c += T.ldrb_imm(2, 2, 0)
    c += T.str_sp(2, 4)                       # colour byte
    c += T.ldr_sp(2, 28 + FR)
    c += T.str_sp(2, 8)                       # surface
    c += T.movs_imm8(2, 16)
    c += T.str_sp(2, 12)
    c += T.lsls_imm(3, 3, 5)
    c += T.ldr_imm32(4, table_va)
    c += T.add_reg(4, 3)
    c += T.mov_reg(6, 1)
    c += T.adds_imm8(6, 15)
    c = _glyph_loop(c, va, L, clip=True)
    L["done"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
