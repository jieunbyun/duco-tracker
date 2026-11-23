// Meetings (0060_meetings.sql): your meeting logs, one series per log, as your .tex files
// kept them — and the way back to .tex, and in from it.
import { supabase } from "./supabase";
import { check } from "./data";
import { today } from "./dates";

export type Section = { heading: string; body: string; closed?: boolean; sent?: string[] };
export type Series = { id: string; name: string; headings: string[]; project_id: string | null; created_at: string };
export type Meeting = {
  id: string; series_id: string; met_on: string; title: string | null; people: string | null;
  sections: Section[]; created_at: string; updated_at: string;
};
export type MeetingFields = Pick<Meeting, "series_id" | "met_on" | "title" | "people" | "sections">;

/** The headings a new series starts its meetings with. */
export const TEMPLATES: { name: string; headings: string[] }[] = [
  { name: "Research", headings: ["Purpose", "Update", "Decided", "They will", "I will", "Open", "Changed my view"] },
  { name: "General", headings: ["Discussion", "Actions"] },
];
/** Sections whose lines are things to do: each line can go to Week as a to-do. */
export const isAction = (h: string) => /^(i will|actions?|next steps|to ?dos?)\.?$/i.test(h.trim());
/** An open question: ticked off once it is settled. */
export const isOpen = (h: string) => /^open( questions?)?\.?$/i.test(h.trim());
/** A section's lines, without their "- " (an empty or "N/A" line is no line). */
export const linesOf = (body: string) =>
  body.split("\n").map((l) => l.replace(/^\s*-\s*/, "").trim()).filter((l) => l && !/^n\/?a$/i.test(l));

// ---- loading and saving ------------------------------------------------------------------
const PAGE = 1000;
const missing = (code?: string) => code === "PGRST205" || code === "42P01";

