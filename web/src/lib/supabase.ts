import { createClient } from "@supabase/supabase-js";

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

// The browser talks to Supabase directly; row-level security (owner-only on
// every table) is what keeps the data private, not this client.
export const supabase = createClient(url, key);
