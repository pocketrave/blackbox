"""v024 L3 step 1: launch helper.

No MIDI or touch trigger: a request word in mod state is written by the simulator (v024) and by the
L3 touch code (v026). LAUNCH runs in the defaultTask loop after the old cave C (cave C3), the task
in which stock touch handling and SendPattern run.

  request 0x80000000 | k<<8 | n   launch L3 clip (column k 0..7, row n 0..9): its record (l3map) is
                                  streamed into a slot of host H(k) that is neither current nor
                                  pending (ring of the 4 constructed slots), as stock SendPattern
                                  sends a pattern; then 0xC0 = slot. If H(k) is stopped it is enabled
                                  as stock ToggleCellPlay does (SetParam 0xBE + Notify).
  request 0x40000000 | k<<8       stop column k (ToggleCellPlay's disable).

Mod state at [0x2401F4FC] + 0x1A1*28 (verified free at runtime):
  +0 u32 request; +4 + k*4 + s  u8 = n+1 of the clip streamed into slot s of H(k) (0 = none).
"""
import thumb as T
import phase5 as P5

STATE_OFF = 0x1A1 * 28
REQ_LAUNCH, REQ_STOP = 0x80000000, 0x40000000
SESSION, ENGINE = 0x24020088, 0x2400A9C0
REGISTRY, REGISTRY_N = 0x24049808, 64
PLAYER_VT = 0x080D0744
DIRTY = 0x8CC4
MAX_EVENTS = 0x200

GETPARAM, SETPARAM = 0x08093E9C, 0x08093ECC
PARAMPOST = 0x0804C59C                       # (eng, code, id, value, [sp] 0, [sp+4] slot)
CLEARSLOT = 0x0804C7E8                       # (eng, code, 0, slot)
ADDEVENT = 0x0804C798                        # (eng, code, event*, [session+0x8CBC], [sp] slot)
NOTIFY = 0x0804C87C                          # (eng, code, 0, enabled): op 0x68 launch/stop
NUMBER = 0x08063C58                          # (container, session+0xE808, 0)
GETEVENT = 0x08063D08                        # (container, i, out*) -> 0 past the end
SLOT_PARAMS = (0x85, 0x86, 0x49)
QUANT, QCELL_OFF = 0x46, 96                  # mod state +96+k: v041 n + 1 of the clip launched in column k
                                             # (v037-v040: cell index + 1)

FR = 52                                      # 20 pushed + 52 = 72: sp 8-aligned at every bl
# frame: [sp] arg5, [sp+4] arg6, [sp+8..0x1F] event buffer, [sp+0x20] player, [sp+0x24] slot,
#        [sp+0x28] n, [sp+0x2C] code, [sp+0x30] host record address


def c3(va, L, va_c, va_launch):
    c = T.push_lo([4], lr=True)
    c += T.bl(va + len(c), va_c)
    c += T.push_lo([0, 1, 2, 3])
    c += T.bl(va + len(c), va_launch)
    c += T.pop_lo([0, 1, 2, 3])
    c += T.pop_lo([4], pc=True)
    return c


def _post(c, va, id_, value_reg, slot_sp=None):
    """ParamPost(ENGINE, [sp+0x2C] code, id_, r<value_reg>, 0, slot). slot_sp None -> 0. Uses r0-r3."""
    if value_reg != 3:
        c += T.mov_reg(3, value_reg)
    c += T.movs_imm8(0, 0)
    c += T.str_sp(0, 0)
    if slot_sp is not None:
        c += T.ldr_sp(0, slot_sp)
    c += T.str_sp(0, 4)
    c += T.ldr_imm32(0, ENGINE)
    c += T.ldr_sp(1, 0x2C)
    c += T.movs_imm8(2, id_)
    c += T.bl(va + len(c), PARAMPOST)
    return c


def _enable(c, va, value):
    """SetParam([sp+0x30] host record, 0xBE, value); Notify(ENGINE, [sp+0x2C] code, 0, value); dirty."""
    c += T.movs_imm8(2, value)
    c += T.movs_imm8(1, 0xBE)
    c += T.ldr_sp(0, 0x30)
    c += T.bl(va + len(c), SETPARAM)
    c += T.movs_imm8(3, value)
    c += T.movs_imm8(2, 0)
    c += T.ldr_sp(1, 0x2C)
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), NOTIFY)
    c += T.ldr_imm32(0, SESSION + DIRTY)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    return c


