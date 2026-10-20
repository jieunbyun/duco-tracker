// Pathways: goals, objectives, projects (existing or potential), people and
// knowledge gaps, laid out in lanes over time and linked across lanes.
import { supabase } from "./supabase";
import { check } from "./data";

export const LANES = [
  { key: "goals", label: "Goals & Objectives" },
  { key: "awards", label: "Awards" },
  { key: "publications", label: "Publications & code/database" },
  { key: "teaching", label: "Teaching" },
  { key: "outreach", label: "Outreach" },
  { key: "grants", label: "Grant Writing" },
] as const;
export type Lane = (typeof LANES)[number]["key"];

export const NODE_KINDS = [
  { key: "goal", label: "Goal", lane: "goals" },
  { key: "objective", label: "Objective", lane: "goals" },
  { key: "project", label: "Project", lane: "publications" },
  { key: "person", label: "Person", lane: "publications" },
  { key: "gap", label: "Knowledge gap", lane: "goals" },
  { key: "award", label: "Award", lane: "awards" },
  { key: "grant", label: "Grant", lane: "grants" },
] as const;
/** Grants and awards go through stages: drafting, submitted, awarded or declined. */
export const staged = (kind: string) => kind === "grant" || kind === "award";
export type NodeKind = (typeof NODE_KINDS)[number]["key"];

// Where a grant application stands. Until it is awarded, what it would fund is uncertain.
export const GRANT_STAGES = ["drafting", "submitted", "awarded", "declined"] as const;
export type GrantStage = (typeof GRANT_STAGES)[number];

export type PwNode = {
  id: string;
  kind: NodeKind;
  lane: Lane;
  title: string;
  detail: string | null;
  status: "active" | "done" | "retired";
  potential: boolean;
  project_id: string | null;
  reading_id: string | null;
  start_on: string | null;
  end_on: string | null;
  effort_pm: number | null;
  cost: number | null;
  fte: number | null;
  lane_row: number;
  grant_stage: GrantStage | null;
  hands_on: boolean; // a project your own research time goes into substantially
  group_project_id: string | null; // a student's shared project it stands for (Supervision)
};
export type PwNodeFields = Omit<PwNode, "id">;
// A link is one kind of arrow, from one item to another; its direction says it all.
// (pw_link.kind is still in the table, left at its default.)
export type PwLink = { id: string; from_id: string; to_id: string };
export type PwRevision = { id: string; changed_at: string; old_title: string; old_detail: string | null; reason: string | null };

const NODE_COLS = "id,kind,lane,title,detail,status,potential,project_id,reading_id,start_on,end_on,effort_pm,cost,fte,lane_row,grant_stage,hands_on,group_project_id";
const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

export async function loadPathways(): Promise<{ nodes: PwNode[]; links: PwLink[]; years: number }> {
  const [n, l, s] = await Promise.all([
    supabase.from("pw_node").select(NODE_COLS).order("created_at"),
    supabase.from("pw_link").select("id,from_id,to_id"),
    supabase.from("user_setting").select("pathway_years").maybeSingle(),
  ]);
  for (const r of [n, l, s]) if (r.error) throw new Error(r.error.message);
  return {
    nodes: ((n.data ?? []) as PwNode[]).map((x) => ({ ...x, effort_pm: num(x.effort_pm), cost: num(x.cost), fte: num(x.fte) })),
    links: (l.data ?? []) as PwLink[],
    years: Number(s.data?.pathway_years ?? 5),
  };
}

// ---- contributors, and what a member sees ------------------------------------------
/** Who contributes to each item (none before 0017, or without a group). */
export async function loadContributors(): Promise<Map<string, string[]>> {
  const out = new Map<string, string[]>();
  const { data, error } = await supabase.from("pw_contributor").select("node_id,user_id");
  if (error) return out;
  for (const r of data as { node_id: string; user_id: string }[]) out.set(r.node_id, [...(out.get(r.node_id) ?? []), r.user_id]);
  return out;
}
export async function setContributors(nodeId: string, want: string[], had: string[]): Promise<void> {
  const add = want.filter((u) => !had.includes(u));
  const drop = had.filter((u) => !want.includes(u));
  if (add.length) await check(supabase.from("pw_contributor").insert(add.map((user_id) => ({ node_id: nodeId, user_id }))));
  if (drop.length) await check(supabase.from("pw_contributor").delete().eq("node_id", nodeId).in("user_id", drop));
}
/** A member's chart: the items they contribute to and the goals those lead to — titles, dates and stages only. */
export async function loadMemberMap(): Promise<{ nodes: PwNode[]; links: PwLink[] }> {
  const [n, l] = await Promise.all([supabase.rpc("member_map"), supabase.rpc("member_map_links")]);
  for (const r of [n, l]) if (r.error) throw new Error(r.error.message);
  const nodes = ((n.data ?? []) as Pick<PwNode, "id" | "kind" | "lane" | "title" | "start_on" | "end_on" | "status" | "grant_stage" | "lane_row">[])
    .map((x) => ({
      ...x, detail: null, potential: false, project_id: null, reading_id: null, effort_pm: null, cost: null, fte: null,
      hands_on: false, group_project_id: null,
    }) as PwNode);
  return { nodes, links: (l.data ?? []) as PwLink[] };
}

