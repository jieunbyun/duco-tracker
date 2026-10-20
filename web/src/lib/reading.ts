// Reading: items (articles, books, …), dated notes, citations, and PDFs kept
// in the private "reading-pdfs" storage bucket (each user's own folder).
import { supabase } from "./supabase";
import { check } from "./data";

export const KINDS = [
  { key: "article", label: "Journal article" },
  { key: "book", label: "Book" },
  { key: "chapter", label: "Book chapter" },
  { key: "report", label: "Report" },
  { key: "other", label: "Other" },
] as const;
export const STATUSES = [
  { key: "reading", label: "Reading" },
  { key: "to_read", label: "To read" },
  { key: "finished", label: "Finished" },
  { key: "abandoned", label: "Abandoned" },
] as const;

export type Reading = {
  id: string;
  kind: string;
  title: string;
  authors: string | null;
  year: number | null;
  venue: string | null;
  publisher: string | null;
  volume: string | null;
  issue: string | null;
  pages: string | null;
  doi: string | null;
  url: string | null;
  citation: string | null;
  status: string;
  started_on: string | null;
  finished_on: string | null;
  project_id: string | null;
  pdf_path: string | null; // a copy stored here (before PDFs moved to OneDrive)
  pdf_size: number | null;
  pdf_url?: string | null; // the PDF on OneDrive
  created_at: string;
  reading_note?: { count: number }[];
};
export type ReadingFields = Omit<Reading, "id" | "created_at" | "reading_note">;
export type Note = { id: string; reading_id: string; noted_on: string; page: string | null; body: string };

const BUCKET = "reading-pdfs";

export async function loadReadings(): Promise<Reading[]> {
  return (await check<Reading[]>(
    supabase.from("reading").select("*, reading_note(count)").order("created_at", { ascending: false }),
  )) ?? [];
}
export async function saveReading(id: string | null, fields: Partial<ReadingFields>): Promise<string> {
  if (id) {
    await check(supabase.from("reading").update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from("reading").insert(fields).select("id").single());
  return row!.id;
}
// Deleting a reading, or its PDF, leaves the file in storage so undo can bring
// it back; prunePdfs() clears files no reading points at, once a session.
export async function deleteReading(r: Reading): Promise<void> {
  await check(supabase.from("reading").delete().eq("id", r.id));
}

export async function loadNotes(readingId: string): Promise<Note[]> {
  return (await check<Note[]>(
    supabase.from("reading_note").select("id,reading_id,noted_on,page,body")
      .eq("reading_id", readingId).order("noted_on", { ascending: false }).order("created_at", { ascending: false }),
  )) ?? [];
}
export async function saveNote(id: string | null, fields: Omit<Note, "id">): Promise<void> {
  await check(id ? supabase.from("reading_note").update(fields).eq("id", id)
                 : supabase.from("reading_note").insert(fields));
}
export async function deleteNote(id: string): Promise<void> {
  await check(supabase.from("reading_note").delete().eq("id", id));
}

// ---- PDFs ----------------------------------------------------------------------
/** The PDF lives on OneDrive; the reading keeps its link. */
export async function setPdfUrl(r: Reading, url: string | null): Promise<void> {
  await saveReading(r.id, { pdf_url: url });
}
/** A link to a stored copy that works for an hour. */
export async function pdfLink(r: Reading): Promise<string> {
  const { data, error } = await supabase.storage.from(BUCKET).createSignedUrl(r.pdf_path!, 3600);
  if (error) throw new Error(error.message);
  return data.signedUrl;
}
export async function removePdf(r: Reading): Promise<void> {
  await saveReading(r.id, { pdf_path: null, pdf_size: null });
}

// ---- details from a DOI (Crossref, open to browsers) ------------------------------
export function cleanDoi(input: string): string {
  return input.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, "");
}
export async function lookupDoi(input: string): Promise<Partial<ReadingFields>> {
  const doi = cleanDoi(input);
  if (!/^10\.\d{4,9}\/\S+$/.test(doi)) throw new Error("That does not look like a DOI (it starts with 10.).");
  const res = await fetch(`https://api.crossref.org/works/${encodeURIComponent(doi)}`);
  if (res.status === 404) throw new Error("No record found for that DOI.");
  if (!res.ok) throw new Error(`The DOI lookup answered ${res.status}.`);
  const m = (await res.json()).message;
  const kind = m.type === "journal-article" ? "article"
    : m.type === "book" || m.type === "monograph" || m.type === "edited-book" ? "book"
    : m.type === "book-chapter" ? "chapter"
    : m.type === "report" ? "report" : "other";
  const authors = (m.author ?? [])
    .map((a: { family?: string; given?: string; name?: string }) => a.family ? `${a.family}${a.given ? `, ${a.given}` : ""}` : a.name ?? "")
    .filter(Boolean)
    .join("; ");
  const year = m.issued?.["date-parts"]?.[0]?.[0] ?? m.published?.["date-parts"]?.[0]?.[0] ?? null;
  return {
    kind,
    title: m.title?.[0] ?? "",
    authors: authors || null,
    year,
    venue: m["container-title"]?.[0] ?? null,
    publisher: m.publisher ?? null,
    volume: m.volume ?? null,
    issue: m.issue ?? null,
    pages: m.page ?? null,
    doi: m.DOI ?? doi,
    url: m.URL ?? `https://doi.org/${doi}`,
  };
}

