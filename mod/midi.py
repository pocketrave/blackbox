"""v043: MIDI notes 111-118 launch / stop the clip of L3 column 1-8 in the selected row (the blue marker's row),
exactly as a tap on that clip.

MIDIB (audioTask) sits in front of cave B at HOOK_B 0x0805004C (r7 = note, r6 = event {+0x10 velocity}). Pads are
served before this point, so normal playing is unaffected; only Global-channel note-ons reach it. Notes 111-118
with velocity > 0 increment prod[k] (mod state +2100+k) and are swallowed (stock does nothing with them); every
other note continues in cave B (109/110 preset switch).
MCONS (defaultTask, called in C3 before LAUNCH): if no launch/stop request is pending, take the lowest column with
prod[k] != seen[k], seen[k] += 1, and TAP(k, selected row). Lossless: audioTask only writes prod, defaultTask only
writes seen.
TAP(k, n) = TREL's decision after a tap on clip (k, n): refresh COLSTATE(k), move the selection to (k, n), SELCLIP;
an empty clip only selects; the playing clip -> stop; the white-marked clip -> stop if the column plays nothing
else, else select only; otherwise launch. Then repaint (DIRTY)."""
import thumb as T
import phase5 as P5
import launch as LA
import paint as PT

NOTE_LO, NOTE_HI = 111, 118
PROD_OFF, SEEN_OFF = 2100, 2108             # mod state: u8 per column (2212 B free, previews end at 2100)
SEL_OFF = 80


def midib(va, L, cave_b_va):
    c = T.cmp_imm(7, NOTE_LO)
    c += T.b_cond(va + len(c), "cc", L.get("old", va))
    c += T.cmp_imm(7, NOTE_HI)
    c += T.b_cond(va + len(c), "hi", L.get("old", va))
    c += T.ldr_imm(3, 6, 0x10)               # velocity (r3 is reloaded by the displaced instruction anyway)
    c += T.cmp_imm(3, 0)
    c += T.b_cond_w(va + len(c), "eq", P5.NOTE_DONE)
    c += T.push_lo([0, 1])
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("done", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + PROD_OFF - NOTE_LO)
    c += T.add_reg(0, 1)
    c += T.adds_reg(0, 0, 7)                 # &prod[note - 111]
    c += T.ldrb_imm(1, 0, 0)
    c += T.adds_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    L["done"] = va + len(c)
    c += T.pop_lo([0, 1])
    c += T.bw(va + len(c), P5.NOTE_DONE)
    L["old"] = va + len(c)
    c += T.bw(va + len(c), cave_b_va)
    return c


def mcons(va, L, tap_va, lastrow=False):
    c = T.push_lo([4, 5, 6], lr=True)        # 16 B
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, LA.STATE_OFF)
    c += T.add_reg(4, 0)                     # r4 = mod state
    c += T.ldr_imm(0, 4, 0)
    c += T.cmp_imm(0, 0)                     # a request is waiting for LAUNCH: next pass
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c += T.movs_imm8(5, 0)                   # k
    L["scan"] = va + len(c)
    c += T.ldr_imm32(0, PROD_OFF)
    c += T.add_reg(0, 4)
    c += T.adds_reg(0, 0, 5)
    c += T.ldrb_imm(1, 0, 0)                 # prod[k]
    c += T.ldrb_imm(2, 0, SEEN_OFF - PROD_OFF)   # seen[k]
    c += T.cmp_reg(1, 2)
    c += T.b_cond(va + len(c), "ne", L.get("hit", va))
    c += T.adds_imm8(5, 1)
    c += T.cmp_imm(5, 8)
    c += T.b_cond(va + len(c), "ne", L.get("scan", va))
    c += T.b_short(va + len(c), L.get("out", va))
    L["hit"] = va + len(c)
    c += T.adds_imm8(2, 1)
    c += T.strb_imm(2, 0, SEEN_OFF - PROD_OFF)
    c += T.movs_imm8(0, SEL_OFF + 1)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(1, 0, 0)                 # the selected row
    if lastrow:                              # v047: a header is selected -> the clip row left behind (+108)
        c += T.cmp_imm(1, 0xFF)
        c += T.b_cond(va + len(c), "ne", L.get("rowok", va))
        c += T.ldrb_imm(1, 0, 108 - (SEL_OFF + 1))
        L["rowok"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), tap_va)
    L["out"] = va + len(c)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


