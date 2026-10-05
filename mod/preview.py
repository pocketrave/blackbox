"""v039 L3 mini note preview on every clip tile (as stock, static, smaller grid).

Stock SEQS previews (class 0x080C1A14) are a cached grid of
16 time columns x 9 pitch rows, built by stock builders from a flat copy of the record's events. L3 reuses the
stock logic: CopyEvents 0x0806384C into the view's flat buffer (view+0x1B00, as stock UpdateCell), drop the notes
past Step Count (v036: they do not play), then the stock builder (PADS 0x080C1D0C / KEYS-MIDI 0x080C1AE8) into a
private scratch object; the 16x9 on/tie bytes are packed into a 40-B per-tile cache in mod RAM.
PAINT draws each tile's cache with FillRect (one rect per tied run): 1-px steps on a 2-px pitch, 2-px pitch rows on
a 3-px pitch, in the 32x26 area above the progress bar. Static: no playhead, no dot grid.
A tile is rebuilt when its clip changed (tag n+1) or the generation changed: PVINV wraps both stock UpdateCell
calls (msg 0x66 one cell, 0x67 all), which run after every edit, CLEAR, UNDO and preset load.
"""
import thumb as T
import phase5 as P5
import launch as LA
import paint as PT

PV_GEN_OFF = 105                            # mod state: u8 generation, +1 per stock UpdateCell
PV_BASE, PV_TILE = 112, 40                  # 40 tiles (k*5 + i) x {u8 n+1, u8 gen, 2 pad, 9 x {u16 on, u16 tie}}
PV_SCR = PV_BASE + 40 * PV_TILE             # 0x184-B scratch preview object (builders touch +0x34..+0x180)
SCR_SIZE = 0x184
UPD = 0x080B48E0                            # stock UpdateCell(view, row, col)
UPD_SITES = (0x080B52E6, 0x080B5468)        # msg 0x67 loop / msg 0x66
FLAT_OFF, FLAT_CLEAR, COPYEV = 0x1B00, 0x08063814, 0x0806384C
B_PADS, B_KEYS = 0x080C1D0C, 0x080C1AE8     # (this, &flat, stepLen, stepMode != 0)
SCR_COUNT, GRID, COL_STRIDE = 0x17C, 0x38, 0x12
C_NOTE = 3                                  # stock note colour
EV_SIZE = 24


def pvinv(va, L, migr_va=None):
    """Replaces bl UpdateCell at both sites: (v041) convert the cell for per-clip Duty/Quant, generation += 1,
    then tail-call UpdateCell (r0-r2 and lr kept)."""
    c = b""
    if migr_va is not None:
        c += T.push_lo([0, 1, 2], lr=True)   # 16 B
        c += T.mov_reg(0, 1)
        c += T.mov_reg(1, 2)
        c += T.bl(va + len(c), migr_va)
        c += T.ldr_sp(1, 8)                  # col
        c += T.cmp_imm(1, 3)
        c += T.b_cond(va + len(c), "ne", L.get("one", va))
        c += T.ldr_sp(0, 4)                  # row
        c += T.movs_imm8(1, 4)
        c += T.bl(va + len(c), migr_va)      # the hidden column 4 cell of this row
        L["one"] = va + len(c)
        c += T.pop_lo([0, 1, 2, 3])          # r3 = saved lr
        c += T.mov_reg(14, 3)
    c += T.push_lo([0])
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("skip", va))
    c += T.ldr_imm32(3, LA.STATE_OFF + PV_GEN_OFF)
    c += T.add_reg(0, 3)
    c += T.ldrb_imm(3, 0, 0)
    c += T.adds_imm8(3, 1)
    c += T.strb_imm(3, 0, 0)
    L["skip"] = va + len(c)
    c += T.pop_lo([0])
    c += T.bw(va + len(c), UPD)
    return c


