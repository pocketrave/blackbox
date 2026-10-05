"""v045 L3 column settings page.

Lists: the stock Seq page lists (0x080EEF28 normal / 0x080EEEE0 MIDI-seq) are rewritten to the CLIP rows
{0x49 Duty, 0x46 Quant, 0x85 Step Len, 0x86 Step Count}; RD2 still recognises them by address (list + 0x7E).
While mod state +106 (colpage = k + 1) is set, ROWSEL (row builder, 0x08098F96) and PISEL (GetPageInfo, 0x0809983A)
pick the COLUMN lists {0x88 Step Mode, 0x6B MIDI Out} / MIDI mode {0x88, 0x7A MIDI channel} instead.
COLOPEN(k) (TREL, header long press): colpage = k + 1, [S+0x1C] = H(k)'s desc, SetView(S, 0x1E, 0, 0) = the stock
param page modal for the host cell; its edits go through SetCellParam to the host's sub-0 record and player.
COLRET (defaultTask, C3): once the UI is back in SEQS ([S+0x8CA4] == 0x2C) clear colpage and run SELCLIP, so the
selected clip is the edited cell again (INFO opens it)."""
import struct

import thumb as T
import phase5 as P5
import launch as LA

COLPAGE_OFF = 106
MODE_OFF, MODE_SEQS = 0x8CA4, 0x2C          # session: current UI mode (0x2C = SEQS)
SETVIEW = 0x0809EAEC                        # SetView(S, mode, 0, 0)
SEL_DESC = 0x1C                             # session: u16 selected sequence desc
LIST_SEQ, LIST_MIDI = 0x080EEF28, 0x080EEEE0
CLIP_SITES = ((LIST_SEQ + 4, bytes.fromhex("88006b00"), bytes.fromhex("85008600")),
              (LIST_MIDI + 4, bytes.fromhex("88007a00"), bytes.fromhex("85008600")))
NAME_ID = 0x19F                             # v046: the Name row (colname.py)
COL_LISTS = struct.pack("<4H", 0x88, 0x6B, NAME_ID, 0) + struct.pack("<4H", 0x88, 0x7A, NAME_ID, 0)   # normal +0, MIDI +8
ROWSEL_SITE, ROWSEL_BACK = 0x08098F96, 0x08098F4C   # cmp r0,#2; beq -> ldr r7, list; b 0x08098F4C
PISEL_SITE, PISEL_BACK = 0x0809983A, 0x0809980E     # cmp r0,#2; beq -> ldr r6, list; b 0x0809980E
SEL_ORIG = bytes.fromhex("022801d0")


def _sel(va, L, rd, back, lists_va):
    """r0 = 0xB7 of the page's cell. rd = the list register the stock code uses. Clobbers r0-r3."""
    c = T.mov_reg(3, 0)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("stock", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + COLPAGE_OFF)
    c += T.add_reg(0, 1)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("stock", va))
    c += T.ldr_imm32(rd, lists_va)
    c += T.cmp_imm(3, 2)
    c += T.b_cond(va + len(c), "ne", L.get("go", va))
    c += T.ldr_imm32(rd, lists_va + 8)
    c += T.b_short(va + len(c), L.get("go", va))
    L["stock"] = va + len(c)
    c += T.ldr_imm32(rd, LIST_SEQ)
    c += T.cmp_imm(3, 2)
    c += T.b_cond(va + len(c), "ne", L.get("go", va))
    c += T.ldr_imm32(rd, LIST_MIDI)
    L["go"] = va + len(c)
    c += T.bw(va + len(c), back)
    return c


def rowsel(va, L, lists_va):
    return _sel(va, L, 7, ROWSEL_BACK, lists_va)


def pisel(va, L, lists_va):
    return _sel(va, L, 6, PISEL_BACK, lists_va)


def colopen(va, L, descs_va, nameprep_va=None):
    """(r0 k)."""
    c = T.push_lo([4], lr=True)
    c += T.mov_reg(4, 0)
    if nameprep_va is not None:              # v046: the Name row's descriptor, table and text
        c += T.bl(va + len(c), nameprep_va)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + COLPAGE_OFF)
    c += T.add_reg(0, 1)
    c += T.adds_imm(1, 4, 1)
    c += T.strb_imm(1, 0, 0)                 # colpage = k + 1
    c += T.lsls_imm(0, 4, 1)
    c += T.ldr_imm32(1, descs_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)                 # desc of H(k)
    c += T.ldr_imm32(1, LA.SESSION + SEL_DESC)
    c += T.strh_imm(0, 1, 0)
    c += T.movs_imm8(3, 0)
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(1, 0x1E)
    c += T.ldr_imm32(0, LA.SESSION)
    c += T.bl(va + len(c), SETVIEW)
    L["out"] = va + len(c)
    c += T.pop_lo([4], pc=True)
    return c


def colret(va, L, selclip_va, clear_kbd=False):
    c = T.push_lo([4], lr=True)
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + COLPAGE_OFF)
    c += T.add_reg(4, 0)
    c += T.ldrb_imm(0, 4, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.SESSION + MODE_OFF)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, MODE_SEQS)
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 4, 0)
    if clear_kbd:                            # v046: SEQ pressed while the keyboard was open
        c += T.strb_imm(0, 4, 1)
    c += T.bl(va + len(c), selclip_va)
    L["out"] = va + len(c)
    c += T.pop_lo([4], pc=True)
    return c


def c3n(va, L, va_c, va_colret, va_mcons, va_launch):
    """HOOK_C: stock call + cave C, then COLRET, MCONS, LAUNCH."""
    c = T.push_lo([4], lr=True)
    c += T.bl(va + len(c), va_c)
    c += T.push_lo([0, 1, 2, 3])
    c += T.bl(va + len(c), va_colret)
    c += T.bl(va + len(c), va_mcons)
    c += T.bl(va + len(c), va_launch)
    c += T.pop_lo([0, 1, 2, 3])
    c += T.pop_lo([4], pc=True)
    return c
