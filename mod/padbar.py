"""v069: PADS progress bar with a 1-px frame (stock tile draw 0x080A43B8, overlay pass, bar path 0x080A47A0).

Stock draws a 2-px frame at the tile's bottom edge, outer (X, Y, w, 10) + inner (X+1, Y+1, w-2, 8), and fills
(X, Y, min(w*v/1000, w), 10) over it. v069 keeps the outer 1-px frame where it is, drops the inner one and fills
inside the frame: (X+1, Y+1, min((w-2)*v/1000, w-2), 8). Rects y-up {x, y, w, h}; a PADS tile is 63 x 54.

The path is reached only by tiles with +0x19C = 1 and no letter: the PADS view (stock) and, since v069, the FX send
page tiles (fxpage.fxlay). Four in-place writes, no cave. The inner rect (x+1, y+1, w-2, 8) is still stored at
[sp+0x28] by 0x080A47BE..0x080A47D2, so the fill takes its origin and width from there.

The record strip (+0x179, 0x080A46DA: fill (X, Y, w, 10)) needs no change: the 1-px frame plus a full fill inside it
covers exactly the same pixels."""

RECTOUTL = 0x0808E994
BAR_PATH = 0x080A47A0                  # the bar variant of the tile overlay pass (letter 0, 0 <= v <= 0x44B)

# (site, stock bytes, new bytes)
SITES = (
    (0x080A47DA, bytes.fromhex("eaf7dbf8"), bytes.fromhex("00bf00bf")),   # bl RectOutl (inner) -> nop; nop
    (0x080A47DE, bytes.fromhex("e268"), bytes.fromhex("0c9a")),           # ldr r2,[r4,#0xc] -> ldr r2,[sp,#0x30] (w-2)
    (0x080A47FC, bytes.fromhex("211d03c9"), bytes.fromhex("0a980b99")),   # adds r1,r4,#4; ldm r1,{r0,r1}
                                                                          # -> ldr r0,[sp,#0x28]; ldr r1,[sp,#0x2c]
    (0x080A480C, bytes.fromhex("0a22"), bytes.fromhex("0822")),           # movs r2,#0xa -> movs r2,#8 (fill h)
)
FRAME_H, FILL_H = 10, 8


def model(x, y, w, v):
    """Reference: (frames, fill) the bar path draws for a tile at (x, y) of width w and value 0 <= v <= 0x44B."""
    fw = (w - 2) * v // 1000
    return [(x, y, w, FRAME_H)], (x + 1, y + 1, min(fw, w - 2), FILL_H)
