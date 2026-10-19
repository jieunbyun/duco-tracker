// CV destinations and the LaTeX export, carried over from the old app so the
// output drops into the same CV source (jobshort / joblong environments).
import type { CvEntry } from "./data";

export const SUPERVISION = "Supervision";
export const CV_STATUSES = ["draft", "ready", "added_to_cv", "archived"] as const;

/** label → [section, subsection] */
export const DESTINATIONS: [string, string, string | null][] = [
  ["Impact — Software, Tools, and Datasets", "Impact", "Software, Tools, and Datasets"],
  ["Impact — Community & Stakeholder Engagement and Outreach", "Impact", "Community & Stakeholder Engagement and Outreach"],
  ["Impact — Knowledge Transfer and Capacity Building", "Impact", "Knowledge Transfer and Capacity Building"],
  ["Impact — Commercialisation", "Impact", "Commercialisation"],
  ["Impact — Policy and Practice Influence", "Impact", "Policy and Practice Influence"],
  ["Teaching — Courses", "Teaching", "Courses"],
  ["Leadership — University Leadership Roles", "Leadership, Management & Engagement", "University Leadership Roles"],
  ["Leadership — Conference Session Organisation", "Leadership, Management & Engagement", "Conference Session Organisation"],
  ["Leadership — Development of Team, Staff & Students", "Leadership, Management & Engagement", "Development of Team, Staff & Students"],
  ["Esteem — Honours and Awards", "Esteem", "Honours and Awards"],
  ["Esteem — Invited Talks & Keynotes", "Esteem", "Invited Talks & Keynotes"],
  ["Esteem — Editorial and Reviewing Roles", "Esteem", "Editorial and Reviewing Roles"],
  ["Esteem — Professional Service", "Esteem", "Professional Service to Learned Societies & Public Bodies"],
  ["Esteem — Media coverage", "Esteem", "Media coverage"],
  ["Esteem — Hosting", "Esteem", "Hosting"],
  ["Grants", "Grants", null],
  ["Grants — Submitted", "Grants - Submitted", null],
  [SUPERVISION, SUPERVISION, null],
  ["Publications", "Publications", null],
  ["Training", "Training", null],
  ["Admin — University", "Admin", "University"],
  ["Admin — External", "Admin", "External"],
  ["Other", "Other", null],
];

export function destinationParts(label: string): [string, string | null] {
  const d = DESTINATIONS.find(([l]) => l === label);
  return d ? [d[1], d[2]] : ["Other", null];
}

export function destinationLabel(section: string, subsection: string | null): string {
  return (
    DESTINATIONS.find(([, s, sub]) => s === section && sub === subsection)?.[0] ??
    DESTINATIONS.find(([, s]) => s === section)?.[0] ??
    "Other"
  );
}

export function texEscape(value: string | null | undefined): string {
  if (!value) return "";
  const map: Record<string, string> = {
    "\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", $: "\\$", "#": "\\#", _: "\\_",
    "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
  };
  return [...value].map((ch) => map[ch] ?? ch).join("");
}

// Fixed names: browsers disagree on "Sep" vs "Sept"; the CV wants "Sep".
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtMonth(iso: string | null): string {
  if (!iso) return "";
  const [y, m] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function supervisionDates(e: CvEntry): string {
  const start = fmtMonth(e.start_on);
  const end = fmtMonth(e.end_on);
  if (start && end) return `${start} - ${end}`;
  return start || end || e.entry_date || String(e.cv_year ?? "");
}

/** Student, degree, institution, country — joined, blanks skipped. */
export function supervisionTitle(e: CvEntry, escape = false): string {
  return [e.title, e.student_level, e.organisation, e.location]
    .map((p) => (p ?? "").trim())
    .filter(Boolean)
    .map((p) => (escape ? texEscape(p) : p))
    .join(", ");
}

/** "Second supervisor (20%): topic" */
export function supervisionBody(e: CvEntry, escape = false): string {
  const esc = escape ? texEscape : (x: string) => x;
  const role = (e.role ?? "").trim();
  const pct = (e.metrics ?? "").trim().replace(/%$/, "").trim();
  const topic = (e.description ?? "").trim();
  const pctPart = pct ? ` (${esc(pct)}${escape ? "\\%" : "%"})` : "";
  if (role && topic) return `${esc(role)}${pctPart}: ${esc(topic)}`;
  return role ? `${esc(role)}${pctPart}` : esc(topic);
}

export function entryLatex(e: CvEntry): string {
  if (e.cv_section === SUPERVISION) {
    return `\\begin{jobshort}{${supervisionTitle(e, true)}}{${texEscape(supervisionDates(e))}}\n${supervisionBody(e, true)}\n\\end{jobshort}`;
  }
  const title = texEscape(e.title);
  const date = texEscape(e.entry_date || String(e.cv_year ?? ""));
  const bullets: string[] = [];
  for (const v of [e.description, e.outcome, e.metrics]) {
    for (const line of (v ?? "").split("\n")) {
      const t = line.trim().replace(/^[-\s]+|[-\s]+$/g, "");
      if (t) bullets.push(texEscape(t));
    }
  }
  if (e.evidence_url) bullets.push(`Evidence: \\url{${texEscape(e.evidence_url)}}`);
  if (bullets.length <= 1) {
    return `\\begin{jobshort}{${title}}{${date}}\n${bullets[0] ?? ""}\n\\end{jobshort}`;
  }
  return [`\\begin{joblong}{${title}}{${date}}`, ...bullets.map((b) => `\\item ${b}`), "\\end{joblong}"].join("\n");
}

/** Grouped by section and subsection, as the CV source is laid out. */
export function entriesLatex(entries: CvEntry[]): string {
  const groups = new Map<string, CvEntry[]>();
  for (const e of entries) {
    const key = `${e.cv_section || "Other"}\u0000${e.cv_subsection ?? ""}`;
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  const chunks: string[] = [];
  let current: string | null = null;
  for (const key of [...groups.keys()].sort()) {
    const [sec, sub] = key.split("\u0000");
    const rows = groups.get(key)!;
    if (sec !== current) {
      chunks.push(`\\section{${texEscape(sec)}}`);
      current = sec;
    }
    if (sub) chunks.push(`\\subsection*{${texEscape(sub)}}`);
    if (sec === SUPERVISION) {
      chunks.push(rows.map(entryLatex).join("\n\\vspace{-10pt}\n"));
    } else {
      chunks.push(...rows.map(entryLatex));
    }
  }
  return chunks.join("\n\n");
}
