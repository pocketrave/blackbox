"""v053: Elektron-style trig conditions on the piano roll's Event "PLAY:" list, with FILL.

A note's cond byte (event +1; stock: 0 = always, 1..99 = chance) also holds 100..122 = 1:2 .. 8:8, 1ST, -1ST,
PRE, -PRE, FILL, -FILL. Stock saves and loads the byte as is, so presets need no change (stock plays these always).
CNT (SetStep entry) counts loops per L3 column: step 0 after a start / launch / slot swap (old step -1) -> 0, step 0
after another step -> +1. COND replaces RENDER's chance gate: it evaluates every cond value, rolls the stock chance
itself (P = cond+1 %, as stock) and keeps the last result per column for PRE. FILL = HELD | MIDI | LATCH bit masks:
BACK held on SEQS (BKD), MIDI note 119 (MIDIB / NOFF), the piano roll FILL button (TOGGLE). FILLSYNC (defaultTask)
gives BACK a release code, ORs the masks into EFF and repaints SEQS on a change."""
import struct

import thumb as T
import phase5 as P5
import launch as LA
import touch as TC

# ---- mod state (2212 B; +2164..+2191 used here)
HELD_OFF, MIDI_OFF, LATCH_OFF, EFF_OFF = 2164, 2165, 2166, 2167
CNT_OFF, LAST_OFF = 2168, 2184            # u16 cnt[8], u8 lastres[8]
NCOL = 8
SEL_OFF = TC.SEL_OFF                       # selection: +80 column, +81 row
assert LAST_OFF + NCOL <= 2212

# ---- conditions
AB = [(1, 2), (2, 2), (1, 3), (2, 3), (3, 3), (1, 4), (2, 4), (3, 4), (4, 4)] + [(a, 8) for a in range(1, 9)]
LABELS = ["%d:%d" % ab for ab in AB] + ["1ST", "-1ST", "PRE", "-PRE", "FILL", "-FILL"]
COND0, NAB, NCOND = 100, len(AB), len(LABELS)      # stored 100..122
UI_COUNT = 1 + NCOND + 99                          # ALWAYS, the conditions, 1%..99%


def evaluate(cond, cnt, last, fill, roll):
    """Reference model: (play, new last result). roll = rand() % 100, used for 1..99 only."""
    if cond == 0 or cond >= COND0 + NCOND:
        return True, last
    if cond < COND0:
        r = roll <= cond
        return r, int(r)
    i = cond - COND0
    if i < NAB:
        a, b = AB[i]
        r = cnt % b == a - 1
        return r, int(r)
    kind, neg = (i - NAB) >> 1, (i - NAB) & 1
    if kind == 1:                                  # PRE: reads, never records
        return bool(last) != bool(neg), last
    base = cnt == 0 if kind == 0 else bool(fill)
    r = base != bool(neg)
    return r, int(r)


def ab_table():
    return b"".join(bytes([a - 1, b]) for a, b in AB)


def stored_to_ui(s):
    if s == 0:
        return 0
    if s < COND0:
        return s + NCOND
    if s < COND0 + NCOND:
        return s - COND0 + 1
    return 0                                       # unknown values show ALWAYS (and play always)


def ui_to_stored(u):
    if u == 0:
        return 0
    if u <= NCOND:
        return u - 1 + COND0
    return u - NCOND


# ---- Event "PLAY:" list (param evtcond 0x10E)
TABLE_POOL, TABLE_STOCK = 0x0808E03C, 0x080EB634               # pool word of RegisterEnum's table argument
REG_COUNT_SITE, REG_COUNT_ORIG = 0x0808DD92, bytes.fromhex("4ff48771")   # mov.w r1,#0x10e (count at [sp])
LOAD_SITE, LOAD_ORIG, LOAD_BACK = 0x080AB022, bytes.fromhex("69784ff48770"), 0x080AB028   # ldrb r1,[r5,#1]; mov.w r0,#0x10e
EDIT_SITE, EDIT_ORIG, EDIT_BACK = 0x080AAC14, bytes.fromhex("cb680593"), 0x080AAC18       # ldr r3,[r1,#0xc]; str r3,[sp,#0x14]


def pct_strings():
    """v057: the mod's own "1%".."99%" texts, packed descending ("99%" first), so no 16-byte run matches the stock
    table's ascending 4-byte slots (the public patch must not carry stock bytes). -> (blob, {n: offset in blob})."""
    blob, offs = b"", {}
    for n in range(99, 0, -1):
        offs[n] = len(blob)
        blob += b"%d%%" % n + b"\x00"
    return blob, offs


