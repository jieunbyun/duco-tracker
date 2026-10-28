// Everything in the app, as one JSON file — to keep on OneDrive (Me/Backups).
// Each table you can read, every row, as stored. The Outlook calendar link is
// left out (it works like a password); the undo log, which lasts two days, too.
import { supabase } from "./supabase";

const TABLES = [
  "area", "category", "area_target", "user_setting",
  "project", "milestone", "time_entry", "todo", "todo_slot",
  "calendar_feed", "calendar_ignore", "cv_entry",
  "reading", "reading_note", "idea_note",
  "pw_node", "pw_link", "pw_revision", "pw_contributor",
  "pw_asset", "asset_contributor", "asset_publication", "asset_link",
  "group_member", "group_project", "group_project_member", "group_milestone",
  "logbook_entry", "logbook_revision", "logbook_comment",
];
const PAGE = 1000;

async function allRows(table: string): Promise<unknown[]> {
  const rows: unknown[] = [];
  // others' actions on shared projects can be read (0042), but are not yours to keep
  const me = table === "todo" ? (await supabase.auth.getSession()).data.session?.user.id : undefined;
  for (let from = 0; ; from += PAGE) {
    let q = supabase.from(table).select("*");
    if (me) q = q.eq("user_id", me);
    const { data, error } = await q.range(from, from + PAGE - 1);
    if (error) throw new Error(error.message);
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE) return rows;
  }
}

export type Backup = { app: string; exported_at: string; tables: Record<string, unknown[]>; missing: string[] };

/** Read everything; tables that do not exist yet (SQL not run) are listed as missing. */
export async function exportEverything(onProgress?: (done: number, total: number) => void): Promise<Backup> {
  const out: Backup = { app: "duco-tracker", exported_at: new Date().toISOString(), tables: {}, missing: [] };
  let done = 0;
  for (const t of TABLES) {
    try {
      let rows = await allRows(t);
      if (t === "calendar_feed") rows = rows.map((r) => ({ ...(r as object), ics_url: null }));
      out.tables[t] = rows;
    } catch {
      out.missing.push(t);
    }
    onProgress?.(++done, TABLES.length);
  }
  return out;
}

export function rowCount(b: Backup): number {
  return Object.values(b.tables).reduce((n, rows) => n + rows.length, 0);
}
