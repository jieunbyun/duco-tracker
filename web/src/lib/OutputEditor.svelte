<script lang="ts">
  import { untrack } from "svelte";
  import { CATEGORIES, OUTPUT_STATUSES, saveOutput, deleteOutput, linkOutputs, unlinkOutputs } from "./assets";
  import type { Output, OutputLink, Category } from "./assets";
  import type { Member } from "./group";
  import { fromMonth, fmtMonth } from "./pathways";

  type Props = {
    output: Output | null; // null = new
    draftCategory?: Category;
    outputs: Output[];
    links: OutputLink[];
    members: Member[];
    publications: { id: string; title: string }[]; // items in Publications & code/database you can link to
    titles: Map<string, string>; // titles of publications already linked
    canEdit: (o: Output) => boolean;
    me?: string; // a new output starts with whoever adds it as a contributor
    onsaved: () => void;
    oncancel: () => void;
  };
  let { output, draftCategory = "other", outputs, links, members, publications, titles, canEdit, me = "", onsaved, oncancel }: Props = $props();

  const o0 = untrack(() => output);
  const editable = untrack(() => (o0 ? canEdit(o0) : true));
  let f = $state({
    name: o0?.name ?? "",
    category: (o0?.category ?? untrack(() => draftCategory)) as Category,
    status: o0?.status ?? "prototype",
    purpose: o0?.purpose ?? "",
    developed: (o0?.developed_on ?? new Date().toISOString().slice(0, 10)).slice(0, 7),
    location: o0?.location ?? "",
  });
  let contrib = $state<string[]>([...(o0?.contributors ?? untrack(() => members).filter((m) => m.user_id === me).map((m) => m.user_id))]);
  let pubs = $state<string[]>([...(o0?.publications ?? [])]);
  let busy = $state(false);
  let error = $state("");

  const nameOf = (uid: string) => members.find((m) => m.user_id === uid)?.display_name ?? "—";
  const outName = (id: string) => outputs.find((o) => o.id === id)?.name ?? "?";
  const titleOf = (id: string) => publications.find((p) => p.id === id)?.title ?? titles.get(id) ?? "(a publication)";
  const eligible = $derived(members.filter((m) => m.active || contrib.includes(m.user_id)));
  const pubOptions = $derived([
    ...publications,
    ...pubs.filter((id) => !publications.some((p) => p.id === id)).map((id) => ({ id, title: titleOf(id) })),
  ]);
  const outgoing = $derived(o0 ? links.filter((l) => l.from_id === o0.id) : []);
  const incoming = $derived(o0 ? links.filter((l) => l.to_id === o0.id) : []);

  async function save(ev: SubmitEvent) {
    ev.preventDefault();
    if (!f.name.trim()) return (error = "Give it a name.");
    busy = true;
    error = "";
    try {
      await saveOutput(o0?.id ?? null, {
        name: f.name.trim(), category: f.category, status: f.status as Output["status"], purpose: f.purpose.trim() || null,
        developed_on: fromMonth(f.developed, false, o0?.developed_on ?? null), location: f.location.trim() || null,
      }, contrib, pubs, o0);
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
  async function remove() {
    if (!o0 || !confirm(`Delete “${o0.name}” and its links?`)) return;
    try { await deleteOutput(o0.id); onsaved(); } catch (e) { error = (e as Error).message; }
  }
  let linkTo = $state("");
  async function connect() {
    if (!o0 || !linkTo) return;
    try { await linkOutputs(o0.id, linkTo); linkTo = ""; onsaved(); } catch (e) { error = (e as Error).message; }
  }
  async function disconnect(l: OutputLink) {
    try { await unlinkOutputs(l.id); onsaved(); } catch (e) { error = (e as Error).message; }
  }
</script>

{#if !editable && o0}
  <div class="ro">
    <p class="muted small">{CATEGORIES.find((c) => c.key === o0.category)?.label} · {o0.status}{o0.developed_on ? ` · ${fmtMonth(o0.developed_on)}` : ""}</p>
    {#if o0.purpose}<p>{o0.purpose}</p>{/if}
    <p class="small"><strong>Contributors:</strong> {o0.contributors.map(nameOf).join(", ") || "—"}</p>
    {#if o0.publications.length}<p class="small"><strong>Publications:</strong> {o0.publications.map(titleOf).join("; ")}</p>{/if}
    {#if o0.location}<p class="small"><a href={o0.location} target="_blank" rel="noopener noreferrer">↗ Data / code</a></p>{/if}
    {#if outgoing.length || incoming.length}
      <p class="small"><strong>Connected:</strong>
        {[...outgoing.map((l) => `→ ${outName(l.to_id)}`), ...incoming.map((l) => `← ${outName(l.from_id)}`)].join(" · ")}</p>
    {/if}
    <p class="muted small">Only whoever added it, its contributors and the group's lead can change it.</p>
    <div class="actions"><button type="button" onclick={oncancel}>Close</button></div>
  </div>
{:else}
  <form class="out-form" onsubmit={save}>
    <label class="span2">Name <input bind:value={f.name} required placeholder="e.g. Exact inference for Bayesian networks" /></label>
    <label>Category
      <select bind:value={f.category}>{#each CATEGORIES as c (c.key)}<option value={c.key}>{c.label}</option>{/each}</select>
    </label>
    <label class="wide">What it does <textarea rows="2" bind:value={f.purpose}></textarea></label>
    <label>Developed <input type="month" bind:value={f.developed} /></label>
    <label>Status <select bind:value={f.status}>{#each OUTPUT_STATUSES as s (s)}<option value={s}>{s}</option>{/each}</select></label>
    <label>Data / code (URL) <input bind:value={f.location} placeholder="https://…" /></label>

    {#if eligible.length}
      <fieldset class="wide pick">
        <legend>Contributors</legend>
        {#each eligible as m (m.user_id)}
          <label class="check"><input type="checkbox" value={m.user_id} bind:group={contrib} /> {m.display_name}</label>
        {/each}
      </fieldset>
    {/if}
    <fieldset class="wide pick">
      <legend>Publications (from Pathways › Publications &amp; code/database)</legend>
      {#each pubOptions as p (p.id)}
        <label class="check"><input type="checkbox" value={p.id} bind:group={pubs} /> {p.title}</label>
      {:else}<span class="muted small">None to link to yet.</span>{/each}
    </fieldset>

    {#if o0}
      <div class="wide conn">
        <h3>Connected to</h3>
        {#each outgoing as l (l.id)}
          <div class="row"><span>→ {outName(l.to_id)}</span><button type="button" class="x" aria-label="Remove link" onclick={() => disconnect(l)}>✕</button></div>
        {/each}
        {#each incoming as l (l.id)}
          {@const from = outputs.find((o) => o.id === l.from_id)}
          <div class="row"><span>← {outName(l.from_id)}</span>
            {#if from && canEdit(from)}<button type="button" class="x" aria-label="Remove link" onclick={() => disconnect(l)}>✕</button>{/if}</div>
        {/each}
        <div class="row">
          <span class="muted">this →</span>
          <select bind:value={linkTo} aria-label="Connect to">
            <option value="">choose an output…</option>
            {#each CATEGORIES as c (c.key)}
              <optgroup label={c.label}>
                {#each outputs.filter((x) => x.category === c.key && x.id !== o0.id && !outgoing.some((l) => l.to_id === x.id)) as x (x.id)}<option value={x.id}>{x.name}</option>{/each}
              </optgroup>
            {/each}
          </select>
          <button type="button" class="mini" disabled={!linkTo} onclick={connect}>Connect</button>
        </div>
      </div>
    {/if}

    {#if error}<p class="error wide">{error}</p>{/if}
    <div class="actions wide">
      <button class="primary" type="submit" disabled={busy}>{o0 ? "Save" : "Add output"}</button>
      <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
      {#if o0}<button type="button" class="danger" onclick={remove} disabled={busy}>Delete</button>{/if}
    </div>
  </form>
{/if}

<style>
  .out-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.65rem 1rem; font-family: var(--font-ui); }
  .out-form > label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .wide { grid-column: 1 / -1; }
  .span2 { grid-column: span 2; }
  .pick { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.4rem 0.7rem; }
  .pick legend { font-size: 0.8rem; color: var(--ink-soft); padding: 0 0.3rem; }
  .check { display: inline-flex; gap: 0.35rem; align-items: center; font-size: 0.85rem; }
  .check input { width: auto; }
  .conn h3 { font-size: 0.9rem; margin: 0 0 0.3rem; }
  .row { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; font-size: 0.85rem; padding: 0.1rem 0; }
  .row select { width: auto; font-size: 0.8rem; padding: 0.2rem 0.3rem; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.75rem; padding: 0 0.2rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  .actions { display: flex; gap: 0.5rem; }
  .danger { margin-left: auto; color: var(--danger); }
  .ro { font-family: var(--font-ui); }
  .small { font-size: 0.85rem; }
  @media (max-width: 40rem) { .out-form { grid-template-columns: 1fr; } .span2 { grid-column: auto; } }
</style>
