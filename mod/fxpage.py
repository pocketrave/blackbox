"""v060: FX send page (mode 0x30) redesign.

- The FX button opens the send page first (cycle 0x30 -> 0x37 -> 0x36 -> 0x30).
- Full-height send bars named by the effect, two send indicators per pad, BR/BL selection over pads and bars.
- INFO: a bar opens the stock effect settings (0x23); a pad opens the stock pad page, Conf tab (0x1C), whose Conf
  lists gain the rows fx1send / fx2send with the stock mod squares."""
import thumb as T

SETVIEW = 0x0809EAEC                   # SetView(S, mode, 0, 0)

# FX button cycle at 0x080A32A4: cmp #0x37 / cmp #0x30 / movs r1 (else) / movs r1 (first case); the 0x36 case stays.
CYCLE_SITES = ((0x080A32A4, bytes.fromhex("372b"), bytes.fromhex("302b")),   # cmp r3,#0x30 -> 0x37 case
               (0x080A32A8, bytes.fromhex("302b"), bytes.fromhex("372b")),   # cmp r3,#0x37 -> 0x36 case
               (0x080A32B0, bytes.fromhex("3721"), bytes.fromhex("3021")),   # else -> 0x30
               (0x080A32BC, bytes.fromhex("3021"), bytes.fromhex("3721")))   # cur 0x30 -> 0x37

# ---- layout (Task 3) -------------------------------------------------------------------------------------------
BAR_OFFS = (0x2254, 0x2300)            # level bars FX1 / FX2 (vt 0x080F16D8, SetRect vt+0x20)
FRAME_OFFS = (0x25B0, 0x2650)          # their frames (vt 0x080EFE48, SetRect vt+0x20)
BUTTON_OFFS = (0x1A34, 0x1BD4)         # FX 1 / FX 2 buttons
BAR_X = (1, 288)
BAR_Y, BAR_W, BAR_H = 1, 30, 219       # y-up rect: full view height
HIDE = 0x080B810C                      # (w, 1): hide a widget
DESELECT = 0x080ABE1C                  # (view): stock deselect of every tile, bars reset
CTOR_SITE, CTOR_ORIG = 0x080AC3A2, bytes.fromhex("fff73bfd")   # bl DESELECT at the ctor tail
TRI_SITES = (0x080ABBCE, 0x080ABBEA)   # bl to the tile triangle setters (send != 0 marks)
TRI_ORIG = (bytes.fromhex("f9f7c7f9"), bytes.fromhex("f9f7c3f9"))


