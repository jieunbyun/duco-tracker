// Repeating small tasks (0071_tidy_repeat.sql): a series makes an ordinary small task on each
// of its dates, when Week first shows that day — every month, every year, or every year on a
// date of the Korean lunar calendar.
//
// The lunar calendar is the browser's own (Intl, calendar "dangi"): no table of dates to keep.
// A lunar date falls in its regular month, never a leap month, as lunar birthdays and memorial
// days are kept. A day a month does not have goes on its last day: the 31st on the 30th (or
// 28th), 29 February on the 28th, a lunar 30th on the 29th.
import { supabase } from "./supabase";
import { addDays, parse } from "./dates";
import type { Tidy } from "./tidy";

export type Every = "month" | "year" | "lunar_year";
export type Repeat = {
  id: string; title: string; every: Every; month: number | null; day: number;
  start_on: string; until: string | null; link: string | null; is_tidy: boolean; created_at: string;
};

async function check<T>(q: PromiseLike<{ data: T | null; error: { message: string } | null }>): Promise<T> {
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return data as T;
}

// ---- the lunar calendar ------------------------------------------------------------
const LUNAR = (() => {
  try {
    const f = new Intl.DateTimeFormat("en-u-ca-dangi", { timeZone: "UTC", year: "numeric", month: "numeric", day: "numeric" });
    return f.resolvedOptions().calendar === "dangi" ? f : null;
  } catch {
    return null;
  }
})();
/** Whether this browser knows the lunar calendar. */
export const hasLunar = !!LUNAR;

export type LunarDate = { month: number; day: number; leap: boolean };
/** The lunar month and day of a "YYYY-MM-DD" day; a leap month comes as "6bis" from Intl. */
export function lunarOf(iso: string): LunarDate | null {
  if (!LUNAR) return null;
  const parts = LUNAR.formatToParts(new Date(`${iso}T12:00:00Z`));
  const m = parts.find((p) => p.type === "month")?.value ?? "";
  const d = parts.find((p) => p.type === "day")?.value ?? "";
  return { month: parseInt(m, 10), day: parseInt(d, 10), leap: !/^\d+$/.test(m) };
}

// ---- which days a series falls on -----------------------------------------------------
const daysInMonth = (y: number, m: number) => new Date(y, m, 0).getDate(); // m: 1–12

/** Whether the series falls on this day (ignoring its start and stop). */
export function fallsOn(r: Pick<Repeat, "every" | "month" | "day">, iso: string): boolean {
  const [y, m, d] = iso.split("-").map(Number);
  if (r.every === "month") return d === Math.min(r.day, daysInMonth(y, m));
  if (r.every === "year") return m === r.month && d === Math.min(r.day, daysInMonth(y, m));
  const l = lunarOf(iso);
  if (!l || l.leap || l.month !== r.month) return false;
  if (l.day === r.day) return true;
  // a lunar 30th, in a month of 29 days, goes on its 29th
  return r.day === 30 && l.day === 29 && lunarOf(addDays(iso, 1))?.day === 1;
}
const live = (r: Repeat, iso: string) => iso >= r.start_on && (!r.until || iso <= r.until);

/** Its next `n` dates after `after`, while it runs (up to a few years ahead). */
export function nextDates(r: Repeat | Pick<Repeat, "every" | "month" | "day">, after: string, n = 3): string[] {
  const out: string[] = [];
  const full = "start_on" in r;
  for (let d = addDays(after, 1), i = 0; out.length < n && i < 366 * (n + 1); d = addDays(d, 1), i++) {
    if (full && r.until && d > r.until) break;
    if (fallsOn(r, d) && (!full || live(r, d))) out.push(d);
  }
  return out;
}

// ---- in words -----------------------------------------------------------------------
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];
export function describe(r: Pick<Repeat, "every" | "month" | "day">): string {
  if (r.every === "month") return `every month on the ${ordinal(r.day)}${r.day > 28 ? " (or its last day)" : ""}`;
  if (r.every === "year") return `every year on ${r.day} ${MONTHS[(r.month ?? 1) - 1]}`;
  return `every year on lunar ${r.month}/${r.day}`;
}
export const fmtShort = (iso: string) =>
  parse(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** The ways a task on this day can repeat: monthly, yearly, and yearly by the lunar calendar. */
export function waysFrom(day: string): { every: Every; month: number | null; day: number; note?: string }[] {
  const [, m, d] = day.split("-").map(Number);
  const out: { every: Every; month: number | null; day: number; note?: string }[] = [
    { every: "month", month: null, day: d },
    { every: "year", month: m, day: d },
  ];
  const l = lunarOf(day);
  if (l) {
    out.push({
      every: "lunar_year", month: l.month, day: l.day,
      note: l.leap ? `This day is in the leap ${ordinal(l.month)} month; the series keeps the regular one.` : undefined,
    });
  }
  return out;
}

// ---- the database ---------------------------------------------------------------------
const COLS = "id, title, every, month, day, start_on, until, link, is_tidy, created_at";

/** Every series, oldest first; null until 0071 is run. */
export async function loadRepeats(): Promise<Repeat[] | null> {
  const r = await supabase.from("tidy_repeat").select(COLS).order("created_at");
  if (r.error) {
    if (r.error.code === "PGRST205" || r.error.code === "42P01") return null;
    throw new Error(r.error.message);
  }
  return r.data as Repeat[];
}

/** Start a series from a small task: the task becomes its first date. */
export async function startRepeat(t: Tidy, way: { every: Every; month: number | null; day: number }): Promise<void> {
  const r = await check<{ id: string }>(supabase.from("tidy_repeat").insert({
    title: t.title, every: way.every, month: way.month, day: way.day, start_on: t.day,
    link: t.link ?? null, is_tidy: !!t.is_tidy,
  }).select("id").single());
  await check(supabase.from("tidy").update({ repeat_id: r.id, repeat_on: t.day }).eq("id", t.id));
}

/** Stop a series after a day: its tasks up to then stay; later ones not ticked go. */
export async function stopRepeat(id: string, after: string): Promise<void> {
  await check(supabase.from("tidy_repeat").update({ until: after }).eq("id", id));
  await check(supabase.from("tidy").delete().eq("repeat_id", id).gt("repeat_on", after).eq("is_done", false));
}

/**
 * Make the tasks the series are due for on the days from `from` to `to`, that are not made yet
 * (`have`: the tasks already loaded for those days). The database keeps one per series and
 * date, so a task moved to another week is not made again. The number made.
 */
export async function fillRepeats(repeats: Repeat[], from: string, to: string, have: Tidy[]): Promise<number> {
  const rows: Record<string, unknown>[] = [];
  for (const r of repeats) {
    for (let d = from < r.start_on ? r.start_on : from; d <= to && (!r.until || d <= r.until); d = addDays(d, 1)) {
      if (!fallsOn(r, d) || have.some((t) => t.repeat_id === r.id && t.repeat_on === d)) continue;
      rows.push({
        day: d, title: r.title, repeat_id: r.id, repeat_on: d, sort_order: null,
        ...(r.link ? { link: r.link } : {}), ...(r.is_tidy ? { is_tidy: true } : {}),
      });
    }
  }
  if (!rows.length) return 0;
  const made = await check<{ id: string }[]>(supabase.from("tidy")
    .upsert(rows, { onConflict: "repeat_id,repeat_on", ignoreDuplicates: true }).select("id"));
  return made?.length ?? 0;
}
