"""v026 L3 grid, display only.

VT1: SEQS view vtable slot 1 (data word 0x080F0E94, stock 0x080AEAF9 = generic container draw) -> PAINT.
PAINT(view, ctx): container draw (status label); hide the 33 stock widgets (16 cells, 16 note previews,
right panel: +0x30 hidden, +0x31 dirty); if ctx byte 0 or 1 (full / bar pass), repaint the grid.
COLSTATE(k): from host H(k) (+0xC24 pending read first, +0xC20 current, +0x5B running) and the engine
table [[0x2400A9C0+0x9A74] + 0x126D0 + 12*(row*5+col)] = {step, ?, state(-100 stopped)} write
mod state +36+4k = {play_n, pend_n, u16 progress}. y-up coordinates: top-down y = 240 - y - h.
"""
import struct

import thumb as T
import phase5 as P5
import launch as LA

VT1_SITE, VT1_ORIG = 0x080F0E94, struct.pack("<I", 0x080AEAF9)
CONTAINER_DRAW = 0x080AEAF8
H1_L3 = bytes.fromhex("0621")                 # knob count 6 -> top 0..5 (v006 had 0d21)
FILLRECT, RECTOUTL, TEXT1X = 0x0808EA22, 0x0808E994, 0x0808F23C
CORE_PTR, ENG_TAB = 0x2400A9C0 + 0x9A74, 0x126D0
COL_OFF = 36
TOP_OFF = 0x1AEC
SECT_NAME0 = 0x29C0 + 24 * 0x30 + 0x2C        # session offset of section 24's name pointer
DIGITS = b"".join(bytes([0x31 + k, 0]) for k in range(8))
HIDE = ([0x34 + r * 0x680 + c * 0x1A0 for r in range(4) for c in range(4)] +
        [0x1B08 + r * 0x610 + c * 0x184 for r in range(4) for c in range(4)] + [0x3D5C])
# v027: on the 5-bit/channel screen #0C0D0F (2) and the gap #0A0B0D (13) look identical, so empty = 1
# (#30353B), notes = 9 (#52585F); pending = 32 (#F0E442 yellow) to differ from the playing outline (3)
# v030: the launch marker is white (15), as stock: the column's target clip = pending, else the
# enabled host's current clip (armed while stopped)
C_GAP, C_HEAD, C_EMPTY, C_NOTES, C_LINE, C_BAR, C_PEND = 13, 2, 1, 9, 3, 5, 15
SEL_OFF, C_SEL = 80, 4                        # v028: L3 selection (mod state +80/+81), stock blue fill
SCROLL_ROWS = ((314, 1), (313, 3), (312, 5), (311, 7))   # v056: scroll triangle rows (x, w), apex first
C_ROWMK = 32                                  # v043: MIDI-actionable row corners, bright yellow #F0E442 (palettes.py)
ROWMK = ((0, 0, 3, 1), (0, 0, 1, 3), (317, 0, 3, 1), (319, 0, 1, 3),          # (dx, dy, w, h) from the band's
         (0, 39, 3, 1), (0, 37, 1, 3), (317, 39, 3, 1), (319, 37, 1, 3))      # bottom-left (y-up), band 320x40


def _slot_to_n(c, va, L, tag, inv_va):
    """r0 = slot address (0 = none) -> r0 = L3 row n or 0xFF. r4 = k, r6 = player, r7 = mod state.
    Clobbers r1-r3."""
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get(tag + "none", va))
    c += T.movw(1, 0x320)
    c += T.add_reg(1, 6)
    c += T.subs_reg(0, 0, 1)
    c += T.movs_imm8(1, 0x48)
    c += T.udiv(2, 0, 1)                      # r2 = s
    c += T.cmp_imm(2, 3)
    c += T.b_cond(va + len(c), "hi", L.get(tag + "none", va))
    c += T.lsls_imm(1, 4, 2)
    c += T.adds_imm8(1, 4)
    c += T.adds_reg(1, 1, 2)
    c += T.add_reg(1, 7)
    c += T.ldrb_imm(0, 1, 0)                  # slot_clip[k][s]
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get(tag + "inv", va))
    c += T.subs_imm8(0, 1)
    c += T.b_short(va + len(c), L.get(tag + "done", va))
    L[tag + "inv"] = va + len(c)
    c += T.ldr_imm32(1, inv_va)
    c += T.lsls_imm(3, 4, 2)
    c += T.add_reg(1, 3)
    c += T.add_reg(1, 2)
    c += T.ldrb_imm(0, 1, 0)
    c += T.b_short(va + len(c), L.get(tag + "done", va))
    L[tag + "none"] = va + len(c)
    c += T.movs_imm8(0, 0xFF)
    L[tag + "done"] = va + len(c)
    return c


