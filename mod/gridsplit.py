"""v012: give the piano roll, grid layouts, menu panels and meters their own lane colour.

These draw calls used palette entry 1, which is also the SEQS/PADS/SONG cell background.
v010 made entry 1 near-black, so the near-black lines (13) and step numbers (2) drawn on them
disappeared. Each listed `movs rN,#1` becomes `movs rN,#9` (entry 9 is unused in stock), and
entry 9 gets a mid grey in palettes.py.
"""
LANE = 9

SITES = [
    (0x080BCA40, "piano roll: grid background"),
    (0x080BCBF0, "piano roll: key-strip lanes"),
    (0x080BCDCC, "piano roll: fill by left strip"),
    (0x080B167C, "menu/param panel 1"),
    (0x080B1694, "menu/param panel 2"),
    (0x080B16AC, "menu/param panel 3"),
    (0x080B16C4, "menu/param panel 4"),
    (0x080B173E, "panel fill (vt 0x080F0D10)"),
    (0x080C5A3A, "meter outline"),
    (0x080C5ABE, "meter tick"),
    (0x080AD7C8, "frame outline (0x080AD438)"),
]

# entry-1 uses that must stay dark (SEQS/PADS/SONG cells, lists, keyboard, progress track)
KEEP = [0x080A4448, 0x080A7090, 0x080BE996, 0x080BFD7A, 0x080C214C, 0x080C2496]


def patches(stock, base):
    """[(va, orig 2 bytes, new 2 bytes)] for bbpatch."""
    out = []
    for va, _ in SITES:
        o = stock[va - base:va - base + 2]
        out.append((va, o, bytes([LANE, o[1]])))
    return out
