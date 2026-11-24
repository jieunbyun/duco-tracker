<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = {
    view: "topics" as "topics" | "date", // under topics, or every note newest first
    tag: null as string | null,
    query: "",
    opened: new Set<string>(), // topics and subtopics opened (they all start folded)
    tags: [] as string[], // what the last new note was tagged
  };
</script>

<script lang="ts">
  // Experiments: what were Tips, Failures, Practice and Diary, in one place, laid out
  // like the Logbook. Umbrella topics with subtopics, notes under either, each note
  // tagged and in your own order (drag ⠿), marked ⊘ outdated (notes, topics and subtopics alike).
  import { tick } from "svelte";
  import {
    TAGS, TAG_LABEL, loadExperiments, addTopic, saveTopic, deleteTopic, addNote, saveNote, deleteNote, placesOf, matches,
    experimentsMarkdown,
  } from "../lib/experiments";
  import type { Tag, Topic, Note } from "../lib/experiments";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, parse } from "../lib/dates";
  import { download } from "../lib/group";
  import Sortable from "../lib/Sortable.svelte";
  import Linked from "../lib/Linked.svelte";

  let topics = $state<Topic[]>([]);
  let notes = $state<Note[]>([]);
  let loading = $state(true);
  let error = $state("");
  let missing = $state(""); // the SQL file not run yet, if one is not

  let view = $state(last.view);
  let tag = $state<Tag | null>(last.tag as Tag | null);
  let query = $state(last.query);
  let opened = $state(new Set(last.opened));
  $effect(() => {
    Object.assign(last, { view, tag, query, opened });
  });
  function setView(v: "topics" | "date") {
    editing = null; // its form may not be in the other view
    view = v;
  }

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
  let draftOutdated = $state(false); // ⊘ in an edit form (the way on a phone, with no hover)
  let saving = $state(false);

  async function load() {
    try {
      ({ topics, notes } = await loadExperiments());
      error = "";
      missing = "";
    } catch (e) {
      const msg = (e as Error).message;
      if (/exp_topic|exp_note/.test(msg) && /exist|schema cache/i.test(msg)) {
        const col = msg.match(/exp_topic\.(tags|outdated)\b|'(tags|outdated)' column/);
        missing = !col ? "0066_experiments.sql" : (col[1] ?? col[2]) === "tags" ? "0068_exp_topic_tags.sql" : "0070_exp_topic_outdated.sql";
      }
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
  // a topic's tags count for everything under it: its notes, and a subtopic's under its topic's
  const inTag = (t: Topic) =>
    !!tag && (t.tags.includes(tag) || !!topics.find((p) => p.id === t.parent_id)?.tags.includes(tag));
  const shows = (n: Note, t: Topic) =>
    (!tag || n.tags.includes(tag) || inTag(t)) && (!query.trim() || matches(`${n.body}\n${t.title}\n${titleOf(t.parent_id)}`, query));
  const notesOf = (t: Topic) => (filtering ? allNotesOf(t).filter((n) => shows(n, t)) : allNotesOf(t));
  // filtering, a topic shows when anything under it does, or it is itself tagged and titled so
  const topicShows = (t: Topic): boolean =>
    !filtering || notesOf(t).length > 0 || subsOf(t).some(topicShows)
    || ((!tag || inTag(t)) && (!query.trim() || matches(`${t.title}\n${titleOf(t.parent_id)}`, query)));
  const shownUmbrellas = $derived(umbrellas.filter(topicShows));
  const isOpen = (t: Topic) => filtering || opened.has(t.id);
  function fold(t: Topic) {
    const s = new Set(opened);
    if (s.has(t.id)) s.delete(t.id);
    else s.add(t.id);
    opened = s;
  }
  function openUp(id: string) {
    if (!opened.has(id)) opened = new Set([...opened, id]);
  }
  const countOf = (t: Topic) => {
    const every = [...allNotesOf(t), ...subsOf(t).flatMap(allNotesOf)];
    const old = every.filter((n) => n.outdated).length;
    return `${every.length} ${every.length === 1 ? "note" : "notes"}${old ? ` · ${old} outdated` : ""}`;
  };
  const shownCount = $derived(filtering ? topics.reduce((a, t) => a + notesOf(t).length, 0) : notes.length);

  // by date: every note that shows, newest first, a group per month
  const pathOf = (id: string) => {
    const t = topics.find((x) => x.id === id);
    return !t ? "" : t.parent_id ? `${titleOf(t.parent_id)} › ${t.title}` : t.title;
  };
  const months = $derived.by(() => {
    const dated = topics.flatMap(notesOf).sort((a, b) =>
      b.noted_on.localeCompare(a.noted_on) || b.created_at.localeCompare(a.created_at));
    const out: { key: string; label: string; rows: Note[] }[] = [];
    for (const n of dated) {
      const key = n.noted_on.slice(0, 7);
      if (out.at(-1)?.key !== key) {
        out.push({ key, label: parse(`${key}-01`).toLocaleDateString("en-GB", { month: "long", year: "numeric" }), rows: [] });
      }
      out.at(-1)!.rows.push(n);
    }
    return out;
  });

  // ---- writing --------------------------------------------------------------------
  async function focusDraft() {
    await tick();
    document.querySelector<HTMLElement>(".draft")?.focus();
  }
  function startTopic(parent: string | null) {
    editing = { kind: "topic", parent };
    draft = "";
    draftTags = tag ? [tag] : []; // so it stays in view under the tag shown
    if (parent) openUp(parent);
    focusDraft();
  }
  function startRename(t: Topic) {
    editing = { kind: "rename", id: t.id };
    draft = t.title;
    draftTags = [...t.tags];
    draftOutdated = t.outdated;
    focusDraft();
  }
  function startNote(t: Topic) {
    editing = { kind: "note", topic: t.id };
    draft = "";
    // tagged as its (sub)topic, else as the topic above it; with neither tagged, as the topic's
    // newest note, else as your last new note. Plus the tag shown, so the note stays in view.
    const parent = topics.find((p) => p.id === t.parent_id);
    const prev = allNotesOf(t).reduce<Note | null>((a, n) => (!a || n.created_at > a.created_at ? n : a), null);
    const from: Tag[] = t.tags.length ? t.tags : parent?.tags.length ? parent.tags
      : prev ? prev.tags : (last.tags as Tag[]);
    draftTags = TAGS.filter((x) => from.includes(x) || x === tag);
    openUp(t.id);
    focusDraft();
  }
  function startEdit(n: Note) {
    editing = { kind: "edit", id: n.id };
    draft = n.body;
    draftTags = [...n.tags];
    draftTopic = n.topic_id;
    draftOutdated = n.outdated;
    focusDraft();
  }
  function cancel() {
    editing = null;
  }
  // clicking a note's text edits it, unless the click is on a link in it or ends a text selection
  function clickNote(ev: MouseEvent, n: Note) {
    if (editing || saving) return;
    if ((ev.target as HTMLElement).closest("a")) return;
    if (window.getSelection()?.toString()) return;
    startEdit(n);
  }
  function toggleTag(t: Tag) {
    draftTags = draftTags.includes(t) ? draftTags.filter((x) => x !== t) : TAGS.filter((x) => x === t || draftTags.includes(x));
  }
  // new topics and notes (and a note moved in) go first: one place before the first
  const firstOrder = (rows: { sort_order: number }[]) => (rows.length ? Math.min(...rows.map((r) => r.sort_order)) - 10 : 0);

  async function submit(ev?: Event) {
    ev?.preventDefault();
    const e = editing;
    const text = draft.trim();
    if (!e || !text || saving) return;
    if ((e.kind === "note" || e.kind === "edit") && !draftTags.length) return void (error = "Give the note at least one tag.");
    editing = null;
    if (e.kind === "topic") {
      const siblings = topics.filter((t) => t.parent_id === e.parent);
      await change(e.parent ? `Added subtopic “${text}”` : `Added topic “${text}”`, () => addTopic(text, e.parent, draftTags, firstOrder(siblings)));
    } else if (e.kind === "rename") {
      const was = topics.find((x) => x.id === e.id)!;
      const label = was.title !== text ? `Renamed “${was.title}” to “${text}”`
        : was.outdated !== draftOutdated ? `Marked “${text}” ${draftOutdated ? "outdated" : "current"}`
        : `Changed the tags on “${text}”`;
      await change(label, () => saveTopic(e.id, { title: text, tags: draftTags, outdated: draftOutdated }));
    } else if (e.kind === "note") {
      last.tags = [...draftTags];
      const t = topics.find((x) => x.id === e.topic)!;
      await change(`Added a note to “${t.title}”`, () =>
        addNote({ topic_id: t.id, body: text, tags: draftTags, sort_order: firstOrder(allNotesOf(t)) }));
    } else {
      const n = notes.find((x) => x.id === e.id)!;
      const moved = draftTopic !== n.topic_id;
      const to = topics.find((x) => x.id === draftTopic);
      const label = moved ? `Moved a note to “${to?.title ?? ""}”`
        : n.outdated !== draftOutdated ? `Marked a note ${draftOutdated ? "outdated" : "current"}` : "Changed a note";
      await change(label, () =>
        saveNote(n.id, { body: text, tags: draftTags, outdated: draftOutdated,
                         ...(moved && to ? { topic_id: to.id, sort_order: firstOrder(allNotesOf(to)) } : {}) }));
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
  async function setTopicOutdated(t: Topic, on: boolean) {
    topics = topics.map((x) => (x.id === t.id ? { ...x, outdated: on } : x));
    await change(`Marked “${t.title}” ${on ? "outdated" : "current"}`, () => saveTopic(t.id, { outdated: on }));
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

{#snippet outToggle()}
  <button type="button" class="tag out-toggle" class:on={draftOutdated} aria-pressed={draftOutdated}
          onclick={() => (draftOutdated = !draftOutdated)}>⊘ Outdated</button>
{/snippet}

{#snippet outMark(on: boolean, what: string, flip: () => void)}
  <!-- ⊘ at the far right: always there once outdated; else on hover (and not on a phone, which
       uses ⊘ Outdated in the edit form instead) -->
  <button type="button" class="out" class:on disabled={saving || !!editing} aria-pressed={on}
          title={on ? `Outdated — click to mark ${what} current again` : `Mark ${what} outdated`}
          aria-label={on ? `Outdated: mark ${what} current` : `Mark ${what} outdated`} onclick={flip}>⊘</button>
{/snippet}

{#snippet titleForm(label: string, t: Topic | null = null)}
  <form class="title-form" onsubmit={submit}>
    <input class="draft" bind:value={draft} placeholder={label} aria-label={label} onkeydown={keys} />
    {@render tagPicker()}
    {#if t}{@render outToggle()}{/if}
    {#if t}<button type="button" class="danger" onclick={() => removeTopic(t)}>Delete</button>{/if}
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
        {@render outToggle()}
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
      <div class="note-main" class:multi={n.body.trim().includes("\n")}>
        <!-- click the text (or Tab to it and press Enter) to edit or delete it -->
        <div class="note-body" class:editable={!editing && !saving} title={editing ? undefined : "Click to edit"}
             role="button" tabindex={editing ? -1 : 0} onclick={(ev) => clickNote(ev, n)}
             onkeydown={(ev) => {
               if ((ev.key === "Enter" || ev.key === " ") && ev.target === ev.currentTarget && !editing && !saving) {
                 ev.preventDefault();
                 startEdit(n);
               }
             }}><Linked text={n.body} /></div>
        <div class="meta">
          {#if view === "date"}<span class="where">{pathOf(n.topic_id)}</span>{/if}
          {#each n.tags as t (t)}<span class="chip tag-chip">{TAG_LABEL[t]}</span>{/each}
          <span class="date">{fmtDay(n.noted_on)}</span>
          {#if n.outdated}<span class="date">· outdated</span>{/if}
        </div>
      </div>
      {@render outMark(n.outdated, "this note", () => setOutdated(n, !n.outdated))}
    </div>
  {/if}
{/snippet}

{#snippet topicBlock(t: Topic)}
  {@const sub = !!t.parent_id}
  {@const list = notesOf(t)}
  {@const subs = subsOf(t).filter(topicShows)}
  <div class="topic" class:sub class:outdated={t.outdated}>
    {#if editing?.kind === "rename" && editing.id === t.id}
      {@render titleForm(sub ? "Subtopic" : "Topic", t)}
    {:else}
      <header>
        <!-- the caret folds; the title opens it for editing (its name, tags, outdated, or delete) -->
        <span class="head">
          <button class="fold" aria-expanded={isOpen(t)} aria-label={`${isOpen(t) ? "Fold" : "Open"} “${t.title}”`}
                  onclick={() => fold(t)} disabled={filtering}>
            <span class="caret" aria-hidden="true">{isOpen(t) ? "▾" : "▸"}</span>
          </button>
          {#if sub}
            <h3><button class="name" onclick={() => startRename(t)} disabled={!!editing} title="Click to edit">{t.title}</button></h3>
          {:else}
            <h2><button class="name" onclick={() => startRename(t)} disabled={!!editing} title="Click to edit">{t.title}</button></h2>
          {/if}
        </span>
        {#each t.tags as x (x)}<span class="chip tag-chip">{TAG_LABEL[x]}</span>{/each}
        <span class="muted count">{countOf(t)}</span>
        <span class="actions">
          <button class="mini" onclick={() => startNote(t)} disabled={!!editing}>+ Note</button>
          {#if !sub}<button class="mini" onclick={() => startTopic(t.id)} disabled={!!editing}>+ Subtopic</button>{/if}
        </span>
        {@render outMark(t.outdated, sub ? "this subtopic" : "this topic", () => setTopicOutdated(t, !t.outdated))}
      </header>
    {/if}
    {#if isOpen(t)}
      <div class="inside">
        {#if editing?.kind === "note" && editing.topic === t.id}{@render noteForm(null)}{/if}
        {#if list.length}
          <Sortable items={list} row={noteRow} onreorder={(ids) => reorderNotes(t, ids)} disabled={filtering || saving || !!editing} />
        {:else if !(editing?.kind === "note" && editing.topic === t.id) && !subs.length}
          <p class="muted empty">No notes yet.</p>
        {/if}
        {#if !sub}
          {#if editing?.kind === "topic" && editing.parent === t.id}{@render titleForm("New subtopic")}{/if}
          {#if subs.length}
            <div class="subs">
              <Sortable items={subs} row={topicBlock} onreorder={(ids) => reorderTopics(subsOf(t), ids)} disabled={filtering || saving || !!editing} />
            </div>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

<section>
  <span class="eyebrow">Experiments</span>
  <h1>Life is experiments</h1>
  <p class="muted intro">
    Topics, their subtopics, and notes under each — tagged Tip, Hypothesis, Practice, Self, Innovation or Modelling (a topic's
    tags count for everything under it). Drag ⠿ to put them in
    order; mark one ⊘ outdated when it no longer holds. Only you see them.
  </p>
  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Experiments needs a change to the database first: run <code>web/db/{missing}</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    <div class="bar">
      {#if view === "topics"}<button class="primary" onclick={() => startTopic(null)} disabled={!!editing}>+ Topic</button>{/if}
      <div class="pick" role="group" aria-label="View">
        <button class:on={view === "topics"} aria-pressed={view === "topics"} onclick={() => setView("topics")}>Topics</button>
        <button class:on={view === "date"} aria-pressed={view === "date"} onclick={() => setView("date")}>By date</button>
      </div>
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
      <p class="muted count">{shownCount} of {notes.length} {notes.length === 1 ? "note" : "notes"}{view === "topics" ? " · clear the search and tag to reorder" : ""}</p>
    {/if}
    {#if editing?.kind === "topic" && editing.parent === null}{@render titleForm("New topic")}{/if}

    {#if view === "date"}
      {#each months as m (m.key)}
        <h2 class="month">{m.label} <span class="muted count">{m.rows.length}</span></h2>
        {#each m.rows as n (n.id)}{@render noteRow(n)}{/each}
      {:else}
        <p class="muted">{filtering ? "Nothing matches." : "No notes yet. Add them under a topic, in Topics."}</p>
      {/each}
    {:else if shownUmbrellas.length}
      <div class="umbrellas">
        <Sortable items={shownUmbrellas} row={topicBlock} onreorder={(ids) => reorderTopics(umbrellas, ids)}
                  disabled={filtering || saving || !!editing} />
      </div>
    {:else if filtering}
      <p class="muted">Nothing matches.</p>
    {:else if !editing}
      <p class="muted">No topics yet. Start with + Topic.</p>
    {/if}
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
  .head { display: flex; gap: 0.15rem; align-items: baseline; min-width: 0; }
  .fold { flex: none; padding: 0 0.2rem; border: none; background: none; color: var(--ink); cursor: pointer; }
  .fold:disabled { opacity: 1; cursor: default; }
  .head h2, .head h3 { margin: 0; font-family: var(--font); overflow-wrap: anywhere; }
  .head h3 { font-size: 1.02rem; font-weight: normal; }
  .name {
    padding: 0; border: none; background: none; font: inherit; color: var(--ink); text-align: left; cursor: text;
    overflow-wrap: anywhere;
  }
  .name:hover:not(:disabled) { text-decoration: underline dotted; text-underline-offset: 0.2em; }
  .name:disabled { opacity: 1; cursor: default; }
  .caret { display: inline-block; width: 0.9rem; font-size: 0.7rem; color: var(--ink-soft); }
  .inside { padding: 0.2rem 0 0 1.1rem; }

  .note { display: flex; gap: 0.55rem; align-items: flex-start; padding: 0.3rem 0.2rem; border-bottom: 1px solid var(--rule); }
  .note:hover { background: var(--panel); }
  /* ⊘ outdated, at the far right: shown on hover (or keyboard focus), always once outdated */
  .out {
    flex: none; padding: 0 0.3rem; border: none; background: none; font-size: 1rem; line-height: 1.4;
    color: var(--ink-soft); cursor: pointer; opacity: 0; transition: opacity 0.12s;
  }
  header .out { align-self: center; }
  .note:hover .out, header:hover .out, .out:focus-visible { opacity: 0.5; }
  .out:hover:not(:disabled) { opacity: 1; }
  .out.on { opacity: 1; color: var(--danger); }
  .out:disabled { cursor: default; }
  /* no hover on a phone: only the outdated ones show it; ⊘ Outdated in the edit form does the rest */
  @media (hover: none) { .out:not(.on) { display: none; } }
  .out-toggle.on { background: var(--danger); border-color: var(--danger); color: var(--paper); }
  /* an outdated topic: its title in grey, and what is under it faded */
  .topic.outdated > header .name { color: var(--ink-soft); }
  .topic.outdated > .inside { opacity: 0.6; }
  /* the text, then its tags and date on the same line when they fit (as a topic's title and
     chips), else on the line below; a note of several lines keeps them below */
  .note-main { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.1rem 0.6rem; }
  .note-main.multi { display: block; }
  .note-body { flex: 0 1 auto; min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.95rem; }
  .note-body.editable { cursor: text; }
  .note-body:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
  /* outdated: still there to read, in grey */
  .note.outdated .note-body { color: var(--ink-soft); opacity: 0.75; }
  .note.outdated .tag-chip { opacity: 0.7; }
  /* a note's tags and date at the right, on its line or the one below */
  .meta {
    display: flex; flex-wrap: wrap; gap: 0.15rem 0.4rem; align-items: baseline; justify-content: flex-end;
    margin-left: auto; font-family: var(--font-ui);
  }
  .tag-chip { margin-left: 0; }
  .where { font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); }
  .month { margin: 1.2rem 0 0.2rem; font-size: 1.05rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.2rem; }
  .date { font-size: 0.75rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; }

  .title-form, .note-form { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; font-family: var(--font-ui); }
  .title-form input { flex: 1 1 16rem; }
  .title-form .tags { align-self: center; }
  .note-form { flex-direction: column; }
  .form-row { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .tag { font-size: 0.78rem; padding: 0.15rem 0.6rem; border-radius: 999px; }
  .tag.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .move { display: flex; gap: 0.35rem; align-items: center; font-size: 0.8rem; color: var(--ink-soft); }
  .move select { width: auto; max-width: 18rem; padding: 0.2rem 0.4rem; font-size: 0.82rem; }

  .earlier { margin-top: 2.5rem; font-family: var(--font-ui); font-size: 0.8rem; }
</style>