def colstate(va, L, hosts_va, inv_va, eng_va):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(12)                     # [sp] current slot address, [sp+4] step
    c += T.mov_reg(4, 0)                      # r4 = k
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(1, LA.STATE_OFF)
    c += T.adds_reg(7, 0, 1)                  # r7 = mod state
    c += T.lsls_imm(5, 4, 2)
    c += T.adds_imm8(5, COL_OFF)
    c += T.add_reg(5, 7)                      # r5 = &out[k]
    c += T.movs_imm8(0, 0xFF)
    c += T.strb_imm(0, 5, 0)
    c += T.strb_imm(0, 5, 1)
    c += T.movs_imm8(0, 0)
    c += T.strh_imm(0, 5, 2)
    # host player
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(2, 1, 0)                   # r2 = code
    c += T.ldr_imm32(1, LA.REGISTRY)
    c += T.movs_imm8(3, 64)
    L["find"] = va + len(c)
    c += T.ldr_imm(6, 1, 0)
    c += T.adds_imm8(1, 4)
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "eq", L.get("fnext", va))
    c += T.ldr_imm(0, 6, 0)
    c += T.str_sp(1, 4)
    c += T.ldr_imm32(1, LA.PLAYER_VT)
    c += T.cmp_reg(0, 1)
    c += T.ldr_sp(1, 4)
    c += T.b_cond(va + len(c), "ne", L.get("fnext", va))
    c += T.ldr_imm(0, 6, 0x18)
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "eq", L.get("found", va))
    L["fnext"] = va + len(c)
    c += T.subs_imm8(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("find", va))
    c += T.bw(va + len(c), L.get("ret", va))
    L["found"] = va + len(c)
    # pending first, then current (v025 race order)
    c += T.movw(3, 0xC20)
    c += T.add_reg(3, 6)
    c += T.ldr_imm(0, 3, 4)                   # pending
    c += T.ldr_imm(1, 3, 0)                   # current
    c += T.str_sp(1, 0)
    c = _slot_to_n(c, va, L, "p", inv_va)
    c += T.strb_imm(0, 5, 1)
    # v030: no pending switch -> the launch marker sits on the enabled host's current clip
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "ne", L.get("marked", va))
    c += T.mov_reg(3, 6)
    c += T.adds_imm8(3, 0x5B)
    c += T.ldrb_imm(0, 3, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("marked", va))
    c += T.ldr_sp(0, 0)
    c = _slot_to_n(c, va, L, "m", inv_va)
    c += T.strb_imm(0, 5, 1)
    L["marked"] = va + len(c)
    # running and engine not stopped
    c += T.mov_reg(3, 6)
    c += T.adds_imm8(3, 0x5B)
    c += T.ldrb_imm(0, 3, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(1, CORE_PTR)
    c += T.ldr_imm(1, 1, 0)
    c += T.ldr_imm32(2, ENG_TAB)
    c += T.add_reg(1, 2)
    c += T.lsls_imm(2, 4, 1)
    c += T.ldr_imm32(3, eng_va)
    c += T.add_reg(3, 2)
    c += T.ldrh_imm(2, 3, 0)
    c += T.add_reg(1, 2)                      # r1 = engine entry
    c += T.ldr_imm(2, 1, 8)                   # state
    c += T.movs_imm8(3, 100)
    c += T.negs(3, 3)
    c += T.cmp_reg(2, 3)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm(2, 1, 0)
    c += T.str_sp(2, 4)                       # step
    c += T.ldr_sp(0, 0)
    c = _slot_to_n(c, va, L, "c", inv_va)
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.strb_imm(0, 5, 0)
    # progress = clamp(step * 1000 / stepcnt, 0, 1000)
    c += T.ldr_sp(0, 0)
    c += T.ldr_imm(2, 0, 4)                   # stepcnt of the current slot
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_sp(0, 4)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "lt", L.get("ret", va))
    c += T.movw(1, 1000)
    c += T.muls(0, 1)
    c += T.udiv(0, 0, 2)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "ls", L.get("pok", va))
    c += T.mov_reg(0, 1)
    L["pok"] = va + len(c)
    c += T.strh_imm(0, 5, 2)
    L["ret"] = va + len(c)
    c += T.add_sp_imm(12)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