def pvbuild(va, L, table_va, qtable_va):
    """(r0 view, r1 k, r2 n, r3 tile): build clip (k, n)'s 16x9 grid with the stock builder, pack it into the tile."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(28)                    # [sp] tile, +4 count, +8 step len, +12 mode flag, +16 0xB7, +20 view, +24 tmp
    c += T.str_sp(0, 20)
    c += T.str_sp(3, 0)
    c += T.movs_imm8(4, 10)
    c += T.muls(4, 1)
    c += T.adds_reg(4, 4, 2)                 # r4 = k*10 + n
    c += T.lsls_imm(0, 4, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)
    c += T.ldr_imm32(5, LA.SESSION)
    c += T.add_reg(5, 0)                     # r5 = clip record
    c += T.lsls_imm(0, 4, 2)
    c += T.ldr_imm32(1, qtable_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)
    c += T.ldr_imm32(6, LA.SESSION)
    c += T.add_reg(6, 0)                     # r6 = the clip cell's pattern-0 record (mode, step mode)
    for rec, pid, off in ((5, 0x86, 4), (5, 0x85, 8), (6, 0x88, 12), (6, 0xB7, 16)):
        c += T.mov_reg(0, rec)
        c += T.movs_imm8(1, pid)
        c += T.bl(va + len(c), LA.GETPARAM)
        if pid == 0x88:
            c += T.cmp_imm(0, 0)
            c += T.b_cond(va + len(c), "eq", L.get("sm0", va))
            c += T.movs_imm8(0, 1)
            L["sm0"] = va + len(c)
        c += T.str_sp(0, off)
    # flat copy of the events (as stock UpdateCell), then keep only the notes inside Step Count (v036)
    c += T.ldr_sp(7, 20)
    c += T.movw(0, FLAT_OFF)
    c += T.add_reg(7, 0)                     # r7 = flat {arr*, n}
    c += T.mov_reg(0, 7)
    c += T.bl(va + len(c), FLAT_CLEAR)
    c += T.mov_reg(1, 5)
    c += T.adds_imm8(1, 0x18)
    c += T.mov_reg(0, 7)
    c += T.bl(va + len(c), COPYEV)
    c += T.ldr_sp(0, 4)
    c += T.movw(3, 960)
    c += T.muls(3, 0)                        # r3 = tick limit
    c += T.ldr_imm(4, 7, 0)                  # r4 = arr
    c += T.ldr_imm(5, 7, 4)                  # r5 = n
    c += T.movs_imm8(6, 0)                   # r6 = kept
    c += T.movs_imm8(0, 0)                   # r0 = i
    L["floop"] = va + len(c)
    c += T.cmp_reg(0, 5)
    c += T.b_cond(va + len(c), "cs", L.get("fdone", va))
    c += T.movs_imm8(1, EV_SIZE)
    c += T.muls(1, 0)
    c += T.adds_reg(1, 1, 4)                 # src
    c += T.ldr_imm(2, 1, 4)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "cs", L.get("fskip", va))
    c += T.movs_imm8(2, EV_SIZE)
    c += T.muls(2, 6)
    c += T.adds_reg(2, 2, 4)                 # dst
    c += T.str_sp(0, 24)
    for o in range(0, EV_SIZE, 4):
        c += T.ldr_imm(0, 1, o)
        c += T.str_imm(0, 2, o)
    c += T.ldr_sp(0, 24)
    c += T.adds_imm8(6, 1)
    L["fskip"] = va + len(c)
    c += T.adds_imm8(0, 1)
    c += T.b_short(va + len(c), L.get("floop", va))
    L["fdone"] = va + len(c)
    c += T.str_imm(6, 7, 4)
    # stock builder into the scratch object
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.ldr_imm32(0, LA.STATE_OFF + PV_SCR)
    c += T.add_reg(4, 0)                     # r4 = scratch
    c += T.ldr_sp(0, 4)
    c += T.movw(1, SCR_COUNT)
    c += T.add_reg(1, 4)
    c += T.str_imm(0, 1, 0)                  # Step Count (time axis) before building
    c += T.movs_imm8(0, 0)                   # the builder never clears tie bytes: zero the 16x9 grid first
    c += T.mov_reg(1, 4)
    c += T.adds_imm8(1, GRID)
    c += T.movs_imm8(2, 16 * COL_STRIDE // 4)
    L["zero"] = va + len(c)
    c += T.str_imm(0, 1, 0)
    c += T.adds_imm8(1, 4)
    c += T.subs_imm8(2, 1)
    c += T.b_cond(va + len(c), "ne", L.get("zero", va))
    c += T.mov_reg(0, 4)
    c += T.mov_reg(1, 7)
    c += T.ldr_sp(2, 8)
    c += T.ldr_sp(3, 12)
    c += T.ldr_sp(5, 16)
    c += T.cmp_imm(5, 0)
    c += T.b_cond(va + len(c), "ne", L.get("keys", va))
    c += T.bl(va + len(c), B_PADS)
    c += T.b_short(va + len(c), L.get("built", va))
    L["keys"] = va + len(c)
    c += T.bl(va + len(c), B_KEYS)
    L["built"] = va + len(c)
    # pack: row r -> {u16 on, u16 tie}, bit c = column c
    c += T.adds_imm8(4, GRID)                # r4 = grid
    c += T.ldr_sp(5, 0)
    c += T.adds_imm8(5, 4)                   # r5 = tile rows
    c += T.movs_imm8(6, 0)                   # r6 = row
    L["prow"] = va + len(c)
    c += T.lsls_imm(7, 6, 1)
    c += T.adds_reg(7, 7, 4)
    c += T.movw(2, 15 * COL_STRIDE)
    c += T.add_reg(7, 2)                     # r7 = &grid[15][row]
    c += T.movs_imm8(0, 0)
    c += T.movs_imm8(1, 0)
    c += T.movs_imm8(3, 16)
    L["pcol"] = va + len(c)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldrb_imm(2, 7, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("pon", va))
    c += T.adds_imm8(0, 1)
    L["pon"] = va + len(c)
    c += T.lsls_imm(1, 1, 1)
    c += T.ldrb_imm(2, 7, 1)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ptie", va))
    c += T.adds_imm8(1, 1)
    L["ptie"] = va + len(c)
    c += T.subs_imm8(7, COL_STRIDE)
    c += T.subs_imm8(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("pcol", va))
    c += T.strh_imm(0, 5, 0)
    c += T.strh_imm(1, 5, 2)
    c += T.adds_imm8(5, 4)
    c += T.adds_imm8(6, 1)
    c += T.cmp_imm(6, 9)
    c += T.b_cond(va + len(c), "ne", L.get("prow", va))
    c += T.add_sp_imm(28)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def pvtile(va, L, build_va):
    """(r0 view, r1 k | i << 8, r2 n, r3 surface): rebuild the tile cache if stale, then draw the notes."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(28)                    # [sp] rect, +16 column, +20 row, +24 view
    c += T.str_sp(0, 24)
    c += T.mov_reg(5, 3)                     # r5 = surface
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.lsls_imm(6, 1, 24)
    c += T.lsrs_imm(6, 6, 24)                # r6 = k
    c += T.lsrs_imm(7, 1, 8)                 # r7 = i
    c += T.movs_imm8(0, 5)
    c += T.muls(0, 6)
    c += T.adds_reg(0, 0, 7)
    c += T.movs_imm8(1, PV_TILE)
    c += T.muls(0, 1)
    c += T.ldr_imm32(1, LA.STATE_OFF + PV_BASE)
    c += T.adds_reg(0, 0, 1)
    c += T.ldr_imm32(1, LA.STATE_OFF + PV_GEN_OFF)
    c += T.add_reg(1, 4)
    c += T.ldrb_imm(1, 1, 0)                 # r1 = generation
    c += T.add_reg(4, 0)                     # r4 = tile
    c += T.mov_reg(3, 2)
    c += T.adds_imm8(3, 1)                   # r3 = n + 1
    c += T.ldrb_imm(0, 4, 0)
    c += T.cmp_reg(0, 3)
    c += T.b_cond(va + len(c), "ne", L.get("rebuild", va))
    c += T.ldrb_imm(0, 4, 1)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("draw", va))
    L["rebuild"] = va + len(c)
    c += T.strb_imm(3, 4, 0)
    c += T.strb_imm(1, 4, 1)
    c += T.ldr_sp(0, 24)
    c += T.mov_reg(1, 6)
    c += T.mov_reg(3, 4)
    c += T.bl(va + len(c), build_va)         # r2 = n still
    L["draw"] = va + len(c)
    c += T.movs_imm8(0, 40)
    c += T.muls(6, 0)
    c += T.adds_imm8(6, 4)                   # r6 = x0 = 40k + 4
    c += T.muls(7, 0)
    c += T.movs_imm8(0, 173)
    c += T.subs_reg(7, 0, 7)                 # r7 = row 0 y = 161 - 40i + 12
    c += T.adds_imm8(4, 4)                   # r4 = tile rows
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 20)
    L["row"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 16)
    L["col"] = va + len(c)
    c += T.ldr_sp(0, 16)
    c += T.cmp_imm(0, 16)
    c += T.b_cond(va + len(c), "cs", L.get("nextrow", va))
    c += T.ldrh_imm(1, 4, 0)
    c += T.lsrs_reg(1, 0)
    c += T.movs_imm8(2, 1)
    c += T.ands_reg(1, 2)
    c += T.b_cond(va + len(c), "eq", L.get("cnext", va))
    c += T.mov_reg(3, 0)                     # r3 = run end
    L["tie"] = va + len(c)
    c += T.cmp_imm(3, 15)
    c += T.b_cond(va + len(c), "cs", L.get("tdone", va))
    c += T.ldrh_imm(1, 4, 2)
    c += T.lsrs_reg(1, 3)
    c += T.movs_imm8(2, 1)
    c += T.ands_reg(1, 2)
    c += T.b_cond(va + len(c), "eq", L.get("tdone", va))
    c += T.adds_imm8(3, 1)
    c += T.b_short(va + len(c), L.get("tie", va))
    L["tdone"] = va + len(c)
    c += T.mov_reg(2, 3)
    c += T.adds_imm8(2, 1)
    c += T.str_sp(2, 16)                     # next column after the run
    c += T.lsls_imm(1, 0, 1)
    c += T.adds_reg(1, 1, 6)
    c += T.str_sp(1, 0)                      # x = x0 + 2 * start
    c += T.str_sp(7, 4)                      # y
    c += T.subs_reg(1, 3, 0)
    c += T.lsls_imm(1, 1, 1)
    c += T.adds_imm8(1, 1)
    c += T.str_sp(1, 8)                      # w = 2 * (end - start) + 1
    c += T.movs_imm8(1, 2)
    c += T.str_sp(1, 12)                     # h = 2
    c += T.add_rd_sp(0, 0)
    c += T.movs_imm8(1, C_NOTE)
    c += T.mov_reg(2, 5)
    c += T.bl(va + len(c), PT.FILLRECT)
    c += T.b_short(va + len(c), L.get("col", va))
    L["cnext"] = va + len(c)
    c += T.adds_imm8(0, 1)
    c += T.str_sp(0, 16)
    c += T.b_short(va + len(c), L.get("col", va))
    L["nextrow"] = va + len(c)
    c += T.adds_imm8(4, 4)
    c += T.adds_imm8(7, 3)
    c += T.ldr_sp(0, 20)
    c += T.adds_imm8(0, 1)
    c += T.str_sp(0, 20)
    c += T.cmp_imm(0, 9)
    c += T.b_cond(va + len(c), "ne", L.get("row", va))
    L["out"] = va + len(c)
    c += T.add_sp_imm(28)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
