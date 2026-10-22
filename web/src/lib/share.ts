// How a to-do's hours fall on the days it is planned on. Kept free of database
// code so it can be checked on its own.
//
// A logged day keeps what was logged. Every other day still to do — an "open"
// card, not logged and not cancelled — gets a share of what is left of the
// estimate: the estimate less everything logged so far. So the open days grow
// when a day comes in under its plan, shrink when one runs over, and follow the
// estimate when it is changed.
//
// The shares follow each open card's own planned hours, which act as weights:
// a day planned at 3 h takes three times the share of a 1 h day, and merging
// two cards (weights added) keeps that. A card without hours weighs as much as
// the average card that has some; when none has any, the days share evenly.

export type OpenCard = { id: string; planned_hours: number | null };

/**
 * Hours for each open card. Without an estimate there is nothing to share, and
 * each card keeps its own planned hours (null when it has none).
 */
export function shareRemaining(
  estimate: number | null,
  logged: number,
  open: OpenCard[],
): Map<string, number | null> {
  const out = new Map<string, number | null>();
  if (estimate === null || estimate === undefined) {
    for (const c of open) out.set(c.id, c.planned_hours);
    return out;
  }
  if (!open.length) return out;
  const left = Math.max(0, estimate - logged);
  const known = open.filter((c) => c.planned_hours !== null && c.planned_hours > 0);
  const avg = known.length ? known.reduce((s, c) => s + c.planned_hours!, 0) / known.length : 1;
  const weight = (c: OpenCard) => (c.planned_hours !== null && c.planned_hours > 0 ? c.planned_hours : avg);
  const total = open.reduce((s, c) => s + weight(c), 0);
  for (const c of open) out.set(c.id, (left * weight(c)) / total);
  return out;
}