def fxlay(va, L):
    """(r0 view): full-height bars and frames, hidden FX buttons. Called on show (slot13 0xD4) and by FXLAYC."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(16)                     # 16 pushed + 16: [sp] rect {x, y, w, h}
    c += T.mov_reg(4, 0)
    for offs in (BAR_OFFS, FRAME_OFFS):
        for off, x in zip(offs, BAR_X):
            for k, v in enumerate((x, BAR_Y, BAR_W, BAR_H)):
                c += T.movw(0, v)
                c += T.str_sp(0, 4 * k)
            c += T.movw(5, off)
            c += T.add_reg(5, 4)
            c += T.mov_reg(0, 5)
            c += T.add_rd_sp(1, 0)
            c += T.ldr_imm(3, 5, 0)
            c += T.ldr_imm(3, 3, 0x20)
            c += T.blx(3)
    for off in BUTTON_OFFS:
        c += T.movw(0, off)
        c += T.add_reg(0, 4)
        c += T.movs_imm8(1, 1)
        c += T.bl(va + len(c), HIDE)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def fxlay_ctor(va, L, fxlay_va):
    """bl from the ctor tail (r0 = r6 = view): FXLAY, then the displaced DESELECT(view)."""
    c = T.push_lo([4], lr=True)
    c += T.mov_reg(4, 0)
    c += T.bl(va + len(c), fxlay_va)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), DESELECT)
    c += T.pop_lo([4], pc=True)
    return c

# ---- selection (Task 4) ----------------------------------------------------------------------------------------
# sel byte at mod state +2192: 0x80 | (row * 6 + col); 0 = not set yet. row 0 = top screen row; col 0 = FX1 bar,
# 1..4 = pads, 5 = FX2 bar.
DESCP = 0x2401F4FC
SEL_OFF = 0x1A1 * 28 + 2192            # from [DESCP]
FROMFX_OFF = SEL_OFF + 1               # Task 6: the pad page was opened from the send page
SEL_SET = 0x80
TILE0_OFF, TILE_STRIDE, TILE_DIRTY = 0x34, 0x1A0, 0x17C   # 16 tiles in reading order (row stride 0x680 = 4 tiles)
TILE_SEL = 0x178                       # tile: stock blue highlight (drawn with colour 4)
BAR_DIRTY = 0x40
CUR_CODE, CUR_FLAG = 0x28D4, 0x28E0    # the stock selected pad (u16 code) and its valid flag
PADSEL = 0x080ABD20                    # (view, &{u32, u16 code}): stock pad select (bars, highlight)
STOCK13, STOCK12 = 0x080ABC44, 0x080ABE78
VT_SLOT13, VT_SLOT12 = 0x080F083C, 0x080F0838
VT13_ORIG, VT12_ORIG = 0x080ABC45, 0x080ABE79
ID_FX1, ID_FX2 = 0xD9, 0xDA
KNOB_BL, KNOB_BR = 1, 3
KNOB_STEP = 300                        # raw knob movement for one step (a detent is about 400, in about 4 messages)
ACC_OFF = SEL_OFF + 4                  # i32 sums of the raw BR / BL movement


def model_nav(sel, knob, delta):
    """Reference: the selection after one encoder message (knob index, signed delta)."""
    row, col = divmod(sel, 6)
    s = (delta > 0) - (delta < 0)
    if knob == KNOB_BR:
        col = min(5, max(0, col + s))
    elif knob == KNOB_BL and 1 <= col <= 4:
        row = min(3, max(0, row + s))
    return row * 6 + col


def pad_code(sel):
    row, col = divmod(sel, 6)
    return ((3 - row) << 4) | (col - 1) if 1 <= col <= 4 else None


def sel_of_code(code):
    return (3 - (code >> 4)) * 6 + (code & 0xF) + 1


def _sel_ptr(c, va, rd, L, none_label):
    """rd = &sel (mod state); branch to none_label when the descriptor array is not there yet."""
    c += T.ldr_imm32(rd, DESCP)
    c += T.ldr_imm(rd, rd, 0)
    c += T.cmp_imm(rd, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get(none_label, va))
    c += T.ldr_imm32(3, SEL_OFF)
    c += T.add_reg(rd, 3)
    return c


def fxmark(va, L):
    """(r0 view): repaint request for the 16 tiles and both bars (indicators, selection). While a bar is selected,
    no pad keeps the stock blue highlight (+0x178), so only one thing is blue."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.movs_imm8(4, 0)                    # 1 = a bar is selected
    c += T.ldr_imm32(3, DESCP)
    c += T.ldr_imm(3, 3, 0)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("go", va))
    c += T.ldr_imm32(2, SEL_OFF)
    c += T.add_reg(3, 2)
    c += T.ldrb_imm(3, 3, 0)
    c += T.cmp_imm(3, SEL_SET)
    c += T.b_cond(va + len(c), "cc", L.get("go", va))
    c += T.subs_imm8(3, SEL_SET)
    c += T.movs_imm8(2, 6)
    c += T.udiv(1, 3, 2)
    c += T.muls(1, 2)
    c += T.subs_reg(3, 3, 1)                  # col
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("bar", va))
    c += T.cmp_imm(3, 5)
    c += T.b_cond(va + len(c), "ne", L.get("go", va))
    L["bar"] = va + len(c)
    c += T.movs_imm8(4, 1)
    L["go"] = va + len(c)
    c += T.movs_imm8(2, 1)
    c += T.movs_imm8(5, 0)
    c += T.movw(1, TILE0_OFF + TILE_SEL)
    c += T.add_reg(1, 0)
    c += T.movs_imm8(3, 16)
    L["loop"] = va + len(c)
    c += T.strb_imm(2, 1, TILE_DIRTY - TILE_SEL)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("keep", va))
    c += T.strb_imm(5, 1, 0)
    L["keep"] = va + len(c)
    c += T.adds_imm8(1, 0xD0)                 # += 0x1A0 in two steps (imm8)
    c += T.adds_imm8(1, 0xD0)
    c += T.subs_imm8(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    for off in BAR_OFFS:
        c += T.movw(1, off + BAR_DIRTY)
        c += T.add_reg(1, 0)
        c += T.strb_w(2, 1, 0)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def fxapply(va, L, mark_va):
    """(r0 view): PADSEL for the selected pad (none for a bar), then FXMARK. sel must be set."""
    c = T.push_lo([4], lr=True)
    c += T.sub_sp_imm(8)                      # 8 + 8: [sp] = {u32 0, u16 code}
    c += T.mov_reg(4, 0)
    c = _sel_ptr(c, va, 0, L, "mark")
    c += T.ldrb_imm(0, 0, 0)
    c += T.movs_imm8(1, 0x7F)
    c += T.ands_reg(0, 1)                     # sel
    c += T.movs_imm8(1, 6)
    c += T.udiv(2, 0, 1)                      # row
    c += T.muls(1, 2)
    c += T.subs_reg(0, 0, 1)                  # col
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("mark", va))
    c += T.cmp_imm(0, 5)
    c += T.b_cond(va + len(c), "eq", L.get("mark", va))
    c += T.subs_imm(0, 0, 1)                  # pad column
    c += T.movs_imm8(1, 3)
    c += T.subs_reg(2, 1, 2)                  # code row = 3 - row
    c += T.lsls_imm(2, 2, 4)
    c += T.orrs_reg(0, 2)
    c += T.add_rd_sp(1, 0)
    c += T.strh_imm(0, 1, 4)
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 1, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), PADSEL)
    L["mark"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), mark_va)
    c += T.add_sp_imm(8)
    c += T.pop_lo([4], pc=True)
    return c


def _rc_to_sel(c, rd, row, col):
    """rd = 0x80 | (row * 6 + col); rd != row, col."""
    c += T.movs_imm8(rd, 6)
    c += T.muls(rd, row)
    c += T.adds_reg(rd, rd, col)
    c += T.adds_imm8(rd, SEL_SET)
    return c


def _code_to_rc(c, code, row, col):
    """row = 3 - (code >> 4), col = (code & 15) + 1; registers distinct, code kept."""
    c += T.lsrs_imm(col, code, 4)
    c += T.movs_imm8(row, 3)
    c += T.subs_reg(row, row, col)
    c += T.movs_imm8(col, 15)
    c += T.ands_reg(col, code)
    c += T.adds_imm8(col, 1)
    return c


