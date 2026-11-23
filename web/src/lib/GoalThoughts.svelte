<script lang="ts">
  // A goal's thoughts: dated notes, newest first. One that no longer holds is marked so —
  // when, and why — and kept, folded away under "No longer valid", to bring back if need be.
  // (This sits inside the goal's form: Enter here adds or saves a thought, never the goal.)
  import { loadThoughts, saveThought, deleteThought } from "./thoughts";
  import type { Thought } from "./thoughts";
  import { undoable } from "./undo.svelte";
  import { fmtDay, today } from "./dates";

  let { nodeId }: { nodeId: string } = $props();

  let thoughts = $state<Thought[]>([]);
  let missing = $state(false);
  let error = $state("");
  let busy = $state(false);
  let body = $state("");
  let editing = $state<{ id: string; noted_on: string; body: string } | null>(null);
  let retiring = $state<{ id: string; why: string } | null>(null); // marking one no longer valid
  let showOld = $state(false);

  async function load() {
    try {
      const t = await loadThoughts(nodeId);
      missing = t === null;
      thoughts = t ?? [];
    } catch (e) {
      error = (e as Error).message;
    }
  }
  // svelte-ignore state_referenced_locally
  load();

  const current = $derived(thoughts.filter((t) => t.valid));
  const old = $derived(thoughts.filter((t) => !t.valid).sort((a, b) => (b.invalid_on ?? "").localeCompare(a.invalid_on ?? "")));

  async function run(label: string, f: () => Promise<void>): Promise<boolean> {
    busy = true;
    error = "";
    try {
      await undoable(label, f);
      await load();
      return true;
    } catch (e) {
      error = (e as Error).message;
      return false;
    } finally {
      busy = false;
    }
  }
  const enter = (ev: KeyboardEvent, f: () => unknown) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); f(); }
    if (ev.key === "Escape") { ev.preventDefault(); editing = null; retiring = null; }
  };

  async function add() {
    const b = body.trim();
    if (!b) return;
    if (await run("Added a thought", () => saveThought(null, { node_id: nodeId, noted_on: today(), body: b }))) body = "";
  }
  async function keep() {
    const e = editing!;
    if (!e.body.trim()) return;
    if (await run("Changed a thought", () => saveThought(e.id, { body: e.body.trim(), noted_on: e.noted_on || today() }))) editing = null;
  }
  async function retire() {
    const r = retiring!;
    if (await run("Marked a thought no longer valid", () => saveThought(r.id, { valid: false, invalid_on: today(), why: r.why.trim() || null }))) {
      retiring = null;
    }
  }
  function revive(t: Thought) {
    run("Marked a thought valid again", () => saveThought(t.id, { valid: true, invalid_on: null, why: null }));
  }
  function remove(t: Thought) {
    if (!confirm("Delete this thought for good? (Marking it no longer valid keeps it.)")) return;
    run("Deleted a thought", () => deleteThought(t.id));
  }
</script>

