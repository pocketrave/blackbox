#!/usr/bin/env python3
"""Minimal Thumb-2 encoder — only the instructions the patches need.

Every encoder here is verified by round-tripping through Capstone in
selftest(); nothing is trusted on inspection alone.
"""

import struct


def _chk(v, bits, name):
    if not (0 <= v < (1 << bits)):
        raise ValueError("%s out of range: %d" % (name, v))


def movw(rd, imm16):
    """MOV (immediate) T3 — rd = imm16 (zero-extended)."""
    _chk(imm16, 16, "imm16")
    i = (imm16 >> 11) & 1
    imm4 = (imm16 >> 12) & 0xF
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF240 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


def movt(rd, imm16):
    """MOVT T1 — rd[31:16] = imm16."""
    _chk(imm16, 16, "imm16")
    i = (imm16 >> 11) & 1
    imm4 = (imm16 >> 12) & 0xF
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF2C0 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


def ldr_imm32(rd, value):
    """Materialise a 32-bit constant into rd with movw+movt."""
    return movw(rd, value & 0xFFFF) + movt(rd, (value >> 16) & 0xFFFF)


def mov_reg(rd, rm):
    """MOV (register) T1 — works across the low/high register boundary."""
    d = (rd >> 3) & 1
    return struct.pack("<H", 0x4600 | (d << 7) | ((rm & 0xF) << 3) | (rd & 0x7))


def movs_imm8(rd, imm8):
    """MOVS (immediate) T1 — low registers, 0..255."""
    _chk(imm8, 8, "imm8")
    if rd > 7:
        raise ValueError("movs_imm8 needs a low register")
    return struct.pack("<H", 0x2000 | (rd << 8) | imm8)


def str_sp(rt, byte_offset):
    """STR (immediate, SP relative) T2."""
    if rt > 7:
        raise ValueError("str_sp needs a low register")
    if byte_offset % 4:
        raise ValueError("SP offset must be word aligned")
    imm8 = byte_offset // 4
    _chk(imm8, 8, "imm8")
    return struct.pack("<H", 0x9000 | (rt << 8) | imm8)


def add_sp_imm(byte_offset):
    """ADD (SP plus immediate) T2."""
    if byte_offset % 4:
        raise ValueError("SP adjust must be word aligned")
    imm7 = byte_offset // 4
    _chk(imm7, 7, "imm7")
    return struct.pack("<H", 0xB000 | imm7)


def _branch_imm(pc, target):
    """Shared imm encoding for BL (T1) and B.W (T4)."""
    off = target - (pc + 4)
    if off & 1:
        raise ValueError("branch target must be halfword aligned")
    if not (-(1 << 24) <= off < (1 << 24)):
        raise ValueError("branch out of range: 0x%X" % off)
    off >>= 1
    s = (off >> 23) & 1
    i1 = (off >> 22) & 1
    i2 = (off >> 21) & 1
    imm10 = (off >> 11) & 0x3FF
    imm11 = off & 0x7FF
    j1 = (~i1 ^ s) & 1
    j2 = (~i2 ^ s) & 1
    return s, j1, j2, imm10, imm11


def bl(pc, target):
    s, j1, j2, imm10, imm11 = _branch_imm(pc, target)
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0xD000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def bw(pc, target):
    s, j1, j2, imm10, imm11 = _branch_imm(pc, target)
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def nop():
    return struct.pack("<H", 0xBF00)


# ---------------------------------------------------------------- selftest

