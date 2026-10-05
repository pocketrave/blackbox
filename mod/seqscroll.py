"""v006 SEQS clip grid: scrolling 4x16 view.

Widget row v shows physical row p=(top+v)&3, variation sub=(top+v)>>2;
inverse v=(p-top)&3. top = the SEQS view's bottom-right encoder value
[view+0x1AEC] (range 0..12, set by H1).
"""
import thumb as T

ROOT_PTR = 0x24002E6C       # UI root object pointer (written once, 0x08044278)
VIEW_OFF = 0x39F90          # SEQS view = root + VIEW_OFF
TOP_OFF = 0x1AEC            # encoder-3 value object +0xC  -> top
LAST_OFF = 0x1AF8           # u8 last encoder-3 value (stock: current panel)
CELLS_OFF = 0x34            # first cell widget
ROW_STRIDE = 0x680
COL_STRIDE = 0x1A0
DESC_OFF = 0x38             # cell widget u16 desc (row<<4 | col)
SEL_OFF = 0x1A90            # view u16 selected desc (layer bits clear)
LABEL_BTN = 0x3F70          # quick panel 4th button (view+0x3D5C+0x214)
SESSION = 0x24020088
MSG_VT = 0x080EAF38
GETP2 = 0x08099504          # (SESSION, msg*, id, int* out)
SETPLAYING = 0x080A4F4C
SETHIGHLIGHT = 0x080A4E86
UPDATECELL = 0x080B48E0
REFRESH = 0x080B4C80
SETTEXT = 0x080A3DEC
P_LAYER = 0xC0


def actv(va, L):
    """r0=view, r1=p, r2=c -> r0 = (active layer == displayed sub), r1 = v."""
    c = b""
    c += T.push_lo([4, 5, 6], lr=True)     # 16 B
    c += T.sub_sp_imm(16)                  # [sp] msg {vt, desc}, [sp+8] out -> 32 B
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.mov_reg(6, 2)
    c += T.ldr_imm32(3, MSG_VT)
    c += T.str_sp(3, 0)
    c += T.lsls_imm(3, 5, 4)
    c += T.orrs_reg(3, 6)
    c += T.movs_imm8(2, 1)
    c += T.lsls_imm(2, 2, 8)
    c += T.orrs_reg(3, 2)                  # 0x100 | p<<4 | c
    c += T.mov_reg(2, 13)
    c += T.strh_imm(3, 2, 4)
    c += T.movs_imm8(3, 0)
    c += T.str_sp(3, 8)
    c += T.ldr_imm32(0, SESSION)
    c += T.mov_reg(1, 13)
    c += T.movs_imm8(2, P_LAYER)
    c += T.add_rd_sp(3, 8)
    c += T.bl(va + len(c), GETP2)
    c += T.ldr_imm32(3, TOP_OFF)
    c += T.add_reg(3, 4)
    c += T.ldr_imm(3, 3)                   # top
    c += T.subs_reg(1, 5, 3)
    c += T.movs_imm8(2, 3)
    c += T.ands_reg(1, 2)                  # v
    c += T.adds_reg(2, 3, 1)
    c += T.lsrs_imm(2, 2, 2)               # sub
    c += T.ldr_sp(3, 8)                    # L
    c += T.movs_imm8(0, 0)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c += T.movs_imm8(0, 1)
    L["out"] = va + len(c)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


H3_SITE, H3_ORIG, H3_BACK = 0x080B48EE, bytes.fromhex("0c461646"), 0x080B48F2
H4_SITE, H4_ORIG, H4_BACK = 0x080B4A00, bytes.fromhex("07990131"), 0x080B4A04
H5_SITE, H5_ORIG, H5_BACK = 0x080B4A86, bytes.fromhex("0899003918bf0121"), 0x080B4A8E


def _top(rd, rview):
    """rd = [rview + TOP_OFF] (rd != rview)."""
    return T.ldr_imm32(rd, TOP_OFF) + T.add_reg(rd, rview) + T.ldr_imm(rd, rd)


