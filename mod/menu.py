"""v038 L3 long-press clip menu: CLEAR / UNDO, as the stock SEQS panel buttons (no OFF).

A long press (>= 400 ms) on a clip selects it and opens the menu (mod state +104 = 1). The menu is two 40x40
buttons in the row below the selected clip (above it on the bottom visible row). While it is open, the next
release goes to MTAP: CLEAR / UNDO / outside; every tap closes it.

CLEAR (MCLEAR) = the stock single-pattern clear 0x0809F820 applied to the clip's own record: Snap (the stock UNDO
snapshot of the cell), clear the UI container, ClearSlot the record's own engine slot (unless it is a host slot
that holds another streamed clip), restream every host slot holding the clip (STREAM of the now empty record),
UI msg 0x66, grid refresh flag.
UNDO = stock Undo 0x080988D4 unchanged (its SendPattern re-sends go through SYNC), guarded: stock restores desc 0
and empties cell (0,0) when no snapshot was taken yet.
"""
import thumb as T
import phase5 as P5
import launch as LA
import paint as PT

MENU_OFF = 104                              # mod state: 1 = menu open (target = the selection +80/+81)
SEL_OFF = 80
SNAP, CLEARCONT, UNDO = 0x08098254, 0x08063CC0, 0x080988D4
NOTE_POST = 0x080B5758                      # (session + 0x30, msg*): UI notification queue
MSG_VT, MSG66_VT = 0x080EAF38, 0x080CFBA4
UNDO_DESC = 0xE91C                          # session: u16 desc of the cell in the UNDO snapshot
GRID_DIRTY = 0x8CC4
C_BOX, C_BTN = PT.C_HEAD, PT.C_PEND         # dark box, white outlines and labels
STRINGS = b"CLEAR\0\0\0UNDO\0\0\0\0"        # +0 "CLEAR", +8 "UNDO"


