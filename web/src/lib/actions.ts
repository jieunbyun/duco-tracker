// The Logbook is built on actions (0023, 0025, 0026): a project's own notes on
// what to do next, each with a dated thread of comments and links. They are
// kept in the to-do table with a kind of their own, "action", so they never
// appear on Week's lists; Week's time log can still work on them.
import { supabase } from "./supabase";
import { check } from "./data";
import { today } from "./dates";

export type Action = {
  id: string;
  title: string;
  links: string[]; // links on the action itself
  project_id: string | null; // a Planning project
  milestone_id: string | null; // and one of its milestones
  group_project_id: string | null; // or a shared project
  group_milestone_id: string | null; // and one of its milestones
  is_done: boolean;
  done_at: string | null;
  created_at: string;
  sort_order: number; // your order, by dragging
};
export type ActionFields = Pick<Action, "title" | "links" | "project_id" | "milestone_id" | "group_project_id" | "group_milestone_id">;
export type ActionComment = { id: string; action_id: string; author_id: string; body: string | null; links: string[]; created_at: string; edited_at?: string | null };

const COLS = "id,title,links,project_id,milestone_id,group_project_id,group_milestone_id,is_done,done_at,created_at,sort_order";
const RECENT_DAYS = 14;
const asAction = (a: Action) => ({ ...a, links: a.links ?? [], sort_order: a.sort_order ?? 100 });
/** Your order first (dragging sets it), then oldest first. */
export const byOrder = (a: Action, b: Action) => a.sort_order - b.sort_order || a.created_at.localeCompare(b.created_at);

/** Your open actions, and those done in the last two weeks. None before 0026 is run. */
export async function loadMyActions(): Promise<Action[]> {
  const since = new Date(Date.now() - RECENT_DAYS * 86_400_000).toISOString();
  const { data, error } = await supabase.from("todo").select(COLS)
    .eq("kind", "action").eq("is_cancelled", false)
    .or(`is_done.eq.false,done_at.gte.${since}`)
    .order("sort_order").order("created_at");
  if (error) return [];
  return ((data ?? []) as Action[]).map(asAction);
}
/** Every action you have ticked off, most recent first: the Logbook's history. */
export async function loadDoneActions(): Promise<Action[]> {
  const { data, error } = await supabase.from("todo").select(COLS)
    .eq("kind", "action").eq("is_done", true).eq("is_cancelled", false)
    .order("done_at", { ascending: false }).limit(1000);
  if (error) return [];
  return ((data ?? []) as Action[]).map(asAction);
}
/** A member's actions on shared projects, open and done (for the supervisor). */
export async function loadMemberActions(userId: string): Promise<Action[]> {
  const { data, error } = await supabase.rpc("member_actions_for", { p: userId });
  if (error) return [];
  return ((data ?? []) as Omit<Action, "project_id" | "milestone_id">[]).map((a) => asAction({
    ...a, project_id: null, milestone_id: null,
  } as Action)).sort(byOrder);
}

export async function addAction(fields: ActionFields, sort_order = 1000): Promise<string> {
  const row = await check<{ id: string }>(
    supabase.from("todo").insert({ ...fields, kind: "action", due_on: today(), must_this_week: false, sort_order })
      .select("id").single());
  return row!.id;
}
export async function saveAction(id: string, fields: Partial<ActionFields>): Promise<void> {
  await check(supabase.from("todo").update(fields).eq("id", id));
}
export async function setActionDone(id: string, done: boolean): Promise<void> {
  await check(supabase.from("todo").update({ is_done: done, done_at: done ? new Date().toISOString() : null }).eq("id", id));
}
/** Delete an action and its thread (Undo brings it back). */
export async function deleteAction(id: string): Promise<void> {
  await check(supabase.from("todo").delete().eq("id", id));
}
/** A new order for some actions (each saved as 10, 20, 30, …; only those that moved). */
export async function saveActionOrder(ids: string[], before: Map<string, number>): Promise<void> {
  for (const [i, id] of ids.entries()) {
    const order = (i + 1) * 10;
    if (before.get(id) !== order) await check(supabase.from("todo").update({ sort_order: order }).eq("id", id));
  }
}

