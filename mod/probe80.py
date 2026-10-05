"""v023 PROBE (v022 fixed): play one hidden column-5 clip through an existing player.

A throwaway feasibility probe for "4 columns x 20 rows = 80 clips", not the feature.

  MIDI note 111  record (row 0, col 4, pattern 0), i.e. the column-5 row-1 clip, is streamed into
                 the player of cell (row 0, col 0) as pattern SLOT 3 (its pattern D), the way
                 SendPattern 0x080985A0 sends a pattern (per-slot params, clear, one add per event),
                 then pattern 0xC0 = 3 is posted to that player (quantized by the engine).
  MIDI note 112  pattern 0xC0 = 0, then stock SendPattern(session, cell (0,0), 3) restores that
                 cell's own pattern D in the engine.

v022 used slot 4: the simulator showed clip players (+0x60 = 0) construct only slots 0-3, so slot
4's container had a NULL index pointer and AddEvent wrote through it (memory at 0 changed). Clip
players have no SectCount gate (that path is for +0x60 = 1), so no 0xC1 post any more.

The note is caught in the audio task (cave B2, before the old cave B) and only sets a mailbox
word, scratch+24. The work runs in the defaultTask loop (cave C2, after the old cave C), the
same task that runs stock SendPattern from touch input. Engine code is unchanged.
"""
import thumb as T
import phase5 as P5

NOTE_GO, NOTE_BACK = 111, 112
MB_OFF = 24                                  # scratch word 6: free (0..20 are used)
SESSION = 0x24020088
ENGINE = 0x2400A9C0
REC_OFF = 0x1C00 + 0 * 0x370 + 4 * 0xB0 + 0 * 0x2C   # ResolveSequenceCell(row 0, col 4, pat 0)
CODE = 1 << 16 | 0 << 8 | 0                  # engine code of the seq player (row 0, col 0)
SLOT = 3                                     # the last CONSTRUCTED slot of a clip player
MAX_EVENTS = 0x200                           # the record's event cap (0x08063B28)

GETPARAM = 0x08093E9C                        # (owner, id) -> value
PARAMPOST = 0x0804C59C                       # (engine, code, id, value, [sp] 0, [sp+4] slot)
CLEARSLOT = 0x0804C7E8                       # (engine, code, 0, slot)
ADDEVENT = 0x0804C798                        # (engine, code, event*, [session+0x8CBC], [sp] slot)
NUMBER = 0x08063C58                          # (container, session+0xE808, 0): give events ids
GETEVENT = 0x08063D08                        # (container, i, out*) -> 0 past the end
SENDPATTERN = 0x080985A0                     # (session, desc*, pat): stock pattern upload
SELECTPATTERN = 0x0805E364                   # engine, for the test only
SLOTCTOR = 0x0805C674                        # engine, for the test only
SLOT_PARAMS = (0x85, 0x86, 0x49)             # Step Len, Step Count, Duty Cycle (per slot)


def b2(va, L, va_b):
    """At HOOK_B 0x0805004C, in front of the old cave B. r7 = note; r0-r2 as there."""
    c = T.cmp_imm(7, NOTE_GO)
    c += T.b_cond(va + len(c), "eq", L.get("go", va))
    c += T.cmp_imm(7, NOTE_BACK)
    c += T.b_cond(va + len(c), "eq", L.get("back", va))
    c += T.bw(va + len(c), va_b)
    L["go"] = va + len(c)
    c += T.push_lo([0, 1, 2])
    c += T.movs_imm8(2, 1)
    c += T.b_short(va + len(c), L.get("store", va))
    L["back"] = va + len(c)
    c += T.push_lo([0, 1, 2])
    c += T.movs_imm8(2, 2)
    L["store"] = va + len(c)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("done", va))
    c += T.movw(1, P5.SCRATCH_OFF)
    c += T.add_reg(0, 1)
    c += T.str_imm(2, 0, MB_OFF)
    L["done"] = va + len(c)
    c += T.pop_lo([0, 1, 2])
    c += T.bw(va + len(c), P5.NOTE_DONE)
    return c


