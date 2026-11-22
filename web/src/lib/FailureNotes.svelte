<script lang="ts">
  // A hypothesis's observations and calibrations: dated notes, newest first, added as
  // the work goes on (as an action's comments in the Logbook). Click one to reword it.
  import { saveNote, deleteNote } from "./failures";
  import type { Note, NoteKind } from "./failures";
  import { undoable } from "./undo.svelte";
  import { fmtDay, today } from "./dates";
  import Linked from "./Linked.svelte";

  type Props = { failureId: string; notes: Note[]; disabled?: boolean; onchanged: () => Promise<void> };
  let { failureId, notes, disabled = false, onchanged }: Props = $props();

  const KINDS: { key: NoteKind; label: string }[] = [
    { key: "observation", label: "Observation" },
    { key: "calibration", label: "Calibration" },
  ];
  const labelOf = (k: NoteKind) => KINDS.find((x) => x.key === k)?.label ?? k;

  let kind = $state<NoteKind>("observation");
  let noted_on = $state(today());
  let body = $state("");
  let editing = $state<string | null>(null);
  let draft = $state({ kind: "observation" as NoteKind, noted_on: "", body: "" });
  let busy = $state(false);
  let error = $state("");

  async function run(label: string, f: () => Promise<void>): Promise<boolean> {
    busy = true;
    error = "";
    try {
      await undoable(label, f);
      await onchanged();
      return true;
    } catch (e) {
      const m = (e as Error).message;
      error = m.includes("failure_note") ? "Notes need web/db/0054_failure_progress.sql run first." : m;
      return false;
    } finally {
      busy = false;
    }
  }
  async function add(ev?: Event) {
    ev?.preventDefault();
    if (!body.trim()) return;
    const k = kind;
    if (await run(`Added ${k}`, () => saveNote(null, { failure_id: failureId, kind: k, noted_on: noted_on || today(), body: body.trim() }))) {
      body = "";
    }
  }
  function open(n: Note) {
    editing = n.id;
    draft = { kind: n.kind, noted_on: n.noted_on, body: n.body };
  }
  async function save(n: Note) {
    if (!draft.body.trim()) return; // emptying a note is not deleting it
    const d = { kind: draft.kind, noted_on: draft.noted_on || n.noted_on, body: draft.body.trim() };
    if (d.kind === n.kind && d.noted_on === n.noted_on && d.body === n.body) return void (editing = null);
    if (await run(`Changed ${d.kind}`, () => saveNote(n.id, d))) editing = null;
  }
  function remove(n: Note) {
    if (confirm(`Delete this ${n.kind}?`)) run(`Deleted ${n.kind}`, () => deleteNote(n.id)).then((ok) => ok && (editing = null));
  }
  // Enter adds or saves; Shift+Enter for a new line; Escape leaves an edit as it was
  const keys = (ev: KeyboardEvent, go: () => void) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); go(); }
    if (ev.key === "Escape" && editing) editing = null;
  };
</script>

<div class="notes">
  <h4>Observations &amp; calibrations {#if notes.length}<span>({notes.length})</span>{/if}</h4>
  <form class="add" onsubmit={add}>
    <select bind:value={kind} aria-label="Kind" {disabled}>
      {#each KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
    </select>
    <input type="date" bind:value={noted_on} aria-label="Date" {disabled} />
    <textarea rows="1" bind:value={body} placeholder="What you saw or set — Enter adds it, Shift+Enter for a new line"
              aria-label="Note" onkeydown={(e) => keys(e, add)} disabled={disabled || busy}></textarea>
    <button type="submit" disabled={disabled || busy || !body.trim()}>Add</button>
  </form>
  {#if error}<p class="error">{error}</p>{/if}
  {#if notes.length}
    <ul>
      {#each notes as n (n.id)}
        <li class={n.kind}>
          {#if editing === n.id}
            <div class="edit">
              <select bind:value={draft.kind} aria-label="Kind">
                {#each KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
              </select>
              <input type="date" bind:value={draft.noted_on} aria-label="Date" />
              <textarea rows="2" bind:value={draft.body} aria-label="Note" onkeydown={(e) => keys(e, () => save(n))}></textarea>
              <div class="actions">
                <button type="button" class="primary" onclick={() => save(n)} disabled={busy || !draft.body.trim()}>Save</button>
                <button type="button" onclick={() => (editing = null)} disabled={busy}>Cancel</button>
                <button type="button" class="danger" onclick={() => remove(n)} disabled={busy}>Delete</button>
              </div>
            </div>
          {:else}
            <span class="when">{fmtDay(n.noted_on)}</span>
            <span class="kind">{labelOf(n.kind)}</span>
            <button type="button" class="body" title="Click to edit" onclick={() => open(n)} disabled={disabled || editing !== null}>
              <Linked text={n.body} />
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .notes { margin: 0.5rem 0 0.2rem 2.9rem; font-family: var(--font-ui); font-size: 0.85rem; }
  h4 { margin: 0 0 0.3rem; font-size: 0.82rem; font-weight: 600; }
  h4 span { font-weight: 400; color: var(--ink-soft); }
  .add, .edit { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: flex-start; }
  select, input { width: auto; padding: 0.2rem 0.35rem; font-size: 0.8rem; }
  textarea { flex: 1 1 16rem; min-width: 0; padding: 0.25rem 0.45rem; font-size: 0.85rem; field-sizing: content; resize: vertical; }
  button { font-size: 0.78rem; padding: 0.2rem 0.65rem; }
  ul { list-style: none; margin: 0.4rem 0 0; padding: 0; display: grid; gap: 0.15rem; }
  li { display: grid; grid-template-columns: 6.5rem 6.2rem minmax(0, 1fr); gap: 0.5rem; align-items: baseline; padding: 0.15rem 0; }
  li:has(.edit) { display: block; }
  .when { color: var(--ink-soft); font-size: 0.78rem; font-variant-numeric: tabular-nums; }
  .kind { font-size: 0.72rem; border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.45rem; justify-self: start; color: var(--ink-soft); }
  .calibration .kind { border-style: dashed; }
  .body {
    border: none; background: none; padding: 0; text-align: left; font-size: 0.85rem; color: var(--ink);
    white-space: pre-wrap; overflow-wrap: anywhere; cursor: text;
  }
  .body:hover:not(:disabled) { text-decoration: underline dotted var(--ink-soft); }
  .body:disabled { opacity: 1; cursor: default; }
  .actions { display: flex; gap: 0.35rem; flex-basis: 100%; }
  .danger { margin-left: auto; color: var(--danger); }
  .error { color: var(--danger); font-size: 0.8rem; margin: 0.3rem 0 0; }
  @media (max-width: 40rem) {
    .notes { margin-left: 0; }
    li { grid-template-columns: auto auto; }
    .body { grid-column: 1 / -1; }
  }
</style>
