// Network (0062_network.sql): the people you know, each time you met them, the opportunities
// you are watching, and the organisations you deal with.
import { supabase } from "./supabase";
import { check } from "./data";
import { at, text, excelDate, type Sheet } from "./xlsx";

export type Contact = {
  id: string; name: string; other_name: string | null; alias: string | null; country: string | null;
  institution: string | null; unit: string | null; title: string | null; email: string | null; keywords: string | null;
  tags: string[]; notes: string | null; created_at: string; updated_at: string;
};
export type ContactFields = Omit<Contact, "id" | "created_at" | "updated_at">;
export type Interaction = { id: string; contact_id: string; met_on: string | null; body: string; created_at: string };
export type Opportunity = { id: string; name: string; deadline: string | null; notes: string | null; done: boolean };
export type Organisation = { id: string; name: string; notes: string | null };
export type Network = { contacts: Contact[]; interactions: Interaction[]; opportunities: Opportunity[]; organisations: Organisation[] };

const missing = (code?: string) => code === "PGRST205" || code === "42P01";
const PAGE = 1000;
async function all<T>(table: string, cols: string, order: (q: any) => any): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; ; from += PAGE) {
    const r = await order(supabase.from(table).select(cols)).range(from, from + PAGE - 1);
    if (r.error) throw new Error(r.error.message);
    out.push(...(r.data as T[]));
    if (r.data.length < PAGE) return out;
  }
}

/** Everything in Network; null until 0062 is run. */
export async function loadNetwork(): Promise<Network | null> {
  const c = await supabase.from("contact").select("id").limit(1);
  if (c.error) {
    if (missing(c.error.code)) return null;
    throw new Error(c.error.message);
  }
  const [contacts, interactions, opportunities, organisations] = await Promise.all([
    all<Contact>("contact", "*", (q) => q.order("name").order("id")),
    all<Interaction>("contact_interaction", "id,contact_id,met_on,body,created_at",
      (q) => q.order("met_on", { ascending: false, nullsFirst: false }).order("created_at", { ascending: false }).order("id")),
    all<Opportunity>("opportunity", "id,name,deadline,notes,done", (q) => q.order("deadline", { nullsFirst: false }).order("id")),
    all<Organisation>("organisation", "id,name,notes", (q) => q.order("name").order("id")),
  ]);
  return { contacts: contacts.map((x) => ({ ...x, tags: x.tags ?? [] })), interactions, opportunities, organisations };
}

async function upsert<T extends object>(table: string, id: string | null, fields: T): Promise<string> {
  if (id) {
    await check(supabase.from(table).update(fields).eq("id", id));
    return id;
  }
  const row = await check<{ id: string }>(supabase.from(table).insert(fields).select("id").single());
  return row!.id;
}
export const saveContact = (id: string | null, f: Partial<ContactFields>) => upsert("contact", id, { ...f, updated_at: new Date().toISOString() });
export const saveInteraction = (id: string | null, f: Partial<Omit<Interaction, "id" | "created_at">>) => upsert("contact_interaction", id, f);
export const saveOpportunity = (id: string | null, f: Partial<Omit<Opportunity, "id">>) => upsert("opportunity", id, f);
export const saveOrganisation = (id: string | null, f: Partial<Omit<Organisation, "id">>) => upsert("organisation", id, f);
export async function remove(table: "contact" | "contact_interaction" | "opportunity" | "organisation", id: string): Promise<void> {
  await check(supabase.from(table).delete().eq("id", id));
}

