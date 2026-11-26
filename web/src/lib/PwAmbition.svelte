<script lang="ts">
  // An ambition at the side of Pathways (0081): a subtopic of your ambitions theme in Experiments.
  // Its title, whether it still stands (⊘ outdated, when it is done or let go), and its notes,
  // added here or in Experiments (›). A new one: just its title, put last among them.
  import { untrack } from "svelte";
  import { addTopic, saveTopic, deleteTopic, addNote, saveNote, TAG_LABEL } from "./experiments";
  import type { Topic, Note, Tag } from "./experiments";
  import { undoable } from "./undo.svelte";
  import { fmtDay } from "./dates";
  import Linked from "./Linked.svelte";

  type Props = {
    topic: Topic | null; // null: a new ambition
    theme: Topic;
    ambitions: Topic[]; // all of them, in your order
    notes: Note[]; // every note in Experiments
    serving: number; // how many activities serve it, ticked or through their links
    readonly?: boolean;
    onchange: () => void | Promise<void>;
    onclose: () => void;
  };
  let { topic, theme, ambitions, notes, serving, readonly = false, onchange, onclose }: Props = $props();

  const t0 = untrack(() => topic);
  let title = $state(t0?.title ?? "");
  let outdated = $state(t0?.outdated ?? false);
  let busy = $state(false);
  let error = $state("");
  const mine = $derived(topic ? notes.filter((n) => n.topic_id === topic.id) : []);
  const live = $derived(mine.filter((n) => !n.outdated).length);
  // a note here takes the ambition's tags, else the theme's (Innovation, to begin with)
  const noteTags = $derived<Tag[]>(topic?.tags.length ? topic.tags : theme.tags.length ? theme.tags : ["innovation"]);
  let noteText = $state("");

  async function change(label: string, run: () => Promise<unknown>): Promise<boolean> {
    busy = true;
    error = "";
    try {
      await undoable(label, run);
      await onchange();
      return true;
    } catch (e) {
      error = (e as Error).message;
      return false;
    } finally {
      busy = false;
    }
  }

  async function save(ev: SubmitEvent) {
    ev.preventDefault();
    const text = title.trim();
    if (!text) return (error = "Give it a title.");
    if (!t0) {
      const last = ambitions.length ? Math.max(...ambitions.map((a) => a.sort_order)) + 10 : 10;
      if (await change(`Added the ambition “${text}”`, () => addTopic(text, theme.id, [], last))) onclose();
      return;
    }
    if (text === t0.title && outdated === t0.outdated) return onclose();
    const label = text !== t0.title ? `Renamed the ambition “${t0.title}” to “${text}”`
      : `Marked the ambition “${text}” ${outdated ? "outdated" : "current"}`;
    if (await change(label, () => saveTopic(t0.id, { title: text, outdated }))) onclose();
  }

  async function addTo() {
    const body = noteText.trim();
    if (!topic || !body) return;
    const first = mine.length ? Math.min(...mine.map((n) => n.sort_order)) - 10 : 0;
    if (await change(`Added a note to “${topic.title}”`, () => addNote({ topic_id: topic.id, body, tags: noteTags, sort_order: first }))) {
      noteText = "";
    }
  }
  function flip(n: Note) {
    change(n.outdated ? "Marked a note current" : "Marked a note outdated", () => saveNote(n.id, { outdated: !n.outdated }));
  }

  async function remove() {
    if (!topic) return;
    const k = mine.length;
    if (!confirm(`Delete the ambition “${topic.title}”${k ? ` and its ${k} ${k === 1 ? "note" : "notes"}` : ""}? `
      + `What serves it loses its tick for it. (Undo brings it back.) To keep it as it was, mark it ⊘ outdated instead.`)) return;
    if (await change(`Deleted the ambition “${topic.title}”`, () => deleteTopic(topic.id))) onclose();
  }
</script>

