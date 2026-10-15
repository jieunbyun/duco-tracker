<script lang="ts">
  import { loadTaxonomy, loadProjects, loadRecentEntries, loadEntryHours, fmtHours } from "../lib/data";
  import type { Taxonomy, Project, TimeEntry, TimeEntryFields } from "../lib/data";
  import { today, weekStart, parse } from "../lib/dates";
  import EntryForm from "../lib/EntryForm.svelte";

  const LAST_CATEGORY = "log.category";

  let tax = $state<Taxonomy | null>(null);
  let projects = $state<Project[]>([]);
  let recent = $state<TimeEntry[]>([]);
  let limit = $state(20);
  let todayHours = $state(0);
  let weekHours = $state(0);
  let error = $state("");
  let editing = $state<string | null>(null);
  let formKey = $state(0); // bump to give the new-entry form fresh defaults
  let flash = $state("");

  async function refresh() {
    try {
      const t = today();
      const [p, r, w] = await Promise.all([loadProjects(), loadRecentEntries(limit), loadEntryHours(weekStart(t), t)]);
      projects = p;
      recent = r;
      weekHours = w.reduce((s, e) => s + e.hours, 0);
      todayHours = w.filter((e) => e.entry_date === t).reduce((s, e) => s + e.hours, 0);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    }
  }

  loadTaxonomy().then((t) => (tax = t)).catch((e) => (error = e.message));
  refresh();

  // ---- defaults for a new entry -------------------------------------------
  // Start where today's last entry ended (else 09:00); end at now, rounded to
  // the quarter hour, when that is later; otherwise an hour after the start.
  function lastCategory(): string {
    try { return localStorage.getItem(LAST_CATEGORY) ?? ""; } catch { return ""; }
  }
  const defaults = $derived.by(() => {
    const t = today();
    const endsToday = recent
      .map((e) => e.ended_at)
      .filter((x): x is string => !!x && x.slice(0, 10) === t)
      .sort();
    const start = endsToday.length ? endsToday[endsToday.length - 1].slice(11, 16) : "09:00";
    const now = new Date();
    const q = Math.round((now.getHours() * 60 + now.getMinutes()) / 15) * 15;
    const [sh, sm] = start.split(":").map(Number);
    const endMin = q > sh * 60 + sm ? q : Math.min(sh * 60 + sm + 60, 24 * 60);
    const end = endMin >= 24 * 60 ? "00:00" : `${String(Math.floor(endMin / 60)).padStart(2, "0")}:${String(endMin % 60).padStart(2, "0")}`;
    const saved = lastCategory();
    const categoryId = tax?.categories.some((c) => c.id === saved) ? saved : tax?.categories[0]?.id ?? "";
    return { date: t, start, end, categoryId };
  });

  async function logged(f: TimeEntryFields) {
    try { localStorage.setItem(LAST_CATEGORY, f.category_id); } catch {}
    flash = "Logged.";
    setTimeout(() => (flash = ""), 2500);
    await refresh();
    formKey += 1;
  }
  async function edited() {
    editing = null;
    await refresh();
  }
  async function more() {
    limit += 20;
    await refresh();
  }

  // ---- display ----------------------------------------------------------------
  const catById = $derived(new Map((tax?.categories ?? []).map((c) => [c.id, c])));
  const areaById = $derived(new Map((tax?.areas ?? []).map((a) => [a.id, a])));
  const projById = $derived(new Map(projects.map((p) => [p.id, p])));

  function placement(e: TimeEntry): string[] {
    const c = catById.get(e.category_id);
    const parts = [areaById.get(c?.area_id ?? "")?.label ?? "", c?.label ?? "?"];
    const p = e.project_id ? projById.get(e.project_id) : null;
    if (p) parts.push(p.name);
    const m = p && e.milestone_id ? p.milestone.find((x) => x.id === e.milestone_id) : null;
    if (m) parts.push(m.title);
    return parts;
  }

  function when(e: TimeEntry): string {
    const t = e.ended_at ? `${e.started_at.slice(11, 16)}–${e.ended_at.slice(11, 16)}` : `${e.started_at.slice(11, 16)}, ${e.manual_minutes} min`;
    return t;
  }

  // Recent entries grouped by day, newest first.
  const days = $derived.by(() => {
    const out: { day: string; label: string; total: number; entries: TimeEntry[] }[] = [];
    for (const e of recent) {
      const day = e.started_at.slice(0, 10);
      let g = out[out.length - 1];
      if (!g || g.day !== day) {
        g = { day, total: 0, entries: [],
              label: parse(day).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) };
        out.push(g);
      }
      g.entries.push(e);
      g.total += e.minutes / 60;
    }
    return out;
  });
