#!/usr/bin/env python3
"""
Step 3 — the quantize gate. Makes `PrCh Quant` actually do something.

A preset switch requested by note 109/110 is held until the next musical
boundary, at the division selected by the `PrCh Quant` parameter added in Step 1.

------------------------------------------------------------------ design

The gate lives entirely inside cave C (the defaultTask main-loop hook). It is
NOT placed in ProcessCommandQueue: that runs in a file-operation context and
gating there would stall file work, and Step 2 established that this call chain
must never run on defaultTask's 2 KB stack anyway.

Cave C already runs every loop iteration, so it can simply not enqueue yet.

    mailbox set (note pressed)
        -> advance the index (so repeated presses accumulate, as in Ableton)
        -> read PrCh Quant
             None  -> enqueue immediately
             else  -> target = (now / div + 1) * div ; mark pending
    pending and now >= target
        -> enqueue, clear pending

------------------------------------------------------------------ verified facts

Transport         0x0804CA68(&out64, 0x2400A9C0) -> 64-bit tick counter.
                  960 ticks per quarter note, derived from the bar/beat maths in
                  0x0809BBF8 (exact divide by 15 via the modular inverse
                  0xEEEEEEEF, then >>6, then /4 and %4 for bar and beat).

Global settings   0x24020088 + 0x8C90 (static). The Tools page reader
owner             0x080996B0 is always called with r0 = 0x24020088 and reads
                  params from sl + 0x8C90 at 0x0809979A.

GetParam          0x08093E9C(owner, id) -> value.

PrCh Quant        id 0x1A0, enum 0x080EC74C:
                  0:8 bars 1:4 bars 2:2 bars 3:1 bar 4:1/2 5:1/4 6:1/8 7:1/16
                  8:None

------------------------------------------------------------------ scratch

    +0   current preset index
    +4   mailbox direction   (0 none, 1 previous, 2 next)
    +8   pending flag
    +12  target tick (low 32 bits)
    +16  index being left (set on the first press of a pending switch)

Low 32 bits of the tick are enough: at 960 PPQN and 120 bpm that is ~1920
ticks/sec, so the counter wraps after roughly 25 days of continuous uptime. A
switch requested in the few milliseconds around that wrap would be late by one
division. Documented rather than handled.

If the transport is stopped the tick does not advance, so a pending switch waits
for playback to start. That is arguably correct for a quantized switch; set
PrCh Quant to None for immediate switching.
"""

import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bbpatch import Patcher, PatchError, BASE
import thumb as T
import fwbase

STOCK = fwbase.STOCK
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")

NOTE_PREV, NOTE_NEXT = 109, 110
DESC_ARRAY_PTR = 0x2401F4FC
SCRATCH_OFF = 0x1F0 * 28
PRESET_MGR = 0x2401F508
SESSION = 0x24020088               # static; referenced from 30+ literal pools
SETTINGS_OWNER = SESSION + 0x8C90  # what the Tools page reads and edits
PRCH_QUANT_ID = 0x1A0

PRESET_LIST = 0x2401F834
GET_NAME_BY_INDEX = 0x0804290C
REQUEST_PRESET_LOAD = 0x08090B78
GET_PARAM = 0x08093E9C
READ_TRANSPORT = 0x0804CA68
ENGINE = 0x2400A9C0

NAME_BUF = 0x110
TICK_OFF = NAME_BUF            # 8 bytes for the 64-bit read, above the name buffer
FRAME = NAME_BUF + 12           # 9 pushed words + FRAME = 320: keeps sp 8-byte aligned

# ticks per division, indexed by the PrCh Quant enum. 960 ticks per quarter.
QUANT_TICKS = [30720, 15360, 7680, 3840, 1920, 960, 480, 240, 0]

HOOK_A, HOOK_A_ORIG, HOOK_A_BACK = 0x0809E23A, bytes.fromhex("d3f82c33"), 0x0809E23E
HOOK_B, HOOK_B_ORIG, HOOK_B_BACK = 0x0805004C, bytes.fromhex("72b1059b"), 0x08050050
CBZ_TARGET = 0x0805006C
NOTE_DONE = 0x0804FEAA
HOOK_C, HOOK_C_TARGET = 0x08043E28, 0x08041B70


def _asm(va, emit):
    L, prev = {}, None
    for _ in range(10):
        c = emit(va, L)
        if c == prev:
            return c
        prev = c
    raise PatchError("cave did not converge")


def cave_a(va, L):
    c = b""
    c += T.push_lo([0, 1, 2])
    c += T.mov_reg(2, 10)
    c += T.ldr_imm32(0, DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("skip", va))
    c += T.movw(1, SCRATCH_OFF)
    c += T.add_reg(0, 1)
    c += T.str_imm(2, 0)
    L["skip"] = va + len(c)
    c += T.pop_lo([0, 1, 2])
    c += HOOK_A_ORIG
    c += T.bw(va + len(c), HOOK_A_BACK)
    return c