/** Every series and meeting; null until 0060 is run. */
export async function loadAll(): Promise<{ series: Series[]; meetings: Meeting[] } | null> {
  const s = await supabase.from("meeting_series").select("id,name,headings,project_id,created_at").order("name");
  if (s.error) {
    if (missing(s.error.code)) return null;
    throw new Error(s.error.message);
  }
  const meetings: Meeting[] = [];
  for (let from = 0; ; from += PAGE) {
    const m = await supabase.from("meeting").select("id,series_id,met_on,title,people,sections,created_at,updated_at")
      .order("met_on", { ascending: false }).order("created_at", { ascending: false }).order("id").range(from, from + PAGE - 1);
    if (m.error) throw new Error(m.error.message);
    meetings.push(...(m.data as Meeting[]).map((x) => ({ ...x, sections: Array.isArray(x.sections) ? x.sections : [] })));
    if (m.data.length < PAGE) break;
  }
  return { series: s.data as Series[], meetings };
}
export async function saveSeries(id: string | null, fields: Partial<Pick<Series, "name" | "headings" | "project_id">>): Promise<string> {
  if (id) {
    await check(supabase.from("meeting_series").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("meeting_series").insert(fields).select("id").single());
  return row!.id;
}
export async function deleteSeries(id: string): Promise<void> {
  await check(supabase.from("meeting_series").delete().eq("id", id));
}
export async function saveMeeting(id: string | null, fields: Partial<MeetingFields>): Promise<string> {
  const at = { ...fields, updated_at: new Date().toISOString() };
  if (id) {
    await check(supabase.from("meeting").update(at).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("meeting").insert(at).select("id").single());
  return row!.id;
}
export async function deleteMeeting(id: string): Promise<void> {
  await check(supabase.from("meeting").delete().eq("id", id));
}
/** A whole log at once: the series and all its meetings. */
export async function importLog(log: ParsedLog): Promise<string> {
  const id = await saveSeries(null, { name: log.name, headings: log.headings });
  if (log.meetings.length) {
    await check(supabase.from("meeting").insert(log.meetings.map((m) => ({ ...m, series_id: id }))));
  }
  return id;
}
/** A line of an action section, as a to-do in Week (filed under the week of `day`). */
export async function sendToWeek(title: string, note: string, day = today()): Promise<void> {
  await check(supabase.from("todo").insert({ kind: "task", title, due_on: day, note }));
}

// ---- from .tex ---------------------------------------------------------------------------
export type ParsedMeeting = Omit<MeetingFields, "series_id">;
export type ParsedLog = { name: string; headings: string[]; meetings: ParsedMeeting[]; skipped: string[] };

const unescape = (s: string) => s.replace(/\\([&%$#_{}])/g, "$1").replace(/~/g, " ");

/** LaTeX body text as plain lines: lists as "- " (nested "  - "), links as [text](url). */
function plain(tex: string): string {
  const out: string[] = [];
  let depth = 0;
  let line = "";
  const flush = () => {
    const t = line.replace(/\s+/g, " ").trim();
    if (t) out.push(depth ? `${"  ".repeat(depth - 1)}- ${t}` : t);
    line = "";
  };
  const text = tex
    .replace(/(^|[^\\])%.*$/gm, "$1") // comments
    .replace(/\\href\{([^}]*)\}\{([^}]*)\}/g, (_, url, label) => `[${label}](${url})`)
    .replace(/\\url\{([^}]*)\}/g, "$1")
    .replace(/\s*\\\\(\[[^\]]*\])?\s*/g, "\n\n"); // a forced line break: a line of its own
  for (const raw of text.split("\n")) {
    let rest = raw;
    // \begin{itemize}[...], and the same written without its \begin
    while (rest.trim()) {
      const begin = rest.match(/^\s*(?:\\begin)?\{(?:itemize|enumerate)\}(\[[^\]]*\])?/);
      const end = rest.match(/^\s*\\end\{(?:itemize|enumerate)\}/);
      const item = rest.match(/^\s*\\item\b\s?/);
      if (begin) { flush(); depth += 1; rest = rest.slice(begin[0].length); continue; }
      if (end) { flush(); depth = Math.max(0, depth - 1); rest = rest.slice(end[0].length); continue; }
      if (item) { flush(); rest = rest.slice(item[0].length); continue; }
      const next = rest.search(/\\item\b|\\end\{(?:itemize|enumerate)\}|\\begin\{(?:itemize|enumerate)\}/);
      const chunk = next > 0 ? rest.slice(0, next) : rest;
      line += ` ${chunk}`;
      rest = next > 0 ? rest.slice(next) : "";
    }
    if (!raw.trim() && !depth) flush(); // a blank line ends a paragraph
  }
  flush();
  return unescape(out.join("\n"));
}

