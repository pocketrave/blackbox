"""Diff-only release patches. A patch holds only the bytes this mod adds or changes, plus SHA-256s of the
stock image and of the result. It contains no unchanged bytes of the stock firmware."""
import hashlib

NAME = "blackbox-pocketrave-mod"
BASE = 0x08040000
BANK1_END = 0x08100000          # the bootloader refuses an image that ends past flash bank 1
MIN_RUN = 16


class PatchError(Exception):
    pass


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def make_patch(stock, built, version, label, stock_version):
    if len(built) < len(stock):
        raise PatchError("built image is shorter than stock")
    if len(built) % 4:
        raise PatchError("built image length %d is not a multiple of 4" % len(built))
    if BASE + len(built) > BANK1_END:
        raise PatchError("built image ends at 0x%08X, past flash bank 1" % (BASE + len(built)))
    writes, i = [], 0
    while i < len(stock):
        if stock[i] == built[i]:
            i += 1
            continue
        j = i
        while j < len(stock) and stock[j] != built[j]:
            j += 1
        writes.append({"offset": i, "bytes": built[i:j].hex()})
        i = j
    return {"name": NAME, "version": version, "label": label, "stock_version": stock_version,
            "stock_size": len(stock), "stock_sha256": sha256(stock),
            "output_size": len(built), "output_sha256": sha256(built),
            "writes": writes, "append": built[len(stock):].hex()}


def apply_patch(stock, patch):
    if sha256(stock) != patch["stock_sha256"]:
        raise PatchError("this is not the stock %s firmware (SHA-256 differs). Use the BLACKBOX.bin from inside "
                         "1010music's %s zip (unzip it first)" % (patch["stock_version"], patch["stock_version"]))
    out = bytearray(stock)
    for w in patch["writes"]:
        b, o = bytes.fromhex(w["bytes"]), w["offset"]
        if o < 0 or o + len(b) > len(stock):
            raise PatchError("write outside the stock image at offset %d" % o)
        out[o:o + len(b)] = b
    out += bytes.fromhex(patch["append"])
    if len(out) != patch["output_size"] or sha256(bytes(out)) != patch["output_sha256"]:
        raise PatchError("the patched image failed its check; nothing written")
    return bytes(out)


def stock_runs(stock, patch, n=MIN_RUN):
    """Runs of >= n payload bytes (more than 2 distinct values) that also occur somewhere in the stock image."""
    index = {stock[k:k + n] for k in range(len(stock) - n + 1)}
    chunks = [(w["offset"], bytes.fromhex(w["bytes"])) for w in patch["writes"]]
    chunks.append((patch["stock_size"], bytes.fromhex(patch["append"])))
    found = []
    for at, buf in chunks:
        k = 0
        while k <= len(buf) - n:
            s = buf[k:k + n]
            if len(set(s)) > 2 and s in index:
                found.append((at + k, s.hex()))
                k += n
            else:
                k += 1
    return found
