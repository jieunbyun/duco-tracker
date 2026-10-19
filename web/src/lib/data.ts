import { supabase } from "./supabase";
import { setWeekStartDay, addDays } from "./dates";

export type Category = {
  id: string;
  area_id: string;
  code: string;
  label: string;
  kind: string;
  sort_order: number;
  description: string | null; // your own note on what belongs here
  is_active: boolean; // false once retired: hidden from pickers, kept for history
};
export type Target = { area_id: string; effective_from: string; weekly_hours: number; email_weekly_hours: number };
export type Area = { id: string; code: string; label: string; sort_order: number };
export type Taxonomy = {
  areas: Area[];
  categories: Category[]; // active ones: what every picker offers
  allCategories: Category[]; // including retired ones, for labelling past hours
  targets: Target[];
  weeksPerYear: number;
  horizonMonths: number;
  weekStartsOn: number;
};

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

// Areas, categories, targets and settings change rarely: load them once and
// share the result; pass refresh after changing any of them.
let taxonomy: Promise<Taxonomy> | null = null;
export function loadTaxonomy(refresh = false): Promise<Taxonomy> {
  if (!taxonomy || refresh) {
    taxonomy = fetchTaxonomy();
    taxonomy.catch(() => (taxonomy = null));
  }
  return taxonomy;
}

