"""v028 L3 touch: taps on the painted grid.

With the stock children hidden, the SEQS view is the touch target. Its press (vt+0x10, 0x080B4C2C) and
release (vt+0x18, 0x080B48C2) handlers act only in drag mode ([view+0x1AF9]). TPRESS / TREL call them
first, then: press = record HAL tick + position, arm (not in drag mode); release = if armed and
< 400 ms: header -> stop column, clip = launch (or stop when it is the playing clip) via the v025
request word, then SelectSeqCell(host cell) unless [session+0x8CC1] == 1. Point {i32 x, i32 y}, y-up.
"""
import struct

import thumb as T
import phase5 as P5
import launch as LA
import paint as PT

VT_PRESS_SITE, VT_PRESS_ORIG = 0x080F0EA0, struct.pack("<I", 0x080B4C2D)
VT_REL_SITE, VT_REL_ORIG = 0x080F0EA8, struct.pack("<I", 0x080B48C3)
PRESS_FN, REL_FN = 0x080B4C2C, 0x080B48C2
TICK = 0x24015CE4
DRAG_OFF = 0x1AF9
SELECT = 0x08098328                         # SelectSeqCell(session, msg*{vt, u16 desc at +4})
MSG_VT = 0x080EAF38
AUTOLAUNCH = 0x8CC1
ROOT_PTR, VIEW_OFF = 0x24002E6C, 0x39F90    # UI root pointer; SEQS view = root + 0x39F90
DIRTY_OFF = 0x34 + 0x17D                    # hidden cell 0 bar-dirty byte: ORed into the draw ctx (0x080A4272)
REPAINT_OFF, REPAINT_N = 88, 3              # mod state: repaint countdown (passes) after a change (v030)
T_BASE = 68                                 # +0 tick, +4 x, +6 y, +8 armed
TAP_MS = 400
SEL_OFF = 80                                # +0 sel_k, +1 sel_n
MENU_OFF = 104                              # v038: clip menu open (menu.py)
ENC_SITE, ENC_ORIG = 0x080B54A8, bytes.fromhex("cb680969")   # ldr r3,[r1,#0xc]; ldr r1,[r1,#0x10]
ENC_BACK = 0x080B54AC                       # stock encoder case continues (r3 = index, r1 = delta)
VALUE_UPDATE = 0x080B0B74                   # stock knob value object update(obj, raw delta); position at obj+0xC
ENC_DONE = 0x080B5308                       # shared epilogue: add sp,#0x54; pop {r4-r9,pc}


