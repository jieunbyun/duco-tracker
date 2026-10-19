// The planning horizon: how much of the next N months is already spoken for.
//
//   capacity   area target (time + email) × weeks_per_year, pro rata to the horizon
//   routine    time in non-project categories (meetings, supervision, email, misc),
//              projected at the pace of the last PACE_DAYS days
//   committed  for each live project in a project-kind category, its remaining
//              planned hours (planned − logged), spread evenly from today (or its
//              start) to its end date; only the share inside the horizon counts
//   free       capacity − routine − committed (negative means over-committed)
import type { Area, HourRow, Project, Taxonomy } from "./data";
import { targetOn } from "./data";
import { addDays, daysIn, today } from "./dates";
import type { Range } from "./dates";

export const PLANNABLE_KINDS = new Set(["project", "mixed"]);
export const LIVE_STATUSES = new Set(["planned", "active", "paused"]);
export const PACE_DAYS = 56;

export function horizonRange(months: number, from = today()): Range {
  const [y, m, d] = from.split("-").map(Number);
  const end = new Date(y, m - 1 + months, d);
  const iso = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
  return { from, to: addDays(iso, -1) };
}

export type ProjectLoad = {
  actual: number;
  remaining: number;     // planned − actual, never below 0
  inHorizon: number;     // the part of `remaining` that falls inside the horizon
  perWeek: number | null; // pace needed to finish by the end date
  flag: "no-plan" | "no-end" | "overdue" | "over-budget" | null;
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

export function projectLoad(p: Project, actual: number, horizon: Range): ProjectLoad {
  const base = { actual, remaining: 0, inHorizon: 0, perWeek: null };
  if (!LIVE_STATUSES.has(p.status)) return { ...base, flag: null };
  const planned = plannedOf(p).hours;
  if (planned === null) return { ...base, flag: "no-plan" };

  const remaining = Math.max(0, planned - actual);
  const over = actual > planned ? "over-budget" : null;
  const t = horizon.from;
  const from = p.start_on && p.start_on > t ? p.start_on : t;
  const end = endOf(p);

  if (!end) return { ...base, remaining, inHorizon: remaining, flag: over ?? "no-end" };
  if (end < t) return { ...base, remaining, inHorizon: remaining, flag: remaining > 0 ? "overdue" : over };

  const windowDays = daysIn({ from, to: end });
  const overlapTo = end < horizon.to ? end : horizon.to;
  const overlapDays = overlapTo >= from ? daysIn({ from, to: overlapTo }) : 0;
  return {
    actual,
    remaining,
    inHorizon: (remaining * overlapDays) / windowDays,
    perWeek: remaining > 0 ? remaining / (windowDays / 7) : null,
    flag: over,
  };
}

export type AreaHorizon = {
  area: Area;
  capacity: number;
  routine: number;
  committed: number;
  free: number;
  freePerWeek: number; // free hours per working week left in the horizon
};

export function areaHorizons(
  tax: Taxonomy,
  hours: HourRow[],
  projects: Project[],
  loads: Map<string, ProjectLoad>,
  horizon: Range,
): AreaHorizon[] {
  const days = daysIn(horizon);
  const workingWeeks = (days / 365) * tax.weeksPerYear;
  const paceFrom = addDays(horizon.from, -PACE_DAYS);
  const cats = new Map(tax.categories.map((c) => [c.id, c]));

  return tax.areas.map((area) => {
    const t = targetOn(tax.targets, area.id, horizon.from);
    const capacity = t ? (t.weekly_hours + t.email_weekly_hours) * workingWeeks : 0;

    const recent = hours.filter((h) =>
      h.area_id === area.id && !PLANNABLE_KINDS.has(h.category_kind) &&
      h.entry_date >= paceFrom && h.entry_date < horizon.from);
    const routine = (recent.reduce((s, h) => s + h.hours, 0) / PACE_DAYS) * days;

    const committed = projects
      .filter((p) => {
        const c = cats.get(p.category_id);
        return c?.area_id === area.id && PLANNABLE_KINDS.has(c.kind);
      })
      .reduce((s, p) => s + (loads.get(p.id)?.inHorizon ?? 0), 0);

    const free = capacity - routine - committed;
    return { area, capacity, routine, committed, free, freePerWeek: workingWeeks ? free / workingWeeks : 0 };
  });
}