async function fetchTaxonomy(): Promise<Taxonomy> {
  const [a, c, t, s] = await Promise.all([
    supabase.from("area").select("id,code,label,sort_order").eq("is_active", true).order("sort_order"),
    supabase.from("category").select("id,area_id,code,label,kind,sort_order,description,is_active").order("sort_order"),
    supabase.from("area_target").select("area_id,effective_from,weekly_hours,email_weekly_hours"),
    supabase.from("user_setting").select("weeks_per_year,horizon_months,week_starts_on").maybeSingle(),
  ]);
  for (const r of [a, c, t, s]) if (r.error) throw new Error(r.error.message);
  setWeekStartDay(Number(s.data?.week_starts_on ?? 1));
  return {
    areas: a.data ?? [],
    categories: (c.data ?? []).filter((x) => x.is_active),
    allCategories: c.data ?? [],
    targets: (t.data ?? []).map((x) => ({
      ...x, weekly_hours: Number(x.weekly_hours), email_weekly_hours: Number(x.email_weekly_hours),
    })),
    weeksPerYear: Number(s.data?.weeks_per_year ?? 52),
    horizonMonths: Number(s.data?.horizon_months ?? 12),
    weekStartsOn: Number(s.data?.week_starts_on ?? 1),
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

// ---- projects and milestones ---------------------------------------------
export const PROJECT_STATUSES = ["planned", "active", "paused", "done", "dropped"] as const;
export const MILESTONE_STATUSES = ["planned", "active", "done", "dropped"] as const;

export type Milestone = {
  id: string;
  project_id: string;
  title: string;
  status: string;
  start_on: string | null;
  due_on: string | null;
  planned_hours: number | null;
  hard_deadline: boolean;
  sort_order: number;
  notes: string | null;
};

export type Project = {
  id: string;
  category_id: string;
  name: string;
  status: string;
  start_on: string | null;
  end_on: string | null;
  planned_hours: number | null;
  is_important: boolean;
  notes: string | null;
  milestone: Milestone[];
};

const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

export async function loadProjects(): Promise<Project[]> {
  const { data, error } = await supabase
    .from("project")
    .select("id,category_id,name,status,start_on,end_on,planned_hours,is_important,notes," +
            "milestone(id,project_id,title,status,start_on,due_on,planned_hours,hard_deadline,sort_order,notes)")
    .order("name");
  if (error) throw new Error(error.message);
  return ((data ?? []) as unknown as Project[]).map((p) => ({
    ...p,
    planned_hours: num(p.planned_hours),
    milestone: p.milestone
      .map((m) => ({ ...m, planned_hours: num(m.planned_hours) }))
      .sort((a, b) => a.sort_order - b.sort_order || (a.due_on ?? "9").localeCompare(b.due_on ?? "9")),
  }));
}

export type ProjectFields = Omit<Project, "id" | "milestone">;
export type MilestoneFields = Omit<Milestone, "id">;

async function check<T>(q: PromiseLike<{ error: { message: string } | null; data?: T | null }>): Promise<T | null | undefined> {
  const { error, data } = await q;
  if (error) throw new Error(error.message);
  return data;
}

/** Insert (id null) or update; returns the row's id either way. */
export async function saveProject(id: string | null, fields: ProjectFields): Promise<string> {
  if (id) {
    await check(supabase.from("project").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("project").insert(fields).select("id").single());
  return row!.id;
}
export async function setProjectStatus(id: string, status: string): Promise<void> {
  await check(supabase.from("project").update({ status }).eq("id", id));
}
export async function deleteProject(id: string): Promise<void> {
  await check(supabase.from("project").delete().eq("id", id));
}
export async function saveMilestone(id: string | null, fields: MilestoneFields): Promise<string> {
  if (id) {
    await check(supabase.from("milestone").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("milestone").insert(fields).select("id").single());
  return row!.id;
}
export async function setMilestoneStatus(id: string, status: string): Promise<void> {
  await check(supabase.from("milestone").update({ status }).eq("id", id));
}
export async function deleteMilestone(id: string): Promise<void> {
  await check(supabase.from("milestone").delete().eq("id", id));
}

/** Every logged hour, thinly: enough for all-time project totals and recent pace. */
export type HourRow = Pick<EntryHours, "entry_date" | "hours" | "area_id" | "category_kind" | "project_id" | "milestone_id">;
export async function loadAllHours(): Promise<HourRow[]> {
  const rows = await fetchAll<HourRow>((a, b) =>
    supabase
      .from("entry_hours")
      .select("entry_date,hours,area_id,category_kind,project_id,milestone_id")
      .order("started_at")
      .order("id")
      .range(a, b),
  );
  return rows.map((r) => ({ ...r, hours: Number(r.hours) }));
}

// ---- time entries ----------------------------------------------------------
export type TimeEntry = {
  id: string;
  category_id: string;
  project_id: string | null;
  milestone_id: string | null;
  started_at: string;
  ended_at: string | null;
  manual_minutes: number | null;
  minutes: number;
  description: string | null;
  is_core: boolean;
};
export type TimeEntryFields = Omit<TimeEntry, "id" | "minutes">;

const ENTRY_COLS = "id,category_id,project_id,milestone_id,started_at,ended_at,manual_minutes,minutes,description,is_core";

export async function loadRecentEntries(limit = 20): Promise<TimeEntry[]> {
  const { data, error } = await supabase
    .from("time_entry")
    .select(ENTRY_COLS)
    .order("started_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return (data ?? []).map((e) => ({ ...e, minutes: Number(e.minutes) }));
}

export async function saveEntry(id: string | null, fields: TimeEntryFields): Promise<string> {
  if (id) {
    await check(supabase.from("time_entry").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("time_entry").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteEntry(id: string): Promise<void> {
  await check(supabase.from("time_entry").delete().eq("id", id));
}

// ---- week planning: to-dos and their sittings ------------------------------
// A to-do (task or meeting) belongs to a week by due_on; a sitting (todo_slot)
// places it on a day, with clock times for a meeting and optional hours for a
// task. A sitting that has been logged points at its time entry.
export type Todo = {
  id: string;
  kind: "task" | "meeting" | "idea"; // idea: "To think about", not tied to a week
  title: string;
  due_on: string;
  category_id: string | null;
  project_id: string | null;
  milestone_id: string | null;
  est_hours: number | null;
  is_core: boolean;
  must_this_week: boolean;
  is_done: boolean;
  done_at: string | null;
  is_cancelled: boolean;
  sort_order: number;
  note: string | null;
  // from Outlook (see outlook.ts); reviewed is false until kept
  source: "outlook" | null;
  source_key: string | null;
  source_uid: string | null;
  source_date: string | null;
  source_start: string | null;
  source_end: string | null;
  source_free: boolean;
  source_all_day: boolean;
  reviewed: boolean;
  is_tentative: boolean; // on the calendar, not counted as planned until confirmed
  source_tentative: boolean;
};
export type TodoFields = Omit<Todo, "id">;

export type Slot = {
  id: string;
  todo_id: string;
  planned_on: string;
  start_time: string | null; // "HH:MM:SS"
  end_time: string | null;
  planned_hours: number | null;
  entry_id: string | null;
  is_cancelled: boolean;
  sort_order: number | null;
};
export type SlotFields = Omit<Slot, "id">;

const TODO_COLS =
  "id,kind,title,due_on,category_id,project_id,milestone_id,est_hours,is_core,must_this_week,is_done,done_at,is_cancelled,sort_order,note,source,source_key,source_uid,source_date,source_start,source_end,source_free,source_all_day,reviewed,is_tentative,source_tentative";
export { TODO_COLS, SLOT_COLS, asTodo, asSlot, check };
const SLOT_COLS = "id,todo_id,planned_on,start_time,end_time,planned_hours,entry_id,is_cancelled,sort_order";

const asTodo = (t: Todo): Todo => ({ ...t, est_hours: num(t.est_hours) });
const asSlot = (x: Slot): Slot => ({ ...x, planned_hours: num(x.planned_hours) });

export type WeekPlan = { todos: Todo[]; slots: Slot[]; carried: Set<string> };

/**
 * Everything planned for a week: to-dos due in it, to-dos with a sitting in
 * it, and — for the current week — open tasks left over from earlier weeks.
 */
export async function loadWeekPlan(from: string, to: string, carryOver: boolean): Promise<WeekPlan> {
  const [due, slots, old] = await Promise.all([
    supabase.from("todo").select(TODO_COLS).gte("due_on", from).lte("due_on", to),
    supabase.from("todo_slot").select(SLOT_COLS).gte("planned_on", from).lte("planned_on", to),
    carryOver
      ? supabase.from("todo").select(TODO_COLS).lt("due_on", from).eq("kind", "task")
          .eq("is_done", false).eq("is_cancelled", false)
      : Promise.resolve({ data: [] as Todo[], error: null }),
  ]);
  for (const r of [due, slots, old]) if (r.error) throw new Error(r.error.message);

  const todos = new Map<string, Todo>();
  for (const t of [...(due.data ?? []), ...(old.data ?? [])] as Todo[]) todos.set(t.id, asTodo(t));
  const missing = [...new Set((slots.data as Slot[]).map((x) => x.todo_id))].filter((id) => !todos.has(id));
  if (missing.length) {
    const extra = await check<Todo[]>(supabase.from("todo").select(TODO_COLS).in("id", missing));
    for (const t of extra ?? []) todos.set(t.id, asTodo(t));
  }
  // every sitting of these to-dos, so a card knows its siblings in other weeks
  const allSlots = todos.size
    ? (await check<Slot[]>(supabase.from("todo_slot").select(SLOT_COLS).in("todo_id", [...todos.keys()]))) ?? []
    : [];
  return {
    todos: [...todos.values()],
    slots: allSlots.map(asSlot),
    carried: new Set((old.data as Todo[]).map((t) => t.id)),
  };
}

export async function saveTodo(id: string | null, fields: Partial<TodoFields>): Promise<string> {
  if (id) {
    await check(supabase.from("todo").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("todo").insert(fields).select("id").single());
  return row!.id;
}
/** Open ideas ("To think about"), newest first — whatever week they were jotted in. */
export async function loadIdeas(): Promise<Todo[]> {
  return ((await check<Todo[]>(
    supabase.from("todo").select(TODO_COLS).eq("kind", "idea").eq("is_done", false).eq("is_cancelled", false)
      .order("created_at", { ascending: false }),
  )) ?? []).map(asTodo);
}

export async function deleteTodo(id: string): Promise<void> {
  await check(supabase.from("todo").delete().eq("id", id));
}
export async function saveSlot(id: string | null, fields: Partial<SlotFields>): Promise<string> {
  if (id) {
    await check(supabase.from("todo_slot").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("todo_slot").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteSlot(id: string): Promise<void> {
  await check(supabase.from("todo_slot").delete().eq("id", id));
}

/**
 * Put deleted rows back with their original ids (for undo), so anything that
 * pointed at them still does. Time entries drop their computed minutes.
 */
export async function reinsertTodo(todo: Todo, slots: Slot[]): Promise<void> {
  await check(supabase.from("todo").insert(todo));
  if (slots.length) await check(supabase.from("todo_slot").insert(slots));
}
export async function reinsertSlot(slot: Slot): Promise<void> {
  await check(supabase.from("todo_slot").insert(slot));
}
export async function reinsertEntry(entry: TimeEntry): Promise<void> {
  const { minutes: _computed, ...row } = entry;
  await check(supabase.from("time_entry").insert(row));
}

/** Time entries that started within [from, to] (whole days). */
export async function loadEntriesBetween(from: string, to: string): Promise<TimeEntry[]> {
  const rows = await fetchAll<TimeEntry>((a, b) =>
    supabase
      .from("time_entry")
      .select(ENTRY_COLS)
      .gte("started_at", `${from}T00:00:00+00:00`)
      .lt("started_at", `${addDays(to, 1)}T00:00:00+00:00`)
      .order("started_at")
      .order("id")
      .range(a, b),
  );
  return rows.map((e) => ({ ...e, minutes: Number(e.minutes) }));
}

// ---- CV ------------------------------------------------------------------------
export type CvEntry = {
  id: string;
  entry_date: string;
  cv_year: number | null;
  cv_section: string;
  cv_subsection: string | null;
  title: string;
  organisation: string | null;
  location: string | null;
  role: string | null;
  description: string | null;
  outcome: string | null;
  metrics: string | null;
  evidence_url: string | null;
  student_level: string | null;
  start_on: string | null;
  end_on: string | null;
  status: string;
  source_type: string;
  entry_id: string | null;
  milestone_id: string | null;
  project_id: string | null;
};
export type CvFields = Omit<CvEntry, "id">;

export async function loadCv(): Promise<CvEntry[]> {
  const rows = await check<CvEntry[]>(
    supabase.from("cv_entry").select("*").order("entry_date", { ascending: false }),
  );
  return rows ?? [];
}
export async function saveCv(id: string | null, fields: Partial<CvFields>): Promise<string> {
  const withYear = fields.entry_date ? { ...fields, cv_year: Number(fields.entry_date.slice(0, 4)) } : fields;
  if (id) {
    await check(supabase.from("cv_entry").update({ ...withYear, updated_at: new Date().toISOString() }).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("cv_entry").insert(withYear).select("id").single());
  return row!.id;
}
export async function deleteCv(id: string): Promise<void> {
  await check(supabase.from("cv_entry").delete().eq("id", id));
}

export type Settings = { weeks_per_year: number; horizon_months: number; week_starts_on: number };
/** A new category in an area; it sorts after the others but before Email and Miscellaneous. */
export async function addCategory(area: Area, label: string, kind: string, existing: Category[]): Promise<void> {
  const slug = label.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 16) || "CAT";
  let code = `${area.code}_${slug}`;
  for (let n = 2; existing.some((c) => c.code === code); n++) code = `${area.code}_${slug}_${n}`;
  const inArea = existing.filter((c) => c.area_id === area.id && c.kind !== "email" && c.kind !== "misc");
  const sort_order = Math.min(94, Math.max(10, ...inArea.map((c) => c.sort_order)) + 5);
  await check(supabase.from("category").insert({ area_id: area.id, code, label: label.trim(), kind, sort_order }));
  await loadTaxonomy(true);
}

/** How much refers to a category: deciding between delete, retire, or neither. */
export async function categoryUsage(id: string): Promise<{ entries: number; todos: number; projects: number; liveProjects: number }> {
  const count = async (q: PromiseLike<{ count: number | null; error: { message: string } | null }>) => {
    const { count: n, error } = await q;
    if (error) throw new Error(error.message);
    // an unreadable count must never pass for "unused": removal stops instead
    if (n === null) throw new Error("Could not check what uses this category; nothing was removed.");
    return n;
  };
  const [entries, todos, projects, liveProjects] = await Promise.all([
    count(supabase.from("time_entry").select("id", { count: "exact", head: true }).eq("category_id", id)),
    count(supabase.from("todo").select("id", { count: "exact", head: true }).eq("category_id", id)),
    count(supabase.from("project").select("id", { count: "exact", head: true }).eq("category_id", id)),
    count(supabase.from("project").select("id", { count: "exact", head: true }).eq("category_id", id)
      .in("status", ["planned", "active", "paused"])),
  ]);
  return { entries, todos, projects, liveProjects };
}
export async function deleteCategory(id: string): Promise<void> {
  await check(supabase.from("category").delete().eq("id", id));
  await loadTaxonomy(true);
}
export async function setCategoryActive(id: string, active: boolean): Promise<void> {
  await check(supabase.from("category").update({ is_active: active }).eq("id", id));
  await loadTaxonomy(true);
}

export async function saveCategory(id: string, fields: { label: string; kind: string; description: string | null }): Promise<void> {
  await check(supabase.from("category").update(fields).eq("id", id));
  await loadTaxonomy(true);
}

export async function saveSettings(fields: Settings): Promise<void> {
  await check(supabase.from("user_setting").upsert(fields));
  await loadTaxonomy(true);
}

/** New weekly targets from a date on; earlier periods keep their targets. */
export async function saveTargets(rows: Omit<Target, never>[]): Promise<void> {
  await check(supabase.from("area_target").upsert(rows, { onConflict: "area_id,effective_from" }));
  await loadTaxonomy(true);
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
