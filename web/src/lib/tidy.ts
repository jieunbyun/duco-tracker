// Small tasks / deadlines (0058_tidy.sql): a checkbox on a day in Week, with no hours, a
// link if you like (0063_tidy_link.sql), and ticked as a tidy-up or not (0066_tidy_kind.sql).
import { supabase } from "./supabase";
import { check } from "./data";

export type Tidy = {
  id: string; day: string; title: string; is_done: boolean; sort_order: number | null; created_at: string;
  link?: string | null; // absent until 0063 is run
  is_tidy?: boolean; // a tidy-up; absent until 0066 is run
};


/** The small tasks on the days from `from` to `to`, in order; null until 0058 is run. */
export async function loadTidies(from: string, to: string): Promise<Tidy[] | null> {
  const query = (cols: string) => supabase.from("tidy").select(cols)
    .gte("day", from).lte("day", to).order("day").order("sort_order", { nullsFirst: false }).order("created_at");
  const r = await query("*"); // every column there is: link and is_tidy are absent until 0063 and 0066 are run
  if (r.error) {
    if (r.error.code === "PGRST205" || r.error.code === "42P01") return null; // no such table yet
    throw new Error(r.error.message);
  }
  return r.data as unknown as Tidy[];
}
export async function addTidy(day: string, title: string, sort_order: number): Promise<void> {
  await check(supabase.from("tidy").insert({ day, title, sort_order }));
}
export async function saveTidy(id: string, fields: Partial<Pick<Tidy, "day" | "title" | "is_done" | "sort_order" | "link" | "is_tidy">>): Promise<void> {
  await check(supabase.from("tidy").update(fields).eq("id", id));
}
export async function deleteTidy(id: string): Promise<void> {
  await check(supabase.from("tidy").delete().eq("id", id));
}

/**
 * A link as typed or pasted, made safe to open: http(s) and mail links only; a bare address
 * ("outlook.office.com/…") gets https://. Null if it isn't one.
 */
export function cleanLink(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(s) ? s : `https://${s}`;
  try {
    const u = new URL(withScheme);
    return ["http:", "https:", "mailto:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
