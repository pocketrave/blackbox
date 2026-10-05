#!/usr/bin/env python3
"""
Step 4 - show the current PRESET NAME in the header instead of "Seq N".

Not a standalone build: build_all.py imports cave_h() from here. Flash only the
image build_all.py produces.

------------------------------------------------------------------ verified facts

Header text is built in the status function around 0x0809BCFA, into a 24-byte
buffer at r5+8, by snprintf 0x080C89F4(buf, 0x18, fmt, ...). Three modes:

  0x0809BD0C  view mode 0x12 -> 0x0809C094 .. 0x0809C0C0  "Seq %d: %c" (layer)
  0x0809BD18  not a sample   -> 0x0809C0D0               "Seq %d"
  otherwise                  -> 0x0809BD2C               sample name (untouched)

Both Seq paths end with `b 0x0809BFBE`. The only branches into them are the two
beq.w above (whole-image scan), so the first 4 bytes of each are safe detours:

  0x0809C0C0  mov r3,r8 ; ldr r2,[pc,#0x38]   -> b.w cave   ("Seq %d: %c")
  0x0809C0D0  mov r3,r8 ; ldr r2,[pc,#0x2c]   -> b.w cave   ("Seq %d")

r0-r3 are dead at both sites (snprintf clobbers them next), r5 is the struct.

Preset name comes from memory only - no SD access, no calls except snprintf:

  index      scratch+0 (Step 2; kept in step by hook A on every LoadBank,
             including boot and browser loads - confirmed on hardware)
  list       0x2401F834: [+0] count, [+0xC] char*[] names, [+0x10] dirty byte
             (GetNameByIndex 0x0804290C reads exactly these; when dirty it
             RESCANS, which is why we do not call it from a display path)

While a quantized switch is pending (scratch+8) and scratch+16 (index being
left, set by cave C) differs from scratch+0 (target), the header shows
"old>new": up to 11 chars of old, '>', then as much of new as fits in 23.

Any doubt -> fall back to the stock "Seq %d" text: descriptor array not yet
allocated, list dirty, index >= count, null table, null or empty name.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb as T

DESC_ARRAY_PTR = 0x2401F4FC
SCRATCH_OFF = 0x1F0 * 28
PRESET_LIST = 0x2401F834
SNPRINTF = 0x080C89F4
HEADER_BACK = 0x0809BFBE
ADD_R0_R5_8 = bytes.fromhex("05f10800")        # add.w r0, r5, #8 (copied from 0x0809C0D6)
MOV_R3_R8 = bytes.fromhex("4346")              # mov r3, r8

# (site, original 4 bytes, original format string)
SITES = [
    (0x0809C0C0, bytes.fromhex("43460e4a"), 0x080CF2C0),   # "Seq %d: %c"
    (0x0809C0D0, bytes.fromhex("43460b4a"), 0x080CF2CC),   # "Seq %d"
]
FMT = b"%s\x00"
OLD_MAX = 11                 # chars of the old name before '>'
BUF_MAX = 0x18 - 1           # header buffer is 24 bytes incl. NUL
BX_LR = bytes.fromhex("7047")


def _adds8(rd, imm8):
    """adds rd, #imm8 (T2)"""
    import struct
    assert 0 <= rd < 8 and 0 <= imm8 < 256
    return struct.pack("<H", 0x3000 | (rd << 8) | imm8)