FR = 28                                       # 20 pushed + 28 = 48: sp 8-aligned at every bl
RECT, TOP, NSLOT = 0, 16, 20


def _imm(c, rd, v):
    return c + (T.movs_imm8(rd, v) if 0 <= v < 256 else T.movw(rd, v & 0xFFFF))


def _rect(c, va, prim, x, y, w, h, colour, w_from_r0=False):
    """prim(&rect, colour, surface r6). w_from_r0: width already in r0."""
    if w_from_r0:
        c += T.str_sp(0, RECT + 8)
    else:
        c = _imm(c, 0, w); c += T.str_sp(0, RECT + 8)
    c = _imm(c, 0, x); c += T.str_sp(0, RECT)
    c = _imm(c, 0, y); c += T.str_sp(0, RECT + 4)
    c = _imm(c, 0, h); c += T.str_sp(0, RECT + 12)
    c += T.add_rd_sp(0, RECT)
    c += T.movs_imm8(1, colour)
    c += T.mov_reg(2, 6)
    c += T.bl(va + len(c), prim)
    return c


def _col_ptr(c, rd, k):
    """rd = &mod state column k (r7 = mod state)."""
    c += T.movs_imm8(rd, COL_OFF + 4 * k)
    c += T.add_reg(rd, 7)
    return c


