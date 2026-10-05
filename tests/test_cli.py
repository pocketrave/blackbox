import json
import os

import pytest

import apply
from tests.test_patchlib import images
from tools import make_patch


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def test_publish_writes_patch_and_manifest(tmp_path):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    out = make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))
    assert out.endswith(os.path.join("patches", "v052.json"))
    with open(tmp_path / "patches" / "manifest.json") as f:
        m = json.load(f)
    assert m["latest"] == "v052" and m["releases"][0]["label"] == "3.1.9(52)"
    make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 53, "2026-10-11", str(tmp_path))
    with open(tmp_path / "patches" / "manifest.json") as f:
        m = json.load(f)
    assert [r["version"] for r in m["releases"]] == ["v053", "v052"]


def test_publish_refuses_stock_bytes(tmp_path):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built + stock[1000:1016])
    with pytest.raises(SystemExit, match="stock bytes"):
        make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))


def test_apply_end_to_end(tmp_path):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    patch = make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))
    out = tmp_path / "out" / "BLACKBOX.bin"
    assert apply.main([str(tmp_path / "stock.bin"), "--patch", patch, "-o", str(out)]) == 0
    assert out.read_bytes() == built


def test_refuses_to_overwrite_stock(tmp_path):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    patch = make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))
    assert apply.main([str(tmp_path / "stock.bin"), "--patch", patch, "-o", str(tmp_path / "stock.bin")]) == 1
    assert (tmp_path / "stock.bin").read_bytes() == stock


def test_refuses_to_overwrite_stock_case_variant(tmp_path):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    flipped = tmp_path / "STOCK.BIN"
    if not flipped.exists():
        pytest.skip("case-sensitive filesystem")
    patch = make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))
    assert apply.main([str(tmp_path / "stock.bin"), "--patch", patch, "-o", str(flipped)]) == 1
    assert (tmp_path / "stock.bin").read_bytes() == stock


def test_publish_refuses_non_reproducing_patch(tmp_path, monkeypatch):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    real = make_patch.make_patch

    def corrupt(*a, **k):
        p = real(*a, **k)
        p["append"] = "00" * 4 + p["append"]
        return p
    monkeypatch.setattr(make_patch, "make_patch", corrupt)
    with pytest.raises(SystemExit, match="does not reproduce"):
        make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))


def test_wrong_input_message(tmp_path, capsys):
    stock, built = images()
    write(tmp_path / "stock.bin", stock)
    write(tmp_path / "built.bin", built)
    patch = make_patch.publish(str(tmp_path / "stock.bin"), str(tmp_path / "built.bin"), 52, "2026-10-10", str(tmp_path))
    assert apply.main([str(tmp_path / "built.bin"), "--patch", patch, "-o", str(tmp_path / "x.bin")]) == 1
    assert "unzip" in capsys.readouterr().out
