<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = {
    tag: null as string | null,
    query: "",
    closed: new Set<string>(), // umbrella topics folded shut
    opened: new Set<string>(), // subtopics opened (they start folded)
    tags: [] as string[], // what the last new note was tagged
  };
</script>

<script lang="ts">
  // Experiments: what were Tips, Failures, Practice and Diary, in one place, laid out
  // like the Logbook. Umbrella topics with subtopics, notes under either, each note
  // tagged and in your own order (drag ⠿), ticked off when it is outdated.
  import { tick } from "svelte";
  import {
    TAGS, TAG_LABEL, loadExperiments, addTopic, saveTopic, deleteTopic, addNote, saveNote, deleteNote, placesOf, matches,
    experimentsMarkdown,
  } from "../lib/experiments";
  import type { Tag, Topic, Note } from "../lib/experiments";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay } from "../lib/dates";
  import { download } from "../lib/group";
  import Sortable from "../lib/Sortable.svelte";
  import Linked from "../lib/Linked.svelte";

  let topics = $state<Topic[]>([]);
  let notes = $state<Note[]>([]);
  let loading = $state(true);
  let error = $state("");
  let missing = $state(false); // the SQL has not been run yet

  let tag = $state<Tag | null>(last.tag as Tag | null);
  let query = $state(last.query);
  let closed = $state(new Set(last.closed));
  let opened = $state(new Set(last.opened));
  $effect(() => {
    Object.assign(last, { tag, query, closed, opened });
  });

  // what is being written: a new topic (under a parent, or none), a new note, a rename, a note's edit
  type Editing =
    | { kind: "topic"; parent: string | null }
    | { kind: "rename"; id: string }
    | { kind: "note"; topic: string }
    | { kind: "edit"; id: string };
  let editing = $state<Editing | null>(null);
  let draft = $state(""); // the title or the note's text
  let draftTags = $state<Tag[]>([]);
  let draftTopic = $state(""); // where an edited note goes
  let saving = $state(false);

  async function load() {
    try {
      ({ topics, notes } = await loadExperiments());
      error = "";
      missing = false;
    } catch (e) {
      const msg = (e as Error).message;
      if (/exp_topic|exp_note/.test(msg) && /exist|schema cache/i.test(msg)) missing = true;
      else error = msg;
    } finally {
      loading = false;
    }
  }
  load();

  async function change(label: string, run: () => Promise<unknown>) {
    saving = true;
    try {
      await undoable(label, run);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      saving = false;
      await load();
    }
  }

  // ---- what shows ---------------------------------------------------------------
  const filtering = $derived(!!tag || !!query.trim());
  const umbrellas = $derived(topics.filter((t) => !t.parent_id));
  const subsOf = (t: Topic) => topics.filter((s) => s.parent_id === t.id);
  const allNotesOf = (t: Topic) => notes.filter((n) => n.topic_id === t.id);
  const titleOf = (id: string | null) => topics.find((t) => t.id === id)?.title ?? "";
  const shows = (n: Note, t: Topic) =>
    (!tag || n.tags.includes(tag)) && (!query.trim() || matches(`${n.body}\n${t.title}\n${titleOf(t.parent_id)}`, query));
  const notesOf = (t: Topic) => (filtering ? allNotesOf(t).filter((n) => shows(n, t)) : allNotesOf(t));
  // filtering, a topic shows when anything under it does (or its own title matches the words)
  const topicShows = (t: Topic): boolean =>
    !filtering || notesOf(t).length > 0 || subsOf(t).some(topicShows)
    || (!tag && matches(`${t.title}\n${titleOf(t.parent_id)}`, query));
  const shownUmbrellas = $derived(umbrellas.filter(topicShows));
  const isOpen = (t: Topic) => filtering || (t.parent_id ? opened.has(t.id) : !closed.has(t.id));
  function fold(t: Topic) {
    const s = new Set(t.parent_id ? opened : closed);
    if (s.has(t.id)) s.delete(t.id);
    else s.add(t.id);
    if (t.parent_id) opened = s;
    else closed = s;
  }
  const countOf = (t: Topic) => {
    const every = [...allNotesOf(t), ...subsOf(t).flatMap(allNotesOf)];
    const old = every.filter((n) => n.outdated).length;
    return `${every.length} ${every.length === 1 ? "note" : "notes"}${old ? ` · ${old} outdated` : ""}`;
  };
  const shownCount = $derived(filtering ? topics.reduce((a, t) => a + notesOf(t).length, 0) : notes.length);

  // ---- writing --------------------------------------------------------------------
  async function focusDraft() {
    await tick();
    document.querySelector<HTMLElement>(".draft")?.focus();
  }
  function startTopic(parent: string | null) {
    editing = { kind: "topic", parent };
    draft = "";
    if (parent) { const c = new Set(closed); c.delete(parent); closed = c; }
    focusDraft();
  }
  function startRename(t: Topic) {
    editing = { kind: "rename", id: t.id };
    draft = t.title;
    focusDraft();
  }
  function startNote(t: Topic) {
    editing = { kind: "note", topic: t.id };
    draft = "";
    // tagged as the filter, else as the topic's last note, else as your last new note
    const prev = allNotesOf(t).at(-1);
    draftTags = tag ? [tag] : prev ? [...prev.tags] : (last.tags as Tag[]).filter((x) => TAGS.includes(x));
    if (t.parent_id) { const o = new Set(opened); o.add(t.id); opened = o; }
    else { const c = new Set(closed); c.delete(t.id); closed = c; }
    focusDraft();
  }
  function startEdit(n: Note) {
    editing = { kind: "edit", id: n.id };
    draft = n.body;
    draftTags = [...n.tags];
    draftTopic = n.topic_id;
    focusDraft();
  }
  function cancel() {
    editing = null;
  }
  function toggleTag(t: Tag) {
    draftTags = draftTags.includes(t) ? draftTags.filter((x) => x !== t) : TAGS.filter((x) => x === t || draftTags.includes(x));
  }
  const nextOrder = (rows: { sort_order: number }[]) => Math.max(0, ...rows.map((r) => r.sort_order)) + 10;

  async function submit(ev?: Event) {
    ev?.preventDefault();
    const e = editing;
    const text = draft.trim();
    if (!e || !text || saving) return;
    if ((e.kind === "note" || e.kind === "edit") && !draftTags.length) return void (error = "Give the note at least one tag.");
    editing = null;
    if (e.kind === "topic") {
      const siblings = topics.filter((t) => t.parent_id === e.parent);
      await change(e.parent ? `Added subtopic “${text}”` : `Added topic “${text}”`, () => addTopic(text, e.parent, nextOrder(siblings)));
    } else if (e.kind === "rename") {
      await change(`Renamed “${titleOf(e.id)}” to “${text}”`, () => saveTopic(e.id, { title: text }));
    } else if (e.kind === "note") {
      last.tags = [...draftTags];
      const t = topics.find((x) => x.id === e.topic)!;
      await change(`Added a note to “${t.title}”`, () =>
        addNote({ topic_id: t.id, body: text, tags: draftTags, sort_order: nextOrder(allNotesOf(t)) }));
    } else {
      const n = notes.find((x) => x.id === e.id)!;
      const moved = draftTopic !== n.topic_id;
      const to = topics.find((x) => x.id === draftTopic);
      await change(moved ? `Moved a note to “${to?.title ?? ""}”` : "Changed a note", () =>
        saveNote(n.id, { body: text, tags: draftTags, ...(moved && to ? { topic_id: to.id, sort_order: nextOrder(allNotesOf(to)) } : {}) }));
    }
  }
  function keys(ev: KeyboardEvent) {
    if (ev.key === "Escape") cancel();
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) submit(ev);
  }

  async function removeTopic(t: Topic) {
    const subs = subsOf(t).length;
    const n = allNotesOf(t).length + subsOf(t).flatMap(allNotesOf).length;
    const what = [subs && `${subs} ${subs === 1 ? "subtopic" : "subtopics"}`, n && `${n} ${n === 1 ? "note" : "notes"}`].filter(Boolean).join(" and ");
    if (!confirm(`Delete “${t.title}”${what ? ` and its ${what}` : ""}? (Undo brings it back.)`)) return;
    editing = null;
    await change(`Deleted “${t.title}”`, () => deleteTopic(t.id));
  }
  async function removeNote(n: Note) {
    if (!confirm("Delete this note? (Undo brings it back.)")) return;
    editing = null;
    await change("Deleted a note", () => deleteNote(n.id));
  }
  async function setOutdated(n: Note, on: boolean) {
    notes = notes.map((x) => (x.id === n.id ? { ...x, outdated: on } : x));
    await change(on ? "Marked a note outdated" : "Marked a note current", () => saveNote(n.id, { outdated: on }));
  }

  // drag to reorder: shown at once, saved behind
  async function reorderTopics(rows: Topic[], ids: string[]) {
    const changes = placesOf(rows, ids);
    if (!changes.length) return;
    const at = new Map(changes.map((c) => [c.id, c.sort_order]));
    topics = topics.map((t) => (at.has(t.id) ? { ...t, sort_order: at.get(t.id)! } : t)).sort((a, b) => a.sort_order - b.sort_order);
    await change("Reordered topics", async () => { for (const c of changes) await saveTopic(c.id, { sort_order: c.sort_order }); });
  }
  async function reorderNotes(t: Topic, ids: string[]) {
    const changes = placesOf(allNotesOf(t), ids);
    if (!changes.length) return;
    const at = new Map(changes.map((c) => [c.id, c.sort_order]));
    notes = notes.map((n) => (at.has(n.id) ? { ...n, sort_order: at.get(n.id)! } : n)).sort((a, b) => a.sort_order - b.sort_order);
    await change(`Reordered notes in “${t.title}”`, async () => { for (const c of changes) await saveNote(c.id, { sort_order: c.sort_order }); });
  }

  function exportAll() {
    download(`experiments-${new Date().toISOString().slice(0, 10)}.md`, experimentsMarkdown(topics, notes));
  }
