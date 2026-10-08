"""v063: MIDI CC with Learn controls the per-pad FX sends (DLY 0xD9 / RVB 0xDA) - no engine change.

The stock MOD page of a send row (the FX pad page, INFO on "DLY amount" / "RVB amount") stores mods like any other
param: 12-B entries {s32 amount -1000..1000, u16 src, u16 dest, s16 slot} in the pad's list (S + 0x1840 +
row * 0xF0 + col * 0x30: +0x10 list, +0x14 u16 count). Learn stores src = 0x8000 | channel << 7 | controller and
amount 1000. The engine has no mod target for the sends, so the mod itself does nothing; this module applies it:

- MODDESC (boot, registrar epilogue): descriptor SRC_ID = a kind-5 enum "Source:" {none, CC} (stock strings).
- MODBUILD (MOD page build, b.w at BUILD_SITE): for dest 0xD9 / 0xDA the Source row is SRC_ID with index 1 for a
  CC src (>= 0x8000), else 0. Other dests: stock rows.
- MODEDIT (MOD page edit, b.w at EDIT_SITE): row SRC_ID -> src 0 / 0x8000, then the stock AddMod tail.
- LEARNEN (b.w at LEARN_SITE in 0x080B76C4): the stock enables the Learn button only for rows 0x53 / 0x54; SRC_ID
  too. Learn then sets channel and controller as usual.
- CCIN (audioTask, b.w at the MIDI node's CC handler entry 0x0804FACC): the event value is in the 14-bit scale
  0..16383 (the stock handler divides it by 16383; v063 read it as 0..127 - any CC >= 1 gave the maximum), so CCIN
  keeps value >> 7. Every CC (controller <= 119, channel <= 15) goes into mbox[8] (descriptor slot 0x1F2): word = 0x80000000 | (channel << 7 | controller) << 8 | value. The slot
  with the same controller is overwritten (the last value wins), else the first free slot; a full mailbox drops it.
  Then the stock handler runs (stock CC mod sources keep working).
- FXMODCC (defaultTask, C3 chain before FILLSYNC): take each mailbox word (LDREX / STREX, retry when a CC came in
  between) and CCAPPLY it: every pad mod with dest 0xD9 / 0xDA and src == 0x8000 | key sets the send with
  SetCellParam (stored in the cell, saved with the preset, shown by the FX page, posted to the engine):
  amount A >= 0: value = (v * A + 63) / 127 (0..A); A < 0: value = ((127 - v) * -A + 63) / 127 (inverted)."""
import struct

import thumb as T

SRC_ID = 0x19C                                   # a free descriptor slot (highest stock id 0x19B)
DESC = 28
DESCP = 0x2401F4FC
LABEL_SRC = 0x080CC018                           # "Source:" (stock, the label of 0x53 / 0x54)
STR_NONE, STR_CC = 0x080CEA68, 0x080CEA90        # "none", "CC" (stock source names)
SESSION = 0x24020088
SCP = 0x0809FA50                                 # SetCellParam(S, msg{+4 u16 code}, id, value, [sp] 0)
ADDROW = 0x080A5038                              # AddRow(rows, id, value)
MODS0, ROW_STRIDE, COL_STRIDE = 0x1840, 0xF0, 0x30   # pad mod container = S + MODS0 + row * 0xF0 + col * 0x30
LIST_OFF, COUNT_OFF, ENT_SZ = 0x10, 0x14, 12
ID_FX1, ID_FX2 = 0xD9, 0xDA
CC_SRC = 0x8000
NPAD = 16

BUILD_SITE, BUILD_ORIG = 0x080B797A, bytes.fromhex("b7f80480")   # ldrh.w r8,[r7,#4]  (src of the slot's mod)
BUILD_BACK, BUILD_DONE = 0x080B797E, 0x080B7918                  # stock search / after the Source AddRow
EDIT_SITE, EDIT_ORIG = 0x0809A5F6, bytes.fromhex("523b032b")     # subs r3,#0x52 ; cmp r3,#3  (row switch)
EDIT_BACK, EDIT_DONE = 0x0809A5FA, 0x0809A60E                    # the stock bhi / the AddMod tail

