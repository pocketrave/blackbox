"""v044 (bug in v042): PADS/KEYS/MIDI mode set to MIDI on a clip of columns 1-4 still played the pad sound.
Mode 0xB7 (and Play Pad 0xB8/0xB9, MIDI out channel 0x6B / MIDI-mode channel 0x7A) are per PLAYER: SetCellParam
writes them to the clip's own cell (sub 0) and that cell's player, but the clip plays in its column's host player
H(k) (in the simulator: cell (3,0) +0x59 changed, host (0,0) did not). These are instrument (column) settings.

CPW replaces the user-edit call of SetCellParam in the command handler (0x080A1BE6, msg 0x6E): it runs the stock
SetCellParam, then, when the id is a column id and the edited cell is the selected L3 clip's cell (mod state +82)
but not its column's host cell, writes the same value into the host cell's pattern-0 record (SetParam) and posts it
to the host (ParamPost). After a mode change it also copies the edited cell's channels (0x7A, 0x6B) to the host, in
that order (the MIDI node re-sends the player's channel from its stored 0x7A / 0x6B after a 0xB7 post).
Step Mode 0x88 is not mirrored (it re-times events; the column page handles it)."""
import thumb as T
import phase5 as P5
import launch as LA

SCP = 0x0809FA50                            # SetCellParam(S, msg{+4 u16 desc}, id, value)
CPW_SITE = 0x080A1BE6                       # its call in the command handler 0x080A1718 (msg 0x6E)
COL_IDS = (0xB7, 0xB8, 0xB9, 0x6B, 0x7A)
CHAN_IDS = (0x7A, 0x6B)
SEL_OFF, SELCELL_OFF = 80, 82


def cpw(va, L, hosts_va):
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(28)                    # [sp] arg5, [sp+4] slot, [sp+8] host rec0, [sp+12] host code,
    c += T.str_sp(1, 16)                     # [sp+16] msg, [sp+20] id, [sp+24] value
    c += T.str_sp(2, 20)
    c += T.str_sp(3, 24)
    c += T.bl(va + len(c), SCP)
    c += T.mov_reg(7, 0)                     # keep SetCellParam's return value
    # a column id?
    c += T.ldr_sp(0, 20)
    for pid in COL_IDS:
        c += T.cmp_imm(0, pid)
        c += T.b_cond(va + len(c), "eq", L.get("col", va))
    c += T.bw(va + len(c), L.get("out", va))
    L["col"] = va + len(c)
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + SEL_OFF)
    c += T.add_reg(4, 0)                     # r4 = &sel
    # the edited cell = the selected clip's cell?
    c += T.ldr_sp(0, 16)
    c += T.ldrh_imm(0, 0, 4)                 # desc kind<<8 | row<<4 | col
    c += T.lsrs_imm(1, 0, 4)
    c += T.movs_imm8(2, 0xF)
    c += T.ands_reg(1, 2)                    # row
    c += T.ands_reg(0, 2)                    # col
    c += T.movs_imm8(2, 5)
    c += T.muls(2, 1)
    c += T.adds_reg(2, 2, 0)                 # row*5 + col
    c += T.ldrb_imm(3, 4, SELCELL_OFF - SEL_OFF)
    c += T.cmp_reg(2, 3)
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    # host of the selected column; skip when the edited cell IS the host (stock already posted there)
    c += T.ldrb_imm(5, 4, 0)                 # sel_k
    c += T.cmp_imm(5, 7)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.lsls_imm(5, 5, 3)
    c += T.ldr_imm32(0, hosts_va)
    c += T.add_reg(5, 0)                     # r5 = &hosts[k] {code, rec0 offset}
    c += T.ldr_imm(0, 5, 0)
    c += T.str_sp(0, 12)                     # host code
    c += T.lsls_imm(1, 0, 16)
    c += T.lsrs_imm(1, 1, 24)                # host row
    c += T.lsls_imm(3, 0, 24)
    c += T.lsrs_imm(3, 3, 24)                # host col
    c += T.movs_imm8(6, 5)
    c += T.muls(6, 1)
    c += T.adds_reg(6, 6, 3)
    c += T.cmp_reg(6, 2)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm(0, 5, 4)
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.add_reg(0, 1)
    c += T.str_sp(0, 8)                      # host pattern-0 record
    c += T.mov_reg(6, 2)                     # r6 = edited cell index (for the channel copy)
    c += T.ldr_sp(5, 20)                     # r5 = id
    c += T.ldr_sp(3, 24)                     # value
    c = _host(c, va, 5, 3)
    # after a mode change: the edited cell's channels follow (0x7A first, then 0x6B)
    c += T.cmp_imm(5, 0xB7)
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    for ch in CHAN_IDS:
        c += T.ldr_sp(0, 16)
        c += T.ldrh_imm(0, 0, 4)
        c += T.lsrs_imm(1, 0, 4)
        c += T.movs_imm8(2, 0xF)
        c += T.ands_reg(1, 2)
        c += T.ands_reg(0, 2)
        c += T.movw(2, 0x370)
        c += T.muls(1, 2)
        c += T.movs_imm8(2, 0xB0)
        c += T.muls(0, 2)
        c += T.adds_reg(0, 0, 1)
        c += T.ldr_imm32(1, LA.SESSION + 0x1C00)
        c += T.adds_reg(0, 0, 1)             # the edited cell's pattern-0 record
        c += T.movs_imm8(1, ch)
        c += T.bl(va + len(c), LA.GETPARAM)
        c += T.mov_reg(3, 0)
        c += T.movs_imm8(5, ch)
        c = _host(c, va, 5, 3)
    L["out"] = va + len(c)
    c += T.mov_reg(0, 7)
    c += T.add_sp_imm(28)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def _host(c, va, id_reg, val_reg):
    """SetParam([sp+8] host rec0, id, value) + ParamPost(ENGINE, [sp+12] host code, id, value, 0, 0).
    id in r<id_reg> (r4-r7, kept), value in r<val_reg> (r3, clobbered). Clobbers r0-r3."""
    c += T.str_sp(val_reg, 24)               # value (reused for the post)
    c += T.mov_reg(2, val_reg)
    c += T.mov_reg(1, id_reg)
    c += T.ldr_sp(0, 8)
    c += T.bl(va + len(c), LA.SETPARAM)
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 0)
    c += T.str_sp(0, 4)
    c += T.ldr_sp(3, 24)
    c += T.mov_reg(2, id_reg)
    c += T.ldr_sp(1, 12)
    c += T.ldr_imm32(0, LA.ENGINE)
    c += T.bl(va + len(c), LA.PARAMPOST)
    return c