def tap(va, L, table_va, colstate_va, selclip_va, dirty_va):
    """(r0 k, r1 n)."""
    c = T.push_lo([4, 5, 6, 7], lr=True)
    c += T.sub_sp_imm(4)
    c += T.mov_reg(5, 0)                     # r5 = k
    c += T.mov_reg(6, 1)                     # r6 = n
    c += T.ldr_imm32(7, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(7, 7, 0)
    c += T.cmp_imm(7, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(0, LA.STATE_OFF)
    c += T.add_reg(7, 0)                     # r7 = mod state
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), colstate_va)      # play / pending of column k, now
    c += T.movs_imm8(0, SEL_OFF)
    c += T.add_reg(0, 7)
    c += T.strb_imm(5, 0, 0)                 # selection = (k, n): a tap always selects the clip
    c += T.strb_imm(6, 0, 1)
    c += T.bl(va + len(c), selclip_va)
    # an empty clip only selects (v030)
    c += T.movs_imm8(2, 10)
    c += T.muls(2, 5)
    c += T.adds_reg(2, 2, 6)
    c += T.lsls_imm(2, 2, 1)
    c += T.ldr_imm32(3, table_va)
    c += T.add_reg(3, 2)
    c += T.ldrh_imm(3, 3, 0)
    c += T.ldr_imm32(2, LA.SESSION + 0x1C)
    c += T.add_reg(3, 2)
    c += T.ldr_imm(3, 3, 0)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.lsls_imm(2, 5, 2)
    c += T.adds_imm8(2, PT.COL_OFF)
    c += T.add_reg(2, 7)
    c += T.ldrb_imm(3, 2, 0)                 # play_n
    c += T.cmp_reg(3, 6)
    c += T.b_cond(va + len(c), "eq", L.get("stop", va))
    c += T.ldrb_imm(3, 2, 1)                 # the white-marked clip (armed / pending)
    c += T.cmp_reg(3, 6)
    c += T.b_cond(va + len(c), "ne", L.get("launch", va))
    c += T.ldrb_imm(3, 2, 0)
    c += T.cmp_imm(3, 0xFF)                  # ... un-launches only when the column plays nothing else
    c += T.b_cond(va + len(c), "eq", L.get("stop", va))
    c += T.b_short(va + len(c), L.get("out", va))
    L["launch"] = va + len(c)
    c += T.lsls_imm(0, 5, 8)
    c += T.orrs_reg(0, 6)
    c += T.ldr_imm32(3, LA.REQ_LAUNCH)
    c += T.orrs_reg(0, 3)
    c += T.str_imm(0, 7, 0)
    c += T.b_short(va + len(c), L.get("out", va))
    L["stop"] = va + len(c)
    c += T.lsls_imm(0, 5, 8)
    c += T.ldr_imm32(3, LA.REQ_STOP)
    c += T.orrs_reg(0, 3)
    c += T.str_imm(0, 7, 0)
    L["out"] = va + len(c)
    c += T.bl(va + len(c), dirty_va)
    L["ret"] = va + len(c)
    c += T.add_sp_imm(4)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c


def c3m(va, L, va_c, va_mcons, va_launch):
    """HOOK_C: stock call + cave C (va_c), then MCONS, then LAUNCH (takes MCONS's request in the same pass)."""
    c = T.push_lo([4], lr=True)
    c += T.bl(va + len(c), va_c)
    c += T.push_lo([0, 1, 2, 3])
    c += T.bl(va + len(c), va_mcons)
    c += T.bl(va + len(c), va_launch)
    c += T.pop_lo([0, 1, 2, 3])
    c += T.pop_lo([4], pc=True)
    return c
