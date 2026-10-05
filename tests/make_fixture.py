"""Writes tests/fixtures/{stock.bin,built.bin,patch.json}: synthetic data (not firmware) for the JS tests."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from tests.test_patchlib import images   # noqa: E402
from tools.patchlib import make_patch    # noqa: E402

stock, built = images(seed=7)
d = os.path.join(HERE, "fixtures")
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "stock.bin"), "wb").write(stock)
open(os.path.join(d, "built.bin"), "wb").write(built)
json.dump(make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9"), open(os.path.join(d, "patch.json"), "w"), indent=1)
print("fixtures written")
