"""UI colour schemes (palette entry -> RGB).

Entry roles (static map): 1 cell/toolbar bg, 2 page bg, 3 all text,
4 selection, 5 accent, 6 red text, 7 waveform, 8 waveform bg, 10 marks/outlines,
11/12 green/red multi-select, 13/16/17 grid lines, 14 black, 15 white, 32 markers.
Only listed entries change; every other entry stays stock.
"""

# Okabe-Ito based, colour-blind safe. Passes all 9 contrast checks.
CVD = {
    1: 0x30353B,    # v013: cells a bit lighter so the dark gaps between SEQS/PADS cells show (v010: 0x16181B)
    2: 0x0C0D0F, 3: 0xF2F2F2, 4: 0x0071B1, 5: 0xE69F00, 6: 0xFF7A45,
    7: 0x56B4E9, 8: 0x0C0D0F, 10: 0x9DA3AA, 11: 0x009E73, 12: 0xD55E00,
    13: 0x0A0B0D,   # v012: grid lines near-black (v010: 0x1C1E22)
    14: 0x000000, 15: 0xFFFFFF,
    16: 0x666D77,   # v013: piano-roll beat lane, a bit darker (v012: 0x737A85, v010: 0x3C4046)
    17: 0x5E646C, 32: 0xF0E442,
    31: 0x56B4E9,   # v049: pressed button fill, sky blue instead of the stock cyan #09D7F5
    9: 0x52585F,    # v013 (a bit darker than v012 0x5E646C): new lane/panel grey for the piano roll, grids, menus, meters (gridsplit.py)
}

ACTIVE_NAME = "colour-blind safe"
ACTIVE = CVD
