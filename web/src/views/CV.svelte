<script lang="ts">
  import { loadCv } from "../lib/data";
  import type { CvEntry } from "../lib/data";
  import { CV_STATUSES, SUPERVISION, entriesLatex, supervisionTitle, supervisionBody, supervisionDates } from "../lib/cv";
  import { fmtDay } from "../lib/dates";
  import CvForm from "../lib/CvForm.svelte";

  let entries = $state<CvEntry[]>([]);
  let loading = $state(true);
  let error = $state("");
  let adding = $state(false);
  let editing = $state<string | null>(null);
  let year = $state("all");
  let section = $state("all");
  let status = $state("all");
  let copied = $state(false);

  async function load() {
    try {
      entries = await loadCv();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  async function saved() {
    adding = false;
    editing = null;
    await load();
  }

  const yearOf = (e: CvEntry) => String(e.cv_year ?? e.entry_date.slice(0, 4));
  const years = $derived([...new Set(entries.map(yearOf))].sort().reverse());
  const sections = $derived([...new Set(entries.map((e) => e.cv_section || "Other"))].sort());

  const byYear = $derived(
    years.map((y) => {
      const rows = entries.filter((e) => yearOf(e) === y);
      const counts = new Map<string, number>();
      for (const e of rows) counts.set(e.cv_section || "Other", (counts.get(e.cv_section || "Other") ?? 0) + 1);
      return { year: y, total: rows.length, counts: [...counts.entries()].sort() };
    }),
  );

  const shown = $derived(
    entries.filter((e) =>
      (year === "all" || yearOf(e) === year) &&
      (section === "all" || (e.cv_section || "Other") === section) &&
      (status === "all" || e.status === status)),
  );
  const latex = $derived(entriesLatex(shown));

  async function copy() {
    try {
      await navigator.clipboard.writeText(latex);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }
</script>

<section class="cv">
  <span class="eyebrow">CV</span>
  <h1>CV records</h1>
  <p class="muted lede">Achievement records to polish into CV entries, with a LaTeX export for your CV source.</p>

  {#if adding}
    <div class="card"><CvForm entry={null} onsaved={saved} oncancel={() => (adding = false)} /></div>
  {:else}
    <button class="primary" onclick={() => { adding = true; editing = null; }}>+ CV entry</button>
  {/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if !entries.length}
    <p class="muted">No CV records yet.</p>
  {:else}
    <h2>By year</h2>
    <div class="years">
      {#each byYear as y (y.year)}
        <details class="year">
          <summary><strong>{y.year}</strong> <span class="muted">{y.total} {y.total === 1 ? "entry" : "entries"}</span></summary>
          <ul>
            {#each y.counts as [sec, n] (sec)}<li>{sec}: {n}</li>{/each}
          </ul>
        </details>
      {/each}
    </div>

    <h2>Review and export</h2>
    <div class="filters">
      <label>Year
        <select bind:value={year}>
          <option value="all">All</option>
          {#each years as y (y)}<option value={y}>{y}</option>{/each}
        </select>
      </label>
      <label>Section
        <select bind:value={section}>
          <option value="all">All</option>
          {#each sections as s (s)}<option value={s}>{s}</option>{/each}
        </select>
      </label>
      <label>Status
        <select bind:value={status}>
          <option value="all">All</option>
          {#each CV_STATUSES as s (s)}<option value={s}>{s.replaceAll("_", " ")}</option>{/each}
        </select>
      </label>
    </div>

    {#if !shown.length}
      <p class="muted">No entries match these filters.</p>
    {/if}
    <ul class="list">
      {#each shown as e (e.id)}
        <li>
          {#if editing === e.id}
            <div class="card"><CvForm entry={e} onsaved={saved} oncancel={() => (editing = null)} /></div>
          {:else}
            <button class="row" onclick={() => { editing = e.id; adding = false; }}>
              <span class="date muted">{fmtDay(e.entry_date)}</span>
              <span class="what">
                {#if e.cv_section === SUPERVISION}
                  <strong>{supervisionTitle(e)}</strong> <span class="muted">· {supervisionDates(e)}</span>
                  <span class="sub">{supervisionBody(e)}</span>
                {:else}
                  <strong>{e.title}</strong>
                  <span class="sub">{[e.role, e.organisation, e.location].filter(Boolean).join(" · ")}</span>
                {/if}
                <span class="sub muted">{e.cv_section}{e.cv_subsection ? ` › ${e.cv_subsection}` : ""}</span>
              </span>
              <span class="chip status-{e.status}">{e.status.replaceAll("_", " ")}</span>
            </button>
          {/if}
        </li>
      {/each}
    </ul>

    {#if shown.length}
      <div class="latex-head">
        <h2>LaTeX</h2>
        <button onclick={copy}>{copied ? "Copied" : "Copy"}</button>
      </div>
      <textarea class="latex" readonly rows="14" value={latex}></textarea>
    {/if}
  {/if}
</section>

<style>
  .lede { font-family: var(--font-ui); font-size: 0.9rem; margin: 0 0 1rem; }
  .cv h2 { margin-top: 2rem; }
  .card { background: var(--panel); border-radius: var(--radius); padding: 1rem; margin: 0.4rem 0; }
  .years { display: flex; flex-wrap: wrap; gap: 0.6rem; font-family: var(--font-ui); font-size: 0.9rem; }
  .year { background: var(--panel); border-radius: var(--radius); padding: 0.5rem 0.8rem; min-width: 10rem; }
  .year summary { cursor: pointer; }
  .year ul { margin: 0.4rem 0 0; padding-left: 1.1rem; font-size: 0.82rem; color: var(--ink-soft); }
  .filters { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.8rem; font-family: var(--font-ui); }
  .filters label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); min-width: 10rem; }
  .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
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
    padding: 0.55rem 0.4rem;
    font-size: 0.9rem;
  }
  .row:hover { background: var(--panel); }
  .date { font-size: 0.82rem; }
  .sub { display: block; font-size: 0.8rem; }
  .latex-head { display: flex; align-items: baseline; gap: 1rem; }
  .latex { font-family: ui-monospace, Consolas, monospace; font-size: 0.8rem; }
  @media (max-width: 40rem) {
    .row { grid-template-columns: 1fr auto; }
    .date { grid-column: 1 / -1; }
  }
</style>