</script>

{#snippet tagPicker()}
  <div class="tags" role="group" aria-label="Tags">
    {#each TAGS as t (t)}
      <button type="button" class="tag" class:on={draftTags.includes(t)} aria-pressed={draftTags.includes(t)}
              onclick={() => toggleTag(t)}>{TAG_LABEL[t]}</button>
    {/each}
  </div>
{/snippet}

{#snippet titleForm(label: string)}
  <form class="title-form" onsubmit={submit}>
    <input class="draft" bind:value={draft} placeholder={label} aria-label={label} onkeydown={keys} />
    <button class="primary" disabled={!draft.trim() || saving}>Save</button>
    <button type="button" onclick={cancel}>Cancel</button>
  </form>
{/snippet}

{#snippet noteForm(n: Note | null)}
  <form class="note-form" onsubmit={submit}>
    <textarea class="draft" rows="3" bind:value={draft} placeholder="The note" aria-label="The note" onkeydown={keys}></textarea>
    <div class="form-row">
      {@render tagPicker()}
      {#if n}
        <label class="move">In
          <select bind:value={draftTopic}>
            {#each umbrellas as u (u.id)}
              <option value={u.id}>{u.title}</option>
              {#each subsOf(u) as s (s.id)}<option value={s.id}>{u.title} › {s.title}</option>{/each}
            {/each}
          </select>
        </label>
      {/if}
      <span class="spacer"></span>
      {#if n}<button type="button" class="danger" onclick={() => removeNote(n)}>Delete</button>{/if}
      <button type="button" onclick={cancel}>Cancel</button>
      <button class="primary" disabled={!draft.trim() || !draftTags.length || saving}>{n ? "Save" : "Add note"}</button>
    </div>
  </form>
{/snippet}

{#snippet noteRow(n: Note)}
  {#if editing?.kind === "edit" && editing.id === n.id}
    {@render noteForm(n)}
  {:else}
    <div class="note" class:outdated={n.outdated}>
      <input type="checkbox" class="tick" checked={n.outdated} disabled={saving}
             title={n.outdated ? "Outdated — untick if it holds again" : "Tick off as outdated"}
             aria-label="Outdated" onchange={(e) => setOutdated(n, e.currentTarget.checked)} />
      <div class="note-main">
        <div class="note-body"><Linked text={n.body} /></div>
        <div class="meta">
          {#each n.tags as t (t)}<span class="chip tag-chip">{TAG_LABEL[t]}</span>{/each}
          <span class="date">{fmtDay(n.noted_on)}</span>
          {#if n.outdated}<span class="date">· outdated</span>{/if}
          <button class="mini link" onclick={() => startEdit(n)} disabled={!!editing}>Edit</button>
        </div>
      </div>
    </div>
  {/if}
{/snippet}

{#snippet topicBlock(t: Topic)}
  {@const sub = !!t.parent_id}
  {@const list = notesOf(t)}
  {@const subs = subsOf(t).filter(topicShows)}
  <div class="topic" class:sub>
    {#if editing?.kind === "rename" && editing.id === t.id}
      {@render titleForm(sub ? "Subtopic" : "Topic")}
    {:else}
      <header>
        <button class="fold" aria-expanded={isOpen(t)} onclick={() => fold(t)} disabled={filtering}>
          <span class="caret" aria-hidden="true">{isOpen(t) ? "▾" : "▸"}</span>
          {#if sub}<h3>{t.title}</h3>{:else}<h2>{t.title}</h2>{/if}
        </button>
        <span class="muted count">{countOf(t)}</span>
        <span class="actions">
          <button class="mini" onclick={() => startNote(t)} disabled={!!editing}>+ Note</button>
          {#if !sub}<button class="mini" onclick={() => startTopic(t.id)} disabled={!!editing}>+ Subtopic</button>{/if}
          <button class="mini" onclick={() => startRename(t)} disabled={!!editing}>Rename</button>
          <button class="mini danger" onclick={() => removeTopic(t)} disabled={!!editing}>Delete</button>
        </span>
      </header>
    {/if}
    {#if isOpen(t)}
      <div class="inside">
        {#if list.length}
          <Sortable items={list} row={noteRow} onreorder={(ids) => reorderNotes(t, ids)} disabled={filtering || saving || !!editing} />
        {:else if !(editing?.kind === "note" && editing.topic === t.id) && !subs.length}
          <p class="muted empty">No notes yet.</p>
        {/if}
        {#if editing?.kind === "note" && editing.topic === t.id}{@render noteForm(null)}{/if}
        {#if !sub}
          {#if subs.length}
            <div class="subs">
              <Sortable items={subs} row={topicBlock} onreorder={(ids) => reorderTopics(subsOf(t), ids)} disabled={filtering || saving || !!editing} />
            </div>
          {/if}
          {#if editing?.kind === "topic" && editing.parent === t.id}{@render titleForm("New subtopic")}{/if}
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

<section>
  <span class="eyebrow">Experiments</span>
  <h1>Life is experiments</h1>
  <p class="muted intro">
    Topics, their subtopics, and notes under each — tagged Tip, Hypothesis, Practice or Self. Drag ⠿ to put them in
    order; tick a note off when it is outdated. Only you see them.
  </p>
  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Experiments needs its tables first: run <code>web/db/0066_experiments.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    <div class="bar">
      <button class="primary" onclick={() => startTopic(null)} disabled={!!editing}>+ Topic</button>
      <input class="search" type="search" bind:value={query} placeholder="Search notes and topics" aria-label="Search" />
      <div class="pick" role="group" aria-label="Show tag">
        <button class:on={!tag} aria-pressed={!tag} onclick={() => (tag = null)}>All</button>
        {#each TAGS as t (t)}
          <button class:on={tag === t} aria-pressed={tag === t} onclick={() => (tag = tag === t ? null : t)}>{TAG_LABEL[t]}</button>
        {/each}
      </div>
      <span class="spacer"></span>
      <button class="mini" onclick={exportAll} disabled={!topics.length} title="As a Markdown file, to keep on OneDrive">Export</button>
    </div>
    {#if filtering}
      <p class="muted count">{shownCount} of {notes.length} {notes.length === 1 ? "note" : "notes"} · clear the search and tag to reorder</p>
    {/if}
    {#if editing?.kind === "topic" && editing.parent === null}{@render titleForm("New topic")}{/if}

    {#if shownUmbrellas.length}
      <div class="umbrellas">
        <Sortable items={shownUmbrellas} row={topicBlock} onreorder={(ids) => reorderTopics(umbrellas, ids)}
                  disabled={filtering || saving || !!editing} />
      </div>
    {:else if filtering}
      <p class="muted">Nothing matches.</p>
    {:else if !editing}
      <p class="muted">No topics yet. Start with + Topic.</p>
    {/if}

    <p class="muted earlier">
      What you had in Tips, Failures, Practice and Diary was copied here when Experiments was set up. The originals are
      still kept: <a href="#/tips">Tips</a> · <a href="#/failures">Failures</a> · <a href="#/practice">Practice</a> ·
      <a href="#/diary">Diary</a>.
    </p>
  {/if}
</section>

<style>
  .intro { font-size: 0.9rem; max-width: 46rem; }
  .bar { display: flex; flex-wrap: wrap; gap: 0.5rem 0.6rem; align-items: center; margin: 0.6rem 0; font-family: var(--font-ui); }
  .search { width: auto; flex: 0 1 16rem; padding: 0.3rem 0.55rem; font-size: 0.85rem; }
  .pick { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .pick button { font-size: 0.8rem; padding: 0.2rem 0.7rem; }
  .pick button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .spacer { flex: 1; }
  .mini { font-size: 0.75rem; padding: 0.1rem 0.5rem; white-space: nowrap; }
  .mini.link { border: none; background: none; padding: 0; color: var(--ink-soft); text-decoration: underline dotted; }
  .danger { color: var(--danger); }
  .count, .empty { font-family: var(--font-ui); font-size: 0.8rem; }
  .empty { margin: 0.3rem 0; }

  /* the space between topics goes on the row, so its ⠿ lines up with the title */
  .umbrellas > :global(ul.sortable > li) { margin-top: 1.2rem; }
  .subs > :global(ul.sortable > li) { margin-top: 0.6rem; }
  .umbrellas > :global(ul.sortable > li > .grip), .subs > :global(ul.sortable > li > .grip) { padding-top: 0.3rem; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-left: auto; }
  header {
    display: flex; flex-wrap: wrap; gap: 0.3rem 0.5rem; align-items: baseline; font-family: var(--font-ui);
    border-bottom: 1px solid var(--rule); padding-bottom: 0.25rem;
  }
  .topic.sub header { border-bottom-style: dashed; }
  .fold {
    display: flex; gap: 0.35rem; align-items: baseline; min-width: 0; padding: 0; border: none; background: none;
    text-align: left; color: var(--ink); cursor: pointer;
  }
  .fold:disabled { opacity: 1; cursor: default; }
  .fold h2, .fold h3 { margin: 0; font-family: var(--font); overflow-wrap: anywhere; }
  .fold h3 { font-size: 1.02rem; }
  .caret { flex: none; width: 0.9rem; font-size: 0.7rem; color: var(--ink-soft); }
  .inside { padding: 0.2rem 0 0 1.1rem; }

  .note { display: flex; gap: 0.55rem; align-items: flex-start; padding: 0.3rem 0.2rem; border-bottom: 1px solid var(--rule); }
  .note:hover { background: var(--panel); }
  .tick { width: auto; margin: 0.3rem 0 0; accent-color: var(--accent); cursor: pointer; }
  .note-main { flex: 1; min-width: 0; }
  .note-body { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.95rem; }
  /* outdated: still there to read, in grey */
  .note.outdated .note-body { color: var(--ink-soft); opacity: 0.75; }
  .note.outdated .tag-chip { opacity: 0.7; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.15rem 0.4rem; align-items: baseline; font-family: var(--font-ui); }
  .tag-chip { margin-left: 0; }
  .date { font-size: 0.75rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; }

  .title-form, .note-form { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; font-family: var(--font-ui); }
  .title-form input { flex: 1 1 16rem; }
  .note-form { flex-direction: column; }
  .form-row { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .tag { font-size: 0.78rem; padding: 0.15rem 0.6rem; border-radius: 999px; }
  .tag.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .move { display: flex; gap: 0.35rem; align-items: center; font-size: 0.8rem; color: var(--ink-soft); }
  .move select { width: auto; max-width: 18rem; padding: 0.2rem 0.4rem; font-size: 0.82rem; }

  .earlier { margin-top: 2.5rem; font-family: var(--font-ui); font-size: 0.8rem; }
</style>