// ---- dates written by hand: "23 Oct 26.", "3 August 26.", "21 September 2026.", "29-Sep-2026:",
// "14-OCT-25:", "Oct-25:" (the 1st of the month), "6-Oct-25:" -------------------------------
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const DATE = /(?:^|[\s(])(?:(\d{1,2})[\s-])?([A-Za-z]{3,9})[\s-](\d{4}|\d{2})\s*[.:;,)]?(?=\s|$)/;
/** An interaction note as written in a cell: its date (if one is given) and the rest. */
export function splitDated(s: string): { met_on: string | null; body: string } {
  const m = s.match(DATE);
  if (m && m.index !== undefined && m.index < 60) {
    const mon = MONTHS.indexOf(m[2].slice(0, 3).toLowerCase());
    if (mon >= 0 && (m[2].length === 3 || "january february march april may june july august september october november december".includes(m[2].toLowerCase()))) {
      const year = m[3].length === 2 ? 2000 + +m[3] : +m[3];
      const day = m[1] ? +m[1] : 1;
      const iso = `${year}-${String(mon + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      if (!Number.isNaN(Date.parse(iso)) && day <= 31) {
        const before = s.slice(0, m.index).trim();
        const after = s.slice(m.index + m[0].length).trim();
        return { met_on: iso, body: [before, after].filter(Boolean).join(" ") };
      }
    }
  }
  return { met_on: null, body: s.trim() };
}

// ---- from a spreadsheet laid out as yours ---------------------------------------------------
export type ParsedPerson = Omit<ContactFields, "tags"> & { tags: string[]; interactions: { met_on: string | null; body: string }[] };
export type ParsedNetwork = { people: ParsedPerson[]; opportunities: { name: string; deadline: string | null }[]; organisations: string[] };

const FIELDS: [keyof ContactFields | "interactions", RegExp][] = [
  ["name", /^(full )?name$/i],
  ["other_name", /korean name|other names?|native name/i],
  ["alias", /alias|nickname/i],
  ["country", /country/i],
  ["institution", /institution|organi[sz]ation|company|affiliation/i],
  ["unit", /other details|department|unit|team/i],
  ["title", /^(job )?title|position|role/i],
  ["email", /e-?mail/i],
  ["keywords", /keywords?|interests?|topics?/i],
  ["interactions", /interactions?|history|met/i],
];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function parseNetwork(sheets: Sheet[]): ParsedNetwork {
  const people = new Map<string, ParsedPerson>();
  const opportunities: ParsedNetwork["opportunities"] = [];
  const organisations: string[] = [];
  for (const s of sheets) {
    const head = (c: number) => text(at(s, 1, c));
    const cols = new Map<string, number>();
    for (let c = 1; c <= s.maxCol; c++) {
      const f = FIELDS.find(([k, re]) => !cols.has(k) && re.test(head(c)));
      if (f) cols.set(f[0], c);
    }
    // opportunities: a scheme (or call) and its deadline
    const cDeadline = [...Array(s.maxCol).keys()].map((i) => i + 1).find((c) => /deadline|due/i.test(head(c)));
    if (cDeadline && !cols.has("institution")) {
      for (let r = 2; r <= s.maxRow; r++) {
        const name = text(at(s, r, 1)).replace(/:$/, "");
        const d = at(s, r, cDeadline)?.v;
        if (name) opportunities.push({ name, deadline: typeof d === "number" ? excelDate(d) : null });
      }
      continue;
    }
    // organisations: a list of names
    if (/organi[sz]ations?/i.test(s.name) && !cols.has("institution")) {
      for (let r = 1; r <= s.maxRow; r++) {
        const name = text(at(s, r, 1));
        if (name && !/^name$/i.test(name)) organisations.push(name);
      }
      continue;
    }
    if (!cols.has("name")) continue;
    const known = new Set(cols.values());
    for (let r = 2; r <= s.maxRow; r++) {
      const name = text(at(s, r, cols.get("name")!));
      if (!name) continue;
      const get = (k: string) => (cols.has(k) ? text(at(s, r, cols.get(k)!)) || null : null);
      const notes: string[] = [];
      let email = get("email");
      // columns without a heading: an e-mail address, a link, or a note
      for (let c = 1; c <= s.maxCol; c++) {
        const cell = at(s, r, c);
        const t = text(cell);
        if (cell?.link) notes.push(`[${t || cell.link}](${cell.link})`);
        else if (known.has(c) || !t) continue;
        else if (EMAIL.test(t) && !email) email = t;
        else notes.push(t);
      }
      const interactions = (get("interactions") ?? "").split(/\n+/).map((x) => x.trim()).filter(Boolean).map(splitDated);
      const p: ParsedPerson = {
        name, other_name: get("other_name"), alias: get("alias"), country: get("country"), institution: get("institution"),
        unit: get("unit"), title: get("title"), email, keywords: get("keywords"), notes: notes.join("\n") || null,
        tags: [s.name], interactions,
      };
      const key = name.toLowerCase();
      const same = people.get(key);
      if (!same) {
        people.set(key, p);
        continue;
      }
      // the same person on another sheet: one person, with both tags, and whatever the other sheet adds
      if (!same.tags.includes(s.name)) same.tags.push(s.name);
      for (const k of ["other_name", "alias", "country", "institution", "unit", "title", "email", "keywords"] as const) same[k] ??= p[k];
      if (p.notes && !same.notes?.includes(p.notes)) same.notes = [same.notes, p.notes].filter(Boolean).join("\n");
      for (const i of p.interactions) if (!same.interactions.some((x) => x.body === i.body)) same.interactions.push(i);
    }
  }
  return { people: [...people.values()], opportunities, organisations };
}

/** Bring a parsed workbook in: new people are added; people already here get any new tags and interactions. */
export async function importNetwork(p: ParsedNetwork, now: Network): Promise<void> {
  for (const person of p.people) {
    const { interactions, ...fields } = person;
    const same = now.contacts.find((c) => c.name.trim().toLowerCase() === person.name.toLowerCase());
    let id = same?.id;
    if (same) {
      const tags = [...new Set([...same.tags, ...person.tags])];
      if (tags.length !== same.tags.length) await saveContact(same.id, { tags });
    } else {
      id = await saveContact(null, fields);
    }
    const had = now.interactions.filter((i) => i.contact_id === id);
    const fresh = interactions.filter((i) => !had.some((h) => h.body === i.body && h.met_on === i.met_on));
    if (fresh.length) await check(supabase.from("contact_interaction").insert(fresh.map((i) => ({ ...i, contact_id: id }))));
  }
  const opps = p.opportunities.filter((o) => !now.opportunities.some((x) => x.name.toLowerCase() === o.name.toLowerCase()));
  if (opps.length) await check(supabase.from("opportunity").insert(opps));
  const orgs = p.organisations.filter((o) => !now.organisations.some((x) => x.name.toLowerCase() === o.toLowerCase()));
  if (orgs.length) await check(supabase.from("organisation").insert(orgs.map((name) => ({ name }))));
}
