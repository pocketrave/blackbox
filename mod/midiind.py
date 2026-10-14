"""v070: green "M" MIDI-in indicator left of the status-bar counter.

Audio side (MIDIT, audioTask, EngineBlock 0x0804CB1C): stock reaches 0x0804CD4C only for Note On (0x90), Note Off
(0x80) and CC (0xB0), from both input ports (flag 0 = TRS DIN, flag 1 = USB-A host), any channel, before any channel
filter (0x0804CC46: `and r3,r0,#0xef; cmp r3,#0x80; beq` / `cmp r0,#0xb0; beq`). Clock / realtime / SysEx / PC /
pitch bend / aftertouch never get there. MIDIT stores uwTick | 1 (never 0 = "never received") as one aligned u32 to
mod state +2116 and runs the two displaced instructions. Leaf, r0 / r3 only (both are rewritten by the displaced
`movs r3,#0x10; mov r0,r5`), no calls. Flags: the cave's `cmp r3,#0` leaves C = 1, V = 0, the same values the stock
`cmp r3,#0x80` / `cmp r0,#0xb0` (equal) left; the displaced `movs` sets N / Z again.

UI side (MIND, defaultTask, status-bar update 0x080AB78C, every pass, also with the transport stopped): chained in
front of the v009 TC cave at TCOL_SITE 0x080AB7E2 (right after SetText(counter)). r4 = bar; r0..r3 free; lr is not
live (the function returns by pop pc), so the cave may call. It reuses the bar's empty stock label +0xE4 (AddChild'ed
by the ctor at 0x080AB71A, never set by stock):
    x = 318 - TextWidth(counter text) - 12, w = 12, align 1 (left), colour 11 (#009E73, the UI green)
    SetText(+0xE4, "M" if desc && t && (uwTick - t) < HOLD_MS else NULL)     (t = [state +2116], unsigned subtract)
SetText 0x080C3B98 only marks the label dirty when the text changes (NULL = empty), so a steady stream costs no
repaints. Then `b.w TC` (TC re-runs the displaced title instructions and returns to 0x080AB7E8)."""

import thumb as T
import launch as LA

DESCP = 0x2401F4FC
TICK = 0x24015CE4                      # HAL uwTick (ms)
T_OFF = 2116                           # mod state +2116..+2119: last Note/CC tick | 1 (0 = never)
HOLD_MS = 150

# audio side
MIDIT_SITE = 0x0804CD4C
MIDIT_ORIG = bytes.fromhex("10232846")     # movs r3,#0x10 ; mov r0,r5
MIDIT_BACK = 0x0804CD50

# UI side
TEXTW = 0x0808ED28                     # TextWidth(char *) = strlen * 12 at the status font
SETTEXT = 0x080C3B98                   # Label::SetText(label, char *) (NULL = empty)
CNT_LABEL, M_LABEL = 0x34, 0xE4        # status-bar children
TXT, ALIGN, COLOUR = 0x31, 0x51, 0x53  # label fields
RIGHT, GAP_W = 318, 12                 # the M box: (RIGHT - W - 12, 222, 12, 20)
GREEN = 11                             # palette 11 = #009E73
ALIGN_LEFT = 1
M_STR = b"M\0\0\0"


def midit(va, L):
    c = T.ldr_imm32(3, DESCP)
    c += T.ldr_imm(3, 3)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("done", va))
    c += T.movw(0, LA.STATE_OFF + T_OFF)
    c += T.add_reg(3, 0)
    c += T.ldr_imm32(0, TICK)
    c += T.ldr_imm(0, 0)
    c += bytes.fromhex("40f00100")         # orr.w r0, r0, #1 (no flags)
    c += T.str_imm(0, 3)
    L["done"] = va + len(c)
    c += MIDIT_ORIG
    c += T.bw(va + len(c), MIDIT_BACK)
    return c


def mind(va, L, str_va, tc_va):
    c = T.mov_reg(0, 4)
    c += T.adds_imm8(0, CNT_LABEL + TXT)   # counter text
    c += T.bl(va + len(c), TEXTW)
    c += T.movw(1, RIGHT - GAP_W)
    c += T.subs_reg(1, 1, 0)                # x = 318 - W - 12
    c += T.mov_reg(2, 4)
    c += T.adds_imm8(2, M_LABEL)
    c += T.str_imm(1, 2, 4)
    c += T.movs_imm8(1, GAP_W)
    c += T.str_imm(1, 2, 0xC)               # w = 12 (one character)
    c += T.movs_imm8(1, ALIGN_LEFT)
    c += T.strb_w(1, 4, M_LABEL + ALIGN)
    c += T.movs_imm8(1, GREEN)
    c += T.strb_w(1, 4, M_LABEL + COLOUR)
    c += T.movs_imm8(1, 0)                  # NULL = ""
    c += T.ldr_imm32(3, DESCP)
    c += T.ldr_imm(3, 3)
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("set", va))
    c += T.movw(2, LA.STATE_OFF + T_OFF)
    c += T.add_reg(3, 2)
    c += T.ldr_imm(3, 3)                    # t
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("set", va))
    c += T.ldr_imm32(2, TICK)
    c += T.ldr_imm(2, 2)
    c += T.subs_reg(2, 2, 3)                # now - t (unsigned, wrap-safe)
    c += T.cmp_imm(2, HOLD_MS)
    c += T.b_cond(va + len(c), "cs", L.get("set", va))
    c += T.ldr_imm32(1, str_va)             # "M"
    L["set"] = va + len(c)
    c += T.mov_reg(0, 4)
    c += T.adds_imm8(0, M_LABEL)
    c += T.bl(va + len(c), SETTEXT)
    c += T.bw(va + len(c), tc_va)
    return c


def model(t, now, desc=True):
    """Reference: the M label text for stored tick t and uwTick now."""
    return "M" if desc and t and ((now - t) & 0xFFFFFFFF) < HOLD_MS else ""


def m_x(counter):
    return RIGHT - GAP_W - 12 * len(counter)
