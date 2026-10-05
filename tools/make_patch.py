"""Turn a built image into a release patch.

  python tools/make_patch.py STOCK BUILT NN [--date YYYY-MM-DD]   -> docs/patches/vNNN.json + manifest.json
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.patchlib import make_patch, stock_runs   # noqa: E402

STOCK_VERSION = "3.1.9"


def publish(stock_path, built_path, nn, date, docs_dir):
    with open(stock_path, "rb") as f:
        stock = f.read()
    with open(built_path, "rb") as f:
        built = f.read()
    version, label = "v%03d" % nn, "%s(%d)" % (STOCK_VERSION, nn)
    patch = make_patch(stock, built, version, label, STOCK_VERSION)
    runs = stock_runs(stock, patch)
    if runs:
        raise SystemExit("REFUSED: payload contains stock bytes (%d runs >= 16 B), first at offset %d"
                         % (len(runs), runs[0][0]))
    pdir = os.path.join(docs_dir, "patches")
    os.makedirs(pdir, exist_ok=True)
    out = os.path.join(pdir, version + ".json")
    with open(out, "w") as f:
        json.dump(patch, f, indent=1)
    mpath = os.path.join(pdir, "manifest.json")
    if os.path.isfile(mpath):
        with open(mpath) as f:
            manifest = json.load(f)
    else:
        manifest = {"latest": None, "releases": []}
    rel = [r for r in manifest["releases"] if r["version"] != version]
    rel.insert(0, {"version": version, "label": label, "file": version + ".json", "date": date,
                   "output_sha256": patch["output_sha256"]})
    rel.sort(key=lambda r: r["version"], reverse=True)
    manifest = {"latest": rel[0]["version"], "releases": rel}
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=1)
    print("wrote %s: %d writes, %d changed bytes, %d appended" % (
        out, len(patch["writes"]), sum(len(w["bytes"]) for w in patch["writes"]) // 2, len(patch["append"]) // 2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("built")
    ap.add_argument("nn", type=int)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    publish(a.stock, a.built, a.nn, a.date, os.path.join(ROOT, "docs"))
