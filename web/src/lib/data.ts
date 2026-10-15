import { supabase } from "./supabase";

export type Category = { id: string; area_id: string; code: string; label: string; kind: string; sort_order: number };
export type Target = { area_id: string; effective_from: string; weekly_hours: number; email_weekly_hours: number };
export type Area = { id: string; code: string; label: string; sort_order: number };
export type Taxonomy = { areas: Area[]; categories: Category[]; targets: Target[]; weeksPerYear: number };

export type EntryHours = {
  id: string;
  entry_date: string;
  hours: number;
  is_core: boolean;
  area_id: string;
  category_id: string;
  category_kind: string;
  project_id: string | null;
  project_name: string | null;
  milestone_id: string | null;
  milestone_title: string | null;
};

const PAGE = 1000; // PostgREST's default row cap per request

/** Run a range-able query page by page until a short page comes back. */
async function fetchAll<T>(page: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>): Promise<T[]> {
  const rows: T[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await page(from, from + PAGE - 1);
    if (error) throw new Error(error.message);
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE) return rows;
  }
}

export async function loadTaxonomy(): Promise<Taxonomy> {
  const [a, c, t, s] = await Promise.all([
    supabase.from("area").select("id,code,label,sort_order").eq("is_active", true).order("sort_order"),
    supabase.from("category").select("id,area_id,code,label,kind,sort_order").eq("is_active", true).order("sort_order"),
    supabase.from("area_target").select("area_id,effective_from,weekly_hours,email_weekly_hours"),
    supabase.from("user_setting").select("weeks_per_year").maybeSingle(),
  ]);
  for (const r of [a, c, t, s]) if (r.error) throw new Error(r.error.message);
  return {
    areas: a.data ?? [],
    categories: c.data ?? [],
    targets: (t.data ?? []).map((x) => ({
      ...x, weekly_hours: Number(x.weekly_hours), email_weekly_hours: Number(x.email_weekly_hours),
    })),
    weeksPerYear: Number(s.data?.weeks_per_year ?? 52),
  };
}

export async function loadEntryHours(from: string, to: string): Promise<EntryHours[]> {
  const rows = await fetchAll<EntryHours>((a, b) =>
    supabase
      .from("entry_hours")
      .select("id,entry_date,hours,is_core,area_id,category_id,category_kind,project_id,project_name,milestone_id,milestone_title")
      .gte("entry_date", from)
      .lte("entry_date", to)
      .order("started_at")
      .order("id")
      .range(a, b),
  );
  return rows.map((r) => ({ ...r, hours: Number(r.hours) }));
}

/** The target an area had on a given day: the latest effective_from not after it. */
export function targetOn(targets: Target[], areaId: string, day: string): Target | undefined {
  return targets
    .filter((t) => t.area_id === areaId && t.effective_from <= day)
    .sort((p, q) => q.effective_from.localeCompare(p.effective_from))[0];
}

export function fmtHours(h: number): string {
  return h >= 100 ? `${Math.round(h)} h` : `${Math.round(h * 10) / 10} h`;
}