def rowmark(va, L):
    """(r0 view, r1 surface): v043, 3-px corners around the selected row's band (MIDI notes 111-118 act on it);
    nothing when that row is scrolled out of view."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(16)                     # 16 + 16 = 32: [sp] rect
    c += T.mov_reg(6, 1)
    c += T.ldr_imm32(1, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(1, 1, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(2, LA.STATE_OFF + SEL_OFF + 1)
    c += T.add_reg(1, 2)
    c += T.ldrb_imm(4, 1, 0)                  # selected row n
    c += T.ldr_imm32(2, TOP_OFF)
    c += T.add_reg(0, 2)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 5)
    c += T.b_cond(va + len(c), "ls", L.get("topok", va))
    c += T.movs_imm8(0, 5)
    L["topok"] = va + len(c)
    c += T.subs_reg(4, 4, 0)                  # i = n - top
    c += T.cmp_imm(4, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.movs_imm8(0, 40)
    c += T.muls(4, 0)
    c += T.movs_imm8(5, 161)
    c += T.subs_reg(5, 5, 4)                  # r5 = band bottom y = 161 - 40 i
    for dx, dy, w, h in ROWMK:
        c = _imm(c, 0, dx); c += T.str_sp(0, RECT)
        c += T.mov_reg(0, 5)
        if dy:
            c += T.adds_imm8(0, dy)
        c += T.str_sp(0, RECT + 4)
        c += T.movs_imm8(0, w); c += T.str_sp(0, RECT + 8)
        c += T.movs_imm8(0, h); c += T.str_sp(0, RECT + 12)
        c += T.add_rd_sp(0, RECT)
        c += T.movs_imm8(1, C_ROWMK)
        c += T.mov_reg(2, 6)
        c += T.bl(va + len(c), FILLRECT)
    L["out"] = va + len(c)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def paint(va, L, colstate_va, table_va, digits_va, rtick_va=None, menudraw_va=None, pvtile_va=None,
          rowmark_va=None, hdrcol_va=None, filltile_va=None):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)
    c += T.mov_reg(4, 0)                      # r4 = view
    c += T.mov_reg(5, 1)                      # r5 = ctx
    c += T.bl(va + len(c), CONTAINER_DRAW)
    c += T.movs_imm8(1, 1)
    for off in HIDE:
        c += T.ldr_imm32(0, off + 0x30)
        c += T.add_reg(0, 4)
        c += T.strb_imm(1, 0, 0)
        c += T.strb_imm(1, 0, 1)
    if rtick_va is not None:
        c += T.bl(va + len(c), rtick_va)     # v030: repaint countdown after a change
    c += T.ldrb_imm(0, 5, 0)
    c += T.ldrb_imm(1, 5, 1)
    c += T.orrs_reg(0, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm(6, 5, 4)                   # r6 = surface
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, LA.STATE_OFF)
    c += T.adds_reg(7, 0, 1)                  # r7 = mod state
    c += T.ldr_imm32(0, TOP_OFF)
    c += T.add_reg(0, 4)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 5)
    c += T.b_cond(va + len(c), "ls", L.get("topok", va))
    c += T.movs_imm8(0, 5)
    L["topok"] = va + len(c)
    c += T.str_sp(0, TOP)
    c = _rect(c, va, FILLRECT, 0, 1, 320, 220, C_GAP)
    for k in range(8):
        x = 40 * k
        c += T.movs_imm8(0, k)
        c += T.bl(va + len(c), colstate_va)
        # header
        if hdrcol_va is None:
            c = _rect(c, va, FILLRECT, x, 201, 40, 20, C_HEAD)
        else:                                 # v047: flash yellow / selected blue / normal (hdrsel.hdrcol)
            for off, v in ((0, x), (4, 201), (8, 40), (12, 20)):
                c = _imm(c, 0, v); c += T.str_sp(0, RECT + off)
            c += T.movs_imm8(0, k)
            c += T.bl(va + len(c), hdrcol_va)
            c += T.str_sp(1, 24)              # text colour for the name
            c += T.mov_reg(1, 0)
            c += T.add_rd_sp(0, RECT)
            c += T.mov_reg(2, 6)
            c += T.bl(va + len(c), FILLRECT)
        c += T.ldr_imm32(0, LA.SESSION + SECT_NAME0 + 0x30 * k)
        c += T.ldr_imm(0, 0, 0)
        c += T.cmp_imm(0, 0)
        c += T.b_cond(va + len(c), "eq", L.get("dig%d" % k, va))
        c += T.ldrb_imm(1, 0, 0)
        c += T.cmp_imm(1, 0)
        c += T.b_cond(va + len(c), "ne", L.get("txt%d" % k, va))
        L["dig%d" % k] = va + len(c)
        c += T.ldr_imm32(0, digits_va + 2 * k)
        L["txt%d" % k] = va + len(c)
        c += T.str_sp(0, NSLOT)               # keep the string pointer while the rect is built
        for off, v in ((0, x + 2), (4, 207), (8, 36), (12, 8)):
            c = _imm(c, 0, v); c += T.str_sp(0, RECT + off)
        c += T.ldr_sp(0, NSLOT)
        c += T.add_rd_sp(1, RECT)
        if hdrcol_va is None:
            c += T.movs_imm8(2, C_LINE)
        else:
            c += T.ldr_sp(2, 24)
        c += T.mov_reg(3, 6)
        c += T.bl(va + len(c), TEXT1X)
        c = _col_ptr(c, 3, k)
        c += T.ldrb_imm(0, 3, 0)
        c += T.cmp_imm(0, 0xFF)
        c += T.b_cond(va + len(c), "eq", L.get("nomark%d" % k, va))
        c = _rect(c, va, FILLRECT, x + 2, 202, 36, 2, C_BAR)
        L["nomark%d" % k] = va + len(c)
        for i in range(5):
            y = 161 - 40 * i
            t = "%d_%d" % (k, i)
            c += T.ldr_sp(0, TOP)
            c += T.adds_imm8(0, i)
            c += T.str_sp(0, NSLOT)           # n
            c += T.lsls_imm(1, 0, 1)
            c += T.ldr_imm32(2, table_va + 2 * 10 * k)
            c += T.add_reg(2, 1)
            c += T.ldrh_imm(2, 2, 0)
            c += T.ldr_imm32(1, LA.SESSION + 0x1C)
            c += T.add_reg(2, 1)
            c += T.ldr_imm(2, 2, 0)           # event count
            c += T.movs_imm8(1, C_NOTES)
            c += T.cmp_imm(2, 0)
            c += T.b_cond(va + len(c), "ne", L.get("col" + t, va))
            c += T.movs_imm8(1, C_EMPTY)
            L["col" + t] = va + len(c)
            c += T.movs_imm8(3, SEL_OFF)
            c += T.add_reg(3, 7)
            c += T.ldrb_imm(0, 3, 0)
            c += T.cmp_imm(0, k)
            c += T.b_cond(va + len(c), "ne", L.get("ns" + t, va))
            c += T.ldrb_imm(0, 3, 1)
            c += T.ldr_sp(3, NSLOT)
            c += T.cmp_reg(0, 3)
            c += T.b_cond(va + len(c), "ne", L.get("ns" + t, va))
            c += T.movs_imm8(1, C_SEL)       # the selected clip: stock blue fill
            L["ns" + t] = va + len(c)
            if filltile_va is not None:       # v055: selected row, fill on, clip with FILL notes -> vermillion
                c += T.movs_imm8(0, k)
                c += T.ldr_sp(2, NSLOT)
                c += T.bl(va + len(c), filltile_va)
            # FillRect(cell, r1 colour)
            for off, v in ((0, x + 1), (4, y), (8, 39), (12, 39)):     # v056: 39 x 39, 1-px gaps (was 38 at y+1)
                c = _imm(c, 0, v); c += T.str_sp(0, RECT + off)
            c += T.add_rd_sp(0, RECT)
            c += T.mov_reg(2, 6)
            c += T.bl(va + len(c), FILLRECT)
            if pvtile_va is not None:         # v039: the clip's mini note preview
                c += T.mov_reg(0, 4)
                c += T.movw(1, k | i << 8)
                c += T.ldr_sp(2, NSLOT)
                c += T.mov_reg(3, 6)
                c += T.bl(va + len(c), pvtile_va)
            # playing?
            c = _col_ptr(c, 3, k)
            c += T.ldrb_imm(0, 3, 0)
            c += T.ldr_sp(1, NSLOT)
            c += T.cmp_reg(0, 1)
            c += T.b_cond_w(va + len(c), "ne", L.get("np" + t, va))
            c = _rect(c, va, RECTOUTL, x + 1, y, 39, 39, C_LINE)
            c = _rect(c, va, RECTOUTL, x + 2, y + 1, 37, 9, C_BAR)
            c = _col_ptr(c, 3, k)
            c += T.ldrh_imm(0, 3, 2)
            c += T.movs_imm8(1, 37)
            c += T.muls(0, 1)
            c += T.movw(1, 1000)
            c += T.udiv(0, 0, 1)              # width 0..37
            c += T.cmp_imm(0, 0)
            c += T.b_cond(va + len(c), "eq", L.get("np" + t, va))
            c = _rect(c, va, FILLRECT, x + 2, y + 1, 0, 9, C_BAR, w_from_r0=True)
            L["np" + t] = va + len(c)
            # pending?
            c = _col_ptr(c, 3, k)
            c += T.ldrb_imm(0, 3, 1)
            c += T.ldr_sp(1, NSLOT)
            c += T.cmp_reg(0, 1)
            c += T.b_cond(va + len(c), "ne", L.get("npe" + t, va))
            c = _rect(c, va, RECTOUTL, x, y, 40, 40, C_PEND)
            L["npe" + t] = va + len(c)
    # v056: scroll triangles at the right edge: up while rows are hidden above (top > 0), down while below (top < 5)
    c += T.ldr_sp(0, TOP)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("noup", va))
    for i, (x_, w_) in enumerate(SCROLL_ROWS):
        c = _rect(c, va, FILLRECT, x_, 197 - i, w_, 1, C_LINE)
    L["noup"] = va + len(c)
    c += T.ldr_sp(0, TOP)
    c += T.cmp_imm(0, 5)
    c += T.b_cond_w(va + len(c), "cs", L.get("nodown", va))
    for i, (x_, w_) in enumerate(SCROLL_ROWS):
        c = _rect(c, va, FILLRECT, x_, 2 + i, w_, 1, C_LINE)
    L["nodown"] = va + len(c)
    if rowmark_va is not None:                # v043: corners of the MIDI-actionable (selected) row
        c += T.mov_reg(0, 4)
        c += T.mov_reg(1, 6)
        c += T.bl(va + len(c), rowmark_va)
    if menudraw_va is not None:               # v038: the long-press clip menu on top of the grid
        c += T.mov_reg(0, 4)
        c += T.mov_reg(1, 6)
        c += T.bl(va + len(c), menudraw_va)
    L["out"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
