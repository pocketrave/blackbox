"""v033 edit sync.

ECHO (0x0809C228, engine echo of the playing slot -> UI 0xC0): drop it for the 8 host cells (rows 0-1,
cols 0-3); the UI 0xC0 of a host is the editor's pattern now (SELCLIP), L3 reads play state from the engine.
SYNC (0x080985A0 SendPattern(session, desc*, pat), every record upload): stock runs via SPSTOCK unless the
target is a host slot that holds a streamed clip (I3); for host pattern 0 the UI 0xC0 is swapped for the
engine's current slot around stock (stock posts 0xC0); then the record is restreamed (STREAM) into every
host slot s >= 1 whose slot_clip says it holds this clip.
"""
import thumb as T
import fwbase
import phase5 as P5
import launch as LA

SP_SITE, SP_ORIG, SP_BACK = 0x080985A0, bytes.fromhex("2de9f04f"), 0x080985A4     # push.w {r4-r11,lr}
ECHO_SITE, ECHO_ORIG, ECHO_BACK = 0x0809C228, bytes.fromhex("70b58eb0"), 0x0809C22C  # push {r4-r6,lr}; sub sp,#0x38


def findp(va, L):
    """r0 = engine code -> r0 = clip player or 0. Uses r1-r3; r4/r5 saved."""
    c = T.push_lo([4, 5])
    c += T.mov_reg(2, 0)
    c += T.ldr_imm32(1, LA.REGISTRY)
    c += T.movs_imm8(3, 64)
    L["loop"] = va + len(c)
    c += T.ldr_imm(0, 1, 0)
    c += T.adds_imm8(1, 4)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("next", va))
    c += T.ldr_imm(4, 0, 0)
    c += T.ldr_imm32(5, LA.PLAYER_VT)
    c += T.cmp_reg(4, 5)
    c += T.b_cond(va + len(c), "ne", L.get("next", va))
    c += T.ldr_imm(4, 0, 0x18)
    c += T.cmp_reg(4, 2)
    c += T.b_cond(va + len(c), "eq", L.get("found", va))
    L["next"] = va + len(c)
    c += T.subs_imm8(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    c += T.movs_imm8(0, 0)
    L["found"] = va + len(c)
    c += T.pop_lo([4, 5])
    c += T.bx(14)
    return c


def stream(va, L, duty_from_clip=False):
    """(r0 code, r1 slot, r2 record, r3 host pattern-0 record): Step Len/Count from the record, duty from the
    host, numbering, clear, events (<= 512) whose start tick < Step Count * 960 (v036). Same frame layout as
    LAUNCH (plus [sp+0x34] = tick limit), so launch._post is reused."""
    FR = 60
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)
    c += T.str_sp(0, 0x2C)
    c += T.str_sp(1, 0x24)
    c += T.mov_reg(6, 2)
    c += T.str_sp(3, 0x30)
    for id_ in LA.SLOT_PARAMS:
        if id_ == 0x49 and not duty_from_clip:   # v033-v040: Duty from the host; v041: the clip's own record
            c += T.ldr_sp(0, 0x30)
        else:
            c += T.mov_reg(0, 6)
        c += T.movs_imm8(1, id_)
        c += T.bl(va + len(c), LA.GETPARAM)
        if id_ == 0x86:
            c += T.movw(1, 960)
            c += T.muls(1, 0)
            c += T.str_sp(1, 0x34)           # v036: tick limit = Step Count * 960
        c = LA._post(c, va, id_, 0, 0x24)
    c += T.mov_reg(5, 6)
    c += T.adds_imm8(5, 0x18)
    c += T.ldr_imm(0, 5, 4)
    c += T.movw(1, LA.MAX_EVENTS)
    c += T.cmp_reg(0, 1)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.movs_imm8(2, 0)
    c += T.ldr_imm32(1, LA.SESSION + 0xE808)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), LA.NUMBER)
    c += T.ldr_sp(3, 0x24)
    c += T.movs_imm8(2, 0)
    c += T.ldr_sp(1, 0x2C)
    c += T.ldr_imm32(0, LA.ENGINE)
    c += T.bl(va + len(c), LA.CLEARSLOT)
    c += T.movs_imm8(4, 0)
    L["loop"] = va + len(c)
    c += T.add_rd_sp(2, 8)
    c += T.mov_reg(1, 4)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), LA.GETEVENT)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_sp(0, 0xC)                    # event start tick (buffer at sp+8)
    c += T.ldr_sp(1, 0x34)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "cs", L.get("skipev", va))
    c += T.ldr_sp(0, 0x24)
    c += T.str_sp(0, 0)
    c += T.ldr_imm32(3, LA.SESSION + 0x8CBC)
    c += T.ldr_imm(3, 3)
    c += T.add_rd_sp(2, 8)
    c += T.ldr_sp(1, 0x2C)
    c += T.ldr_imm32(0, LA.ENGINE)
    c += T.bl(va + len(c), LA.ADDEVENT)
    L["skipev"] = va + len(c)
    c += T.adds_imm8(4, 1)
    c += T.b_short(va + len(c), L.get("loop", va))
    L["out"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def echo(va, L):
    """r0 this, r1 msg {+8 engine code, +0xC slot}. Host clip players (code 1rrcc, rr <= 1, cc <= 3): drop."""
    c = T.ldr_imm(3, 1, 8)
    c += T.lsrs_imm(2, 3, 16)
    c += T.cmp_imm(2, 1)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.lsls_imm(2, 3, 16)
    c += T.lsrs_imm(2, 2, 24)               # row
    c += T.cmp_imm(2, 1)
    c += T.b_cond(va + len(c), "hi", L.get("stock", va))
    c += T.lsls_imm(2, 3, 24)
    c += T.lsrs_imm(2, 2, 24)               # col
    c += T.cmp_imm(2, 3)
    c += T.b_cond(va + len(c), "hi", L.get("stock", va))
    c += T.bx(14)
    L["stock"] = va + len(c)
    c += ECHO_ORIG
    c += T.bw(va + len(c), ECHO_BACK)
    return c


def stock_sp(va, L):
    """Called with SendPattern's arguments: the displaced push, then the stock body; returns to the caller."""
    return SP_ORIG + T.bw(va + 4, SP_BACK)


FR = 28   # 20 pushed + 28 = 48. [sp] r0, [sp+4] r1, [sp+8] pat, [sp+12] saved UI 0xC0, [sp+16] rec0, [sp+20] kn


def _call_stock(c, va, stock_va):
    c += T.ldr_sp(0, 0)
    c += T.ldr_sp(1, 4)
    c += T.ldr_sp(2, 8)
    c += T.bl(va + len(c), stock_va)
    return c


def sync(va, L, stock_va, stream_va, findp_va, inv80_va, table_va, hosts_va, per_clip=False):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)
    c += T.str_sp(0, 0)
    c += T.str_sp(1, 4)
    c += T.str_sp(2, 8)
    c += T.ldrh_imm(3, 1, 4)                # desc
    c += T.lsrs_imm(0, 3, 8)
    c += T.movs_imm8(1, 0x1F)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("plain", va))
    c += T.lsrs_imm(4, 3, 4)
    c += T.movs_imm8(0, 0xF)
    c += T.ands_reg(4, 0)                   # r4 = row
    c += T.movs_imm8(5, 0xF)
    c += T.ands_reg(5, 3)                   # r5 = col
    c += T.ldr_sp(6, 8)                     # r6 = pat
    c += T.cmp_imm(4, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("plain", va))
    c += T.cmp_imm(5, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("plain", va))
    c += T.cmp_imm(6, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("plain", va))
    if per_clip:                            # v042: a re-sent B-D record holds intended values: mark it converted
        c += T.cmp_imm(6, 0)
        c += T.b_cond(va + len(c), "eq", L.get("nomark", va))
        c += T.movw(0, 0x370)
        c += T.muls(0, 4)
        c += T.movs_imm8(1, 0xB0)
        c += T.muls(1, 5)
        c += T.adds_reg(0, 0, 1)
        c += T.movs_imm8(1, 0x2C)
        c += T.muls(1, 6)
        c += T.adds_reg(0, 0, 1)
        c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
        c += T.adds_reg(0, 0, 1)
        c += T.movs_imm8(1, 0x88)
        c += T.movs_imm8(2, 2)              # migrate.MARK
        c += T.bl(va + len(c), LA.SETPARAM)
        L["nomark"] = va + len(c)
    c += T.cmp_imm(4, 1)
    c += T.b_cond_w(va + len(c), "hi", L.get("stockrs", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("stockrs", va))
    c += T.lsls_imm(7, 4, 2)
    c += T.adds_reg(7, 7, 5)                # r7 = host index k = col + 4*row
    c += T.cmp_imm(6, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("host0", va))
    # host, pattern p > 0: stock only while slot p holds the stock pattern (I2/I3)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("stockrs", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 4)
    c += T.add_reg(0, 1)
    c += T.lsls_imm(1, 7, 2)
    c += T.add_reg(0, 1)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)                # slot_clip[k][p]
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("stockrs", va))
    c += T.bw(va + len(c), L.get("resync", va))
    # host, pattern 0: swap UI 0xC0 for the engine's current slot around stock
    L["host0"] = va + len(c)
    c += T.movw(0, 0x370)
    c += T.muls(0, 4)
    c += T.movs_imm8(1, 0xB0)
    c += T.muls(1, 5)
    c += T.adds_reg(0, 0, 1)
    c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
    c += T.adds_reg(0, 0, 1)
    c += T.str_sp(0, 16)                    # rec0
    c += T.movs_imm8(1, 0xC0)
    c += T.bl(va + len(c), LA.GETPARAM)
    c += T.str_sp(0, 12)                    # UI 0xC0
    c += T.lsls_imm(0, 4, 8)
    c += T.orrs_reg(0, 5)
    c += T.movs_imm8(1, 1)
    c += T.lsls_imm(1, 1, 16)
    c += T.orrs_reg(0, 1)                   # code 1<<16 | row<<8 | col
    c += T.bl(va + len(c), findp_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("stockrs", va))
    c += T.movw(1, 0xC20)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(1, 1, 0)                 # current slot address
    c += T.cmp_imm(1, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("stockrs", va))
    c += T.subs_reg(1, 1, 0)
    c += T.movw(0, 0x320)
    c += T.subs_reg(1, 1, 0)
    c += T.movs_imm8(0, 0x48)
    c += T.udiv(2, 1, 0)                    # current slot index
    c += T.ldr_sp(0, 16)
    c += T.movs_imm8(1, 0xC0)
    c += T.bl(va + len(c), LA.SETPARAM)
    c = _call_stock(c, va, stock_va)
    c += T.ldr_sp(0, 16)
    c += T.movs_imm8(1, 0xC0)
    c += T.ldr_sp(2, 12)
    c += T.bl(va + len(c), LA.SETPARAM)
    c += T.bw(va + len(c), L.get("resync", va))
    L["stockrs"] = va + len(c)
    c = _call_stock(c, va, stock_va)
    # restream the record into every host slot s >= 1 that holds this clip (I3)
    L["resync"] = va + len(c)
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.ldr_imm32(1, inv80_va)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                # kn
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.str_sp(0, 20)
    c += T.movs_imm8(1, 10)
    c += T.udiv(4, 0, 1)                    # r4 = k
    c += T.muls(1, 4)
    c += T.subs_reg(5, 0, 1)                # r5 = n
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 4)
    c += T.adds_reg(7, 0, 1)
    c += T.lsls_imm(1, 4, 2)
    c += T.add_reg(7, 1)                    # r7 = &slot_clip[k][0]
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(0, 1, 0)
    c += T.str_sp(0, 12)                    # host code
    c += T.ldr_imm(0, 1, 4)
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.add_reg(0, 1)
    c += T.str_sp(0, 16)                    # host pattern-0 record
    if per_clip:                            # v042: the column's launched clip re-sent -> its own Quant to the host
        c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
        c += T.ldr_imm(0, 0, 0)
        c += T.ldr_imm32(1, LA.STATE_OFF + LA.QCELL_OFF)
        c += T.add_reg(0, 1)
        c += T.adds_reg(0, 0, 4)
        c += T.ldrb_imm(0, 0, 0)            # launched[k] = n + 1
        c += T.adds_imm(1, 5, 1)
        c += T.cmp_reg(0, 1)
        c += T.b_cond(va + len(c), "ne", L.get("noq", va))
        c += T.ldr_sp(0, 20)
        c += T.lsls_imm(0, 0, 1)
        c += T.ldr_imm32(1, table_va)
        c += T.add_reg(1, 0)
        c += T.ldrh_imm(0, 1, 0)
        c += T.ldr_imm32(1, LA.SESSION)
        c += T.add_reg(0, 1)                # the clip record
        c += T.movs_imm8(1, LA.QUANT)
        c += T.bl(va + len(c), LA.GETPARAM)
        c += T.mov_reg(3, 0)
        c += T.movs_imm8(0, 0)
        c += T.str_sp(0, 0)                 # [sp] / [sp+4] (r0 / r1 copies) are not used after stock ran
        c += T.str_sp(0, 4)
        c += T.ldr_sp(1, 12)
        c += T.movs_imm8(2, LA.QUANT)
        c += T.ldr_imm32(0, LA.ENGINE)
        c += T.bl(va + len(c), LA.PARAMPOST)
        L["noq"] = va + len(c)
    c += T.adds_imm(6, 5, 1)                # r6 = n + 1 (the pattern is no longer needed)
    for s in (1, 2, 3):
        c += T.ldrb_imm(0, 7, s)
        c += T.cmp_reg(0, 6)                 # slot_clip[k][s] == n + 1 ?
        c += T.b_cond_w(va + len(c), "ne", L.get("ns%d" % s, va))
        c += T.ldr_sp(0, 20)
        c += T.lsls_imm(0, 0, 1)
        c += T.ldr_imm32(1, table_va)
        c += T.add_reg(1, 0)
        c += T.ldrh_imm(2, 1, 0)
        c += T.ldr_imm32(1, LA.SESSION)
        c += T.add_reg(2, 1)                # record
        c += T.ldr_sp(0, 12)
        c += T.movs_imm8(1, s)
        c += T.ldr_sp(3, 16)
        c += T.bl(va + len(c), stream_va)
        L["ns%d" % s] = va + len(c)
    c += T.bw(va + len(c), L.get("out", va))
    L["plain"] = va + len(c)
    c = _call_stock(c, va, stock_va)
    L["out"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


# ---- v033 (sim finding): the piano roll and 7 other editor routines post single events with AddEvent
# 0x0804C798 / ClearSlot 0x0804C7E8 directly, not through SendPattern. Wrap both functions:
#   caller inside the mod (return address >= MOD_START): pass through (LAUNCH / STREAM stream on purpose);
#   target = host slot p >= 1 holding a streamed clip (slot_clip != 0): drop (I3);
#   otherwise post, then mirror the same op into every host slot s >= 1 that holds this record's clip.
ADD_SITE, ADD_ORIG, ADD_BACK = 0x0804C798, bytes.fromhex("10b58cb0"), 0x0804C79C   # push {r4,lr}; sub sp,#0x30
CLR_SITE, CLR_ORIG, CLR_BACK = 0x0804C7E8, bytes.fromhex("10b592b0"), 0x0804C7EC   # push {r4,lr}; sub sp,#0x48
MOD_START = fwbase.STOCK_END                 # end of the stock image: every mod cave lies above


def tramp_add(va, L):
    return ADD_ORIG + T.bw(va + 4, ADD_BACK)


def tramp_clr(va, L):
    return CLR_ORIG + T.bw(va + 4, CLR_BACK)


EFR = 28   # 20 pushed + 28 = 48. [sp] outgoing slot arg, [sp+8] r0, [sp+12] code, [sp+16] r2, [sp+20] r3, [sp+24] slot


def _post_orig(c, va, is_add, tramp_va, code_reg=None, slot_reg=None):
    """Call the original with the saved args; code/slot from registers if given. Uses r0-r3."""
    if slot_reg is None:
        c += T.ldr_sp(3, 24)
    else:
        c += T.mov_reg(3, slot_reg)
    if is_add:
        c += T.str_sp(3, 0)                  # [sp] = slot
        c += T.ldr_sp(3, 20)                 # r3 = original 4th arg
    c += T.ldr_sp(0, 8)
    if code_reg is None:
        c += T.ldr_sp(1, 12)
    else:
        c += T.mov_reg(1, code_reg)
    c += T.ldr_sp(2, 16)
    c += T.bl(va + len(c), tramp_va)
    return c


def evwrap(va, L, is_add, tramp_va, inv80_va, hosts_va):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(EFR)
    c += T.str_sp(0, 8)
    c += T.str_sp(1, 12)
    c += T.str_sp(2, 16)
    c += T.str_sp(3, 20)
    if is_add:
        c += T.ldr_sp(4, 48)                 # caller's [sp] = slot
        c += T.lsls_imm(4, 4, 16)
        c += T.lsrs_imm(4, 4, 16)
    else:
        c += T.mov_reg(4, 3)
    c += T.str_sp(4, 24)
    c += T.ldr_sp(4, 44)                     # return address
    c += T.ldr_imm32(5, MOD_START)
    c += T.cmp_reg(4, 5)
    c += T.b_cond_w(va + len(c), "cs", L.get("pass", va))
    c += T.lsrs_imm(4, 1, 16)
    c += T.cmp_imm(4, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("pass", va))
    c += T.lsls_imm(4, 1, 16)
    c += T.lsrs_imm(4, 4, 24)                # r4 = row
    c += T.lsls_imm(5, 1, 24)
    c += T.lsrs_imm(5, 5, 24)                # r5 = col
    c += T.ldr_sp(6, 24)                     # r6 = slot / pattern
    c += T.cmp_imm(4, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(5, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(6, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("pass", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 4)
    c += T.adds_reg(7, 0, 1)                 # r7 = &slot_clip[0][0]
    if is_add:                               # v036: a clip plays only the notes inside its Step Count
        c += T.movw(0, 0x370)
        c += T.muls(0, 4)
        c += T.movs_imm8(1, 0xB0)
        c += T.muls(1, 5)
        c += T.adds_reg(0, 0, 1)
        c += T.movs_imm8(1, 0x2C)
        c += T.muls(1, 6)
        c += T.adds_reg(0, 0, 1)
        c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
        c += T.adds_reg(0, 0, 1)             # record (row, col, pattern)
        c += T.movs_imm8(1, 0x86)
        c += T.bl(va + len(c), LA.GETPARAM)  # Step Count
        c += T.movw(1, 960)
        c += T.muls(0, 1)                    # limit = count * 960 (event ticks are step units)
        c += T.ldr_sp(1, 16)                 # event*
        c += T.ldr_imm(1, 1, 4)              # start tick
        c += T.cmp_reg(1, 0)
        c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    # host slot p >= 1 holding a streamed clip: drop (I3)
    c += T.cmp_imm(4, 1)
    c += T.b_cond(va + len(c), "hi", L.get("post", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond(va + len(c), "hi", L.get("post", va))
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "eq", L.get("post", va))
    c += T.lsls_imm(0, 4, 2)
    c += T.adds_reg(0, 0, 5)                 # host k = col + 4*row
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.add_reg(0, 7)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "ne", L.get("mirror", va))   # v034: drop the post, but still mirror
    L["post"] = va + len(c)
    c = _post_orig(c, va, is_add, tramp_va)
    # mirror into the host slots that hold this record's clip
    L["mirror"] = va + len(c)
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.ldr_imm32(1, inv80_va)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                 # kn
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 10)
    c += T.udiv(4, 0, 1)                     # r4 = k
    c += T.muls(1, 4)
    c += T.subs_reg(6, 0, 1)
    c += T.adds_imm8(6, 1)                   # r6 = n + 1
    c += T.lsls_imm(0, 4, 2)
    c += T.add_reg(7, 0)                     # r7 = &slot_clip[k][0]
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(4, 1, 0)                  # r4 = host code
    for sl in (1, 2, 3):
        c += T.ldrb_imm(0, 7, sl)
        c += T.cmp_reg(0, 6)
        c += T.b_cond_w(va + len(c), "ne", L.get("m%d" % sl, va))
        c += T.movs_imm8(5, sl)
        c = _post_orig(c, va, is_add, tramp_va, code_reg=4, slot_reg=5)
        L["m%d" % sl] = va + len(c)
    c += T.bw(va + len(c), L.get("out", va))
    L["pass"] = va + len(c)
    c = _post_orig(c, va, is_add, tramp_va)
    L["out"] = va + len(c)
    c += T.add_sp_imm(EFR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


# ---- v034: piano-roll playhead. The editor reads its cell's engine position via 0x08097860(out*, x,
# msg*{desc at +4}) -> 0x0804CA14(out*, engine, row*5+col). A streamed clip plays in its column's host,
# so when the asked cell is the selected L3 clip's cell (mod state +82) and that clip is what the column
# plays (COLSTATE play_n == sel_n), read the host's entry instead.
POS_SITE, POS_ORIG, POS_BACK = 0x08097860, bytes.fromhex("10b50446"), 0x08097864   # push {r4,lr}; mov r4,r0
POS_READ = 0x0804CA14


def posw(va, L, colstate_va, hosts_va):
    c = T.push_lo([4, 5, 6], lr=True)        # 16 B: sp 8-aligned at the bl
    c += T.mov_reg(4, 0)                     # r4 = out*
    c += T.ldrh_imm(3, 2, 4)                 # desc
    c += T.lsrs_imm(0, 3, 4)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(0, 1)
    c += T.movs_imm8(1, 5)
    c += T.muls(0, 1)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(1, 3)
    c += T.adds_reg(5, 0, 1)                 # r5 = idx = row*5 + col
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("read", va))
    c += T.ldr_imm32(1, LA.STATE_OFF)
    c += T.adds_reg(6, 0, 1)                 # r6 = mod state
    c += T.movs_imm8(0, 82)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_reg(0, 5)
    c += T.b_cond_w(va + len(c), "ne", L.get("read", va))
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)                 # k
    c += T.bl(va + len(c), colstate_va)      # refresh play_n (no calls inside; keeps r4-r7)
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(1, 0, 0)                 # k
    c += T.ldrb_imm(2, 0, 1)                 # sel_n
    c += T.lsls_imm(0, 1, 2)
    c += T.adds_imm8(0, 36)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)                 # play_n of column k
    c += T.cmp_reg(0, 2)
    c += T.b_cond_w(va + len(c), "ne", L.get("read", va))
    c += T.lsls_imm(0, 1, 3)
    c += T.ldr_imm32(2, hosts_va)
    c += T.add_reg(2, 0)
    c += T.ldr_imm(2, 2, 0)                  # host code 1<<16 | row<<8 | col
    c += T.lsls_imm(0, 2, 16)
    c += T.lsrs_imm(0, 0, 24)                # host row
    c += T.movs_imm8(1, 5)
    c += T.muls(0, 1)
    c += T.lsls_imm(1, 2, 24)
    c += T.lsrs_imm(1, 1, 24)                # host col
    c += T.adds_reg(5, 0, 1)                 # idx = host row*5 + col
    L["read"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.ldr_imm32(1, LA.ENGINE)
    c += T.mov_reg(2, 5)
    c += T.bl(va + len(c), POS_READ)
    c += T.mov_reg(0, 4)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


# ---- v034: piano-roll playhead, root cause. The piano roll's prepare 0x080C17E0 takes the playhead step
# from 0x08097838(x, msg*{desc}) = word 0 of the cell's engine position entry (setter 0x080BA420). POS2W
# replaces that function with the POSW redirect (selected clip playing on its host -> host entry).
POS2_SITE, POS2_ORIG = 0x08097838, bytes.fromhex("00b585b0")    # push {lr}; sub sp,#0x14


def pos2w(va, L, colstate_va, hosts_va):
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(16)                    # 16 + 16 = 32: [sp] 12-byte entry
    c += T.ldrh_imm(3, 1, 4)                 # desc
    c += T.lsrs_imm(0, 3, 4)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(0, 1)
    c += T.movs_imm8(1, 5)
    c += T.muls(0, 1)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(1, 3)
    c += T.adds_reg(5, 0, 1)                 # r5 = idx (stock computes the same, no range check)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("read", va))
    c += T.ldr_imm32(1, LA.STATE_OFF)
    c += T.adds_reg(6, 0, 1)
    c += T.movs_imm8(0, 82)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_reg(0, 5)
    c += T.b_cond_w(va + len(c), "ne", L.get("read", va))
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)
    c += T.bl(va + len(c), colstate_va)
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(1, 0, 0)                 # k
    c += T.ldrb_imm(2, 0, 1)                 # sel_n
    c += T.lsls_imm(0, 1, 2)
    c += T.adds_imm8(0, 36)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)                 # play_n
    c += T.cmp_reg(0, 2)
    c += T.b_cond_w(va + len(c), "ne", L.get("read", va))
    c += T.lsls_imm(0, 1, 3)
    c += T.ldr_imm32(2, hosts_va)
    c += T.add_reg(2, 0)
    c += T.ldr_imm(2, 2, 0)
    c += T.lsls_imm(0, 2, 16)
    c += T.lsrs_imm(0, 0, 24)
    c += T.movs_imm8(1, 5)
    c += T.muls(0, 1)
    c += T.lsls_imm(1, 2, 24)
    c += T.lsrs_imm(1, 1, 24)
    c += T.adds_reg(5, 0, 1)                 # host idx
    L["read"] = va + len(c)
    c += T.mov_reg(0, 13)
    c += T.ldr_imm32(1, LA.ENGINE)
    c += T.mov_reg(2, 5)
    c += T.bl(va + len(c), POS_READ)
    c += T.ldr_sp(0, 0)                      # step
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