def ui_table(stock, label_vas, pct_vas):
    """123 string pointers in list order: ALWAYS (stock entry 0), the 23 conditions, 1%..99% (the mod's own texts;
    v053-v056 pointed at the stock entries 1..99, which copied 396 stock bytes into the payload)."""
    w0 = struct.unpack_from("<I", stock, TABLE_STOCK - 0x08040000)[0]
    return b"".join(struct.pack("<I", x) for x in [w0] + list(label_vas) + [pct_vas[n] for n in range(1, 100)])


def _to_ui(c, va, L, r, tag):
    c += T.cmp_imm(r, 0)
    c += T.b_cond(va + len(c), "eq", L.get(tag + "d", va))
    c += T.cmp_imm(r, COND0)
    c += T.b_cond(va + len(c), "cs", L.get(tag + "c", va))
    c += T.adds_imm8(r, NCOND)                     # 1..99 -> 24..122
    c += T.b_short(va + len(c), L.get(tag + "d", va))
    L[tag + "c"] = va + len(c)
    c += T.cmp_imm(r, COND0 + NCOND)
    c += T.b_cond(va + len(c), "cs", L.get(tag + "z", va))
    c += T.subs_imm8(r, COND0 - 1)                 # 100..122 -> 1..23
    c += T.b_short(va + len(c), L.get(tag + "d", va))
    L[tag + "z"] = va + len(c)
    c += T.movs_imm8(r, 0)
    L[tag + "d"] = va + len(c)
    return c


def _to_stored(c, va, L, r, tag):
    c += T.cmp_imm(r, 0)
    c += T.b_cond(va + len(c), "eq", L.get(tag + "d", va))
    c += T.cmp_imm(r, NCOND)
    c += T.b_cond(va + len(c), "hi", L.get(tag + "p", va))
    c += T.adds_imm8(r, COND0 - 1)                 # 1..23 -> 100..122
    c += T.b_short(va + len(c), L.get(tag + "d", va))
    L[tag + "p"] = va + len(c)
    c += T.subs_imm8(r, NCOND)                     # 24..122 -> 1..99
    L[tag + "d"] = va + len(c)
    return c


def cntset(va, L):
    """bl from the evtcond registration (was mov.w r1,#0x10e): list length [sp] = UI_COUNT, r1 = 0x10E."""
    c = T.movs_imm8(1, UI_COUNT)
    c += T.str_sp(1, 0)
    c += T.movw(1, 0x10E)
    c += T.bx(14)
    return c


def s2u(va, L):
    """LoadEvent: the PLAY widget gets the list index of the stored cond; then the displaced mov.w r0,#0x10e."""
    c = T.ldrb_imm(1, 5, 1)
    c = _to_ui(c, va, L, 1, "u")
    c += T.movw(0, 0x10E)
    c += T.bw(va + len(c), LOAD_BACK)
    return c


import colmenu as CM

# ---- BACK: press = held (SEQS), long = swallowed (SEQS), release = clear held
BTN_TABLE, BTN_N, BTN_STRIDE = 0x24009AB0, 13, 0x18     # {+8 press, +0xA release, +0xC long} codes
BACK_CODE, LONG_CODE, REL_CODE = 7, 8, 9                 # REL_CODE: unused by every button (stock 3.1.9 table)
DISP_SITE, DISP_ORIG = 0x080A2E98, bytes.fromhex("082b00f02f82")    # cmp r3,#8; beq.w long
DISP_NEXT, DISP_LONG, DISP_EXIT = 0x080A2E9E, 0x080A32FC, 0x080A3122
FILL_LO = 119                                            # v055: notes 119..126 = fill of columns 1..8 (selected row)
COL_OFF, LASTROW_OFF = 36, 108                           # mod state: COLSTATE {play row, pend row, u16} x 8; last clip row
NOFF_SITE, NOFF_ORIG = 0x0805026A, bytes.fromhex("f76817b9")        # ldr r7,[r6,#0xc]; cbnz r7
NOFF_ZERO, NOFF_GO = 0x0805026E, 0x08050274


def _bit(c, rk, rt):
    """rk = 1 << rk (rk 0..7), rt scratch."""
    c += T.movs_imm8(rt, 7)
    c += T.subs_reg(rk, rt, rk)
    c += T.movs_imm8(rt, 0x80)
    c += T.lsrs_reg(rt, rk)
    c += T.mov_reg(rk, rt)
    return c