LEARN_SITE, LEARN_ORIG = 0x080B76EC, bytes.fromhex("542814bf")  # cmp r0,#0x54 ; ite ne  (Learn enable)
LEARN_BACK = 0x080B76DC                                           # set the Learn button state from r1
CC_SITE, CC_ORIG = 0x0804FACC, bytes.fromhex("90f8b132")         # ldrb.w r3,[r0,#0x2b1]  (CC handler entry)
CC_BACK = CC_SITE + 4
MBOX_OFF, NSLOT = 0x1F2 * DESC, 8                # 32 B in the free descriptor slot 0x1F2 (0x1F1 = FX labels)
PENDING = 0x80000000
CC_MAX, CH_MAX, V_MAX = 119, 15, 127
VAL_SHIFT = 7                                    # event value 0..16383 (v1: 7-bit CC << 7) -> top 7 bits
CLREX = bytes.fromhex("bff32f8f")


# ---------------------------------------------------------------- reference model
def src_of(ch, cc):
    return CC_SRC | (ch << 7) | cc


def mbox_word(ch, cc, v):
    return PENDING | (((ch << 7) | cc) << 8) | min(v, V_MAX)


def send_value(amount, v):
    if amount < 0:
        return ((V_MAX - v) * -amount + 63) // V_MAX
    return (v * amount + 63) // V_MAX


# ---------------------------------------------------------------- data
def table():
    return struct.pack("<II", STR_NONE, STR_CC)


def desc_blob(table_va):
    """{id, kind 5, label, table, count 2, min 0, max 1, tag 0} (tag 0: never serialized)."""
    return struct.pack("<HBBIIIiiI", SRC_ID, 5, 0, LABEL_SRC, table_va, 2, 0, 1, 0)


# ---------------------------------------------------------------- caves
def moddesc(va, L, tmpl_va):
    """bl from the registrar epilogue: copy the template into descriptor SRC_ID. r0-r3 only."""
    c = T.ldr_imm32(2, DESCP)
    c += T.ldr_imm(2, 2, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, SRC_ID * DESC)
    c += T.add_reg(2, 0)
    c += T.ldr_imm32(1, tmpl_va)
    for o in range(0, DESC, 4):
        c += T.ldr_imm(0, 1, o)
        c += T.str_imm(0, 2, o)
    L["out"] = va + len(c)
    c += T.bx(14)
    return c


def modbuild(va, L):
    """b.w from BUILD_SITE (r4 = page + 0x9000, r7 = GetMod output, sp = the build frame)."""
    c = BUILD_ORIG                               # r8 = src
    c += T.ldrh_w(2, 4, 0xE50)                   # the page's dest
    c += T.cmp_imm(2, ID_FX1)
    c += T.b_cond(va + len(c), "eq", L.get("mine", va))
    c += T.cmp_imm(2, ID_FX2)
    c += T.b_cond(va + len(c), "eq", L.get("mine", va))
    c += T.bw(va + len(c), BUILD_BACK)
    L["mine"] = va + len(c)
    c += T.mov_reg(2, 8)
    c += T.lsrs_imm(2, 2, 15)                    # 1 = CC
    c += T.movw(1, SRC_ID)
    c += T.add_rd_sp(0, 0x318)
    c += T.bl(va + len(c), ADDROW)
    c += T.bw(va + len(c), BUILD_DONE)
    return c


def modedit(va, L):
    """b.w from EDIT_SITE (r3 = row, r2 = value; r0, r1 free): row SRC_ID -> src [sp+0x18]; else stock."""
    c = T.movw(0, SRC_ID)
    c += T.cmp_reg(3, 0)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.movs_imm8(0, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("st", va))
    c += T.movw(0, CC_SRC)
    L["st"] = va + len(c)
    c += T.add_rd_sp(1, 0x18)
    c += T.strh_imm(0, 1, 0)
    c += T.bw(va + len(c), EDIT_DONE)
    L["stock"] = va + len(c)
    c += EDIT_ORIG
    c += T.bw(va + len(c), EDIT_BACK)
    return c


