# Third-party material

- **Spleen 8x16 font** (glyph rows in `mod/fonts/spleen16.json`, drawn into the firmware as the 16-px text font):
  Copyright (c) 2018-2026, Frederic Cambus. BSD 2-Clause License, full text in `mod/fonts/LICENSE.spleen`.

No 1010music code, data or artwork is included. The release patches in `docs/patches/` contain only bytes this
project writes; `tools/make_patch.py` refuses a patch in which any run of 16 or more bytes also occurs in the stock image.
