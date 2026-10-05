"""v046 L3 column Name row.

The column page (colmenu.py) gets a third row, param id NAME_ID 0x19F (a free descriptor slot). Its descriptor is a
kind-5 enum whose 3-entry table points at one RAM buffer holding the column's name (first 6 characters of song
section 24+k's name, or the column number when empty): stock enum formatting shows that text. NAMEPREP fills the
descriptor, table and buffer every time COLOPEN opens the page.
RD2 returns 1 for NAME_ID (so a BR turn either way changes the value and the page emits its edit).
EDITW (0x080A77BE, the page's 0x6E post for a changed row) catches NAME_ID: prefill the keyboard with the current
name (KbdSetText), set the waiting flag (mod state +107 = k + 1), send {0xD0} (the stock keyboard opens in place of
the page); NAME_ID never reaches SetCellParam / the engine.
NAMERET (in front of SH2 at 0x080A78C4, the page's 0xD4 = shown again after the keyboard): when the flag is set,
clear it; on Enter (KbdGetResult == 1) save the first 6 characters with SetName(section 24 + k) and refresh the
buffer; always set the previous mode [S+0x8CA5] = SEQS (else BACK on the page would reopen the keyboard)."""
import thumb as T
import phase5 as P5
import launch as LA

NAME_ID = 0x19F
DESC_SZ = 28
KBD_OFF = 107                               # mod state: k + 1 while the keyboard edits column k's name
NAMEBUF_OFF, TABLE_OFF = 2144, 2152         # mod state: 8-B name buffer, 3 x pointer table (enum texts)
NAME_MAX = 6
SECT0, SECT_SZ, SECT_NAME = 0x29C0 + 24 * 0x30, 0x30, 0x2C   # session: section record 24 + k, name pointer
ROOT_PTR, KBD = 0x24002E6C, 0x19DE8
KBD_SET, KBD_GET, SETNAME = 0x080C42AC, 0x080C4758, 0x0808FCA4
SEND = 0x080AED14                           # (widget, msg*): send up to the parent (the page's own send)
MSG_VT = 0x080CFBA4
EDIT_SITE, EDIT_ORIG, EDIT_BACK, EDIT_POSTED = 0x080A77BE, bytes.fromhex("018f2a69"), 0x080A77C2, 0x080A77E2
PREV_MODE = 0x8CA5                          # session: previous UI mode (BACK target)
LABEL = b"Name:\0\0\0"


def namefill(va, L):
    """(r0 k): name buffer = first 6 chars of section 24+k's name, or the digit k+1. Returns r0 = &buffer.
    Leaf, clobbers r0-r3."""
    c = T.push_lo([4, 5], lr=False)
    c += T.mov_reg(5, 0)                     # k
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.ldr_imm32(1, LA.STATE_OFF + NAMEBUF_OFF)
    c += T.add_reg(4, 1)                     # r4 = buffer
    c += T.movs_imm8(0, SECT_SZ)
    c += T.muls(0, 5)
    c += T.ldr_imm32(1, LA.SESSION + SECT0 + SECT_NAME)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(1, 1, 0)                  # name pointer
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("digit", va))
    c += T.ldrb_imm(2, 1, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("digit", va))
    c += T.movs_imm8(3, 0)
    L["copy"] = va + len(c)
    c += T.ldrb_imm(2, 1, 0)
    c += T.cmp_imm(2, 0)
    c += T.b_cond(va + len(c), "eq", L.get("end", va))
    c += T.adds_reg(0, 4, 3)
    c += T.strb_imm(2, 0, 0)
    c += T.adds_imm8(1, 1)
    c += T.adds_imm8(3, 1)
    c += T.cmp_imm(3, NAME_MAX)
    c += T.b_cond(va + len(c), "ne", L.get("copy", va))
    L["end"] = va + len(c)
    c += T.adds_reg(0, 4, 3)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 0, 0)
    c += T.b_short(va + len(c), L.get("ret", va))
    L["digit"] = va + len(c)
    c += T.mov_reg(2, 5)
    c += T.adds_imm8(2, 0x31)
    c += T.strb_imm(2, 4, 0)
    c += T.movs_imm8(2, 0)
    c += T.strb_imm(2, 4, 1)
    L["ret"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.pop_lo([4, 5])
    c += T.bx(14)
    return c


def nameprep(va, L, namefill_va, label_va):
    """(r0 k): fill descriptor NAME_ID {id, kind 5, label, table, count 3, min 0, max 2, tag 0}, its table and the
    name buffer."""
    c = T.push_lo([4, 5], lr=True)           # 12 B ... keep 8-aligned below
    c += T.push_lo([6])
    c += T.mov_reg(5, 0)
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("out", va))
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), namefill_va)      # r0 = buffer
    c += T.ldr_imm32(1, LA.STATE_OFF + TABLE_OFF)
    c += T.adds_reg(1, 4, 1)                 # r1 = table
    for i in range(3):
        c += T.str_imm(0, 1, 4 * i)
    c += T.ldr_imm32(2, NAME_ID * DESC_SZ)
    c += T.adds_reg(2, 4, 2)                 # r2 = descriptor
    c += T.ldr_imm32(0, NAME_ID | 5 << 16)   # u16 id, u8 kind 5, pad
    c += T.str_imm(0, 2, 0)
    c += T.ldr_imm32(0, label_va)
    c += T.str_imm(0, 2, 4)
    c += T.str_imm(1, 2, 8)                  # table
    c += T.movs_imm8(0, 3)
    c += T.str_imm(0, 2, 12)                 # count
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 2, 16)                 # min
    c += T.str_imm(0, 2, 24)                 # tag
    c += T.movs_imm8(0, 2)
    c += T.str_imm(0, 2, 20)                 # max
    L["out"] = va + len(c)
    c += T.pop_lo([6])
    c += T.pop_lo([4, 5], pc=True)
    return c