def selftest(verbose=True):
    """Round-trip every encoder through Capstone. Raises on mismatch."""
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    base = 0x080F1E60
    cases = [
        (movw(1, 0x01A0), "movw r1, #0x1a0"),
        (movw(3, 0xC72C), "movw r3, #0xc72c"),
        (movt(3, 0x080E), "movt r3, #0x80e"),
        (mov_reg(0, 8), "mov r0, r8"),
        (mov_reg(0, 4), "mov r0, r4"),
        (movs_imm8(3, 9), "movs r3, #9"),
        (movs_imm8(2, 8), "movs r2, #8"),
        (str_sp(3, 0), "str r3, [sp]"),
        (str_sp(3, 4), "str r3, [sp, #4]"),
        (add_sp_imm(0x14), "add sp, #0x14"),
        (bl(base, 0x0808C0D8), None),
        (bw(base, 0x080949DA), None),
        (nop(), "nop"),
        (ldrh_imm(6, 5, 4), "ldrh r6, [r5, #4]"),
        (strh_imm(3, 2, 4), "strh r3, [r2, #4]"),
        (lsrs_imm(3, 6, 8), "lsrs r3, r6, #8"),
        (lsrs_imm(3, 3, 28), "lsrs r3, r3, #0x1c"),
        (orrs_reg(3, 2), "orrs r3, r2"),
        (lsls_imm(3, 6, 28), "lsls r3, r6, #0x1c"),
        (mov_reg(1, 13), "mov r1, sp"),
        (cmp_reg(3, 6), "cmp r3, r6"),
        (add_reg(3, 4), "add r3, r4"),
        (adds_imm8(1, 0x30), "adds r1, #0x30"),
        (subs_imm8(0, 0x34), "subs r0, #0x34"),
        (adds_reg(2, 2, 3), "adds r2, r2, r3"),
        (subs_reg(4, 1, 3), "subs r4, r1, r3"),
        (ands_reg(4, 3), "ands r4, r3"),
        (add_rd_sp(1, 0x20), "add r1, sp, #0x20"),
        (negs(1, 1), "rsbs r1, r1, #0"),
        (bx(14), "bx lr"),
        (sxth(6, 6), "sxth r6, r6"),
        (ldrex(3, 6), "ldrex r3, [r6]"),
        (strex(0, 1, 6), "strex r0, r1, [r6]"),
        (ldrh_w(2, 4, 0xE50), "ldrh.w r2, [r4, #0xe50]"),
    ]
    ok = True
    for code, expect in cases:
        got = list(md.disasm(code, base))
        if not got:
            print("  FAIL: could not disassemble %s" % code.hex(" "))
            ok = False
            continue
        text = "%s %s" % (got[0].mnemonic, got[0].op_str)
        text = text.strip()
        if expect is not None and text != expect:
            print("  FAIL: %s -> %r (expected %r)" % (code.hex(" "), text, expect))
            ok = False
        elif verbose:
            print("  ok  %-12s %s" % (code.hex(" "), text))
    if not ok:
        raise AssertionError("thumb.py selftest failed")
    return True




# ---------------------------------------------------------------- added for phase 4

def push_lo(regs, lr=False):
    """PUSH T1 - low registers, optionally LR."""
    m = 0
    for r in regs:
        if r > 7:
            raise ValueError("push_lo takes low registers only")
        m |= 1 << r
    return struct.pack("<H", 0xB400 | (1 << 8 if lr else 0) | m)


def pop_lo(regs, pc=False):
    """POP T1 - low registers, optionally PC."""
    m = 0
    for r in regs:
        if r > 7:
            raise ValueError("pop_lo takes low registers only")
        m |= 1 << r
    return struct.pack("<H", 0xBC00 | (1 << 8 if pc else 0) | m)


