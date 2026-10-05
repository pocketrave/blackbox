"""v049: the settings pages' top row becomes a 1-8 selector; the piano roll hides the sequence
miniature and the pattern letter; the pressed-button colour (palette 31) becomes sky blue (palettes.py).

TOPBAR replaces `bl Load` in the param page's show (0x080A78CA). Before Load it takes the toolbar's 2 stock buttons
out of the tab toolbar (page+0xB5F0) and gives it back its stock rect (pad pages lay their tabs out in it). After
Load, on a sequence page (the mod's column page and clip page), the tab toolbar becomes the top row (0,182,320,38)
with 8 equal buttons "1".."8" (ids 0x12F+j; the page's 6 tab buttons + the toolbar's 2), the current one selected
(fill 5, as the piano roll's selected buttons), and the old top row (mini 4x4 grid + 3 empty boxes) is hidden.
Current = colpage - 1 on the column page, else the selected L3 column.
TBTAP (0x080A7472, the page handler's first type test): a press/release of ids 0x12F..0x136 on a sequence page is
taken: on release TBACT(j) switches the column page to column j (COLOPEN) or the clip page to column j's clip in the
same row (selection, SELCLIP, SetView 0x1E); the previous mode is kept so BACK still goes back.
ROLLDRAW (piano roll view vt 0x080F1658 slot 1, generic container draw) hides the view's mini 4x4 grid (+0xB95C) and
pattern-letter button (+0xBAC4, id 0xE7) before every draw; the KEYS-mode pad miniature is another widget."""
import thumb as T
import phase5 as P5
import launch as LA
import touch as TC
import colmenu as CM

LOAD_SITE, LOAD = 0x080A78CA, 0x080A7330
TAP_SITE, TAP_ORIG, TAP_BACK, TAP_EXIT = 0x080A7472, bytes.fromhex("0b883d2b"), 0x080A7476, 0x080A7514
ROLL_VT1, ROLL_VT1_ORIG = 0x080F1658 + 4, 0x080AEAF9
CONTAINER_DRAW = 0x080AEAF8
REMOVE, ADDBTN, SETTEXT, SETSEL, SELFILL, HIDE = 0x080AEC62, 0x080C4ED8, 0x080A3DEC, 0x080A3E00, 0x080A3EA6, 0x080B810C
TB, TB_STOCK, PG_BTNS, BTN_STRIDE, TOOL, PAGE_DESC = 0xB5F0, 0xB62C, 0xB968, 0xA0, 0x3C, 0x38
ID0 = 0x12F
C_CUR = 5                                   # selected fill = the piano roll's selected-button look
MINI_OFF, LETTER_OFF = 0xB95C, 0xBAC4       # piano roll view: mini grid (vt 0x080F106C), letter button (id 0xE7)
MINI_VT, BTN_VT, LETTER_ID = 0x080F106C, 0x080EFE48, 0xE7
PREV_MODE = 0x8CA5
NUMS = b"".join(bytes([0x31 + j, 0]) for j in range(8))


def _is_seq_page(c, va, L, page_reg, no_label):
    c += T.ldrh_imm(0, page_reg, PAGE_DESC)
    c += T.lsrs_imm(0, 0, 8)
    c += T.movs_imm8(1, 0x1F)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get(no_label, va))
    return c