def _state(c, va, L, rd, out):
    """rd = mod state, or branch to `out` if the descriptor array is not there yet. Uses r3."""
    c += T.ldr_imm32(rd, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(rd, rd, 0)
    c += T.cmp_imm(rd, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get(out, va))
    c += T.ldr_imm32(3, LA.STATE_OFF)
    c += T.add_reg(rd, 3)
    return c


def tpress(va, L):
    c = T.push_lo([4, 5, 6], lr=True)        # 16 B: sp stays 8-aligned at the bl
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.bl(va + len(c), PRESS_FN)
    c += T.mov_reg(6, 0)                     # stock return value
    c += T.ldr_imm32(1, DRAG_OFF)
    c += T.add_reg(1, 4)
    c += T.ldrb_imm(1, 1, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c = _state(c, va, L, 2, "out")
    c += T.adds_imm8(2, T_BASE)
    c += T.ldr_imm32(3, TICK)
    c += T.ldr_imm(3, 3, 0)
    c += T.str_imm(3, 2, 0)
    c += T.ldr_imm(3, 5, 0)
    c += T.strh_imm(3, 2, 4)
    c += T.ldr_imm(3, 5, 4)
    c += T.strh_imm(3, 2, 6)
    c += T.movs_imm8(3, 1)
    c += T.strb_imm(3, 2, 8)
    L["out"] = va + len(c)
    c += T.mov_reg(0, 6)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


FR = 20                                      # 20 pushed + 20 = 40: [sp..+15] msg, [sp+16] return value


def trel(va, L, descs_va, dirty_va=None, table_va=None, selclip_va=None, menutap_va=None, colopen_va=None,
         hsel_va=None, hstop=False):
    fr = FR if menutap_va is None else FR + 8   # v038: [sp+20] = long press
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(fr)
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.bl(va + len(c), REL_FN)
    c += T.str_sp(0, 16)
    c = _state(c, va, L, 7, "out")           # r7 = mod state
    c += T.movs_imm8(6, T_BASE)
    c += T.add_reg(6, 7)                     # r6 = touch record
    c += T.ldrb_imm(0, 6, 8)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 6, 8)                 # disarm
    c += T.ldr_imm32(1, DRAG_OFF)
    c += T.add_reg(1, 4)
    c += T.ldrb_imm(1, 1, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    if menutap_va is not None:               # v038: menu open -> this release belongs to the menu
        c += T.movs_imm8(0, MENU_OFF)
        c += T.add_reg(0, 7)
        c += T.ldrb_imm(0, 0, 0)
        c += T.cmp_imm(0, 0)
        c += T.b_cond(va + len(c), "eq", L.get("nomenu", va))
        c += T.mov_reg(0, 4)
        c += T.mov_reg(1, 6)
        c += T.bl(va + len(c), menutap_va)
        c += T.bw(va + len(c), L.get("out", va))
        L["nomenu"] = va + len(c)
    c += T.ldr_imm32(0, TICK)
    c += T.ldr_imm(0, 0, 0)
    c += T.ldr_imm(1, 6, 0)
    c += T.subs_reg(0, 0, 1)                 # held ms (unsigned)
    c += T.movw(1, TAP_MS)
    if menutap_va is None:
        c += T.cmp_reg(0, 1)
        c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    else:
        c += T.movs_imm8(2, 0)
        c += T.cmp_reg(0, 1)
        c += T.b_cond(va + len(c), "cc", L.get("short", va))
        c += T.movs_imm8(2, 1)
        L["short"] = va + len(c)
        c += T.str_sp(2, 20)
    c += T.ldrh_imm(0, 6, 4)                 # x
    c += T.movs_imm8(1, 40)
    c += T.udiv(5, 0, 1)                     # r5 = k
    c += T.cmp_imm(5, 8)
    c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    c += T.ldrh_imm(0, 6, 6)                 # y (y-up)
    c += T.cmp_imm(0, 220)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.cmp_imm(0, 201)
    c += T.b_cond_w(va + len(c), "cs", L.get("stop" if menutap_va is None else "hdr", va))
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "cc", L.get("out", va))
    c += T.movs_imm8(1, 200)
    c += T.subs_reg(1, 1, 0)
    c += T.movs_imm8(2, 40)
    c += T.udiv(1, 1, 2)                     # i = (200 - y) / 40
    c += T.ldr_imm32(0, PT.TOP_OFF)
    c += T.add_reg(0, 4)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 5)
    c += T.b_cond(va + len(c), "ls", L.get("topok", va))
    c += T.movs_imm8(0, 5)
    L["topok"] = va + len(c)
    c += T.adds_reg(1, 1, 0)                 # r1 = n
    c += T.movs_imm8(2, SEL_OFF)
    c += T.add_reg(2, 7)
    c += T.strb_imm(5, 2, 0)                 # selection = (k, n): a tap always selects the clip
    c += T.strb_imm(1, 2, 1)
    if selclip_va is not None:               # v033: INFO/editors follow the selected clip
            c += T.bl(va + len(c), selclip_va)
            c += T.movs_imm8(2, SEL_OFF)
            c += T.add_reg(2, 7)
            c += T.ldrb_imm(1, 2, 1)             # n again (SELCLIP clobbers r0-r3)
    if menutap_va is not None:               # v038: a long press selects the clip and opens the menu
        c += T.ldr_sp(3, 20)
        c += T.cmp_imm(3, 0)
        c += T.b_cond(va + len(c), "eq", L.get("tapgo", va))
        c += T.movs_imm8(3, MENU_OFF)
        c += T.add_reg(3, 7)
        c += T.movs_imm8(0, 1)
        c += T.strb_imm(0, 3, 0)
        c += T.bw(va + len(c), L.get("out", va))
        L["tapgo"] = va + len(c)
    if table_va is not None:                 # v030: an empty clip only selects, as stock
        c += T.movs_imm8(2, 10)
        c += T.muls(2, 5)
        c += T.adds_reg(2, 2, 1)
        c += T.lsls_imm(2, 2, 1)
        c += T.ldr_imm32(3, table_va)
        c += T.add_reg(3, 2)
        c += T.ldrh_imm(3, 3, 0)
        c += T.ldr_imm32(2, LA.SESSION + 0x1C)
        c += T.add_reg(3, 2)
        c += T.ldr_imm(3, 3, 0)              # event count of the clip's record
        c += T.cmp_imm(3, 0)
        c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.lsls_imm(2, 5, 2)
    c += T.adds_imm8(2, PT.COL_OFF)
    c += T.add_reg(2, 7)
    c += T.ldrb_imm(3, 2, 0)                 # play_n of column k
    c += T.cmp_reg(3, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("stop", va))
    c += T.ldrb_imm(3, 2, 1)                 # v030: the white-marked clip (armed / pending) un-launches
    c += T.cmp_reg(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("notmarked", va))
    c += T.ldrb_imm(3, 2, 0)                 # v031: ...but only when the column is not playing another
    c += T.cmp_imm(3, 0xFF)                  # clip: then a tap on the pending clip only selects it
    c += T.b_cond_w(va + len(c), "eq", L.get("stop", va))
    c += T.bw(va + len(c), L.get("out", va))
    L["notmarked"] = va + len(c)
    # launch request, then select the host cell
    c += T.lsls_imm(0, 5, 8)
    c += T.orrs_reg(0, 1)
    c += T.ldr_imm32(3, LA.REQ_LAUNCH)
    c += T.orrs_reg(0, 3)
    c += T.str_imm(0, 7, 0)
    if selclip_va is None:                   # v029-v032: select the host cell
        c += T.ldr_imm32(0, LA.SESSION + AUTOLAUNCH)
        c += T.ldrb_imm(0, 0, 0)
        c += T.cmp_imm(0, 1)
        c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
        c += T.movs_imm8(0, 0)
        for off in (0, 4, 8, 12):
            c += T.str_sp(0, off)
        c += T.ldr_imm32(0, MSG_VT)
        c += T.str_sp(0, 0)
        c += T.ldr_imm32(0, descs_va)
        c += T.lsls_imm(1, 5, 1)
        c += T.add_reg(0, 1)
        c += T.ldrh_imm(0, 0, 0)
        c += T.mov_reg(1, 13)
        c += T.strh_imm(0, 1, 4)
        c += T.ldr_imm32(0, LA.SESSION)
        c += T.bl(va + len(c), SELECT)
    c += T.bw(va + len(c), L.get("out", va))
    if menutap_va is not None:               # v038: a long press on a header does nothing yet
        L["hdr"] = va + len(c)
        c += T.ldr_sp(2, 20)
        c += T.cmp_imm(2, 0)
        if colopen_va is None:
            c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
        else:                                # v045: a long press on a header opens the column settings page
            c += T.b_cond(va + len(c), "eq", L.get("stop" if hsel_va is None else "hshort", va))
            c += T.mov_reg(0, 5)
            c += T.bl(va + len(c), colopen_va)
            c += T.bw(va + len(c), L.get("out", va))
            if hsel_va is not None:              # v047: a header tap selects + flashes; no stop any more
                L["hshort"] = va + len(c)
                c += T.mov_reg(0, 5)
                c += T.bl(va + len(c), hsel_va)
                if hstop:                        # v056: ... and stops the column again (HSEL keeps r5, r7)
                    c += T.bw(va + len(c), L.get("stop", va))
                else:
                    c += T.bw(va + len(c), L.get("out", va))
    L["stop"] = va + len(c)
    c += T.lsls_imm(0, 5, 8)
    c += T.ldr_imm32(3, LA.REQ_STOP)
    c += T.orrs_reg(0, 3)
    c += T.str_imm(0, 7, 0)
    L["out"] = va + len(c)
    if dirty_va is not None:
        c += T.bl(va + len(c), dirty_va)     # repaint now, also while stopped (v030)
    c += T.ldr_sp(0, 16)
    c += T.add_sp_imm(fr)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def dirty(va, L):
    """Mark the SEQS view dirty (hidden cell 0 +0x17D) and arm the repaint countdown. Clobbers r0, r1."""
    c = T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("st", va))
    c += T.ldr_imm32(1, VIEW_OFF + DIRTY_OFF)
    c += T.add_reg(0, 1)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    L["st"] = va + len(c)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + REPAINT_OFF)
    c += T.add_reg(0, 1)
    c += T.movs_imm8(1, REPAINT_N)
    c += T.strb_imm(1, 0, 0)
    L["ret"] = va + len(c)
    c += T.bx(14)
    return c