</script>

<section class="log">
  <span class="eyebrow">Log</span>
  <h1>Log a session</h1>
  <p class="totals muted">
    Today <strong>{fmtHours(todayHours)}</strong> · This week <strong>{fmtHours(weekHours)}</strong>
  </p>

  {#if error}<p class="error">{error}</p>{/if}

  {#if tax}
    <div class="card">
      {#key formKey}
        <EntryForm entry={null} {tax} {projects} {defaults} onsaved={logged} />
      {/key}
      {#if flash}<p class="flash" role="status">{flash}</p>{/if}
    </div>

    <h2>Recent</h2>
    {#if !recent.length}
      <p class="muted">Nothing logged yet.</p>
    {/if}
    {#each days as g (g.day)}
      <div class="day">
        <div class="day-head"><span>{g.label}</span><span class="muted">{fmtHours(g.total)}</span></div>
        {#each g.entries as e (e.id)}
          {#if editing === e.id}
            <div class="card editing">
              <EntryForm entry={e} {tax} {projects} {defaults} onsaved={edited} oncancel={() => (editing = null)} />
            </div>
          {:else}
            {@const parts = placement(e)}
            <button class="row" onclick={() => (editing = e.id)}>
              <span class="time">{when(e)}</span>
              <span class="where">
                <span class="muted">{parts.slice(0, 2).join(" › ")}</span>{#if parts.length > 2} › {parts.slice(2).join(" › ")}{/if}
                {#if e.description}<span class="desc">{e.description}</span>{/if}
              </span>
              <span class="hours">{e.is_core ? "🎯 " : ""}{fmtHours(e.minutes / 60)}</span>
            </button>
          {/if}
        {/each}
      </div>
    {/each}
    {#if recent.length >= limit}<button class="more" onclick={more}>Show more</button>{/if}
  {/if}
</section>

<style>
  .totals { font-family: var(--font-ui); font-size: 0.9rem; margin: 0 0 1rem; }
  .card { background: var(--panel); border-radius: var(--radius); padding: 1rem; }
  .card.editing { margin: 0.3rem 0 0.6rem; }
  .flash { font-family: var(--font-ui); font-size: 0.85rem; margin: 0.6rem 0 0; color: var(--accent); }
  .log h2 { margin-top: 2rem; }

  .day { margin-bottom: 1rem; font-family: var(--font-ui); }
  .day-head {
    display: flex;
    justify-content: space-between;
    font-size: 0.82rem;
    font-weight: 600;
    border-bottom: 1px solid var(--rule);
    padding: 0.2rem 0.4rem;
  }
  .row {
    width: 100%;
    display: grid;
    grid-template-columns: 7.5rem 1fr auto;
    gap: 0.9rem;
    align-items: baseline;
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 0.45rem 0.4rem;
    font-size: 0.9rem;
  }
  .row:hover { background: var(--panel); }
  .time { font-variant-numeric: tabular-nums; color: var(--ink-soft); font-size: 0.85rem; }
  .desc { display: block; font-size: 0.8rem; color: var(--ink-soft); }
  .hours { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .more { font-size: 0.85rem; }
  @media (max-width: 40rem) {
    .row { grid-template-columns: 1fr auto; }
    .time { grid-column: 1 / -1; }
  }
</style>
