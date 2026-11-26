// The Day tab: everything written down on one day, from every tab, to read back like a diary.
// Each entry carries the address of its own tab (with which one in "?…"), where it is changed;
// see dayBack.svelte.ts. Nothing here writes. A table not made yet (its SQL not run) or one
// that fails to load just leaves its part out.
import { supabase } from "./supabase";
import { loadEntriesBetween, loadWeekPlan, loadProjects, loadTaxonomy, TODO_COLS } from "./data";
import type { TimeEntry, Todo, Project, Taxonomy } from "./data";
import { loadTidies } from "./tidy";
import { loadDays, areaLabel } from "./diary";
import type { DiaryDay } from "./diary";
import { money } from "./budget";
import { SKILLS } from "./practice";
import { addDays, parse, weekStart } from "./dates";

export type DayItem = {
  key: string;
  when?: string; // "09:00–10:30", or how long
  text: string;
  more?: string | null; // a longer text under it (a note's body)
  meta?: string; // where it belongs: a project, a topic, a reading
  done?: boolean; // ticked or not, for what can be
  href: string | null; // where it is changed
};
export type DaySection = { key: string; title: string; total?: string; items: DayItem[] };
export type DayLog = { diary: DiaryDay | null; diaryMissing: boolean; sections: DaySection[] };

type Q = PromiseLike<{ data: unknown; error: unknown }>;
async function rows<T>(q: Q): Promise<T[]> {
  try {
    const r = await q;
    return r.error ? [] : ((r.data ?? []) as T[]);
  } catch {
    return [];
  }
}
/** The `col` of each row of `table` with these ids. */
async function namesOf(table: string, col: string, ids: (string | null | undefined)[]): Promise<Map<string, string>> {
  const want = [...new Set(ids.filter((x): x is string => !!x))];
  if (!want.length) return new Map();
  const got = await rows<Record<string, string>>(supabase.from(table).select(`id,${col}`).in("id", want));
  return new Map(got.map((r) => [r.id, r[col]]));
}

const hm = (t: string | null | undefined) => (t ? t.slice(0, 5) : "");
// time entries hold the diary's wall-clock time labelled UTC (see dates.ts)
const clock = (ts: string | null) => (ts ? ts.slice(11, 16) : "");
const hours = (min: number) => {
  const h = Math.round((min / 60) * 100) / 100;
  return `${h} h`;
};
const span = (a: string, b: string) => (a && b ? `${a}–${b}` : a);
const join = (...xs: (string | null | undefined)[]) => xs.filter((x) => x && x.trim()).join(" · ");
const clip = (s: string | null | undefined, n = 400) => {
  const t = (s ?? "").trim();
  return t.length > n ? `${t.slice(0, n).trimEnd()}…` : t || null;
};

