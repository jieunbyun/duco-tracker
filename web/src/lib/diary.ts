// Diary (0059_diary.sql): a day's happiest and worst moments and mood, and a month's look back.
import { supabase } from "./supabase";
import { check } from "./data";

export const AREAS = ["work", "family", "friends", "health", "self", "other"] as const;
export type LifeArea = (typeof AREAS)[number];
export const areaLabel = (a: string | null) => (a ? a[0].toUpperCase() + a.slice(1) : "");

export type DiaryDay = {
  id: string; day: string; mood: number | null;
  best: string | null; best_why: string | null; best_area: LifeArea | null; best_star: boolean;
  worst: string | null; worst_area: LifeArea | null; worst_star: boolean;
};
export type DiaryFields = Omit<DiaryDay, "id">;
export type DiaryMonth = { month: string; reflection: string | null };

const missing = (code?: string) => code === "PGRST205" || code === "42P01";
const COLS = "id,day,mood,best,best_why,best_area,best_star,worst,worst_area,worst_star";

/** The days written from `from` to `to`; null until 0059 is run. */
export async function loadDays(from: string, to: string): Promise<DiaryDay[] | null> {
  const r = await supabase.from("diary_day").select(COLS).gte("day", from).lte("day", to).order("day");
  if (r.error) {
    if (missing(r.error.code)) return null;
    throw new Error(r.error.message);
  }
  return r.data as DiaryDay[];
}
/** One day, written or blank. */
export async function saveDay(fields: DiaryFields): Promise<void> {
  await check(supabase.from("diary_day").upsert({ ...fields, updated_at: new Date().toISOString() }, { onConflict: "user_id,day" }));
}
export async function deleteDay(day: string): Promise<void> {
  await check(supabase.from("diary_day").delete().eq("day", day));
}
export async function setStar(id: string, which: "best" | "worst", on: boolean): Promise<void> {
  await check(supabase.from("diary_day").update(which === "best" ? { best_star: on } : { worst_star: on }).eq("id", id));
}

export async function loadMonth(month: string): Promise<DiaryMonth> {
  const r = await supabase.from("diary_month").select("month,reflection").eq("month", month).maybeSingle();
  if (r.error && !missing(r.error.code)) throw new Error(r.error.message);
  return (r.data as DiaryMonth | null) ?? { month, reflection: null };
}
export async function saveMonth(month: string, reflection: string | null): Promise<void> {
  await check(supabase.from("diary_month").upsert({ month, reflection, updated_at: new Date().toISOString() }, { onConflict: "user_id,month" }));
}
