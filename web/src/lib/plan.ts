// A project's plan and how its remaining hours fall over time. Kept free of
// database code so it can be checked on its own.
//
// Remaining hours are spread evenly over a window, from today (or the start,
// if later) to the end date; only the share inside the horizon is committed.
// When the plan comes from milestones, each milestone is spread over its own
// window — its start and due dates, falling back to the project's — so work
// due soon weighs on the near term.
import type { Project } from "./data";
import { daysIn } from "./dates";
import type { Range } from "./dates";

export const LIVE_STATUSES = new Set(["planned", "active", "paused"]);

export type Flag = "no-plan" | "no-end" | "overdue" | "over-budget" | null;

export type ProjectLoad = {
  actual: number;
  remaining: number; // hours still to do, never below 0
  inHorizon: number; // the part of `remaining` that falls inside the horizon
  perWeek: number | null; // pace needed to finish on time
  flag: Flag;
};

/**
 * A project's plan, from its milestones (dropped ones aside) when:
 *   - every milestone has planned hours — their sum overrides the project's own figure; or
 *   - the project has no figure of its own — the sum of those milestones that have hours.
 * Otherwise (own figure, and some milestones without hours) the project's figure stands.
 */
export function plannedOf(p: Project): { hours: number | null; fromMilestones: boolean; complete: boolean } {
  const ms = p.milestone.filter((m) => m.status !== "dropped");
  const withHours = ms.filter((m) => m.planned_hours !== null);
  const sum = withHours.reduce((s, m) => s + (m.planned_hours ?? 0), 0);
  const complete = ms.length > 0 && withHours.length === ms.length;
  if (complete || (p.planned_hours === null && withHours.length)) {
    return { hours: sum, fromMilestones: true, complete };
  }
  return { hours: p.planned_hours, fromMilestones: false, complete };
}

/** The project's end date, or failing that its latest milestone due date. */
export function endOf(p: Project): string | null {
  if (p.end_on) return p.end_on;
  const dues = p.milestone.filter((m) => m.status !== "dropped" && m.due_on).map((m) => m.due_on!).sort();
  return dues.length ? dues[dues.length - 1] : null;
}

/** Spread `remaining` hours from max(today, start) to `end`. */
function spread(remaining: number, start: string | null, end: string | null, horizon: Range) {
  if (remaining <= 0) return { inHorizon: 0, perWeek: 0, flag: null as Flag };
  if (!end) return { inHorizon: remaining, perWeek: 0, flag: "no-end" as Flag };
  const t = horizon.from;
  if (end < t) return { inHorizon: remaining, perWeek: 0, flag: "overdue" as Flag };
  let from = start && start > t ? start : t;
  if (from > end) from = end; // a start after the due date: due in a day
  const windowDays = daysIn({ from, to: end });
  const overlapTo = end < horizon.to ? end : horizon.to;
  const overlapDays = overlapTo >= from ? daysIn({ from, to: overlapTo }) : 0;
  return {
    inHorizon: (remaining * overlapDays) / windowDays,
    perWeek: remaining / (windowDays / 7),
    flag: null as Flag,
  };
}

export function projectLoad(
  p: Project,
  actual: number,
  horizon: Range,
  actualByMilestone: Map<string, number> = new Map(),
): ProjectLoad {
  const base = { actual, remaining: 0, inHorizon: 0, perWeek: null };
  if (!LIVE_STATUSES.has(p.status)) return { ...base, flag: null };
  const plan = plannedOf(p);
  if (plan.hours === null) return { ...base, flag: "no-plan" };
  const over: Flag = actual > plan.hours ? "over-budget" : null;

  if (!plan.fromMilestones) {
    const remaining = Math.max(0, plan.hours - actual);
    const s = spread(remaining, p.start_on, endOf(p), horizon);
    return {
      actual,
      remaining,
      inHorizon: s.inHorizon,
      perWeek: s.perWeek || null,
      flag: s.flag === "overdue" ? "overdue" : over ?? s.flag,
    };
  }

  // milestone by milestone, each over its own dates
  // the pace shown is for milestones already under way; if none are, all of them
  let remaining = 0, inHorizon = 0, perWeek = 0, paceNow = 0;
  let overdue = false, noEnd = false;
  for (const m of p.milestone) {
    if (m.status === "dropped" || m.status === "done" || m.planned_hours === null) continue;
    const left = Math.max(0, m.planned_hours - (actualByMilestone.get(m.id) ?? 0));
    const start = m.start_on ?? p.start_on;
    const s = spread(left, start, m.due_on ?? endOf(p), horizon);
    remaining += left;
    inHorizon += s.inHorizon;
    perWeek += s.perWeek;
    if (!start || start <= horizon.from) paceNow += s.perWeek;
    overdue ||= s.flag === "overdue";
    noEnd ||= s.flag === "no-end";
  }
  return {
    actual,
    remaining,
    inHorizon,
    perWeek: paceNow || perWeek || null,
    flag: overdue ? "overdue" : over ?? (noEnd ? "no-end" : null),
  };
}

// ---- a milestone's share of one week ------------------------------------------
export type MilestoneWeek = {
  due: string | null; // its due date, or the project's end
  remaining: number | null; // planned − logged; null when it has no planned hours
  suggested: number | null; // this week's share of `remaining`
  overdue: boolean;
  dueThisWeek: boolean;
};

/**
 * Whether a milestone is live in `week` (its dates overlap it, or it is overdue
 * and not done), and how many of its remaining hours fall in that week when
 * spread evenly from today (or its start) to its due date — the same rule as
 * the planning horizon. Null when the milestone is not live that week.
 */
export function milestoneWeek(
  p: Project,
  m: Project["milestone"][number],
  logged: number,
  week: Range,
  todayIso: string,
): MilestoneWeek | null {
  if (!LIVE_STATUSES.has(p.status) || m.status === "done" || m.status === "dropped") return null;
  const start = m.start_on ?? p.start_on;
  const due = m.due_on ?? endOf(p);
  const overdue = !!due && due < todayIso;
  if (!overdue) {
    if (start && start > week.to) return null; // not started by the end of the week
    if (due && due < week.from) return null; // over before the week begins
  }
  const remaining = m.planned_hours === null ? null : Math.max(0, m.planned_hours - logged);
  let suggested: number | null = null;
  if (remaining !== null && remaining > 0) {
    if (overdue) suggested = remaining;
    else if (due) {
      // spread from today (or the start) to the due date; this week's slice of that
      let from = start && start > todayIso ? start : todayIso;
      if (from > due) from = due;
      const lo = from > week.from ? from : week.from;
      const hi = due < week.to ? due : week.to;
      suggested = hi >= lo ? (remaining * daysIn({ from: lo, to: hi })) / daysIn({ from, to: due }) : 0;
    }
  }
  return {
    due,
    remaining,
    suggested: suggested === null ? null : Math.round(suggested * 2) / 2, // to the half hour
    overdue,
    dueThisWeek: !!due && due >= week.from && due <= week.to,
  };
}