// ---- citations -----------------------------------------------------------------------
function authorList(r: Pick<Reading, "authors">): { family: string; given: string }[] {
  return (r.authors ?? "").split(";").map((s) => s.trim()).filter(Boolean).map((s) => {
    const [family, given = ""] = s.split(",").map((x) => x.trim());
    return { family, given };
  });
}
const initials = (given: string) => given.split(/[\s-]+/).filter(Boolean).map((g) => `${g[0]}.`).join(" ");

/** An APA-style reference from the details (your own citation wins if set). */
export function citationOf(r: Reading): string {
  if (r.citation?.trim()) return r.citation.trim();
  const a = authorList(r).map((x) => (x.given ? `${x.family}, ${initials(x.given)}` : x.family));
  const who = a.length > 1 ? `${a.slice(0, -1).join(", ")}, & ${a[a.length - 1]}` : a[0] ?? "";
  const when = r.year ? `(${r.year})` : "(n.d.)";
  const doi = r.doi ? ` https://doi.org/${r.doi}` : r.url ? ` ${r.url}` : "";
  let where = "";
  if (r.kind === "article") {
    where = [r.venue, r.volume ? `${r.volume}${r.issue ? `(${r.issue})` : ""}` : "", r.pages].filter(Boolean).join(", ");
  } else if (r.kind === "chapter") {
    where = [r.venue ? `In ${r.venue}` : "", r.pages ? `(pp. ${r.pages})` : ""].filter(Boolean).join(" ") + (r.publisher ? `. ${r.publisher}` : "");
  } else {
    where = r.publisher ?? r.venue ?? "";
  }
  return [who && `${who} ${when}.`, `${r.title}.`, where && `${where}.`].filter(Boolean).join(" ") + doi;
}

/** A BibTeX entry, keyed surname + year + first word of the title. */
export function bibtexOf(r: Reading): string {
  const first = authorList(r)[0]?.family ?? "anon";
  const word = (r.title.match(/[A-Za-z]{3,}/)?.[0] ?? "item").toLowerCase();
  const key = `${first.normalize("NFD").replace(/[^A-Za-z]/g, "").toLowerCase()}${r.year ?? ""}${word}`;
  const type = r.kind === "article" ? "article" : r.kind === "book" ? "book" : r.kind === "chapter" ? "incollection" : r.kind === "report" ? "techreport" : "misc";
  const authors = authorList(r).map((x) => (x.given ? `${x.family}, ${x.given}` : x.family)).join(" and ");
  const fields: [string, string | number | null | undefined][] = [
    ["author", authors],
    ["title", r.title],
    [r.kind === "chapter" ? "booktitle" : "journal", r.kind === "article" || r.kind === "chapter" ? r.venue : null],
    ["publisher", r.kind !== "article" ? r.publisher : null],
    ["year", r.year],
    ["volume", r.volume],
    ["number", r.issue],
    ["pages", r.pages?.replace(/-/g, "--")],
    ["doi", r.doi],
    ["url", r.doi ? null : r.url],
  ];
  const body = fields.filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => `  ${k} = {${v}}`);
  return `@${type}{${key},\n${body.join(",\n")}\n}`;
}

export function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

let pruned = false;
/** Remove stored PDFs no reading points at — at the start of a session, when no undo can need them. */
export async function prunePdfs(readings: Reading[]): Promise<void> {
  if (pruned) return;
  pruned = true;
  const { data: u } = await supabase.auth.getUser();
  if (!u.user) return;
  const { data, error } = await supabase.storage.from(BUCKET).list(u.user.id, { limit: 1000 });
  if (error || !data) return;
  const used = new Set(readings.map((r) => r.pdf_path).filter(Boolean));
  const orphans = data.map((f) => `${u.user!.id}/${f.name}`).filter((path) => !used.has(path));
  if (orphans.length) await supabase.storage.from(BUCKET).remove(orphans);
}
