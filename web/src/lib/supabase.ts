import { createClient } from "@supabase/supabase-js";
import { undoFetch } from "./undo.svelte";

// Keep only the origin: the dashboard's "API URL" ends in /rest/v1/, which
// supabase-js would append a second time ("Invalid path specified").
const rawUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const url = rawUrl ? new URL(rawUrl).origin : undefined;
const key = import.meta.env.VITE_SUPABASE_KEY as string | undefined;

if (!url || !key) {
  throw new Error(
    "Missing VITE_SUPABASE_URL / VITE_SUPABASE_KEY — copy web/.env.example to web/.env.local and fill it in.",
  );
}

/**
 * How this page was reached from an email link: "invite" (a new student) or
 * "recovery" (a password reset). Read before the client takes the link apart.
 */
export const arrival = new URLSearchParams(location.hash.replace(/^#/, "")).get("type");

// The browser talks to Supabase directly; row-level security (owner-only on
// every table) is what keeps the data private, not this client. Each write is
// tagged with the action it belongs to, for undo.
export const supabase = createClient(url, key, { global: { fetch: undoFetch } });
