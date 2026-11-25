// Going from the Day tab to an entry, to change it there, and back again. The Day tab opens
// the entry's own tab with a "?…" that says which entry (#/reading?r=<reading>&n=<note>);
// while you are in that tab, a "Back to Day" button (App.svelte) takes you back to that day.

export const dayBack = $state({ tab: "", day: "" });

/** Open an entry in its own tab, from the Day tab showing `day`. */
export function openFromDay(day: string, hash: string) {
  dayBack.tab = hash.match(/^#\/(\w+)/)?.[1] ?? "";
  dayBack.day = day;
  location.hash = hash;
}

/** The "?…" a tab was opened with, taken off the address, so a reload starts afresh. */
export function arrivedAt(tab: string): URLSearchParams {
  const p = new URLSearchParams(location.hash.split("?")[1] ?? "");
  if (p.size) history.replaceState(null, "", `#/${tab}`);
  return p;
}