def name_of(va, L):
    """Leaf: r0 = preset index -> r0 = name ptr, or 0. Clobbers r1, r2.
    Memory only (see module doc); bails whenever the list is dirty."""
    c = b""
    c += T.ldr_imm32(1, PRESET_LIST)
    c += T.ldrb_imm(2, 1, 0x10)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("fail", va))
    c += T.ldr_imm(2, 1)                        # count
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "cs", L.get("fail", va))
    c += T.ldr_imm(1, 1, 0xC)                   # name table
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("fail", va))
    c += T.lsls_imm(0, 0, 2)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(0, 1)                        # name
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("fail", va))
    c += T.ldrb_imm(2, 0, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("fail", va))
    c += BX_LR
    L["fail"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += BX_LR
    return c


def cave_h(va, L, fmt_va, orig_fmt, name_of_va):
    """Header text. lr is dead here (the stock code's own bl clobbers it).
    The pushes are undone BEFORE snprintf: the "Seq %d: %c" path passes its
    5th argument at [sp], placed by stock code before the detour."""
    c = b""
    c += T.push_lo([4, 6, 7])
    c += T.ldr_imm32(4, DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("orig", va))
    c += T.movw(0, SCRATCH_OFF)
    c += T.add_reg(4, 0)                        # r4 = scratch
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 4, 20)                    # scratch+20 = 0: not "old>new"
    c += T.ldr_imm(0, 4)                        # new / current index
    c += T.bl(va + len(c), name_of_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("orig", va))
    c += T.mov_reg(6, 0)                        # r6 = new name

    c += T.ldr_imm(0, 4, 8)                     # pending?
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("single", va))
    c += T.ldr_imm(0, 4, 16)                    # old index
    c += T.ldr_imm(1, 4)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("single", va))
    c += T.bl(va + len(c), name_of_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("single", va))
    c += T.mov_reg(7, 0)                        # r7 = old name

    # compose "old>new" into r5+8, bounded
    c += ADD_R0_R5_8                            # r0 = dst
    c += T.mov_reg(2, 0)
    c += _adds8(2, OLD_MAX)                     # r2 = old limit
    L["l1"] = va + len(c)
    c += T.ldrb_imm(3, 7, 0)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("sep", va))
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "cs", L.get("sep", va))
    c += T.strb_imm(3, 0, 0)
    c += T.adds_imm(0, 0, 1)
    c += T.adds_imm(7, 7, 1)
    c += T.b_short(va + len(c), L.get("l1", va))
    L["sep"] = va + len(c)
    c += T.movs_imm8(3, ord(">"))
    c += T.strb_imm(3, 0, 0)
    c += T.adds_imm(0, 0, 1)
    c += bytes.fromhex("05f11f02")              # add.w r2, r5, #0x1f  (= r5+8+23)
    L["l2"] = va + len(c)
    c += T.ldrb_imm(3, 6, 0)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("term", va))
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "cs", L.get("term", va))
    c += T.strb_imm(3, 0, 0)
    c += T.adds_imm(0, 0, 1)
    c += T.adds_imm(6, 6, 1)
    c += T.b_short(va + len(c), L.get("l2", va))
    L["term"] = va + len(c)
    c += T.movs_imm8(3, 0)
    c += T.strb_imm(3, 0, 0)
    c += T.movs_imm8(3, 1)
    c += T.str_imm(3, 4, 20)                    # scratch+20 = 1: title is "old>new"
    c += T.pop_lo([4, 6, 7])
    c += T.bw(va + len(c), HEADER_BACK)

    L["single"] = va + len(c)
    c += T.mov_reg(3, 6)
    c += T.pop_lo([4, 6, 7])
    c += T.ldr_imm32(2, fmt_va)                 # "%s"
    c += T.b_short(va + len(c), L.get("fmt", va))

    L["orig"] = va + len(c)
    c += T.pop_lo([4, 6, 7])
    c += MOV_R3_R8
    c += T.ldr_imm32(2, orig_fmt)

    L["fmt"] = va + len(c)
    c += T.movs_imm8(1, 0x18)
    c += ADD_R0_R5_8
    c += T.bl(va + len(c), SNPRINTF)
    c += T.bw(va + len(c), HEADER_BACK)
    return c


# ---- title colour: red while "old>new" is shown ---------------------------------
# Label +0x53 = text colour index (read at draw time by 0x080C3D2C -> DrawText
# 0x0808EE54). Title label = statusbar+0x13C, so the byte is statusbar+0x18F.
# Hook just before its SetText in the update fn: 0x080AB7E2 `add r1,sp,#0x20 ;
# add.w r0,r4,#0x13c` -> b.w cave. r2/r3 are dead there (SetText takes r0/r1).
# The colour flips together with the text, and SetText marks the label dirty
# when the text differs, so the redraw is guaranteed.
TCOL_SITE = 0x080AB7E2
TCOL_ORIG = bytes.fromhex("08a904f59e70")   # add r1,sp,#0x20 ; add.w r0,r4,#0x13c
TCOL_BACK = 0x080AB7E8                      # bl SetText
COL_NORMAL, COL_PENDING = 3, 6              # palette: 3 = #FCFCFC white, 6 = #FF0000 red
STRB_W_R2_R4_18F = bytes.fromhex("84f88f21")   # strb.w r2, [r4, #0x18f]


def cave_tcol(va, L):
    c = b""
    c += T.movs_imm8(2, COL_NORMAL)
    c += T.ldr_imm32(3, DESC_ARRAY_PTR)
    c += T.ldr_imm(3, 3)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("set", va))
    c += T.movw(1, SCRATCH_OFF)
    c += T.add_reg(3, 1)
    c += T.ldr_imm(3, 3, 20)                    # "old>new" flag from cave_h
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("set", va))
    c += T.movs_imm8(2, COL_PENDING)
    L["set"] = va + len(c)
    c += STRB_W_R2_R4_18F
    c += TCOL_ORIG                              # displaced, position-independent
    c += T.bw(va + len(c), TCOL_BACK)
    return c
