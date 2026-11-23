// Reading an .xlsx workbook in the browser, with nothing added: an .xlsx is a zip of XML
// files, read here with the browser's own DecompressionStream and DOMParser.
// Each cell comes with its value (as Excel last saved it), its formula and its link, if any.

export type Cell = { v: string | number | null; f?: string; link?: string };
export type Sheet = { name: string; cells: Map<string, Cell>; maxRow: number; maxCol: number };

/** "C12" → [row 12, column 3]. */
export function rc(ref: string): [number, number] {
  const m = ref.match(/^([A-Z]+)(\d+)$/)!;
  let col = 0;
  for (const ch of m[1]) col = col * 26 + (ch.charCodeAt(0) - 64);
  return [+m[2], col];
}
/** [row 12, column 3] → "C12". */
export function ref(row: number, col: number): string {
  let s = "";
  for (let c = col; c > 0; c = Math.floor((c - 1) / 26)) s = String.fromCharCode(65 + ((c - 1) % 26)) + s;
  return `${s}${row}`;
}
export const at = (s: Sheet, row: number, col: number) => s.cells.get(ref(row, col));
/** A cell's text, trimmed ("" when empty). */
export const text = (c: Cell | undefined) => (c?.v === null || c?.v === undefined ? "" : String(c.v).trim());

/** Excel's day number (1900 date system) → "2026-09-10". */
export function excelDate(n: number): string {
  return new Date(Date.UTC(1899, 11, 30) + Math.round(n) * 86400000).toISOString().slice(0, 10);
}

