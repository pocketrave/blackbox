"""v065/v066: per-clip colour and label ("clip decoration") - reference model and constants.

Two new per-clip params live in the clip record's param list (id, value pairs, capacity 64):
COLOUR_ID (0x19A) = colour index 0..10 (0 = Default, 1..10 = COLOURS[1..10]); LAB0_ID / LAB1_ID (0x19D / 0x19E) = the
label text, 8 ASCII bytes packed little-endian into two u32 words (NUL / control character ends it).
The record ctor adds its 11 stock params with AddParam; the mod replaces the 11th `bl AddParam` (id 0x7A) at CTOR_SITE
with a hook that runs AddParam itself, then adds the 3 new params (a full list drops them silently).

Clip fill: colour 1..10 uses palette entry ENTRIES[colour - 1] (new entries, see palettes.CVD); colour 0 keeps the stock
fill (C_NOTES with notes, C_EMPTY without). Mod state: KBDF_OFF (keyboard flag) and descriptor slot 0x1F3 (+4..+23:
2 x pointer table at +4, 9-byte text buffer at +12); nothing may touch a slot's tag field (+24..+27).

Colour row (v065, Task 5): COLOUR_ID sits in the clip page row lists (LIST_SEQ_FREE / LIST_MIDI_FREE). One source
for the record (ruling): RD2 (read) and CDEDIT (write) both take the record from CDREC (selected clip k = mod state
+80, n = +81 -> SESSION + L3 table[k*10+n]), not from RD2's active-layer path, so the shown value and the written
value are on the same record by construction. CDEDIT writes the record only (SetParam / AddParam): no SetCellParam,
no engine post (the engine ignores unknown cell ids anyway).

This module holds the model and the constants (all addresses are stock 3.1.9, base 0x08040000). The Thumb-2 cave
generators are added by later tasks."""
import struct

import thumb as T
import phase5 as P5
import launch as LA
import paint as PT
import colname as CN

COLOUR_ID, LAB0_ID, LAB1_ID = 0x19A, 0x19D, 0x19E
LABEL_MAX = 8
KBDF_OFF = 2194                                     # mod state: keyboard flag
PREV_FALLBACK = 0x2C                                # SEQS: KBDF value when the previous mode reads 0
SLOT_1F3 = 0x1F3 * 28                               # descriptor array offset of slot 0x1F3 (free +4..+23)
LTAB_IN_SLOT, LBUF_IN_SLOT = 4, 12                  # 2 x pointer table, text buffer (8 + NUL)

# stock 3.1.9 functions
ADDPARAM = 0x08093EF6                               # (r0 record, r1 id, r2 value); no return; drops when full (cap 64)
GETPARAM = 0x08093E9C
SETPARAM = 0x08093ECC                               # (r0 record, r1 id, r2 value); writes +4 of the entry with that id

# record ctor: the 11th `bl AddParam` (id 0x7A) is replaced by the hook
CTOR_SITE = 0x08094426
CTOR_ORIG = bytes.fromhex("fff766fd")
CTOR_BACK = 0x0809442A
CTOR_REC_REG = "r4"                                 # the record (r5 also live; r0-r3, ip free)

# free space in the stock lists (3.1.9)
LIST_SEQ_FREE = 0x080EEF30
LIST_MIDI_FREE = 0x080EEEE8

COLOURS = [("Default", None), ("Slate", 0x42556B), ("Denim", 0x29596B), ("Teal", 0x295D5A), ("Sage", 0x395942),
           ("Moss", 0x4A5931), ("Ochre", 0x635121), ("Clay", 0x734531), ("Rose", 0x6B454A), ("Mauve", 0x634963),
           ("Plum", 0x5A496B)]
ENTRIES = (18, 19, 20, 21, 22, 23, 25, 26, 28, 33)
C_EMPTY, C_NOTES = 1, 9


def pack_label(text):
    b = text.encode("ascii", "replace")[:LABEL_MAX].ljust(LABEL_MAX, b"\0")
    return int.from_bytes(b[:4], "little"), int.from_bytes(b[4:], "little")


