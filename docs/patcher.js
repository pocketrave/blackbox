// Applies a diff-only release patch to the user's own stock image, in the browser. Same rules as
// tools/patchlib.py: the stock SHA-256 must match before anything happens, and so must the result's.
export const hex = (buf) => [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, "0")).join("");
export const unhex = (s) => Uint8Array.from(s.match(/../g) || [], (h) => parseInt(h, 16));
export const sha256 = async (bytes) => hex(await crypto.subtle.digest("SHA-256", bytes));

export class PatchError extends Error {}

export async function applyPatch(stock, patch) {
  if ((await sha256(stock)) !== patch.stock_sha256)
    throw new PatchError(`That is not the stock ${patch.stock_version} firmware (its SHA-256 differs), so nothing ` +
      `was patched. Use the BLACKBOX.bin from inside 1010music's ${patch.stock_version} zip (unzip it first).`);
  const add = unhex(patch.append);
  const out = new Uint8Array(stock.length + add.length);
  out.set(stock);
  for (const w of patch.writes) {
    const b = unhex(w.bytes);
    if (w.offset < 0 || w.offset + b.length > stock.length)
      throw new PatchError(`Write outside the stock image at offset ${w.offset}.`);
    out.set(b, w.offset);
  }
  out.set(add, stock.length);
  if (out.length !== patch.output_size || (await sha256(out)) !== patch.output_sha256)
    throw new PatchError("The patched image failed its check. Nothing to download.");
  return out;
}

export async function loadManifest(fetchFn, base) {
  let r;
  try {
    r = await fetchFn(`${base}manifest.json`);
  } catch (e) {
    throw new PatchError("Could not load the release list. Open this page from its web server " +
      "(not as a local file), or check your connection.");
  }
  if (!r.ok) throw new PatchError(`Could not load the release list (HTTP ${r.status}).`);
  return r.json();
}
