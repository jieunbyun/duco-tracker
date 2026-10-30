// The time a member gives their actions on shared projects (0047, 0048): the hours
// they project for one, and the hours they log on it. These are theirs alone: their
// supervisor sees only each project's share of the week, and other members nothing.
import { supabase } from "./supabase";
import { check } from "./data";

export type TimeLog = {
  id: string; action_id: string; worked_on: string;
  start_time: string | null; end_time: string | null; // "HH:MM:SS"; or just hours
  hours: number;
};
export type ActionTimes = { logs: TimeLog[]; plans: Map<string, number> };
export type TimeShare = { week: string; group_project_id: string; share: number }; // a whole percentage

/** Your own time on these actions — nothing until 0047 is run. */
export async function loadActionTimes(actionIds: string[]): Promise<ActionTimes> {
  const none: ActionTimes = { logs: [], plans: new Map() };
  if (!actionIds.length) return none;
  const [logs, plans] = await Promise.all([
    supabase.from("action_time").select("id,action_id,worked_on,start_time,end_time,hours").in("action_id", actionIds)
      .order("worked_on", { ascending: false }).order("created_at", { ascending: false }),
    supabase.from("action_plan").select("action_id,planned_hours").in("action_id", actionIds),
  ]);
  if (logs.error || plans.error) return none;
  return {
    logs: (logs.data as TimeLog[]).map((x) => ({ ...x, hours: Number(x.hours) })),
    plans: new Map((plans.data as { action_id: string; planned_hours: number }[]).map((x) => [x.action_id, Number(x.planned_hours)])),
  };
}

/** A member's weeks, newest first, each project's share of the time logged in it (for the supervisor). */
export async function loadTimeShares(userId: string): Promise<TimeShare[]> {
  const { data, error } = await supabase.rpc("member_time_shares", { p: userId });
  return error ? [] : ((data ?? []) as TimeShare[]);
}

/** Each project's share of a member's time over a period; null dates leave that end open. */
export async function loadPeriodShares(userId: string, from: string | null, to: string | null): Promise<Omit<TimeShare, "week">[]> {
  const { data, error } = await supabase.rpc("member_period_shares", { p: userId, d0: from, d1: to });
  return error ? [] : ((data ?? []) as Omit<TimeShare, "week">[]);
}

/** The hours projected for an action; null clears them. */
export async function saveActionPlan(actionId: string, hours: number | null): Promise<void> {
  await check(hours === null
    ? supabase.from("action_plan").delete().eq("action_id", actionId)
    : supabase.from("action_plan").upsert({ action_id: actionId, planned_hours: hours }));
}
export async function addTimeLog(fields: Omit<TimeLog, "id">): Promise<void> {
  await check(supabase.from("action_time").insert(fields));
}
export async function deleteTimeLog(id: string): Promise<void> {
  await check(supabase.from("action_time").delete().eq("id", id));
}

/** Hours between two "HH:MM" times, to the minute; 0 if the end is not after the start. */
export function hoursBetween(start: string, end: string): number {
  const mins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
  return Math.max(0, Math.round(((mins(end) - mins(start)) / 60) * 100) / 100);
}