def learnen(va, L):
    """b.w from LEARN_SITE (r0 = the selected row id; the 0x53 case is handled before): r1 = 1 for the Source rows
    0x54 and SRC_ID, else 0; then the stock button update."""
    c = T.cmp_imm(0, 0x54)
    c += T.b_cond(va + len(c), "eq", L.get("on", va))
    c += T.movw(1, SRC_ID)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("on", va))
    c += T.movs_imm8(1, 0)
    c += T.bw(va + len(c), LEARN_BACK)
    L["on"] = va + len(c)
    c += T.movs_imm8(1, 1)
    c += T.bw(va + len(c), LEARN_BACK)
    return c


def ccin(va, L):
    """b.w from CC_SITE (r0 node, r1 event {+8 channel, +0xC controller, +0x10 value}). Keeps r0-r2; r3 is
    reloaded by the displaced instruction."""
    c = T.push_lo([0, 1, 2, 4, 5, 6, 7])
    c += T.ldr_imm(3, 1, 0xC)                    # controller
    c += T.cmp_imm(3, CC_MAX)
    c += T.b_cond(va + len(c), "hi", L.get("pop", va))
    c += T.ldr_imm(2, 1, 8)                      # channel
    c += T.cmp_imm(2, CH_MAX)
    c += T.b_cond(va + len(c), "hi", L.get("pop", va))
    c += T.lsls_imm(2, 2, 7)
    c += T.orrs_reg(2, 3)
    c += T.lsls_imm(7, 2, 8)                     # key << 8
    c += T.ldr_imm(3, 1, 0x10)                   # value, 14-bit scale 0..16383 (stock: / 16383)
    c += T.lsrs_imm(3, 3, VAL_SHIFT)             # -> 0..127
    c += T.cmp_imm(3, V_MAX)
    c += T.b_cond(va + len(c), "ls", L.get("v", va))
    c += T.movs_imm8(3, V_MAX)
    L["v"] = va + len(c)
    c += T.orrs_reg(7, 3)
    c += T.movs_imm8(3, 1)
    c += T.lsls_imm(3, 3, 31)
    c += T.orrs_reg(7, 3)                        # r7 = the new word
    c += T.lsls_imm(6, 7, 1)
    c += T.lsrs_imm(6, 6, 9)                     # r6 = key
    c += T.ldr_imm32(4, DESCP)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("pop", va))
    c += T.ldr_imm32(0, MBOX_OFF)
    c += T.add_reg(4, 0)                         # r4 = mailbox
    c += T.movs_imm8(5, 0)                       # first free slot
    c += T.movs_imm8(2, 0)                       # offset
    L["loop"] = va + len(c)
    c += T.adds_reg(1, 4, 2)
    c += T.ldr_imm(0, 1, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("used", va))
    c += T.cmp_imm(5, 0)
    c += T.b_cond(va + len(c), "ne", L.get("next", va))
    c += T.mov_reg(5, 1)
    c += T.b_short(va + len(c), L.get("next", va))
    L["used"] = va + len(c)
    c += T.lsls_imm(3, 0, 1)
    c += T.lsrs_imm(3, 3, 9)
    c += T.cmp_reg(3, 6)
    c += T.b_cond(va + len(c), "ne", L.get("next", va))
    c += T.str_imm(7, 1, 0)                      # same controller: the last value wins
    c += T.b_short(va + len(c), L.get("pop", va))
    L["next"] = va + len(c)
    c += T.adds_imm8(2, 4)
    c += T.cmp_imm(2, 4 * NSLOT)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    c += T.cmp_imm(5, 0)
    c += T.b_cond(va + len(c), "eq", L.get("pop", va))
    c += T.str_imm(7, 5, 0)
    L["pop"] = va + len(c)
    c += T.pop_lo([0, 1, 2, 4, 5, 6, 7])
    c += CC_ORIG
    c += T.bw(va + len(c), CC_BACK)
    return c