def unpack_label(w0, w1):
    out = b""
    for ch in (w0 & 0xFFFFFFFF).to_bytes(4, "little") + (w1 & 0xFFFFFFFF).to_bytes(4, "little"):
        if not 0x20 <= ch <= 0x7E:
            break
        out += bytes([ch])
    return out.decode("ascii")


def fill_entry(colour, has_notes):
    if 1 <= colour <= len(ENTRIES):
        return ENTRIES[colour - 1]
    return C_NOTES if has_notes else C_EMPTY


# ---------------------------------------------------------------- Task 4: descriptors at boot, params in every record
DESCP = 0x2401F4FC                                  # -> descriptor array (500 x 28 B)
DESC_SZ = 28
INT_MIN, INT_MAX = -2**31, 2**31 - 1
LBUF_INIT = 0x2D                                    # "-" + NUL (word store: "-", 0, 0, 0)
_STRS = ("Colour:", "Label:", "clipcol", "cliplab0", "cliplab1")


def _blob_layout():
    """(strings bytes, {name: offset}, table offset): 11 colour names + _STRS, NUL-terminated, then the 4-aligned
    11-pointer name table."""
    out, offs = b"", {}
    for s in [n for n, _ in COLOURS] + list(_STRS):
        offs[s] = len(out)
        out += s.encode("ascii") + bytes(1)
    tab = (len(out) + 3) & ~3
    return out.ljust(tab, bytes(1)), offs, tab


def names_blob(va):
    """Flash rodata at `va` (4-aligned): the strings, then CDNAMES (11 pointers to the colour names)."""
    strs, offs, tab = _blob_layout()
    return strs + struct.pack("<11I", *(va + offs[n] for n, _ in COLOURS))


def blob_addr(va, name):
    """Address of string `name` (or "CDNAMES" for the table) in the blob at `va`."""
    _, offs, tab = _blob_layout()
    return va + (tab if name == "CDNAMES" else offs[name])


def _fill_desc(c, pid, kind, label, table_reg, table, count, lo, hi, tag):
    """r2 = descriptor array; r3 = descriptor pid; r0 scratch. table_reg (low reg) overrides table."""
    c += T.ldr_imm32(0, pid * DESC_SZ)
    c += T.adds_reg(3, 2, 0)
    c += T.ldr_imm32(0, pid | kind << 16)            # u16 id, u8 kind, u8 pad 0
    c += T.str_imm(0, 3, 0)
    for off, v in ((4, label), (8, table), (12, count), (16, lo), (20, hi), (24, tag)):
        if off == 8 and table_reg is not None:
            c += T.str_imm(table_reg, 3, 8)
            continue
        v &= 0xFFFFFFFF
        c += T.movs_imm8(0, v) if v < 256 else T.ldr_imm32(0, v)
        c += T.str_imm(0, 3, off)
    return c