<div class="thoughts">
  <span class="head">Thoughts <span class="muted small">— on this goal, as they come; mark one no longer valid to keep it apart</span></span>

  {#if missing}
    <p class="muted small">Thoughts need web/db/0065_pw_thoughts.sql run first, in the Supabase SQL editor.</p>
  {:else}
    <div class="add">
      <input bind:value={body} placeholder="A thought on this goal, then Enter" aria-label="New thought" disabled={busy}
             onkeydown={(ev) => enter(ev, add)} />
      <button type="button" class="mini" disabled={busy || !body.trim()} onclick={add}>Add</button>
    </div>

    <ul>
      {#each current as t (t.id)}
        <li>
          {#if editing?.id === t.id}
            <div class="edit">
              <input type="date" bind:value={editing.noted_on} aria-label="Date" />
              <input bind:value={editing.body} aria-label="Thought" onkeydown={(ev) => enter(ev, keep)} />
              <button type="button" class="mini" onclick={keep}>Save</button>
              <button type="button" class="mini" onclick={() => (editing = null)}>Cancel</button>
              <button type="button" class="mini danger" onclick={() => remove(t)}>Delete</button>
            </div>
          {:else if retiring?.id === t.id}
            <div class="edit">
              <span class="body">{t.body}</span>
              <input bind:value={retiring.why} placeholder="Why it no longer holds (optional), then Enter" aria-label="Why"
                     onkeydown={(ev) => enter(ev, retire)} />
              <button type="button" class="mini" onclick={retire}>No longer valid</button>
              <button type="button" class="mini" onclick={() => (retiring = null)}>Cancel</button>
            </div>
          {:else}
            <span class="date">{fmtDay(t.noted_on)}</span>
            <button type="button" class="body text" title="Click to reword" onclick={() => { retiring = null; editing = { id: t.id, noted_on: t.noted_on, body: t.body }; }}>{t.body}</button>
            <button type="button" class="mini" title="Keep it, apart, as no longer valid" onclick={() => { editing = null; retiring = { id: t.id, why: "" }; }}>No longer valid…</button>
          {/if}
        </li>
      {/each}
    </ul>
    {#if !current.length}<p class="muted small">No thoughts yet.</p>{/if}

    {#if old.length}
      <button type="button" class="fold" aria-expanded={showOld} onclick={() => (showOld = !showOld)}>
        {showOld ? "▾" : "▸"} No longer valid ({old.length})
      </button>
      {#if showOld}
        <ul class="old">
          {#each old as t (t.id)}
            <li>
              <span class="date">{fmtDay(t.noted_on)}</span>
              <span class="body"><s>{t.body}</s>
                <span class="muted small">— no longer valid{t.invalid_on ? ` since ${fmtDay(t.invalid_on)}` : ""}{t.why ? `: ${t.why}` : ""}</span></span>
              <span class="acts">
                <button type="button" class="mini" onclick={() => revive(t)}>Valid again</button>
                <button type="button" class="mini danger" onclick={() => remove(t)}>Delete</button>
              </span>
            </li>
          {/each}
        </ul>
      {/if}
    {/if}
  {/if}
  {#if error}<p class="error small">{error}</p>{/if}
</div>

<style>
  .thoughts { display: grid; gap: 0.4rem; border-top: 1px solid var(--rule); padding-top: 0.6rem; }
  .head { font-size: 0.85rem; font-weight: 600; color: var(--ink); }
  .head .small { font-weight: 400; }
  .small { font-size: 0.78rem; }
  .add, .edit { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
  .add input { flex: 1; min-width: 12rem; }
  .edit input:not([type="date"]) { flex: 1; min-width: 10rem; }
  .edit input[type="date"] { width: auto; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.15rem; }
  li { display: grid; grid-template-columns: 6.5rem minmax(0, 1fr) auto; gap: 0.5rem; align-items: baseline; padding: 0.2rem 0; border-bottom: 1px solid var(--rule); }
  li:has(.edit) { grid-template-columns: 1fr; }
  .date { font-size: 0.75rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; }
  .body { font-size: 0.9rem; color: var(--ink); overflow-wrap: anywhere; font-family: var(--font-body, inherit); }
  .text { text-align: left; background: none; border: none; padding: 0; cursor: pointer; }
  .text:hover { text-decoration: underline dotted; }
  .old .body s { color: var(--ink-soft); }
  .acts { display: flex; gap: 0.25rem; }
  .mini { font-size: 0.72rem; padding: 0.12rem 0.5rem; white-space: nowrap; }
  .danger { color: var(--danger); }
  .fold { justify-self: start; background: none; border: none; padding: 0.2rem 0; color: var(--ink-soft); font-size: 0.82rem; cursor: pointer; }
  @media (max-width: 40rem) {
    li { grid-template-columns: 1fr auto; }
    li .date { grid-column: 1 / -1; }
  }
</style>