def fxs13(va, L, mark_va, apply_va, lay_va):
    """vt slot13 (r0 view, r1 msg): BR/BL move the selection; 0x66/0x67 repaint; 0xD4 (show) re-layout + select."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(12)                     # 20 + 12 = 32
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.ldrh_imm(3, 5, 0)
    for t, lab in ((0x32, "knob"), (0x66, "redraw"), (0x67, "redraw"), (0xD4, "show")):
        c += T.cmp_imm(3, t)
        c += T.b_cond_w(va + len(c), "eq", L.get(lab, va))
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), STOCK13)
    c += T.bw(va + len(c), L.get("out", va))
    # 0x66 / 0x67: stock, then repaint (the send indicators read the cells)
    L["redraw"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), STOCK13)
    c += T.mov_reg(6, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), mark_va)
    c += T.mov_reg(0, 6)
    c += T.bw(va + len(c), L.get("out", va))
    # 0x32 encoder: BR (3) column, BL (1) row; TL / TR stock
    L["knob"] = va + len(c)
    c += T.ldrh_imm(3, 5, 0xC)
    c += T.cmp_imm(3, KNOB_BR)
    c += T.b_cond(va + len(c), "eq", L.get("go", va))
    c += T.cmp_imm(3, KNOB_BL)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    L["go"] = va + len(c)
    c += T.mov_reg(7, 3)                      # knob
    c += T.ldrh_imm(6, 5, 0x10)
    c += T.sxth(6, 6)                         # raw movement (s16)
    c = _sel_ptr(c, va, 0, L, "zero")
    c += T.movs_imm8(1, ACC_OFF - SEL_OFF)
    c += T.cmp_imm(7, KNOB_BR)
    c += T.b_cond(va + len(c), "eq", L.get("acc", va))
    c += T.movs_imm8(1, ACC_OFF - SEL_OFF + 4)
    L["acc"] = va + len(c)
    c += T.add_reg(1, 0)                      # &sum of this knob
    c += T.ldr_imm(2, 1, 0)
    c += T.cmp_imm(6, 0)                      # a movement against the sum's sign restarts the sum
    c += T.b_cond(va + len(c), "lt", L.get("dneg", va))
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ge", L.get("add", va))
    c += T.movs_imm8(2, 0)
    c += T.b_short(va + len(c), L.get("add", va))
    L["dneg"] = va + len(c)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "le", L.get("add", va))
    c += T.movs_imm8(2, 0)
    L["add"] = va + len(c)
    c += T.adds_reg(2, 2, 6)
    c += T.movw(3, KNOB_STEP)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "ge", L.get("pos", va))
    c += T.negs(3, 3)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "le", L.get("neg", va))
    c += T.str_imm(2, 1, 0)                   # less than one unit: keep the sum, no move
    c += T.b_short(va + len(c), L.get("zero", va))
    L["pos"] = va + len(c)
    c += T.movs_imm8(6, 0)                    # direction: 0 = forward
    c += T.b_short(va + len(c), L.get("moved", va))
    L["neg"] = va + len(c)
    c += T.movs_imm8(6, 1)                    # 1 = back
    L["moved"] = va + len(c)
    c += T.movs_imm8(2, 0)                    # the sum restarts after a step: no drift, no double step
    c += T.str_imm(2, 1, 0)
    c += T.ldrb_imm(1, 0, 0)
    c += T.cmp_imm(1, SEL_SET)
    c += T.b_cond(va + len(c), "cs", L.get("has", va))
    c += T.movs_imm8(1, SEL_SET | 1)          # not set yet: pad (row 0, col 1)
    L["has"] = va + len(c)
    c += T.subs_imm8(1, SEL_SET)
    c += T.movs_imm8(3, 6)
    c += T.udiv(2, 1, 3)                      # row
    c += T.muls(3, 2)
    c += T.subs_reg(3, 1, 3)                  # col
    c += T.cmp_imm(7, KNOB_BR)
    c += T.b_cond(va + len(c), "ne", L.get("bl", va))
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "ne", L.get("left", va))
    c += T.cmp_imm(3, 5)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.adds_imm8(3, 1)
    c += T.b_short(va + len(c), L.get("store", va))
    L["left"] = va + len(c)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.subs_imm8(3, 1)
    c += T.b_short(va + len(c), L.get("store", va))
    L["bl"] = va + len(c)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.cmp_imm(3, 5)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "ne", L.get("up", va))
    c += T.cmp_imm(2, 3)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.adds_imm8(2, 1)
    c += T.b_short(va + len(c), L.get("store", va))
    L["up"] = va + len(c)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("store", va))
    c += T.subs_imm8(2, 1)
    L["store"] = va + len(c)
    c = _rc_to_sel(c, 1, 2, 3)
    c += T.strb_imm(1, 0, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), apply_va)
    L["zero"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.bw(va + len(c), L.get("out", va))
    # 0xD4 show: stock, full-height layout, then the selection (first show: the stock pad, else the top-left pad)
    L["show"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), STOCK13)
    c += T.mov_reg(6, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), lay_va)
    c = _sel_ptr(c, va, 7, L, "showout")
    c += T.ldrb_imm(1, 7, 0)
    c += T.cmp_imm(1, SEL_SET)
    c += T.b_cond(va + len(c), "cs", L.get("apply", va))
    c += T.movs_imm8(1, SEL_SET | 1)
    c += T.movw(0, CUR_FLAG)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("st", va))
    c += T.movw(0, CUR_CODE)
    c += T.add_reg(0, 4)
    c += T.ldrh_imm(0, 0, 0)
    c = _code_to_rc(c, 0, 2, 3)
    c = _rc_to_sel(c, 1, 2, 3)
    L["st"] = va + len(c)
    c += T.strb_imm(1, 7, 0)
    L["apply"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), apply_va)
    L["showout"] = va + len(c)
    c += T.mov_reg(0, 6)
    L["out"] = va + len(c)
    c += T.add_sp_imm(12)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def fxs12(va, L, mark_va):
    """vt slot12 (r0 view, r1 notification): a tile tap selects the pad; a bar touch (0x6E from a level bar)
    selects the bar and is swallowed (no send change)."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(16)                     # 16 + 16 = 32
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.ldrh_imm(3, 5, 0)
    c += T.cmp_imm(3, 3)
    c += T.b_cond(va + len(c), "eq", L.get("tap", va))
    c += T.cmp_imm(3, 0x6E)
    c += T.b_cond(va + len(c), "eq", L.get("bar", va))
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), STOCK12)
    c += T.bw(va + len(c), L.get("out", va))
    L["tap"] = va + len(c)
    c += T.ldrh_imm(3, 5, 8)
    c += T.lsrs_imm(2, 3, 8)                  # FX button codes 0x300 / 0x310: stock only
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c = _sel_ptr(c, va, 6, L, "stock")
    c += T.ldrh_imm(3, 5, 8)
    c = _code_to_rc(c, 3, 2, 1)
    c = _rc_to_sel(c, 0, 2, 1)
    c += T.strb_imm(0, 6, 0)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), STOCK12)
    c += T.mov_reg(6, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), mark_va)
    c += T.mov_reg(0, 6)
    c += T.bw(va + len(c), L.get("out", va))
    L["bar"] = va + len(c)
    c += T.ldr_imm(3, 5, 0xC)
    c += T.movs_imm8(6, 0)
    c += T.cmp_imm(3, ID_FX1)
    c += T.b_cond(va + len(c), "eq", L.get("barsel", va))
    c += T.movs_imm8(6, 5)
    c += T.cmp_imm(3, ID_FX2)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    L["barsel"] = va + len(c)
    c = _sel_ptr(c, va, 1, L, "stock")
    c += T.ldrb_imm(2, 1, 0)
    c += T.cmp_imm(2, SEL_SET)
    c += T.b_cond(va + len(c), "cs", L.get("has", va))
    c += T.movs_imm8(2, SEL_SET)
    L["has"] = va + len(c)
    c += T.subs_imm8(2, SEL_SET)
    c += T.movs_imm8(3, 6)
    c += T.udiv(0, 2, 3)                      # row
    c += T.muls(0, 3)
    c += T.adds_reg(0, 0, 6)
    c += T.adds_imm8(0, SEL_SET)
    c += T.strb_imm(0, 1, 0)
    c += T.movs_imm8(0, 0x67)                 # the bar moved its own fill: refresh it from the selected pad
    c += T.str_sp(0, 0)
    c += T.mov_reg(0, 4)
    c += T.add_rd_sp(1, 0)
    c += T.bl(va + len(c), STOCK13)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), mark_va)
    c += T.movs_imm8(0, 0)
    L["out"] = va + len(c)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


