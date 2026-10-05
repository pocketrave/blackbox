"""v041: convert old presets for per-clip Duty / Quant. Stock kept Duty 0x49 / Quant 0x46 on
pattern A (sub 0) of each cell; patterns B-D hold untouched defaults. MIGR(row, col) copies A's values into every
pattern 1..3 not yet converted and marks it with 0x88 = MARK (stock never reads or posts 0x88 of patterns 1-3;
the Step Mode toggle 0x08098728 copies each record onto itself).
v041 ran it on every stock UpdateCell; v042 runs it once per load, at the start of the stock
upload-all loop (UPLW at 0x0809CC84, function 0x0809CB4C, callers 0x0809E218 / 0x080A2258): that loop SendPatterns
every cell from the LIVE records. (A wrapper on the session loader 0x08096AD8 was tried first: the sim showed the
loader parses into staging and the live records are filled after it returns, so LOADW is not installed.)
Edits / pastes / UNDO of a B-D record mark it through SYNC (sync.py)."""
import thumb as T
import launch as LA

MARK = 2
LOADER = 0x08096AD8                         # session loader (r0-r3 args, no stack args)
LOAD_SITES = (0x080918F6, 0x08091916, 0x08092336, 0x08092882)   # its 4 callers (bl)
UPL_SITE, UPL_ORIG, UPL_BACK = 0x0809CC84, bytes.fromhex("4ff0000a"), 0x0809CC88   # mov.w sl, #0
P_DUTY, P_QUANT, P_STEPMODE = 0x49, 0x46, 0x88


def migr(va, L):
    """(r0 row, r1 col)."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(4)
    c += T.cmp_imm(0, 3)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.cmp_imm(1, 4)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.movw(2, 0x370)
    c += T.muls(2, 0)
    c += T.movs_imm8(3, 0xB0)
    c += T.muls(3, 1)
    c += T.adds_reg(2, 2, 3)
    c += T.ldr_imm32(3, LA.SESSION + 0x1C00)
    c += T.adds_reg(4, 2, 3)                 # r4 = pattern-0 record (A)
    c += T.movs_imm8(6, 1)                   # r6 = p
    L["loop"] = va + len(c)
    c += T.movs_imm8(5, 0x2C)
    c += T.muls(5, 6)
    c += T.adds_reg(5, 5, 4)                 # r5 = record p
    c += T.mov_reg(0, 5)
    c += T.movs_imm8(1, P_STEPMODE)
    c += T.bl(va + len(c), LA.GETPARAM)
    c += T.cmp_imm(0, MARK)
    c += T.b_cond(va + len(c), "eq", L.get("next", va))
    for pid in (P_DUTY, P_QUANT):
        c += T.mov_reg(0, 4)
        c += T.movs_imm8(1, pid)
        c += T.bl(va + len(c), LA.GETPARAM)
        c += T.mov_reg(2, 0)
        c += T.mov_reg(0, 5)
        c += T.movs_imm8(1, pid)
        c += T.bl(va + len(c), LA.SETPARAM)
    c += T.movs_imm8(2, MARK)
    c += T.mov_reg(0, 5)
    c += T.movs_imm8(1, P_STEPMODE)
    c += T.bl(va + len(c), LA.SETPARAM)
    L["next"] = va + len(c)
    c += T.adds_imm8(6, 1)
    c += T.cmp_imm(6, 4)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    L["out"] = va + len(c)
    c += T.add_sp_imm(4)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def loadw(va, L, migr_va):
    """bl site replacement: the session loader with its own args, then MIGR over all 20 cells; returns its r0."""
    c = T.push_lo([4, 5, 6], lr=True)        # 16 B
    c += T.bl(va + len(c), LOADER)
    c += T.mov_reg(4, 0)
    c += T.movs_imm8(5, 0)                   # row
    L["row"] = va + len(c)
    c += T.movs_imm8(6, 0)                   # col
    L["col"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.mov_reg(1, 6)
    c += T.bl(va + len(c), migr_va)
    c += T.adds_imm8(6, 1)
    c += T.cmp_imm(6, 5)
    c += T.b_cond(va + len(c), "ne", L.get("col", va))
    c += T.adds_imm8(5, 1)
    c += T.cmp_imm(5, 4)
    c += T.b_cond(va + len(c), "ne", L.get("row", va))
    c += T.mov_reg(0, 4)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def uplw(va, L, migr_va):
    """b.w from the upload-all loop's first instruction: MIGR every cell, restore r0-r4 / lr, sl = 0, continue."""
    c = T.push_lo([0, 1, 2, 3, 4], lr=True)  # 24 B: sp stays 8-aligned
    c += T.movs_imm8(4, 0)
    L["loop"] = va + len(c)
    c += T.movs_imm8(1, 5)
    c += T.udiv(0, 4, 1)                     # row = i / 5
    c += T.muls(1, 0)
    c += T.subs_reg(1, 4, 1)                 # col = i - 5 * row
    c += T.bl(va + len(c), migr_va)
    c += T.adds_imm8(4, 1)
    c += T.cmp_imm(4, 20)
    c += T.b_cond(va + len(c), "ne", L.get("loop", va))
    c += T.ldr_sp(0, 20)
    c += T.mov_reg(14, 0)                    # lr back
    c += T.pop_lo([0, 1, 2, 3, 4])
    c += T.add_sp_imm(4)
    c += T.movw(10, 0)                       # displaced: mov.w sl, #0
    c += T.bw(va + len(c), UPL_BACK)
    return c
