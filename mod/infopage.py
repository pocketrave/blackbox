"""v008: SEQS INFO x2 page without tabs."""
import thumb as T

GETPARAM = 0x08093E9C
RESOLVE = 0x08097CE8
GETPAGEINFO = 0x080996B0
P_STEPLEN, P_STEPCOUNT, P_LAYER = 0x85, 0x86, 0xC0

D1_SITE, D2_SITE = 0x080EEF30, 0x080EEEE8                       # Seq lists, after 4 ids
D_ORIG, D_NEW = bytes.fromhex("00000000"), bytes.fromhex("85008600")


PAGE_DESC = 0x38                       # page object: msg struct +0x34, desc at +0x38
TABCOUNT = 0x770
SH_SITE, SH_ORIG, SH_BACK = 0x080A78C4, bytes.fromhex("01990131"), 0x080A78C8
NB_SITE, NB_ORIG, NB_BACK = 0x080A73C4, bytes.fromhex("d5f87037"), 0x080A73C8


def sh(va, L):
    """Page show: sequence pages load tab 0 (the only page); others stock: active layer + 1."""
    c = T.ldrh_imm(1, 4, PAGE_DESC)
    c += T.lsrs_imm(1, 1, 8)
    c += T.cmp_imm(1, 1)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.movs_imm8(1, 0)
    c += T.bw(va + len(c), SH_BACK)
    L["stock"] = va + len(c)
    c += T.ldr_sp(1, 4)
    c += T.adds_imm(1, 1, 1)
    c += T.bw(va + len(c), SH_BACK)
    return c


def nb(va, L):
    """Load: sequence pages insert no tab buttons (count 0); others stock [r5+0x770]."""
    c = T.ldrh_imm(3, 5, PAGE_DESC)
    c += T.lsrs_imm(3, 3, 8)
    c += T.cmp_imm(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.movs_imm8(3, 0)
    c += T.bw(va + len(c), NB_BACK)
    L["stock"] = va + len(c)
    c += T.ldr_imm32(3, TABCOUNT)
    c += T.add_reg(3, 5)
    c += T.ldr_imm(3, 3)
    c += T.bw(va + len(c), NB_BACK)
    return c


# ---------------------------------------------------------------- fix (C1): the rows the page SHOWS
# The visible rows are built by 0x08098D40 (called from the page refresh 0x080A729C), not by
# GetPageInfo. Its layer-1 loop reads every id with `bl GetParam` at 0x08098F70 from owner r8 =
# Resolve(sess, msg, 0) on the Seq page. At that point: r0 = r8 = owner, r1 = r5 = id,
# r7 = list end (list + 0x7E), [sp+4] = session; tab and msg are gone.
ROWGET_SITE, ROWGET_ORIG = 0x08098F70, bytes.fromhex("faf794ff")
SEQ_END, MIDI_END = 0x080EEF28 + 0x7E, 0x080EEEE0 + 0x7E       # r7 on the Seq page (normal / MIDI-seq)
DEFAULT_OFF = 0x8CC8                    # Resolve's fallback object (sub > 3 or a bad desc)
SUB_STRIDE = 0x2C                       # owner(sub) = owner(0) + sub * 0x2C (Resolve 0x08097D2A)


SCP_SITES = ((0x0809FE26, bytes.fromhex("002411e0")),      # SetCellParam 0x49: movs r4,#0; b 0x0809FE4E
             (0x080A0292, bytes.fromhex("0024dbe5")))      # SetCellParam 0x46: movs r4,#0; b 0x0809FE4E
SCP_ACTIVE = 0x0809FE3C                                     # r4 = GetParam(sub 0, 0xC0): the active layer
CLIP_IDS = (P_STEPLEN, P_STEPCOUNT, 0x49, 0x46)             # v041: per-clip ids (read from the active layer)


def rd2(va, L, ids=(P_STEPLEN, P_STEPCOUNT), clamp_stepmode=False, name_id=None):
    """Seq page rows of `ids`: read from the active layer's record, as the write path writes them.
    Active layer > 3 -> the default object (Resolve's fallback, the same as SetCellParam's write)."""
    c = b""
    if name_id is not None:                    # v046: the column page's Name row reads 1 (edits in both directions)
        c += T.ldr_imm32(3, name_id)
        c += T.cmp_reg(1, 3)
        c += T.b_cond(va + len(c), "ne", L.get("notname", va))
        c += T.movs_imm8(0, 1)
        c += T.bx(14)
        L["notname"] = va + len(c)
    for pid in ids[:-1]:
        c += T.cmp_imm(1, pid)
        c += T.b_cond(va + len(c), "eq", L.get("pat", va))
    c += T.cmp_imm(1, ids[-1])
    c += T.b_cond(va + len(c), "ne", L.get("plain", va))
    L["pat"] = va + len(c)
    c += T.ldr_imm32(2, SEQ_END)
    c += T.cmp_reg(7, 2)
    c += T.b_cond(va + len(c), "eq", L.get("t0", va))
    c += T.ldr_imm32(2, MIDI_END)
    c += T.cmp_reg(7, 2)
    c += T.b_cond(va + len(c), "ne", L.get("plain", va))
    L["t0"] = va + len(c)
    c += T.push_lo([4, 5, 6], lr=True)         # 16 B
    c += T.mov_reg(4, 0)                       # owner(sub 0)
    c += T.mov_reg(5, 1)                       # id
    c += T.ldr_sp(6, 16 + 4)                   # session (caller's [sp+4])
    c += T.ldr_imm32(3, DEFAULT_OFF)
    c += T.add_reg(3, 6)
    c += T.mov_reg(0, 4)
    c += T.cmp_reg(4, 3)                       # already the default object -> read it as is
    c += T.b_cond(va + len(c), "eq", L.get("get", va))
    c += T.movs_imm8(1, P_LAYER)
    c += T.bl(va + len(c), GETPARAM)           # r0 = active layer
    c += T.cmp_imm(0, 3)
    c += T.b_cond(va + len(c), "hi", L.get("dflt", va))
    c += T.movs_imm8(1, SUB_STRIDE)
    c += T.muls(1, 0)
    c += T.mov_reg(0, 4)
    c += T.add_reg(0, 1)                       # owner(active layer)
    c += T.b_short(va + len(c), L.get("get", va))
    L["dflt"] = va + len(c)
    c += T.ldr_imm32(0, DEFAULT_OFF)
    c += T.add_reg(0, 6)
    L["get"] = va + len(c)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), GETPARAM)
    c += T.pop_lo([4, 5, 6], pc=True)
    L["plain"] = va + len(c)
    if clamp_stepmode:                         # v042: 0x88 = 2 (the per-clip marker, leaked by a paste) reads as ON
        c += T.cmp_imm(1, 0x88)
        c += T.b_cond(va + len(c), "ne", L.get("tail", va))
        c += T.push_lo([4], lr=True)
        c += T.bl(va + len(c), GETPARAM)
        c += T.cmp_imm(0, 1)
        c += T.b_cond(va + len(c), "ls", L.get("sm", va))
        c += T.movs_imm8(0, 1)
        L["sm"] = va + len(c)
        c += T.pop_lo([4], pc=True)
        L["tail"] = va + len(c)
    c += T.bw(va + len(c), GETPARAM)           # tail call, lr intact
    return c