def launch(va, L, table_va, hosts_va, dirty_va=None, reserve0=False, count_filter=False, qtable_va=None,
           duty_from_clip=False, quant_per_clip=False):
    assert qtable_va is None or count_filter     # v037 keeps k at [sp+0x38] (the count_filter frame)
    c = T.push_lo([4, 5, 6, 7], lr=True)
    fr = 60 if count_filter else FR             # v036: [sp+0x34] = tick limit
    c += T.sub_sp_imm(fr)
    # ---- take the request -------------------------------------------------------------------
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, STATE_OFF)
    c += T.adds_reg(7, 0, 1)                 # r7 = mod state
    c += T.ldr_imm(5, 7, 0)                  # r5 = request
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.movs_imm8(1, 0)
    c += T.str_imm(1, 7, 0)                  # clear it (taken even if invalid)
    if dirty_va is not None:
        c += T.bl(va + len(c), dirty_va)     # v030: repaint (with countdown) after every request
    # ---- decode: k = (req >> 8) & 0xFF < 8, n = req & 0xFF ------------------------------------
    c += T.lsrs_imm(0, 5, 8)
    c += T.movs_imm8(1, 0xFF)
    c += T.ands_reg(0, 1)
    c += T.cmp_imm(0, 8)
    c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    c += T.mov_reg(4, 0)                     # r4 = k
    if qtable_va is not None:
        c += T.str_sp(4, 0x38)
    c += T.lsls_imm(0, 4, 3)
    c += T.ldr_imm32(1, hosts_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(0, 1, 0)
    c += T.str_sp(0, 0x2C)                   # code of H(k)
    c += T.ldr_imm(0, 1, 4)
    c += T.ldr_imm32(2, SESSION)
    c += T.add_reg(0, 2)
    c += T.str_sp(0, 0x30)                   # host pattern-0 record
    # ---- host player from the engine node registry ------------------------------------------
    c += T.ldr_imm32(1, REGISTRY)
    c += T.movs_imm8(3, REGISTRY_N)
    L["find"] = va + len(c)
    c += T.ldr_imm(6, 1, 0)
    c += T.adds_imm8(1, 4)
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "eq", L.get("fnext", va))
    c += T.ldr_imm(0, 6, 0)
    c += T.ldr_imm32(2, PLAYER_VT)
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "ne", L.get("fnext", va))
    c += T.ldr_imm(0, 6, 0x18)
    c += T.ldr_sp(2, 0x2C)
    c += T.cmp_reg(0, 2)
    c += T.b_cond(va + len(c), "eq", L.get("found", va))
    L["fnext"] = va + len(c)
    c += T.subs_imm8(3, 1)
    c += T.b_cond(va + len(c), "ne", L.get("find", va))
    c += T.bw(va + len(c), L.get("out", va))
    L["found"] = va + len(c)
    c += T.str_sp(6, 0x20)                   # player
    # ---- stop ----------------------------------------------------------------------------------
    c += T.lsrs_imm(0, 5, 30)
    c += T.cmp_imm(0, 1)                     # 0x40000000 -> 1
    c += T.b_cond(va + len(c), "ne", L.get("islaunch", va))
    c = _enable(c, va, 0)
    c += T.bw(va + len(c), L.get("out", va))
    L["islaunch"] = va + len(c)
    c += T.cmp_imm(0, 2)                     # 0x80000000 -> 2
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    # ---- launch: n < 10, record = SESSION + table[k*10 + n] -----------------------------------
    c += T.movs_imm8(0, 0xFF)
    c += T.ands_reg(5, 0)                    # r5 = n
    c += T.cmp_imm(5, 10)
    c += T.b_cond_w(va + len(c), "cs", L.get("out", va))
    c += T.str_sp(5, 0x28)
    c += T.movs_imm8(0, 10)
    c += T.muls(0, 4)                        # r0 = k*10
    c += T.adds_reg(0, 0, 5)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)
    c += T.ldr_imm32(1, SESSION)
    c += T.adds_reg(6, 0, 1)                 # r6 = record
    if reserve0:                             # v033 I1: the host's own pattern-0 record lives in slot 0
        c += T.ldr_sp(0, 0x30)
        c += T.cmp_reg(6, 0)
        c += T.b_cond_w(va + len(c), "ne", L.get("ring", va))
        c += T.movs_imm8(0, 0)
        c += T.str_sp(0, 0x24)
        c += T.bw(va + len(c), L.get("sent", va))
        L["ring"] = va + len(c)
    # ---- slot: lowest of 0..3 that is neither current nor pending ------------------------------
    c += T.ldr_sp(2, 0x20)
    c += T.movw(3, 0xC20)
    c += T.add_reg(3, 2)
    # pending first: if audioTask commits pending -> current between the two loads, the slot that
    # becomes current was already read as pending, so it is still avoided (v024)
    c += T.ldr_imm(1, 3, 4)                  # pending slot address (0 = none)
    c += T.ldr_imm(0, 3, 0)                  # current slot address
    c += T.movw(3, 0x320)
    c += T.add_reg(2, 3)                     # slot 0 address
    c += T.movs_imm8(3, 0)
    if reserve0:
        c += T.adds_imm8(2, 0x48)            # start at slot 1
        c += T.movs_imm8(3, 1)
    L["pick"] = va + len(c)
    c += T.cmp_reg(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("pnext", va))
    c += T.cmp_reg(2, 1)
    c += T.b_cond(va + len(c), "ne", L.get("picked", va))
    L["pnext"] = va + len(c)
    c += T.adds_imm8(2, 0x48)
    c += T.adds_imm8(3, 1)
    c += T.cmp_imm(3, 4)
    c += T.b_cond(va + len(c), "ne", L.get("pick", va))
    c += T.bw(va + len(c), L.get("out", va))   # unreachable: at most 2 of 4 slots are taken
    L["picked"] = va + len(c)
    c += T.str_sp(3, 0x24)                   # slot
    # ---- stream: per-slot params, numbering, clear, events -------------------------------------
    for id_ in SLOT_PARAMS:
        if id_ == 0x49 and not duty_from_clip:   # v024-v040: Duty from the host (instrument)
            c += T.ldr_sp(0, 0x30)
        else:                                # Step Len / Step Count, and v041 Duty: the clip's own record
            c += T.mov_reg(0, 6)
        c += T.movs_imm8(1, id_)
        c += T.bl(va + len(c), GETPARAM)
        if count_filter and id_ == 0x86:
            c += T.movw(1, 960)
            c += T.muls(1, 0)
            c += T.str_sp(1, 0x34)           # v036: tick limit = Step Count * 960
        c = _post(c, va, id_, 0, 0x24)
    c += T.mov_reg(5, 6)
    c += T.adds_imm8(5, 0x18)                # r5 = event container
    c += T.ldr_imm(0, 5, 4)
    c += T.movw(1, MAX_EVENTS)
    c += T.cmp_reg(0, 1)
    c += T.b_cond_w(va + len(c), "hi", L.get("out", va))
    c += T.movs_imm8(2, 0)
    c += T.ldr_imm32(1, SESSION + 0xE808)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), NUMBER)
    c += T.ldr_sp(3, 0x24)
    c += T.movs_imm8(2, 0)
    c += T.ldr_sp(1, 0x2C)
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), CLEARSLOT)
    c += T.movs_imm8(4, 0)                   # r4 = event index (k no longer needed in r4)
    L["loop"] = va + len(c)
    c += T.add_rd_sp(2, 8)
    c += T.mov_reg(1, 4)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), GETEVENT)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("sent", va))
    if count_filter:                         # v036: only the notes inside Step Count
        c += T.ldr_sp(0, 0xC)
        c += T.ldr_sp(1, 0x34)
        c += T.cmp_reg(0, 1)
        c += T.b_cond(va + len(c), "cs", L.get("skipev", va))
    c += T.ldr_sp(0, 0x24)
    c += T.str_sp(0, 0)
    c += T.ldr_imm32(3, SESSION + 0x8CBC)
    c += T.ldr_imm(3, 3)
    c += T.add_rd_sp(2, 8)
    c += T.ldr_sp(1, 0x2C)
    c += T.ldr_imm32(0, ENGINE)
    c += T.bl(va + len(c), ADDEVENT)
    if count_filter:
        L["skipev"] = va + len(c)
    c += T.adds_imm8(4, 1)
    c += T.b_short(va + len(c), L.get("loop", va))
    L["sent"] = va + len(c)
    if qtable_va is not None and quant_per_clip:  # v041: the launched clip's own record; +96+k = n + 1
        c += T.ldr_sp(0, 0x28)
        c += T.adds_imm8(0, 1)
        c += T.ldr_sp(1, 0x38)
        c += T.add_reg(1, 7)
        c += T.adds_imm8(1, QCELL_OFF)
        c += T.strb_imm(0, 1, 0)
        c += T.mov_reg(0, 6)                 # r6 = the clip record (kept from the table lookup)
        c += T.movs_imm8(1, QUANT)
        c += T.bl(va + len(c), GETPARAM)
        c = _post(c, va, QUANT, 0, None)
    elif qtable_va is not None:              # v037-v040: the clip cell's pattern-0 Quant; +96+k = cell + 1
        c += T.ldr_sp(0, 0x38)
        c += T.movs_imm8(1, 10)
        c += T.muls(1, 0)
        c += T.ldr_sp(0, 0x28)
        c += T.adds_reg(1, 1, 0)
        c += T.lsls_imm(1, 1, 2)
        c += T.ldr_imm32(0, qtable_va)
        c += T.add_reg(0, 1)
        c += T.ldr_imm(5, 0, 0)              # r5 = cell << 16 | cell pattern-0 record offset
        c += T.lsrs_imm(0, 5, 16)
        c += T.adds_imm8(0, 1)
        c += T.ldr_sp(1, 0x38)
        c += T.add_reg(1, 7)
        c += T.adds_imm8(1, QCELL_OFF)
        c += T.strb_imm(0, 1, 0)             # qcell[k] = cell + 1
        c += T.lsls_imm(0, 5, 16)
        c += T.lsrs_imm(0, 0, 16)
        c += T.ldr_imm32(1, SESSION)
        c += T.add_reg(0, 1)
        c += T.movs_imm8(1, QUANT)
        c += T.bl(va + len(c), GETPARAM)
        c = _post(c, va, QUANT, 0, None)
    # ---- select the slot ---------------------------------------------------------------------
    c += T.ldr_sp(4, 0x24)
    c = _post(c, va, 0xC0, 4, None)
    # ---- mod state: slot_clip[k][slot] = n + 1 --------------------------------------------------
    if reserve0:                             # v033: slot 0 stays stock (I1): no slot_clip entry
        c += T.ldr_sp(0, 0x24)
        c += T.cmp_imm(0, 0)
        c += T.b_cond_w(va + len(c), "eq", L.get("nostore", va))
    c += T.ldr_sp(0, 0x2C)
    c += T.lsls_imm(1, 0, 30)                # k from the code: col bits (0..3) ...
    c += T.lsrs_imm(1, 1, 30)
    c += T.lsrs_imm(0, 0, 8)
    c += T.movs_imm8(2, 1)
    c += T.ands_reg(0, 2)                    # ... + 4 * row (row 0 or 1)
    c += T.lsls_imm(0, 0, 2)
    c += T.adds_reg(1, 1, 0)                 # r1 = k
    c += T.lsls_imm(1, 1, 2)
    c += T.adds_imm8(1, 4)
    c += T.ldr_sp(0, 0x24)
    c += T.adds_reg(1, 1, 0)
    c += T.add_reg(1, 7)                     # r1 = &state[4 + k*4 + slot]
    c += T.ldr_sp(0, 0x28)
    c += T.adds_imm8(0, 1)
    c += T.strb_imm(0, 1, 0)
    if reserve0:
        L["nostore"] = va + len(c)
    # ---- stopped host: enable it -----------------------------------------------------------------
    c += T.ldr_sp(2, 0x20)
    c += T.adds_imm8(2, 0x5B)
    c += T.ldrb_imm(0, 2, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "ne", L.get("out", va))
    c = _enable(c, va, 1)
    L["out"] = va + len(c)
    c += T.add_sp_imm(fr)
    c += T.pop_lo([4, 5, 6, 7], pc=True)
    return c
