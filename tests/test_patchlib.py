import os
import random

import pytest

from tools.patchlib import PatchError, apply_patch, make_patch, stock_runs


def images(seed=1):
    rnd = random.Random(seed)
    stock = bytes(rnd.randrange(256) for _ in range(4096))
    built = bytearray(stock)
    built[100:104] = b"\x01\x02\x03\x04"
    built[2000] ^= 0xFF
    built += bytes(rnd.randrange(256) for _ in range(512))
    return stock, bytes(built)


def test_roundtrip():
    stock, built = images()
    p = make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")
    assert [w["offset"] for w in p["writes"]] == [100, 2000]
    assert apply_patch(stock, p) == built


def test_patch_holds_no_unchanged_stock_bytes():
    stock, built = images()
    p = make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")
    assert sum(len(w["bytes"]) // 2 for w in p["writes"]) == 5


def test_wrong_stock_refused():
    stock, built = images()
    p = make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")
    with pytest.raises(PatchError, match="not the stock 3.1.9"):
        apply_patch(built, p)


def test_tampered_patch_refused():
    stock, built = images()
    p = make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")
    p["append"] = p["append"][:-2] + ("00" if p["append"][-2:] != "00" else "01")
    with pytest.raises(PatchError, match="failed its check"):
        apply_patch(stock, p)


def test_write_outside_stock_refused():
    stock, built = images()
    p = make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")
    p["writes"].append({"offset": len(stock) - 1, "bytes": "0000"})
    with pytest.raises(PatchError, match="outside the stock image"):
        apply_patch(stock, p)


def test_unaligned_or_oversized_output_refused():
    stock, built = images()
    with pytest.raises(PatchError, match="multiple of 4"):
        make_patch(stock, built + b"\x00", "v001", "3.1.9(1)", "3.1.9")


def test_stock_runs_detects_copied_code():
    stock, built = images()
    p = make_patch(stock, built + stock[1000:1016], "v001", "3.1.9(1)", "3.1.9")
    assert stock_runs(stock, p) == [(len(built), stock[1000:1016].hex())]
    assert stock_runs(stock, make_patch(stock, built, "v001", "3.1.9(1)", "3.1.9")) == []