def c2(va, L, va_c, va_probe):
    """At HOOK_C 0x08043E28 (bl): the old cave C (stock call + preset gate), then the probe.
    Pushes 8 bytes so the old cave C sees the same sp alignment as before; keeps r0-r3."""
    c = T.push_lo([4], lr=True)
    c += T.bl(va + len(c), va_c)
    c += T.push_lo([0, 1, 2, 3])
    c += T.bl(va + len(c), va_probe)
    c += T.pop_lo([0, 1, 2, 3])
    c += T.pop_lo([4], pc=True)
    return c


def _post(c, va, id_, value_reg, slot):
    """ParamPost(ENGINE, CODE, id_, r<value_reg>, 0, slot). Uses r0-r3."""
    if value_reg != 3:
        c += T.mov_reg(3, value_reg)
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 0)
    c += T.movs_imm8(0, slot)
    c += T.str_sp(0, 4)
    c += T.ldr_imm32(0, ENGINE)
    c += T.ldr_imm32(1, CODE)
    c += T.movs_imm8(2, id_)
    c += T.bl(va + len(c), PARAMPOST)
    return c


def probe(va, L):
    FR = 36                                  # 20 pushed + 36 = 56: sp 8-aligned at every bl
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(FR)                    # [sp] arg5, [sp+4] arg6, [sp+8..0x20] event buffer
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movw(1, P5.SCRATCH_OFF)
    c += T.add_reg(0, 1)
    c += T.ldr_imm(5, 0, MB_OFF)
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 0)
    c += T.str_imm(1, 0, MB_OFF)             # take the request
    c += T.cmp_imm(5, 1)
    c += T.b_cond_w(va + len(c), "eq", L.get("go", va))
    c += T.movs_imm8(4, 0)                   # 2 = back: pattern 0
    c = _post(c, va, 0xC0, 4, 0)
    c += T.movw(0, 0x100)                    # fake desc at sp+8: u16 +4 = layer 1, row 0, col 0
    c += T.add_rd_sp(1, 8)
    c += T.strh_imm(0, 1, 4)
    c += T.movs_imm8(2, SLOT)
    c += T.ldr_imm32(0, SESSION)
    c += T.bl(va + len(c), SENDPATTERN)     # restore the cell's own pattern D in the engine
    c += T.bw(va + len(c), L.get("out", va))

    L["go"] = va + len(c)
    c += T.ldr_imm32(6, SESSION + REC_OFF)   # r6 = the column-5 row-1 record
    for id_ in SLOT_PARAMS:
        c += T.mov_reg(0, 6)
        c += T.movs_imm8(1, id_)
        c += T.bl(va + len(c), GETPARAM)
        c = _post(c, va, id_, 0, SLOT)
    c += T.mov_reg(7, 6)
    c += T.adds_imm8(7, 0x18)                # r7 = its event container
    c += T.ldr_imm(0, 7, 4)                  # count
    c += T.movw(1, MAX_EVENTS)
    c += T.cmp_reg(0, 1)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))   # not a sane record: send nothing more
    c += T.movs_imm8(2, 0)
    c += T.ldr_imm32(1, SESSION + 0xE808)
    c += T.mov_reg(0, 7)
    c += T.bl(va + len(c), NUMBER)
    c += T.movs_imm8(3, SLOT)
    c += T.movs_imm8(2, 0)
    c += T.ldr_imm32(1, CODE)
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), CLEARSLOT)
    c += T.movs_imm8(5, 0)                   # r5 = event index
    L["loop"] = va + len(c)
    c += T.add_rd_sp(2, 8)
    c += T.mov_reg(1, 5)
    c += T.mov_reg(0, 7)
    c += T.bl(va + len(c), GETEVENT)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("sent", va))
    c += T.movs_imm8(0, SLOT)
    c += T.str_sp(0, 0)
    c += T.ldr_imm32(3, SESSION + 0x8CBC)
    c += T.ldr_imm(3, 3)
    c += T.add_rd_sp(2, 8)
    c += T.ldr_imm32(1, CODE)
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), ADDEVENT)
    c += T.adds_imm8(5, 1)
    c += T.b_short(va + len(c), L.get("loop", va))
    L["sent"] = va + len(c)
    c += T.movs_imm8(4, SLOT)
    c = _post(c, va, 0xC0, 4, 0)             # play slot 3 (engine quantizes as usual)

    L["out"] = va + len(c)
    c += T.add_sp_imm(FR)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
