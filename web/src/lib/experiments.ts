// Experiments ("Life is experiments", 0066_experiments.sql): umbrella topics, each
// with subtopics, and notes under either, each note tagged Tip, Hypothesis,
// Practice, Self, Innovation (0067), Modelling (0069) and/or Teaching (0079), and marked outdated (⊘) when it no longer holds;
// a topic or subtopic can be marked outdated too (0070). One umbrella topic is the theme of your
// ambitions (0081): always there (made when missing; it cannot be deleted), its title yours to change, and
// its subtopics are the ambitions Pathways ticks its activities for.
// Both topics and notes are in your own order (sort_order 10, 20, 30…).
import { supabase } from "./supabase";

export const TAGS = ["tip", "hypothesis", "practice", "self", "innovation", "modelling", "teaching"] as const;
export type Tag = (typeof TAGS)[number];
export const TAG_LABEL: Record<Tag, string> = {
  tip: "Tip", hypothesis: "Hypothesis", practice: "Practice", self: "Self", innovation: "Innovation", modelling: "Modelling", teaching: "Teaching",
};

/** tags (0068): none needed; they count for everything under the topic. outdated: 0070. */
export type Topic = {
  id: string; parent_id: string | null; title: string; tags: Tag[]; outdated: boolean; sort_order: number; created_at: string;
  ambitions?: boolean; // the theme of your ambitions (0081)
};
const TOPIC_COLS = "id, parent_id, title, tags, outdated, sort_order, created_at";
export const THEME_TITLE = "Innovation ambitions"; // the theme's first title
export type Note = {
  id: string;
  topic_id: string;
  body: string;
  tags: Tag[];
  outdated: boolean;
  noted_on: string;
  sort_order: number;
  created_at: string;
};

async function check<T>(q: PromiseLike<{ data: T | null; error: { message: string } | null }>): Promise<T> {
  const { data, error } = await q;
  if (error) throw new Error(error.message);
  return data as T;
}

/**
 * Every topic and note. themed: the theme of your ambitions is there (0081 is run); it is made
 * here when it is missing, first among the topics.
 */
export async function loadExperiments(): Promise<{ topics: Topic[]; notes: Note[]; themed: boolean }> {
  const topicsQ = async () => {
    const r = await supabase.from("exp_topic").select(`${TOPIC_COLS}, ambitions`).order("sort_order").order("created_at");
    if (r.error && /ambitions/.test(r.error.message)) return { themed: false, rows: await check<Topic[]>(supabase.from("exp_topic").select(TOPIC_COLS).order("sort_order").order("created_at")) };
    if (r.error) throw new Error(r.error.message);
    return { themed: true, rows: (r.data ?? []) as Topic[] };
  };
  const [t, notes] = await Promise.all([
    topicsQ(),
    check<Note[]>(supabase.from("exp_note").select("id, topic_id, body, tags, outdated, noted_on, sort_order, created_at")
      .order("sort_order").order("created_at")),
  ]);
  const topics = t.rows ?? [];
  if (t.themed && !topics.some((x) => x.ambitions)) {
    const top = topics.filter((x) => !x.parent_id);
    const { data, error } = await supabase.from("exp_topic")
      .insert({ title: THEME_TITLE, parent_id: null, tags: ["innovation"], ambitions: true, sort_order: top.length ? Math.min(...top.map((x) => x.sort_order)) - 10 : 0 })
      .select(`${TOPIC_COLS}, ambitions`).single();
    if (data) topics.unshift(data as Topic);
    else if (error && !/duplicate|unique/i.test(error.message)) throw new Error(error.message);
    else return loadExperiments(); // made meanwhile, elsewhere
  }
  return { topics, notes: notes ?? [], themed: t.themed };
}
/** The theme of your ambitions, and its subtopics (the ambitions) in your order. */
export function ambitionsOf(topics: Topic[]): { theme: Topic | null; ambitions: Topic[] } {
  const theme = topics.find((t) => t.ambitions) ?? null;
  const ambitions = theme ? topics.filter((t) => t.parent_id === theme.id).sort((a, b) => a.sort_order - b.sort_order || a.created_at.localeCompare(b.created_at)) : [];
  return { theme, ambitions };
}

export async function addTopic(title: string, parent_id: string | null, tags: Tag[], sort_order: number): Promise<Topic> {
  return check<Topic>(supabase.from("exp_topic").insert({ title, parent_id, tags, sort_order }).select(TOPIC_COLS).single());
}
export async function saveTopic(id: string, fields: Partial<Pick<Topic, "title" | "tags" | "outdated" | "sort_order">>): Promise<void> {
  await check(supabase.from("exp_topic").update(fields).eq("id", id));
}
/** Its subtopics and every note under them go with it. */
export async function deleteTopic(id: string): Promise<void> {
  await check(supabase.from("exp_topic").delete().eq("id", id));
}

export async function addNote(fields: Pick<Note, "topic_id" | "body" | "tags" | "sort_order">): Promise<Note> {
  return check<Note>(supabase.from("exp_note").insert(fields)
    .select("id, topic_id, body, tags, outdated, noted_on, sort_order, created_at").single());
}
export async function saveNote(id: string, fields: Partial<Pick<Note, "body" | "tags" | "outdated" | "sort_order" | "topic_id">>): Promise<void> {
  await check(supabase.from("exp_note").update({ ...fields, updated_at: new Date().toISOString() }).eq("id", id));
}
export async function deleteNote(id: string): Promise<void> {
  await check(supabase.from("exp_note").delete().eq("id", id));
}

/** The new order as 10, 20, 30…, only the rows whose place changed. */
export function placesOf<T extends { id: string; sort_order: number }>(rows: T[], ids: string[]): { id: string; sort_order: number }[] {
  return ids
    .map((id, i) => ({ id, sort_order: (i + 1) * 10 }))
    .filter((c) => rows.find((r) => r.id === c.id)?.sort_order !== c.sort_order);
}

/** Every word must appear in the note, its topic or subtopic (any order, any case). */
export function matches(text: string, query: string): boolean {
  const hay = text.toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}

export function experimentsMarkdown(topics: Topic[], notes: Note[]): string {
  const lines = ["# Life is experiments", ""];
  const notesOf = (t: Topic) => notes.filter((n) => n.topic_id === t.id);
  const note = (n: Note) =>
    `- ${n.outdated ? "~~" : ""}${n.body.replace(/\n/g, "\n  ")}${n.outdated ? "~~ (outdated)" : ""} ` +
    `_[${n.tags.map((t) => TAG_LABEL[t]).join(", ")} · ${n.noted_on}]_`;
  const tagged = (t: Topic) =>
    (t.tags?.length ? ` _[${t.tags.map((x) => TAG_LABEL[x]).join(", ")}]_` : "") + (t.outdated ? " (outdated)" : "");
  for (const t of topics.filter((x) => !x.parent_id)) {
    lines.push(`## ${t.title}${tagged(t)}`, "", ...notesOf(t).map(note));
    for (const s of topics.filter((x) => x.parent_id === t.id)) lines.push("", `### ${s.title}${tagged(s)}`, "", ...notesOf(s).map(note));
    lines.push("");
  }
  return lines.join("\n");
}