// ---- the zip --------------------------------------------------------------------------
async function inflate(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function unzip(buf: ArrayBuffer): Promise<Map<string, () => Promise<string>>> {
  const view = new DataView(buf);
  const bytes = new Uint8Array(buf);
  // the end-of-central-directory record, within the last 64 KB
  let eocd = -1;
  for (let i = buf.byteLength - 22; i >= Math.max(0, buf.byteLength - 65557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("This doesn't look like an .xlsx file.");
  const count = view.getUint16(eocd + 10, true);
  let p = view.getUint32(eocd + 16, true);
  const files = new Map<string, () => Promise<string>>();
  const dec = new TextDecoder();
  for (let i = 0; i < count; i++) {
    if (view.getUint32(p, true) !== 0x02014b50) break;
    const method = view.getUint16(p + 10, true);
    const size = view.getUint32(p + 20, true);
    const nameLen = view.getUint16(p + 28, true);
    const extraLen = view.getUint16(p + 30, true);
    const commentLen = view.getUint16(p + 32, true);
    const local = view.getUint32(p + 42, true);
    const name = dec.decode(bytes.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;
    files.set(name, async () => {
      const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
      const raw = bytes.subarray(start, start + size);
      if (method === 0) return dec.decode(raw);
      if (method === 8) return dec.decode(await inflate(raw));
      throw new Error(`Unsupported compression in ${name}.`);
    });
  }
  return files;
}

// ---- the workbook ---------------------------------------------------------------------
const xml = (s: string) => new DOMParser().parseFromString(s, "application/xml");
const byTag = (d: Document | Element, tag: string) => [...d.getElementsByTagName(tag)];
const R_ID = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

async function rels(files: Map<string, () => Promise<string>>, path: string): Promise<Map<string, string>> {
  const dir = path.slice(0, path.lastIndexOf("/") + 1);
  const relPath = `${dir}_rels/${path.slice(dir.length)}.rels`;
  const out = new Map<string, string>();
  if (!files.has(relPath)) return out;
  for (const r of byTag(xml(await files.get(relPath)!()), "Relationship")) {
    const t = r.getAttribute("Target") ?? "";
    out.set(r.getAttribute("Id") ?? "", r.getAttribute("TargetMode") === "External" || /^[a-z]+:/i.test(t) ? t
      : t.startsWith("/") ? t.slice(1) : dir + t);
  }
  return out;
}

/** Every sheet of an .xlsx file. */
export async function readXlsx(buf: ArrayBuffer): Promise<Sheet[]> {
  const files = await unzip(buf);
  const get = async (p: string) => (files.has(p) ? files.get(p)!() : null);
  const shared: string[] = [];
  const ss = await get("xl/sharedStrings.xml");
  if (ss) for (const si of byTag(xml(ss), "si")) shared.push(byTag(si, "t").map((t) => t.textContent ?? "").join(""));
  const wbRels = await rels(files, "xl/workbook.xml");
  const wb = xml((await get("xl/workbook.xml")) ?? "");
  const sheets: Sheet[] = [];
  for (const s of byTag(wb, "sheet")) {
    const path = wbRels.get(s.getAttributeNS(R_ID, "id") ?? s.getAttribute("r:id") ?? "") ?? "";
    const src = await get(path);
    if (!src) continue;
    const doc = xml(src);
    const cells = new Map<string, Cell>();
    let maxRow = 0, maxCol = 0;
    for (const c of byTag(doc, "c")) {
      const r = c.getAttribute("r");
      if (!r) continue;
      const t = c.getAttribute("t");
      const v = byTag(c, "v")[0]?.textContent ?? null;
      const f = byTag(c, "f")[0]?.textContent ?? undefined;
      let value: Cell["v"] = null;
      if (t === "s" && v !== null) value = shared[+v] ?? null;
      else if (t === "inlineStr") value = byTag(c, "t").map((x) => x.textContent ?? "").join("");
      else if (t === "str" || t === "e") value = v;
      else if (t === "b") value = v === "1" ? "TRUE" : "FALSE";
      else if (v !== null && v !== "") value = Number.isNaN(+v) ? v : +v;
      if (value === null && !f) continue;
      cells.set(r, { v: value, ...(f ? { f } : {}) });
      const [row, col] = rc(r);
      maxRow = Math.max(maxRow, row);
      maxCol = Math.max(maxCol, col);
    }
    // links on cells
    const sheetRels = await rels(files, path);
    for (const h of byTag(doc, "hyperlink")) {
      const r = h.getAttribute("ref")?.split(":")[0];
      const target = sheetRels.get(h.getAttributeNS(R_ID, "id") ?? h.getAttribute("r:id") ?? "");
      if (r && target) cells.set(r, { ...(cells.get(r) ?? { v: null }), link: target });
    }
    sheets.push({ name: s.getAttribute("name") ?? "", cells, maxRow, maxCol });
  }
  return sheets;
}

/** A formula made of numbers alone ("=425+450", "=80*2*6", "=313.94+(8.6*2+72.2)"): its value; else null. */
export function arithmetic(f: string): number | null {
  const s = f.replace(/^=/, "").replace(/\s+/g, "");
  if (!/^[\d.+\-*/()]+$/.test(s)) return null;
  let i = 0;
  const num = (): number => {
    if (s[i] === "(") { i++; const v = sum(); i++; return v; }
    if (s[i] === "-") { i++; return -num(); }
    const m = s.slice(i).match(/^\d+(\.\d+)?|^\.\d+/);
    if (!m) throw new Error("bad");
    i += m[0].length;
    return +m[0];
  };
  const product = (): number => {
    let v = num();
    while (s[i] === "*" || s[i] === "/") { const op = s[i++]; const w = num(); v = op === "*" ? v * w : v / w; }
    return v;
  };
  const sum = (): number => {
    let v = product();
    while (s[i] === "+" || s[i] === "-") { const op = s[i++]; const w = product(); v = op === "+" ? v + w : v - w; }
    return v;
  };
  try {
    const v = sum();
    return i === s.length && Number.isFinite(v) ? v : null;
  } catch {
    return null;
  }
}
/** The top-level terms added up in a formula of numbers ("=425+450+(8.6*2)" → [425, 450, 17.2]); null if not one. */
export function terms(f: string): number[] | null {
  const s = f.replace(/^=/, "").replace(/\s+/g, "");
  if (arithmetic(s) === null) return null;
  const out: string[] = [];
  let depth = 0, cur = "";
  for (const ch of s) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "+" && !depth && cur) { out.push(cur); cur = ""; continue; }
    cur += ch;
  }
  if (cur) out.push(cur);
  return out.map((t) => arithmetic(t)!);
}