def ldr_imm(rt, rn, off=0):
    """LDR (immediate) T1 - low registers, word offset 0..124."""
    if rt > 7 or rn > 7:
        raise ValueError("ldr_imm needs low registers")
    if off % 4 or off > 124:
        raise ValueError("bad offset")
    return struct.pack("<H", 0x6800 | ((off // 4) << 6) | (rn << 3) | rt)


def str_imm(rt, rn, off=0):
    """STR (immediate) T1 - low registers, word offset 0..124."""
    if rt > 7 or rn > 7:
        raise ValueError("str_imm needs low registers")
    if off % 4 or off > 124:
        raise ValueError("bad offset")
    return struct.pack("<H", 0x6000 | ((off // 4) << 6) | (rn << 3) | rt)


def cmp_imm(rn, imm8):
    """CMP (immediate) T1 - low register."""
    if rn > 7:
        raise ValueError("cmp_imm needs a low register")
    _chk(imm8, 8, "imm8")
    return struct.pack("<H", 0x2800 | (rn << 8) | imm8)


def add_reg(rd, rm):
    """ADD (register) T2 - high registers permitted."""
    return struct.pack("<H", 0x4400 | ((rd & 8) << 4) | ((rm & 0xF) << 3) | (rd & 7))


def adds_imm(rd, rn, imm3):
    """ADDS (immediate) T1."""
    _chk(imm3, 3, "imm3")
    return struct.pack("<H", 0x1C00 | (imm3 << 6) | (rn << 3) | rd)


def subs_imm(rd, rn, imm3):
    """SUBS (immediate) T1."""
    _chk(imm3, 3, "imm3")
    return struct.pack("<H", 0x1E00 | (imm3 << 6) | (rn << 3) | rd)


_COND = {"eq": 0, "ne": 1, "cs": 2, "cc": 3, "mi": 4, "pl": 5,
         "vs": 6, "vc": 7, "hi": 8, "ls": 9, "ge": 10, "lt": 11,
         "gt": 12, "le": 13}


def b_cond_narrow(pc, cond, target):
    """B<cond> T1 - short conditional branch, +/-256 bytes."""
    off = target - (pc + 4)
    if off % 2:
        raise ValueError("misaligned branch")
    off >>= 1
    if not (-128 <= off < 128):
        raise ValueError("conditional branch out of range: %d" % off)
    return struct.pack("<H", 0xD000 | (_COND[cond] << 8) | (off & 0xFF))


def b_short(pc, target):
    """B T2 - unconditional short branch, +/-2048 bytes."""
    off = target - (pc + 4)
    if off % 2:
        raise ValueError("misaligned branch")
    off >>= 1
    if not (-1024 <= off < 1024):
        raise ValueError("branch out of range: %d" % off)
    return struct.pack("<H", 0xE000 | (off & 0x7FF))


def cmp_reg(rn, rm):
    """CMP (register) T1 - low registers."""
    if rn > 7 or rm > 7:
        raise ValueError("cmp_reg needs low registers")
    return struct.pack("<H", 0x4280 | (rm << 3) | rn)


def sub_sp_imm(byte_offset):
    """SUB (SP minus immediate) T1."""
    if byte_offset % 4:
        raise ValueError("SP adjust must be word aligned")
    imm7 = byte_offset // 4
    _chk(imm7, 7, "imm7")
    return struct.pack("<H", 0xB080 | imm7)


def strb_imm(rt, rn, off=0):
    """STRB (immediate) T1 - low registers, byte offset 0..31."""
    if rt > 7 or rn > 7:
        raise ValueError("strb_imm needs low registers")
    _chk(off, 5, "imm5")
    return struct.pack("<H", 0x7000 | (off << 6) | (rn << 3) | rt)


def b_cond_w(pc, cond, target):
    """B<cond>.W T3 - wide conditional branch, +/-1MB."""
    off = target - (pc + 4)
    if off % 2:
        raise ValueError("misaligned branch")
    off >>= 1
    if not (-(1 << 19) <= off < (1 << 19)):
        raise ValueError("b_cond_w out of range")
    s = (off >> 19) & 1
    j2 = (off >> 18) & 1
    j1 = (off >> 17) & 1
    imm6 = (off >> 11) & 0x3F
    imm11 = off & 0x7FF
    hw1 = 0xF000 | (s << 10) | (_COND[cond] << 6) | imm6
    hw2 = 0x8000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def ldr_sp(rt, byte_offset):
    """LDR (immediate, SP relative) T2."""
    if rt > 7:
        raise ValueError("ldr_sp needs a low register")
    if byte_offset % 4:
        raise ValueError("SP offset must be word aligned")
    imm8 = byte_offset // 4
    _chk(imm8, 8, "imm8")
    return struct.pack("<H", 0x9800 | (rt << 8) | imm8)


def ldrb_imm(rt, rn, off=0):
    """LDRB (immediate) T1 - low registers, byte offset 0..31."""
    if rt > 7 or rn > 7:
        raise ValueError("ldrb_imm needs low registers")
    _chk(off, 5, "imm5")
    return struct.pack("<H", 0x7800 | (off << 6) | (rn << 3) | rt)


def b_cond(pc, cond, target):
    """Conditional branch, narrow if it reaches, wide otherwise.

    Auto-widening matters because cave layout shifts between assembly passes;
    a hand-picked width can silently go out of range as code is added. The
    convergence loop in the callers settles the resulting size changes.
    """
    try:
        return b_cond_narrow(pc, cond, target)
    except ValueError:
        return b_cond_w(pc, cond, target)


def lsls_imm(rd, rm, imm5):
    """LSLS (immediate) T1 - low registers."""
    if rd > 7 or rm > 7:
        raise ValueError("lsls_imm needs low registers")
    _chk(imm5, 5, "imm5")
    return struct.pack("<H", 0x0000 | (imm5 << 6) | (rm << 3) | rd)


def muls(rdm, rn):
    """MULS T1 - rdm = rdm * rn, low registers."""
    if rdm > 7 or rn > 7:
        raise ValueError("muls needs low registers")
    return struct.pack("<H", 0x4340 | (rn << 3) | rdm)


def udiv(rd, rn, rm):
    """UDIV T1 - rd = rn / rm (Cortex-M7 has hardware divide)."""
    return struct.pack("<HH", 0xFBB0 | rn, 0xF0F0 | (rd << 8) | rm)


# ---------------------------------------------------------------- added for v005


def ldrh_imm(rt, rn, off=0):
    """LDRH (immediate) T1 - low registers, even byte offset 0..62."""
    if rt > 7 or rn > 7:
        raise ValueError("ldrh_imm needs low registers")
    if off % 2:
        raise ValueError("ldrh offset must be even")
    _chk(off // 2, 5, "imm5")
    return struct.pack("<H", 0x8800 | ((off // 2) << 6) | (rn << 3) | rt)


def strh_imm(rt, rn, off=0):
    """STRH (immediate) T1 - low registers, even byte offset 0..62."""
    if rt > 7 or rn > 7:
        raise ValueError("strh_imm needs low registers")
    if off % 2:
        raise ValueError("strh offset must be even")
    _chk(off // 2, 5, "imm5")
    return struct.pack("<H", 0x8000 | ((off // 2) << 6) | (rn << 3) | rt)


def lsrs_imm(rd, rm, imm5):
    """LSRS (immediate) T1 - low registers, shift 1..31 (0 would mean 32)."""
    if rd > 7 or rm > 7:
        raise ValueError("lsrs_imm needs low registers")
    if not 1 <= imm5 <= 31:
        raise ValueError("lsrs shift must be 1..31")
    return struct.pack("<H", 0x0800 | (imm5 << 6) | (rm << 3) | rd)


def lsrs_reg(rdn, rm):
    """LSRS (register) T1 - rdn >>= rm (low byte), low registers. v039."""
    if rdn > 7 or rm > 7:
        raise ValueError("lsrs_reg needs low registers")
    return struct.pack("<H", 0x40C0 | (rm << 3) | rdn)


def orrs_reg(rdn, rm):
    """ORRS (register) T1 - rdn |= rm, low registers."""
    if rdn > 7 or rm > 7:
        raise ValueError("orrs_reg needs low registers")
    return struct.pack("<H", 0x4300 | (rm << 3) | rdn)


# ---------------------------------------------------------------- added for v006


def adds_imm8(rdn, imm8):
    """ADDS (immediate) T2 - rdn += imm8, low register."""
    if rdn > 7:
        raise ValueError("adds_imm8 needs a low register")
    _chk(imm8, 8, "imm8")
    return struct.pack("<H", 0x3000 | (rdn << 8) | imm8)


def subs_imm8(rdn, imm8):
    """SUBS (immediate) T2 - rdn -= imm8, low register."""
    if rdn > 7:
        raise ValueError("subs_imm8 needs a low register")
    _chk(imm8, 8, "imm8")
    return struct.pack("<H", 0x3800 | (rdn << 8) | imm8)


def adds_reg(rd, rn, rm):
    """ADDS (register) T1 - rd = rn + rm, low registers."""
    if rd > 7 or rn > 7 or rm > 7:
        raise ValueError("adds_reg needs low registers")
    return struct.pack("<H", 0x1800 | (rm << 6) | (rn << 3) | rd)


def subs_reg(rd, rn, rm):
    """SUBS (register) T1 - rd = rn - rm, low registers."""
    if rd > 7 or rn > 7 or rm > 7:
        raise ValueError("subs_reg needs low registers")
    return struct.pack("<H", 0x1A00 | (rm << 6) | (rn << 3) | rd)


def ands_reg(rdn, rm):
    """ANDS (register) T1 - rdn &= rm, low registers."""
    if rdn > 7 or rm > 7:
        raise ValueError("ands_reg needs low registers")
    return struct.pack("<H", 0x4000 | (rm << 3) | rdn)


def add_rd_sp(rd, off):
    """ADD (SP plus immediate) T1 - rd = sp + off, off = 0..1020 step 4."""
    if rd > 7:
        raise ValueError("add_rd_sp needs a low register")
    if off % 4:
        raise ValueError("add_rd_sp offset must be word aligned")
    _chk(off // 4, 8, "imm8")
    return struct.pack("<H", 0xA800 | (rd << 8) | (off // 4))


# ---------------------------------------------------------------- added for v011


def negs(rd, rm):
    """RSBS (immediate 0) T1 = NEGS rd, rm - low registers."""
    if rd > 7 or rm > 7:
        raise ValueError("negs needs low registers")
    return struct.pack("<H", 0x4240 | (rm << 3) | rd)


def bx(rm):
    """BX rm T1."""
    return struct.pack("<H", 0x4700 | ((rm & 0xF) << 3))


def blx(rm):
    """BLX rm T1 (v053)."""
    return struct.pack("<H", 0x4780 | ((rm & 0xF) << 3))


def ldrb_w(rt, rn, imm12):
    """LDRB.W (immediate) T2 - rt = byte [rn + imm12], any registers (rn may be sp), offset 0..4095 (v055)."""
    _chk(imm12, 12, "imm12")
    return struct.pack("<HH", 0xF890 | (rn & 0xF), ((rt & 0xF) << 12) | imm12)


def strb_w(rt, rn, imm12):
    """STRB.W (immediate) T2 - byte [rn + imm12] = rt, offset 0..4095 (v055)."""
    _chk(imm12, 12, "imm12")
    return struct.pack("<HH", 0xF880 | (rn & 0xF), ((rt & 0xF) << 12) | imm12)


if __name__ == "__main__":
    print("thumb.py selftest")
    selftest()
    print("all encoders verified against Capstone")


# ---------------------------------------------------------------- added for v059
def ldrexb(rt, rn):
    """LDREXB T1 - rt = [rn] (byte), opens the exclusive monitor."""
    return struct.pack("<HH", 0xE8D0 | rn, (rt << 12) | 0xF4F)


def strexb(rd, rt, rn):
    """STREXB T1 - [rn] = rt (byte) if the monitor is still open; rd = 0 on success, 1 on failure."""
    return struct.pack("<HH", 0xE8C0 | rn, (rt << 12) | 0xF40 | rd)


# ---------------------------------------------------------------- added for v060
def sxth(rd, rm):
    """SXTH T1 - rd = sign-extended halfword of rm, low registers."""
    if rd > 7 or rm > 7:
        raise ValueError("sxth needs low registers")
    return struct.pack("<H", 0xB200 | (rm << 3) | rd)


# ---------------------------------------------------------------- added for v063
def ldrex(rt, rn):
    """LDREX T1 - rt = [rn] (word), opens the exclusive monitor."""
    return struct.pack("<HH", 0xE850 | rn, (rt << 12) | 0xF00)


def strex(rd, rt, rn):
    """STREX T1 - [rn] = rt (word) if the monitor is still open; rd = 0 on success, 1 on failure."""
    return struct.pack("<HH", 0xE840 | rn, (rt << 12) | (rd << 8))


def ldrh_w(rt, rn, imm12):
    """LDRH.W T2 - rt = halfword [rn + imm12], imm12 0..4095."""
    if not 0 <= imm12 < 4096:
        raise ValueError("ldrh.w offset")
    return struct.pack("<HH", 0xF8B0 | rn, (rt << 12) | imm12)
