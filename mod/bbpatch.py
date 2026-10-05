#!/usr/bin/env python3
"""
blackbox firmware patcher — safety-first binary patching for BLACKBOX.bin

HARD RULES enforced by this module:
  1. The stock image is NEVER modified in place. Read stock -> write a new file.
  2. No byte below BASE (0x08040000) is ever written. That region belongs to the
     bootloader and is what makes SD-card recovery possible.
  3. Every patch verifies the bytes it is about to replace. If the image is not
     what we expect (wrong version, already patched), it fails loudly and writes
     nothing.

Usage is via the Patcher class; see phase1.py for a worked example.
"""

import os
import sys

BASE = 0x08040000          # application load address
BOOTLOADER_END = BASE      # nothing below this may ever be written


class PatchError(Exception):
    pass


class Patcher:
    def __init__(self, stock_path):
        self.stock_path = stock_path
        with open(stock_path, "rb") as f:
            self.stock = f.read()
        self.data = bytearray(self.stock)
        self.log = []
        self.orig_len = len(self.stock)

    # ---------- address helpers ----------

    def _check_va(self, va, length):
        if va < BOOTLOADER_END:
            raise PatchError(
                "REFUSED: write at VA 0x%08X is below 0x%08X (bootloader region)"
                % (va, BOOTLOADER_END))
        off = va - BASE
        if off < 0:
            raise PatchError("REFUSED: VA 0x%08X is below image base" % va)
        if off + length > len(self.data):
            raise PatchError(
                "REFUSED: write at VA 0x%08X len %d runs past image end (0x%08X)"
                % (va, length, BASE + len(self.data)))
        return off

    # ---------- primitive operations ----------

    def expect(self, va, expected):
        """Assert the current bytes at va match `expected`. Never writes."""
        off = self._check_va(va, len(expected))
        actual = bytes(self.data[off:off + len(expected)])
        if actual != expected:
            raise PatchError(
                "VERIFY FAILED at VA 0x%08X\n  expected: %s\n  actual:   %s"
                % (va, expected.hex(" "), actual.hex(" ")))
        return True

    def write_bytes(self, va, new, expected=None):
        """Overwrite bytes at va. If `expected` is given, verify first."""
        if expected is not None:
            if len(expected) != len(new):
                raise PatchError(
                    "REFUSED: replacement length %d != expected length %d "
                    "(in-place patches must not change size)"
                    % (len(new), len(expected)))
            self.expect(va, expected)
        off = self._check_va(va, len(new))
        old = bytes(self.data[off:off + len(new)])
        self.data[off:off + len(new)] = new
        self.log.append(("write", va, old, bytes(new)))
        return va

    def patch_cstring(self, va, old_str, new_str, encoding="ascii"):
        """Replace a NUL-terminated string with one of identical length."""
        old_b = old_str.encode(encoding)
        new_b = new_str.encode(encoding)
        if len(new_b) != len(old_b):
            raise PatchError(
                "REFUSED: %r is %d bytes but %r is %d bytes; string patches "
                "must be the same length" % (new_str, len(new_b), old_str, len(old_b)))
        # require the terminator to still be there afterwards
        off = self._check_va(va, len(old_b) + 1)
        if self.data[off + len(old_b)] != 0:
            raise PatchError(
                "REFUSED: no NUL terminator after string at VA 0x%08X" % va)
        return self.write_bytes(va, new_b, expected=old_b)

    def append(self, blob, align=4):
        """Append bytes past the current image end. Returns the VA of the blob.

        Used for code caves and new rodata in later steps.
        """
        while len(self.data) % align:
            self.data.append(0xFF)
        va = BASE + len(self.data)
        self.data.extend(blob)
        self.log.append(("append", va, b"", bytes(blob)))
        return va

    # ---------- output ----------

    IMAGE_ALIGN = 4     # the bootloader verifies in 32-bit words

    def pad_image(self):
        """Pad the image end to IMAGE_ALIGN.

        Every image the bootloader has accepted was a multiple of 4 bytes; the
        one image whose length was 2 mod 4 was rejected with "unable to verify".
        append(align=...) only aligns the START of each blob, so without this the
        final blob can leave the image on a halfword boundary.
        """
        pad = (-len(self.data)) % self.IMAGE_ALIGN
        if pad:
            va = BASE + len(self.data)
            self.data.extend(b"\xFF" * pad)
            self.log.append(("pad", va, b"", b"\xFF" * pad))
        return pad

    def save(self, out_path):
        if os.path.abspath(out_path) == os.path.abspath(self.stock_path):
            raise PatchError("REFUSED: refusing to overwrite the stock image")
        self.pad_image()
        if len(self.data) % self.IMAGE_ALIGN:
            raise PatchError("SAFETY: image length %d is not %d-byte aligned"
                             % (len(self.data), self.IMAGE_ALIGN))
        with open(out_path, "wb") as f:
            f.write(self.data)
        return out_path

    def report(self):
        lines = []
        lines.append("stock : %s (%d bytes, ends at VA 0x%08X)"
                     % (os.path.basename(self.stock_path), self.orig_len,
                        BASE + self.orig_len))
        lines.append("output: %d bytes (ends at VA 0x%08X)"
                     % (len(self.data), BASE + len(self.data)))
        delta = len(self.data) - self.orig_len
        lines.append("size delta: %+d bytes" % delta)
        lines.append("")
        changed = sum(1 for a, b in zip(self.stock, self.data) if a != b)
        lines.append("bytes changed within original image: %d" % changed)
        lines.append("bytes appended past original end:    %d" % max(0, delta))
        lines.append("")
        lines.append("lowest VA written: 0x%08X  (bootloader region starts below 0x%08X)"
                     % (min([e[1] for e in self.log], default=BASE), BOOTLOADER_END))
        lines.append("")
        for kind, va, old, new in self.log:
            if kind == "write":
                lines.append("  WRITE  VA 0x%08X  %s -> %s" % (va, old.hex(" "), new.hex(" ")))
                try:
                    lines.append("         %r -> %r" % (old.decode("ascii"), new.decode("ascii")))
                except Exception:
                    pass
            else:
                lines.append("  APPEND VA 0x%08X  %d bytes" % (va, len(new)))
        return "\n".join(lines)

    def verify_safety(self):
        """Final gate. Raises if any invariant was violated."""
        # 1. nothing below BASE (structurally impossible above, re-checked here)
        for kind, va, old, new in self.log:
            if va < BOOTLOADER_END:
                raise PatchError("SAFETY: write below bootloader boundary at 0x%08X" % va)
        # 2. the untouched prefix must be byte-identical outside logged writes
        touched = set()
        for kind, va, old, new in self.log:
            if kind == "write":
                for i in range(len(new)):
                    touched.add(va - BASE + i)
        for i in range(min(len(self.stock), len(self.data))):
            if self.stock[i] != self.data[i] and i not in touched:
                raise PatchError(
                    "SAFETY: unlogged change at file offset 0x%X (VA 0x%08X)"
                    % (i, BASE + i))
        return True
