"""Patch your own stock Blackbox 3.1.9 firmware. Needs only Python 3.

  python apply.py path/to/BLACKBOX.bin [--patch docs/patches/vNNN.json] [-o out/BLACKBOX.bin]

The input must be the unmodified BLACKBOX.bin from 1010music's 3.1.9 zip. It is checked by SHA-256
before anything is written, and the result is checked again.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from tools.patchlib import PatchError, apply_patch   # noqa: E402


def latest_patch():
    mpath = os.path.join(ROOT, "docs", "patches", "manifest.json")
    m = json.load(open(mpath))
    return os.path.join(ROOT, "docs", "patches", m["latest"] + ".json")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("--patch", default=None)
    ap.add_argument("-o", "--out", default=os.path.join("out", "BLACKBOX.bin"))
    a = ap.parse_args(argv)
    with open(a.patch or latest_patch()) as f:
        patch = json.load(f)
    if os.path.abspath(a.out) == os.path.abspath(a.stock):
        print("REFUSED: that would overwrite your stock file. Keep it: it is your way back.")
        return 1
    try:
        with open(a.stock, "rb") as f:
            data = apply_patch(f.read(), patch)
    except PatchError as e:
        print("Nothing written: %s." % e)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes) = %s %s" % (a.out, len(data), patch["name"], patch["label"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