def cave_b(va, L):
    c = b""
    c += T.cmp_imm(7, NOTE_PREV)
    c += T.b_cond(va + len(c), "eq", L.get("prev", va))
    c += T.cmp_imm(7, NOTE_NEXT)
    c += T.b_cond(va + len(c), "eq", L.get("next", va))
    c += T.cmp_imm(2, 0)
    c += T.b_cond_w(va + len(c), "eq", CBZ_TARGET)
    c += T.ldr_sp(3, 0x14)
    c += T.bw(va + len(c), HOOK_B_BACK)

    L["prev"] = va + len(c)
    c += T.push_lo([0, 1, 2])
    c += T.movs_imm8(2, 1)
    c += T.b_short(va + len(c), L.get("store", va))
    L["next"] = va + len(c)
    c += T.push_lo([0, 1, 2])
    c += T.movs_imm8(2, 2)
    L["store"] = va + len(c)
    c += T.ldr_imm32(0, DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("done", va))
    c += T.movw(1, SCRATCH_OFF)
    c += T.add_reg(0, 1)
    c += T.str_imm(2, 0, 4)
    L["done"] = va + len(c)
    c += T.pop_lo([0, 1, 2])
    c += T.bw(va + len(c), NOTE_DONE)
    return c


def cave_c(va, L, table_va):
    c = b""
    c += T.push_lo([], lr=True)
    c += T.bl(va + len(c), HOOK_C_TARGET)          # displaced call, pristine regs
    c += T.push_lo([0, 1, 2, 3, 4, 5, 6, 7])
    c += T.sub_sp_imm(FRAME)

    c += T.ldr_imm32(0, DESC_ARRAY_PTR)
    c += T.ldr_imm(0, 0)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.movw(1, SCRATCH_OFF)
    c += T.add_reg(0, 1)
    c += T.mov_reg(4, 0)                            # r4 = scratch

    # ---- a new request? -------------------------------------------------
    c += T.ldr_imm(6, 4, 4)                         # r6 = mailbox
    c += T.cmp_imm(6, 0)
    c += T.b_cond(va + len(c), "eq", L.get("chkpend", va))
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 4, 4)                         # clear mailbox

    c += T.ldr_imm(5, 4, 0)                         # r5 = index
    # remember the preset we are leaving, for the header's "old>new" - but only
    # on the first press; further presses while pending keep the original
    c += T.ldr_imm(0, 4, 8)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "ne", L.get("keepold", va))
    c += T.str_imm(5, 4, 16)                        # scratch+16 = old index
    L["keepold"] = va + len(c)
    c += T.ldr_imm32(0, PRESET_LIST)
    c += T.ldr_imm(3, 0)                            # r3 = list count
    c += T.cmp_imm(3, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.cmp_imm(6, 1)
    c += T.b_cond(va + len(c), "eq", L.get("prevcalc", va))
    c += T.adds_imm(5, 5, 1)
    c += T.cmp_reg(5, 3)
    c += T.b_cond(va + len(c), "cc", L.get("idxok", va))
    c += T.movs_imm8(5, 0)
    c += T.b_short(va + len(c), L.get("idxok", va))
    L["prevcalc"] = va + len(c)
    c += T.cmp_imm(5, 0)
    c += T.b_cond(va + len(c), "ne", L.get("dec", va))
    c += T.mov_reg(5, 3)
    L["dec"] = va + len(c)
    c += T.subs_imm(5, 5, 1)
    L["idxok"] = va + len(c)
    c += T.str_imm(5, 4, 0)                         # store index

    # ---- read PrCh Quant ------------------------------------------------
    # The live settings owner is the STATIC object 0x24020088 + 0x8C90 - exactly
    # what the Tools page reads (0x080996B0: mov sl,r0 with r0 = 0x24020088 at
    # every caller; 0x0809979A: sl + 0x8c90 -> GetParam). The earlier
    # *(0x2401F508+0x2BC) was inferred, never verified, and made GetParam return
    # 0 ("8 bars") so every switch was held.
    c += T.ldr_imm32(0, SETTINGS_OWNER)             # r0 = settings owner
    c += T.movw(1, PRCH_QUANT_ID)
    c += T.bl(va + len(c), GET_PARAM)               # r0 = enum index
    c += T.cmp_imm(0, len(QUANT_TICKS) - 1)
    c += T.b_cond(va + len(c), "cs", L.get("enqueue", va))   # >= 8 (None) -> now
    c += T.lsls_imm(0, 0, 2)
    c += T.ldr_imm32(1, table_va)
    c += T.add_reg(1, 0)
    c += T.ldr_imm(1, 1)                            # r1 = ticks per division
    c += T.cmp_imm(1, 0)
    c += T.b_cond(va + len(c), "eq", L.get("enqueue", va))

    # target = (now / div + 1) * div
    c += T.mov_reg(7, 1)                            # keep div in r7
    c += T.mov_reg(0, 13)
    c += T.movw(1, TICK_OFF)
    c += T.add_reg(0, 1)                            # r0 = &tick
    c += T.ldr_imm32(1, ENGINE)
    c += T.bl(va + len(c), READ_TRANSPORT)
    c += T.ldr_sp(0, TICK_OFF)                      # r0 = now (low 32)
    c += T.mov_reg(1, 7)                            # r1 = div
    c += T.udiv(2, 0, 1)
    c += T.adds_imm(2, 2, 1)
    c += T.muls(2, 1)                               # r2 = target
    c += T.str_imm(2, 4, 12)
    c += T.movs_imm8(0, 1)
    c += T.str_imm(0, 4, 8)                         # pending = 1
    c += T.b_short(va + len(c), L.get("out", va))

    # ---- pending: has the boundary arrived? -----------------------------
    L["chkpend"] = va + len(c)
    c += T.ldr_imm(0, 4, 8)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.mov_reg(0, 13)
    c += T.movw(1, TICK_OFF)
    c += T.add_reg(0, 1)
    c += T.ldr_imm32(1, ENGINE)
    c += T.bl(va + len(c), READ_TRANSPORT)
    c += T.ldr_sp(0, TICK_OFF)
    c += T.ldr_imm(1, 4, 12)                        # target
    c += T.cmp_reg(0, 1)
    c += T.b_cond(va + len(c), "cc", L.get("out", va))   # now < target -> wait
    c += T.movs_imm8(0, 0)
    c += T.str_imm(0, 4, 8)                         # clear pending
    c += T.ldr_imm(5, 4, 0)                         # r5 = index

    # ---- enqueue --------------------------------------------------------
    L["enqueue"] = va + len(c)
    c += T.ldr_imm(5, 4, 0)
    c += T.mov_reg(2, 13)
    c += T.movs_imm8(3, 0)
    c += T.strb_imm(3, 2, 0)
    c += T.mov_reg(1, 5)
    c += T.ldr_imm32(0, PRESET_LIST)
    c += T.bl(va + len(c), GET_NAME_BY_INDEX)
    c += T.cmp_imm(0, 0)
    c += T.b_cond(va + len(c), "eq", L.get("out", va))
    c += T.mov_reg(1, 13)
    c += T.ldr_imm32(0, PRESET_MGR)
    c += T.bl(va + len(c), REQUEST_PRESET_LOAD)     # enqueue only - never drain here

    L["out"] = va + len(c)
    c += T.add_sp_imm(FRAME)
    c += T.pop_lo([0, 1, 2, 3, 4, 5, 6, 7])
    c += T.pop_lo([], pc=True)
    return c


def build():
    p = Patcher(STOCK)
    p.expect(HOOK_A, HOOK_A_ORIG)
    p.expect(HOOK_B, HOOK_B_ORIG)
    c_orig = bytes(p.data[HOOK_C - BASE:HOOK_C - BASE + 4])
    if c_orig != T.bl(HOOK_C, HOOK_C_TARGET):
        raise PatchError("hook C site changed")

    table_va = p.append(b"".join(struct.pack("<I", t) for t in QUANT_TICKS), align=4)
    vas = {}
    for name, fn in (("A", cave_a), ("B", cave_b)):
        va = BASE + len(p.data) + ((4 - len(p.data) % 4) % 4)
        got = p.append(_asm(va, fn), align=4)
        assert got == va
        vas[name] = va
    va = BASE + len(p.data) + ((4 - len(p.data) % 4) % 4)
    got = p.append(_asm(va, lambda v, L: cave_c(v, L, table_va)), align=4)
    assert got == va
    vas["C"] = va

    p.write_bytes(HOOK_A, T.bw(HOOK_A, vas["A"]), expected=HOOK_A_ORIG)
    p.write_bytes(HOOK_B, T.bw(HOOK_B, vas["B"]), expected=HOOK_B_ORIG)
    p.write_bytes(HOOK_C, T.bl(HOOK_C, vas["C"]), expected=c_orig)
    p.verify_safety()
    out = os.path.join(OUTDIR, "BLACKBOX_p5_quantgate.bin")
    p.save(out)
    return p, out, vas, table_va


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    T.selftest(verbose=False)
    try:
        p, out, vas, table_va = build()
    except (PatchError, AssertionError) as e:
        print("FAILED: %s" % e)
        return 1
    print(p.report())
    print("\n  quant table @ %08X : %s" % (table_va, QUANT_TICKS))
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    d = open(out, "rb").read()
    print("\n  cave C @ %08X:" % vas["C"])
    for ins in md.disasm(d[vas["C"] - BASE:vas["C"] - BASE + 260], vas["C"]):
        print("    %08X  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
    dst = os.path.join(OUTDIR, "test_quantgate")
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(out, os.path.join(dst, "BLACKBOX.BIN"))
    print("\n  ready to copy: %s%sBLACKBOX.BIN" % (dst, os.sep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
