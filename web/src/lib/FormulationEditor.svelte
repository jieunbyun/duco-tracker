<script lang="ts">
  // Problem formulation: a debate as its views side by side — each with its objectives and
  // underlying assumptions — the conflicts between objectives, and the data that would
  // validate them. Edited as one draft; Save keeps it (one undo).
  import { emptyFormulation, newId } from "./practice";
  import type { Formulation, View } from "./practice";

  let { formulation, onsave, onclose }: {
    formulation: Formulation | null;
    onsave: (f: Formulation) => Promise<boolean>;
    onclose: () => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  const start = formulation ?? emptyFormulation();
  let saved = $state(JSON.stringify(start));
  let f = $state<Formulation>(structuredClone(start));
  let saving = $state(false);
  const dirty = $derived(JSON.stringify(f) !== saved);

  // every objective and assumption, with the view it belongs to, for the pickers
  const viewName = (v: View, i: number) => v.name.trim() || `View ${i + 1}`;
  const objectives = $derived(f.views.flatMap((v, i) => v.objectives.map((o) => ({ ...o, view: viewName(v, i) }))));
  const claims = $derived(f.views.flatMap((v, i) => [
    ...v.objectives.map((o) => ({ id: o.id, text: o.text, view: viewName(v, i), kind: "objective" as const })),
    ...v.assumptions.map((a) => ({ id: a.id, text: a.text, view: viewName(v, i), kind: "assumption" as const })),
  ]));
  const backed = $derived(new Set(f.data.flatMap((d) => d.tests)));
  const unbacked = $derived(claims.filter((c) => c.text.trim() && !backed.has(c.id)));
  const short = (s: string, n = 48) => (s.length > n ? `${s.slice(0, n - 1)}…` : s || "(blank)");

  function addView() {
    f.views.push({ id: newId(), name: "", objectives: [], assumptions: [] });
  }
  function removeView(i: number) {
    const v = f.views[i];
    const n = v.objectives.length + v.assumptions.length;
    if (n && !confirm(`Remove “${viewName(v, i)}” and its ${n} ${n === 1 ? "entry" : "entries"}?`)) return;
    for (const x of [...v.objectives, ...v.assumptions]) forget(x.id);
    f.views.splice(i, 1);
  }
  /** An objective or assumption gone: out of the conflicts and the data's links too. */
  function forget(id: string) {
    for (const c of f.conflicts) {
      if (c.a === id) c.a = null;
      if (c.b === id) c.b = null;
    }
    for (const d of f.data) d.tests = d.tests.filter((t) => t !== id);
  }
  function removeFrom<T extends { id: string }>(list: T[], i: number) {
    forget(list[i].id);
    list.splice(i, 1);
  }
  function toggleTest(d: Formulation["data"][number], id: string) {
    d.tests = d.tests.includes(id) ? d.tests.filter((t) => t !== id) : [...d.tests, id];
  }

  async function save() {
    saving = true;
    try {
      const snap = $state.snapshot(f) as Formulation;
      if (await onsave(snap)) saved = JSON.stringify(snap);
    } finally {
      saving = false;
    }
  }
  function close() {
    if (dirty && !confirm("Leave without saving the changes to this formulation?")) return;
    onclose();
  }
  function revert() {
    f = JSON.parse(saved);
  }
</script>

<div class="formulation">
  <div class="bar">
    <span class="eyebrow">Problem formulation</span>
    <span class="acts">
      {#if dirty}<span class="muted small">Unsaved changes</span>{/if}
      <button class="primary" disabled={!dirty || saving} onclick={save}>{saving ? "Saving…" : "Save"}</button>
      {#if dirty}<button onclick={revert}>Revert</button>{/if}
      <button onclick={close}>Close</button>
    </span>
  </div>

  <label class="question">The debate
    <textarea rows="2" bind:value={f.question} placeholder="e.g. How should water in the catchment be shared between farming, the river and the city?"></textarea>
  </label>

  <section>
    <h3>Views <span class="muted small">each with its own objectives and underlying assumptions</span></h3>
    <div class="views">
      {#each f.views as v, vi (v.id)}
        <div class="view">
          <div class="view-head">
            <input class="name" bind:value={v.name} placeholder={`View ${vi + 1}, e.g. Conservation`} aria-label="View name" />
            <button class="x" title="Remove this view" aria-label={`Remove ${viewName(v, vi)}`} onclick={() => removeView(vi)}>✕</button>
          </div>

          <h4>Objectives</h4>
          {#each v.objectives as o, oi (o.id)}
            <div class="entry">
              <div class="fields">
                <textarea rows="1" bind:value={o.text} placeholder="What this view wants, e.g. Keep minimum river flow" aria-label="Objective"></textarea>
                <input class="measure" bind:value={o.measure} placeholder="Measured by… (e.g. flow in m³/s, Aug–Sep)" aria-label="Measure" />
              </div>
              <button class="x" aria-label="Remove objective" onclick={() => removeFrom(v.objectives, oi)}>✕</button>
            </div>
          {/each}
          <button class="add" onclick={() => v.objectives.push({ id: newId(), text: "", measure: "" })}>+ Objective</button>

          <h4>Assumptions</h4>
          {#each v.assumptions as a, ai (a.id)}
            <div class="entry">
              <textarea rows="1" bind:value={a.text} placeholder="What this view takes for granted, e.g. Yields fall if irrigation is cut" aria-label="Assumption"></textarea>
              <button class="x" aria-label="Remove assumption" onclick={() => removeFrom(v.assumptions, ai)}>✕</button>
            </div>
          {/each}
          <button class="add" onclick={() => v.assumptions.push({ id: newId(), text: "" })}>+ Assumption</button>
        </div>
      {/each}
      <button class="add-view" onclick={addView}>+ View</button>
    </div>
  </section>

  <section>
    <h3>Conflicts <span class="muted small">two objectives that pull against each other, and why</span></h3>
    {#each f.conflicts as c, ci (c.id)}
      <div class="conflict">
        <select bind:value={c.a} aria-label="First objective">
          <option value={null}>Choose an objective…</option>
          {#each objectives as o (o.id)}<option value={o.id}>{o.view}: {short(o.text)}</option>{/each}
        </select>
        <span class="vs">vs</span>
        <select bind:value={c.b} aria-label="Second objective">
          <option value={null}>Choose an objective…</option>
          {#each objectives as o (o.id)}<option value={o.id}>{o.view}: {short(o.text)}</option>{/each}
        </select>
        <textarea rows="1" bind:value={c.why} placeholder="Why they conflict, e.g. the same water in late summer" aria-label="Why they conflict"></textarea>
        <button class="x" aria-label="Remove conflict" onclick={() => f.conflicts.splice(ci, 1)}>✕</button>
      </div>
    {/each}
    {#if objectives.length < 2}
      <p class="muted small">Add objectives to at least two views to set them against each other.</p>
    {:else}
      <button class="add" onclick={() => f.conflicts.push({ id: newId(), a: null, b: null, why: "" })}>+ Conflict</button>
    {/if}
  </section>

  <section>
    <h3>Data for validation <span class="muted small">and the objectives or assumptions each would test</span></h3>
    {#each f.data as d, di (d.id)}
      <div class="datum">
        <div class="datum-head">
          <input bind:value={d.name} placeholder="Dataset, e.g. Gauged daily river flow 2000–2024" aria-label="Dataset" />
          <input bind:value={d.source} placeholder="Source or link" aria-label="Source" />
          <button class="x" aria-label="Remove dataset" onclick={() => f.data.splice(di, 1)}>✕</button>
        </div>
        <textarea rows="1" bind:value={d.notes} placeholder="Notes: coverage, gaps, how it would be used" aria-label="Notes"></textarea>
        {#if claims.length}
          <div class="tests" role="group" aria-label="What it tests">
            <span class="muted small">Tests:</span>
            {#each claims as c (c.id)}
              <button class="chip" class:on={d.tests.includes(c.id)} aria-pressed={d.tests.includes(c.id)}
                      title={`${c.view} · ${c.kind}: ${c.text}`} onclick={() => toggleTest(d, c.id)}>
                <span class="kind">{c.kind === "objective" ? "O" : "A"}</span>{c.view}: {short(c.text, 32)}
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
    <button class="add" onclick={() => f.data.push({ id: newId(), name: "", source: "", notes: "", tests: [] })}>+ Dataset</button>

    {#if unbacked.length}
      <div class="unbacked">
        <span class="eyebrow">Not yet backed by data ({unbacked.length})</span>
        <ul>
          {#each unbacked as c (c.id)}<li><span class="kind">{c.kind === "objective" ? "O" : "A"}</span>{c.view}: {c.text}</li>{/each}
        </ul>
      </div>
    {/if}
  </section>
</div>

<style>
  .formulation { display: grid; gap: 1rem; padding: 0.9rem; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel); }
  .bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem;
         position: sticky; top: 3.4rem; z-index: 2; background: var(--panel); padding: 0.2rem 0; }
  .acts { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; }
  .acts button { font-size: 0.82rem; padding: 0.3rem 0.8rem; }
  .small { font-size: 0.78rem; }
  h3 { font-size: 1rem; margin: 0 0 0.5rem; }
  h3 .small { font-weight: 400; margin-left: 0.3rem; }
  h4 { font-family: var(--font-ui); font-size: 0.75rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-soft); margin: 0.6rem 0 0.3rem; font-weight: 600; }
  label.question { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  textarea { resize: vertical; field-sizing: content; min-height: 2.1rem; color: var(--ink); }
  .views { display: grid; grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); gap: 0.8rem; align-items: start; }
  .view { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.7rem; display: grid; gap: 0.35rem; }
  .view-head { display: flex; gap: 0.3rem; }
  .name { font-weight: 600; }
  .entry { display: flex; gap: 0.3rem; align-items: start; }
  .entry > textarea, .fields { flex: 1; min-width: 0; }
  .fields { display: grid; gap: 0.2rem; }
  .measure { font-size: 0.82rem; }
  .x { background: none; border: none; color: var(--ink-soft); padding: 0.3rem 0.4rem; line-height: 1; }
  .x:hover { color: var(--danger); }
  .add { justify-self: start; font-size: 0.8rem; padding: 0.2rem 0.6rem; background: none; }
  .add-view { min-height: 4rem; border-style: dashed; background: none; color: var(--ink-soft); }
  .conflict { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) minmax(0, 1.2fr) auto; gap: 0.4rem; align-items: start; margin-bottom: 0.4rem; }
  .vs { font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); align-self: center; }
  .datum { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.6rem; display: grid; gap: 0.35rem; margin-bottom: 0.5rem; }
  .datum-head { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) auto; gap: 0.3rem; }
  .tests { display: flex; flex-wrap: wrap; gap: 0.25rem; align-items: center; }
  .chip { font-size: 0.75rem; padding: 0.1rem 0.55rem; border-radius: 999px; background: none; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .kind { display: inline-block; font-family: var(--font-ui); font-size: 0.68rem; font-weight: 700; margin-right: 0.3rem; opacity: 0.75; }
  .unbacked { margin-top: 0.6rem; padding: 0.5rem 0.7rem; border-left: 3px solid var(--danger); background: var(--paper); border-radius: var(--radius); }
  .unbacked ul { margin: 0.3rem 0 0; padding-left: 1.1rem; font-size: 0.88rem; }
  @media (max-width: 40rem) {
    .conflict { grid-template-columns: minmax(0, 1fr) auto; }
    .conflict .vs { display: none; }
    .conflict select, .conflict textarea { grid-column: 1; }
    .conflict .x { grid-column: 2; grid-row: 1; }
    .datum-head { grid-template-columns: minmax(0, 1fr) auto; }
    .datum-head input:nth-child(2) { grid-column: 1; }
    .datum-head .x { grid-column: 2; grid-row: 1; }
  }
</style>
