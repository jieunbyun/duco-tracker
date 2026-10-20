// The group: members (students, collaborators) who sign in to the same app and
// see only their projects and logbook (0015_group.sql, 0016_members.sql). The
// supervisor reads every logbook and comments, and keeps a logbook of their
// own; only an entry's author writes it, and every edit keeps the version
// before it.
import { supabase } from "./supabase";
import { check } from "./data";

export type Role = "supervisor" | "member";
export type Member = {
  user_id: string; role: Role; display_name: string; email: string | null; active: boolean; joined_on: string;
  planning_project_id: string | null; // their project under Research › Supervision in your Planning, which names them
};
export type GroupProject = {
  id: string; title: string; aim: string | null; status: "active" | "paused" | "done";
  start_on: string | null; end_on: string | null; lead_id: string | null; members: string[]; // user ids
};
export type GroupMilestone = { id: string; project_id: string; title: string; due_on: string | null; done: boolean; done_on: string | null; sort_order: number };
export type EntryKind = "entry" | "weekly";
export type Entry = {
  id: string; author_id: string; project_id: string | null; entry_date: string; kind: EntryKind;
  did: string | null; results: string | null; next: string | null; links: string[];
  created_at: string; updated_at: string;
};
export type EntryFields = Pick<Entry, "project_id" | "entry_date" | "kind" | "did" | "results" | "next" | "links">;
export type Revision = { id: string; entry_id: string; changed_at: string; old_row: Entry };
export type Comment = { id: string; entry_id: string; author_id: string; body: string; created_at: string };

/** The three parts of an entry, named for its kind. */
export const FIELDS: Record<EntryKind, { did: string; results: string; next: string }> = {
  entry: { did: "What I did", results: "Results", next: "Next" },
  weekly: { did: "Done this week", results: "Blocked on", next: "Next" },
};

/**
 * The signed-in person's place in the group: their role, or "none" when the
 * group exists but they have not been added yet, or null before 0015 is run
 * (then the app is simply the owner's planner, as before).
 */
export async function myRole(): Promise<Role | "none" | null> {
  const { data: u } = await supabase.auth.getUser();
  if (!u.user) return null;
  const { data, error } = await supabase.from("group_member").select("role,active").eq("user_id", u.user.id).maybeSingle();
  if (error) return null; // no group table yet
  if (!data || !data.active) {
    // the owner of the planner, if the group is not set up for them, keeps the planner
    const { count } = await supabase.from("area").select("id", { count: "exact", head: true });
    return count ? null : "none";
  }
  return (data.role === "supervisor" ? "supervisor" : "member") as Role; // (student, collaborator: before 0016)
}
export async function myId(): Promise<string> {
  const { data } = await supabase.auth.getUser();
  return data.user?.id ?? "";
}

// ---- members ---------------------------------------------------------------------
export async function loadMembers(): Promise<Member[]> {
  return (await check<Member[]>(
    supabase.from("group_member").select("user_id,role,display_name,email,active,joined_on,planning_project_id").order("display_name"),
  )) ?? [];
}
/** Add someone already invited in Supabase, by email; named after their Planning Supervision project when there is one. */
export async function addMember(email: string, name: string, planningProjectId: string | null): Promise<void> {
  await check(supabase.rpc("add_group_member", { p_email: email, p_name: name, p_planning_project: planningProjectId }));
}
export async function saveMember(userId: string, fields: Partial<Pick<Member, "display_name" | "active">>): Promise<void> {
  await check(supabase.from("group_member").update(fields).eq("user_id", userId));
}