// ---- the threads -------------------------------------------------------------------
export async function loadActionComments(actionIds: string[]): Promise<ActionComment[]> {
  if (!actionIds.length) return [];
  const out: ActionComment[] = [];
  for (let i = 0; i < actionIds.length; i += 200) {
    const { data, error } = await supabase.from("action_comment").select("*")
      .in("action_id", actionIds.slice(i, i + 200)).order("created_at");
    if (error) return [];
    out.push(...((data ?? []) as ActionComment[]).map((c) => ({ ...c, links: c.links ?? [] })));
  }
  return out;
}
/** Recent comments you can see, newest first (yours, and members' on shared projects). */
export async function loadRecentComments(days = 30): Promise<ActionComment[]> {
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const { data, error } = await supabase.from("action_comment").select("*")
    .gte("created_at", since).order("created_at", { ascending: false }).limit(2000);
  if (error) return [];
  return ((data ?? []) as ActionComment[]).map((c) => ({ ...c, links: c.links ?? [] }));
}
export async function addActionComment(actionId: string, body: string, links: string[]): Promise<void> {
  await check(supabase.from("action_comment").insert({ action_id: actionId, body: body.trim() || null, links }));
}
/** Your own comment's text and links, at any time; it then shows as edited. */
export async function editActionComment(id: string, body: string, links: string[]): Promise<void> {
  await check(supabase.from("action_comment").update({ body: body.trim() || null, links }).eq("id", id));
}
/** Possible on the day it was written; after that a comment stays. */
export async function deleteActionComment(id: string): Promise<void> {
  await check(supabase.from("action_comment").delete().eq("id", id));
}
export const commentDeletable = (c: ActionComment) => Date.now() - new Date(c.created_at).getTime() < 86_400_000;

/** Comments on each shared project's actions since a date (for Pathways and Members). */
export async function loadProjectActivity(since: string): Promise<Map<string, number>> {
  const { data, error } = await supabase.rpc("group_project_activity", { since });
  if (error) return new Map();
  return new Map(((data ?? []) as { group_project_id: string; comments: number }[]).map((r) => [r.group_project_id, Number(r.comments)]));
}

// ---- what a time block did to actions (Week's log keeps it in its note) -------------
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

// ---- export ----------------------------------------------------------------------------
/** A logbook of actions as Markdown: by project, each action with its thread. */
export function actionsMarkdown(actions: Action[], comments: ActionComment[], title: string,
                                whereOf: (a: Action) => string, nameOf: (uid: string) => string): string {
  const out = [`# ${title}`, "", `Exported ${today()}.`, ""];
  const groups = new Map<string, Action[]>();
  for (const a of actions) groups.set(whereOf(a), [...(groups.get(whereOf(a)) ?? []), a]);
  for (const [where, list] of [...groups].sort((x, y) => x[0].localeCompare(y[0]))) {
    out.push(`## ${where}`, "");
    for (const a of list) {
      out.push(`### ${a.is_done ? "[x]" : "[ ]"} ${a.title}${a.done_at ? ` (done ${a.done_at.slice(0, 10)})` : ""}`, "");
      for (const l of a.links) out.push(`- ${l}`);
      if (a.links.length) out.push("");
      for (const c of comments.filter((x) => x.action_id === a.id)) {
        out.push(`- ${c.created_at.slice(0, 10)}, ${nameOf(c.author_id)}: ${(c.body ?? "").replace(/\n/g, " ")}${c.links.length ? ` (${c.links.join(", ")})` : ""}`);
      }
      out.push("");
    }
  }
  return out.join("\n");
}
