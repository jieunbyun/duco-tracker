// Small tasks / deadlines (0058_tidy.sql): a checkbox on a day in Week, with no hours, a
// link if you like (0063_tidy_link.sql), and ticked as a tidy-up or not (0066_tidy_kind.sql).
import { supabase } from "./supabase";
import { check } from "./data";
import { addDays, parse } from "./dates";

export type Tidy = {
  id: string; day: string; title: string; is_done: boolean; sort_order: number | null; created_at: string;
  link?: string | null; // absent until 0063 is run
  is_tidy?: boolean; // a tidy-up; absent until 0066 is run
  // one date of a repeating series (0071_tidy_repeat.sql, lib/repeat.ts); absent until 0071 is run
  repeat_id?: string | null;
  repeat_on?: string | null; // the date it is for, kept when it is moved
  skipped?: boolean; // deleted from its series: hidden, and not made again
  follows?: string | null; // the small task this one follows on from (0072_tidy_follow.sql)
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
export async function saveTidy(id: string, fields: Partial<Pick<Tidy, "day" | "title" | "is_done" | "sort_order" | "link" | "is_tidy" | "repeat_id" | "repeat_on" | "skipped" | "follows">>): Promise<void> {
  await check(supabase.from("tidy").update(fields).eq("id", id));
}
export async function deleteTidy(id: string): Promise<void> {
  await check(supabase.from("tidy").delete().eq("id", id));
}

// ---- follow-ons (0072_tidy_follow.sql) ---------------------------------------------------
/** Whether an error is the follows column not being there yet. */
export const noFollows = (msg: string) => /follows/i.test(msg) && /column|schema cache|exist/i.test(msg);

export async function addFollowOn(t: Tidy, day: string, title: string, sort_order: number): Promise<void> {
  await check(supabase.from("tidy").insert({ day, title, sort_order, follows: t.id }));
}

/**
 * The small tasks linked to these (`have`) by follow-ons, either way, that are not among them:
 * so a task can name the one it follows, or its follow-on, in another week. Empty until 0072 is run.
 */
export async function loadLinked(have: Tidy[]): Promise<Tidy[]> {
  const ids = new Set(have.map((t) => t.id));
  const before = [...new Set(have.map((t) => t.follows).filter((x): x is string => !!x && !ids.has(x)))];
  const [a, b] = await Promise.all([
    before.length ? supabase.from("tidy").select("*").in("id", before) : Promise.resolve({ data: [], error: null }),
    ids.size ? supabase.from("tidy").select("*").in("follows", [...ids]) : Promise.resolve({ data: [], error: null }),
  ]);
  if (a.error || b.error) return [];
  return [...(a.data as Tidy[]), ...(b.data as Tidy[]).filter((t) => !ids.has(t.id))];
}

/** Every small task joined to this one by follow-ons, either way, this one too. */
async function chainOf(id: string): Promise<Tidy[]> {
  const got = new Map<string, Tidy>();
  let frontier = [id];
  for (let round = 0; frontier.length && round < 50; round++) {
    const [a, b] = await Promise.all([
      supabase.from("tidy").select("*").in("id", frontier),
      supabase.from("tidy").select("*").in("follows", frontier),
    ]);
    if (a.error || b.error) throw new Error((a.error ?? b.error)!.message);
    const next = new Set<string>();
    for (const t of [...(a.data as Tidy[]), ...(b.data as Tidy[])]) {
      if (got.has(t.id)) continue;
      got.set(t.id, t);
      next.add(t.id);
      if (t.follows && !got.has(t.follows)) next.add(t.follows);
    }
    frontier = [...next]; // the new ones: their follow-ons, and what they follow, are looked up next
  }
  return [...got.values()];
}

/** Move a small task to `to`, and those joined to it by follow-ons, not yet ticked, by as many days. */
export async function moveWithFollowOns(t: Tidy, to: string): Promise<void> {
  const shift = Math.round((parse(to).getTime() - parse(t.day).getTime()) / 86_400_000);
  for (const x of await chainOf(t.id)) {
    if (x.id === t.id) await saveTidy(x.id, { day: to, sort_order: null });
    else if (!x.is_done && !x.skipped) await saveTidy(x.id, { day: addDays(x.day, shift), sort_order: null });
  }
}

/** Before a small task goes: the ones that follow it follow the one before it instead. */
export async function unlinkFollowOns(t: Tidy): Promise<void> {
  await check(supabase.from("tidy").update({ follows: t.follows ?? null }).eq("follows", t.id));
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