def editw(va, L, empty_va):
    """b.w at EDIT_SITE (r0 = row owner, r4 = page, r5 = msg {+0xC value, +0x10 id}); frame sp+0x1C.. msg area."""
    c = T.ldr_imm(2, 5, 0x10)                # displaced: ldr r2, [r5, #0x10]
    c += T.ldr_imm32(3, NAME_ID)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "eq", L.get("name", va))
    c += T.ldrh_imm(1, 0, 0x38)              # displaced: ldrh r1, [r0, #0x38]
    c += T.bw(va + len(c), EDIT_BACK)
    L["name"] = va + len(c)
    c += T.ldr_imm32(0, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("posted", va))
    c += T.ldr_imm32(1, LA.STATE_OFF + 106)  # colmenu.COLPAGE_OFF: k + 1
    c += T.add_reg(0, 1)
    c += T.ldrb_imm(1, 0, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("posted", va))
    c += T.strb_imm(1, 0, KBD_OFF - 106)     # waiting flag = k + 1
    c += T.subs_imm8(1, 1)
    c += T.movs_imm8(0, SECT_SZ)
    c += T.muls(0, 1)
    c += T.ldr_imm32(1, LA.SESSION + SECT0 + SECT_NAME)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(1, 1, 0)                  # the current name (NULL -> "")
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "ne", L.get("hasname", va))
    c += T.ldr_imm32(1, empty_va)            # "" (the label's trailing NUL)
    L["hasname"] = va + len(c)
    c += T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.ldr_imm32(2, KBD)
    c += T.add_reg(0, 2)
    c += T.bl(va + len(c), KBD_SET)
    c += T.movs_imm8(0, 0)
    for off in (0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30):
        c += T.str_sp(0, off)
    c += T.movs_imm8(0, 0xD0)
    c += T.add_rd_sp(1, 0x1C)
    c += T.strh_imm(0, 1, 0)
    c += T.ldr_imm32(0, MSG_VT)
    c += T.str_sp(0, 0x20)
    c += T.mov_reg(0, 4)
    c += T.bl(va + len(c), SEND)
    L["posted"] = va + len(c)
    c += T.bw(va + len(c), EDIT_POSTED)
    return c


def nameret(va, L, sh2_va, namefill_va):
    """b.w at the SH site (0xD4 page shown), in front of SH2: all registers and sp handed to SH2 unchanged."""
    c = T.push_lo([0, 1, 2, 3, 4, 5, 6, 7], lr=True)   # 36 B
    c += T.sub_sp_imm(260)                   # 296: 8-aligned; [sp..+255] the keyboard result
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("done", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + KBD_OFF)
    c += T.add_reg(4, 0)                     # r4 = &flag
    c += T.ldrb_imm(5, 4, 0)
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("done", va))
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 4, 0)
    c += T.subs_imm8(5, 1)                   # r5 = k
    c += T.ldr_imm32(0, LA.SESSION + PREV_MODE)
    c += T.movs_imm8(1, 0x2C)
    c += T.strb_imm(1, 0, 0)                 # BACK on the page -> SEQS (not the keyboard again)
    c += T.ldr_imm32(0, ROOT_PTR)
    c += T.ldr_imm(0, 0, 0)
    c += T.ldr_imm32(1, KBD)
    c += T.add_reg(0, 1)
    c += T.add_rd_sp(1, 0)
    c += T.bl(va + len(c), KBD_GET)
    c += T.cmp_imm(0, 1)
    c += T.b_cond(va + len(c), "ne", L.get("refresh", va))
    c += T.movs_imm8(0, 0)
    c += T.add_rd_sp(1, 0)
    c += T.strb_imm(0, 1, NAME_MAX)          # keep 6 characters
    c += T.movs_imm8(0, SECT_SZ)
    c += T.muls(0, 5)
    c += T.ldr_imm32(1, LA.SESSION + SECT0)
    c += T.add_reg(0, 1)                     # section record 24 + k
    c += T.add_rd_sp(1, 0)
    c += T.bl(va + len(c), SETNAME)
    L["refresh"] = va + len(c)
    c += T.mov_reg(0, 5)
    c += T.bl(va + len(c), namefill_va)
    L["done"] = va + len(c)
    c += T.add_sp_imm(260)
    c += T.ldr_sp(0, 32)
    c += T.mov_reg(14, 0)                    # lr back
    c += T.pop_lo([0, 1, 2, 3, 4, 5, 6, 7])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), sh2_va)
    return c
