// Failures (0052_failures.sql): hypotheses under your themes, each on a project or
// milestone if you like, and the ways between them and Planning or Members.
// A Planning project that stands for a shared project counts as the same project,
// and so do their milestones: what is on one shows on the other.
import { supabase } from "./supabase";
import { check } from "./data";
import type { Project, Milestone } from "./data";
import type { GroupProject, GroupMilestone, Member } from "./group";

export type Theme = { id: string; name: string; created_at: string };
export type Attachment = {
  project_id: string | null; milestone_id: string | null;
  group_project_id: string | null; group_milestone_id: string | null;
};
export type Failure = Attachment & {
  id: string; theme_id: string; hypothesis: string; test: string | null; lesson: string | null;
  created_on: string; due_on: string | null; created_at: string;
};
export type FailureFields = Omit<Failure, "id" | "created_at">;
export type Board = { themes: Theme[]; items: Failure[]; error?: string };

export const NOWHERE: Attachment = { project_id: null, milestone_id: null, group_project_id: null, group_milestone_id: null };
const PAGE = 1000; // PostgREST's default row cap per request

/** Everything in Failures; null until 0052 is run. */
export async function loadBoard(): Promise<Board | null> {
  const t = await supabase.from("failure_theme").select("*").order("created_at");
  if (t.error) {
    if (t.error.code === "PGRST205" || t.error.code === "42P01") return null; // no such table yet
    throw new Error(t.error.message);
  }
  const items: Failure[] = [];
  for (let from = 0; ; from += PAGE) {
    const f = await supabase.from("failure").select("*")
      .order("created_on", { ascending: false }).order("created_at", { ascending: false }).order("id")
      .range(from, from + PAGE - 1);
    if (f.error) throw new Error(f.error.message);
    items.push(...(f.data as Failure[]));
    if (f.data.length < PAGE) return { themes: t.data as Theme[], items };
  }
}
/** The same for Planning and Members, which must still open if it cannot be read. */
export function loadBoardBeside(): Promise<Board | null> {
  return loadBoard().catch((e) => ({ themes: [], items: [], error: (e as Error).message }));
}
export async function saveTheme(id: string | null, name: string): Promise<string> {
  if (id) {
    await check(supabase.from("failure_theme").update({ name }).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("failure_theme").insert({ name }).select("id").single());
  return row!.id;
}
export async function deleteTheme(id: string): Promise<void> {
  await check(supabase.from("failure_theme").delete().eq("id", id));
}
export async function saveFailure(id: string | null, fields: FailureFields): Promise<string> {
  if (id) {
    await check(supabase.from("failure").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("failure").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteFailure(id: string): Promise<void> {
  await check(supabase.from("failure").delete().eq("id", id));
}

// ---- what is on what -----------------------------------------------------------------

/** On a project or any of its milestones: the Planning one, the shared one, or both as one. */
export function onProject(f: Attachment, planning: Project | undefined, sharedId: string | null | undefined): boolean {
  return (!!sharedId && f.group_project_id === sharedId)
    || (!!planning && (f.project_id === planning.id || planning.milestone.some((m) => m.id === f.milestone_id)));
}
/** On a milestone: likewise. */
export function onMilestone(f: Attachment, planning: Milestone | undefined, sharedId: string | null | undefined): boolean {
  return (!!sharedId && f.group_milestone_id === sharedId) || (!!planning && f.milestone_id === planning.id);
}

export type World = { planning: Project[]; shared: GroupProject[]; sharedMilestones: GroupMilestone[] };
export type Place = { project?: Project; milestone?: Milestone; group?: GroupProject; groupMilestone?: GroupMilestone };

/** Where a hypothesis is, on both sides where they are linked. */
export function placeOf(f: Attachment, w: World): Place {
  if (f.group_project_id || f.group_milestone_id) {
    const groupMilestone = w.sharedMilestones.find((m) => m.id === f.group_milestone_id);
    const gid = groupMilestone?.project_id ?? f.group_project_id;
    const group = w.shared.find((p) => p.id === gid);
    const project = group && w.planning.find((p) => p.group_project_id === group.id);
    const milestone = groupMilestone && project?.milestone.find((m) => m.group_milestone_id === groupMilestone.id);
    return { project, milestone, group, groupMilestone };
  }
  const milestone = w.planning.flatMap((p) => p.milestone).find((m) => m.id === f.milestone_id);
  const pid = milestone?.project_id ?? f.project_id;
  const project = w.planning.find((p) => p.id === pid);
  const group = w.shared.find((p) => p.id === project?.group_project_id);
  const groupMilestone = w.sharedMilestones.find((m) => m.id === milestone?.group_milestone_id);
  return { project, milestone, group, groupMilestone };
}

// ---- going back and forth ------------------------------------------------------------

function hashOf(tab: string, params: Record<string, string | null | undefined>): string {
  const q = new URLSearchParams(Object.entries(params).filter((e): e is [string, string] => !!e[1])).toString();
  return `#/${tab}${q ? `?${q}` : ""}`;
}
export const planningHash = (project: string, milestone?: string | null, failure?: string) =>
  hashOf("planning", { p: project, m: milestone, f: failure });
export const membersHash = (member: string, project: string, milestone?: string | null, failure?: string) =>
  hashOf("supervision", { u: member, p: project, m: milestone, f: failure });
export const failuresHash = (failure: string | null, back?: string | null) => hashOf("failures", { f: failure, back });

/** From a project or milestone to one of its hypotheses, or to a new one on it; `here` is the way back. */
export function toFailures(here: string, to: string | Attachment) {
  const params = typeof to === "string"
    ? { f: to }
    : { new: "1", p: to.project_id, m: to.milestone_id, g: to.group_project_id, gm: to.group_milestone_id };
  history.replaceState(null, "", here); // so the browser's Back lands here too
  location.hash = hashOf("failures", { ...params, back: here });
}
/** Only ever back to those two tabs: the address bar must not be able to put another address in a link. */
export const safeBack = (v: string | null) => (v && /^#\/(planning|supervision)(\?[\w=&%.-]*)?$/.test(v) ? v : null);

/** Whose projects to show a shared one under in Members: yours if you are on it. */
export function memberFor(p: GroupProject, me: string, members: Member[]): string | null {
  const on = (id: string) => p.members.includes(id) || p.lead_id === id;
  return on(me) ? me : (members.find((m) => on(m.user_id))?.user_id ?? null);
}