def topbar(va, L, nums_va):
    """bl replacement for Load(page r0, tab r1); returns Load's r0."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(12)                    # 32: [sp] Load's r0, [sp+4] button
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.ldr_imm32(6, TB)
    c += T.add_reg(6, 4)                     # r6 = tab toolbar
    for off in (TB_STOCK, TB_STOCK + BTN_STRIDE):
        c += T.mov_reg(0, 6)
        c += T.ldr_imm32(1, off)
        c += T.add_reg(1, 4)
        c += T.bl(va + len(c), REMOVE)
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 6, 4)
    c += T.str_imm(0, 6, 8)
    c += T.movw(0, 320)
    c += T.str_imm(0, 6, 12)
    c += T.movs_imm8(0, 38)
    c += T.str_imm(0, 6, 16)                 # stock rect (0,0,320,38): pad pages lay their tabs out in it
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), LOAD)
    c += T.str_sp(0, 0)
    c = _is_seq_page(c, va, L, 4, "out")
    c += T.ldr_imm32(7, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(7, 7, 0)
    c += T.cmp_imm(7, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + TC.SEL_OFF)
    c += T.add_reg(7, 0)                     # r7 = &sel
    c += T.ldrb_imm(0, 7, CM.COLPAGE_OFF - TC.SEL_OFF)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("clip", va))
    c += T.subs_imm8(0, 1)
    c += T.mov_reg(7, 0)
    c += T.b_short(va + len(c), L.get("cur", va))
    L["clip"] = va + len(c)
    c += T.ldrb_imm(7, 7, 0)                 # the selected L3 column
    L["cur"] = va + len(c)                   # r7 = current column
    c += T.movs_imm8(0, 0)
    c += T.strh_imm(0, 6, 0x34)              # no buttons yet
    c += T.movs_imm8(0, 8)
    c += T.strh_imm(0, 6, 0x36)              # 8 equal slots
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 6, 4)
    c += T.movs_imm8(0, 182)
    c += T.str_imm(0, 6, 8)                  # the top row (y-up)
    c += T.movs_imm8(5, 7)                   # j = 7 .. 0 (AddButton lays out right to left)
    L["loop"] = va + len(c)
    c += T.cmp_imm(5, 6)
    c += T.b_cond(va + len(c), "cs", L.get("hi", va))
    c += T.movs_imm8(0, BTN_STRIDE)
    c += T.muls(0, 5)
    c += T.ldr_imm32(1, PG_BTNS)
    c += T.b_short(va + len(c), L.get("got", va))
    L["hi"] = va + len(c)
    c += T.subs_imm(0, 5, 6)
    c += T.movs_imm8(1, BTN_STRIDE)
    c += T.muls(0, 1)
    c += T.ldr_imm32(1, TB_STOCK)
    L["got"] = va + len(c)
    c += T.adds_reg(0, 0, 1)
    c += T.adds_reg(0, 0, 4)                 # the button
    c += T.str_sp(0, 4)
    c += T.movw(1, ID0)
    c += T.adds_reg(1, 1, 5)
    c += T.str_imm(1, 0, 0x14)               # id 0x12F + j
    c += T.ldr_imm32(1, nums_va)
    c += T.lsls_imm(2, 5, 1)
    c += T.adds_reg(1, 1, 2)
    c += T.bl(va + len(c), SETTEXT)          # "1" + j
    c += T.ldr_sp(0, 4)
    c += T.movs_imm8(1, C_CUR)
    c += T.bl(va + len(c), SELFILL)
    c += T.ldr_sp(0, 4)
    c += T.movs_imm8(1, 0)
    c += T.cmp_reg(5, 7)
    c += T.b_cond(va + len(c), "ne", L.get("sel", va))
    c += T.movs_imm8(1, 1)
    L["sel"] = va + len(c)
    c += T.bl(va + len(c), SETSEL)
    c += T.mov_reg(0, 6)
    c += T.ldr_sp(1, 4)
    c += T.bl(va + len(c), ADDBTN)
    c += T.subs_imm8(5, 1)
    c += T.b_cond(va + len(c), "ge", L.get("loop", va))
    c += T.mov_reg(0, 6)
    c += T.movs_imm8(1, 0)
    c += T.bl(va + len(c), HIDE)             # show the selector
    c += T.mov_reg(0, 4)
    c += T.adds_imm8(0, TOOL)
    c += T.movs_imm8(1, 1)
    c += T.bl(va + len(c), HIDE)             # hide the old top row (mini grid + 3 empty boxes)
    L["out"] = va + len(c)
    c += T.ldr_sp(0, 0)
    c += T.add_sp_imm(12)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def tbact(va, L, colopen_va, selclip_va):
    """(r0 j): switch the column page to column j, or the clip page to column j's clip in the same row."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.mov_reg(4, 0)
    c += T.ldr_imm32(5, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(5, 5, 0)
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + TC.SEL_OFF)
    c += T.add_reg(5, 0)                     # r5 = &sel
    c += T.ldr_imm32(0, LA.SESSION + PREV_MODE)
    c += T.ldrb_imm(6, 0, 0)                 # keep the BACK target
    c += T.ldrb_imm(0, 5, CM.COLPAGE_OFF - TC.SEL_OFF)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("clip", va))
    c += T.adds_imm(1, 4, 1)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("restore", va))
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), colopen_va)
    c += T.b_short(va + len(c), L.get("restore", va))
    L["clip"] = va + len(c)
    c += T.ldrb_imm(0, 5, 0)
    c += T.cmp_reg(0, 4)
    c += T.b_cond(va + len(c), "eq", L.get("restore", va))
    c += T.strb_imm(4, 5, 0)                 # the selection moves to column j, same row
    c += T.bl(va + len(c), selclip_va)
    c += T.movs_imm8(3, 0)
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(1, 0x1E)
    c += T.ldr_imm32(0, LA.SESSION)
    c += T.bl(va + len(c), CM.SETVIEW)
    L["restore"] = va + len(c)
    c += T.ldr_imm32(0, LA.SESSION + PREV_MODE)
    c += T.strb_imm(6, 0, 0)
    L["ret"] = va + len(c)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def tbtap(va, L, tbact_va):
    """b.w at TAP_SITE (r1 = r5 = msg {u16 type, +0xC id}, r4 = page)."""
    c = T.ldrh_imm(3, 1, 0)
    c += T.cmp_imm(3, 1)
    c += T.b_cond(va + len(c), "eq", L.get("maybe", va))
    c += T.cmp_imm(3, 2)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    L["maybe"] = va + len(c)
    c += T.ldr_imm(2, 1, 0xC)
    c += T.movw(0, ID0)
    c += T.subs_reg(2, 2, 0)
    c += T.cmp_imm(2, 7)
    c += T.b_cond(va + len(c), "hi", L.get("stock", va))
    c = _is_seq_page(c, va, L, 4, "stock")
    c += T.cmp_imm(3, 2)
    c += T.b_cond(va + len(c), "ne", L.get("swallow", va))   # press: nothing (the button shows it pressed)
    c += T.mov_reg(0, 2)
    c += T.bl(va + len(c), tbact_va)
    L["swallow"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.bw(va + len(c), TAP_EXIT)
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)                     # r0 = page, as on entry
    c += T.mov_reg(1, 5)                     # r1 = msg (the seq-page test uses r1; r5 holds msg too)
    c += T.ldrh_imm(3, 1, 0)                 # displaced: ldrh r3, [r1]; cmp r3, #0x3d
    c += T.cmp_imm(3, 0x3D)
    c += T.bw(va + len(c), TAP_BACK)
    return c