def rtick(va, L):
    """Called by PAINT on every pass: while the countdown runs, mark the next pass dirty too, so the
    engine's reply to a launch (marker, slot) is drawn while the transport is stopped. Clobbers r0-r2."""
    c = T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + REPAINT_OFF)
    c += T.add_reg(0, 1)
    c += T.ldrb_imm(1, 0, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.subs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    c += T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(1, VIEW_OFF + DIRTY_OFF)
    c += T.add_reg(0, 1)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    L["ret"] = va + len(c)
    c += T.bx(14)
    return c


def _clamp(c, va, L, tag, reg, hi):
    c += T.cmp_imm(reg, 0)
    c += T.b_cond(va + len(c), "ge", L.get(tag + "lo", va))
    c += T.movs_imm8(reg, 0)
    L[tag + "lo"] = va + len(c)
    c += T.cmp_imm(reg, hi)
    c += T.b_cond(va + len(c), "le", L.get(tag + "hi", va))
    c += T.movs_imm8(reg, hi)
    L[tag + "hi"] = va + len(c)
    return c


def enc(va, L, dirty_va=None, selclip_va=None, header=False):
    """At 0x080B54A8 (SEQS msg 0x32 = encoder): r1 = msg, r5 = view. TL (0) / TR (2) move the L3
    selection; other knobs run the displaced loads and continue. Uses r0-r3 only."""
    L["dirty_va"] = dirty_va
    c = T.ldr_imm(3, 1, 0xC)                 # displaced 1: r3 = encoder index
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ours", va))
    c += T.cmp_imm(3, 2)
    c += T.b_cond(va + len(c), "eq", L.get("ours", va))
    c += T.ldr_imm(1, 1, 0x10)               # displaced 2: r1 = delta
    c += T.bw(va + len(c), ENC_BACK)
    L["ours"] = va + len(c)
    # the message carries a RAW movement: let the stock value object turn it into whole steps (as the
    # stock TL/TR path does at 0x080B54B4/0x080B5514) and move the selection by the position change
    c += T.push_lo([4, 6])                   # 8 B: sp stays 8-aligned (handler frame) at the bl
    c += T.mov_reg(4, 3)                     # r4 = index
    c += T.ldr_imm(1, 1, 0x10)               # r1 = raw delta
    c += T.movw(0, 0x1A98)                   # TL value object
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("obj", va))
    c += T.movw(0, 0x1AB0)                   # TR value object
    L["obj"] = va + len(c)
    c += T.add_reg(0, 5)
    c += T.ldr_imm(6, 0, 0xC)                # r6 = old position
    c += T.bl(va + len(c), VALUE_UPDATE)
    c += T.movw(0, 0x1A98)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("obj2", va))
    c += T.movw(0, 0x1AB0)
    L["obj2"] = va + len(c)
    c += T.add_reg(0, 5)
    c += T.ldr_imm(0, 0, 0xC)                # new position
    c += T.subs_reg(1, 0, 6)                 # d = new - old (v030: inverted after the hardware test)
    c += T.b_cond_w(va + len(c), "eq", L.get("done", va))
    # TL/TR objects wrap modulo their count (16): d mod count into -count/2 .. count/2 (v028)
    c += T.movw(2, 0x1A98)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("obj3", va))
    c += T.movw(2, 0x1AB0)
    L["obj3"] = va + len(c)
    c += T.add_reg(2, 5)
    c += T.ldr_imm(2, 2, 0x10)               # count
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ge", L.get("dpos", va))
    c += T.adds_reg(1, 1, 2)
    L["dpos"] = va + len(c)
    c += T.lsls_imm(3, 1, 1)
    c += T.cmp_reg(3, 2)
    c += T.b_cond(va + len(c), "lt", L.get("stepok", va))
    c += T.subs_reg(1, 1, 2)
    L["stepok"] = va + len(c)
    c += T.mov_reg(0, 4)                     # r0 = index
    c = _state(c, va, L, 2, "done")          # r2 = mod state (uses r3)
    c += T.adds_imm8(2, SEL_OFF)             # r2 = &sel
    c += T.cmp_imm(0, 2)                     # v032: TR (2) = columns, TL (0) = rows
    c += T.b_cond(va + len(c), "ne", L.get("tr", va))
    c += T.ldrb_imm(3, 2, 0)
    c += T.adds_reg(3, 3, 1)
    c = _clamp(c, va, L, "k", 3, 7)
    c += T.strb_imm(3, 2, 0)
    c += T.b_short(va + len(c), L.get("done", va))
    L["tr"] = va + len(c)
    c += T.ldrb_imm(3, 2, 1)
    if header:                               # v047: the header row (sel_n 0xFF) sits above row 1
        c += T.cmp_imm(3, 0xFF)
        c += T.b_cond(va + len(c), "ne", L.get("rows", va))
        c += T.cmp_imm(1, 0)
        c += T.b_cond_w(va + len(c), "le", L.get("done", va))
        c += T.subs_imm(3, 1, 1)             # down from the header: row 1 (+ further steps)
        c += T.b_short(va + len(c), L.get("clampn", va))
        L["rows"] = va + len(c)
        c += T.adds_reg(3, 3, 1)
        c += T.cmp_imm(3, 0)
        c += T.b_cond(va + len(c), "ge", L.get("clampn", va))
        c += T.ldrb_imm(0, 2, 1)
        c += T.strb_imm(0, 2, 28)            # hdrsel.LAST_OFF: the clip row left behind
        c += T.movs_imm8(0, 0xFF)
        c += T.strb_imm(0, 2, 1)
        c += T.b_short(va + len(c), L.get("done", va))
        L["clampn"] = va + len(c)
    else:
        c += T.adds_reg(3, 3, 1)
    c = _clamp(c, va, L, "n", 3, 9)
    c += T.strb_imm(3, 2, 1)
    c += T.ldr_imm32(0, PT.TOP_OFF)
    c += T.add_reg(0, 5)
    c += T.ldr_imm(1, 0, 0)                  # top
    c += T.cmp_reg(3, 1)
    c += T.b_cond(va + len(c), "cs", L.get("below", va))
    c += T.mov_reg(1, 3)                     # n < top -> top = n
    c += T.b_short(va + len(c), L.get("set", va))
    L["below"] = va + len(c)
    c += T.adds_imm(2, 1, 4)
    c += T.cmp_reg(3, 2)
    c += T.b_cond(va + len(c), "ls", L.get("done", va))
    c += T.subs_imm(1, 3, 4)                 # n > top + 4 -> top = n - 4
    L["set"] = va + len(c)
    # scroll through the BR value object so its accumulator stays in step (v028)
    c += T.ldr_imm(2, 0, 0)
    c += T.subs_reg(1, 1, 2)                 # rows to move
    c += T.movw(0, 0x1AE0)
    c += T.add_reg(0, 5)
    c += T.ldr_imm(2, 0, 8)                  # raw units per step
    c += T.muls(1, 2)
    c += T.bl(va + len(c), VALUE_UPDATE)
    L["done"] = va + len(c)
    if selclip_va is not None:
        c += T.bl(va + len(c), selclip_va)   # v033: the editor target follows the highlight
    if L["dirty_va"] is not None:
        c += T.bl(va + len(c), L["dirty_va"])    # repaint now, also while stopped (v030)
    c += T.pop_lo([4, 6])
    c += T.bw(va + len(c), ENC_DONE)
    return c


