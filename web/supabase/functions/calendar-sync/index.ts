// calendar-sync — a Supabase Edge Function.
//
// Fetches YOUR published Outlook calendar (.ics) and hands it to the app,
// which does all the reading and saving itself. Needed only because browsers
// may not read Outlook's link directly.
//
// It runs as the signed-in user: the link comes from that user's own
// calendar_feed row (row-level security applies), so it cannot be used to
// fetch any other address.
//
// Deploy: Supabase dashboard > Edge Functions > Deploy a new function >
// Via editor, name it "calendar-sync", paste this file, Deploy.
import { createClient } from "jsr:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function fail(message: string, status: number) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });

  // the project's public key (older projects call it the anon key)
  const key = Deno.env.get("SUPABASE_ANON_KEY") ?? Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ?? "";
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, key, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data, error } = await supabase.from("calendar_feed").select("ics_url").maybeSingle();
  if (error) return fail(error.message, 400);
  if (!data?.ics_url) return fail("No calendar link saved yet.", 400);

  const url = data.ics_url.trim().replace(/^webcal:/i, "https:");
  if (!/^https:\/\//i.test(url)) return fail("The calendar link must start with https://", 400);

  let res: Response;
  try {
    res = await fetch(url, { headers: { "User-Agent": "duco-tracker calendar sync" } });
  } catch (e) {
    return fail(`Could not reach the calendar: ${(e as Error).message}`, 502);
  }
  if (!res.ok) return fail(`The calendar link answered ${res.status}.`, 502);
  const text = await res.text();
  if (!text.includes("BEGIN:VCALENDAR")) return fail("That link did not return a calendar.", 502);

  return new Response(text, { headers: { ...cors, "Content-Type": "text/plain; charset=utf-8" } });
});