def ccapply(va, L):
    """(r0 = mailbox word): SetCellParam for every pad mod of a send dest with this CC as src. AAPCS."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(36)                        # 56 B: [sp] arg 5 = 0, [sp+4] dest, msg at sp+8 (24 B)
    c += T.mov_reg(4, 0)
    c += T.movs_imm8(1, 0)
    for o in range(0, 32, 4):
        c += T.str_sp(1, o)
    c += T.movs_imm8(5, 0)                       # pad 0..15 = row * 4 + col
    L["pad"] = va + len(c)
    c += T.lsrs_imm(1, 5, 2)
    c += T.movs_imm8(2, ROW_STRIDE)
    c += T.muls(1, 2)
    c += T.movs_imm8(2, 3)
    c += T.ands_reg(2, 5)
    c += T.movs_imm8(3, COL_STRIDE)
    c += T.muls(2, 3)
    c += T.adds_reg(1, 1, 2)
    c += T.ldr_imm32(0, SESSION + MODS0)
    c += T.add_reg(0, 1)                         # the pad's mod container
    c += T.ldr_imm(6, 0, LIST_OFF)
    c += T.ldrh_imm(7, 0, COUNT_OFF)
    L["ent"] = va + len(c)
    c += T.cmp_imm(7, 0)
    c += T.b_cond(va + len(c), "eq", L.get("padnext", va))
    c += T.ldrh_imm(0, 6, 4)                     # src
    c += T.lsls_imm(1, 4, 1)
    c += T.lsrs_imm(1, 1, 9)
    c += T.movw(2, CC_SRC)
    c += T.orrs_reg(1, 2)                        # 0x8000 | key
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "ne", L.get("entnext", va))
    c += T.ldrh_imm(0, 6, 6)                     # dest
    c += T.cmp_imm(0, ID_FX1)
    c += T.b_cond(va + len(c), "eq", L.get("hit", va))
    c += T.cmp_imm(0, ID_FX2)
    c += T.b_cond(va + len(c), "ne", L.get("entnext", va))
    L["hit"] = va + len(c)
    c += T.str_sp(0, 4)
    c += T.ldr_imm(1, 6, 0)                      # amount
    c += T.lsls_imm(2, 4, 25)
    c += T.lsrs_imm(2, 2, 25)                    # v
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ge", L.get("pos", va))
    c += T.negs(1, 1)
    c += T.movs_imm8(3, V_MAX)
    c += T.subs_reg(2, 3, 2)
    L["pos"] = va + len(c)
    c += T.muls(2, 1)
    c += T.adds_imm8(2, 63)
    c += T.movs_imm8(3, V_MAX)
    c += T.udiv(3, 2, 3)                         # value
    c += T.lsrs_imm(0, 5, 2)
    c += T.lsls_imm(0, 0, 4)
    c += T.movs_imm8(1, 3)
    c += T.ands_reg(1, 5)
    c += T.orrs_reg(0, 1)                        # code = row << 4 | col
    c += T.add_rd_sp(1, 8)
    c += T.strh_imm(0, 1, 4)
    c += T.ldr_sp(2, 4)
    c += T.ldr_imm32(0, SESSION)
    c += T.bl(va + len(c), SCP)
    L["entnext"] = va + len(c)
    c += T.adds_imm8(6, ENT_SZ)
    c += T.subs_imm8(7, 1)
    c += T.b_short(va + len(c), L.get("ent", va))
    L["padnext"] = va + len(c)
    c += T.adds_imm8(5, 1)
    c += T.cmp_imm(5, NPAD)
    c += T.b_cond(va + len(c), "ne", L.get("pad", va))
    c += T.add_sp_imm(36)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def fxmodcc(va, L, va_apply, next_va):
    """defaultTask pass (called by C3 where FILLSYNC was): apply the pending CCs, then tail-call next_va."""
    c = T.push_lo([4, 5, 6], lr=True)            # lr at sp+12
    c += T.ldr_imm32(4, DESCP)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, MBOX_OFF)
    c += T.add_reg(4, 0)                         # r4 = mailbox
    c += T.movs_imm8(5, 0)
    L["loop"] = va + len(c)
    c += T.adds_reg(6, 4, 5)
    L["take"] = va + len(c)
    c += T.ldrex(0, 6)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("clrex", va))
    c += T.movs_imm8(1, 0)
    c += T.strex(2, 1, 6)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("take", va))   # a CC came in between: take it again
    c += T.bl(va + len(c), va_apply)
    c += T.b_short(va + len(c), L.get("next", va))
    L["clrex"] = va + len(c)
    c += CLREX
    L["next"] = va + len(c)
    c += T.adds_imm8(5, 4)
    c += T.cmp_imm(5, 4 * NSLOT)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    L["out"] = va + len(c)
    c += T.ldr_sp(0, 12)
    c += T.mov_reg(14, 0)
    c += T.pop_lo([4, 5, 6])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), next_va)
    return c