/** "12-11-26. Title" → 2026-11-12 and "Title"; null without a date. */
function sectionHead(s: string): { met_on: string; title: string } | null {
  const m = s.trim().match(/^(\d{1,2})[-./](\d{1,2})[-./](\d{2}|\d{4})\.?\s*(.*)$/);
  if (!m) return null;
  const [, d, mo, y, rest] = m;
  const year = y.length === 2 ? `20${y}` : y;
  const iso = `${year}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  if (Number.isNaN(Date.parse(iso)) || +mo > 12 || +d > 31) return null;
  return { met_on: iso, title: unescape(rest.replace(/\.\s*$/, "").trim()) };
}

/** A .tex meeting log, as your files are written: \section*{date. title}, \paragraph{Heading.}. */
export function parseTex(tex: string, fileName = ""): ParsedLog {
  const name = unescape(tex.match(/\\fancyhead\[R\]\{([^}]*)\}/)?.[1]?.trim()
    || fileName.replace(/\.tex$/i, "").replace(/^\d{4}\s+/, "").trim() || "Meetings");
  const body = tex.split(/\\begin\{document\}/)[1]?.split(/\\end\{document\}/)[0] ?? tex;
  const parts = body.split(/\\section\*?\{/).slice(1);
  const meetings: ParsedMeeting[] = [];
  const skipped: string[] = [];
  const seen: string[] = [];
  for (const part of parts) {
    // the section's title runs to its closing brace (titles may hold \& and the like)
    let i = 0, level = 1;
    for (; i < part.length && level; i++) {
      if (part[i] === "{" && part[i - 1] !== "\\") level++;
      if (part[i] === "}" && part[i - 1] !== "\\") level--;
    }
    const head = sectionHead(part.slice(0, i - 1));
    const rest = part.slice(i);
    if (!head) {
      skipped.push(part.slice(0, i - 1).trim() || "(untitled)");
      continue;
    }
    const sections: Section[] = [];
    const chunks = rest.split(/\\paragraph\*?\{/);
    const lead = plain(chunks[0]);
    if (lead) sections.push({ heading: "Notes", body: lead });
    for (const c of chunks.slice(1)) {
      const close = c.indexOf("}");
      const heading = unescape(c.slice(0, close).replace(/[.:]\s*$/, "").trim());
      const text = plain(c.slice(close + 1));
      if (!heading && !text) continue;
      sections.push({ heading: heading || "Notes", body: text });
      if (heading && !seen.some((h) => h.toLowerCase() === heading.toLowerCase())) seen.push(heading);
    }
    meetings.push({ ...head, people: null, sections });
  }
  const research = seen.some((h) => /^i will$/i.test(h));
  return { name, headings: (research ? TEMPLATES[0] : TEMPLATES[1]).headings, meetings, skipped };
}

// ---- to .tex -----------------------------------------------------------------------------
/** Escapes what LaTeX would read as a command, but leaves your own \commands, and links, as they are. */
function esc(s: string): string {
  return s.split(/(\[[^\]]*\]\([^)]*\))/).map((part, i) => {
    if (i % 2) {
      const [, label, url] = part.match(/^\[([^\]]*)\]\(([^)]*)\)$/)!;
      return `\\href{${url}}{${esc(label)}}`;
    }
    return part.replace(/(^|[^\\])([&%$#_])/g, "$1\\$2");
  }).join("");
}
function texBody(body: string): string {
  const out: string[] = [];
  let depth = 0;
  const to = (d: number) => {
    while (depth < d) { out.push(`${"\t".repeat(depth)}\\begin{itemize}[nosep]`); depth++; }
    while (depth > d) { depth--; out.push(`${"\t".repeat(depth)}\\end{itemize}`); }
  };
  for (const raw of body.split("\n")) {
    if (!raw.trim()) continue;
    const m = raw.match(/^(\s*)-\s+(.*)$/);
    if (m) {
      to(Math.floor(m[1].replace(/\t/g, "  ").length / 2) + 1);
      out.push(`${"\t".repeat(depth)}\\item ${esc(m[2])}`);
    } else {
      to(0);
      // a line after a line: a forced break, so the two don't run together
      if (out.length && !out[out.length - 1].trim().startsWith("\\")) out[out.length - 1] += " \\\\";
      out.push(esc(raw.trim()));
    }
  }
  to(0);
  return out.join("\n");
}
const dmy = (iso: string) => `${iso.slice(8, 10)}-${iso.slice(5, 7)}-${iso.slice(2, 4)}`;

/** A series as a .tex file, laid out as yours are: newest meeting first. */
export function toTex(series: Series, meetings: Meeting[]): string {
  const out = [
    "\\documentclass[final,11pt]{article}", "",
    "\\usepackage[margin=2.5cm]{geometry}", "\\usepackage{fancyhdr}", "\\usepackage{parskip,hyperref,enumitem}", "",
    "\\pagestyle{fancy}", "\\fancyhf{}", "\\fancyhead[L]{Meeting notes}", `\\fancyhead[R]{${esc(series.name)}}`, "",
    "\\begin{document}", "",
  ];
  for (const m of [...meetings].sort((a, b) => b.met_on.localeCompare(a.met_on))) {
    const title = [m.title?.trim(), m.people?.trim() ? `(${m.people.trim()})` : ""].filter(Boolean).join(" ");
    out.push(`\\section*{${dmy(m.met_on)}.${title ? ` ${esc(title)}` : ""}}`, "");
    for (const s of m.sections) {
      if (!s.body.trim()) continue;
      const body = texBody(s.body);
      out.push(body.startsWith("\\begin") ? `\\paragraph{${esc(s.heading)}.}\n${body}` : `\\paragraph{${esc(s.heading)}.} ${body}`, "");
    }
  }
  out.push("\\end{document}", "");
  return out.join("\n");
}
export function downloadTex(fileName: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "application/x-tex" }));
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