def rolldraw(va, L):
    """Piano roll view draw (r0 view, r1 ctx): hide the mini grid and the pattern letter, then the stock draw."""
    c = T.push_lo([0, 1, 4], lr=True)        # 16 B
    for off, vt, idv in ((MINI_OFF, MINI_VT, None), (LETTER_OFF, BTN_VT, LETTER_ID)):
        tag = "s%X" % off
        c += T.ldr_imm32(4, off)
        c += T.add_reg(4, 0)
        c += T.ldr_imm(2, 4, 0)
        c += T.ldr_imm32(3, vt)
        c += T.cmp_reg(2, 3)
        c += T.b_cond(va + len(c), "ne", L.get(tag, va))
        if idv is not None:
            c += T.ldr_imm(2, 4, 0x14)
            c += T.cmp_imm(2, idv)
            c += T.b_cond(va + len(c), "ne", L.get(tag, va))
        c += T.movs_imm8(2, 1)
        c += T.adds_imm8(4, 0x30)
        c += T.strb_imm(2, 4, 0)             # +0x30 hidden
        c += T.strb_imm(2, 4, 1)             # +0x31
        L[tag] = va + len(c)
    c += T.ldr_sp(0, 12)
    c += T.mov_reg(14, 0)
    c += T.pop_lo([0, 1, 4])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), CONTAINER_DRAW)
    return c
