"""v047: the L3 header row is selectable like the clips.

Selection: sel_n = HDR (0xFF) means "the header of column sel_k". TL moves up from row 1 to the header and back down
(ENC, touch.py); the clip row left behind is kept at mod state +108 (MIDI notes 111-118 keep acting on it; the
yellow MIDI corners are not drawn while the header is selected: ROWMK finds no visible row).
A short tap on a header selects it and flashes it yellow for FLASH_MS (HSEL); it no longer stops the column.
A long press opens the column page as before; INFO while a header is selected opens it too (INFOW, on the two SEQS
SetView(…, 0x12) calls). HDRCOL gives PAINT each header's fill / text colour: yellow while flashing (and keeps the
view repainting until the flash is over), blue when selected, normal otherwise."""
import thumb as T
import phase5 as P5
import launch as LA
import paint as PT
import touch as TC
import colmenu as CM

HDR = 0xFF
LAST_OFF, FLASH_OFF, FLASH_T_OFF = 108, 109, 2160   # mod state: last clip row, flashing header k+1, u32 start tick
FLASH_MS = 300
C_FLASH, C_FLASH_TXT = PT.C_ROWMK, 14       # bright yellow, black text
C_SEL_TXT = 15                              # white text on the blue selected header
INFO_SITES = (0x080A303A, 0x080A3052)       # bl SetView with r1 = 0x12 (INFO -> piano roll) in the button dispatcher


def hsel(va, L):
    """(r0 k): select header k (remember the clip row), start the flash. Leaf, clobbers r0-r3."""
    c = T.ldr_imm32(1, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(1, 1, 0)
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("ret", va))
    c += T.ldr_imm32(2, LA.STATE_OFF + TC.SEL_OFF)
    c += T.add_reg(1, 2)                     # r1 = &sel
    c += T.ldrb_imm(2, 1, 1)
    c += T.cmp_imm(2, HDR)
    c += T.b_cond(va + len(c), "eq", L.get("keep", va))
    c += T.strb_imm(2, 1, LAST_OFF - TC.SEL_OFF)
    L["keep"] = va + len(c)
    c += T.strb_imm(0, 1, 0)                 # sel_k = k
    c += T.movs_imm8(2, HDR)
    c += T.strb_imm(2, 1, 1)                 # sel_n = header
    c += T.adds_imm8(0, 1)
    c += T.strb_imm(0, 1, FLASH_OFF - TC.SEL_OFF)
    c += T.ldr_imm32(2, TC.TICK)
    c += T.ldr_imm(2, 2, 0)
    c += T.ldr_imm32(3, FLASH_T_OFF - TC.SEL_OFF)
    c += T.add_reg(3, 1)
    c += T.str_imm(2, 3, 0)
    L["ret"] = va + len(c)
    c += T.bx(14)
    return c


def hdrcol(va, L):
    """(r0 k) -> r0 fill colour, r1 text colour. Leaf, clobbers r0-r3."""
    c = T.push_lo([4, 5], lr=False)
    c += T.mov_reg(4, 0)
    c += T.ldr_imm32(5, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(5, 5, 0)
    c += T.cmp_imm(5, 0)
    c += T.b_cond_w(va + len(c), "eq", L.get("plain", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + TC.SEL_OFF)
    c += T.add_reg(5, 0)                     # r5 = &sel
    c += T.ldrb_imm(0, 5, FLASH_OFF - TC.SEL_OFF)
    c += T.subs_imm8(0, 1)
    c += T.cmp_reg(0, 4)
    c += T.b_cond(va + len(c), "ne", L.get("nofl", va))
    c += T.ldr_imm32(1, FLASH_T_OFF - TC.SEL_OFF)
    c += T.add_reg(1, 5)
    c += T.ldr_imm(1, 1, 0)
    c += T.ldr_imm32(2, TC.TICK)
    c += T.ldr_imm(2, 2, 0)
    c += T.subs_reg(2, 2, 1)                 # ms since the tap
    c += T.movw(3, FLASH_MS)
    c += T.cmp_reg(2, 3)
    c += T.b_cond(va + len(c), "cs", L.get("over", va))
    c += T.ldr_imm32(0, TC.ROOT_PTR)         # keep repainting until the flash is over (also while stopped)
    c += T.ldr_imm(0, 0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("yel", va))
    c += T.ldr_imm32(1, TC.VIEW_OFF + TC.DIRTY_OFF)
    c += T.add_reg(0, 1)
    c += T.movs_imm8(1, 1)
    c += T.strb_imm(1, 0, 0)
    L["yel"] = va + len(c)
    c += T.movs_imm8(0, C_FLASH)
    c += T.movs_imm8(1, C_FLASH_TXT)
    c += T.b_short(va + len(c), L.get("ret", va))
    L["over"] = va + len(c)
    c += T.movs_imm8(0, 0)
    c += T.strb_imm(0, 5, FLASH_OFF - TC.SEL_OFF)
    L["nofl"] = va + len(c)
    c += T.ldrb_imm(0, 5, 1)
    c += T.cmp_imm(0, HDR)
    c += T.b_cond(va + len(c), "ne", L.get("plain", va))
    c += T.ldrb_imm(0, 5, 0)
    c += T.cmp_reg(0, 4)
    c += T.b_cond(va + len(c), "ne", L.get("plain", va))
    c += T.movs_imm8(0, PT.C_SEL)
    c += T.movs_imm8(1, C_SEL_TXT)
    c += T.b_short(va + len(c), L.get("ret", va))
    L["plain"] = va + len(c)
    c += T.movs_imm8(0, PT.C_HEAD)
    c += T.movs_imm8(1, PT.C_LINE)
    L["ret"] = va + len(c)
    c += T.pop_lo([4, 5])
    c += T.bx(14)
    return c


def infow(va, L, colopen_va):
    """bl replacement for SetView(S, 0x12, 0, 0) at the INFO sites: on SEQS with a selected header -> COLOPEN(k);
    otherwise tail-call SetView with r0-r3 and lr unchanged."""
    c = T.push_lo([0, 1, 2, 3, 4], lr=True)  # 24 B
    c += T.cmp_imm(1, 0x12)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.ldr_imm32(4, LA.SESSION + CM.MODE_OFF)
    c += T.ldrb_imm(4, 4, 0)
    c += T.cmp_imm(4, CM.MODE_SEQS)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.ldr_imm32(4, P5.DESC_ARRAY_PTR)
    c += T.ldr_imm(4, 4, 0)
    c += T.cmp_imm(4, 0)
    c += T.b_cond(va + len(c), "eq", L.get("stock", va))
    c += T.ldr_imm32(0, LA.STATE_OFF + TC.SEL_OFF)
    c += T.add_reg(4, 0)
    c += T.ldrb_imm(0, 4, 1)
    c += T.cmp_imm(0, HDR)
    c += T.b_cond(va + len(c), "ne", L.get("stock", va))
    c += T.ldrb_imm(0, 4, 0)
    c += T.bl(va + len(c), colopen_va)
    c += T.pop_lo([0, 1, 2, 3, 4], pc=True)
    L["stock"] = va + len(c)
    c += T.ldr_sp(0, 20)
    c += T.mov_reg(14, 0)
    c += T.pop_lo([0, 1, 2, 3, 4])
    c += T.add_sp_imm(4)
    c += T.bw(va + len(c), CM.SETVIEW)
    return c
