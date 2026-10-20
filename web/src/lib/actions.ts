// Logbook action items are to-dos (0023_logbook_actions.sql): one list. An
// action item added in the Logbook is a to-do on your Week list too, and
// ticking it in either place ticks both. Only to-dos that belong to a project
// (a Planning one or a shared one) show in the Logbook.
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
    .eq("kind", "task").eq("is_cancelled", false)
    .or("project_id.not.is.null,group_project_id.not.is.null")
    .or(`is_done.eq.false,done_at.gte.${since}`)
    .order("created_at");
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

export async function addAction(fields: ActionFields): Promise<void> {
  // a to-do for this week, flexible: it carries over on Week's list until done
  await check(supabase.from("todo").insert({ ...fields, kind: "task", due_on: today(), must_this_week: false }));
}
export async function saveAction(id: string, fields: Partial<ActionFields>): Promise<void> {
  await check(supabase.from("todo").update(fields).eq("id", id));
}
export async function setActionDone(id: string, done: boolean): Promise<void> {
  await check(supabase.from("todo").update({ is_done: done, done_at: done ? new Date().toISOString() : null }).eq("id", id));
}