<div class="pw-amb">
  <form class="amb-form" onsubmit={save}>
    <label class="wide">{t0 ? "The ambition" : "A new ambition"}
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={title} required readonly={readonly} autofocus={!t0}
             placeholder="e.g. A model of the whole plant that people use" />
    </label>
    {#if t0}
      <label class="check"><input type="checkbox" bind:checked={outdated} disabled={readonly} /> ⊘ Outdated: done, or let go (it stays, greyed, under <em>All</em>)</label>
    {:else}
      <p class="hint">A subtopic of “{theme.title}” in Experiments: it becomes a column in the Ambitions view, to tick what serves it, and its notes are kept there.</p>
    {/if}
    {#if error}<p class="error">{error}</p>{/if}
    {#if !readonly}
      <div class="row">
        {#if t0}<button type="button" class="danger" disabled={busy} onclick={remove}>Delete</button>{/if}
        <span class="spacer"></span>
        <button type="button" onclick={onclose}>Cancel</button>
        <button class="primary" disabled={busy || !title.trim()}>{t0 ? "Save" : "Add it"}</button>
      </div>
    {/if}
  </form>

  {#if topic}
    <div class="notes">
      <div class="notes-head">
        <h3>Notes</h3>
        <span class="muted small">{live} {live === 1 ? "note" : "notes"}{mine.length > live ? ` · ${mine.length - live} outdated` : ""} · {serving} {serving === 1 ? "activity serves" : "activities serve"} it</span>
        <span class="spacer"></span>
        <a class="mini-link" href={`#/experiments?t=${topic.id}`} title="Open it in Experiments, to reorder, retag or move its notes">Experiments ›</a>
      </div>
      {#if !readonly}
        <textarea rows="2" bind:value={noteText} disabled={busy}
                  placeholder={`A note on it — what achieving it looks like, a thought, a change of mind. Enter adds it (tagged ${noteTags.map((x) => TAG_LABEL[x]).join(", ")})`}
                  onkeydown={(ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); addTo(); } }}></textarea>
      {/if}
      {#if mine.length}
        <ul>
          {#each mine as n (n.id)}
            <li class:outdated={n.outdated}>
              <span class="when">{fmtDay(n.noted_on)}</span>
              <span class="body"><Linked text={n.body} /></span>
              {#if !readonly}
                <button type="button" class="out" class:on={n.outdated} disabled={busy} aria-pressed={n.outdated}
                        title={n.outdated ? "Outdated — click to mark it current again" : "Mark it outdated"}
                        aria-label={n.outdated ? "Outdated: mark it current" : "Mark it outdated"} onclick={() => flip(n)}>⊘</button>
              {/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted small">No notes yet.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .pw-amb { font-family: var(--font-ui); display: grid; gap: 1rem; }
  .amb-form { display: grid; gap: 0.6rem; }
  .amb-form label.wide { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .check { display: flex; gap: 0.4rem; align-items: center; font-size: 0.84rem; }
  .check input { width: auto; }
  .hint { font-size: 0.8rem; color: var(--ink-soft); margin: 0; }
  .row { display: flex; gap: 0.4rem; align-items: center; }
  .spacer { flex: 1; }
  .danger { color: var(--danger); }
  .error { color: var(--danger); font-size: 0.82rem; margin: 0; }
  .notes { display: grid; gap: 0.45rem; border-top: 1px solid var(--rule); padding-top: 0.7rem; }
  .notes-head { display: flex; flex-wrap: wrap; gap: 0.3rem 0.6rem; align-items: baseline; }
  .notes-head h3 { margin: 0; font-size: 0.95rem; }
  .small { font-size: 0.78rem; margin: 0; }
  .mini-link { font-size: 0.76rem; white-space: nowrap; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
  li { display: grid; grid-template-columns: auto 1fr auto; gap: 0 0.6rem; font-size: 0.85rem; align-items: start; }
  li .when { font-size: 0.72rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; padding-top: 0.12rem; white-space: nowrap; }
  li .body { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--ink); }
  li.outdated .body { color: var(--ink-soft); opacity: 0.75; }
  .out { padding: 0 0.3rem; border: none; background: none; color: var(--ink-soft); opacity: 0.4; font-size: 0.95rem; line-height: 1.3; }
  li:hover .out, .out:focus-visible { opacity: 0.8; }
  .out.on { opacity: 1; color: var(--danger); }
</style>