export async function loadDay(day: string): Promise<DayLog> {
  // stamps made by the clock (done_at, created_at) are true UTC: the day runs from local midnight
  const from = parse(day).toISOString();
  const to = parse(addDays(day, 1)).toISOString();
  const week = `#/week?w=${weekStart(day)}&d=${day}`;
  const me = (await supabase.auth.getSession()).data.session?.user.id ?? "";

  const [
    diary, entries, plan, doneTodos, newIdeas, tidies, ideaNotes, meetings, expNotes, readingNotes, interactions,
    thoughts, sessions, failureNotes, actionsDone, actionsNew, comments, actionTime, expenses, cv, tax, projects,
  ] = await Promise.all([
    loadDays(day, day).catch(() => [] as DiaryDay[]),
    loadEntriesBetween(day, day).catch(() => [] as TimeEntry[]),
    loadWeekPlan(day, day).catch(() => ({ todos: [] as Todo[], slots: [] })),
    rows<Todo>(supabase.from("todo").select(TODO_COLS).neq("kind", "action").gte("done_at", from).lt("done_at", to)),
    rows<Todo & { created_at: string }>(supabase.from("todo").select(`${TODO_COLS},created_at`).eq("kind", "idea")
      .gte("created_at", from).lt("created_at", to)),
    loadTidies(day, day).then((x) => x ?? []).catch(() => []),
    rows<{ id: string; todo_id: string; body: string; created_at: string }>(
      supabase.from("idea_note").select("id,todo_id,body,created_at").gte("created_at", from).lt("created_at", to).order("created_at")),
    rows<{ id: string; series_id: string; title: string | null; people: string | null; sections: { heading: string; body: string }[] }>(
      supabase.from("meeting").select("id,series_id,title,people,sections").eq("met_on", day).order("created_at")),
    rows<{ id: string; topic_id: string; body: string; tags: string[] }>(
      supabase.from("exp_note").select("id,topic_id,body,tags").eq("noted_on", day).order("created_at")),
    rows<{ id: string; reading_id: string; page: string | null; body: string | null; quote?: string | null }>(
      supabase.from("reading_note").select("*").eq("noted_on", day)),
    rows<{ id: string; contact_id: string; body: string }>(
      supabase.from("contact_interaction").select("id,contact_id,body").eq("met_on", day).order("created_at")),
    rows<{ id: string; node_id: string; body: string; valid: boolean }>(
      supabase.from("pw_thought").select("id,node_id,body,valid").eq("noted_on", day).order("created_at")),
    rows<{ id: string; practice_id: string; skill: string; minutes: number | null; did: string | null; went_well: string | null; to_fix: string | null }>(
      supabase.from("practice_session").select("id,practice_id,skill,minutes,did,went_well,to_fix").eq("done_on", day).order("created_at")),
    rows<{ id: string; failure_id: string; kind: string; body: string }>(
      supabase.from("failure_note").select("id,failure_id,kind,body").eq("noted_on", day).order("created_at")),
    rows<{ id: string; title: string; project_id: string | null; milestone_id: string | null }>(
      supabase.from("todo").select("id,title,project_id,milestone_id").eq("kind", "action").eq("user_id", me)
        .eq("is_done", true).gte("done_at", from).lt("done_at", to)),
    rows<{ id: string; title: string; project_id: string | null; milestone_id: string | null; is_done: boolean }>(
      supabase.from("todo").select("id,title,project_id,milestone_id,is_done").eq("kind", "action").eq("user_id", me)
        .gte("created_at", from).lt("created_at", to)),
    rows<{ id: string; action_id: string; body: string | null; links: string[] | null }>(
      supabase.from("action_comment").select("id,action_id,body,links").eq("author_id", me)
        .gte("created_at", from).lt("created_at", to).order("created_at")),
    rows<{ id: string; action_id: string; start_time: string | null; end_time: string | null; hours: number }>(
      supabase.from("action_time").select("id,action_id,start_time,end_time,hours").eq("worked_on", day).eq("user_id", me)),
    rows<{ id: string; budget_id: string; amount: number; item: string | null; detail: string | null }>(
      supabase.from("budget_expense").select("id,budget_id,amount,item,detail").eq("spent_on", day).order("created_at")),
    rows<{ id: string; title: string; cv_section: string; organisation: string | null; description: string | null }>(
      supabase.from("cv_entry").select("id,title,cv_section,organisation,description").eq("entry_date", day)),
    loadTaxonomy().catch(() => null as Taxonomy | null),
    loadProjects().catch(() => [] as Project[]),
  ]);

  // the names of what the notes are on
  const actionIds = [...comments.map((c) => c.action_id), ...actionTime.map((t) => t.action_id)];
  const noteIds = [...new Set(ideaNotes.map((n) => n.todo_id))];
  const thoughtNodes = [...new Set(thoughts.map((t) => t.node_id))];
  const [noteOn, series, topics, readings, contacts, nodes, practices, failures, actionTitles, budgets, copied] = await Promise.all([
    noteIds.length
      ? rows<{ id: string; title: string; kind: string; due_on: string }>(supabase.from("todo").select("id,title,kind,due_on").in("id", noteIds))
      : [],
    namesOf("meeting_series", "name", meetings.map((m) => m.series_id)),
    rows<{ id: string; title: string; parent_id: string | null }>(supabase.from("exp_topic").select("id,title,parent_id")),
    namesOf("reading", "title", readingNotes.map((n) => n.reading_id)),
    namesOf("contact", "name", interactions.map((i) => i.contact_id)),
    namesOf("pw_node", "title", thoughts.map((t) => t.node_id)),
    namesOf("practice", "title", sessions.map((s) => s.practice_id)),
    namesOf("failure", "hypothesis", failureNotes.map((n) => n.failure_id)),
    actionIds.length
      ? rows<{ id: string; title: string; project_id: string | null; milestone_id: string | null }>(
        supabase.from("todo").select("id,title,project_id,milestone_id").in("id", [...new Set(actionIds)]))
      : [],
    expenses.length
      ? rows<{ id: string; name: string; currency: string }>(
        supabase.from("budget").select("id,name,currency").in("id", [...new Set(expenses.map((e) => e.budget_id))]))
      : [],
    // old ambitions copied into Experiments (0081): their thoughts are notes there now, shown with the notes
    thoughtNodes.length
      ? rows<{ id: string }>(supabase.from("pw_node").select("id").in("id", thoughtNodes).not("ambition_topic_id", "is", null))
      : [],
  ]);
  const gone = new Set(copied.map((x) => x.id));

  const onTodo = (n: { todo_id: string }) => noteOn.find((t) => t.id === n.todo_id);
  const cat = (id: string | null) => (id ? tax?.allCategories.find((c) => c.id === id)?.label ?? "" : "");
  const proj = (id: string | null) => (id ? projects.find((p) => p.id === id)?.name ?? "" : "");
  const topicPath = (id: string) => {
    const t = topics.find((x) => x.id === id);
    const p = t?.parent_id ? topics.find((x) => x.id === t.parent_id) : null;
    return p ? `${p.title} › ${t!.title}` : t?.title ?? "";
  };
  const logbook = (a: { project_id: string | null; milestone_id: string | null } | undefined) =>
    a?.project_id ? `#/logbook?p=${a.project_id}${a.milestone_id ? `&m=${a.milestone_id}` : ""}` : "#/logbook";
  const sections: DaySection[] = [];
  const add = (s: DaySection) => { if (s.items.length) sections.push(s); };

  // ---- time ---------------------------------------------------------------------------
  const minutes = entries.reduce((a, e) => a + (Number(e.minutes) || 0), 0);
  add({
    key: "time", title: "Time", total: minutes ? hours(minutes) : undefined,
    items: entries.map((e) => ({
      key: e.id,
      when: e.ended_at ? span(clock(e.started_at), clock(e.ended_at)) : hours(e.minutes),
      text: e.description?.trim() || cat(e.category_id) || "Time",
      meta: join(e.description?.trim() ? cat(e.category_id) : "", proj(e.project_id), e.ended_at ? hours(e.minutes) : ""),
      href: `${week}&entry=${e.id}`,
    })),
  });

  // ---- the calendar, and the to-dos ---------------------------------------------------------
  const byId = new Map(plan.todos.map((t) => [t.id, t]));
  const sittings = plan.slots.filter((s) => s.planned_on === day && !s.is_cancelled)
    .sort((a, b) => (a.start_time ?? "99").localeCompare(b.start_time ?? "99"));
  add({
    key: "calendar", title: "Calendar",
    items: sittings.flatMap((s) => {
      const t = byId.get(s.todo_id);
      if (!t || t.kind !== "meeting" || t.is_cancelled) return [];
      return [{
        key: s.id, when: span(hm(s.start_time), hm(s.end_time)), text: t.title,
        meta: join(t.source === "outlook" ? "Outlook" : "", t.is_tentative ? "tentative" : "", proj(t.project_id)),
        href: `${week}&todo=${t.id}`,
      }];
    }),
  });
  const todoItems: DayItem[] = [];
  const seen = new Set<string>();
  for (const s of sittings) {
    const t = byId.get(s.todo_id);
    if (!t || t.kind !== "task" || t.is_cancelled || seen.has(t.id)) continue;
    seen.add(t.id);
    todoItems.push({
      key: t.id, when: span(hm(s.start_time), hm(s.end_time)), text: t.title, done: t.is_done,
      meta: join(proj(t.project_id), cat(t.category_id)), href: `${week}&todo=${t.id}`,
    });
  }
  for (const t of doneTodos) {
    if (seen.has(t.id) || t.kind === "idea") continue;
    seen.add(t.id);
    todoItems.push({
      key: t.id, text: t.title, done: true, meta: join(t.kind === "meeting" ? "meeting" : "", proj(t.project_id), "ticked off this day"),
      href: `${week}&todo=${t.id}`,
    });
  }
  add({ key: "todos", title: "To-dos", items: todoItems });
  add({
    key: "small", title: "Small tasks",
    items: tidies.filter((t) => !t.skipped).map((t) => ({
      key: t.id, text: t.title, done: t.is_done, meta: join(t.is_tidy ? "tidy-up" : "", t.repeat_id ? "↻ repeats" : ""),
      href: `${week}&tidy=${t.id}`,
    })),
  });

  add({
    key: "comments", title: "Comments on to-dos",
    items: ideaNotes.filter((n) => onTodo(n) && onTodo(n)!.kind !== "idea").map((n) => {
      const t = onTodo(n)!;
      // opened in the week it is filed under, where its window has the comments
      return { key: n.id, text: n.body, meta: `on ${t.title}`, href: `#/week?w=${weekStart(t.due_on)}&d=${t.due_on}&todo=${t.id}` };
    }),
  });

  // ---- meetings -----------------------------------------------------------------------
  add({
    key: "meetings", title: "Meetings",
    items: meetings.map((m) => ({
      key: m.id, text: m.title?.trim() || series.get(m.series_id) || "Meeting",
      meta: join(m.title?.trim() ? series.get(m.series_id) : "", m.people),
      more: clip((m.sections ?? []).filter((x) => x.body?.trim()).map((x) => `${x.heading}: ${x.body.trim()}`).join("\n")),
      href: `#/meetings?m=${m.id}`,
    })),
  });

  // ---- notes ----------------------------------------------------------------------------
  add({
    key: "experiments", title: "Experiments",
    items: expNotes.map((n) => ({ key: n.id, text: n.body, meta: join(topicPath(n.topic_id), (n.tags ?? []).join(", ")), href: `#/experiments?n=${n.id}` })),
  });
  add({
    key: "reading", title: "Reading",
    items: readingNotes.map((n) => ({
      key: n.id, text: n.quote?.trim() ? `“${n.quote.trim()}”` : n.body ?? "", more: n.quote?.trim() ? clip(n.body) : null,
      meta: join(readings.get(n.reading_id), n.page ? `p. ${n.page}` : ""), href: `#/reading?r=${n.reading_id}&n=${n.id}`,
    })),
  });
  add({
    key: "ideas", title: "Ideas",
    items: [
      ...newIdeas.map((t) => ({ key: t.id, text: t.title, more: clip(t.note), meta: "jotted down", href: `${week}&idea=${t.id}` })),
      ...ideaNotes.filter((n) => onTodo(n)?.kind === "idea").map((n) => ({
        key: n.id, text: n.body, meta: `on ${onTodo(n)!.title}`, href: `${week}&idea=${n.todo_id}&note=${n.id}`,
      })),
    ],
  });
  add({
    key: "people", title: "People",
    items: interactions.map((i) => ({ key: i.id, text: i.body, meta: contacts.get(i.contact_id), href: `#/network?c=${i.contact_id}&i=${i.id}` })),
  });
  add({
    key: "pathways", title: "Pathways thoughts",
    items: thoughts.filter((t) => !gone.has(t.node_id)).map((t) => ({ key: t.id, text: t.body, meta: join(nodes.get(t.node_id), t.valid ? "" : "no longer valid"), href: `#/pathways?g=${t.node_id}` })),
  });
  add({
    key: "practice", title: "Practice",
    items: sessions.map((s) => ({
      key: s.id, text: s.did?.trim() || `${SKILLS.find((k) => k.key === s.skill)?.label ?? s.skill} practice`,
      more: clip(join(s.went_well ? `Went well: ${s.went_well}` : "", s.to_fix ? `To fix: ${s.to_fix}` : "")),
      meta: join(practices.get(s.practice_id), SKILLS.find((k) => k.key === s.skill)?.label, s.minutes ? `${s.minutes} min` : ""),
      href: `#/practice?s=${s.id}`,
    })),
  });
  add({
    key: "failures", title: "Hypotheses",
    items: failureNotes.map((n) => ({ key: n.id, text: n.body, meta: join(failures.get(n.failure_id), n.kind), href: `#/failures?f=${n.failure_id}` })),
  });

  // ---- the Logbook ----------------------------------------------------------------------
  const action = new Map(actionTitles.map((a) => [a.id, a]));
  const logged = actionTime.reduce((a, t) => a + Number(t.hours || 0), 0);
  add({
    key: "logbook", title: "Logbook", total: logged ? `${Math.round(logged * 100) / 100} h on actions` : undefined,
    items: [
      ...actionsNew.map((a) => ({ key: `n${a.id}`, text: a.title, meta: join("new action", proj(a.project_id)), done: a.is_done, href: logbook(a) })),
      ...actionsDone.filter((a) => !actionsNew.some((x) => x.id === a.id))
        .map((a) => ({ key: `d${a.id}`, text: a.title, meta: join("done", proj(a.project_id)), done: true, href: logbook(a) })),
      ...comments.map((c) => ({
        key: c.id, text: c.body?.trim() || (c.links ?? []).join(" ") || "A link", meta: `on ${action.get(c.action_id)?.title ?? "an action"}`,
        href: logbook(action.get(c.action_id)),
      })),
      ...actionTime.map((t) => ({
        key: t.id, when: t.start_time ? span(hm(t.start_time), hm(t.end_time)) : `${Number(t.hours)} h`,
        text: action.get(t.action_id)?.title ?? "An action", meta: join("time on it", t.start_time ? `${Number(t.hours)} h` : ""),
        href: logbook(action.get(t.action_id)),
      })),
    ],
  });

  // ---- money, and the CV ------------------------------------------------------------------
  add({
    key: "expenses", title: "Expenses",
    items: expenses.map((e) => {
      const b = budgets.find((x) => x.id === e.budget_id);
      return {
        key: e.id, when: money(Number(e.amount), b?.currency), text: e.item?.trim() || "Expense", more: clip(e.detail),
        meta: b?.name, href: `#/budget?e=${e.id}`,
      };
    }),
  });
  add({
    key: "cv", title: "CV",
    items: cv.map((c) => ({ key: c.id, text: c.title, meta: join(c.cv_section, c.organisation), more: clip(c.description, 200), href: `#/cv?e=${c.id}` })),
  });

  return { diary: diary?.[0] ?? null, diaryMissing: diary === null, sections };
}

export const diaryLines = (d: DiaryDay) => [
  ...(d.best ? [{ label: "Best", text: d.best, why: d.best_why, area: areaLabel(d.best_area), star: d.best_star }] : []),
  ...(d.worst ? [{ label: "Worst", text: d.worst, why: null, area: areaLabel(d.worst_area), star: d.worst_star }] : []),
];
