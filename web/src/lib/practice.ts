// Practice (0055_practice.sql): a goal practised over days, and under it one session a
// skill a day — reading, writing or speaking — with your own feedback and ratings.
import { supabase } from "./supabase";
import { check } from "./data";

export type Skill = "reading" | "writing" | "speaking";
export const SKILLS: { key: Skill; label: string }[] = [
  { key: "reading", label: "Reading" },
  { key: "writing", label: "Writing" },
  { key: "speaking", label: "Speaking" },
];
export const skillLabel = (s: Skill) => SKILLS.find((k) => k.key === s)?.label ?? s;

/** What each skill is rated on, 1–5, in a session. */
export const CRITERIA: Record<Skill, string[]> = {
  reading: ["Understanding the argument", "Judging the evidence", "Notes worth keeping"],
  writing: ["Structure and argument", "Clarity", "Concision", "Use of sources"],
  speaking: ["Structure", "Delivery and pace", "Visuals", "Handling questions"],
};

export type Practice = {
  id: string; title: string; goal: string | null; started_on: string; done_on: string | null; created_at: string;
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
  return { practices: p.data as Practice[], sessions };
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