# ---- overlay draw (Task 5) -------------------------------------------------------------------------------------
SESSION = 0x24020088
VT_SLOT1, VT1_ORIG = 0x080F080C, 0x080AEAF9
CONTAINER_DRAW = 0x080AEAF8            # (view, ctx): draws the children
GETCP = 0x08099504                     # (S, &{u32, u16 code}, id, int *out)
GETCN = 0x0809AD74                     # (S, &{u32, u16 code}, out >= 0x58 B): FX code 0x300|k<<4 -> short name
FILLRECT, RECTOUTL, TEXT1X = 0x0808EA22, 0x0808E994, 0x0808F23C
C_BG, C_SEND, C_SEL, C_SELBLUE = 1, 5, 15, 4    # C_SELBLUE: the stock selected-tile blue (0x080A443C)
FONT_CW = 0x240000D4                   # u16 char width of TEXT1X's font (font struct 0x240000D0)
BAR_FILL = 0x44                        # level bar: its orange fill rect {x, y, w, h}
SEL_MARGIN = 3                         # a selected bar: its fill is drawn this much narrower on each side
IND_XO, IND_W, IND_H = (2, 58), 3, 50  # indicator x offsets in the tile (FX1 left, FX2 right), width, inner height
LABEL_Y, LABEL_H = 4, 10                # bar labels: at the bottom of the bars
DR_RECT, DR_REF, DR_VAL, DR_NAME, DR_FRAME = 0, 16, 24, 32, 0x7C


def _dr_rect(c, x=None, y=None, w=None, h=None):
    """Store the given rect fields (None: already in r0 for that field is not supported; ints only)."""
    for off, v in ((0, x), (4, y), (8, w), (12, h)):
        if v is not None:
            c += T.movw(0, v)
            c += T.str_sp(0, DR_RECT + off)
    return c


