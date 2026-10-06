#!/usr/bin/env python3
"""
Build ONE image containing every step. Each phaseN.py patched stock
independently, which meant the Step 3 gate shipped without the Step 1 parameter
it reads - GetParam returned 0 for the unregistered id, which indexes the
division table as "8 bars".

From now on this is the only script that produces a flashable image.

  Step 1  descriptor for `PrCh Quant` (id 0x1A0)      detour 0x0808E1CC
          add it to the global settings owner         detour 0x080949D6
          put it on the Tools -> Clock page           2-byte write 0x080EEDF8

  Step 2  record index on index-based loads           detour 0x0809E23A
          notes 109/110 -> mailbox (audio task)       detour 0x0805004C

  Step 3  gate + enqueue in the defaultTask loop      detour 0x08043E28

  Step 4  preset name in the header (not "Seq N")     detours 0x0809C0C0, 0x0809C0D0

  Step 6  boot into the SEQS view instead of PADS     2-byte write 0x080A2312

  Step 7  one enabled cell per column (SEQS touch)  detour 0x080A1A96
"""

import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbpatch import Patcher, PatchError, BASE
import thumb as T
import phase5 as P5
import phase6 as P6
import colx as CX
import seqscroll as SS
import infopage as IP
import gridsplit as GS
import cellbar as CB
import font16 as FN
import probe80 as PR
import launch as LA
import l3map as L3M
import paint as PT
import touch as TC
import menu as MN
import preview as PV
import migrate as MG
import midi as MI
import colparam as CP
import colmenu as CM
import colname as CN
import hdrsel as HS
import topbar as TBR
import trig as TR

LEGACY = os.environ.get("BB_LEGACY_CAVES") == "1"
BANK1_END = 0x08100000                     # v039 (hardware): an image past flash bank 1 fails "Unable to verify"
import splash as SPL
import sync as SY

STOCK = P5.STOCK
OUTDIR = P5.OUTDIR

# ---- Step 1 constants (verified in phase3.py) --------------------------------
NEW_ID = 0x01A0
ENUM_TABLE = 0x080EC74C
ENUM_COUNT = 9
DEFAULT_VALUE = 8                      # "None" - inert until the user sets it
LABEL = b"PrCh Quant:\x00"
TAG = b"prchquant\x00"
REGISTER_ENUM_PARAM = 0x0808C0D8
ADD_PARAM = 0x08093EF6
S1_DETOUR_DESC = 0x0808E1CC            # epilogue of the descriptor registrar
S1_DETOUR_OWNER = 0x080949D6           # tail of the global settings ctor
S1_OWNER_ORIG = bytes.fromhex("04f11000")   # add.w r0, r4, #0x10
CLOCK_FREE_SLOT = 0x080EEDF8

# ---- UI palette overrides -----------------------------------
# 34 ARGB8888 words at flash 0x080F1D80 (.data, copied to 0x24000000 and loaded
# into the DMA2D CLUT once at boot). Data-only patch: {index: (stock, new)}.
PALETTE = 0x080F1D80

# ---- Step 4 title label geometry -----------------------------------------------
# Status-bar widget ctor 0x080AB614. Title label = this+0x13C (text set at
# 0x080AB7E8). Rect is [+0x140 x, +0x144 y, +0x148 w, +0x14C h]; stock sets x AND
# w from one register (0x080AB73E movs r3,#0x8c), so a second value needs a cave.
# Label +0x51 = alignment (1 left, 2 centre, 3 right; all header labels use 1),
# +0x53 = text colour index. DrawText 0x0808EE54 draws from box x and clips to
# whole chars within box w (fixed-width font, char w = 2*[0x240000D4]).
# New: x = 10 (where the bars:beats counter began), w = 240 (up to the counter,
# which now sits at 250..320).
TITLE_SITE = 0x080AB73E                    # movs r3,#0x8c ; str.w r3,[r4,#0x140]
TITLE_BACK = 0x080AB750                    # after the four rect stores
TITLE_X, TITLE_W = 10, 210                 # v056: 240 -> 210, ends before the counter box (222)
COUNTER_ALIGN = 0x34 + 0x51                # v056: counter label (this+0x34) +0x51 alignment: 3 = right

# Progress bar (this+0x194, class ctor 0x080BE758) is never added to the bar, so
# it is never drawn. Its SetValue 0x080BE784 (called from the update fn
# 0x080AB802) only stores [+0x34] and a dirty flag [+0x32] - no parent/child
# walk - so an unlinked instance is harmless. r0 after the call is overwritten
# by `mov r0, r4` at 0x080AB77A.
# bars:beats counter (this+0x34) moves into its place: x 10 -> 250, w 100 -> 70.
STATUSBAR_PATCHES = [
    (0x080AB776, T.bl(0x080AB776, 0x080AEC44), bytes.fromhex("00bf00bf")),  # bl AddChild(pbar) -> nop nop
    (0x080AB6EA, bytes.fromhex("0a23"), bytes.fromhex("de23")),          # counter x = 222 (v056; v013: 250)
    (0x080AB6F2, bytes.fromhex("6423"), bytes.fromhex("6023")),          # counter w = 96 = 8 chars, right-aligned (v056; was 70)
]
# ---- Startup view: SEQS instead of PADS ----------------------------------------
# View mode byte = [0x24020088+0x8CA4]; SetView 0x0809EAEC(this, mode, 0, 0).
# The ctor 0x080973A8 sets mode 1 (boot; nav buttons are ignored while it is 1).
# The periodic update 0x080A2258 leaves mode 1 through exactly one call:
# SetView(this, 2) at 0x080A230E. Nav-button table 0x080A325C: PADS=2, SEQS=0x2C.
# Changing the immediate makes boot land where the SEQS button would.
STARTUP_VIEW_SITE = 0x080A2312
STARTUP_VIEW_ORIG = bytes.fromhex("0221")      # movs r1, #2    (PADS)
STARTUP_VIEW_NEW = bytes.fromhex("2c21")       # movs r1, #0x2c (SEQS)

