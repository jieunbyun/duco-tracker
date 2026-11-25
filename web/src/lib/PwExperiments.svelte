<script lang="ts">
  // The Experiments (topics and subtopics, 0066) on a Pathways item, kept up from the map: link
  // existing ones, start a new one, and add notes to them; the rest is done in Experiments (›).
  import { TAGS, TAG_LABEL, addTopic, addNote, matches } from "./experiments";
  import type { Tag, Topic, Note } from "./experiments";
  import { linkExperiment, unlinkExperiment } from "./pathways";
  import { undoable } from "./undo.svelte";
  import { fmtDay } from "./dates";
  import Linked from "./Linked.svelte";

  type Props = {
    nodeId: string;
    topics: Topic[];
    notes: Note[];
    linked: string[]; // the topics on this item, in the order they were linked
    onchange: () => void | Promise<void>;
  };
  let { nodeId, topics, notes, linked, onchange }: Props = $props();

  const byId = $derived(new Map(topics.map((t) => [t.id, t])));
  const subsOf = (t: Topic) => topics.filter((x) => x.parent_id === t.id);
  const notesOf = (t: Topic) => notes.filter((n) => n.topic_id === t.id);
  const pathOf = (t: Topic) => {
    const p = t.parent_id ? byId.get(t.parent_id) : undefined;
    return p ? `${p.title} › ${t.title}` : t.title;
  };
  const everyNote = (t: Topic) => [...notesOf(t), ...subsOf(t).flatMap(notesOf)];
  const mine = $derived(linked.map((id) => byId.get(id)).filter((t): t is Topic => !!t));
  const firstOrder = (rows: { sort_order: number }[]) => (rows.length ? Math.min(...rows.map((r) => r.sort_order)) - 10 : 0);

  let mode = $state<"existing" | "new" | null>(null);
  let opened = $state(new Set<string>());
  let busy = $state(false);
  let error = $state("");
  function toggle(id: string) {
    const s = new Set(opened);
    if (s.has(id)) s.delete(id);
    else s.add(id);
    opened = s;
  }

  async function change(label: string, run: () => Promise<unknown>): Promise<boolean> {
    busy = true;
    error = "";
    try {
      await undoable(label, run);
      await onchange();
      return true;
    } catch (e) {
      const msg = (e as Error).message;
      error = /pw_experiment/.test(msg) ? "Linking experiments needs web/db/0076_pw_experiments.sql run first, in the Supabase SQL editor." : msg;
      return false;
    } finally {
      busy = false;
    }
  }

  // ---- an existing topic or subtopic ------------------------------------------------------
  let find = $state("");
  /** Umbrella topics with their subtopics, narrowed by what is typed (in titles or notes); linked ones left out. */
  const candidates = $derived.by(() => {
    const q = find.trim();
    const hit = (t: Topic) => !q || matches(`${pathOf(t)} ${notesOf(t).map((n) => n.body).join(" ")}`, q);
    return topics.filter((t) => !t.parent_id).map((t) => ({
      top: t,
      self: !linked.includes(t.id) && hit(t),
      subs: subsOf(t).filter((s) => !linked.includes(s.id) && hit(s)),
    })).filter((g) => g.self || g.subs.length);
  });
  async function link(t: Topic) {
    if (await change(`Linked “${t.title}”`, () => linkExperiment(nodeId, t.id))) {
      mode = null;
      find = "";
      opened = new Set([...opened, t.id]);
    }
  }
  function unlink(t: Topic) {
    change(`Unlinked “${t.title}”`, () => unlinkExperiment(nodeId, t.id));
  }

  // ---- a new one: a subtopic under a topic, or a topic of its own -------------------------
  let newTitle = $state("");
  let newParent = $state(""); // a topic's id, or "" for a topic of its own
  let newTags = $state<Tag[]>(["innovation"]);
  const umbrellas = $derived(topics.filter((t) => !t.parent_id));
  async function create(ev: SubmitEvent) {
    ev.preventDefault();
    const title = newTitle.trim();
    if (!title) return;
    const parent = newParent || null;
    const siblings = topics.filter((t) => t.parent_id === parent);
    let id = "";
    const ok = await change(`Started “${title}” in Experiments`, async () => {
      id = (await addTopic(title, parent, newTags, firstOrder(siblings))).id;
      await linkExperiment(nodeId, id);
    });
    if (ok) {
      mode = null;
      newTitle = "";
      opened = new Set([...opened, id]);
    }
  }

  // ---- a note, added to a linked topic -----------------------------------------------------
  let noteText = $state<Record<string, string>>({});
  let noteTags = $state<Tag[]>(["hypothesis"]);
  async function addTo(t: Topic) {
    const body = (noteText[t.id] ?? "").trim();
    if (!body || !noteTags.length) return;
    if (await change(`Added a note to “${t.title}”`, () => addNote({ topic_id: t.id, body, tags: noteTags, sort_order: firstOrder(notesOf(t)) }))) {
      noteText[t.id] = "";
    }
  }
  function toggleTag(list: Tag[], x: Tag): Tag[] {
    return list.includes(x) ? list.filter((y) => y !== x) : [...list, x];
  }
