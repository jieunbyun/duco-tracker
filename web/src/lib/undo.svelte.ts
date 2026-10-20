// One undo for every tab. Each write the app sends carries an "x-undo-group"
// header naming the action it belongs to; the database logs the rows each
// action changed (0013_undo.sql) and undo_group() plays them backwards.
//
// An action is either named (undoable(label, run): every write inside run) or
// inferred: writes less than a second apart belong together. Background writes
// (the calendar sync) go through quietly() and are neither logged nor undone.
// The list of actions lives for this session only.

type Action = { id: string; label: string };

export const undo = $state({
  actions: [] as Action[], // oldest first
  toast: null as string | null,
  version: 0, // bumped after an undo, so the open tab reloads
});

const MAX = 50;
const GAP_MS = 1000;
let open: { id: string; label: string | null; named: boolean; last: number } | null = null;
let quiet = 0;
let untaggable = false;
let toastTimer: ReturnType<typeof setTimeout> | undefined;

const NOUN: Record<string, string> = {
  area: "area", area_target: "targets", category: "category", user_setting: "settings", project: "project",
  milestone: "milestone", time_entry: "time entry", todo: "to-do", todo_slot: "plan", cv_entry: "CV entry",
  calendar_feed: "Outlook settings", calendar_ignore: "ignored event", reading: "reading", reading_note: "note",
  pw_node: "Pathways item", pw_link: "link", pw_revision: "goal wording", pw_asset: "asset",
};
function describe(method: string, table: string, prefer: string): string {
  const noun = NOUN[table] ?? table.replace(/_/g, " ");
  if (method === "DELETE") return `Deleted ${noun}`;
  if (method === "PATCH") return `Changed ${noun}`;
  return prefer.includes("resolution=") ? `Saved ${noun}` : `Added ${noun}`;
}

function groupForWrite() {
  const now = Date.now();
  if (!open || (!open.named && now - open.last > GAP_MS)) open = { id: crypto.randomUUID(), label: null, named: false, last: now };
  open.last = now;
  return open;
}
function record(id: string, label: string) {
  if (undo.actions.some((a) => a.id === id)) return;
  undo.actions = [...undo.actions.slice(-(MAX - 1)), { id, label }];
}

/** The fetch the Supabase client uses: tags each write with its action. */
export async function undoFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
  const method = (init?.method ?? "GET").toUpperCase();
  const m = url.pathname.match(/\/rest\/v1\/([A-Za-z_]+)$/);
  if (!m || method === "GET" || method === "HEAD" || quiet > 0 || untaggable) return fetch(input, init);
  const g = groupForWrite();
  const headers = new Headers(init?.headers);
  headers.set("x-undo-group", g.id);
  let res: Response;
  try {
    res = await fetch(input, { ...init, headers });
  } catch (e) {
    // should the server ever refuse the header, saving matters more than undo
    if (!(e instanceof TypeError)) throw e;
    untaggable = true;
    return fetch(input, init);
  }
  if (res.ok) record(g.id, g.label ?? describe(method, m[1], headers.get("Prefer") ?? ""));
  return res;
}

/** Run an action whose writes undo together, under a name. */
export async function undoable<T>(label: string, run: () => Promise<T>): Promise<T> {
  const mine = { id: crypto.randomUUID(), label, named: true, last: Date.now() };
  open = mine;
  try {
    return await run();
  } finally {
    if (open === mine) open = null;
  }
}

/** Name the latest action, after the fact. */
export function nameLast(label: string) {
  const last = undo.actions[undo.actions.length - 1];
  if (last) undo.actions = [...undo.actions.slice(0, -1), { ...last, label }];
}

/** Writes that are not the user's doing, such as a calendar sync. */
export async function quietly<T>(run: () => Promise<T>): Promise<T> {
  quiet++;
  try {
    return await run();
  } finally {
    quiet--;
  }
}

function showToast(text: string) {
  undo.toast = text;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (undo.toast = null), 6000);
}

let busy = false;
/** Undo the latest action, then reload the open tab. */
export async function undoLast(): Promise<void> {
  const a = undo.actions[undo.actions.length - 1];
  if (!a || busy) return;
  busy = true;
  try {
    const { supabase } = await import("./supabase");
    const { data, error } = await quietly(async () => supabase.rpc("undo_group", { g: a.id }));
    if (error) throw new Error(error.message);
    undo.actions = undo.actions.filter((x) => x.id !== a.id);
    showToast(data ? `Undone: ${a.label}` : `Nothing was recorded for “${a.label}”, so nothing changed`);
  } catch (e) {
    showToast(`Could not undo “${a.label}”: ${(e as Error).message}`);
  } finally {
    busy = false;
    undo.version++;
  }
}