def _dr_call(c, va, prim, colour):
    c += T.add_rd_sp(0, DR_RECT)
    c += T.movs_imm8(1, colour)
    c += T.mov_reg(2, 6)
    c += T.bl(va + len(c), prim)
    return c


def _ref(c, code_reg=None, code=None):
    """[sp+DR_REF] = {0, u16 code}; r1 = &ref."""
    c += T.movs_imm8(1, 0)
    c += T.str_sp(1, DR_REF)
    if code is not None:
        c += T.movw(0, code)
        code_reg = 0
    c += T.add_rd_sp(1, DR_REF)
    c += T.strh_imm(code_reg, 1, 4)
    return c


def fxdraw(va, L):
    """vt slot1 (r0 view, r1 ctx): stock container draw, then on ctx[0] (surface [ctx+4]): the send indicators of the
    16 pads (orange only, over the tile, the stock blue included), a selected bar in blue under its own orange
    fill, and the effect short names centred at the bottom of the bars."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(DR_FRAME)               # 20 + 0x7C = 144
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.bl(va + len(c), CONTAINER_DRAW)
    c += T.ldrb_imm(0, 5, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm(6, 5, 4)                   # surface
    # indicators: tile t in memory order (code row t >> 2, col t & 3)
    c += T.movs_imm8(7, 0)
    L["tile"] = va + len(c)
    for pid, xo in ((ID_FX1, IND_XO[0]), (ID_FX2, IND_XO[1])):
        n = "%X" % pid
        c += T.movs_imm8(0, 0)
        c += T.str_sp(0, DR_VAL)
        c += T.lsrs_imm(0, 7, 2)
        c += T.lsls_imm(0, 0, 4)
        c += T.movs_imm8(1, 3)
        c += T.ands_reg(1, 7)
        c += T.orrs_reg(0, 1)
        c = _ref(c, code_reg=0)
        c += T.ldr_imm32(0, SESSION)
        c += T.movs_imm8(2, pid)
        c += T.add_rd_sp(3, DR_VAL)
        c += T.bl(va + len(c), GETCP)
        c += T.ldr_sp(0, DR_VAL)
        c += T.cmp_imm(0, 0)
        c += T.b_cond_w(va + len(c), "le", L.get("skip" + n, va))
        c += T.movs_imm8(1, IND_H)
        c += T.muls(0, 1)
        c += T.movw(1, 1000)
        c += T.udiv(0, 0, 1)
        c += T.cmp_imm(0, IND_H)
        c += T.b_cond(va + len(c), "ls", L.get("hok" + n, va))
        c += T.movs_imm8(0, IND_H)
        L["hok" + n] = va + len(c)
        c += T.cmp_imm(0, 0)
        c += T.b_cond_w(va + len(c), "eq", L.get("skip" + n, va))
        c += T.str_sp(0, DR_RECT + 12)
        c += T.movs_imm8(0, 3)
        c += T.ands_reg(0, 7)
        c += T.lsls_imm(0, 0, 6)
        c += T.adds_imm8(0, 32 + xo)
        c += T.str_sp(0, DR_RECT)
        c += T.lsrs_imm(0, 7, 2)
        c += T.movs_imm8(1, 55)
        c += T.muls(0, 1)
        c += T.adds_imm8(0, 3)
        c += T.str_sp(0, DR_RECT + 4)
        c = _dr_rect(c, w=IND_W)
        c = _dr_call(c, va, FILLRECT, C_SEND)
        L["skip" + n] = va + len(c)
    c += T.adds_imm8(7, 1)
    c += T.cmp_imm(7, 16)
    c += T.b_cond_w(va + len(c), "ne", L.get("tile", va))
    # a selected bar: blue inside its orange frame, then its own fill again
    c = _sel_ptr(c, va, 0, L, "labels")
    c += T.ldrb_imm(1, 0, 0)
    c += T.cmp_imm(1, SEL_SET)
    c += T.b_cond_w(va + len(c), "cc", L.get("labels", va))
    c += T.subs_imm8(1, SEL_SET)
    c += T.movs_imm8(3, 6)
    c += T.udiv(2, 1, 3)
    c += T.muls(3, 2)
    c += T.subs_reg(3, 1, 3)                  # col
    c += T.movw(5, BAR_OFFS[0])
    c += T.movs_imm8(7, BAR_X[0])
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("bar", va))
    c += T.movw(5, BAR_OFFS[1])
    c += T.movw(7, BAR_X[1])
    c += T.cmp_imm(3, 5)
    c += T.b_cond_w(va + len(c), "ne", L.get("labels", va))
    L["bar"] = va + len(c)
    c += T.add_reg(5, 4)                      # the bar
    c += T.adds_imm(0, 7, 1)
    c += T.str_sp(0, DR_RECT)
    c = _dr_rect(c, y=BAR_Y + 1, w=BAR_W - 2, h=BAR_H - 2)
    c = _dr_call(c, va, FILLRECT, C_SELBLUE)
    c += T.ldr_imm(3, 5, BAR_FILL + 12)       # the bar's own fill, narrower: a blue margin stays at 100 %
    c += T.cmp_imm(3, 0)
    c += T.b_cond_w(va + len(c), "le", L.get("labels", va))
    c += T.str_sp(3, DR_RECT + 12)
    c += T.ldr_imm(3, 5, BAR_FILL + 4)
    c += T.str_sp(3, DR_RECT + 4)
    c += T.ldr_imm(3, 5, BAR_FILL)
    c += T.adds_imm8(3, SEL_MARGIN)
    c += T.str_sp(3, DR_RECT)
    c += T.ldr_imm(3, 5, BAR_FILL + 8)
    c += T.subs_imm8(3, 2 * SEL_MARGIN)
    c += T.cmp_imm(3, 0)
    c += T.b_cond_w(va + len(c), "le", L.get("labels", va))
    c += T.str_sp(3, DR_RECT + 8)
    c = _dr_call(c, va, FILLRECT, C_SEND)
    # bar labels: the effect's short name, centred, at the bottom
    L["labels"] = va + len(c)
    for k, x in enumerate(BAR_X):
        c = _ref(c, code=0x300 | k << 4)
        c += T.ldr_imm32(0, SESSION)
        c += T.add_rd_sp(2, DR_NAME)
        c += T.movs_imm8(3, 0)
        c += T.str_sp(3, DR_NAME)
        c += T.bl(va + len(c), GETCN)
        c += T.add_rd_sp(0, DR_NAME)          # w = strlen * char width
        c += T.movs_imm8(1, 0)
        L["len%d" % k] = va + len(c)
        c += T.ldrb_imm(2, 0, 0)
        c += T.cmp_imm(2, 0)
        c += T.b_cond(va + len(c), "eq", L.get("lend%d" % k, va))
        c += T.adds_imm8(0, 1)
        c += T.adds_imm8(1, 1)
        c += T.b_short(va + len(c), L.get("len%d" % k, va))
        L["lend%d" % k] = va + len(c)
        c += T.ldr_imm32(2, FONT_CW)
        c += T.ldrh_imm(2, 2, 0)
        c += T.muls(1, 2)
        c += T.movw(0, x)
        c += T.cmp_imm(1, BAR_W)
        c += T.b_cond(va + len(c), "ls", L.get("fit%d" % k, va))
        c += T.movs_imm8(1, BAR_W)
        L["fit%d" % k] = va + len(c)
        c += T.str_sp(1, DR_RECT + 8)
        c += T.movs_imm8(2, BAR_W)
        c += T.subs_reg(2, 2, 1)
        c += T.lsrs_imm(2, 2, 1)
        c += T.adds_reg(0, 0, 2)
        c += T.str_sp(0, DR_RECT)
        c = _dr_rect(c, y=LABEL_Y, h=LABEL_H)
        c += T.add_rd_sp(0, DR_NAME)
        c += T.add_rd_sp(1, DR_RECT)
        c += T.movs_imm8(2, C_SEL)
        c += T.mov_reg(3, 6)
        c += T.bl(va + len(c), TEXT1X)
    L["out"] = va + len(c)
    c += T.add_sp_imm(DR_FRAME)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


# ---- INFO / pad page / labels (Task 6) ---------------------------------------------------------------------------
# Conf lists (section 4 of the 9 pad layout records): append fx1send / fx2send at the 0 terminator.
CONF_ENDS = (0x080EF0A0, 0x080EF208, 0x080EF370, 0x080EF4DC, 0x080EF640, 0x080EF910, 0x080EFA78, 0x080EFBE2,
             0x080EFD4C)
CONF_ADD = bytes.fromhex("d900da00")
MODTAB_SITE, MODTAB_ORIG = 0x080F12EA, bytes.fromhex("32003300")   # mod-square ids 23/24 (duplicates of 12/11)
LBUF_OFF = 0x1F1 * 28                  # two 16-B label buffers in the free descriptor slot 0x1F1 (from [DESCP])
LBUF_LEN, NAME_MAX = 16, 7
DESC = 28
INFO_SITE, INFO_ORIG = 0x080A305E, bytes.fromhex("fbf745fd")      # bl SetView(S, 0x23) for modes 0x24 and 0x30
TABCHOOSE = 0x080991A8                 # (S, wanted tab mode, &{.., u16 code @+4}) -> the tab stock allows (else 0x18)
FXBTN = 0x0809D210                     # (S, &{u32, u16 0x300|k<<4}): [S+0x28] = FX slot (the FX 1/2 button tap)
MODE_OFF = 0x8CA4
PAD_OFF = 0x14                         # [S+0x14] u16: the pad the pad page edits
V_FXSET, V_CONF, V_SEND, V_MOD = 0x23, 0x1C, 0x30, 0x13
BACK_SITE, BACK_ORIG = 0x080A314E, bytes.fromhex("a38ac3f30312032a")  # ldrh r3,[r4,#0x14]; ubfx r2,r3,#4,#4; cmp r2,#3
BACK_RESUME, BACK_EXIT = 0x080A3156, 0x080A311A
SV_SITE, SV_ORIG = SETVIEW, bytes.fromhex("f0b5adf5617d")         # push {r4-r7,lr}; sub.w sp,sp,#0x384
SV_RESUME = SETVIEW + 6


def strings():
    """-> (blob, {name: offset}): the boot labels and the suffix."""
    blob, offs = b"", {}
    for k, s in (("fx1", b"FX1 Send:"), ("fx2", b"FX2 Send:"), ("amt", b" amount:")):
        offs[k] = len(blob)
        blob += s + b"\0"
    return blob, offs


def _copy(c, va, L, tag, dst, src, maxlen=None, cnt=None):
    """Copy the C string src -> dst (both advanced; dst ends at the NUL, which is written). r3 scratch;
    maxlen: at most that many chars (cnt = a free low register)."""
    if maxlen:
        c += T.movs_imm8(cnt, maxlen)
    L["c" + tag] = va + len(c)
    c += T.ldrb_imm(3, src, 0)
    c += T.strb_imm(3, dst, 0)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("e" + tag, va))
    c += T.adds_imm8(src, 1)
    c += T.adds_imm8(dst, 1)
    if maxlen:
        c += T.subs_imm8(cnt, 1)
        c += T.b_cond(va + len(c), "ne", L.get("c" + tag, va))
        c += T.movs_imm8(3, 0)
        c += T.strb_imm(3, dst, 0)
    else:
        c += T.b_short(va + len(c), L.get("c" + tag, va))
    L["e" + tag] = va + len(c)
    return c


def labinit(va, L, str_va, offs):
    """bl from the registrar epilogue: label buffers = "FX1 Send:" / "FX2 Send:", desc[0xD9/0xDA].label -> them.
    r0-r3 only."""
    c = T.push_lo([4], lr=True)
    c += T.ldr_imm32(2, DESCP)
    c += T.ldr_imm(2, 2, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    for k, pid in enumerate((ID_FX1, ID_FX2)):
        c += T.ldr_imm32(0, LBUF_OFF + LBUF_LEN * k)
        c += T.add_reg(0, 2)
        c += T.ldr_imm32(1, pid * DESC)
        c += T.add_reg(1, 2)
        c += T.str_imm(0, 1, 4)
        c += T.ldr_imm32(1, str_va + offs["fx%d" % (k + 1)])
        c = _copy(c, va, L, "b%d" % k, 0, 1)
    L["out"] = va + len(c)
    c += T.pop_lo([4], pc=True)
    return c


def fxinfo(va, L, str_va, offs):
    """bl at INFO_SITE (r0 = S, r1 = 0x23, r2 = r3 = 0). Mode 0x30 with a selection: a bar -> its FX settings page;
    a pad -> the stock pad page, Conf tab, with the send labels "<short> amount:". Else the stock SetView."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(0x6C)                   # 20 + 0x6C = 128: [sp] ref, [sp+8] name buffer (0x58 B)
    c += T.mov_reg(4, 0)
    c += T.movw(3, 0x8000)
    c += T.add_reg(3, 4)
    c += T.ldrb_w(3, 3, MODE_OFF - 0x8000)
    c += T.cmp_imm(3, V_SEND)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    c = _sel_ptr(c, va, 5, L, "stock")
    c += T.ldrb_imm(1, 5, 0)
    c += T.cmp_imm(1, SEL_SET)
    c += T.b_cond_w(va + len(c), "cc", L.get("stock", va))
    c += T.subs_imm8(1, SEL_SET)
    c += T.movs_imm8(3, 6)
    c += T.udiv(6, 1, 3)                      # row
    c += T.muls(3, 6)
    c += T.subs_reg(7, 1, 3)                  # col
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 0)
    c += T.movw(0, 0x300)
    c += T.cmp_imm(7, 0)
    c += T.b_cond(va + len(c), "eq", L.get("bar", va))
    c += T.movw(0, 0x310)
    c += T.cmp_imm(7, 5)
    c += T.b_cond(va + len(c), "ne", L.get("pad", va))
    L["bar"] = va + len(c)
    c += T.add_rd_sp(1, 0)
    c += T.strh_imm(0, 1, 4)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), FXBTN)
    c += T.movs_imm8(1, V_FXSET)
    c += T.b_short(va + len(c), L.get("view", va))
    L["pad"] = va + len(c)
    for k in range(2):                        # label k = "<short name of FX k+1> amount:"
        c += T.movs_imm8(0, 0)
        c += T.str_sp(0, 8)
        c += T.movw(0, 0x300 | k << 4)
        c += T.add_rd_sp(1, 0)
        c += T.strh_imm(0, 1, 4)
        c += T.mov_reg(0, 4)
        c += T.add_rd_sp(2, 8)
        c += T.bl(va + len(c), GETCN)
        c = _sel_ptr(c, va, 0, L, "stock")
        c += T.ldr_imm32(1, LBUF_OFF - SEL_OFF + LBUF_LEN * k)
        c += T.add_reg(0, 1)                  # dst
        c += T.add_rd_sp(1, 8)                # src
        c = _copy(c, va, L, "n%d" % k, 0, 1, maxlen=NAME_MAX, cnt=2)
        c += T.ldr_imm32(1, str_va + offs["amt"])
        c = _copy(c, va, L, "a%d" % k, 0, 1)
    c += T.movs_imm8(0, 3)                    # code = (3 - row) << 4 | (col - 1)
    c += T.subs_reg(0, 0, 6)
    c += T.lsls_imm(0, 0, 4)
    c += T.subs_imm8(7, 1)
    c += T.orrs_reg(0, 7)
    c += T.strh_imm(0, 4, PAD_OFF)
    c += T.movs_imm8(0, 1)
    c += T.strb_imm(0, 5, 1)                  # fromfx
    c += T.mov_reg(0, 4)                      # the stock tab chooser: Conf where the pad type has it, else Main
    c += T.movs_imm8(1, V_CONF)
    c += T.mov_reg(2, 4)
    c += T.adds_imm8(2, PAD_OFF - 4)
    c += T.bl(va + len(c), TABCHOOSE)
    c += T.mov_reg(1, 0)
    L["view"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(3, 0)
    c += T.bl(va + len(c), SETVIEW)
    c += T.b_short(va + len(c), L.get("out", va))
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.movs_imm8(1, V_FXSET)
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(3, 0)
    c += T.bl(va + len(c), SETVIEW)
    L["out"] = va + len(c)
    c += T.add_sp_imm(0x6C)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def fxback(va, L):
    """b.w at BACK_SITE (BACK on the pad tabs 0x18..0x1D, r4 = S): opened from the send page -> back to it."""
    c = _sel_ptr(b"", va, 0, L, "stock")
    c += T.ldrb_imm(1, 0, 1)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("stock", va))
    c += T.movs_imm8(1, 0)
    c += T.strb_imm(1, 0, 1)
    c += T.mov_reg(0, 4)
    c += T.movs_imm8(1, V_SEND)
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(3, 0)
    c += T.bl(va + len(c), SETVIEW)
    c += T.bw(va + len(c), BACK_EXIT)
    L["stock"] = va + len(c)
    c += BACK_ORIG
    c += T.bw(va + len(c), BACK_RESUME)
    return c


