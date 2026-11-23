// Practice (0055_practice.sql): a goal practised over days, and under it one session a
// skill a day — reading, writing, speaking or formulation — with your own feedback and
// ratings; and, on a practice, the formulation of a debate (0057).
import { supabase } from "./supabase";
import { check } from "./data";

export type Skill = "reading" | "writing" | "speaking" | "formulation";
export const SKILLS: { key: Skill; label: string }[] = [
  { key: "reading", label: "Reading" },
  { key: "writing", label: "Writing" },
  { key: "speaking", label: "Speaking" },
  { key: "formulation", label: "Formulation" },
];
export const skillLabel = (s: Skill) => SKILLS.find((k) => k.key === s)?.label ?? s;

/** What each skill is rated on, 1–5, in a session. */
export const CRITERIA: Record<Skill, string[]> = {
  reading: ["Understanding the argument", "Judging the evidence", "Notes worth keeping"],
  writing: ["Structure and argument", "Clarity", "Concision", "Use of sources"],
  speaking: ["Structure", "Delivery and pace", "Visuals", "Handling questions"],
  formulation: ["Objectives made explicit", "Assumptions surfaced", "Fair to each view", "Testable against data"],
};

// ---- problem formulation (0057): a debate as views, each with its objectives and
// assumptions; the conflicts between objectives; and the data that would validate them
export type Item = { id: string; text: string };
/** Whose objective it is: the whole system's, a member's, or a stakeholder group's ("" untagged). */
export type Tag = "system" | "member" | "group" | "";
export const TAGS: { key: Exclude<Tag, "">; label: string }[] = [
  { key: "system", label: "System" },
  { key: "member", label: "Member" },
  { key: "group", label: "Stakeholder group" },
];
export const tagLabel = (t: Tag) => TAGS.find((x) => x.key === t)?.label ?? "";
export type Objective = Item & { measure: string; tag: Tag };
export type View = { id: string; name: string; objectives: Objective[]; assumptions: Item[] };
export type Conflict = { id: string; a: string | null; b: string | null; why: string };
export type Datum = { id: string; name: string; source: string; notes: string; tests: string[] };
export type Formulation = { question: string; views: View[]; conflicts: Conflict[]; data: Datum[] };

export const newId = () => crypto.randomUUID();
export const emptyFormulation = (): Formulation => ({
  question: "",
  views: [{ id: newId(), name: "", objectives: [], assumptions: [] }, { id: newId(), name: "", objectives: [], assumptions: [] }],
  conflicts: [],
  data: [],
});
/** As stored, with every list present (a hand-edited or older document may lack some). */
export function asFormulation(f: unknown): Formulation | null {
  if (!f || typeof f !== "object") return null;
  const o = f as Partial<Formulation>;
  const arr = <T>(v: T[] | undefined) => (Array.isArray(v) ? v : []);
  return {
    question: o.question ?? "",
    views: arr(o.views).map((v) => ({
      id: v.id ?? newId(), name: v.name ?? "",
      objectives: arr(v.objectives).map((x) => ({
        id: x.id ?? newId(), text: x.text ?? "", measure: x.measure ?? "",
        tag: TAGS.some((t) => t.key === x.tag) ? x.tag : ("" as Tag),
      })),
      assumptions: arr(v.assumptions).map((x) => ({ id: x.id ?? newId(), text: x.text ?? "" })),
    })),
    conflicts: arr(o.conflicts).map((c) => ({ id: c.id ?? newId(), a: c.a ?? null, b: c.b ?? null, why: c.why ?? "" })),
    data: arr(o.data).map((d) => ({ id: d.id ?? newId(), name: d.name ?? "", source: d.source ?? "", notes: d.notes ?? "", tests: arr(d.tests) })),
  };
}
/** Counts for a one-line summary. */
export function formulationSize(f: Formulation) {
  return {
    views: f.views.length,
    objectives: f.views.reduce((n, v) => n + v.objectives.length, 0),
    byTag: TAGS.map((t) => ({ ...t, n: f.views.reduce((n, v) => n + v.objectives.filter((o) => o.tag === t.key).length, 0) }))
      .filter((t) => t.n),
    assumptions: f.views.reduce((n, v) => n + v.assumptions.length, 0),
    conflicts: f.conflicts.length,
    data: f.data.length,
  };
}

export type Practice = {
  id: string; title: string; goal: string | null; started_on: string; done_on: string | null; created_at: string;
  formulation?: Formulation | null; // absent until 0057 is run
};
export type PracticeFields = Omit<Practice, "id" | "created_at">;
export type Session = {
  id: string; practice_id: string; done_on: string; skill: Skill; minutes: number | null;
  did: string | null; went_well: string | null; to_fix: string | null; next_focus: string | null;
  ratings: Record<string, number>; created_at: string;
};
export type SessionFields = Omit<Session, "id" | "created_at">;
export type Book = { practices: Practice[]; sessions: Session[] };

const PAGE = 1000; // PostgREST's default row cap per request

/** Everything in Practice; null until 0055 is run. */
export async function loadBook(): Promise<Book | null> {
  const p = await supabase.from("practice").select("*").order("started_on", { ascending: false }).order("created_at", { ascending: false });
  if (p.error) {
    if (p.error.code === "PGRST205" || p.error.code === "42P01") return null; // no such table yet
    throw new Error(p.error.message);
  }
  const sessions: Session[] = [];
  for (let from = 0; ; from += PAGE) {
    const s = await supabase.from("practice_session").select("*")
      .order("done_on", { ascending: false }).order("created_at", { ascending: false }).order("id")
      .range(from, from + PAGE - 1);
    if (s.error) throw new Error(s.error.message);
    sessions.push(...(s.data as Session[]));
    if (s.data.length < PAGE) break;
  }
  const practices = (p.data as Practice[]).map((x) => ({ ...x, formulation: asFormulation(x.formulation) }));
  return { practices, sessions };
}

export async function savePractice(id: string | null, fields: Partial<PracticeFields>): Promise<string> {
  if (id) {
    await check(supabase.from("practice").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("practice").insert(fields).select("id").single());
  return row!.id;
}
export async function deletePractice(id: string): Promise<void> {
  await check(supabase.from("practice").delete().eq("id", id));
}
export async function saveSession(id: string | null, fields: Partial<SessionFields>): Promise<void> {
  await check(id ? supabase.from("practice_session").update(fields).eq("id", id) : supabase.from("practice_session").insert(fields));
}
export async function deleteSession(id: string): Promise<void> {
  await check(supabase.from("practice_session").delete().eq("id", id));
}

/** The mean of a session's ratings, or null if it has none. */
export function average(r: Record<string, number>): number | null {
  const v = Object.values(r).filter((n) => typeof n === "number");
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