def _row_plays(c, va, L, rs, rk, ra, rb, miss, tag):
    """Branch to `miss` unless column rk (0..7) plays the selected row's clip: COLSTATE play row == selected row
    (a selected header counts as its last clip row, +108). rs = mod state; ra, rb scratch (low registers)."""
    c += T.ldr_imm32(ra, SEL_OFF + 1)
    c += T.add_reg(ra, rs)
    c += T.ldrb_imm(ra, ra, 0)
    c += T.cmp_imm(ra, 0xFF)
    c += T.b_cond(va + len(c), "ne", L.get(tag + "r", va))
    c += T.ldr_imm32(ra, LASTROW_OFF)
    c += T.add_reg(ra, rs)
    c += T.ldrb_imm(ra, ra, 0)
    L[tag + "r"] = va + len(c)
    c += T.lsls_imm(rb, rk, 2)
    c += T.adds_reg(rb, rb, rs)
    c += T.adds_imm8(rb, COL_OFF)
    c += T.ldrb_imm(rb, rb, 0)               # play row of column rk
    c += T.cmp_reg(rb, ra)
    c += T.b_cond(va + len(c), "ne", L.get(miss, va))
    return c


def _is_seqs(c, va, L, rd, rs, miss):
    c += T.ldr_imm32(rd, CM.MODE_OFF)
    c += T.add_reg(rd, rs)
    c += T.ldrb_imm(rd, rd, 0)
    c += T.cmp_imm(rd, CM.MODE_SEQS)
    c += T.b_cond_w(va + len(c), "ne", miss)
    return c


def bkd(va, L):
    """Button dispatcher (b.w from 0x080A2E98; r0 = r4 = session, r3 = code; r1, r2, r5 free)."""
    c = T.cmp_imm(3, LONG_CODE)
    c += T.b_cond(va + len(c), "eq", L.get("long", va))
    c += T.cmp_imm(3, REL_CODE)
    c += T.b_cond(va + len(c), "eq", L.get("rel", va))
    c += T.cmp_imm(3, BACK_CODE)
    c += T.b_cond_w(va + len(c), "ne", DISP_NEXT)
    c = _is_seqs(c, va, L, 5, 0, DISP_NEXT)
    c += T.push_lo([3, 4])                   # r3 = the code (stock compares it next), r4 = session
    c = _state(c, va, L, 5, 1, "pnext")
    c += T.ldr_imm32(1, SEL_OFF)
    c += T.add_reg(1, 5)
    c += T.ldrb_imm(2, 1, 0)                 # selected column
    c += T.cmp_imm(2, NCOL)
    c += T.b_cond(va + len(c), "cs", L.get("pnext", va))
    c = _row_plays(c, va, L, 5, 2, 3, 4, "pnext", "b")   # v055: only if the column plays the selected clip
    c = _bit(c, 2, 1)
    c += T.ldr_imm32(1, HELD_OFF)
    c += T.add_reg(5, 1)
    c += T.ldrb_imm(1, 5, 0)
    c += T.orrs_reg(1, 2)
    c += T.strb_imm(1, 5, 0)
    L["pnext"] = va + len(c)
    c += T.pop_lo([3, 4])
    L["next"] = va + len(c)
    c += T.bw(va + len(c), DISP_NEXT)        # stock press path (msg 0x54, wake)
    L["long"] = va + len(c)
    c = _is_seqs(c, va, L, 5, 0, DISP_LONG)
    c += T.bw(va + len(c), DISP_EXIT)
    L["rel"] = va + len(c)
    c = _state(c, va, L, 5, 1, "exit")
    c += T.ldr_imm32(1, HELD_OFF)
    c += T.add_reg(5, 1)
    c += T.movs_imm8(1, 0)
    c += T.strb_imm(1, 5, 0)
    L["exit"] = va + len(c)
    c += T.bw(va + len(c), DISP_EXIT)
    return c


def fillsync(va, L, mcons_va, dirty_va):
    """defaultTask pass (called by C3 where MCONS was): BACK gets REL_CODE as release code; EFF = HELD|MIDI|LATCH,
    repaint SEQS when it changes; then tail-call MCONS."""
    c = T.push_lo([4, 5, 6], lr=True)        # 16 B
    c += T.ldr_imm32(0, BTN_TABLE)
    c += T.movs_imm8(1, BTN_N)
    L["scan"] = va + len(c)
    c += T.ldrh_imm(2, 0, 8)
    c += T.cmp_imm(2, BACK_CODE)
    c += T.b_cond(va + len(c), "ne", L.get("nx", va))
    c += T.ldrh_imm(2, 0, 0xA)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("nx", va))
    c += T.movs_imm8(2, REL_CODE)
    c += T.strh_imm(2, 0, 0xA)
    L["nx"] = va + len(c)
    c += T.adds_imm8(0, BTN_STRIDE)
    c += T.subs_imm8(1, 1)
    c += T.b_cond(va + len(c), "ne", L.get("scan", va))
    c = _state(c, va, L, 4, 0, "out")
    c += T.ldr_imm32(5, HELD_OFF)
    c += T.add_reg(5, 4)
    c += T.ldrb_imm(0, 5, 0)
    c += T.ldrb_imm(1, 5, MIDI_OFF - HELD_OFF)
    c += T.orrs_reg(0, 1)
    c += T.ldrb_imm(1, 5, LATCH_OFF - HELD_OFF)
    c += T.orrs_reg(0, 1)
    c += T.ldrb_imm(1, 5, EFF_OFF - HELD_OFF)
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.strb_imm(0, 5, EFF_OFF - HELD_OFF)
    c += T.bl(va + len(c), dirty_va)
    L["out"] = va + len(c)
    c += T.ldr_sp(0, 12)
    c += T.mov_reg(14, 0)
    c += T.pop_lo([4, 5, 6])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), mcons_va)
    return c