</script>

{#snippet tagPicker(list: Tag[], set: (l: Tag[]) => void)}
  <span class="tags" role="group" aria-label="Tags">
    {#each TAGS as x (x)}
      <button type="button" class="tag" class:on={list.includes(x)} aria-pressed={list.includes(x)}
              onclick={() => set(toggleTag(list, x))}>{TAG_LABEL[x]}</button>
    {/each}
  </span>
{/snippet}

{#snippet noteLine(n: Note)}
  <li class:outdated={n.outdated}>
    <span class="when">{fmtDay(n.noted_on)}</span>
    <span class="body"><Linked text={n.body} /></span>
    <span class="ntags">{n.tags.map((x) => TAG_LABEL[x]).join(", ")}{n.outdated ? " · outdated" : ""}</span>
  </li>
{/snippet}

<div class="pw-exp">
  <div class="head">
    <span class="muted">{mine.length ? `${mine.length} linked` : "None linked yet"}</span>
    <span class="spacer"></span>
    <button type="button" class="mini" disabled={busy || !topics.length} onclick={() => (mode = mode === "existing" ? null : "existing")}>+ Existing…</button>
    <button type="button" class="mini primary" disabled={busy} onclick={() => (mode = mode === "new" ? null : "new")}>+ New</button>
  </div>
  {#if error}<p class="error">{error}</p>{/if}

  {#if mode === "existing"}
    <div class="box">
      <div class="find">
        <!-- svelte-ignore a11y_autofocus -->
        <input type="search" bind:value={find} placeholder="Find a topic or subtopic (its title or notes)…" autofocus
               onkeydown={(ev) => { if (ev.key === "Escape") { ev.preventDefault(); mode = null; } }} />
        <button type="button" class="mini" onclick={() => { mode = null; find = ""; }}>Cancel</button>
      </div>
      {#each candidates as g (g.top.id)}
        <div class="group">
          {#if g.self}
            <button type="button" class="cand top" class:outdated={g.top.outdated} disabled={busy} onclick={() => link(g.top)}>
              <span>{g.top.title}</span><span class="meta">topic · {everyNote(g.top).length} notes</span>
            </button>
          {:else}
            <h5>{g.top.title}</h5>
          {/if}
          {#each g.subs as s (s.id)}
            <button type="button" class="cand" class:outdated={s.outdated} disabled={busy} onclick={() => link(s)}>
              <span>{s.title}</span><span class="meta">{notesOf(s).length} notes</span>
            </button>
          {/each}
        </div>
      {:else}
        <p class="muted small">{find.trim() ? "None match." : "Every topic is linked already."}</p>
      {/each}
    </div>
  {:else if mode === "new"}
    <form class="box new" onsubmit={create}>
      <label>Title <input bind:value={newTitle} required placeholder="e.g. Does a surrogate model hold beyond 10 bar?" /></label>
      <label>Under
        <select bind:value={newParent}>
          <option value="">— a topic of its own —</option>
          {#each umbrellas as t (t.id)}<option value={t.id}>{t.title}</option>{/each}
        </select>
      </label>
      <div class="row"><span class="muted small">Tags</span>{@render tagPicker(newTags, (l) => (newTags = l))}</div>
      <div class="row">
        <button class="primary mini" type="submit" disabled={busy || !newTitle.trim()}>Start it in Experiments</button>
        <button type="button" class="mini" onclick={() => (mode = null)}>Cancel</button>
      </div>
    </form>
  {/if}

  {#each mine as t (t.id)}
    {@const all = everyNote(t)}
    {@const live = all.filter((n) => !n.outdated).length}
    <div class="exp" class:outdated={t.outdated}>
      <div class="exp-head">
        <button type="button" class="caret" aria-expanded={opened.has(t.id)} onclick={() => toggle(t.id)}>
          <span aria-hidden="true">{opened.has(t.id) ? "▾" : "▸"}</span> {pathOf(t)}
        </button>
        <span class="meta">{live} {live === 1 ? "note" : "notes"}{all.length > live ? ` · ${all.length - live} outdated` : ""}</span>
        <a class="mini-link" href={`#/experiments?t=${t.id}`} title="Open it in Experiments">Experiments ›</a>
        <button type="button" class="x" aria-label={`Unlink ${t.title}`} title="Unlink it from this item (it stays in Experiments)"
                disabled={busy} onclick={() => unlink(t)}>✕</button>
      </div>
      {#if opened.has(t.id)}
        <div class="exp-body">
          <div class="add">
            <textarea rows="2" bind:value={noteText[t.id]} placeholder="Add a note — Enter adds it (saved at once)"
                      onkeydown={(ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); addTo(t); } }}></textarea>
            <div class="row">{@render tagPicker(noteTags, (l) => (noteTags = l))}</div>
          </div>
          {#if notesOf(t).length}<ul>{#each notesOf(t) as n (n.id)}{@render noteLine(n)}{/each}</ul>{/if}
          {#each subsOf(t) as s (s.id)}
            {#if notesOf(s).length}
              <h5>{s.title}</h5>
              <ul>{#each notesOf(s) as n (n.id)}{@render noteLine(n)}{/each}</ul>
            {/if}
          {/each}
          {#if !all.length}<p class="muted small">No notes yet.</p>{/if}
        </div>
      {/if}
    </div>
  {/each}
</div>

<style>
  .pw-exp { font-family: var(--font-ui); display: grid; gap: 0.5rem; }
  .head { display: flex; align-items: center; gap: 0.4rem; }
  .head .muted { font-size: 0.82rem; }
  .spacer { flex: 1; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; white-space: nowrap; }
  .small { font-size: 0.8rem; margin: 0; }
  .error { color: var(--danger); font-size: 0.8rem; margin: 0; }
  .box { background: var(--panel); padding: 0.6rem; display: grid; gap: 0.45rem; max-height: 22rem; overflow-y: auto; }
  .find { display: flex; gap: 0.4rem; align-items: center; }
  .find input { flex: 1; }
  .group { display: grid; gap: 0.2rem; }
  h5 { margin: 0.2rem 0 0.1rem; font-size: 0.78rem; color: var(--ink-soft); font-weight: 600; }
  .cand {
    display: flex; gap: 0.6rem; align-items: baseline; justify-content: space-between; width: 100%; text-align: left;
    background: var(--paper); border: 1px solid var(--rule); border-radius: 0; padding: 0.3rem 0.5rem; font-size: 0.84rem;
  }
  .cand:not(.top) { margin-left: 0.8rem; width: calc(100% - 0.8rem); }
  .cand.top { font-weight: 600; }
  .cand:hover { border-color: var(--ink-soft); }
  .cand.outdated span:first-child { text-decoration: line-through; color: var(--ink-soft); }
  .meta { font-size: 0.74rem; color: var(--ink-soft); font-weight: 400; white-space: nowrap; }
  .new label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); }
  .row { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
  .tags { display: inline-flex; flex-wrap: wrap; gap: 0.25rem; }
  .tag { font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 0; }
  .tag.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .exp { border: 1px solid var(--rule); border-left: 3px solid var(--accent); }
  .exp.outdated { opacity: 0.6; }
  .exp-head { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.4rem; }
  .caret { flex: 1; min-width: 0; text-align: left; background: none; border: none; padding: 0; font-size: 0.86rem; font-weight: 600; color: var(--ink); }
  .mini-link { font-size: 0.74rem; white-space: nowrap; }
  .x { background: none; border: none; padding: 0 0.3rem; color: var(--ink-soft); font-size: 0.8rem; }
  .exp-body { padding: 0.2rem 0.6rem 0.6rem; display: grid; gap: 0.35rem; }
  .add { display: grid; gap: 0.3rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; }
  li { display: grid; grid-template-columns: auto 1fr; gap: 0 0.6rem; font-size: 0.82rem; }
  li .when { font-size: 0.72rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; padding-top: 0.1rem; }
  li .body { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--ink); }
  li .ntags { grid-column: 2; font-size: 0.7rem; color: var(--ink-soft); }
  li.outdated .body { text-decoration: line-through; color: var(--ink-soft); }
</style>