import palettes as PL                  # colour scheme (v010+: colour-blind safe; v002-v009 had only 7 = #005E3A)
with open(STOCK, "rb") as _f:
    _stock = _f.read()
PALETTE_OVERRIDES = {}
for _i, _rgb in sorted(PL.ACTIVE.items()):
    _old = struct.unpack_from("<I", _stock, PALETTE - BASE + 4 * _i)[0]
    if (0xFF000000 | _rgb) != _old:
        PALETTE_OVERRIDES[_i] = (_old, 0xFF000000 | _rgb)


def build():
    p = Patcher(STOCK)

    # verify every site before writing anything
    desc_orig = bytes(p.data[S1_DETOUR_DESC - BASE:S1_DETOUR_DESC - BASE + 6])
    if desc_orig[:2] != b"\x05\xb0":
        raise PatchError("S1 desc detour: expected 'add sp,#0x14', got %s" % desc_orig.hex(" "))
    p.expect(S1_DETOUR_OWNER, S1_OWNER_ORIG)
    p.expect(P5.HOOK_A, P5.HOOK_A_ORIG)
    p.expect(P5.HOOK_B, P5.HOOK_B_ORIG)
    hc_orig = bytes(p.data[P5.HOOK_C - BASE:P5.HOOK_C - BASE + 4])
    if hc_orig != T.bl(P5.HOOK_C, P5.HOOK_C_TARGET):
        raise PatchError("hook C site changed")
    p.expect(CLOCK_FREE_SLOT, b"\x00\x00")
    p.expect(CLOCK_FREE_SLOT + 2, b"\x00\x00")
    for site, orig, _ in P6.SITES:
        p.expect(site, orig)
    p.expect(0x0809C0D6, P6.ADD_R0_R5_8)
    p.expect(P6.TCOL_SITE, P6.TCOL_ORIG)
    title_orig = bytes(p.data[TITLE_SITE - BASE:TITLE_BACK - BASE])
    if title_orig[:2] != bytes.fromhex("8c23"):
        raise PatchError("title rect site changed: %s" % title_orig.hex(" "))
    ST_X, ST_Y, ST_W, ST_H = (title_orig[i:i + 4] for i in (2, 6, 10, 14))   # the four str.w
    for va, orig, _ in STATUSBAR_PATCHES:
        p.expect(va, orig)
    p.expect(STARTUP_VIEW_SITE, STARTUP_VIEW_ORIG)
    p.expect(CX.SITE, CX.SITE_ORIG)
    for s_, o_ in ((SS.H3_SITE, SS.H3_ORIG), (SS.H4_SITE, SS.H4_ORIG), (SS.H5_SITE, SS.H5_ORIG)):
        p.expect(s_, o_)
    p.expect(IP.ROWGET_SITE, IP.ROWGET_ORIG)
    p.expect(SS.KNOB_SITE, SS.KNOB_ORIG)
    p.expect(CB.W1_SITE, CB.W1_ORIG)
    p.expect(FN.G1_SITE, FN.ENTRY_ORIG)
    p.expect(FN.G2_SITE, FN.ENTRY_ORIG)
    p.expect(CB.W2_SITE, CB.W2_ORIG)
    for s_, _ in CB.RO_SITES:
        if bytes(p.data[s_ - BASE:s_ - BASE + 4]) != T.bl(s_, CB.RECTOUTL):
            raise PatchError("cellbar RO site %08X is not bl RectOutl" % s_)
    GRID = GS.patches(p.data, BASE)
    for va_, o_, _n in GRID:
        p.expect(va_, bytes([1, o_[1]]))
    p.expect(IP.D1_SITE, IP.D_ORIG)
    for site, orig in IP.SCP_SITES:
        p.expect(site, orig)
    p.expect(IP.D2_SITE, IP.D_ORIG)
    p.expect(IP.SH_SITE, IP.SH_ORIG)
    p.expect(IP.NB_SITE, IP.NB_ORIG)
    p.expect(SS.H6_SITE, SS.H6_ORIG)
    for s_ in (SS.H7A_SITE, SS.H7B_SITE, SS.H7C_SITE):
        p.expect(s_, SS.MLA_ORIG)
    p.expect(SS.H1_SITE, SS.H1_ORIG)
    p.expect(PT.VT1_SITE, PT.VT1_ORIG)
    p.expect(TC.VT_PRESS_SITE, TC.VT_PRESS_ORIG)
    p.expect(TC.VT_REL_SITE, TC.VT_REL_ORIG)
    p.expect(TC.ENC_SITE, TC.ENC_ORIG)
    p.expect(SY.SP_SITE, SY.SP_ORIG)
    p.expect(SY.ECHO_SITE, SY.ECHO_ORIG)
    p.expect(SY.ADD_SITE, SY.ADD_ORIG)
    p.expect(SY.CLR_SITE, SY.CLR_ORIG)
    p.expect(SY.POS_SITE, SY.POS_ORIG)
    p.expect(SY.STATE_SITE, SY.STATE_ORIG)
    p.expect(SY.POS2_SITE, SY.POS2_ORIG)
    p.expect(SY.PP_SITE, SY.PP_ORIG)
    p.expect(SPL.POOL_VER, struct.pack("<I", SPL.ORIG_VER))
    p.expect(SS.H2_SITE, SS.H2_ORIG)
    p.expect(TR.SETSTEP, TR.SETSTEP_ORIG)                                       # v053
    p.expect(TR.GATE, TR.GATE_ORIG)
    p.expect(TR.REG_COUNT_SITE, TR.REG_COUNT_ORIG)
    p.expect(TR.LOAD_SITE, TR.LOAD_ORIG)
    p.expect(TR.EDIT_SITE, TR.EDIT_ORIG)
    p.expect(TR.TABLE_POOL, struct.pack("<I", TR.TABLE_STOCK))
    p.expect(TR.DISP_SITE, TR.DISP_ORIG)
    p.expect(TR.NOFF_SITE, TR.NOFF_ORIG)
    for s_ in TR.TXT_SITES + (TR.CTOR_TXT_SITE,):
        if bytes(p.data[s_ - BASE:s_ - BASE + 4]) != T.bl(s_, TBR.SETTEXT):
            raise PatchError("letter SetText site %08X changed" % s_)
    p.expect(TR.LETTER_REL_SITE, TR.LETTER_REL_ORIG)
    p.expect(TR.MD1_SITE, TR.MD1_ORIG)
    p.expect(TR.MD2_SITE, TR.MD2_ORIG)
    p.expect(CN.INFO_SITE, CN.INFO_ORIG)                                        # v056
    for s_, o_ in ((TR.NCA_SITE, TR.NCA_ORIG), (TR.NCB_SITE, TR.NCB_ORIG), (TR.NCC_SITE, TR.NCC_ORIG)):
        p.expect(s_, o_)
    p.expect(SS.POOL_SITE, SS.POOL_ORIG)
    p.expect(SS.L_SITE, SS.L_ORIG)
    for s_, o_ in ((SS.RF_TOP_SITE, SS.RF_TOP_ORIG), (SS.RF_RESET_SITE, SS.RF_RESET_ORIG),
                   (SS.T0R_SITE, SS.T0R_ORIG), (SS.T0G_SITE, SS.T0G_ORIG)):
        p.expect(s_, o_)

    # ---- appended data ------------------------------------------------------
    label_va = p.append(LABEL, align=4)
    tag_va = p.append(TAG, align=4)
    table_va = p.append(b"".join(struct.pack("<I", t) for t in P5.QUANT_TICKS), align=4)
    fmt_va = p.append(P6.FMT, align=4)

    def emit(fn):
        va = BASE + len(p.data) + ((4 - len(p.data) % 4) % 4)
        got = p.append(P5._asm(va, fn), align=4)
        assert got == va, "cave alignment drift"
        return va

    # v040: superseded caves (replaced by newer versions, unreachable) are no longer emitted: v039 grew past the end of
    # flash bank 1 (0x08100000) and the bootloader refused it ("Unable to verify"). BB_LEGACY_CAVES=1 emits them.
    def emit_legacy(fn):
        return emit(fn) if LEGACY else 0

    # ---- Step 1 cave: register the descriptor, then the displaced epilogue ---
    def s1_desc(va, L):
        c = b""
        c += T.ldr_imm32(3, tag_va)
        c += T.str_sp(3, 4)
        c += T.movs_imm8(3, ENUM_COUNT)
        c += T.str_sp(3, 0)
        c += T.ldr_imm32(3, ENUM_TABLE)
        c += T.ldr_imm32(2, label_va)
        c += T.movw(1, NEW_ID)
        c += T.mov_reg(0, 8)
        c += T.bl(va + len(c), REGISTER_ENUM_PARAM)
        c += desc_orig                       # add sp,#0x14 ; pop.w {...,pc}
        return c

    # ---- Step 1 cave: AddParam, then the displaced instruction --------------
    def s1_owner(va, L):
        c = b""
        c += T.movs_imm8(2, DEFAULT_VALUE)
        c += T.movw(1, NEW_ID)
        c += T.mov_reg(0, 4)
        c += T.bl(va + len(c), ADD_PARAM)
        c += S1_OWNER_ORIG
        c += T.bw(va + len(c), S1_DETOUR_OWNER + 4)
        return c

    va_desc = emit(s1_desc)
    va_owner = emit(s1_owner)
    va_a = emit(P5.cave_a)
    va_b = emit(P5.cave_b)
    va_c = emit(lambda v, L: P5.cave_c(v, L, table_va))
    va_name = emit(P6.name_of)

    def title_rect(va, L):
        c = b""
        c += T.movs_imm8(3, TITLE_X)
        c += ST_X                            # str.w r3, [r4, #0x140]
        c += ST_Y                            # str.w r6, [r4, #0x144]  (y, stock)
        c += T.movs_imm8(3, TITLE_W)
        c += ST_W                            # str.w r3, [r4, #0x148]
        c += ST_H                            # str.w r5, [r4, #0x14c]  (h, stock)
        c += T.movs_imm8(3, 3)
        c += T.strb_w(3, 4, COUNTER_ALIGN)   # v056: the counter grows to the left as digits are added
        c += T.bw(va + len(c), TITLE_BACK)
        return c
    va_title = emit(title_rect)
    va_tcol = emit(P6.cave_tcol)
    va_h = [emit(lambda v, L, f=f: P6.cave_h(v, L, fmt_va, f, va_name)) for _, _, f in P6.SITES]
    va_x = emit(CX.cave)
    va_actv = emit(SS.actv)
    va_h3 = emit(SS.h3)
    va_h4 = emit(SS.h4)
    va_h5 = emit(lambda v, L: SS.h5(v, L, va_actv))
    va_h6 = emit(lambda v, L: SS.h6(v, L, va_actv))
    va_h7a = emit(lambda v, L: SS.h7a(v, L, va_actv))
    va_h7b = emit(SS.h7b)
    va_h7c = emit(lambda v, L: SS.h7c(v, L, va_actv))
    va_scroll = emit(SS.h2)
    va_l = emit(SS.lskip)
    va_t0r = emit(SS.t0r)
    va_t0g = emit(lambda v, L: SS.t0g(v, L, va_actv))
    va_rd2 = emit(lambda v, L: IP.rd2(v, L, IP.CLIP_IDS, clamp_stepmode=True, name_id=CN.NAME_ID))   # v041/2/6
    va_sh = emit(IP.sh)
    va_nb = emit(IP.nb)
    va_knob = emit(SS.knob)
    va_w1 = emit(CB.w1)
    va_w2 = emit(CB.w2)
    va_ro = emit(CB.ro)
    rect_stock_va = p.append(struct.pack("<iiii", *IP.RECT_STOCK), align=4)
    rect_seq_va = p.append(struct.pack("<iiii", *IP.RECT_SEQ), align=4)
    va_sh2 = emit(lambda v, L: IP.sh2(v, L, rect_stock_va, rect_seq_va))
    font16_va = p.append(FN.table(), align=4)
    va_g1 = emit(lambda v, L: FN.g1(v, L, font16_va))
    va_g2 = emit(lambda v, L: FN.g2(v, L, font16_va))
    label0_va = p.append(SS.LABEL0, align=4)       # after every cave: earlier caves keep their VAs
    # v022 probe (80 clips): new caves after everything; old caves B and C stay and are chained
    va_b2 = emit(lambda v, L: PR.b2(v, L, va_b))
    va_probe = emit(PR.probe)
    va_c2 = emit(lambda v, L: PR.c2(v, L, va_c, va_probe))
    # v024 L3 step 1: launch helper; v023 probe caves stay, unused (no MIDI test triggers)
    l3map_va = p.append(L3M.table(), align=4)
    l3hosts_va = p.append(L3M.hosts(), align=4)
    va_launch = emit_legacy(lambda v, L: LA.launch(v, L, l3map_va, l3hosts_va))
    va_c3 = emit_legacy(lambda v, L: LA.c3(v, L, va_c, va_launch))
    # v026 L3 grid display
    l3inv_va = p.append(L3M.inv_table(), align=4)
    l3eng_va = p.append(L3M.eng_offsets(), align=4)
    digits_va = p.append(PT.DIGITS, align=4)
    va_colstate = emit(lambda v, L: PT.colstate(v, L, l3hosts_va, l3inv_va, l3eng_va))
    va_paint = emit_legacy(lambda v, L: PT.paint(v, L, va_colstate, l3map_va, digits_va))
    # v028 L3 touch + selection + TL/TR
    l3desc_va = p.append(L3M.descs(), align=4)
    va_tpress = emit(TC.tpress)
    va_trel = emit_legacy(lambda v, L: TC.trel(v, L, l3desc_va))
    va_enc = emit_legacy(TC.enc)
    # v030: repaint on change + white launch marker + TL/TR inverted. New DIRTY/RTICK; LAUNCH, C3,
    # PAINT, TREL, ENC re-emitted after them (the earlier copies stay in the image, unused)
    va_dirty = emit(TC.dirty)
    va_rtick = emit(TC.rtick)
    va_launch2 = emit_legacy(lambda v, L: LA.launch(v, L, l3map_va, l3hosts_va, va_dirty))
    va_c3b = emit_legacy(lambda v, L: LA.c3(v, L, va_c, va_launch2))
    va_paint2 = emit_legacy(lambda v, L: PT.paint(v, L, va_colstate, l3map_va, digits_va, va_rtick))
    va_trel2 = emit_legacy(lambda v, L: TC.trel(v, L, l3desc_va, va_dirty, l3map_va))
    va_enc2 = emit_legacy(lambda v, L: TC.enc(v, L, va_dirty))
    # v032 splash text: an appended version string (the shared stock version string stays); v051: no "by" string
    splash_ver_va = p.append(SPL.ver_string(), align=4)
    # v033 INFO -> selected clip + edit sync; LAUNCH reserves slot 0; TREL/ENC call SELCLIP
    inv80_va = p.append(L3M.inv80(), align=4)
    va_findp = emit(SY.findp)
    va_stream = emit(lambda v, L: SY.stream(v, L, duty_from_clip=True))   # v041: Duty per clip
    va_echo = emit(SY.echo)
    va_spstock = emit(SY.stock_sp)
    va_sync = emit(lambda v, L: SY.sync(v, L, va_spstock, va_stream, va_findp, inv80_va, l3map_va, l3hosts_va,
                                        per_clip=True))                       # v042
    va_selclip = emit(lambda v, L: TC.selclip(v, L, l3map_va, guard=True))          # v047: ignores a header
    va_launch3 = emit_legacy(lambda v, L: LA.launch(v, L, l3map_va, l3hosts_va, va_dirty, reserve0=True))
    va_c3c = emit_legacy(lambda v, L: LA.c3(v, L, va_c, va_launch3))
    va_trel3 = emit_legacy(lambda v, L: TC.trel(v, L, l3desc_va, va_dirty, l3map_va, selclip_va=va_selclip))
    va_enc3 = emit_legacy(lambda v, L: TC.enc(v, L, va_dirty, selclip_va=va_selclip))
    va_addtr = emit(SY.tramp_add)
    va_clrtr = emit(SY.tramp_clr)
    va_addw = emit(lambda v, L: SY.evwrap(v, L, True, va_addtr, inv80_va, l3hosts_va))
    va_clrw = emit(lambda v, L: SY.evwrap(v, L, False, va_clrtr, inv80_va, l3hosts_va))
    va_posw = emit(lambda v, L: SY.posw(v, L, va_colstate, l3hosts_va))           # v034 playhead
    va_statetr = emit(SY.tramp_state)
    va_statew = emit(lambda v, L: SY.statew(v, L, va_colstate, va_statetr))       # v034 playhead 2
    va_pos2w = emit(lambda v, L: SY.pos2w(v, L, va_colstate, l3hosts_va))         # v034 playhead step
    va_pptr = emit(SY.tramp_pp)
    va_restream = emit(lambda v, L: SY.restream(v, L, va_stream, inv80_va, l3map_va, l3hosts_va))   # v036
    va_paramw = emit_legacy(lambda v, L: SY.paramwrap(v, L, va_pptr, inv80_va, l3hosts_va, va_restream))   # v035/v036
    va_launch4 = emit_legacy(lambda v, L: LA.launch(v, L, l3map_va, l3hosts_va, va_dirty, reserve0=True, count_filter=True))
    va_c3d = emit_legacy(lambda v, L: LA.c3(v, L, va_c, va_launch4))                     # v036 count filter
    # v037 per-clip Quant Size: LAUNCH posts the clip cell's Quant to the host; PARAMW routes Quant edits
    qtable_va = p.append(L3M.qtable(), align=4)
    va_paramw2 = emit(lambda v, L: SY.paramwrap(v, L, va_pptr, inv80_va, l3hosts_va, va_restream, quant=True,
                                                      duty_per_clip=True, quant_clip_inv80=inv80_va))
    va_launch5 = emit(lambda v, L: LA.launch(v, L, l3map_va, l3hosts_va, va_dirty, reserve0=True, count_filter=True,
                                             qtable_va=qtable_va, duty_from_clip=True, quant_per_clip=True))
    va_c3e = emit_legacy(lambda v, L: LA.c3(v, L, va_c, va_launch5))
    # v038 long-press clip menu: CLEAR / UNDO
    menu_str_va = p.append(MN.STRINGS, align=4)
    va_mpos = emit(MN.menupos)
    va_mdraw = emit(lambda v, L: MN.menudraw(v, L, va_mpos, menu_str_va))
    va_mclear = emit(lambda v, L: MN.clipclear(v, L, l3map_va, va_restream))
    va_mtap = emit(lambda v, L: MN.menutap(v, L, va_mpos, va_mclear))
    va_paint3 = emit_legacy(lambda v, L: PT.paint(v, L, va_colstate, l3map_va, digits_va, va_rtick, menudraw_va=va_mdraw))
    va_trel4 = emit_legacy(lambda v, L: TC.trel(v, L, l3desc_va, va_dirty, l3map_va, selclip_va=va_selclip,
                                         menutap_va=va_mtap))
    # v039 mini note preview on every clip tile (stock builder, cached per tile, static)
    va_migr = emit(MG.migr)                                                      # v041: old presets
    va_pvinv = emit(PV.pvinv)                                                    # v042: no conversion here
    va_uplw = emit(lambda v, L: MG.uplw(v, L, va_migr))                           # v042: convert before uploads
    # v043 MIDI notes 111-118 = a tap on column 1-8 in the selected row
    va_midib = emit(lambda v, L: MI.midib(v, L, va_b, fill_lo=TR.FILL_LO))      # v055 fill notes 119-126
    va_tap = emit(lambda v, L: MI.tap(v, L, l3map_va, va_colstate, va_selclip, va_dirty))
    va_mcons = emit(lambda v, L: MI.mcons(v, L, va_tap, lastrow=True))            # v047: header -> last clip row
    va_fsync = emit(lambda v, L: TR.fillsync(v, L, va_mcons, va_dirty))          # v053: fill masks, BACK release
    va_c3m = emit_legacy(lambda v, L: MI.c3m(v, L, va_c, va_mcons, va_launch5))
    va_pvbuild = emit(lambda v, L: PV.pvbuild(v, L, l3map_va, qtable_va))
    va_pvtile = emit(lambda v, L: PV.pvtile(v, L, va_pvbuild))
    va_cpw = emit(lambda v, L: CP.cpw(v, L, l3hosts_va))                           # v044: instrument edits -> host
    # v045 column settings page (header long press)
    col_lists_va = p.append(CM.COL_LISTS, align=4)
    va_rowsel = emit(lambda v, L: CM.rowsel(v, L, col_lists_va))
    va_pisel = emit(lambda v, L: CM.pisel(v, L, col_lists_va))
    name_label_va = p.append(CN.LABEL, align=4)                                   # v046 Name row
    va_namefill = emit(CN.namefill)
    va_nameprep = emit(lambda v, L: CN.nameprep(v, L, va_namefill, name_label_va))
    va_editw = emit(lambda v, L: CN.editw(v, L, name_label_va + 5))
    va_nameret = emit(lambda v, L: CN.nameret(v, L, va_sh2, va_namefill))
    va_colopen = emit(lambda v, L: CM.colopen(v, L, l3desc_va, va_nameprep))
    va_colret = emit(lambda v, L: CM.colret(v, L, va_selclip, clear_kbd=True))
    va_c3n = emit(lambda v, L: CM.c3n(v, L, va_c, va_colret, va_fsync, va_launch5))   # v053: FILLSYNC, then MCONS
    va_trel5 = emit_legacy(lambda v, L: TC.trel(v, L, l3desc_va, va_dirty, l3map_va, selclip_va=va_selclip,
                                         menutap_va=va_mtap, colopen_va=va_colopen))
    # v047 selectable header row
    va_hsel = emit(HS.hsel)
    va_hdrcol = emit(HS.hdrcol)
    va_infow = emit(lambda v, L: HS.infow(v, L, va_colopen))
    va_enc4 = emit(lambda v, L: TC.enc(v, L, va_dirty, selclip_va=va_selclip, header=True))
    va_trel6 = emit(lambda v, L: TC.trel(v, L, l3desc_va, va_dirty, l3map_va, selclip_va=va_selclip,
                                         menutap_va=va_mtap, colopen_va=va_colopen, hsel_va=va_hsel,
                                         hstop=True))   # v056: header tap stops the column again
    # v049 settings-page 1-8 selector, piano roll without the mini grid / letter
    nums_va = p.append(TBR.NUMS, align=4)
    va_topbar = emit(lambda v, L: TBR.topbar(v, L, nums_va))
    va_tbact = emit(lambda v, L: TBR.tbact(v, L, va_colopen, va_selclip))
    va_tbtap = emit(lambda v, L: TBR.tbtap(v, L, va_tbact))
    va_rolldraw = emit(lambda v, L: TBR.rolldraw(v, L, fill=True))                 # v053 one-row toolbar + FILL
    va_rowmk = emit(PT.rowmark)                                                   # v043: MIDI row corners
    va_filltile = emit(lambda v, L: TR.filltile(v, L, l3map_va))                   # v055 fill tile rule
    va_paint4 = emit(lambda v, L: PT.paint(v, L, va_colstate, l3map_va, digits_va, va_rtick, menudraw_va=va_mdraw,
                                           pvtile_va=va_pvtile, rowmark_va=va_rowmk, hdrcol_va=va_hdrcol,
                                           filltile_va=va_filltile))
    # ---- v053: trig conditions
    ab_va = p.append(TR.ab_table(), align=4)
    va_cnt = emit(TR.cnt)
    va_cond = emit(lambda v, L: TR.cond(v, L, ab_va))
    lab_vas = [p.append(s_.encode() + b"\0", align=2) for s_ in TR.LABELS]
    _pct, _pct_offs = TR.pct_strings()                                             # v057: own 1%..99% texts
    pct_va = p.append(_pct, align=4)
    evtab_va = p.append(TR.ui_table(_stock, lab_vas, {n: pct_va + o for n, o in _pct_offs.items()}), align=4)
    va_cntset = emit(TR.cntset)
    va_s2u = emit(TR.s2u)
    va_u2s = emit(TR.u2s)
    va_bkd = emit(TR.bkd)
    va_noff = emit(TR.noff)
    fill_str_va = p.append(TR.FILL_STR, align=4)
    va_filltxt = emit(lambda v, L: TR.filltxt(v, L, fill_str_va))
    va_fillctor = emit(lambda v, L: TR.fillctor(v, L, fill_str_va))
    va_toggle = emit(TR.toggle)
    va_md1 = emit(TR.md1)                                                          # v054 multi-note PLAY edit
    va_md2 = emit(TR.md2)
    va_nca = emit(lambda v, L: TR.nc_cache(v, L, 7))                              # v055 note colour
    va_ncb = emit(lambda v, L: TR.nc_cache(v, L, 6))
    va_ncc = emit(TR.nc_colour)
    va_infn = emit(CN.infn)                                                        # v056 INFO on the Name row

    # ---- install ------------------------------------------------------------
    p.write_bytes(S1_DETOUR_DESC, T.bw(S1_DETOUR_DESC, va_desc) + T.nop(), expected=desc_orig)
    p.write_bytes(S1_DETOUR_OWNER, T.bw(S1_DETOUR_OWNER, va_owner), expected=S1_OWNER_ORIG)
    p.write_bytes(P5.HOOK_A, T.bw(P5.HOOK_A, va_a), expected=P5.HOOK_A_ORIG)
    p.write_bytes(P5.HOOK_B, T.bw(P5.HOOK_B, va_midib), expected=P5.HOOK_B_ORIG)        # v024: back to cave B
    p.write_bytes(P5.HOOK_C, T.bl(P5.HOOK_C, va_c3n), expected=hc_orig)       # v030: C3B
    p.write_bytes(CLOCK_FREE_SLOT, struct.pack("<H", NEW_ID), expected=b"\x00\x00")
    for (site, orig, _), va in zip(P6.SITES, va_h):
        p.write_bytes(site, T.bw(site, va), expected=orig)
    p.write_bytes(TITLE_SITE, T.bw(TITLE_SITE, va_title), expected=title_orig[:4])
    p.write_bytes(P6.TCOL_SITE, T.bw(P6.TCOL_SITE, va_tcol) + T.nop(), expected=P6.TCOL_ORIG)
    for va, orig, new in STATUSBAR_PATCHES:
        p.write_bytes(va, new, expected=orig)
    p.write_bytes(STARTUP_VIEW_SITE, STARTUP_VIEW_NEW, expected=STARTUP_VIEW_ORIG)
    p.write_bytes(CX.SITE, T.bw(CX.SITE, va_x) + T.nop(), expected=CX.SITE_ORIG)
    p.write_bytes(SS.H3_SITE, T.bw(SS.H3_SITE, va_h3), expected=SS.H3_ORIG)
    p.write_bytes(SS.H4_SITE, T.bw(SS.H4_SITE, va_h4), expected=SS.H4_ORIG)
    p.write_bytes(SS.H5_SITE, T.bw(SS.H5_SITE, va_h5) + T.nop() + T.nop(), expected=SS.H5_ORIG)
    p.write_bytes(SS.H6_SITE, T.bw(SS.H6_SITE, va_h6) + T.nop() * 5, expected=SS.H6_ORIG)
    for s_, v_ in ((SS.H7A_SITE, va_h7a), (SS.H7B_SITE, va_h7b), (SS.H7C_SITE, va_h7c)):
        p.write_bytes(s_, T.bw(s_, v_), expected=SS.MLA_ORIG)
    p.write_bytes(SS.H1_SITE, PT.H1_L3, expected=SS.H1_ORIG)                       # v026: top 0..5
    p.write_bytes(PT.VT1_SITE, struct.pack("<I", va_paint4 | 1), expected=PT.VT1_ORIG)
    p.write_bytes(CP.CPW_SITE, T.bl(CP.CPW_SITE, va_cpw), expected=T.bl(CP.CPW_SITE, CP.SCP))   # v044
    p.write_bytes(MG.UPL_SITE, T.bw(MG.UPL_SITE, va_uplw), expected=MG.UPL_ORIG)    # v042: convert before uploads
    for site in PV.UPD_SITES:                                                    # v039 preview invalidation
        p.write_bytes(site, T.bl(site, va_pvinv), expected=T.bl(site, PV.UPD))  # v026: PAINT
    p.write_bytes(TC.VT_PRESS_SITE, struct.pack("<I", va_tpress | 1), expected=TC.VT_PRESS_ORIG)  # v028
    p.write_bytes(TC.VT_REL_SITE, struct.pack("<I", va_trel6 | 1), expected=TC.VT_REL_ORIG)        # v028
    p.write_bytes(TC.ENC_SITE, T.bw(TC.ENC_SITE, va_enc4), expected=TC.ENC_ORIG)
    p.write_bytes(TBR.LOAD_SITE, T.bl(TBR.LOAD_SITE, va_topbar), expected=T.bl(TBR.LOAD_SITE, TBR.LOAD))   # v049
    p.write_bytes(TBR.TAP_SITE, T.bw(TBR.TAP_SITE, va_tbtap), expected=TBR.TAP_ORIG)                        # v049
    p.write_bytes(TBR.ROLL_VT1, struct.pack("<I", va_rolldraw | 1), expected=struct.pack("<I", TBR.ROLL_VT1_ORIG))  # v049
    for site in HS.INFO_SITES:                                                   # v047: INFO on a header
        p.write_bytes(site, T.bl(site, va_infow), expected=T.bl(site, CM.SETVIEW))
    p.write_bytes(SY.SP_SITE, T.bw(SY.SP_SITE, va_sync), expected=SY.SP_ORIG)        # v033 SYNC
    p.write_bytes(SY.ECHO_SITE, T.bw(SY.ECHO_SITE, va_echo), expected=SY.ECHO_ORIG)  # v033 ECHO
    p.write_bytes(SY.ADD_SITE, T.bw(SY.ADD_SITE, va_addw), expected=SY.ADD_ORIG)     # v033 ADDW
    p.write_bytes(SY.CLR_SITE, T.bw(SY.CLR_SITE, va_clrw), expected=SY.CLR_ORIG)     # v033 CLRW
    p.write_bytes(SY.POS_SITE, T.bw(SY.POS_SITE, va_posw), expected=SY.POS_ORIG)     # v034 POSW
    p.write_bytes(SY.STATE_SITE, T.bw(SY.STATE_SITE, va_statew), expected=SY.STATE_ORIG)  # v034 STATEW
    p.write_bytes(SY.POS2_SITE, T.bw(SY.POS2_SITE, va_pos2w), expected=SY.POS2_ORIG)     # v034 POS2W
    p.write_bytes(SY.PP_SITE, T.bw(SY.PP_SITE, va_paramw2), expected=SY.PP_ORIG)          # v035 PARAMW
    p.write_bytes(SPL.POOL_VER, struct.pack("<I", splash_ver_va), expected=struct.pack("<I", SPL.ORIG_VER))  # v032                 # v028 TL/TR
    p.write_bytes(SS.H2_SITE, T.bw(SS.H2_SITE, va_scroll), expected=SS.H2_ORIG)
    p.write_bytes(SS.POOL_SITE, struct.pack("<I", label0_va), expected=SS.POOL_ORIG)
    p.write_bytes(SS.L_SITE, T.bw(SS.L_SITE, va_l), expected=SS.L_ORIG)
    p.write_bytes(SS.RF_TOP_SITE, SS.RF_TOP_NEW, expected=SS.RF_TOP_ORIG)
    p.write_bytes(SS.RF_RESET_SITE, SS.RF_RESET_NEW, expected=SS.RF_RESET_ORIG)
    p.write_bytes(SS.T0R_SITE, T.bw(SS.T0R_SITE, va_t0r) + T.nop() * 2, expected=SS.T0R_ORIG)
    p.write_bytes(SS.T0G_SITE, T.bw(SS.T0G_SITE, va_t0g) + T.nop(), expected=SS.T0G_ORIG)
    p.write_bytes(IP.ROWGET_SITE, T.bl(IP.ROWGET_SITE, va_rd2), expected=IP.ROWGET_ORIG)
    for site, orig, new in CM.CLIP_SITES:                                        # v045: clip rows only
        p.write_bytes(site, new, expected=orig)
    p.write_bytes(CN.EDIT_SITE, T.bw(CN.EDIT_SITE, va_editw), expected=CN.EDIT_ORIG)   # v046 Name edit
    p.write_bytes(CM.ROWSEL_SITE, T.bw(CM.ROWSEL_SITE, va_rowsel), expected=CM.SEL_ORIG)   # v045
    p.write_bytes(CM.PISEL_SITE, T.bw(CM.PISEL_SITE, va_pisel), expected=CM.SEL_ORIG)     # v045
    for site, orig in IP.SCP_SITES:                                              # v041: Duty/Quant per clip
        p.write_bytes(site, T.bw(site, IP.SCP_ACTIVE), expected=orig)
    p.write_bytes(IP.SH_SITE, T.bw(IP.SH_SITE, va_nameret), expected=IP.SH_ORIG)   # v046: NAMERET -> SH2   # v016: SH2 (SH unused)
    p.write_bytes(IP.NB_SITE, T.bw(IP.NB_SITE, va_nb), expected=IP.NB_ORIG)
    # v048: BR scroll reversed back -- the v011 KNOB negation is no longer installed (stock direction)
    p.write_bytes(CB.W1_SITE, T.bw(CB.W1_SITE, va_w1), expected=CB.W1_ORIG)
    p.write_bytes(FN.G1_SITE, T.bw(FN.G1_SITE, va_g1), expected=FN.ENTRY_ORIG)
    p.write_bytes(FN.G2_SITE, T.bw(FN.G2_SITE, va_g2), expected=FN.ENTRY_ORIG)
    p.write_bytes(CB.W2_SITE, T.bw(CB.W2_SITE, va_w2) + T.nop(), expected=CB.W2_ORIG)
    for s_, _ in CB.RO_SITES:
        p.write_bytes(s_, T.bl(s_, va_ro), expected=T.bl(s_, CB.RECTOUTL))
    for va_, o_, n_ in GRID:
        p.write_bytes(va_, n_, expected=o_)
    for i, (stock, new) in sorted(PALETTE_OVERRIDES.items()):
        assert 0 <= i < 34
        p.write_bytes(PALETTE + 4 * i, struct.pack("<I", new), expected=struct.pack("<I", stock))

    p.write_bytes(TR.SETSTEP, T.bw(TR.SETSTEP, va_cnt), expected=TR.SETSTEP_ORIG)          # v053 loop count
    p.write_bytes(TR.GATE, T.bw(TR.GATE, va_cond) + T.nop(), expected=TR.GATE_ORIG)       # v053 condition gate
    p.write_bytes(TR.TABLE_POOL, struct.pack("<I", evtab_va), expected=struct.pack("<I", TR.TABLE_STOCK))   # v053 list
    p.write_bytes(TR.REG_COUNT_SITE, T.bl(TR.REG_COUNT_SITE, va_cntset), expected=TR.REG_COUNT_ORIG)
    p.write_bytes(TR.LOAD_SITE, T.bw(TR.LOAD_SITE, va_s2u) + T.nop(), expected=TR.LOAD_ORIG)
    p.write_bytes(TR.EDIT_SITE, T.bw(TR.EDIT_SITE, va_u2s), expected=TR.EDIT_ORIG)
    p.write_bytes(TR.DISP_SITE, T.bw(TR.DISP_SITE, va_bkd) + T.nop(), expected=TR.DISP_ORIG)   # v053 BACK = fill
    p.write_bytes(TR.NOFF_SITE, T.bw(TR.NOFF_SITE, va_noff), expected=TR.NOFF_ORIG)           # v053 note 119 off
    for s_ in TR.TXT_SITES:                                                      # v053 letter -> FILL
        p.write_bytes(s_, T.bl(s_, va_filltxt), expected=T.bl(s_, TBR.SETTEXT))
    p.write_bytes(TR.CTOR_TXT_SITE, T.bl(TR.CTOR_TXT_SITE, va_fillctor), expected=T.bl(TR.CTOR_TXT_SITE, TBR.SETTEXT))
    p.write_bytes(TR.LETTER_REL_SITE, T.b_cond_w(TR.LETTER_REL_SITE, "eq", va_toggle), expected=TR.LETTER_REL_ORIG)
    p.write_bytes(TR.MD1_SITE, T.bw(TR.MD1_SITE, va_md1), expected=TR.MD1_ORIG)          # v054
    p.write_bytes(TR.MD2_SITE, T.bw(TR.MD2_SITE, va_md2), expected=TR.MD2_ORIG)
    for s_, o_, v_ in ((TR.NCA_SITE, TR.NCA_ORIG, va_nca), (TR.NCB_SITE, TR.NCB_ORIG, va_ncb), (TR.NCC_SITE, TR.NCC_ORIG, va_ncc)):
        p.write_bytes(s_, T.bl(s_, v_), expected=o_)                                # v055 note colour
    p.write_bytes(CN.INFO_SITE, T.bw(CN.INFO_SITE, va_infn) + T.nop() * 2, expected=CN.INFO_ORIG)   # v056
    p.verify_safety()
    out = os.path.join(OUTDIR, "BLACKBOX_all.bin")
    p.save(out)
    size = os.path.getsize(out)
    assert size <= BANK1_END - BASE, ("image is %d B, ends at 0x%08X: past flash bank 1 (0x%08X); the bootloader "
                                      "refuses it (v039)" % (size, BASE + size, BANK1_END))
    return p, out, dict(desc=va_desc, owner=va_owner, A=va_a, B=va_b, C=va_c, N=va_name, T=va_title, TC=va_tcol, H1=va_h[0], H2=va_h[1], X=va_x, ACTV=va_actv, H3=va_h3, H4=va_h4, H5=va_h5, H6=va_h6, H7A=va_h7a, H7B=va_h7b, H7C=va_h7c, SCROLL=va_scroll, LSKIP=va_l, T0R=va_t0r, T0G=va_t0g, RD2=va_rd2, SH=va_sh, NB=va_nb, KNOB=va_knob, W1=va_w1, W2=va_w2, RO=va_ro, SH2=va_sh2, G1=va_g1, G2=va_g2, B2=va_b2, PROBE=va_probe, C2=va_c2, LAUNCH=va_launch5, C3=va_c3n, C3_OLD=va_c3e, C3M=va_c3m, COLOPEN=va_colopen, NAMEPREP=va_nameprep, NAMEFILL=va_namefill, EDITW=va_editw, NAMERET=va_nameret, COLRET=va_colret, ROWSEL=va_rowsel, PISEL=va_pisel, MIDIB=va_midib, ROWMK=va_rowmk, CPW=va_cpw, MCONS=va_mcons, TAP=va_tap, QTABLE=qtable_va, L3MAP=l3map_va, L3HOSTS=l3hosts_va, COLSTATE=va_colstate, PAINT=va_paint4, PVINV=va_pvinv, MIGR=va_migr, UPLW=va_uplw, PVBUILD=va_pvbuild, PVTILE=va_pvtile, TPRESS=va_tpress, TREL=va_trel6, TREL5=va_trel5, HSEL=va_hsel, TOPBAR=va_topbar, TBACT=va_tbact, TBTAP=va_tbtap, ROLLDRAW=va_rolldraw, HDRCOL=va_hdrcol, INFOW=va_infow, TREL4=va_trel4, MPOS=va_mpos, MDRAW=va_mdraw, MCLEAR=va_mclear, MTAP=va_mtap, ENC=va_enc4, FINDP=va_findp, STREAM=va_stream, ECHO=va_echo, SPSTOCK=va_spstock, SYNC=va_sync, SELCLIP=va_selclip, ADDTR=va_addtr, CLRTR=va_clrtr, ADDW=va_addw, CLRW=va_clrw, POSW=va_posw, STATEW=va_statew, POS2W=va_pos2w, PPTR=va_pptr, PARAMW=va_paramw2, RESTREAM=va_restream, DIRTY=va_dirty, RTICK=va_rtick, CNT=va_cnt, COND=va_cond, ABTAB=ab_va, CNTSET=va_cntset, S2U=va_s2u, U2S=va_u2s, EVTAB=evtab_va, BKD=va_bkd, FSYNC=va_fsync, NOFF=va_noff, TOGGLE=va_toggle, FILLTXT=va_filltxt, FILLCTOR=va_fillctor, MD1=va_md1, MD2=va_md2, FILLTILE=va_filltile, NCA=va_nca, NCB=va_ncb, NCC=va_ncc, INFN=va_infn, table=table_va)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    T.selftest(verbose=False)
    try:
        p, out, vas = build()
    except (PatchError, AssertionError) as e:
        print("FAILED: %s" % e)
        return 1
    print(p.report())
    print("\n  caves: " + ", ".join("%s@%08X" % (k, v) for k, v in vas.items()))
    dst = os.path.join(OUTDIR, "test_all")
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(out, os.path.join(dst, "BLACKBOX.BIN"))
    print("\n  ready to copy: %s%sBLACKBOX.BIN" % (dst, os.sep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
