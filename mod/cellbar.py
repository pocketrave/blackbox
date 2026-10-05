"""v014: the SEQS cell progress bar spans the full cell width, with a 1-px frame.

The cell draw (body 0x080A41B8) has two bar layouts. Cells with an A-D letter (+0x198 != 0)
take the letter path 0x080A49AC, which leaves 10 px on the right for the letter. SEQS cells
keep a letter internally (v006 only hides it, LSKIP), so their bar was 53 of 63 px, and its frame
is two nested 1-px outlines. For SEQS view cells only (same range check as LSKIP), these
caves give the bar the full width and skip the inner outline. Other screens stay stock.
"""
import thumb as T
import seqscroll as SS

RECTOUTL = 0x0808E994
W1_SITE, W1_ORIG, W1_BACK = 0x080A49BA, bytes.fromhex("c3680193"), 0x080A49BE    # ldr r3,[r0,#0xc]; str r3,[sp,#4]
W2_SITE, W2_ORIG, W2_BACK = 0x080A48C8, bytes.fromhex("e268a2f10a03"), 0x080A48CE  # ldr r2,[r4,#0xc]; sub.w r3,r2,#0xa
RO_SITES = ((0x080A48C4, "playing bar"), (0x080A4886, "text-box variant (-200/1100)"))  # bl RectOutl (inner outline)
SEQS_EXTRA = 8                          # [sp+4] = w + 8, so the stock "-10" / "-12" become w-2 / w-4


def _in_seqs(c, va, L, rcell, ra, rb, no_label):
    """Branch to L[no_label] unless rcell is a SEQS view cell. Clobbers ra, rb, flags."""
    c += T.ldr_imm32(ra, SS.ROOT_PTR)
    c += T.ldr_imm(ra, ra)
    c += T.cmp_imm(ra, 0)
    c += T.b_cond(va + len(c), "eq", L.get(no_label, va))
    c += T.ldr_imm32(rb, SS.VIEW_OFF + SS.CELLS_OFF)
    c += T.add_reg(ra, rb)
    c += T.cmp_reg(rcell, ra)
    c += T.b_cond(va + len(c), "cc", L.get(no_label, va))
    c += T.ldr_imm32(rb, 4 * SS.ROW_STRIDE)
    c += T.add_reg(ra, rb)
    c += T.cmp_reg(rcell, ra)
    c += T.b_cond(va + len(c), "cs", L.get(no_label, va))
    return c


def w1(va, L):
    """r0 = cell: [sp+4] = w (+8 for SEQS cells). r1, r2 preserved."""
    c = T.ldr_imm(3, 0, 0xC)
    c += T.push_lo([1, 2])
    c = _in_seqs(c, va, L, 0, 1, 2, "store")
    c += T.adds_imm8(3, SEQS_EXTRA)
    L["store"] = va + len(c)
    c += T.pop_lo([1, 2])
    c += T.str_sp(3, 4)
    c += T.bw(va + len(c), W1_BACK)
    return c


def w2(va, L):
    """r4 = cell: SEQS cells r2 = r3 = w - 2 (fill base and its clamp); else stock r2 = w, r3 = w - 10.
    r0, r1 are dead here; r2 is only read by the clamp at 0x080A48F0."""
    c = T.ldr_imm(2, 4, 0xC)
    c += T.mov_reg(3, 2)
    c = _in_seqs(c, va, L, 4, 0, 1, "stock")
    c += T.subs_imm8(3, 2)
    c += T.mov_reg(2, 3)                    # clamp (cmp r3,r2 at 0x080A48F0) = w - 2: fill stays inside the frame
    c += T.b_short(va + len(c), L.get("back", va))
    L["stock"] = va + len(c)
    c += T.subs_imm8(3, 10)
    L["back"] = va + len(c)
    c += T.bw(va + len(c), W2_BACK)
    return c


def ro(va, L):
    """Replaces `bl RectOutl` for the inner outline: skipped for SEQS cells (r4), else stock."""
    c = T.push_lo([0, 1])
    c = _in_seqs(c, va, L, 4, 0, 1, "draw")
    c += T.pop_lo([0, 1])
    c += T.bx(14)                           # skip: return to the caller
    L["draw"] = va + len(c)
    c += T.pop_lo([0, 1])
    c += T.bw(va + len(c), RECTOUTL)        # tail call, lr intact
    return c