# ---------------------------------------------------------------- v016: full-height INFO page
# SH2 replaces SH at the same site (SH stays emitted but unused, so earlier caves keep their VAs).
# On every page show (msg 0xD4): sequence pages hide the tab toolbar and give the parameter list
# the whole upper area; other pages get the stock toolbar and list rect back (the page object is
# shared).
TOOLBAR = 0xB5F0                      # tab toolbar widget (rect 0,0,320,38)
LIST = 0xA48                          # parameter list widget
HIDE = 0x080B810C                     # (w, v): w+0x30 = v (1 = hidden), marks dirty
SETRECT = 0x080B9B80                  # (list, rect*): copy to +4 and +0x38, re-layout rows
SCROLL_OFF = 0xC0                     # list+0x34 scroll view +0x8C: offset (setter 0x080C578A clamps and stores)
RECT_STOCK = (0, 40, 320, 141)        # ctor 0x080A7BEE..: (0, h_tb+2, 320, 0xB3-h_tb)
RECT_SEQ = (0, 1, 320, 180)           # 6 rows x 30 px; 1-px gap to the bottom toolbar at y 182


def sh2(va, L, stock_va, seq_va):
    c = T.ldr_sp(1, 4)                        # active layer (before the push)
    c += T.push_lo([1, 2, 3, 5])              # 16 B
    c += T.ldrh_imm(5, 4, PAGE_DESC)
    c += T.lsrs_imm(5, 5, 8)
    c += T.cmp_imm(5, 1)
    c += T.b_cond(va + len(c), "ne", L.get("ns", va))
    c += T.movs_imm8(5, 1)
    c += T.b_short(va + len(c), L.get("s", va))
    L["ns"] = va + len(c)
    c += T.movs_imm8(5, 0)
    L["s"] = va + len(c)                      # r5 = 1 on sequence pages
    c += T.ldr_imm32(0, TOOLBAR)
    c += T.add_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), HIDE)
    c += T.ldr_imm32(0, LIST)
    c += T.add_reg(0, 4)
    c += T.ldr_imm32(1, stock_va)
    c += T.cmp_imm(5, 0)
    c += T.b_cond(va + len(c), "eq", L.get("go", va))
    c += T.ldr_imm32(1, seq_va)
    c += T.ldr_imm32(2, LIST + SCROLL_OFF)
    c += T.add_reg(2, 4)
    c += T.movs_imm8(3, 0)
    c += T.str_imm(3, 2, 0)                   # seq page: scroll offset = 0 (content 6 rows <= h, so 0 is valid)
    L["go"] = va + len(c)
    c += T.bl(va + len(c), SETRECT)
    c += T.mov_reg(12, 5)                     # keep seq across the pop
    c += T.pop_lo([1, 2, 3, 5])
    c += T.mov_reg(3, 12)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("stock", va))
    c += T.movs_imm8(1, 0)                    # sequence page: tab 0
    c += T.bw(va + len(c), SH_BACK)
    L["stock"] = va + len(c)
    c += T.adds_imm(1, 1, 1)                  # stock: active layer + 1
    c += T.bw(va + len(c), SH_BACK)
    return c