C_FILL = 11                                              # v058: bluish green #009E73 = C_COND (v053-v057: vermillion 12)
GETEVENT = 0x08063D08                                    # (container, i, out*) -> 0 past the end
FILL_V = COND0 + NAB + 4                                 # stored FILL (121); -FILL = 122


def filltile(va, L, table_va):
    """PAINT, per clip tile (r0 column k, r1 colour, r2 row n) -> r1 = C_FILL when the tile is in the selected row (a
    selected header: its last clip row), the column's fill is on (EFF) and the clip holds a FILL or -FILL note; else r1
    unchanged. table_va = the L3 record offsets (u16 per k*10+n). Keeps r4-r11; r0, r2, r3 clobbered."""
    c = T.push_lo([1, 4, 5, 6, 7], lr=True)  # 24 B
    c += T.sub_sp_imm(0x18)                  # event buffer; 48 B frame, saved r1 at sp+0x18
    c += T.mov_reg(6, 0)
    c += T.mov_reg(7, 2)
    c = _state(c, va, L, 4, 0, "ret")
    c += T.ldr_imm32(0, EFF_OFF)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(0, 0, 0)
    c += T.lsrs_reg(0, 6)
    c += T.movs_imm8(1, 1)
    c += T.ands_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))      # fill off for this column: no scan
    c += T.ldr_imm32(0, SEL_OFF + 1)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(0, 0, 0)
    c += T.cmp_imm(0, 0xFF)
    c += T.b_cond(va + len(c), "ne", L.get("hr", va))
    c += T.ldr_imm32(0, LASTROW_OFF)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(0, 0, 0)
    L["hr"] = va + len(c)
    c += T.cmp_reg(0, 7)
    c += T.b_cond(va + len(c), "ne", L.get("ret", va))      # not the selected row
    c += T.movs_imm8(0, 10)
    c += T.muls(0, 6)
    c += T.adds_reg(0, 0, 7)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.adds_reg(0, 0, 1)
    c += T.ldrh_imm(0, 0, 0)                 # record offset
    c += T.ldr_imm32(1, LA.SESSION + 0x18)
    c += T.adds_reg(5, 0, 1)                 # r5 = the record's event container
    c += T.movs_imm8(6, 0)
    L["loop"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.mov_reg(1, 6)
    c += T.add_rd_sp(2, 0)
    c += T.bl(va + len(c), GETEVENT)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.add_rd_sp(0, 0)
    c += T.ldrb_imm(0, 0, 1)                 # cond
    c += T.subs_imm8(0, FILL_V)
    c += T.cmp_imm(0, 1)
    c += T.b_cond(va + len(c), "ls", L.get("found", va))    # FILL or -FILL
    c += T.adds_imm8(6, 1)
    c += T.b_short(va + len(c), L.get("loop", va))
    L["found"] = va + len(c)
    c += T.movs_imm8(0, C_FILL)
    c += T.str_sp(0, 0x18)
    L["ret"] = va + len(c)
    c += T.add_sp_imm(0x18)
    c += T.pop_lo([1, 4, 5, 6, 7], pc=True)
    return c


# ---- v055: piano roll notes with a cond (chance or condition) draw bluish green. Each note is a 0x50-byte widget
# (grid + 0x34 + i*0x50; +0x48 event id, +0x4E spare). The two AddNote variants cache the event's cond there (the
# refresh's event copy is at caller sp+0xC, so cond = callee [sp+0x55]); the note draw picks the colour from it.
C_COND = 11                                              # bluish green #009E73 (palette 11)
NCA_SITE, NCA_ORIG = 0x080BBD9C, bytes.fromhex("129bfb67")   # ldr r3,[sp,#0x48]; str r3,[r7,#0x7c]  (AddNote, steps)
NCB_SITE, NCB_ORIG = 0x080BBE72, bytes.fromhex("129bf367")   # ldr r3,[sp,#0x48]; str r3,[r6,#0x7c]  (AddNote, ticks)
NCC_SITE, NCC_ORIG = 0x080BC968, bytes.fromhex("4a680521")   # ldr r2,[r1,#4]; movs r1,#5   (note draw, not selected)


def nc_cache(va, L, rw):
    """bl from AddNote (rw = grid + i*0x50): the displaced id store, then widget +0x4E = the event's cond. r3 only."""
    c = T.ldr_sp(3, 0x48)
    c += T.str_imm(3, rw, 0x7C)
    c += T.ldrb_w(3, 13, 0x55)
    c += T.strb_w(3, rw, 0x82)
    c += T.bx(14)
    return c


def nc_colour(va, L):
    """bl from the note draw (r0 widget, r1 ctx): r2 = ctx surface, r1 = 5 (orange) or C_COND when +0x4E != 0."""
    c = T.ldr_imm(2, 1, 4)
    c += T.ldrb_w(1, 0, 0x4E)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ne", L.get("cond", va))
    c += T.movs_imm8(1, 5)
    c += T.bx(14)
    L["cond"] = va + len(c)
    c += T.movs_imm8(1, C_COND)
    c += T.bx(14)
    return c


def noff(va, L):
    """MIDI note-off handler (b.w from 0x0805026A; r6 = event): notes FILL_LO..+7 clear their column's MIDI fill bit.
    r0-r3 are free here (stock sets them before use)."""
    c = T.ldr_imm(7, 6, 0xC)
    c += T.cmp_imm(7, FILL_LO)
    c += T.b_cond(va + len(c), "cc", L.get("st", va))
    c += T.cmp_imm(7, FILL_LO + NCOL - 1)
    c += T.b_cond(va + len(c), "hi", L.get("st", va))
    c = _state(c, va, L, 0, 1, "st")
    c += T.mov_reg(1, 7)
    c += T.subs_imm8(1, FILL_LO)             # column
    c = _bit(c, 1, 2)                        # r1 = bit
    c += T.ldr_imm32(2, MIDI_OFF)
    c += T.add_reg(2, 0)
    c += T.ldrb_imm(0, 2, 0)
    c += T.mov_reg(3, 0)
    c += T.ands_reg(3, 1)
    c += T.b_cond(va + len(c), "eq", L.get("st", va))
    c += T.subs_reg(0, 0, 1)
    c += T.strb_imm(0, 2, 0)
    L["st"] = va + len(c)
    c += T.cmp_imm(7, 0)
    c += T.b_cond_w(va + len(c), "eq", NOFF_ZERO)
    c += T.bw(va + len(c), NOFF_GO)
    return c


import topbar as TB

# ---- piano roll: the pattern-letter button (id 0xE7) becomes FILL (row layout: topbar.rolldraw)
FILL_STR = b"FILL\x00"
TXT_SITES = (0x080BFEDA, 0x080C0E94, 0x080C1392, 0x080C1532)   # bl SetText(letter, pattern letter)
CTOR_TXT_SITE = 0x080C06E8                                       # bl SetText(letter, "A") in the ctor
LETTER_REL_SITE, LETTER_REL_ORIG = 0x080C0BCA, bytes.fromhex("00f05b82")   # beq.w 0x080C1084 (letter released)
ROLL_EXIT = 0x080C0AF2                                           # handler exit: r0 = r8


def filltxt(va, L, str_va):
    c = T.ldr_imm32(1, str_va)
    c += T.bw(va + len(c), TB.SETTEXT)
    return c


def fillctor(va, L, str_va):
    """Ctor: text FILL and the selected fill of the other piano roll buttons."""
    c = T.push_lo([0], lr=True)
    c += T.ldr_imm32(1, str_va)
    c += T.bl(va + len(c), TB.SETTEXT)
    c += T.ldr_sp(0, 0)
    c += T.movs_imm8(1, TB.C_CUR)
    c += T.bl(va + len(c), TB.SELFILL)
    c += T.pop_lo([0], pc=True)
    return c


def toggle(va, L):
    """FILL released (r4 = piano roll view): flip the latched fill of the selected column, show it, exit."""
    c = _state(b"", va, L, 0, 1, "out")
    c += T.ldr_imm32(1, SEL_OFF)
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(2, 1, 0)
    c += T.cmp_imm(2, NCOL)
    c += T.b_cond(va + len(c), "cs", L.get("out", va))
    c = _bit(c, 2, 1)                        # r2 = bit
    c += T.ldr_imm32(1, LATCH_OFF)
    c += T.add_reg(1, 0)                     # r1 = &LATCH
    c += T.ldrb_imm(0, 1, 0)
    c += T.mov_reg(3, 0)
    c += T.ands_reg(3, 2)
    c += T.b_cond(va + len(c), "eq", L.get("set", va))
    c += T.subs_reg(0, 0, 2)
    c += T.strb_imm(0, 1, 0)
    c += T.movs_imm8(1, 0)
    c += T.b_short(va + len(c), L.get("show", va))
    L["set"] = va + len(c)
    c += T.orrs_reg(0, 2)
    c += T.strb_imm(0, 1, 0)
    c += T.movs_imm8(1, 1)
    L["show"] = va + len(c)
    c += T.ldr_imm32(0, TB.LETTER_OFF)
    c += T.add_reg(0, 4)
    c += T.bl(va + len(c), TB.SETSEL)
    L["out"] = va + len(c)
    c += T.movs_imm8(3, 0)
    c += T.mov_reg(8, 3)
    c += T.bw(va + len(c), ROLL_EXIT)
    return c


# ---- v054: a PLAY edit with several notes selected (piano roll relay 0x080C0288) moves the other notes by the
# edited note's step in list positions, clamped to the list (stock: stored-value delta, usat #7 -> data loss)
MD_FIELD = 7                                                    # msg 0x16F field 7 = cond
MD1_SITE, MD1_ORIG, MD1_BACK = 0x080C02FA, bytes.fromhex("baeb0003"), 0x080C02FE   # subs.w r3, sl, r0
MD2_SITE, MD2_ORIG, MD2_BACK = 0x080C03A6, bytes.fromhex("41465844"), 0x080C03AA   # mov r1, r8; add r0, fp


def md1(va, L):
    """Relay delta (b.w from 0x080C02FA; r8 field, sl new stored value, r0 old): r3 = new - old, in list positions for
    field 7, flags as SUBS (the stock bne follows). r0-r2 are free here."""
    c = T.mov_reg(1, 8)
    c += T.cmp_imm(1, MD_FIELD)
    c += T.b_cond(va + len(c), "ne", L.get("st", va))
    c += T.mov_reg(1, 10)
    c = _to_ui(c, va, L, 1, "n")
    c = _to_ui(c, va, L, 0, "o")
    c += T.subs_reg(3, 1, 0)
    c += T.bw(va + len(c), MD1_BACK)
    L["st"] = va + len(c)
    c += T.mov_reg(1, 10)
    c += T.subs_reg(3, 1, 0)
    c += T.bw(va + len(c), MD1_BACK)
    return c


def md2(va, L):
    """Relay apply (b.w from 0x080C03A6; r0 another note's stored value, fp delta, r8 field): r1 = r8 and r0 = value
    + delta, for field 7 in list positions clamped to 0..UI_COUNT-1. r2, r3 are the clamp call's arguments: kept."""
    c = T.mov_reg(1, 8)
    c += T.cmp_imm(1, MD_FIELD)
    c += T.b_cond(va + len(c), "ne", L.get("st", va))
    c = _to_ui(c, va, L, 0, "u")
    c += T.add_reg(0, 11)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "lt", L.get("lo", va))
    c += T.cmp_imm(0, UI_COUNT - 1)
    c += T.b_cond(va + len(c), "le", L.get("conv", va))
    c += T.movs_imm8(0, UI_COUNT - 1)
    c += T.b_short(va + len(c), L.get("conv", va))
    L["lo"] = va + len(c)
    c += T.movs_imm8(0, 0)
    L["conv"] = va + len(c)
    c = _to_stored(c, va, L, 0, "s")
    c += T.bw(va + len(c), MD2_BACK)
    L["st"] = va + len(c)
    c += T.add_reg(0, 11)
    c += T.bw(va + len(c), MD2_BACK)
    return c