def svhook(va, L):
    """b.w at the SetView entry: a view other than the pad tabs / MOD page clears fromfx. Arguments kept."""
    c = T.push_lo([0, 1, 2, 3])
    c += T.cmp_imm(1, V_MOD)
    c += T.b_cond(va + len(c), "eq", L.get("keep", va))
    c += T.subs_imm8(1, 0x18)
    c += T.cmp_imm(1, 0x1D - 0x18)
    c += T.b_cond(va + len(c), "ls", L.get("keep", va))
    c = _sel_ptr(c, va, 0, L, "keep")
    c += T.movs_imm8(1, 0)
    c += T.strb_imm(1, 0, 1)
    L["keep"] = va + len(c)
    c += T.pop_lo([0, 1, 2, 3])
    c += SV_ORIG
    c += T.bw(va + len(c), SV_RESUME)
    return c


# ---- the pad page opened from the send page: two rows, no tabs (v062) -------------------------------------------
ROWS_SITE, ROWS_ORIG = 0x080B8956, bytes.fromhex("e0f7f3f9")      # bl BuildRows in the pad page refresh 0x080B892C
BUILDROWS = 0x08098D40                 # (S, &{.., u16 code @+4}, rows, tab) -> 1 / 0
ROWSCLEAR = 0x080A4FC2                 # (rows): count = 0
CELLOBJ = 0x08098D0C                   # (S, &code) -> the cell's param owner
GETPARAM = 0x08093E9C                  # (owner, id) -> value
ADDROW = 0x080A5038                    # (rows, id, value)
TABSEL = 0x080B8724                    # (page, k): show tab bar k of the 3, hide the others
TABS_SITES = (0x080B8844, 0x080B8BCC)  # its two callers (bl), both with r0 = the pad page
TABS_ORIG = (bytes.fromhex("fff76eff"), bytes.fromhex("fff7aafd"))
TABBAR_OFFS = (0xF6D0, 0xFA48, 0xFDC0) # the 3 tab bars of the pad page (vt+0x2C = hide(1) / show(0))


