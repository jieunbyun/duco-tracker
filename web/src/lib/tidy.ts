// Tidy-ups (0058_tidy.sql): small daily tasks with no hours, a checkbox on a day in Week.
import { supabase } from "./supabase";
import { check } from "./data";

export type Tidy = { id: string; day: string; title: string; is_done: boolean; sort_order: number | null; created_at: string };

/** The tidy-ups on the days from `from` to `to`, in order; null until 0058 is run. */
export async function loadTidies(from: string, to: string): Promise<Tidy[] | null> {
  const r = await supabase.from("tidy").select("id,day,title,is_done,sort_order,created_at")
    .gte("day", from).lte("day", to).order("day").order("sort_order", { nullsFirst: false }).order("created_at");
  if (r.error) {
    if (r.error.code === "PGRST205" || r.error.code === "42P01") return null; // no such table yet
    throw new Error(r.error.message);
  }
  return r.data as Tidy[];
}
export async function addTidy(day: string, title: string, sort_order: number): Promise<void> {
  await check(supabase.from("tidy").insert({ day, title, sort_order }));
}
export async function saveTidy(id: string, fields: Partial<Pick<Tidy, "day" | "title" | "is_done" | "sort_order">>): Promise<void> {
  await check(supabase.from("tidy").update(fields).eq("id", id));
}
export async function deleteTidy(id: string): Promise<void> {
  await check(supabase.from("tidy").delete().eq("id", id));
}
