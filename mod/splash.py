"""v032 boot splash: the version label reads "<stock version>(NN)"; v051: the "by 1010music" label stays stock.

The splash view ctor (0x080C71DC..0x080C72B8) loads each label's text from its own literal-pool word;
each pool word has exactly one user. Repoint the version label's word at an appended string. The shared version
string 0x080CF290 (stock version: also a version query reply and other views) is NOT changed.

NN = the mod version number: BB_MOD_VERSION, else one more than the highest vNNN folder in the versions directory.
"""
import os

import fwbase

POOL_BY, ORIG_BY = 0x080C72C4, 0x080CFAAC      # -> "by 1010music" (centred label, 300 px; not patched)
POOL_VER, ORIG_VER = 0x080C72C8, 0x080CF290    # -> stock version (right-aligned label, 120 px)


def mod_version():
    env = os.environ.get("BB_MOD_VERSION")
    if env:
        return int(env)
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions")
    nums = [int(n[1:]) for n in os.listdir(d) if n[0] == "v" and n[1:].isdigit()] if os.path.isdir(d) else []
    return (max(nums) if nums else 0) + 1


def ver_string():
    return ("%s(%d)" % (fwbase.VERSION, mod_version())).encode() + b"\0"