def cddesc(va, L, blob_va):
    """CDDESC (bl from the registrar epilogue, after MODDESC): fill descriptors COLOUR_ID, LAB0_ID, LAB1_ID, the
    label table LTAB (2 pointers, both to LBUF) and LBUF = "-". Leaf; r0-r3 only; nothing when [DESCP] == 0.

    Kind choice: LAB0_ID is kind 5 (enum, the clip page shows LBUF through the 2-entry LTAB) at all times. The
    preset writer 0x08095328 formats every id except 0xF8/0xF9 with "%d" (0x0804A3B4), the reader 0x08095EC0 parses
    it with "%d" (0x0804A03C) and SetParam 0x08093ECC does not clamp to min/max, so a packed label word (> max 1)
    round-trips; no kind switch in RD2 / SH2 is needed.
    Slot 0x1F3: only +4..+15 are written (LTAB +4..+11, LBUF word +12..+15); +0..+3 (modcc mbox[7]) and the tag
    field +24..+27 stay untouched."""
    c = T.ldr_imm32(2, DESCP)
    c += T.ldr_imm(2, 2, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(0, SLOT_1F3 + LBUF_IN_SLOT)
    c += T.adds_reg(1, 2, 0)                         # r1 = LBUF
    c += T.movs_imm8(0, LBUF_INIT)
    c += T.str_imm(0, 1, 0)                          # "-", NUL
    c += T.ldr_imm32(0, SLOT_1F3 + LTAB_IN_SLOT)
    c += T.adds_reg(0, 2, 0)                         # r0 = LTAB
    c += T.str_imm(1, 0, 0)
    c += T.str_imm(1, 0, 4)
    c += T.mov_reg(1, 0)                             # r1 = LTAB (LAB0 table)
    c = _fill_desc(c, LAB0_ID, 5, blob_addr(blob_va, "Label:"), 1, None, 2, 0, 1,
                   blob_addr(blob_va, "cliplab0"))
    c = _fill_desc(c, COLOUR_ID, 5, blob_addr(blob_va, "Colour:"), None, blob_addr(blob_va, "CDNAMES"),
                   len(COLOURS), 0, len(COLOURS) - 1, blob_addr(blob_va, "clipcol"))
    c = _fill_desc(c, LAB1_ID, 1, 0, None, 0, 0, INT_MIN, INT_MAX, blob_addr(blob_va, "cliplab1"))
    L["out"] = va + len(c)
    c += T.bx(14)
    return c


def cdadd(va, L):
    """CDADD (b.w at CTOR_SITE, replaces the 11th `bl AddParam`; r0 = r4 = record, r1 = 0x7A, r2 = 0): the displaced
    AddParam(r4, 0x7A, 0), then AddParam(r4, id, 0) for COLOUR_ID, LAB0_ID, LAB1_ID, then b.w CTOR_BACK.
    r4 / r5 are saved around the calls (AddParam keeps r4 anyway); LR is not live at CTOR_BACK (`b` to
    `ldrb r3,[r5]; strb r3,[r4,#8]; pop {r3,r4,r5,pc}`). 8-B push keeps the stack 8-aligned."""
    c = T.push_lo([4, 5])
    c += T.bl(va + len(c), ADDPARAM)                 # displaced: AddParam(r4, 0x7A, 0)
    for pid in (COLOUR_ID, LAB0_ID, LAB1_ID):
        c += T.mov_reg(0, 4)
        c += T.movw(1, pid)
        c += T.movs_imm8(2, 0)
        c += T.bl(va + len(c), ADDPARAM)
    c += T.pop_lo([4, 5])
    c += T.bw(va + len(c), CTOR_BACK)
    return c


# ---------------------------------------------------------------- Task 5: Colour row on the clip page
COLOUR_MAX = len(COLOURS) - 1                       # 10


def cdrec(va, L, table_va):
    """CDREC (void) -> r0 = record of the selected clip (mod state +80 k, +81 n): SESSION + u16 table[k*10+n];
    0 when there is no descriptor array, k > 7 or n > 9 (a header selection has n = 0xFF). Leaf; r0-r3 only."""
    c = T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("zero", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + PT.SEL_OFF)
    c += T.add_reg(0, 1)
    c += T.ldrb_imm(1, 0, 0)                         # k
    c += T.ldrb_imm(2, 0, 1)                         # n
    c += T.cmp_imm(1, 7)
    c += T.b_cond(va + len(c), "hi", L.get("zero", va))
    c += T.cmp_imm(2, 9)
    c += T.b_cond(va + len(c), "hi", L.get("zero", va))
    c += T.movs_imm8(0, 10)
    c += T.muls(0, 1)
    c += T.adds_reg(0, 0, 2)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.adds_reg(0, 0, 1)
    c += T.bx(14)
    L["zero"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.bx(14)
    return c


def cdhas(va, L):
    """CDHAS (r0 record, r1 id) -> r0 = 1 if the record's param list (+4 ptr, +0xA u16 count, 8-B entries
    {u16 id, s32 value}) holds the id, else 0. Leaf; r0-r3 only."""
    c = T.ldrh_imm(2, 0, 0xA)                        # count
    c += T.ldr_imm(0, 0, 4)                          # list
    L["loop"] = va + len(c)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("no", va))
    c += T.ldrh_imm(3, 0, 0)
    c += T.cmp_reg(3, 1)
    c += T.b_cond(va + len(c), "eq", L.get("yes", va))
    c += T.adds_imm8(0, 8)
    c += T.subs_imm8(2, 1)
    c += T.b_short(va + len(c), L.get("loop", va))
    L["no"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.bx(14)
    L["yes"] = va + len(c)
    c += T.movs_imm8(0, 1)
    c += T.bx(14)
    return c


def cdedit(va, L, cdrec_va, cdhas_va, labfill_va=None, empty_va=None):
    """CDEDIT (b.w from EDITW's non-Name path; r0 = row owner, r2 = id, r4 = page, r5 = msg {+0xC value, +0x10 id}).
    id != COLOUR_ID: the displaced `ldrh r1,[r0,#0x38]`, b.w EDIT_BACK (stock post).
    id == COLOUR_ID: value = [r5+0xC] clamped 0..10; record = CDREC; record 0 -> nothing; CDHAS ? SetParam :
    AddParam (record, COLOUR_ID, value); v067: then [SESSION + DIRTY] = 1 (preset modified); then b.w EDIT_POSTED (no
    0x6E post: no SetCellParam, no engine).
    EDIT_POSTED reads [r5+0x10] and r4 (page): r4 / r5 / sp are kept (the same state the Name path leaves); LR is
    not live there (the page handler saved it in its prologue).
    v066 (labfill_va / empty_va set): id == LAB0_ID -> the label keyboard path (_cdedit_label); None emits the v065
    bytes."""
    c = T.ldr_imm32(3, COLOUR_ID)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "eq", L.get("colour", va))
    if labfill_va is not None:
        c += T.ldr_imm32(3, LAB0_ID)
        c += T.cmp_reg(2, 3)
        c += T.b_cond_w(va + len(c), "eq", L.get("label", va))
    c += T.ldrh_imm(1, 0, 0x38)                      # displaced: ldrh r1, [r0, #0x38]
    c += T.bw(va + len(c), CN.EDIT_BACK)
    L["colour"] = va + len(c)
    c += T.push_lo([4, 5])
    c += T.bl(va + len(c), cdrec_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.mov_reg(4, 0)                             # r4 = record
    c += T.ldr_imm32(1, COLOUR_ID)
    c += T.bl(va + len(c), cdhas_va)
    c += T.mov_reg(3, 0)                             # r3 = has
    c += T.ldr_imm(2, 5, 0xC)                        # value (signed)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ge", L.get("pos", va))
    c += T.movs_imm8(2, 0)
    L["pos"] = va + len(c)
    c += T.cmp_imm(2, COLOUR_MAX)
    c += T.b_cond(va + len(c), "le", L.get("ok", va))
    c += T.movs_imm8(2, COLOUR_MAX)
    L["ok"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.ldr_imm32(1, COLOUR_ID)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("add", va))
    c += T.bl(va + len(c), SETPARAM)
    c += T.b_short(va + len(c), L.get("mod", va))
    L["add"] = va + len(c)
    c += T.bl(va + len(c), ADDPARAM)
    L["mod"] = va + len(c)
    c += LA.set_modified(0, 1)                       # v067: a record was written -> preset modified (PSET Save)
    L["out"] = va + len(c)
    c += T.pop_lo([4, 5])
    c += T.bw(va + len(c), CN.EDIT_POSTED)
    if labfill_va is not None:
        L["label"] = va + len(c)
        c += _cdedit_label(va + len(c), L, labfill_va, empty_va)
    return c


def _cdedit_label(va, L, labfill_va, empty_va):
    """CDEDIT label branch (r4 = page, r5 = msg, sp = the page handler's frame, as in colname.editw's Name path):
    LABFILL (LBUF = the selected clip's label or "-"); KBDF = [SESSION + PREV_MODE] (the page's previous UI mode,
    nonzero: the clip page is reached from the piano roll; 0 -> PREV_FALLBACK 0x2C SEQS); the Name flag (mod state
    +107) = 0; KbdSetText(kbd, LBUF, or "" when LBUF is "-"); send {0xD0}
    from the frame area sp+0x1C..+0x33 exactly like editw; b.w EDIT_POSTED. No record write here (LABRET does it).
    Nothing but LABFILL when [DESC_ARRAY_PTR] == 0. Keeps r4 / r5 / sp; LR is not live."""
    c = T.bl(va, labfill_va)                         # keeps r4-r11
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("lposted", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + KBDF_OFF)
    c += T.adds_reg(1, 0, 1)                         # r1 = &KBDF
    c += T.ldr_imm32(2, LA.SESSION + CN.PREV_MODE)
    c += T.ldrb_imm(2, 2, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("lprev", va))
    c += T.movs_imm8(2, PREV_FALLBACK)               # prev 0: BACK -> SEQS (and KBDF must be nonzero)
    L["lprev"] = va + len(c)
    c += T.strb_imm(2, 1, 0)                         # KBDF = previous mode (LABRET restores it)
    c += T.movs_imm8(2, 0)
    c += T.ldr_imm32(3, LA.STATE_OFF + CN.KBD_OFF)
    c += T.adds_reg(3, 0, 3)
    c += T.strb_imm(2, 3, 0)                         # the column Name keyboard is not waiting
    c += T.ldr_imm32(1, SLOT_1F3 + LBUF_IN_SLOT)
    c += T.add_reg(1, 0)                             # r1 = LBUF
    c += T.ldrb_imm(2, 1, 0)
    c += T.cmp_imm(2, 0x2D)
    c += T.b_cond(va + len(c), "ne", L.get("ltext", va))
    c += T.ldrb_imm(2, 1, 1)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "ne", L.get("ltext", va))
    c += T.ldr_imm32(1, empty_va)                    # "-" (no label) -> "" (a NUL byte in flash)
    L["ltext"] = va + len(c)
    c += T.ldr_imm32(0, CN.ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.ldr_imm32(2, CN.KBD)
    c += T.add_reg(0, 2)
    c += T.bl(va + len(c), CN.KBD_SET)
    c += T.movs_imm8(0, 0)
    for off in (0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30):
        c += T.str_sp(0, off)
    c += T.movs_imm8(0, 0xD0)
    c += T.add_rd_sp(1, 0x1C)
    c += T.strh_imm(0, 1, 0)
    c += T.ldr_imm32(0, CN.MSG_VT)
    c += T.str_sp(0, 0x20)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), CN.SEND)
    L["lposted"] = va + len(c)
    c += T.bw(va + len(c), CN.EDIT_POSTED)
    return c


