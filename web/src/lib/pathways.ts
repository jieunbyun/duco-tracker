// Pathways: goals, objectives, projects (existing or potential), people and
// knowledge gaps, laid out in lanes over time and linked across lanes.
import { supabase } from "./supabase";
import { check } from "./data";

export const LANES = [
  { key: "research", label: "Research" },
  { key: "teaching", label: "Teaching" },
  { key: "outreach", label: "Outreach" },
  { key: "supervision", label: "Supervision" },
  { key: "grants", label: "Grant writing" },
] as const;
export type Lane = (typeof LANES)[number]["key"];

export const NODE_KINDS = [
  { key: "goal", label: "Goal", lane: "research" },
  { key: "objective", label: "Objective", lane: "research" },
  { key: "project", label: "Project", lane: "research" },
  { key: "person", label: "Person", lane: "supervision" },
  { key: "gap", label: "Knowledge gap", lane: "research" },
  { key: "grant", label: "Grant", lane: "grants" },
] as const;
export type NodeKind = (typeof NODE_KINDS)[number]["key"];

export const LINK_KINDS = [
  { key: "feeds", label: "feeds into" },
  { key: "advances", label: "advances" },
  { key: "works_on", label: "works on" },
  { key: "learns", label: "needs to learn" },
  { key: "funds", label: "would fund" },
] as const;
export type LinkKind = (typeof LINK_KINDS)[number]["key"];

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
};
export type PwNodeFields = Omit<PwNode, "id">;
export type PwLink = { id: string; from_id: string; to_id: string; kind: LinkKind };
export type PwRevision = { id: string; changed_at: string; old_title: string; old_detail: string | null; reason: string | null };

const NODE_COLS = "id,kind,lane,title,detail,status,potential,project_id,reading_id,start_on,end_on,effort_pm,cost,fte,lane_row,grant_stage";
const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));

export async function loadPathways(): Promise<{ nodes: PwNode[]; links: PwLink[]; years: number }> {
  const [n, l, s] = await Promise.all([
    supabase.from("pw_node").select(NODE_COLS).order("created_at"),
    supabase.from("pw_link").select("id,from_id,to_id,kind"),
    supabase.from("user_setting").select("pathway_years").maybeSingle(),
  ]);
  for (const r of [n, l, s]) if (r.error) throw new Error(r.error.message);
  return {
    nodes: ((n.data ?? []) as PwNode[]).map((x) => ({ ...x, effort_pm: num(x.effort_pm), cost: num(x.cost), fte: num(x.fte) })),
    links: (l.data ?? []) as PwLink[],
    years: Number(s.data?.pathway_years ?? 5),
  };
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

/** Link two items (one link per pair; linking again changes its kind). */
export async function saveLink(from_id: string, to_id: string, kind: LinkKind): Promise<void> {
  await check(supabase.from("pw_link").upsert({ from_id, to_id, kind }, { onConflict: "from_id,to_id" }));
}
export async function setLinkKind(id: string, kind: LinkKind): Promise<void> {
  await check(supabase.from("pw_link").update({ kind }).eq("id", id));
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

/** The link kind a drag from one item to another most likely means. */
export function inferLinkKind(from: PwNode, to: PwNode): LinkKind {
  if (from.kind === "grant") return "funds";
  if (from.kind === "gap" || to.kind === "gap") return "learns";
  if (from.kind === "person") return "works_on";
  if (to.kind === "goal") return "advances";
  return "feeds";
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
