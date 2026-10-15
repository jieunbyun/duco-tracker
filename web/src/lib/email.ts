// Email is one shared pot: time logged under any Email category is counted in
// equal shares to every area that has an Email category (Teaching, Admin and
// Outreach), whichever of them it was logged under. Totals are unchanged; only
// the split between areas is.
import type { Taxonomy } from "./data";

type Row = { hours: number; area_id: string; category_kind: string; category_id?: string };

/** area id → its Email category id, for the areas that share email. */
export function emailAreas(tax: Taxonomy): Map<string, string> {
  const out = new Map<string, string>();
  for (const a of tax.areas) {
    const c = tax.categories.find((x) => x.area_id === a.id && x.kind === "email");
    if (c) out.set(a.id, c.id);
  }
  return out;
}

/** Rows with every email row replaced by equal shares, one per sharing area. */
export function shareEmail<T extends Row>(rows: T[], tax: Taxonomy): T[] {
  const areas = emailAreas(tax);
  if (areas.size < 2) return rows;
  const out: T[] = [];
  for (const r of rows) {
    if (r.category_kind !== "email") {
      out.push(r);
      continue;
    }
    for (const [area_id, category_id] of areas) {
      out.push({ ...r, hours: r.hours / areas.size, area_id, ...("category_id" in r ? { category_id } : {}) });
    }
  }
  return out;
}