# ---------------------------------------------------------------- Task 9: keyboard result (LABRET)
def labret(va, L, sh2_va, cdrec_va, cdhas_va, labfill_va):
    """LABRET (b.w from NAMERET, in front of SH2; the page's 0xD4 = shown again): NAMERET's contract - all registers
    and sp handed to SH2 unchanged, 8-aligned frame (36 + 260 B), result buffer [sp..+259] >= 256 B (KbdGetResult
    strncpy's 255 bytes + NUL).
    KBDF == 0 -> SH2 (no work). Else [SESSION + PREV_MODE] = KBDF (the clip page's previous mode before the keyboard;
    after the round trip it is 0x10 and BACK would reopen the keyboard), KBDF = 0, KbdGetResult(kbd, buffer).
    Enter (1): the first 8 bytes, cut at the first byte outside 0x20..0x7E, the rest zero, as two little-endian
    words; record = CDREC (0 -> no write); for LAB0_ID / LAB1_ID: CDHAS ? SetParam : AddParam; v067: then
    [SESSION + DIRTY] = 1 (preset modified). Always LABFILL."""
    c = T.push_lo([0, 1, 2, 3, 4, 5, 6, 7], lr=True)   # 36 B
    c += T.sub_sp_imm(260)                   # 296: 8-aligned; [sp..+259] the keyboard result
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("done", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + KBDF_OFF)
    c += T.add_reg(4, 0)                     # r4 = &KBDF
    c += T.ldrb_imm(5, 4, 0)
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("done", va))
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 4, 0)                 # KBDF = 0
    c += T.ldr_imm32(0, LA.SESSION + CN.PREV_MODE)
    c += T.strb_imm(5, 0, 0)                 # previous mode back (BACK -> piano roll, not the keyboard)
    c += T.ldr_imm32(0, CN.ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.ldr_imm32(1, CN.KBD)
    c += T.add_reg(0, 1)
    c += T.add_rd_sp(1, 0)
    c += T.bl(va + len(c), CN.KBD_GET)
    c += T.cmp_imm(0, 1)
    c += T.b_cond_w(va + len(c), "ne", L.get("refill", va))
    c += T.add_rd_sp(3, 0)                   # r3 = buffer
    c += T.movs_imm8(1, 0)                   # r1 = length
    L["scan"] = va + len(c)
    c += T.adds_reg(0, 3, 1)
    c += T.ldrb_imm(2, 0, 0)
    c += T.subs_imm8(2, 0x20)
    c += T.cmp_imm(2, 0x7E - 0x20)
    c += T.b_cond(va + len(c), "hi", L.get("zero", va))   # unsigned: < 0x20 or > 0x7E ends the text
    c += T.adds_imm8(1, 1)
    c += T.cmp_imm(1, LABEL_MAX)
    c += T.b_cond(va + len(c), "cc", L.get("scan", va))
    L["zero"] = va + len(c)
    c += T.cmp_imm(1, LABEL_MAX)
    c += T.b_cond(va + len(c), "cs", L.get("packed", va))
    c += T.adds_reg(0, 3, 1)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 0, 0)
    c += T.adds_imm8(1, 1)
    c += T.b_short(va + len(c), L.get("zero", va))
    L["packed"] = va + len(c)
    c += T.ldr_sp(6, 0)                      # r6 = LAB0 (bytes 0..3)
    c += T.ldr_sp(7, 4)                      # r7 = LAB1 (bytes 4..7)
    c += T.bl(va + len(c), cdrec_va)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("refill", va))
    c += T.mov_reg(4, 0)                     # r4 = record
    for i, (pid, reg) in enumerate(((LAB0_ID, 6), (LAB1_ID, 7))):
        c += T.mov_reg(0, 4)
        c += T.movw(1, pid)
        c += T.bl(va + len(c), cdhas_va)
        c += T.mov_reg(5, 0)                 # r5 = has
        c += T.mov_reg(0, 4)
        c += T.movw(1, pid)
        c += T.mov_reg(2, reg)
        c += T.cmp_imm(5, 0)
        c += T.b_cond(va + len(c), "eq", L.get("add%d" % i, va))
        c += T.bl(va + len(c), SETPARAM)
        c += T.b_short(va + len(c), L.get("next%d" % i, va))
        L["add%d" % i] = va + len(c)
        c += T.bl(va + len(c), ADDPARAM)
        L["next%d" % i] = va + len(c)
    c += LA.set_modified(0, 1)               # v067: label written -> preset modified (not on Cancel / no clip)
    L["refill"] = va + len(c)
    c += T.bl(va + len(c), labfill_va)
    L["done"] = va + len(c)
    c += T.add_sp_imm(260)
    c += T.ldr_sp(0, 32)
    c += T.mov_reg(14, 0)                    # lr back
    c += T.pop_lo([0, 1, 2, 3, 4, 5, 6, 7])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), sh2_va)
    return c


