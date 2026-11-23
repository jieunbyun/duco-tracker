// Thoughts on a Pathways goal (0065_pw_thoughts.sql): dated notes, each still valid or no
// longer valid (when, and why) — all kept.
import { supabase } from "./supabase";
import { check } from "./data";

export type Thought = {
  id: string; node_id: string; noted_on: string; body: string; valid: boolean; invalid_on: string | null; why: string | null; created_at: string;
};
export type ThoughtFields = Omit<Thought, "id" | "created_at">;

/** A goal's thoughts, newest first; null until 0065 is run. */
export async function loadThoughts(nodeId: string): Promise<Thought[] | null> {
  const r = await supabase.from("pw_thought").select("id,node_id,noted_on,body,valid,invalid_on,why,created_at")
    .eq("node_id", nodeId).order("noted_on", { ascending: false }).order("created_at", { ascending: false });
  if (r.error) {
    if (r.error.code === "PGRST205" || r.error.code === "42P01") return null;
    throw new Error(r.error.message);
  }
  return r.data as Thought[];
}
export async function saveThought(id: string | null, fields: Partial<ThoughtFields>): Promise<void> {
  await check(id ? supabase.from("pw_thought").update(fields).eq("id", id) : supabase.from("pw_thought").insert(fields));
}
export async function deleteThought(id: string): Promise<void> {
  await check(supabase.from("pw_thought").delete().eq("id", id));
}
