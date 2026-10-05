import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { applyPatch, loadManifest, PatchError } from "../../docs/patcher.js";

const fx = (name) => new URL(`../fixtures/${name}`, import.meta.url);
const stock = new Uint8Array(await readFile(fx("stock.bin")));
const built = new Uint8Array(await readFile(fx("built.bin")));
const patch = JSON.parse(await readFile(fx("patch.json"), "utf8"));

test("roundtrip matches the Python patcher", async () => {
  assert.deepEqual(await applyPatch(stock, patch), built);
});

test("wrong stock", async () => {
  await assert.rejects(applyPatch(built, patch), (e) => e instanceof PatchError && /unzip/.test(e.message));
});

test("tampered patch", async () => {
  const bad = { ...patch, append: patch.append.slice(0, -2) + (patch.append.endsWith("00") ? "01" : "00") };
  await assert.rejects(applyPatch(stock, bad), (e) => e instanceof PatchError && /failed its check/.test(e.message));
});

test("manifest load failure", async () => {
  const failing = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(loadManifest(failing, "patches/"), (e) => e instanceof PatchError && /web server/.test(e.message));
  const notFound = async () => ({ ok: false, status: 404 });
  await assert.rejects(loadManifest(notFound, "patches/"), (e) => e instanceof PatchError && /404/.test(e.message));
});