def h3(va, L):
    """UpdateCell entry: r4 = widget row v = (p - top) & 3; r6 = col."""
    c = _top(3, 5)
    c += T.subs_reg(4, 1, 3)
    c += T.movs_imm8(3, 3)
    c += T.ands_reg(4, 3)
    c += T.mov_reg(6, 2)
    c += T.bw(va + len(c), H3_BACK)
    return c


def h4(va, L):
    """Displayed variation: [sp+0x1c] = sub = (top + v) >> 2; r1 = sub + 1 (letter index)."""
    c = _top(3, 5)
    c += T.adds_reg(3, 3, 4)
    c += T.lsrs_imm(3, 3, 2)
    c += T.str_sp(3, 0x1C)
    c += T.adds_imm(1, 3, 1)
    c += T.bw(va + len(c), H4_BACK)
    return c


def h5(va, L, actv_va):
    """Playing flag: r1 = enabled && active layer == displayed sub.
    At this point r5 = view + v*0x680 + c*0x1A0 and r4 = v*0x680 (0x080B4A5A..7E)."""
    c = T.subs_reg(0, 5, 4)
    c += T.ldr_imm32(3, COL_STRIDE)
    c += T.muls(3, 6)
    c += T.subs_reg(0, 0, 3)                  # r0 = view
    c += T.lsrs_imm(1, 7, 4)
    c += T.movs_imm8(2, 0xF)
    c += T.ands_reg(1, 2)
    c += T.mov_reg(2, 6)
    c += T.bl(va + len(c), actv_va)
    c += T.ldr_sp(1, 0x20)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("z", va))
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("z", va))
    c += T.movs_imm8(1, 1)
    c += T.b_short(va + len(c), L.get("o", va))
    L["z"] = va + len(c)
    c += T.movs_imm8(1, 0)
    L["o"] = va + len(c)
    c += T.bw(va + len(c), H5_BACK)
    return c


H6_SITE = 0x080B4DAA
H6_ORIG = bytes.fromhex("0399003918bf01212846f0f7caf8")
H6_BACK = 0x080B4DB8


def h6(va, L, actv_va):
    """Refresh loop body: SetPlaying(widget showing phys (p,c), enabled && active==displayed)."""
    c = T.ldr_sp(0, 4)
    c += T.subs_imm8(0, CELLS_OFF)          # view
    c += T.lsrs_imm(1, 7, 4)               # p
    c += T.mov_reg(2, 4)                   # col
    c += T.bl(va + len(c), actv_va)        # r0 = act, r1 = v
    c += T.ldr_sp(2, 0xC)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("z", va))
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("z", va))
    c += T.movs_imm8(2, 1)
    c += T.b_short(va + len(c), L.get("w", va))
    L["z"] = va + len(c)
    c += T.movs_imm8(2, 0)
    L["w"] = va + len(c)
    c += T.ldr_sp(0, 4)
    c += T.ldr_imm32(3, ROW_STRIDE)
    c += T.muls(3, 1)
    c += T.add_reg(0, 3)
    c += T.ldr_imm32(3, COL_STRIDE)
    c += T.muls(3, 4)
    c += T.add_reg(0, 3)
    c += T.mov_reg(1, 2)
    c += T.bl(va + len(c), SETPLAYING)
    c += T.bw(va + len(c), H6_BACK)
    return c


EXIT13 = 0x080B5308                      # slot-13 epilogue (r4,r6-r9 dead)
MLA_ORIG = bytes.fromhex("03fb0200")     # mla r0, r3, r2, r0
H7A_SITE, H7A_BACK = 0x080B53C2, 0x080B53C6
H7B_SITE, H7B_BACK = 0x080B53FA, 0x080B53FE
H7C_SITE, H7C_BACK = 0x080B5438, 0x080B543C


def h7a(va, L, actv_va):
    """msg 0x37: only for the displayed clip that is active; r0 += v*0x680."""
    c = T.mov_reg(7, 1)                    # col
    c += T.mov_reg(6, 0)                   # col*0x1A0 + 0x34
    c += T.mov_reg(0, 5)
    c += T.mov_reg(1, 2)
    c += T.mov_reg(2, 7)
    c += T.bl(va + len(c), actv_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("x", va))
    c += T.ldr_imm32(3, ROW_STRIDE)
    c += T.muls(3, 1)
    c += T.mov_reg(0, 6)
    c += T.add_reg(0, 3)
    c += T.bw(va + len(c), H7A_BACK)
    L["x"] = va + len(c)
    c += T.bw(va + len(c), EXIT13)
    return c