export async function saveYears(years: number): Promise<void> {
  await check(supabase.from("user_setting").update({ pathway_years: years }).not("user_id", "is", null));
}

export async function saveNode(id: string | null, fields: Partial<PwNodeFields>): Promise<string> {
  if (id) {
    await check(supabase.from("pw_node").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("pw_node").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteNode(id: string): Promise<void> {
  await check(supabase.from("pw_node").delete().eq("id", id));
}

/** Link two items (one link per pair; linking them again changes nothing). */
export async function saveLink(from_id: string, to_id: string): Promise<void> {
  await check(supabase.from("pw_link").upsert({ from_id, to_id }, { onConflict: "from_id,to_id", ignoreDuplicates: true }));
}
export async function deleteLink(id: string): Promise<void> {
  await check(supabase.from("pw_link").delete().eq("id", id));
}

export async function loadRevisions(nodeId: string): Promise<PwRevision[]> {
  return (await check<PwRevision[]>(
    supabase.from("pw_revision").select("id,changed_at,old_title,old_detail,reason")
      .eq("node_id", nodeId).order("changed_at", { ascending: false }),
  )) ?? [];
}
export async function addRevision(nodeId: string, oldTitle: string, oldDetail: string | null, reason: string | null): Promise<void> {
  await check(supabase.from("pw_revision").insert({ node_id: nodeId, old_title: oldTitle, old_detail: oldDetail, reason }));
}


// ---- the timeline ----------------------------------------------------------------
// Dates are "YYYY-MM-DD"; the map starts at the first of this month and runs
// `years` ahead. Positions are fractions of that span (0 = start, 1 = end).
export function monthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}
export function addMonths(iso: string, months: number): string {
  const [y, m] = iso.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + months, 1));
  return d.toISOString().slice(0, 10);
}
const dayNo = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86_400_000;

export function fraction(iso: string, from: string, to: string): number {
  return (dayNo(iso) - dayNo(from)) / (dayNo(to) - dayNo(from));
}
/** The month (its first day) nearest a fraction of the span. */
export function monthAt(f: number, from: string, to: string): string {
  const day = dayNo(from) + f * (dayNo(to) - dayNo(from));
  const d = new Date(day * 86_400_000);
  const first = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  const next = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  const pick = d.getTime() - first < next - d.getTime() ? first : next;
  return new Date(pick).toISOString().slice(0, 10);
}
// Pathways works in months: an item runs from the first of its first month to
// the last day of its last month. (A linked Planning project keeps its exact
// days; only months are shown.)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-10-15" → "Oct 2026" */
export function fmtMonth(iso: string): string {
  return `${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
}
/** The last day of a date's month. */
export function monthEnd(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}
/**
 * A month picked as "YYYY-MM" back to a date: the first of the month for a
 * start, the last day for an end. A date already in that month is kept as it is.
 */
export function fromMonth(ym: string, end: boolean, was: string | null = null): string | null {
  if (!ym) return null;
  if (was && was.slice(0, 7) === ym) return was;
  return end ? monthEnd(`${ym}-01`) : `${ym}-01`;
}

/** A date moved by whole months, keeping its day (clamped to the month's length). */
export function shiftMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const last = new Date(Date.UTC(y, m - 1 + months + 1, 0)).getUTCDate();
  return new Date(Date.UTC(y, m - 1 + months, Math.min(d, last))).toISOString().slice(0, 10);
}

/** Months between two dates (whole months, by their firsts). */
export function monthsBetween(a: string, b: string): number {
  return (+b.slice(0, 4) - +a.slice(0, 4)) * 12 + (+b.slice(5, 7) - +a.slice(5, 7));
}
