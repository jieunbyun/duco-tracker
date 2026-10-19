// The planning horizon: how much of the next N months is already spoken for.
//
//   capacity   area target (time + email) × weeks_per_year, pro rata to the horizon
//   routine    time in non-project categories (meetings, supervision, email, misc),
//              projected at the pace of the last PACE_DAYS days
//   committed  for each live project in a project-kind category, its remaining
//              planned hours spread over time (see plan.ts — by milestone when
//              the plan comes from milestones); only the share inside counts
//   free       capacity − routine − committed (negative means over-committed)
import type { Area, HourRow, Project, Taxonomy } from "./data";
import { targetOn } from "./data";
import { addDays, daysIn, today } from "./dates";
import type { Range } from "./dates";
import type { ProjectLoad } from "./plan";

// The project plan lives in plan.ts; re-exported for the views.
export { LIVE_STATUSES, plannedOf, endOf, projectLoad } from "./plan";
export type { ProjectLoad } from "./plan";

export const PLANNABLE_KINDS = new Set(["project", "mixed"]);
export const PACE_DAYS = 56;

export function horizonRange(months: number, from = today()): Range {
  const [y, m, d] = from.split("-").map(Number);
  const end = new Date(y, m - 1 + months, d);
  const iso = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
  return { from, to: addDays(iso, -1) };
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