def h7b(va, L):
    """msg 0x38 (clear): remap only; r0 += ((p - top) & 3) * 0x680."""
    c = T.mov_reg(6, 0)
    c += _top(3, 5)
    c += T.subs_reg(2, 2, 3)
    c += T.movs_imm8(3, 3)
    c += T.ands_reg(2, 3)
    c += T.ldr_imm32(3, ROW_STRIDE)
    c += T.muls(3, 2)
    c += T.mov_reg(0, 6)
    c += T.add_reg(0, 3)
    c += T.bw(va + len(c), H7B_BACK)
    return c


def h7c(va, L, actv_va):
    """msg 0x3B (progress): gated like 0x37; r1 = msg* preserved."""
    c = T.mov_reg(6, 0)
    c += T.mov_reg(7, 1)                   # msg*
    c += T.mov_reg(4, 2)                   # p
    c += T.ldrh_imm(3, 7, 8)
    c += T.movs_imm8(2, 0xF)
    c += T.ands_reg(3, 2)                  # col
    c += T.mov_reg(0, 5)
    c += T.mov_reg(1, 4)
    c += T.mov_reg(2, 3)
    c += T.bl(va + len(c), actv_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("x", va))
    c += T.ldr_imm32(3, ROW_STRIDE)
    c += T.muls(3, 1)
    c += T.mov_reg(0, 6)
    c += T.add_reg(0, 3)
    c += T.mov_reg(1, 7)
    c += T.bw(va + len(c), H7C_BACK)
    L["x"] = va + len(c)
    c += T.bw(va + len(c), EXIT13)
    return c


H1_SITE, H1_ORIG, H1_NEW = 0x080B5256, bytes.fromhex("0221"), bytes.fromhex("0d21")  # count 2 -> 13
H2_SITE, H2_ORIG = 0x080B552C, bytes.fromhex("05f58052")
POOL_SITE, POOL_ORIG = 0x080B8480, bytes.fromhex("60b00c08")    # -> "" for the 4th button
LABEL0 = b"1-4\x00"


def _num(va, c0, L, key, rbuf, rn):
    """Append decimal rn (1..16) at [rbuf] and advance rbuf. c0 = cave offset. Clobbers r2."""
    c = T.cmp_imm(rn, 10)
    c += T.b_cond(va + c0 + len(c), "lt", L.get(key, va))
    c += T.movs_imm8(2, 0x31) + T.strb_imm(2, rbuf, 0) + T.adds_imm8(rbuf, 1)
    c += T.subs_imm8(rn, 10)
    L[key] = va + c0 + len(c)
    c += T.adds_imm8(rn, 0x30) + T.strb_imm(rn, rbuf, 0) + T.adds_imm8(rbuf, 1)
    return c