SETPARAM_FN = 0x08093ECC                    # local SetParam(owner, id, value): no engine post


def selclip(va, L, table_va, guard=False):
    """Select the L3-selected clip's own record for INFO / the editors: UI 0xC0 of its cell := its pattern
    (local), then SelectSeqCell(cell) unless [session+0x8CC1] == 1. Clobbers r0-r3."""
    FR = 24                                 # 16 pushed + 24 = 40: [sp..+15] msg, [sp+16] pattern
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(FR)
    c = _state(c, va, L, 4, "out")          # r4 = mod state
    c += T.movs_imm8(3, SEL_OFF)
    c += T.add_reg(3, 4)
    c += T.ldrb_imm(0, 3, 0)
    c += T.ldrb_imm(1, 3, 1)
    if guard:                               # v047: sel_n 0xFF = a header: no clip to select
        c += T.cmp_imm(1, 9)
        c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.movs_imm8(2, 10)
    c += T.muls(0, 2)
    c += T.adds_reg(0, 0, 1)                # kn
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)
    c += T.ldr_imm32(1, 0x1C00)
    c += T.subs_reg(0, 0, 1)                # r*0x370 + c*0xB0 + p*0x2C
    c += T.movw(1, 0x370)
    c += T.udiv(5, 0, 1)                    # r5 = row
    c += T.muls(1, 5)
    c += T.subs_reg(0, 0, 1)
    c += T.movs_imm8(1, 0xB0)
    c += T.udiv(6, 0, 1)                    # r6 = col
    c += T.muls(1, 6)
    c += T.subs_reg(0, 0, 1)
    c += T.movs_imm8(1, 0x2C)
    c += T.udiv(0, 0, 1)
    c += T.str_sp(0, 16)                    # pattern
    c += T.movs_imm8(0, 5)                  # v034: remember the selected cell index row*5+col (+82)
    c += T.muls(0, 5)
    c += T.adds_reg(0, 0, 6)
    c += T.movs_imm8(1, SEL_OFF + 2)
    c += T.add_reg(1, 4)
    c += T.strb_imm(0, 1, 0)
    c += T.ldr_sp(0, 16)
    c += T.strb_imm(0, 1, 1)                 # +83: the selected pattern (v034)
    c += T.movw(0, 0x370)
    c += T.muls(0, 5)
    c += T.movs_imm8(1, 0xB0)
    c += T.muls(1, 6)
    c += T.adds_reg(0, 0, 1)
    c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
    c += T.adds_reg(0, 0, 1)                # cell pattern-0 record
    c += T.movs_imm8(1, 0xC0)
    c += T.ldr_sp(2, 16)
    c += T.bl(va + len(c), SETPARAM_FN)
    c += T.ldr_imm32(0, LA.SESSION + AUTOLAUNCH)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(0, 0)
    for off in (0, 4, 8, 12):
        c += T.str_sp(0, off)
    c += T.ldr_imm32(0, MSG_VT)
    c += T.str_sp(0, 0)
    c += T.lsls_imm(0, 5, 4)
    c += T.orrs_reg(0, 6)
    c += T.movs_imm8(1, 1)
    c += T.lsls_imm(1, 1, 8)
    c += T.orrs_reg(0, 1)                   # 0x100 | row<<4 | col
    c += T.mov_reg(1, 13)
    c += T.strh_imm(0, 1, 4)
    c += T.ldr_imm32(0, LA.SESSION)
    c += T.bl(va + len(c), SELECT)
    L["out"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c
