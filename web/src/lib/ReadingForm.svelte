<script lang="ts">
  import { untrack } from "svelte";
  import { KINDS, STATUSES, saveReading, deleteReading, lookupDoi } from "./reading";
  import type { Reading, ReadingFields } from "./reading";
  import type { Project } from "./data";
  import { LIVE_STATUSES } from "./plan";
  import { today } from "./dates";

  type Props = {
    reading: Reading | null; // null = new
    projects: Project[];
    onsaved: (id: string) => void;
    ondeleted?: () => void;
    oncancel: () => void;
  };
  let { reading, projects, onsaved, ondeleted, oncancel }: Props = $props();

  const r0 = untrack(() => reading);
  let f = $state({
    kind: r0?.kind ?? "article",
    title: r0?.title ?? "",
    authors: r0?.authors ?? "",
    year: r0?.year ?? (null as number | null),
    venue: r0?.venue ?? "",
    publisher: r0?.publisher ?? "",
    volume: r0?.volume ?? "",
    issue: r0?.issue ?? "",
    pages: r0?.pages ?? "",
    doi: r0?.doi ?? "",
    url: r0?.url ?? "",
    citation: r0?.citation ?? "",
    status: r0?.status ?? "reading",
    started_on: r0?.started_on ?? (r0 ? "" : today()),
    finished_on: r0?.finished_on ?? "",
    project_id: r0?.project_id ?? "",
  });
  let busy = $state(false);
  let looking = $state(false);
  let error = $state("");
  let note = $state("");

  const projectOptions = $derived(
    projects.filter((p) => LIVE_STATUSES.has(p.status) || p.id === r0?.project_id).sort((a, b) => a.name.localeCompare(b.name)),
  );
  const venueLabel = $derived(f.kind === "article" ? "Journal" : f.kind === "chapter" ? "Book title" : "Series / venue");

  // dates follow the status, unless you have set them
  function onStatus() {
    if (f.status === "reading" && !f.started_on) f.started_on = today();
    if (f.status === "finished" && !f.finished_on) f.finished_on = today();
  }

  async function fillFromDoi() {
    looking = true;
    error = "";
    note = "";
    try {
      const d = await lookupDoi(f.doi);
      f.kind = d.kind ?? f.kind;
      f.title = d.title || f.title;
      f.authors = d.authors ?? f.authors;
      f.year = d.year ?? f.year;
      f.venue = d.venue ?? "";
      f.publisher = d.publisher ?? "";
      f.volume = d.volume ?? "";
      f.issue = d.issue ?? "";
      f.pages = d.pages ?? "";
      f.doi = d.doi ?? f.doi;
      f.url = d.url ?? f.url;
      note = "Filled in from the DOI — check and save.";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      looking = false;
    }
  }

  const blank = (v: string) => v.trim() || null;

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!f.title.trim()) return (error = "Give it a title.");
    if (f.started_on && f.finished_on && f.finished_on < f.started_on) return (error = "It finishes before it starts.");
    busy = true;
    error = "";
    try {
      const fields: Partial<ReadingFields> = {
        kind: f.kind, title: f.title.trim(), authors: blank(f.authors),
        year: f.year === null || Number.isNaN(f.year) ? null : Math.round(f.year),
        venue: blank(f.venue), publisher: blank(f.publisher), volume: blank(f.volume), issue: blank(f.issue),
        pages: blank(f.pages), doi: blank(f.doi), url: blank(f.url), citation: blank(f.citation),
        status: f.status, started_on: f.started_on || null, finished_on: f.finished_on || null,
        project_id: f.project_id || null,
      };
      onsaved(await saveReading(r0?.id ?? null, fields));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!r0 || !confirm(`Delete “${r0.title}”, its notes${r0.pdf_path ? " and its PDF" : ""}?`)) return;
    busy = true;
    try {
      await deleteReading(r0);
      ondeleted?.();
    } catch (e) {
      error = (e as Error).message;
      busy = false;
    }
  }
</script>

<form class="rform" onsubmit={save}>
  <div class="doi wide">
    <label>DOI <input bind:value={f.doi} placeholder="10.1038/nature14539, or a doi.org link" /></label>
    <button type="button" onclick={fillFromDoi} disabled={looking || !f.doi.trim()}>{looking ? "Looking up…" : "Fill from DOI"}</button>
  </div>
  {#if note}<p class="ok wide">{note}</p>{/if}

  <label>Kind
    <select bind:value={f.kind}>{#each KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}</select>
  </label>
  <label class="span2">Title <input bind:value={f.title} required /></label>
  <label class="span2">Authors <input bind:value={f.authors} placeholder="Surname, Given; Surname, Given" /></label>
  <label>Year <input type="number" min="1000" max="2999" bind:value={f.year} /></label>
  <label class="span2">{venueLabel} <input bind:value={f.venue} /></label>
  <label>Publisher <input bind:value={f.publisher} /></label>
  {#if f.kind === "article"}
    <label>Volume <input bind:value={f.volume} /></label>
    <label>Issue <input bind:value={f.issue} /></label>
  {/if}
  <label>Pages <input bind:value={f.pages} placeholder="e.g. 436-444" /></label>
  <label class="span2">Link <input type="url" bind:value={f.url} placeholder="https://…" /></label>

  <label>Status
    <select bind:value={f.status} onchange={onStatus}>{#each STATUSES as s (s.key)}<option value={s.key}>{s.label}</option>{/each}</select>
  </label>
  <label>Started <input type="date" bind:value={f.started_on} /></label>
  <label>Finished <input type="date" bind:value={f.finished_on} min={f.started_on || undefined} /></label>
  <label class="span2">Project (optional)
    <select bind:value={f.project_id}>
      <option value="">— none —</option>
      {#each projectOptions as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
    </select>
  </label>
  <label class="wide">Your own citation (optional — used instead of the generated one)
    <textarea rows="2" bind:value={f.citation}></textarea>
  </label>

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{r0 ? "Save" : "Add"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if r0}<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>{/if}
  </div>
</form>

<style>
  .rform { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.65rem 1rem; font-family: var(--font-ui); }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .span2 { grid-column: span 2; }
  .doi { display: flex; gap: 0.5rem; align-items: end; }
  .doi label { flex: 1; }
  .ok { color: var(--accent); font-size: 0.82rem; margin: 0; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) {
    .rform { grid-template-columns: 1fr; }
    .span2 { grid-column: auto; }
  }
</style>
