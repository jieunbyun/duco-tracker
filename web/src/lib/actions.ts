// Logbook action items: a project's internal notes on what to do next, with
// comments and links (0023_logbook_actions.sql, 0025_actions_apart.sql). They
// are kept in the to-do table with a kind of their own, "action", so they never
// appear on Week's lists; they are worked on in Logbook sessions and in Week's
// time log.
import { supabase } from "./supabase";
import { check } from "./data";
import { today } from "./dates";

export type Action = {
  id: string;
  title: string;
  note: string | null;
  links: string[];
  project_id: string | null; // a Planning project
  milestone_id: string | null; // and one of its milestones
  group_project_id: string | null; // or a shared project
  is_done: boolean;
  done_at: string | null;
  created_at: string;
};
export type ActionFields = Pick<Action, "title" | "note" | "links" | "project_id" | "milestone_id" | "group_project_id">;

const COLS = "id,title,note,links,project_id,milestone_id,group_project_id,is_done,done_at,created_at";
const RECENT_DAYS = 14;

/** Your open action items, and those done in the last two weeks. None before 0023 is run. */
export async function loadMyActions(): Promise<Action[]> {
  const since = new Date(Date.now() - RECENT_DAYS * 86_400_000).toISOString();
  const { data, error } = await supabase.from("todo").select(COLS)
    .eq("kind", "action").eq("is_cancelled", false)
    .or("project_id.not.is.null,group_project_id.not.is.null")
    .or(`is_done.eq.false,done_at.gte.${since}`)
    .order("created_at");
  if (error) return [];
  return ((data ?? []) as Action[]).map((a) => ({ ...a, links: a.links ?? [] }));
}

/** Every action you have ticked off, most recent first: the Logbook's action history. */
export async function loadDoneActions(): Promise<Action[]> {
  const { data, error } = await supabase.from("todo").select(COLS)
    .eq("kind", "action").eq("is_done", true).eq("is_cancelled", false)
    .order("done_at", { ascending: false }).limit(1000);
  if (error) return [];
  return ((data ?? []) as Action[]).map((a) => ({ ...a, links: a.links ?? [] }));
}

/** A member's action items on shared projects (read-only, for the supervisor). */
export async function loadMemberActions(userId: string): Promise<Action[]> {
  const { data, error } = await supabase.rpc("member_actions_for", { p: userId });
  if (error) return [];
  return ((data ?? []) as Omit<Action, "project_id" | "milestone_id">[]).map((a) => ({
    ...a, project_id: null, milestone_id: null, links: a.links ?? [],
  }));
}

export async function addAction(fields: ActionFields): Promise<string> {
  const row = await check<{ id: string }>(
    supabase.from("todo").insert({ ...fields, kind: "action", due_on: today(), must_this_week: false }).select("id").single());
  return row!.id;
}
export async function saveAction(id: string, fields: Partial<ActionFields>): Promise<void> {
  await check(supabase.from("todo").update(fields).eq("id", id));
}
export async function setActionDone(id: string, done: boolean): Promise<void> {
  await check(supabase.from("todo").update({ is_done: done, done_at: done ? new Date().toISOString() : null }).eq("id", id));
}
/** Delete an action (Undo brings it back). */
export async function deleteAction(id: string): Promise<void> {
  await check(supabase.from("todo").delete().eq("id", id));
}
/** Add a dated comment and/or links to an action: they accumulate over sessions. */
export async function addToAction(a: Action, comment: string, links: string[]): Promise<void> {
  const line = comment.trim() ? `${today()}: ${comment.trim()}` : "";
  await saveAction(a.id, {
    note: [a.note, line].filter(Boolean).join("\n") || null,
    links: [...new Set([...a.links, ...links])],
  });
}

/** What a session did to an action: the entry keeps these, with titles as they were. */
export type ActionStep = { id: string; title: string; what: ("done" | "added" | "updated")[] };
export function noteStep(log: ActionStep[], a: { id: string; title: string }, what: ActionStep["what"][number]): ActionStep[] {
  const has = log.find((s) => s.id === a.id);
  if (!has) return [...log, { id: a.id, title: a.title, what: [what] }];
  return log.map((s) => (s.id === a.id && !s.what.includes(what) ? { ...s, what: [...s.what, what] } : s));
}
/** "Done: A, B · New: C · Updated: D" */
export function stepSummary(log: ActionStep[]): string {
  const of = (w: ActionStep["what"][number]) => log.filter((s) => s.what.includes(w)).map((s) => s.title);
  return [["Done", of("done")], ["New", of("added")], ["Updated", of("updated").filter((t) => !of("added").includes(t))]]
    .filter(([, xs]) => xs.length).map(([k, xs]) => `${k}: ${(xs as string[]).join(", ")}`).join(" · ");
}
