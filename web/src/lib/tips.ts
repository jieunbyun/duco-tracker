// Tips: checklists kept by topic (0051_tips.sql), and the search that finds
// them as you type — like "Everything": every word must appear somewhere in the
// topic (its title, category, notes or any item), in any order.
//
//   paper submit       both words
//   "cover letter"     the phrase as written
//   grant|funding      either word
//   !draft             not this word
import { supabase } from "./supabase";

export type TipItem = { id: string; text: string; done: boolean };
export type Tip = {
  id: string;
  title: string;
  category: string | null;
  notes: string | null;
  items: TipItem[];
  created_at: string;
  updated_at: string;
};
export type TipFields = Pick<Tip, "title" | "category" | "notes" | "items">;

const COLS = "id, title, category, notes, items, created_at, updated_at";

export async function loadTips(): Promise<Tip[]> {
  const { data, error } = await supabase.from("tip").select(COLS).order("updated_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []).map((t) => ({ ...t, items: Array.isArray(t.items) ? t.items : [] })) as Tip[];
}

export async function addTip(fields: Partial<TipFields> & { title: string }): Promise<Tip> {
  const { data, error } = await supabase.from("tip").insert({ items: [], ...fields }).select(COLS).single();
  if (error) throw new Error(error.message);
  return data as Tip;
}

/** Saves one after another, so a quick run of ticks lands in the order made. */
let queue: Promise<unknown> = Promise.resolve();
export function saveTip(id: string, fields: Partial<TipFields>): Promise<string> {
  const updated_at = new Date().toISOString();
  const run = queue.then(async () => {
    const { error } = await supabase.from("tip").update({ ...fields, updated_at }).eq("id", id);
    if (error) throw new Error(error.message);
    return updated_at;
  });
  queue = run.catch(() => undefined);
  return run;
}

export async function deleteTip(id: string): Promise<void> {
  const { error } = await supabase.from("tip").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

export const newItem = (text: string): TipItem => ({ id: crypto.randomUUID(), text, done: false });

/** One item per line, dropping list marks ("- ", "* ", "1. ", "[ ] ", "☐ ") so a pasted list comes in clean. */
export function linesToItems(text: string): TipItem[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim().replace(/^(?:[-*•–]\s+|\d+[.)]\s+)?(?:\[[ xX]?\]\s*|[☐☑✓✔]\s*)?/, "").trim())
    .filter(Boolean)
    .map(newItem);
}

/** The checklist as Markdown, to paste elsewhere. */
export function tipAsText(t: Tip): string {
  const lines = [`# ${t.title}`, ...t.items.map((i) => `- [${i.done ? "x" : " "}] ${i.text}`)];
  if (t.notes?.trim()) lines.push("", t.notes.trim());
  return lines.join("\n");
}

// ---- search ----------------------------------------------------------------

type Term = { any: string[]; not: boolean };
export type Query = { terms: Term[]; marks: string[] }; // marks: the words to light up

export function parseQuery(q: string): Query {
  const terms: Term[] = [];
  for (const m of q.matchAll(/(!?)"([^"]*)"?|(\S+)/g)) {
    let not = m[1] === "!";
    let raw = m[2] ?? m[3] ?? "";
    if (m[3] && raw.startsWith("!")) {
      not = true;
      raw = raw.slice(1);
    }
    const any = (m[2] !== undefined ? [raw] : raw.split("|")).map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (any.length) terms.push({ any, not });
  }
  return { terms, marks: [...new Set(terms.filter((t) => !t.not).flatMap((t) => t.any))] };
}

const haystack = (t: Tip) =>
  [t.title, t.category ?? "", t.notes ?? "", ...t.items.map((i) => i.text)].join("\n").toLowerCase();

export function matches(t: Tip, q: Query): boolean {
  if (!q.terms.length) return true;
  const h = haystack(t);
  return q.terms.every((term) => term.any.some((w) => h.includes(w)) !== term.not);
}

/** How strongly a topic answers the search: words in its title count most. */
export function score(t: Tip, q: Query): number {
  const title = t.title.toLowerCase();
  let s = 0;
  for (const term of q.terms) {
    if (term.not) continue;
    if (term.any.some((w) => title.startsWith(w))) s += 4;
    else if (term.any.some((w) => title.includes(w))) s += 3;
    else if (term.any.some((w) => (t.category ?? "").toLowerCase().includes(w))) s += 2;
  }
  return s;
}

/** The items (or notes lines) the search words were found in, for the results list. */
export function hits(t: Tip, q: Query, max = 3): string[] {
  if (!q.marks.length) return [];
  const found = (s: string) => q.marks.some((w) => s.toLowerCase().includes(w));
  const lines = [...t.items.map((i) => i.text), ...(t.notes ?? "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean)];
  return lines.filter(found).slice(0, max);
}

/** Text cut into plain and lit-up pieces. */
export function highlight(text: string, marks: string[]): { s: string; hit: boolean }[] {
  if (!marks.length || !text) return [{ s: text, hit: false }];
  const lower = text.toLowerCase();
  const on = new Array<boolean>(text.length).fill(false);
  for (const w of marks) {
    for (let i = lower.indexOf(w); i >= 0; i = lower.indexOf(w, i + 1)) on.fill(true, i, i + w.length);
  }
  const out: { s: string; hit: boolean }[] = [];
  for (let i = 0; i < text.length; ) {
    let j = i;
    while (j < text.length && on[j] === on[i]) j++;
    out.push({ s: text.slice(i, j), hit: on[i] });
    i = j;
  }
  return out;
}