# ---------------------------------------------------------------- Task 6: grid fill (CLIPCOL in PAINT)
def clipcol(va, L, table_va):
    """CLIPCOL (PAINT, per clip tile; r0 column k, r1 colour, r2 row n) -> r1 = ENTRIES[c - 1] when the clip record's
    COLOUR_ID value c is 1..10, else r1 unchanged (GetParam gives 0 for a missing id). Record = SESSION + u16
    table[k*10+n] (table_va = the L3 record offsets). Same convention as trig.filltile: keeps r4-r11; r0, r2, r3, ip
    clobbered. 8-B push keeps PAINT's 8-aligned sp aligned at the GetParam call. The 10-byte entry table follows the
    code."""
    c = T.push_lo([1], lr=True)                      # [sp] = r1 (the result slot)
    c += T.movs_imm8(3, 10)
    c += T.muls(0, 3)
    c += T.adds_reg(0, 0, 2)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)                         # record offset
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.adds_reg(0, 0, 1)                         # r0 = record
    c += T.ldr_imm32(1, COLOUR_ID)
    c += T.bl(va + len(c), GETPARAM)
    c += T.subs_imm8(0, 1)
    c += T.cmp_imm(0, len(ENTRIES) - 1)
    c += T.b_cond(va + len(c), "hi", L.get("out", va))   # unsigned: 0 (Default), > 10 and < 0 keep r1
    c += T.ldr_imm32(1, L.get("tab", va))
    c += T.add_reg(1, 0)
    c += T.ldrb_imm(1, 1, 0)
    c += T.str_sp(1, 0)
    L["out"] = va + len(c)
    c += T.pop_lo([1], pc=True)
    L["tab"] = va + len(c)
    c += bytes(ENTRIES) + bytes(len(ENTRIES) % 2)
    return c