def u2s(va, L):
    """Event edit (msg 0x16F field 7): the stored value of the chosen list index."""
    c = T.ldr_imm(3, 1, 0xC)
    c = _to_stored(c, va, L, 3, "s")
    c += T.str_sp(3, 0x14)
    c += T.bw(va + len(c), EDIT_BACK)
    return c


# ---- engine sites
SETSTEP, SETSTEP_ORIG, SETSTEP_BACK = 0x0805CDA0, bytes.fromhex("90f85810"), 0x0805CDA4   # ldrb.w r1,[r0,#0x58]
GATE, GATE_ORIG = 0x0805D3A6, bytes.fromhex("622b40f2b880")                              # cmp r3,#0x62; bls.w
PLAY, SKIP, RAND = 0x0805D3AC, 0x0805D45A, 0x080C89D4
SLOT_CUR = 0xC20                           # player: current slot (slot +0 Step Len, +4 Step Count)


def _state(c, va, L, rd, tmp, miss):
    """rd = mod state; branch to `miss` while the descriptor array is not there."""
    c += T.ldr_imm32(rd, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(rd, rd, 0)
    c += T.cmp_imm(rd, 0)
    c += T.b_cond(va + len(c), "eq", L.get(miss, va))
    c += T.ldr_imm32(tmp, LA.STATE_OFF)
    c += T.add_reg(rd, tmp)
    return c


def _col(c, va, L, rd, rp, tmp, miss):
    """rd = L3 column 0..7 of the player at rp ([rp+0x18] = 0x10000 | row << 8 | col), else branch to `miss`."""
    c += T.ldr_imm(rd, rp, 0x18)
    c += T.lsrs_imm(tmp, rd, 16)
    c += T.cmp_imm(tmp, 1)
    c += T.b_cond(va + len(c), "ne", L.get(miss, va))
    c += T.lsrs_imm(tmp, rd, 8)
    c += T.lsls_imm(tmp, tmp, 24)
    c += T.lsrs_imm(tmp, tmp, 22)            # row * 4
    c += T.lsls_imm(rd, rd, 24)
    c += T.lsrs_imm(rd, rd, 24)              # col
    c += T.adds_reg(rd, rd, tmp)
    c += T.cmp_imm(rd, NCOL)
    c += T.b_cond(va + len(c), "cs", L.get(miss, va))
    return c


def cnt(va, L):
    """SetStep entry (r0 player, r2 step): loop count of the player's column at step 0.
    Keeps r0, r2, r3 and the stack; then the displaced ldrb.w r1,[r0,#0x58]."""
    c = T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    c += T.push_lo([3, 4, 5, 6])
    c = _state(c, va, L, 4, 1, "pop")
    c = _col(c, va, L, 3, 0, 5, "pop")
    c += T.lsls_imm(5, 3, 1)
    c += T.adds_reg(5, 5, 4)
    c += T.ldr_imm32(1, CNT_OFF)
    c += T.add_reg(5, 1)                     # r5 = &cnt[col]
    c += T.ldr_imm(1, 0, 0x20)               # old step
    c += T.adds_imm8(1, 1)
    c += T.b_cond(va + len(c), "eq", L.get("reset", va))   # -1: start / launch / slot swap
    c += T.subs_imm8(1, 1)
    c += T.b_cond(va + len(c), "eq", L.get("pop", va))     # step 0 again: no new loop
    c += T.ldrh_imm(1, 5, 0)
    c += T.adds_imm8(1, 1)
    c += T.strh_imm(1, 5, 0)
    c += T.b_short(va + len(c), L.get("pop", va))
    L["reset"] = va + len(c)
    c += T.movs_imm8(1, 0)
    c += T.strh_imm(1, 5, 0)
    c += T.ldr_imm32(6, LAST_OFF)
    c += T.add_reg(6, 4)
    c += T.adds_reg(6, 6, 3)
    c += T.strb_imm(1, 6, 0)                 # PRE starts false
    L["pop"] = va + len(c)
    c += T.pop_lo([3, 4, 5, 6])
    L["out"] = va + len(c)
    c += SETSTEP_ORIG
    c += T.bw(va + len(c), SETSTEP_BACK)
    return c


def cond(va, L, ab_va):
    """RENDER's chance gate (b.w from 0x0805D3A6; r2 velocity, r5 player, cond byte at sp+0x31).
    Exits to PLAY or SKIP with r2 = velocity and sp, r4-r11 unchanged (r0, r1, r3, lr are scratch, as stock's roll)."""
    c = T.str_sp(2, 0x10)                    # the velocity slot the stock roll uses
    c += T.add_rd_sp(3, 0x30)
    c += T.ldrb_imm(3, 3, 1)                 # r3 = cond
    c += T.cmp_imm(3, 0)
    c += T.b_cond_w(va + len(c), "eq", PLAY)
    c += T.cmp_imm(3, COND0 + NCOND)
    c += T.b_cond_w(va + len(c), "cs", PLAY)
    # v055: a one-step clip (current slot's Step Count, slot +4, == 1) plays its trig conditions always
    c += T.cmp_imm(3, COND0)
    c += T.b_cond(va + len(c), "cc", L.get("multi", va))
    c += T.ldr_imm32(0, SLOT_CUR)
    c += T.add_reg(0, 5)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("multi", va))
    c += T.ldr_imm(0, 0, 4)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "eq", PLAY)
    L["multi"] = va + len(c)
    c += T.push_lo([4, 5, 6, 7])             # 16 B: velocity slot now at sp+0x20
    c += T.movs_imm8(7, NCOL)                # r7 = column, NCOL = none
    c = _state(c, va, L, 4, 0, "nost")
    c = _col(c, va, L, 0, 5, 1, "havecol")
    c += T.mov_reg(7, 0)
    c += T.b_short(va + len(c), L.get("havecol", va))
    L["nost"] = va + len(c)
    c += T.movs_imm8(4, 0)
    L["havecol"] = va + len(c)
    c += T.movs_imm8(6, 0)                   # r6 = loop count (0 without a column)
    c += T.cmp_imm(7, NCOL)
    c += T.b_cond(va + len(c), "eq", L.get("gotcnt", va))
    c += T.lsls_imm(0, 7, 1)
    c += T.adds_reg(0, 0, 4)
    c += T.ldr_imm32(1, CNT_OFF)
    c += T.add_reg(0, 1)
    c += T.ldrh_imm(6, 0, 0)
    L["gotcnt"] = va + len(c)
    c += T.cmp_imm(3, COND0)
    c += T.b_cond(va + len(c), "cs", L.get("ext", va))
    # chance, as stock: rand() % 100 <= cond
    c += T.mov_reg(5, 3)
    c += T.bl(va + len(c), RAND)
    c += T.movs_imm8(1, 100)
    c += T.udiv(2, 0, 1)
    c += T.muls(2, 1)
    c += T.subs_reg(0, 0, 2)
    c += T.movs_imm8(1, 1)
    c += T.cmp_reg(0, 5)
    c += T.b_cond(va + len(c), "ls", L.get("rec", va))
    c += T.movs_imm8(1, 0)
    c += T.b_short(va + len(c), L.get("rec", va))
    L["ext"] = va + len(c)
    c += T.subs_imm8(3, COND0)
    c += T.cmp_imm(3, NAB)
    c += T.b_cond(va + len(c), "cs", L.get("flags", va))
    # A:B: cnt % B == A - 1
    c += T.ldr_imm32(0, ab_va)
    c += T.lsls_imm(1, 3, 1)
    c += T.adds_reg(0, 0, 1)
    c += T.ldrb_imm(1, 0, 0)                 # A - 1
    c += T.ldrb_imm(2, 0, 1)                 # B
    c += T.udiv(0, 6, 2)
    c += T.muls(0, 2)
    c += T.subs_reg(0, 6, 0)                 # cnt % B
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "eq", L.get("yes", va))
    c += T.movs_imm8(1, 0)
    c += T.b_short(va + len(c), L.get("rec", va))
    L["yes"] = va + len(c)
    c += T.movs_imm8(1, 1)
    c += T.b_short(va + len(c), L.get("rec", va))
    L["flags"] = va + len(c)
    c += T.subs_imm8(3, NAB)                 # 0..5
    c += T.movs_imm8(2, 1)
    c += T.ands_reg(2, 3)                    # r2 = negate
    c += T.lsrs_imm(3, 3, 1)                 # 0 1ST, 1 PRE, 2 FILL
    c += T.cmp_imm(3, 1)
    c += T.b_cond(va + len(c), "eq", L.get("pre", va))
    c += T.b_cond(va + len(c), "hi", L.get("fill", va))
    c += T.movs_imm8(1, 0)                   # 1ST: cnt == 0
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "ne", L.get("neg", va))
    c += T.movs_imm8(1, 1)
    c += T.b_short(va + len(c), L.get("neg", va))
    L["fill"] = va + len(c)
    c += T.movs_imm8(1, 0)
    c += T.cmp_imm(7, NCOL)
    c += T.b_cond(va + len(c), "eq", L.get("neg", va))
    c += T.ldr_imm32(0, HELD_OFF)
    c += T.add_reg(0, 4)
    c += T.ldrb_imm(1, 0, 0)
    c += T.ldrb_imm(6, 0, 1)
    c += T.orrs_reg(1, 6)
    c += T.ldrb_imm(6, 0, 2)
    c += T.orrs_reg(1, 6)
    c += T.lsrs_reg(1, 7)
    c += T.movs_imm8(6, 1)
    c += T.ands_reg(1, 6)
    L["neg"] = va + len(c)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("rec", va))
    c += T.movs_imm8(0, 1)
    c += T.subs_reg(1, 0, 1)
    c += T.b_short(va + len(c), L.get("rec", va))
    L["pre"] = va + len(c)
    c += T.movs_imm8(1, 0)
    c += T.cmp_imm(7, NCOL)
    c += T.b_cond(va + len(c), "eq", L.get("preneg", va))
    c += T.ldr_imm32(0, LAST_OFF)
    c += T.add_reg(0, 4)
    c += T.adds_reg(0, 0, 7)
    c += T.ldrb_imm(1, 0, 0)
    L["preneg"] = va + len(c)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("decide", va))
    c += T.movs_imm8(0, 1)
    c += T.subs_reg(1, 0, 1)
    c += T.b_short(va + len(c), L.get("decide", va))
    L["rec"] = va + len(c)
    c += T.cmp_imm(7, NCOL)
    c += T.b_cond(va + len(c), "eq", L.get("decide", va))
    c += T.ldr_imm32(0, LAST_OFF)
    c += T.add_reg(0, 4)
    c += T.adds_reg(0, 0, 7)
    c += T.strb_imm(1, 0, 0)
    L["decide"] = va + len(c)
    c += T.pop_lo([4, 5, 6, 7])
    c += T.ldr_sp(2, 0x10)                   # velocity back
    c += T.cmp_imm(1, 0)
    c += T.b_cond_w(va + len(c), "eq", SKIP)
    c += T.bw(va + len(c), PLAY)
    return c