def menupos(va, L):
    """(r0 view) -> r0 = x0, r1 = y0 (y-up bottom) of the 80x40 menu, or r0 = -1 (closed / clip not visible).
    Leaf, clobbers r0-r3."""
    c = T.mov_reg(3, 0)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("none", va))
    c += T.ldr_imm32(2, LA.STATE_OFF + SEL_OFF)
    c += T.adds_reg(2, 2, 0)                 # r2 = &sel
    c += T.ldrb_imm(1, 2, MENU_OFF - SEL_OFF)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("none", va))
    c += T.ldr_imm32(1, PT.TOP_OFF)
    c += T.add_reg(1, 3)
    c += T.ldr_imm(1, 1, 0)
    c += T.cmp_imm(1, 5)
    c += T.b_cond(va + len(c), "ls", L.get("topok", va))
    c += T.movs_imm8(1, 5)
    L["topok"] = va + len(c)
    c += T.ldrb_imm(0, 2, 1)                 # n
    c += T.subs_reg(0, 0, 1)                 # i = n - top
    c += T.cmp_imm(0, 4)
    c += T.b_cond(va + len(c), "hi", L.get("none", va))   # also n < top (unsigned)
    c += T.movs_imm8(1, 40)
    c += T.muls(1, 0)
    c += T.movs_imm8(3, 161)
    c += T.subs_reg(3, 3, 1)                 # row y = 161 - 40 i
    c += T.cmp_imm(0, 4)
    c += T.b_cond(va + len(c), "eq", L.get("up", va))
    c += T.subs_imm8(3, 40)                  # below the clip
    c += T.b_short(va + len(c), L.get("ydone", va))
    L["up"] = va + len(c)
    c += T.adds_imm8(3, 40)                  # bottom visible row: above it
    L["ydone"] = va + len(c)
    c += T.ldrb_imm(0, 2, 0)                 # k
    c += T.movs_imm8(1, 40)
    c += T.muls(0, 1)
    c += T.cmp_imm(0, 240)
    c += T.b_cond(va + len(c), "ls", L.get("xok", va))
    c += T.movs_imm8(0, 240)
    L["xok"] = va + len(c)
    c += T.mov_reg(1, 3)
    c += T.bx(14)
    L["none"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.subs_imm8(0, 1)
    c += T.bx(14)
    return c


def _r(c, va, prim, dx, dy, w, h, colour):
    """prim(&{r4 + dx, r5 + dy, w, h}, colour, r6 surface). Rect at [sp]."""
    for off, reg, d in ((0, 4, dx), (4, 5, dy)):
        c += T.mov_reg(0, reg)
        if d:
            c += T.adds_imm8(0, d)
        c += T.str_sp(0, off)
    c += T.movs_imm8(0, w); c += T.str_sp(0, 8)
    c += T.movs_imm8(0, h); c += T.str_sp(0, 12)
    c += T.add_rd_sp(0, 0)
    c += T.movs_imm8(1, colour)
    c += T.mov_reg(2, 6)
    c += T.bl(va + len(c), prim)
    return c


def menudraw(va, L, pos_va, str_va):
    """(r0 view, r1 surface): called by PAINT after the grid."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(20)                    # 20 + 20 = 40: [sp] rect
    c += T.mov_reg(6, 1)
    c += T.bl(va + len(c), pos_va)
    c += T.mov_reg(2, 0)
    c += T.adds_imm8(2, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c = _r(c, va, PT.FILLRECT, 0, 0, 80, 40, C_BOX)
    c = _r(c, va, PT.RECTOUTL, 1, 1, 38, 38, C_BTN)
    c = _r(c, va, PT.RECTOUTL, 41, 1, 38, 38, C_BTN)
    for dx, s in ((3, 0), (46, 8)):
        c += T.mov_reg(0, 4); c += T.adds_imm8(0, dx); c += T.str_sp(0, 0)
        c += T.mov_reg(0, 5); c += T.adds_imm8(0, 16); c += T.str_sp(0, 4)
        c += T.movs_imm8(0, 36); c += T.str_sp(0, 8)
        c += T.movs_imm8(0, 8); c += T.str_sp(0, 12)
        c += T.ldr_imm32(0, str_va + s)
        c += T.add_rd_sp(1, 0)
        c += T.movs_imm8(2, C_BTN)
        c += T.mov_reg(3, 6)
        c += T.bl(va + len(c), PT.TEXT1X)
    L["out"] = va + len(c)
    c += T.add_sp_imm(20)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def menutap(va, L, pos_va, clear_va):
    """(r0 view, r1 touch record {+4 u16 x, +6 u16 y, y-up}): a release while the menu is open. Closes it."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(4)
    c += T.mov_reg(6, 1)
    c += T.bl(va + len(c), pos_va)
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.ldr_imm32(7, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(7, 7, 0)
    c += T.cmp_imm(7, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + SEL_OFF)
    c += T.add_reg(7, 0)                     # r7 = &sel
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 7, MENU_OFF - SEL_OFF)   # close
    c += T.mov_reg(0, 4)
    c += T.adds_imm8(0, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldrh_imm(0, 6, 6)
    c += T.subs_reg(0, 0, 5)
    c += T.cmp_imm(0, 40)
    c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    c += T.ldrh_imm(0, 6, 4)
    c += T.subs_reg(0, 0, 4)
    c += T.cmp_imm(0, 80)
    c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    c += T.cmp_imm(0, 40)
    c += T.b_cond(va + len(c), "cs", L.get("undo", va))
    c += T.ldrb_imm(0, 7, 0)
    c += T.ldrb_imm(1, 7, 1)
    c += T.bl(va + len(c), clear_va)
    c += T.b_short(va + len(c), L.get("out", va))
    L["undo"] = va + len(c)
    c += T.ldr_imm32(0, LA.SESSION + UNDO_DESC)
    c += T.ldrh_imm(0, 0, 0)
    c += T.lsrs_imm(0, 0, 8)
    c += T.movs_imm8(1, 0x1F)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 1)                     # a sequence-cell snapshot exists
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c += T.ldr_imm32(0, LA.SESSION)
    c += T.bl(va + len(c), UNDO)
    L["out"] = va + len(c)
    c += T.add_sp_imm(4)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def _desc(c, rd, tmp):
    """rd = 0x100 | row(r6) << 4 | col(r7)."""
    c += T.lsls_imm(rd, 6, 4)
    c += T.orrs_reg(rd, 7)
    c += T.movs_imm8(tmp, 1)
    c += T.lsls_imm(tmp, tmp, 8)
    c += T.orrs_reg(rd, tmp)
    return c


def clipclear(va, L, table_va, restream_va):
    """(r0 k, r1 n): clear L3 clip (k, n) as the stock single-pattern CLR does."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(28)                    # 20 + 28 = 48: [sp..+0x17] msg
    c += T.movs_imm8(2, 10)
    c += T.muls(2, 0)
    c += T.adds_reg(2, 2, 1)
    c += T.lsls_imm(2, 2, 1)
    c += T.ldr_imm32(3, table_va)
    c += T.add_reg(3, 2)
    c += T.ldrh_imm(4, 3, 0)                 # record offset
    c += T.ldr_imm32(5, LA.SESSION)
    c += T.add_reg(5, 4)                     # r5 = record
    c += T.movw(0, 0x1C00)
    c += T.subs_reg(0, 4, 0)
    c += T.movw(1, 0x370)
    c += T.udiv(6, 0, 1)                     # r6 = row
    c += T.muls(1, 6)
    c += T.subs_reg(0, 0, 1)
    c += T.movs_imm8(1, 0xB0)
    c += T.udiv(7, 0, 1)                     # r7 = col
    c += T.muls(1, 7)
    c += T.subs_reg(0, 0, 1)
    c += T.movs_imm8(1, 0x2C)
    c += T.udiv(4, 0, 1)                     # r4 = pattern
    # Snap(S, m{vt, desc}): the stock UNDO snapshot of the cell
    c += T.ldr_imm32(0, MSG_VT)
    c += T.str_sp(0, 0)
    c = _desc(c, 0, 1)
    c += T.add_rd_sp(1, 0)
    c += T.strh_imm(0, 1, 4)
    c += T.ldr_imm32(0, LA.SESSION)
    c += T.bl(va + len(c), SNAP)
    c += T.mov_reg(0, 5)
    c += T.adds_imm8(0, 0x18)
    c += T.bl(va + len(c), CLEARCONT)
    # the record's own engine slot, unless it is a host slot (p >= 1) holding another streamed clip
    c += T.cmp_imm(6, 1)
    c += T.b_cond(va + len(c), "hi", L.get("direct", va))
    c += T.cmp_imm(7, 3)
    c += T.b_cond(va + len(c), "hi", L.get("direct", va))
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("direct", va))
    c += T.ldr_imm32(1, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(1, 1, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("direct", va))
    c += T.lsls_imm(0, 6, 2)
    c += T.adds_reg(0, 0, 7)                 # host column kh
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 4)
    c += T.adds_reg(1, 1, 0)
    c += T.ldr_imm32(0, LA.STATE_OFF + 4)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                 # slot_clip[kh][p]
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("streamed", va))
    L["direct"] = va + len(c)
    c += T.lsls_imm(1, 6, 8)
    c += T.orrs_reg(1, 7)
    c += T.movs_imm8(0, 1)
    c += T.lsls_imm(0, 0, 16)
    c += T.orrs_reg(1, 0)
    c += T.movs_imm8(2, 0)
    c += T.mov_reg(3, 4)
    c += T.ldr_imm32(0, LA.ENGINE)
    c += T.bl(va + len(c), LA.CLEARSLOT)
    L["streamed"] = va + len(c)
    c += T.mov_reg(0, 6)
    c += T.mov_reg(1, 7)
    c += T.mov_reg(2, 4)
    c += T.bl(va + len(c), restream_va)
    # UI msg 0x66 {u16 0x66, vt, u16 desc @8, 1, 0, 0}, then the grid refresh flag
    c += T.movs_imm8(0, 0)
    for off in (0, 0x10, 0x14):
        c += T.str_sp(0, off)
    c += T.movs_imm8(0, 1)
    c += T.str_sp(0, 0xC)
    c += T.ldr_imm32(0, MSG66_VT)
    c += T.str_sp(0, 4)
    c += T.add_rd_sp(1, 0)
    c += T.movs_imm8(0, 0x66)
    c += T.strh_imm(0, 1, 0)
    c = _desc(c, 0, 2)
    c += T.strh_imm(0, 1, 8)
    c += T.ldr_imm32(0, LA.SESSION + 0x30)
    c += T.bl(va + len(c), NOTE_POST)
    c += T.ldr_imm32(0, LA.SESSION + GRID_DIRTY)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    c += T.add_sp_imm(28)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
