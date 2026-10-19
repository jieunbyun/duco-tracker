<script lang="ts">
  import { untrack } from "svelte";
  import { saveCv, deleteCv } from "./data";
  import type { CvEntry, CvFields } from "./data";
  import { DESTINATIONS, SUPERVISION, CV_STATUSES, destinationLabel, destinationParts } from "./cv";
  import { today } from "./dates";

  type Props = {
    entry: CvEntry | null; // null = new entry
    preset?: Partial<CvFields>; // e.g. links when adding from a logged session
    onsaved: () => void;
    oncancel: () => void;
  };
  let { entry, preset, onsaved, oncancel }: Props = $props();

  const e0 = untrack(() => entry);
  const p0 = untrack(() => preset) ?? {};
  const src = { ...p0, ...(e0 ?? {}) } as Partial<CvEntry>;

  let destination = $state(src.cv_section ? destinationLabel(src.cv_section, src.cv_subsection ?? null) : DESTINATIONS[0][0]);
  let entry_date = $state(src.entry_date ?? today());
  let title = $state(src.title ?? "");
  let organisation = $state(src.organisation ?? "");
  let location = $state(src.location ?? "");
  let role = $state(src.role ?? "");
  let description = $state(src.description ?? "");
  let outcome = $state(src.outcome ?? "");
  let metrics = $state(src.metrics ?? "");
  let evidence_url = $state(src.evidence_url ?? "");
  let student_level = $state(src.student_level ?? "");
  let start_on = $state(src.start_on ?? "");
  let end_on = $state(src.end_on ?? "");
  let status = $state(src.status ?? "draft");
  let busy = $state(false);
  let error = $state("");

  const supervision = $derived(destination === SUPERVISION);
  const blank = (v: string) => v.trim() || null;

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!title.trim()) return (error = supervision ? "Enter the student's name." : "Give the entry a title.");
    const [cv_section, cv_subsection] = destinationParts(destination);
    const fields: Partial<CvFields> = {
      ...p0,
      cv_section,
      cv_subsection,
      entry_date: supervision ? start_on || entry_date : entry_date,
      title: title.trim(),
      organisation: blank(organisation),
      location: blank(location),
      role: blank(role),
      description: blank(description),
      metrics: blank(metrics),
      status,
      ...(supervision
        ? { student_level: blank(student_level), start_on: start_on || null, end_on: end_on || null }
        : { outcome: blank(outcome), evidence_url: blank(evidence_url) }),
    };
    if (!e0) fields.source_type = p0.source_type ?? "manual";
    busy = true;
    error = "";
    try {
      await saveCv(e0?.id ?? null, fields);
      onsaved();
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!e0 || !confirm(`Delete “${e0.title}”?`)) return;
    busy = true;
    try {
      await deleteCv(e0.id);
      onsaved();
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }
</script>

<form class="cv-form" onsubmit={save}>
  <label class="wide">
    CV destination
    <select bind:value={destination}>
      {#each DESTINATIONS as [label] (label)}<option value={label}>{label}</option>{/each}
    </select>
  </label>

  {#if supervision}
    <p class="hint wide muted">
      Renders as a <code>jobshort</code>: {"{"}student, level, institution, country{"}"}{"{"}start – end{"}"},
      then a “role (%): topic” line.
    </p>
    <label>Student name <input bind:value={title} placeholder="e.g. John Smith" /></label>
    <label>Degree / level <input bind:value={student_level} placeholder="e.g. PhD, MSc Research" /></label>
    <label>Institution <input bind:value={organisation} placeholder="e.g. Imperial College London" /></label>
    <label>Country <input bind:value={location} placeholder="e.g. United Kingdom" /></label>
    <label>Start <input type="date" bind:value={start_on} /></label>
    <label>End (expected) <input type="date" bind:value={end_on} /></label>
    <label>Supervisory role <input bind:value={role} placeholder="e.g. First / Second / Co- supervisor" /></label>
    <label>Percentage <input bind:value={metrics} placeholder="e.g. 20 — omit for co-/external" /></label>
    <label class="wide">Project topic <input bind:value={description} /></label>
  {:else}
    <label>Date <input type="date" bind:value={entry_date} required /></label>
    <label class="span2">Title <input bind:value={title} placeholder="e.g. Editorial Board Member, Structural Safety" /></label>
    <label>Organisation / funder / host <input bind:value={organisation} /></label>
    <label>Role <input bind:value={role} /></label>
    <label>Location <input bind:value={location} /></label>
    <label class="wide">Description / draft bullet(s) <textarea rows="3" bind:value={description}></textarea></label>
    <label class="wide">Outcome / significance <textarea rows="2" bind:value={outcome}></textarea></label>
    <label>Metrics <input bind:value={metrics} placeholder="e.g. c. 100 attendees, £10,000" /></label>
    <label class="span2">Evidence URL <input type="url" bind:value={evidence_url} /></label>
  {/if}

  <label>
    Status
    <select bind:value={status}>
      {#each CV_STATUSES as s (s)}<option value={s}>{s.replaceAll("_", " ")}</option>{/each}
    </select>
  </label>

  {#if error}<p class="error wide">{error}</p>{/if}
  <div class="actions wide">
    <button class="primary" type="submit" disabled={busy}>{e0 ? "Save changes" : "Save CV entry"}</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
    {#if e0}<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>{/if}
  </div>
</form>

<style>
  .cv-form {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.7rem 1rem;
    font-family: var(--font-ui);
  }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .span2 { grid-column: span 2; }
  .hint { font-size: 0.8rem; margin: 0; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  @media (max-width: 40rem) {
    .cv-form { grid-template-columns: 1fr; }
    .span2 { grid-column: auto; }
  }
</style>
