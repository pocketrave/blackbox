"""Stock firmware profile: which stock image the mod is built on.

Every module that needs the stock image, its hash, its end address or its version string reads it
from here. BB_STOCK_VERSION picks the profile; BB_STOCK overrides the file path.
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # private: the blackbox-3.1.8 folder; public repo: the repo root
BASE = 0x08040000

PROFILES = {
    "3.1.8": {"file": "BLACKBOX.bin", "size": 728664,
              "sha256": "078847398cdad7663b3cbdcb1edbce49b5d80a2bfbbf4bc9292d88be19d11e7a"},
    "3.1.9": {"file": os.path.join("firmware", "BLACKBOX-3.1.9.bin"), "size": 728696,
              "sha256": "281ae303d32e5eb52adca7817a648a34e4bd3848017f26673dd9df3905f1341d"},
}
VERSION = os.environ.get("BB_STOCK_VERSION", "3.1.9")
if VERSION not in PROFILES:
    raise SystemExit("BB_STOCK_VERSION=%s: known stock versions are %s" % (VERSION, ", ".join(PROFILES)))
PROFILE = PROFILES[VERSION]
SIZE = PROFILE["size"]
SHA256 = PROFILE["sha256"]
STOCK_END = BASE + SIZE                 # first byte after the stock image: every mod cave lies above


def stock_path(version):
    return os.path.join(ROOT, PROFILES[version]["file"])


STOCK = os.environ.get("BB_STOCK") or stock_path(VERSION)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_stock(path=None):
    """Return `path` (default STOCK) if it is the pristine stock image of this profile, else exit."""
    path = path or STOCK
    if not os.path.isfile(path):
        raise SystemExit("stock %s not found: put the stock %s BLACKBOX.bin there (or set BB_STOCK)" % (path, VERSION))
    got = sha256_file(path)
    if got != SHA256:
        raise SystemExit("stock %s is not pristine %s (sha256 %s, expected %s)" % (path, VERSION, got[:16], SHA256[:16]))
    return path