def _fromfx(c, va, L, none_label):
    """r0 = fromfx byte; branch to none_label when it is 0 or the descriptor array is not there. r3 scratch."""
    c = _sel_ptr(c, va, 0, L, none_label)
    c += T.ldrb_imm(0, 0, 1)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get(none_label, va))
    return c


def fxrows(va, L):
    """bl at ROWS_SITE (r0 S, r1 &code, r2 rows, r3 tab): opened from the send page -> the rows fx1send, fx2send
    only (any tab); else the stock BuildRows."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(12)                     # 20 + 12 = 32
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.mov_reg(6, 2)
    c += T.mov_reg(7, 3)
    c = _fromfx(c, va, L, "stock")
    c += T.mov_reg(0, 6)
    c += T.bl(va + len(c), ROWSCLEAR)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), CELLOBJ)
    c += T.mov_reg(5, 0)
    for pid in (ID_FX1, ID_FX2):
        c += T.mov_reg(0, 5)
        c += T.movs_imm8(1, pid)
        c += T.bl(va + len(c), GETPARAM)
        c += T.mov_reg(2, 0)
        c += T.movs_imm8(1, pid)
        c += T.mov_reg(0, 6)
        c += T.bl(va + len(c), ADDROW)
    c += T.movs_imm8(0, 1)
    c += T.b_short(va + len(c), L.get("out", va))
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(2, 6)
    c += T.mov_reg(3, 7)
    c += T.bl(va + len(c), BUILDROWS)
    L["out"] = va + len(c)
    c += T.add_sp_imm(12)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def fxtabs(va, L):
    """bl at TABS_SITES (r0 page, r1 k): the stock tab-bar choice, then, opened from the send page, all 3 bars hidden.
    The stock return value is kept."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.mov_reg(4, 0)
    c += T.bl(va + len(c), TABSEL)
    c += T.mov_reg(5, 0)
    c = _fromfx(c, va, L, "out")
    for off in TABBAR_OFFS:
        c += T.movw(0, off)
        c += T.add_reg(0, 4)
        c += T.ldr_imm(3, 0, 0)
        c += T.ldr_imm(3, 3, 0x2C)
        c += T.movs_imm8(1, 1)
        c += T.blx(3)
    L["out"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c
