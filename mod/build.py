"""Build the mod from your own stock 3.1.9 BLACKBOX.bin.

  python mod/build.py NN          -> out/BLACKBOX.bin   (NN = the release number on the splash, 3.1.9(NN))

Put the stock image at firmware/BLACKBOX-3.1.9.bin first (firmware/README.md). Needs: pip install capstone
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main(argv):
    if len(argv) != 1 or not argv[0].isdigit():
        print(__doc__)
        return 2
    os.environ["BB_MOD_VERSION"] = argv[0]
    os.environ.setdefault("BB_STOCK_VERSION", "3.1.9")
    sys.path.insert(0, HERE)
    import fwbase
    fwbase.check_stock()
    import build_all
    rc = build_all.main()
    if rc:
        return rc
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    dst = os.path.join(ROOT, "out", "BLACKBOX.bin")
    shutil.copyfile(os.path.join(HERE, "build", "test_all", "BLACKBOX.BIN"), dst)
    print("wrote %s sha256 %s" % (dst, fwbase.sha256_file(dst)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