def h2(va, L):
    """After encoder-3 AddDelta: if top changed -> rebind, highlight, UpdateCell x16, refresh, label."""
    c = _top(6, 5)                                        # r6 = top
    c += T.ldr_imm32(3, LAST_OFF)
    c += T.add_reg(3, 5)
    c += T.ldrb_imm(2, 3, 0)
    c += T.cmp_reg(2, 6)
    c += T.b_cond(va + len(c), "eq", L.get("exit", va))
    c += T.strb_imm(6, 3, 0)
    # --- rebind 16 widgets + highlight
    c += T.movs_imm8(7, 0)                                # v
    L["rv"] = va + len(c)
    c += T.movs_imm8(4, 0)                                # col
    L["rc"] = va + len(c)
    c += T.ldr_imm32(0, ROW_STRIDE)
    c += T.muls(0, 7)
    c += T.ldr_imm32(1, COL_STRIDE)
    c += T.muls(1, 4)
    c += T.add_reg(0, 1)
    c += T.adds_imm8(0, CELLS_OFF)
    c += T.add_reg(0, 5)                                  # r0 = widget
    c += T.adds_reg(1, 6, 7)
    c += T.movs_imm8(2, 3)
    c += T.ands_reg(1, 2)
    c += T.lsls_imm(1, 1, 4)
    c += T.orrs_reg(1, 4)                                 # r1 = desc
    c += T.strh_imm(1, 0, DESC_OFF)
    c += T.ldr_imm32(3, SEL_OFF)
    c += T.add_reg(3, 5)
    c += T.ldrh_imm(3, 3, 0)
    c += T.movs_imm8(2, 0)
    c += T.cmp_reg(1, 3)
    c += T.b_cond(va + len(c), "ne", L.get("nh", va))
    c += T.movs_imm8(2, 1)
    L["nh"] = va + len(c)
    c += T.mov_reg(8, 0)                      # keep widget
    c += T.mov_reg(1, 2)
    c += T.bl(va + len(c), SETHIGHLIGHT)
    c += T.mov_reg(0, 8)
    c += T.movs_imm8(1, 0)
    c += T.bl(va + len(c), SETREC)            # record mark off (stock msg 0x67 does the same)
    c += T.adds_imm8(4, 1)
    c += T.cmp_imm(4, 4)
    c += T.b_cond(va + len(c), "ne", L.get("rc", va))
    c += T.adds_imm8(7, 1)
    c += T.cmp_imm(7, 4)
    c += T.b_cond(va + len(c), "ne", L.get("rv", va))
    # --- UpdateCell(view, p, c) for all 16 physical cells
    c += T.movs_imm8(7, 0)
    L["up"] = va + len(c)
    c += T.movs_imm8(4, 0)
    L["uc"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.mov_reg(1, 7)
    c += T.mov_reg(2, 4)
    c += T.bl(va + len(c), UPDATECELL)
    c += T.adds_imm8(4, 1)
    c += T.cmp_imm(4, 4)
    c += T.b_cond(va + len(c), "ne", L.get("uc", va))
    c += T.adds_imm8(7, 1)
    c += T.cmp_imm(7, 4)
    c += T.b_cond(va + len(c), "ne", L.get("up", va))
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), REFRESH)
    # --- label "a-b" in an 8-byte stack buffer (frame 112+8 = 120, aligned)
    c += T.sub_sp_imm(8)
    c += T.mov_reg(4, 13)                                 # r4 = write ptr
    c += T.mov_reg(1, 6)
    c += T.adds_imm8(1, 1)                                # a = top + 1
    c += _num(va, len(c), L, "n1", 4, 1)
    c += T.movs_imm8(2, 0x2D)
    c += T.strb_imm(2, 4, 0)
    c += T.adds_imm8(4, 1)
    c += T.mov_reg(1, 6)
    c += T.adds_imm8(1, 4)                                # b = top + 4
    c += _num(va, len(c), L, "n2", 4, 1)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 4, 0)
    c += T.ldr_imm32(0, LABEL_BTN)
    c += T.add_reg(0, 5)
    c += T.mov_reg(1, 13)
    c += T.bl(va + len(c), SETTEXT)
    c += T.add_sp_imm(8)
    L["exit"] = va + len(c)
    c += T.bw(va + len(c), EXIT13)
    return c


L_SITE, L_ORIG = 0x080A45D6, bytes.fromhex("40f0d181")   # bne.w 0x080A497C
L_DRAW, L_SKIP = 0x080A497C, 0x080A45DA


def lskip(va, L):
    """Skip the A-D letter for SEQS view cells only; stock branch elsewhere."""
    c = T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("skip0", va))
    c += T.push_lo([0, 1])
    c += T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("draw", va))
    c += T.ldr_imm32(1, VIEW_OFF + CELLS_OFF)
    c += T.add_reg(0, 1)                               # first cell
    c += T.cmp_reg(4, 0)
    c += T.b_cond(va + len(c), "cc", L.get("draw", va))
    c += T.ldr_imm32(1, 4 * ROW_STRIDE)
    c += T.add_reg(0, 1)                               # end of the 16 cells
    c += T.cmp_reg(4, 0)
    c += T.b_cond(va + len(c), "cs", L.get("draw", va))
    c += T.pop_lo([0, 1])
    L["skip0"] = va + len(c)
    c += T.bw(va + len(c), L_SKIP)
    L["draw"] = va + len(c)
    c += T.pop_lo([0, 1])
    c += T.bw(va + len(c), L_DRAW)
    return c