# ---------------------------------------------------------------- Task 8: Label row (LABFILL)
def labfill(va, L, cdrec_va):
    """LABFILL (void): LBUF = [DESCP] + SLOT_1F3 + LBUF_IN_SLOT = unpack_label(LAB0, LAB1) of the selected clip's
    record (CDREC), NUL-terminated, or "-" when there is no clip or the text is empty. Writes at most the 9 bytes
    +12..+20 of slot 0x1F3 (never +0..+3 modcc mailbox, never +21..+27 / the tag field +24..+27). Nothing when
    [DESCP] == 0. Calls CDREC and GetParam x2; keeps r4-r11 (16-B push keeps sp 8-aligned)."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.ldr_imm32(0, DESCP)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.ldr_imm32(1, SLOT_1F3 + LBUF_IN_SLOT)
    c += T.adds_reg(4, 0, 1)                         # r4 = LBUF
    c += T.bl(va + len(c), cdrec_va)                 # r0 = record or 0 (r0-r3 only)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("dash", va))
    c += T.mov_reg(5, 0)                             # r5 = record
    c += T.ldr_imm32(1, LAB0_ID)
    c += T.bl(va + len(c), GETPARAM)
    c += T.mov_reg(6, 0)                             # r6 = LAB0
    c += T.mov_reg(0, 5)
    c += T.ldr_imm32(1, LAB1_ID)
    c += T.bl(va + len(c), GETPARAM)                 # r0 = LAB1
    for i in range(4):                               # bytes 0..7 (little-endian); byte stores, no alignment need
        c += T.strb_imm(6, 4, i)
        c += T.strb_imm(0, 4, 4 + i)
        if i < 3:
            c += T.lsrs_imm(6, 6, 8)
            c += T.lsrs_imm(0, 0, 8)
    c += T.movs_imm8(1, 0)                           # r1 = length
    L["loop"] = va + len(c)
    c += T.adds_reg(3, 4, 1)
    c += T.ldrb_imm(2, 3, 0)
    c += T.subs_imm8(2, 0x20)
    c += T.cmp_imm(2, 0x7E - 0x20)
    c += T.b_cond(va + len(c), "hi", L.get("end", va))  # unsigned: < 0x20 or > 0x7E ends the text
    c += T.adds_imm8(1, 1)
    c += T.cmp_imm(1, LABEL_MAX)
    c += T.b_cond(va + len(c), "cc", L.get("loop", va))
    L["end"] = va + len(c)
    c += T.adds_reg(3, 4, 1)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 3, 0)                         # NUL at [length] (byte 8 at most)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ne", L.get("out", va))
    L["dash"] = va + len(c)
    c += T.movs_imm8(0, 0x2D)
    c += T.strb_imm(0, 4, 0)                         # "-"
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 4, 1)                         # NUL
    L["out"] = va + len(c)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c


# ---------------------------------------------------------------- Task 10: label on the grid (CLIPLAB in PAINT)
LAB_W, LAB_H, LAB_COLOUR = 6 * LABEL_MAX, 8, 3      # rect 48 x 8 (8 chars of the 6x8 font), palette 3 = white
LAB_DX, LAB_DY = 3, 29                              # PAINT: rect = {x + 3, y + 29} for the tile {x + 1, y, 39, 39}
SCREEN_W = 320                                      # the pixel writer 0x0808F524 clips y only: x >= 320 wraps a row


def cliplab(va, L, table_va):
    """CLIPLAB (PAINT, per clip tile; r0 k, r1 n, r2 x | y << 16 = the text rect's bottom-left (y-up), r3 surface):
    the clip's label (LAB0 / LAB1 of record SESSION + u16 table[k*10+n]) as TEXT1X(buf, {x, y, w, 8}, 3, surface),
    w = min(48, 320 - x): the stock pixel writer clips y but not x (x >= 320 lands on the next framebuffer row, at the
    left edge), so whole chars past the screen's right edge are dropped (column 7: 6 chars).
    buf = 12 B on the stack: the 8 bytes, cut at the first byte outside 0x20..0x7E, NUL-terminated; empty -> no call.
    TEXT1X draws glyph row 0 at rect.y + 7 and the last row at rect.y (no clip to the rect height; the rect width
    only caps the char count, 48 = 8 x 6). Keeps r4-r11; r0-r3, ip clobbered. Frame 16 + 32 = 48 B: sp stays
    8-aligned at the GetParam and TEXT1X calls ([sp+0..15] rect, [sp+16..27] buf)."""
    c = T.push_lo([4, 5, 6], lr=True)
    c += T.sub_sp_imm(32)
    c += T.mov_reg(4, 3)                             # r4 = surface
    c += T.mov_reg(5, 2)                             # r5 = x | y << 16
    c += T.movs_imm8(3, 10)
    c += T.muls(0, 3)
    c += T.adds_reg(0, 0, 1)
    c += T.lsls_imm(0, 0, 1)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldrh_imm(0, 1, 0)                         # record offset
    c += T.ldr_imm32(1, LA.SESSION)
    c += T.adds_reg(6, 0, 1)                         # r6 = record
    c += T.mov_reg(0, 6)
    c += T.ldr_imm32(1, LAB0_ID)
    c += T.bl(va + len(c), GETPARAM)
    c += T.str_sp(0, 16)                             # bytes 0..3 (little-endian)
    c += T.mov_reg(0, 6)
    c += T.ldr_imm32(1, LAB1_ID)
    c += T.bl(va + len(c), GETPARAM)
    c += T.str_sp(0, 20)                             # bytes 4..7
    c += T.add_rd_sp(3, 16)                          # r3 = buf
    c += T.movs_imm8(1, 0)                           # r1 = length
    L["loop"] = va + len(c)
    c += T.adds_reg(0, 3, 1)
    c += T.ldrb_imm(2, 0, 0)
    c += T.subs_imm8(2, 0x20)
    c += T.cmp_imm(2, 0x7E - 0x20)
    c += T.b_cond(va + len(c), "hi", L.get("end", va))  # unsigned: < 0x20 or > 0x7E ends the text
    c += T.adds_imm8(1, 1)
    c += T.cmp_imm(1, LABEL_MAX)
    c += T.b_cond(va + len(c), "cc", L.get("loop", va))
    L["end"] = va + len(c)
    c += T.adds_reg(0, 3, 1)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 0, 0)                         # NUL at [length] (byte 8 at most: buf +8..+11)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.lsls_imm(0, 5, 16)
    c += T.lsrs_imm(0, 0, 16)
    c += T.str_sp(0, 0)                              # rect x
    c += T.lsrs_imm(0, 5, 16)
    c += T.str_sp(0, 4)                              # rect y (bottom, y-up)
    c += T.movw(0, SCREEN_W)
    c += T.ldr_sp(1, 0)
    c += T.subs_reg(0, 0, 1)                         # 320 - x
    c += T.cmp_imm(0, LAB_W)
    c += T.b_cond(va + len(c), "le", L.get("wok", va))
    c += T.movs_imm8(0, LAB_W)
    L["wok"] = va + len(c)
    c += T.str_sp(0, 8)                              # rect w = min(48, 320 - x): TEXT1X then drops the chars past it
    c += T.movs_imm8(0, LAB_H)
    c += T.str_sp(0, 12)
    c += T.add_rd_sp(0, 16)
    c += T.add_rd_sp(1, 0)
    c += T.movs_imm8(2, LAB_COLOUR)
    c += T.mov_reg(3, 4)
    c += T.bl(va + len(c), PT.TEXT1X)
    L["out"] = va + len(c)
    c += T.add_sp_imm(32)
    c += T.pop_lo([4, 5, 6], pc=True)
    return c
