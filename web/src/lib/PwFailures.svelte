<script lang="ts">
  // The hypotheses (Failures) on a Pathways item's project, changed right there: add one, edit it,
  // tick it complete or delete it. Its observations and calibrations stay in Failures (›).
  import FailureForm from "./FailureForm.svelte";
  import { saveFailure, deleteFailure, isLate, toFailures, placeOf } from "./failures";
  import type { Board, Failure, Attachment, World } from "./failures";
  import type { Taxonomy } from "./data";
  import { undoable } from "./undo.svelte";
  import { fmtDay, today } from "./dates";

  type Props = {
    board: Board;
    items: Failure[]; // those on this item's project or its milestones
    attach: Attachment; // what a new one is put on
    world: World;
    tax: Taxonomy;
    milestoneOf?: (f: Failure) => string | undefined;
    onchange: () => void | Promise<void>;
  };
  let { board, items, attach, world, tax, milestoneOf, onchange }: Props = $props();

  let editing = $state<string | null>(null); // a hypothesis's id, "new", or "existing" (picking one)
  let busy = $state(false);
  let error = $state("");
  const open = $derived(items.filter((f) => !f.done_on));
  const done = $derived(items.filter((f) => f.done_on));
  const themeOf = (f: Failure) => board.themes.find((t) => t.id === f.theme_id)?.name ?? "";

  async function change(label: string, run: () => Promise<unknown>) {
    busy = true;
    error = "";
    try {
      await undoable(label, run);
      await onchange();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
  const setDone = (f: Failure, on: boolean) =>
    change(on ? "Completed a hypothesis" : "Reopened a hypothesis", () => saveFailure(f.id, { done_on: on ? today() : null }));
  function remove(f: Failure) {
    const short = f.hypothesis.length > 60 ? `${f.hypothesis.slice(0, 60)}…` : f.hypothesis;
    if (!confirm(`Delete the hypothesis “${short}”?`)) return;
    editing = null;
    change("Deleted hypothesis", () => deleteFailure(f.id));
  }
  // ---- an existing hypothesis, from anywhere in Failures, put on this item ----------------
  let find = $state("");
  const here = $derived(new Set(items.map((f) => f.id)));
  const whereNow = (f: Failure) => {
    const at = placeOf(f, world);
    return at.project?.name ?? at.group?.title ?? null;
  };
  /** The rest, by theme: ongoing first, then completed; narrowed by what is typed. */
  const candidates = $derived.by(() => {
    const q = find.trim().toLocaleLowerCase();
    const rest = board.items.filter((f) => !here.has(f.id)
      && (!q || `${f.hypothesis} ${f.test ?? ""} ${f.lesson ?? ""}`.toLocaleLowerCase().includes(q)));
    return board.themes.map((t) => ({
      theme: t,
      items: rest.filter((f) => f.theme_id === t.id).sort((a, b) => Number(!!a.done_on) - Number(!!b.done_on)),
    })).filter((g) => g.items.length);
  });
  function pick(f: Failure) {
    const from = whereNow(f);
    if (from && !confirm(`It is on “${from}” now. Move it here?`)) return;
    editing = null;
    find = "";
    change(from ? "Moved a hypothesis" : "Put a hypothesis on a project", () => saveFailure(f.id, attach));
  }

  async function saved() {
    editing = null;
    await onchange();
  }
</script>

{#snippet row(f: Failure)}
  {#if editing === f.id}
    <FailureForm failure={f} themes={board.themes} {world} {tax} onsaved={saved}
                 oncancel={() => (editing = null)} ondelete={() => remove(f)} />
  {:else}
    {@const ms = milestoneOf?.(f)}
    {@const late = isLate(f, today())}
    <li>
      <input type="checkbox" checked={!!f.done_on} disabled={busy || !!editing}
             title={f.done_on ? "Completed — untick to reopen" : "Mark it complete"}
             aria-label={`Completed: ${f.hypothesis}`} onchange={(e) => setDone(f, e.currentTarget.checked)} />
      <div class="what">
        <button type="button" class="hypothesis" class:done={!!f.done_on} disabled={!!editing}
                title="Edit it" onclick={() => (editing = f.id)}>{f.hypothesis}</button>
        <p class="meta">
          {themeOf(f)}{ms ? ` · ${ms}` : ""} · created {fmtDay(f.created_on)}
          {#if f.done_on}· completed {fmtDay(f.done_on)}
          {:else if f.due_on}· <span class:overdue={late}>deadline {fmtDay(f.due_on)}{late ? " ⚠ overdue" : ""}</span>{/if}
        </p>
        {#if f.lesson}<p class="lesson"><strong>Lesson:</strong> {f.lesson}</p>{/if}
      </div>
      <button type="button" class="mini" title="Its observations and calibrations, in Failures"
              onclick={() => toFailures("#/pathways", f.id)}>Failures ›</button>
    </li>
  {/if}
{/snippet}

<div class="pw-failures">
  <div class="head">
    <span class="muted">{open.length} ongoing{done.length ? ` · ${done.length} completed` : ""}</span>
    <span class="spacer"></span>
    <button type="button" class="mini" disabled={!!editing || !!board.error || !board.items.length}
            title="One already in Failures" onclick={() => (editing = "existing")}>+ Existing…</button>
    <button type="button" class="primary mini" disabled={!!editing || !!board.error} onclick={() => (editing = "new")}>+ Hypothesis</button>
  </div>
  {#if board.error}<p class="error">Could not load Failures: {board.error}</p>{/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if editing === "existing"}
    <div class="existing">
      <div class="find">
        <!-- svelte-ignore a11y_autofocus -->
        <input type="search" bind:value={find} placeholder="Find a hypothesis (its words, test or lesson)…" autofocus
               onkeydown={(ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); editing = null; } }} />
        <button type="button" class="mini" onclick={() => { editing = null; find = ""; }}>Cancel</button>
      </div>
      {#each candidates as g (g.theme.id)}
        <div class="theme">
          <h5>{g.theme.name}</h5>
          {#each g.items as f (f.id)}
            {@const from = whereNow(f)}
            <button type="button" class="cand" class:done={!!f.done_on} disabled={busy} onclick={() => pick(f)}>
              <span class="cand-text">{f.hypothesis}</span>
              <span class="meta">{from ? `on ${from}` : "on no project"}{f.done_on ? ` · completed ${fmtDay(f.done_on)}` : f.due_on ? ` · deadline ${fmtDay(f.due_on)}` : ""}</span>
            </button>
          {/each}
        </div>
      {:else}
        <p class="muted small">{find.trim() ? "None match." : "Every hypothesis is on it already."}</p>
      {/each}
    </div>
  {/if}
  {#if editing === "new"}
    <FailureForm failure={null} {attach} themes={board.themes} {world} {tax} onsaved={saved} oncancel={() => (editing = null)} />
  {/if}
  {#if open.length}
    <ul>{#each open as f (f.id)}{@render row(f)}{/each}</ul>
  {:else if editing !== "new"}
    <p class="muted small">No ongoing hypotheses on it.</p>
  {/if}
  {#if done.length}
    <details>
      <summary class="muted">Completed ({done.length})</summary>
      <ul>{#each done as f (f.id)}{@render row(f)}{/each}</ul>
    </details>
  {/if}
</div>

<style>
  .pw-failures { font-family: var(--font-ui); display: grid; gap: 0.4rem; }
  .head { display: flex; align-items: center; gap: 0.4rem; }
  .spacer { flex: 1; }
  .existing { background: var(--panel); padding: 0.6rem; display: grid; gap: 0.5rem; max-height: 22rem; overflow-y: auto; }
  .find { display: flex; gap: 0.4rem; align-items: center; position: sticky; top: -0.6rem; background: var(--panel); padding: 0.1rem 0; }
  .find input { flex: 1; }
  .theme h5 { margin: 0 0 0.2rem; font-size: 0.78rem; color: var(--ink-soft); font-weight: 600; }
  .cand {
    display: grid; gap: 0.1rem; width: 100%; text-align: left; background: var(--paper); border: 1px solid var(--rule);
    border-radius: 0; padding: 0.35rem 0.5rem; margin-bottom: 0.25rem; cursor: pointer;
  }
  .cand:hover { border-color: var(--ink-soft); }
  .cand-text { font-size: 0.84rem; color: var(--ink); white-space: pre-wrap; overflow-wrap: anywhere; }
  .cand.done .cand-text { text-decoration: line-through; color: var(--ink-soft); }
  .head .muted { font-size: 0.82rem; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: flex; gap: 0.5rem; align-items: flex-start; padding: 0.4rem 0; border-bottom: 1px solid var(--rule); }
  li input { width: auto; margin-top: 0.2rem; }
  .what { flex: 1; min-width: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .hypothesis {
    display: block; width: 100%; text-align: left; background: none; border: none; padding: 0;
    font-size: 0.86rem; color: var(--ink); white-space: pre-wrap; cursor: pointer;
  }
  .hypothesis:hover { text-decoration: underline; }
  .hypothesis.done { text-decoration: line-through; color: var(--ink-soft); }
  .meta { font-size: 0.74rem; color: var(--ink-soft); }
  .lesson { font-size: 0.78rem; color: var(--ink-soft); }
  .overdue, .error { color: var(--danger); }
  .error { font-size: 0.8rem; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; white-space: nowrap; }
  .small { font-size: 0.8rem; }
  details summary { cursor: pointer; font-size: 0.82rem; padding: 0.3rem 0; }
</style>