// ---- projects and milestones -------------------------------------------------------
export async function loadGroupProjects(): Promise<GroupProject[]> {
  const rows = (await check<(Omit<GroupProject, "members"> & { group_project_member: { user_id: string }[] })[]>(
    supabase.from("group_project").select("id,title,aim,status,start_on,end_on,lead_id,group_project_member(user_id)").order("created_at"),
  )) ?? [];
  return rows.map(({ group_project_member, ...p }) => ({ ...p, members: group_project_member.map((m) => m.user_id) }));
}
export async function saveGroupProject(id: string | null, fields: Partial<Omit<GroupProject, "id" | "members">>): Promise<string> {
  if (id) {
    await check(supabase.from("group_project").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("group_project").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteGroupProject(id: string): Promise<void> {
  await check(supabase.from("group_project").delete().eq("id", id));
}
export async function addProjectMember(projectId: string, userId: string): Promise<void> {
  await check(supabase.from("group_project_member").upsert({ project_id: projectId, user_id: userId }, { ignoreDuplicates: true }));
}
export async function removeProjectMember(projectId: string, userId: string): Promise<void> {
  await check(supabase.from("group_project_member").delete().eq("project_id", projectId).eq("user_id", userId));
}

export async function loadMilestones(): Promise<GroupMilestone[]> {
  return (await check<GroupMilestone[]>(
    supabase.from("group_milestone").select("id,project_id,title,due_on,done,done_on,sort_order").order("sort_order").order("due_on"),
  )) ?? [];
}
export async function saveMilestone(id: string | null, fields: Partial<Omit<GroupMilestone, "id">>): Promise<void> {
  await check(id ? supabase.from("group_milestone").update(fields).eq("id", id) : supabase.from("group_milestone").insert(fields));
}
export async function deleteMilestone(id: string): Promise<void> {
  await check(supabase.from("group_milestone").delete().eq("id", id));
}

// ---- the logbook ---------------------------------------------------------------------
const ENTRY_COLS = "id,author_id,project_id,entry_date,kind,did,results,next,links,created_at,updated_at";
/** Entries you can see: your own (a member), or everyone's (the supervisor); newest first. */
export async function loadEntries(authorId?: string): Promise<Entry[]> {
  let q = supabase.from("logbook_entry").select(ENTRY_COLS);
  if (authorId) q = q.eq("author_id", authorId);
  return (await check<Entry[]>(q.order("entry_date", { ascending: false }).order("created_at", { ascending: false }))) ?? [];
}
export async function saveEntry(id: string | null, fields: EntryFields): Promise<void> {
  await check(id ? supabase.from("logbook_entry").update(fields).eq("id", id) : supabase.from("logbook_entry").insert(fields));
}
export async function deleteEntry(id: string): Promise<void> {
  await check(supabase.from("logbook_entry").delete().eq("id", id));
}
/** Whether an entry can still be deleted (on the day it was written). */
export const deletable = (e: Entry) => Date.now() - new Date(e.created_at).getTime() < 86_400_000;

export async function loadRevisions(entryId: string): Promise<Revision[]> {
  return (await check<Revision[]>(
    supabase.from("logbook_revision").select("id,entry_id,changed_at,old_row").eq("entry_id", entryId).order("changed_at", { ascending: false }),
  )) ?? [];
}
/** How many times each entry has been edited. */
export async function revisionCounts(entryIds: string[]): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  if (!entryIds.length) return out;
  const rows = (await check<{ entry_id: string }[]>(supabase.from("logbook_revision").select("entry_id").in("entry_id", entryIds))) ?? [];
  for (const r of rows) out.set(r.entry_id, (out.get(r.entry_id) ?? 0) + 1);
  return out;
}

export async function loadComments(entryIds: string[]): Promise<Comment[]> {
  if (!entryIds.length) return [];
  return (await check<Comment[]>(
    supabase.from("logbook_comment").select("id,entry_id,author_id,body,created_at").in("entry_id", entryIds).order("created_at"),
  )) ?? [];
}
export async function addComment(entryId: string, body: string): Promise<void> {
  await check(supabase.from("logbook_comment").insert({ entry_id: entryId, body }));
}
export async function deleteComment(id: string): Promise<void> {
  await check(supabase.from("logbook_comment").delete().eq("id", id));
}

/** "link one, link two" or one per line → the addresses, without repeats. */
export function parseLinks(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map((s) => s.trim()).filter((s) => /^https?:\/\//i.test(s)))];
}
/** A short name for a link: the file or folder it points at, else its site. */
export function linkName(url: string): string {
  try {
    const u = new URL(url);
    const last = decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() ?? "");
    const file = u.searchParams.get("file") ?? (last.includes(".") ? last : "");
    return file || u.hostname.replace(/^www\./, "");
  } catch {
    return "link";
  }
}

// ---- export --------------------------------------------------------------------------
/** A logbook as Markdown, oldest first, with comments: to keep on OneDrive, or take along. */
export function logbookMarkdown(entries: Entry[], projects: GroupProject[], members: Member[], comments: Comment[],
                                edits: Map<string, number>, title: string): string {
  const name = (id: string) => members.find((m) => m.user_id === id)?.display_name ?? "?";
  const proj = (id: string | null) => (id ? projects.find((p) => p.id === id)?.title ?? "(project removed)" : "No project");
  const out = [`# ${title}`, "", `Exported ${new Date().toISOString().slice(0, 10)}.`, ""];
  for (const e of [...entries].sort((a, b) => a.entry_date.localeCompare(b.entry_date) || a.created_at.localeCompare(b.created_at))) {
    const f = FIELDS[e.kind];
    out.push(`## ${e.entry_date} · ${proj(e.project_id)}${e.kind === "weekly" ? " · weekly update" : ""}`, "");
    out.push(`*${name(e.author_id)}*${edits.get(e.id) ? ` · edited ${edits.get(e.id)}× (last ${e.updated_at.slice(0, 10)})` : ""}`, "");
    for (const k of ["did", "results", "next"] as const) if (e[k]) out.push(`**${f[k]}**`, "", e[k]!, "");
    if (e.links.length) out.push("**Links**", "", ...e.links.map((l) => `- ${l}`), "");
    const cs = comments.filter((c) => c.entry_id === e.id);
    if (cs.length) out.push("**Comments**", "", ...cs.map((c) => `- ${name(c.author_id)}, ${c.created_at.slice(0, 10)}: ${c.body.replace(/\n/g, " ")}`), "");
  }
  return out.join("\n");
}
export function download(filename: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
