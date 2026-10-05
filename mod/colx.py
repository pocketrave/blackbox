"""Step 7 (v005): one enabled cell per column on the SEQS grid.

The SEQS grid touch posts event 0xFA; the command handler 0x080A1718 answers
it at 0x080A1A96 with ToggleCellPlay(this, msg). This cave runs first. If the
touched cell is stopped (it is about to be launched), every other enabled cell
in the same column is disabled exactly as ToggleCellPlay disables one:

    SetParam(owner, 0xBE, 0); Notify(0x2400A9C0, 1<<16 | row<<8 | col, 0, 0);
    [this+0x8CC4] = 1

SelectSeqCell is deliberately skipped for those cells (it may launch when
[this+0x8CC1] == 1 and it would move the selection). Then the stock
ToggleCellPlay runs for the touched cell. The engine quantizes all of these
messages the same way, so there is no timing logic here.
"""
import thumb as T

SITE = 0x080A1A96                          # event 0xFA case in 0x080A1718
SITE_ORIG = bytes.fromhex("03a9f6f79afc")  # add r1,sp,#0xc ; bl ToggleCellPlay
BACK = 0x080A1A9C                          # b 0x080A1A50 (shared handler exit)
TOGGLE = 0x080983D0                        # ToggleCellPlay(this, msg*)
RESOLVE = 0x08097CE8                       # ResolveSequenceCell(this, msg*, sub)
GETPARAM = 0x08093E9C
SETPARAM = 0x08093ECC
NOTIFY = 0x0804C87C                        # engine notify(engine, code, 0, enabled)
ENGINE = 0x2400A9C0
MSG_VT = 0x080EAF38                        # first word of the stock msg struct
DIRTY_OFF = 0x8CC4                         # this+0x8CC4 = grid needs refresh
P_PLAY = 0xBE                              # seqplayenable
SETCELLPARAM = 0x0809FA50                  # (this, msg*, id, value, [sp]=0): stock A-D path
SELECT = 0x08098328                        # SelectSeqCell(this, msg*)
P_LAYER = 0xC0
ROOT_PTR = 0x24002E6C
TOP_FROM_ROOT = 0x39F90 + 0x1AEC


def cave(va, L):
    c = b""
    c += SITE_ORIG[:2]                     # add r1, sp, #0xc   (msg*, before our push)
    c += T.push_lo([4, 5, 6, 7])           # 16 B
    c += T.sub_sp_imm(16)                  # [sp] vt, [sp+4] desc_i, [sp+8] owner; frame 32 B
    c += T.mov_reg(4, 0)                   # r4 = this
    c += T.mov_reg(5, 1)                   # r5 = msg*
    c += T.ldrh_imm(6, 5, 4)               # r6 = touched desc
    c += T.lsrs_imm(3, 6, 8)
    c += T.cmp_imm(3, 1)                   # sequence layer only
    c += T.b_cond(va + len(c), "ne", L.get("done", va))
    # --- v006: the touched widget shows sub = (top + ((row - top) & 3)) >> 2
    c += T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("excl", va))
    c += T.ldr_imm32(3, TOP_FROM_ROOT)
    c += T.add_reg(3, 0)
    c += T.ldr_imm(3, 3)                   # top
    c += T.lsrs_imm(2, 6, 4)
    c += T.movs_imm8(1, 0xF)
    c += T.ands_reg(2, 1)                  # row
    c += T.subs_reg(2, 2, 3)
    c += T.movs_imm8(1, 3)
    c += T.ands_reg(2, 1)                  # v
    c += T.adds_reg(2, 2, 3)
    c += T.lsrs_imm(7, 2, 2)               # r7 = sub
    c += T.movs_imm8(2, 0)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), RESOLVE)
    c += T.movs_imm8(1, P_LAYER)
    c += T.bl(va + len(c), GETPARAM)
    c += T.cmp_reg(0, 7)
    c += T.b_cond(va + len(c), "eq", L.get("excl", va))
    c += T.movs_imm8(3, 0)
    c += T.str_sp(3, 0)                    # 5th arg = 0
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.movs_imm8(2, P_LAYER)
    c += T.mov_reg(3, 7)
    c += T.bl(va + len(c), SETCELLPARAM)
    c += T.movs_imm8(2, 0)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), RESOLVE)
    c += T.movs_imm8(1, P_PLAY)
    c += T.bl(va + len(c), GETPARAM)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("excl", va))
    # playing instrument: variation switch only (stock timing), select it, no toggle
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6, 7])
    c += T.bl(va + len(c), SELECT)
    c += T.bw(va + len(c), BACK)
    L["excl"] = va + len(c)
    c += T.movs_imm8(2, 0)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), RESOLVE)
    c += T.movs_imm8(1, P_PLAY)
    c += T.bl(va + len(c), GETPARAM)
    c += T.cmp_imm(0, 0)                   # already enabled: this touch stops it
    c += T.b_cond(va + len(c), "ne", L.get("done", va))
    c += T.ldr_imm32(3, MSG_VT)
    c += T.str_sp(3, 0)
    c += T.movs_imm8(7, 0)                 # r7 = physRow 0..3
    L["loop"] = va + len(c)
    c += T.lsls_imm(3, 6, 28)
    c += T.lsrs_imm(3, 3, 28)              # r3 = col
    c += T.lsls_imm(2, 7, 4)
    c += T.orrs_reg(3, 2)
    c += T.movs_imm8(2, 1)
    c += T.lsls_imm(2, 2, 8)
    c += T.orrs_reg(3, 2)                  # r3 = 0x100 | row<<4 | col
    c += T.cmp_reg(3, 6)
    c += T.b_cond(va + len(c), "eq", L.get("next", va))
    c += T.mov_reg(2, 13)                  # r2 = sp
    c += T.strh_imm(3, 2, 4)               # [sp+4] = desc_i
    c += T.mov_reg(1, 13)
    c += T.movs_imm8(2, 0)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), RESOLVE)
    c += T.str_sp(0, 8)                    # owner
    c += T.movs_imm8(1, P_PLAY)
    c += T.bl(va + len(c), GETPARAM)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("next", va))
    c += T.ldr_sp(0, 8)
    c += T.movs_imm8(1, P_PLAY)
    c += T.movs_imm8(2, 0)
    c += T.bl(va + len(c), SETPARAM)
    c += T.lsls_imm(1, 7, 8)
    c += T.lsls_imm(3, 6, 28)
    c += T.lsrs_imm(3, 3, 28)
    c += T.orrs_reg(1, 3)
    c += T.ldr_imm32(3, 0x10000)
    c += T.orrs_reg(1, 3)                  # r1 = 1<<16 | row<<8 | col
    c += T.movs_imm8(2, 0)
    c += T.movs_imm8(3, 0)                 # enabled = 0
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), NOTIFY)
    c += T.ldr_imm32(3, DIRTY_OFF)
    c += T.add_reg(3, 4)
    c += T.movs_imm8(2, 1)
    c += T.strb_imm(2, 3, 0)               # [this+0x8CC4] = 1
    L["next"] = va + len(c)
    c += T.adds_imm(7, 7, 1)
    c += T.cmp_imm(7, 4)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    L["done"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 5)
    c += T.add_sp_imm(16)
    c += T.pop_lo([4, 5, 6, 7])
    c += T.bl(va + len(c), TOGGLE)         # stock launch/stop of the touched cell
    c += T.bw(va + len(c), BACK)
    return c