# ---------------------------------------------------------------- fix pass (C1, C3, I1)
SETREC = 0x080A4E9A                  # cell +0x179 record mark (msgs 0x37/0x38)
PREVIEW_UPD = 0x080C1A84             # per-frame note-preview update

# C1: the stock Refresh cursor re-sync reads encoder 3 as an offset and resets it to 0.
RF_TOP_SITE, RF_TOP_ORIG = 0x080B4CE6, bytes.fromhex("d2f8ec3a")        # ldr.w r3,[r2,#0xaec]
RF_TOP_NEW = T.movs_imm8(3, 0) + T.nop()                                 # enc1 alone (as 0x080B5574)
RF_RESET_SITE, RF_RESET_ORIG = 0x080B4D28, bytes.fromhex("00210af5d750fbf70dfd")  # SetValue(enc3, 0)
RF_RESET_NEW = T.nop() * 5

# C3: per-frame tick = view slot 0 0x080B55F4, loops physical rows r = [sp] / r1.
T0R_SITE, T0R_ORIG, T0R_BACK = 0x080B56EC, bytes.fromhex("164675464f46e046"), 0x080B56F4
T0G_SITE, T0G_ORIG, T0G_BACK = 0x080B5682, bytes.fromhex("30460cf0fef9"), 0x080B5688


def t0r(va, L):
    """Row setup: bind widget arrays to row v = (r - top) & 3 instead of r.
    In: r1 = r, r2 preview base, lr cell base, sb aux base, ip 'G'-flag ptr (all for row r);
    view = [sp+0x18]. Out: r6/r5/r7/r8 for row v; r1, r2, lr, sb, ip unchanged."""
    c = T.ldr_sp(0, 0x18)
    c += _top(3, 0)
    c += T.subs_reg(0, 1, 3)
    c += T.movs_imm8(3, 3)
    c += T.ands_reg(0, 3)                     # v
    c += T.subs_reg(0, 0, 1)                  # d = v - r
    c += T.ldr_imm32(3, 0x610)
    c += T.muls(3, 0)
    c += T.add_reg(3, 2)
    c += T.mov_reg(6, 3)
    c += T.ldr_imm32(3, ROW_STRIDE)
    c += T.muls(3, 0)
    c += T.add_reg(3, 14)
    c += T.mov_reg(5, 3)
    c += T.ldr_imm32(3, 0x1E0)
    c += T.muls(3, 0)
    c += T.add_reg(3, 9)
    c += T.mov_reg(7, 3)
    c += T.lsls_imm(3, 0, 2)
    c += T.add_reg(3, 12)
    c += T.mov_reg(8, 3)
    c += T.bw(va + len(c), T0R_BACK)
    return c


def t0g(va, L, actv_va):
    """Per cell: if the displayed clip is not its cell's active layer, progress = -100 (stock 'stopped')."""
    c = T.ldr_sp(0, 0x18)
    c += T.ldr_sp(1, 0)
    c += T.mov_reg(2, 4)
    c += T.bl(va + len(c), actv_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("keep", va))
    c += T.ldr_imm32(9, 0xFFFFFF9C)           # sb = -100
    L["keep"] = va + len(c)
    c += T.mov_reg(0, 6)                      # displaced: mov r0, r6; bl preview update
    c += T.bl(va + len(c), PREVIEW_UPD)
    c += T.bw(va + len(c), T0G_BACK)
    return c


# ---------------------------------------------------------------- v011: clockwise scrolls DOWN
# View slot 13, encoder index 3: r1 = delta ([msg+0x10], 0x080B54AA), r0 = view; then
# `add.w r0,r0,#0x1ae0; bl AddDelta`. Only this path is the bottom-right encoder.
KNOB_SITE, KNOB_ORIG, KNOB_BACK = 0x080B5524, bytes.fromhex("00f5d750"), 0x080B5528


def knob(va, L):
    c = T.negs(1, 1)                           # delta = -delta
    c += KNOB_ORIG                             # add.w r0, r0, #0x1ae0
    c += T.bw(va + len(c), KNOB_BACK)
    return c