# ---- v034: piano-roll playhead, part 2. The editor also reads the cell's UI play state
# 0x08099FEC(session, msg*) -> &session[0x8C68 + (row*5+col)*2] = {flag, pattern} (via 0x0809A3F0) and
# draws the playhead only when it says "playing this pattern". A streamed clip plays in its column's host, so
# for the selected clip's cell, while that clip is what the column plays, return a mod-owned
# {1, selected pattern} at mod state +84.
STATE_SITE, STATE_ORIG, STATE_BACK = 0x08099FEC, bytes.fromhex("02468b88"), 0x08099FF0   # mov r2,r0; ldrh r3,[r1,#4]
PLAY_ENTRY = 84


def tramp_state(va, L):
    return STATE_ORIG + T.bw(va + 4, STATE_BACK)


def statew(va, L, colstate_va, tramp_va):
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.ldrh_imm(3, 1, 4)
    c += T.lsrs_imm(0, 3, 8)
    c += T.movs_imm8(1, 0x1F)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    c += T.lsrs_imm(0, 3, 4)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("stock", va))
    c += T.movs_imm8(1, 5)
    c += T.muls(0, 1)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(1, 3)
    c += T.cmp_imm(1, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("stock", va))
    c += T.adds_reg(3, 0, 1)                 # idx
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("stock", va))
    c += T.ldr_imm32(1, LA.STATE_OFF)
    c += T.adds_reg(6, 0, 1)                 # r6 = mod state
    c += T.movs_imm8(0, 82)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_reg(0, 3)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)
    c += T.bl(va + len(c), colstate_va)
    c += T.movs_imm8(0, 80)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(1, 0, 0)                 # k
    c += T.ldrb_imm(2, 0, 1)                 # sel_n
    c += T.ldrb_imm(3, 0, 3)                 # selected pattern (+83)
    c += T.lsls_imm(0, 1, 2)
    c += T.adds_imm8(0, 36)
    c += T.add_reg(0, 6)
    c += T.ldrb_imm(0, 0, 0)                 # play_n
    c += T.cmp_reg(0, 2)
    c += T.b_cond_w(va + len(c), "ne", L.get("stock", va))
    c += T.movs_imm8(0, PLAY_ENTRY)
    c += T.add_reg(0, 6)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)                 # playing
    c += T.strb_imm(3, 0, 1)                 # this pattern
    c += T.pop_lo([4, 5, 6], pc=True)
    L["stock"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.bl(va + len(c), tramp_va)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


# ---- v035: per-pattern parameters. SetCellParam writes Step Len 0x85 / Step Count 0x86 into the edited
# record and posts them straight to the cell's own player with ParamPost 0x0804C59C(eng, code, id, value,
# [sp] arg5, [sp+4] slot), not via SendPattern (v034 hardware bug). PARAMW applies the ADDW rules to these
# ids (drop a post to a host slot holding another streamed clip, mirror into the host slots holding the
# edited clip) and sends duty 0x49 posted for a host also to every streamed slot (duty = instrument).
PP_SITE, PP_ORIG, PP_BACK = 0x0804C59C, bytes.fromhex("00b587b0"), 0x0804C5A0   # push {lr}; sub sp,#0x1c
PFR = 36   # 20 pushed + 36 = 56. [sp] out arg5, [sp+4] out slot, [sp+8] r0, [sp+12] code, [sp+16] id,
           # [sp+20] value, [sp+24] slot, [sp+28] arg5


def tramp_pp(va, L):
    return PP_ORIG + T.bw(va + 4, PP_BACK)


def _pp_post(c, va, tramp_va, code_reg=None, slot_reg=None):
    if slot_reg is None:
        c += T.ldr_sp(3, 24)
    else:
        c += T.mov_reg(3, slot_reg)
    c += T.str_sp(3, 4)
    c += T.ldr_sp(3, 28)
    c += T.str_sp(3, 0)
    c += T.ldr_sp(0, 8)
    if code_reg is None:
        c += T.ldr_sp(1, 12)
    else:
        c += T.mov_reg(1, code_reg)
    c += T.ldr_sp(2, 16)
    c += T.ldr_sp(3, 20)
    c += T.bl(va + len(c), tramp_va)
    return c


def paramwrap(va, L, tramp_va, inv80_va, hosts_va, restream_va=None, quant=False, duty_per_clip=False,
              quant_clip_inv80=None):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(PFR)
    c += T.str_sp(0, 8)
    c += T.str_sp(1, 12)
    c += T.str_sp(2, 16)
    c += T.str_sp(3, 20)
    c += T.ldr_sp(4, 56)
    c += T.str_sp(4, 28)                     # arg5
    c += T.ldr_sp(4, 60)
    c += T.lsls_imm(4, 4, 16)
    c += T.lsrs_imm(4, 4, 16)
    c += T.str_sp(4, 24)                     # slot
    c += T.ldr_sp(4, 52)                     # return address
    c += T.ldr_imm32(5, MOD_START)
    c += T.cmp_reg(4, 5)
    c += T.b_cond_w(va + len(c), "cs", L.get("pass", va))
    if quant and quant_clip_inv80 is not None:
        c = _quant_clip(c, va, L, tramp_va, hosts_va, quant_clip_inv80)
    elif quant:
        c = _quant(c, va, L, tramp_va, hosts_va)
    c += T.cmp_imm(2, 0x85)
    c += T.b_cond(va + len(c), "eq", L.get("dec", va))
    c += T.cmp_imm(2, 0x86)
    c += T.b_cond(va + len(c), "eq", L.get("dec", va))
    c += T.cmp_imm(2, 0x49)
    c += T.b_cond_w(va + len(c), "ne", L.get("pass", va))
    L["dec"] = va + len(c)
    c += T.lsrs_imm(4, 1, 16)
    c += T.cmp_imm(4, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("pass", va))
    c += T.lsls_imm(4, 1, 16)
    c += T.lsrs_imm(4, 4, 24)                # r4 = row
    c += T.lsls_imm(5, 1, 24)
    c += T.lsrs_imm(5, 5, 24)                # r5 = col
    c += T.ldr_sp(6, 24)                     # r6 = slot / pattern
    c += T.cmp_imm(4, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(5, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(6, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("pass", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 4)
    c += T.adds_reg(7, 0, 1)                 # r7 = &slot_clip[0][0]
    if not duty_per_clip:                    # v035-v040: Duty is the host's (instrument); v041: per clip -> steps
        c += T.ldr_sp(0, 16)
        c += T.cmp_imm(0, 0x49)
        c += T.b_cond_w(va + len(c), "ne", L.get("steps", va))
        # duty: a host cell's duty goes to its slot and to every streamed slot of that host
        c += T.cmp_imm(4, 1)
        c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
        c += T.cmp_imm(5, 3)
        c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
        c = _pp_post(c, va, tramp_va)
        c += T.lsls_imm(0, 4, 2)
        c += T.adds_reg(0, 0, 5)
        c += T.lsls_imm(0, 0, 2)
        c += T.add_reg(7, 0)                 # r7 = &slot_clip[k][0]
        for sl in (1, 2, 3):
            c += T.ldrb_imm(0, 7, sl)
            c += T.cmp_imm(0, 0)
            c += T.b_cond_w(va + len(c), "eq", L.get("d%d" % sl, va))
            c += T.movs_imm8(6, sl)
            c = _pp_post(c, va, tramp_va, slot_reg=6)
            L["d%d" % sl] = va + len(c)
        c += T.bw(va + len(c), L.get("out", va))
    # Step Len / Step Count: the ADDW rules
    L["steps"] = va + len(c)
    c += T.cmp_imm(4, 1)
    c += T.b_cond(va + len(c), "hi", L.get("post", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond(va + len(c), "hi", L.get("post", va))
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "eq", L.get("post", va))
    c += T.lsls_imm(0, 4, 2)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.add_reg(0, 7)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "ne", L.get("mirror", va))
    L["post"] = va + len(c)
    c = _pp_post(c, va, tramp_va)
    L["mirror"] = va + len(c)
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.ldr_imm32(1, inv80_va)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                 # kn
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 10)
    c += T.udiv(4, 0, 1)                     # r4 = k
    c += T.muls(1, 4)
    c += T.subs_reg(6, 0, 1)
    c += T.adds_imm8(6, 1)                   # r6 = n + 1
    c += T.lsls_imm(0, 4, 2)
    c += T.add_reg(7, 0)                     # r7 = &slot_clip[k][0]
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(4, 1, 0)                  # r4 = host code
    for sl in (1, 2, 3):
        c += T.ldrb_imm(0, 7, sl)
        c += T.cmp_reg(0, 6)
        c += T.b_cond_w(va + len(c), "ne", L.get("m%d" % sl, va))
        c += T.movs_imm8(5, sl)
        c = _pp_post(c, va, tramp_va, code_reg=4, slot_reg=5)
        L["m%d" % sl] = va + len(c)
    if restream_va is not None:              # v036: Step Count changed -> reload the filtered clip
        c += T.ldr_sp(0, 16)
        c += T.cmp_imm(0, 0x86)
        c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
        c += T.ldr_sp(3, 12)                 # code
        c += T.lsls_imm(0, 3, 16)
        c += T.lsrs_imm(0, 0, 24)            # row
        c += T.lsls_imm(1, 3, 24)
        c += T.lsrs_imm(1, 1, 24)            # col
        c += T.ldr_sp(2, 24)                 # pattern
        c += T.bl(va + len(c), restream_va)
    c += T.bw(va + len(c), L.get("out", va))
    L["pass"] = va + len(c)
    c = _pp_post(c, va, tramp_va)
    L["out"] = va + len(c)
    c += T.add_sp_imm(PFR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def _quant(c, va, L, tramp_va, hosts_va):
    """v037 per-clip Quant Size (0x46, a per-cell Seq-tab setting). The engine uses the playing player's quant, and
    an L3 clip plays in its column's host, so: a cell's Quant goes to every host whose last launched clip
    (qcell[k], mod state +96) is from this cell. The stock post to a host cell is dropped while that host plays a
    clip from another cell (the host's own value comes back when its own clip is launched)."""
    c += T.cmp_imm(2, LA.QUANT)
    c += T.b_cond_w(va + len(c), "ne", L.get("notq", va))
    c += T.lsrs_imm(4, 1, 16)
    c += T.cmp_imm(4, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("pass", va))
    c += T.lsls_imm(4, 1, 16)
    c += T.lsrs_imm(4, 4, 24)                # r4 = row
    c += T.lsls_imm(5, 1, 24)
    c += T.lsrs_imm(5, 5, 24)                # r5 = col
    c += T.cmp_imm(4, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(5, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("pass", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + LA.QCELL_OFF)
    c += T.adds_reg(7, 0, 1)                 # r7 = &qcell[0]
    c += T.movs_imm8(6, 5)
    c += T.muls(6, 4)
    c += T.adds_reg(6, 6, 5)
    c += T.adds_imm8(6, 1)                   # r6 = cell + 1
    c += T.cmp_imm(4, 1)                     # a host cell (rows 0-1, cols 0-3)?
    c += T.b_cond(va + len(c), "hi", L.get("qpost", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond(va + len(c), "hi", L.get("qpost", va))
    c += T.lsls_imm(0, 4, 2)
    c += T.adds_reg(0, 0, 5)                 # k of this host
    c += T.adds_reg(0, 0, 7)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("qpost", va))
    c += T.cmp_reg(0, 6)
    c += T.b_cond(va + len(c), "ne", L.get("qmir", va))
    L["qpost"] = va + len(c)
    c = _pp_post(c, va, tramp_va)
    L["qmir"] = va + len(c)
    c += T.movs_imm8(4, 0)
    L["qloop"] = va + len(c)
    c += T.adds_reg(0, 7, 4)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_reg(0, 6)
    c += T.b_cond(va + len(c), "ne", L.get("qnext", va))
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(5, 1, 0)                  # host code
    c += T.ldr_sp(0, 12)
    c += T.cmp_reg(5, 0)
    c += T.b_cond(va + len(c), "eq", L.get("qnext", va))
    c = _pp_post(c, va, tramp_va, code_reg=5)
    L["qnext"] = va + len(c)
    c += T.adds_imm8(4, 1)
    c += T.cmp_imm(4, 8)
    c += T.b_cond(va + len(c), "ne", L.get("qloop", va))
    c += T.bw(va + len(c), L.get("out", va))
    L["notq"] = va + len(c)
    c += T.ldr_sp(2, 16)                     # restore r2 = id
    return c


def _quant_clip(c, va, L, tramp_va, hosts_va, inv80_va):
    """v041 per-clip Quant (0x46): edited record = (code row/col, slot = its pattern). It is clip (k, n) via inv80.
    Post to H(k) when +96+k == n + 1 (that clip is the one launched in column k). The stock post to the cell's own
    player passes for a non-host cell; for a host cell only when nothing is launched in that column and the
    post is for pattern 0 (the host still plays its own pattern A)."""
    c += T.cmp_imm(2, LA.QUANT)
    c += T.b_cond_w(va + len(c), "ne", L.get("notq", va))
    c += T.lsrs_imm(4, 1, 16)
    c += T.cmp_imm(4, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("pass", va))
    c += T.lsls_imm(4, 1, 16)
    c += T.lsrs_imm(4, 4, 24)                # r4 = row
    c += T.lsls_imm(5, 1, 24)
    c += T.lsrs_imm(5, 5, 24)                # r5 = col
    c += T.cmp_imm(4, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.cmp_imm(5, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("pass", va))
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("pass", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + LA.QCELL_OFF)
    c += T.adds_reg(7, 0, 1)                 # r7 = &launched[0] (n + 1 per column)
    # host cell? (rows 0-1, cols 0-3): stock post only if nothing launched there and pattern 0
    c += T.cmp_imm(4, 1)
    c += T.b_cond(va + len(c), "hi", L.get("qpost", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond(va + len(c), "hi", L.get("qpost", va))
    c += T.lsls_imm(0, 4, 2)
    c += T.adds_reg(0, 0, 5)
    c += T.adds_reg(0, 0, 7)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("qmir", va))
    c += T.ldr_sp(0, 24)                     # pattern (slot argument)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("qmir", va))
    L["qpost"] = va + len(c)
    c = _pp_post(c, va, tramp_va)
    L["qmir"] = va + len(c)
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.ldr_sp(1, 24)
    c += T.cmp_imm(1, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.adds_reg(0, 0, 1)
    c += T.ldr_imm32(1, inv80_va)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                 # k*10 + n, or 0xFF
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 10)
    c += T.udiv(4, 0, 1)                     # r4 = k
    c += T.muls(1, 4)
    c += T.subs_reg(6, 0, 1)
    c += T.adds_imm8(6, 1)                   # r6 = n + 1
    c += T.adds_reg(0, 7, 4)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_reg(0, 6)
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(5, 1, 0)                  # host code
    # A host cell's stock post was dropped whenever something is launched there (branch to qmir), so the
    # launched clip's value always needs this post; when nothing is launched, +96+k == n + 1 cannot hold.
    c = _pp_post(c, va, tramp_va, code_reg=5)
    c += T.bw(va + len(c), L.get("out", va))
    L["notq"] = va + len(c)
    c += T.ldr_sp(2, 16)
    return c


# ---- v036: reload a record into every host slot that holds it (after a Step Count change), so the notes
# inside the new count play: host slot 0 if the record is the host cell's own pattern 0 (I1), and every slot
# s >= 1 whose slot_clip says it holds this record's clip (I3). STREAM filters by Step Count.
def restream(va, L, stream_va, inv80_va, table_va, hosts_va):
    """(r0 row, r1 col, r2 pattern). Uses the record's own params; duty from the host."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(12)                    # 20 + 12 = 32: [sp] record, [sp+4] host code, [sp+8] host record
    c += T.mov_reg(4, 0)
    c += T.mov_reg(5, 1)
    c += T.mov_reg(6, 2)
    c += T.movw(0, 0x370)
    c += T.muls(0, 4)
    c += T.movs_imm8(1, 0xB0)
    c += T.muls(1, 5)
    c += T.adds_reg(0, 0, 1)
    c += T.movs_imm8(1, 0x2C)
    c += T.muls(1, 6)
    c += T.adds_reg(0, 0, 1)
    c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
    c += T.adds_reg(0, 0, 1)
    c += T.str_sp(0, 0)                      # record
    # the host cell's own pattern 0 lives in host slot 0
    c += T.cmp_imm(4, 1)
    c += T.b_cond(va + len(c), "hi", L.get("ring", va))
    c += T.cmp_imm(5, 3)
    c += T.b_cond(va + len(c), "hi", L.get("ring", va))
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "ne", L.get("ring", va))
    c += T.lsls_imm(0, 4, 8)
    c += T.orrs_reg(0, 5)
    c += T.movs_imm8(1, 1)
    c += T.lsls_imm(1, 1, 16)
    c += T.orrs_reg(0, 1)                    # code 1<<16 | row<<8 | col
    c += T.movs_imm8(1, 0)
    c += T.ldr_sp(2, 0)
    c += T.ldr_sp(3, 0)
    c += T.bl(va + len(c), stream_va)
    L["ring"] = va + len(c)
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(0, 0, 6)
    c += T.ldr_imm32(1, inv80_va)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(0, 1, 0)                 # kn
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 10)
    c += T.udiv(4, 0, 1)                     # k
    c += T.muls(1, 4)
    c += T.subs_reg(6, 0, 1)
    c += T.adds_imm8(6, 1)                   # n + 1
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 4)
    c += T.adds_reg(7, 0, 1)
    c += T.lsls_imm(1, 4, 2)
    c += T.add_reg(7, 1)                     # &slot_clip[k][0]
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(0, 1, 0)
    c += T.str_sp(0, 4)                      # host code
    c += T.ldr_imm(0, 1, 4)
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.add_reg(0, 1)
    c += T.str_sp(0, 8)                      # host pattern-0 record
    for sl in (1, 2, 3):
        c += T.ldrb_imm(0, 7, sl)
        c += T.cmp_reg(0, 6)
        c += T.b_cond_w(va + len(c), "ne", L.get("r%d" % sl, va))
        c += T.ldr_sp(0, 4)
        c += T.movs_imm8(1, sl)
        c += T.ldr_sp(2, 0)
        c += T.ldr_sp(3, 8)
        c += T.bl(va + len(c), stream_va)
        L["r%d" % sl] = va + len(c)
    L["out"] = va + len(c)
    c += T.add_sp_imm(12)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
