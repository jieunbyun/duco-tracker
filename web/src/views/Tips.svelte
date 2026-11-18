<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { query: "", category: null as string | null, sort: "az" as "az" | "new" | "changed", selected: null as string | null };
</script>

<script lang="ts">
  import { tick } from "svelte";
  import { loadTips, addTip, saveTip, deleteTip, parseQuery, matches, score, hits, highlight } from "../lib/tips";
  import type { Tip, TipFields } from "../lib/tips";
  import { undoable } from "../lib/undo.svelte";
  import TipEditor from "../lib/TipEditor.svelte";

  const NONE = "\u0000none"; // the "No category" filter

  let tips = $state<Tip[]>([]);
  let loading = $state(true);
  let error = $state("");
  let query = $state(last.query);
  let category = $state<string | null>(last.category);
  let sort = $state(last.sort);
  let selected = $state<string | null>(last.selected);
  let opened = $state(false); // on a phone: the topic is showing instead of the list
  let focusOnOpen = $state<"title" | "add" | null>(null);
  let searchEl = $state<HTMLInputElement>();
  let listEl = $state<HTMLElement>();

  $effect(() => {
    Object.assign(last, { query, category, sort, selected });
  });

  async function load() {
    try {
      tips = await loadTips();
      error = "";
      if (!selected || !tips.some((t) => t.id === selected)) selected = results[0]?.id ?? null;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  const q = $derived(parseQuery(query));
  const categories = $derived.by(() => {
    const n = new Map<string, number>();
    for (const t of tips) if (t.category?.trim()) n.set(t.category.trim(), (n.get(t.category.trim()) ?? 0) + 1);
    return [...n.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  });
  const uncategorised = $derived(tips.filter((t) => !t.category?.trim()).length);
  const inCategory = (t: Tip) =>
    category === null || (category === NONE ? !t.category?.trim() : t.category?.trim() === category);

  const results = $derived.by(() => {
    const order = (a: Tip, b: Tip) =>
      sort === "az" ? a.title.localeCompare(b.title, undefined, { sensitivity: "base", numeric: true })
      : sort === "new" ? b.created_at.localeCompare(a.created_at)
      : b.updated_at.localeCompare(a.updated_at);
    const found = tips.filter((t) => inCategory(t) && matches(t, q));
    return q.marks.length ? found.sort((a, b) => score(b, q) - score(a, q) || order(a, b)) : found.sort(order);
  });
  const current = $derived(tips.find((t) => t.id === selected) ?? null);
  const sel = $derived(results.findIndex((t) => t.id === selected));

  // As you type, the best match is the one shown (as in "Everything").
  function onQuery() {
    selected = results[0]?.id ?? selected;
  }
  function pickCategory(c: string | null) {
    category = category === c ? null : c;
    selected = results[0]?.id ?? selected;
  }

  function show(id: string, open = false) {
    selected = id;
    if (open) opened = true;
    tick().then(() => listEl?.querySelector<HTMLElement>(`[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" }));
  }

  function searchKeys(ev: KeyboardEvent) {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      if (!results.length) return;
      ev.preventDefault();
      const step = ev.key === "ArrowDown" ? 1 : -1;
      const i = sel < 0 ? (step > 0 ? 0 : results.length - 1) : Math.min(results.length - 1, Math.max(0, sel + step));
      show(results[i].id);
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (results.length) show(results[Math.max(sel, 0)].id, true);
      else if (query.trim()) create(query.trim().replace(/^"|"$/g, ""));
    } else if (ev.key === "Escape") {
      if (query) { ev.preventDefault(); query = ""; onQuery(); }
    }
  }

  // "/" or Ctrl+K from anywhere in the tab goes to the search box.
  function globalKeys(ev: KeyboardEvent) {
    const el = document.activeElement as HTMLElement | null;
    const typing = !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
    if (((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") || (ev.key === "/" && !typing && !ev.ctrlKey && !ev.metaKey)) {
      if (document.querySelector("dialog[open]")) return;
      ev.preventDefault();
      opened = false;
      searchEl?.focus();
      searchEl?.select();
    }
  }

  async function create(title = "") {
    try {
      const t = await undoable("Added tip topic", () =>
        addTip({ title: title || "New topic", category: category && category !== NONE ? category : null }));
      tips = [t, ...tips];
      if (!title) query = "";
      focusOnOpen = title ? "add" : "title";
      show(t.id, true);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function update(id: string, fields: Partial<TipFields>, label: string) {
    tips = tips.map((t) => (t.id === id ? { ...t, ...fields } : t));
    try {
      const at = await undoable(label, () => saveTip(id, fields));
      tips = tips.map((t) => (t.id === id ? { ...t, updated_at: at } : t));
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
      await load();
    }
  }

  async function remove(t: Tip) {
    if (!confirm(`Delete the topic “${t.title}” and its checklist?`)) return;
    const i = results.findIndex((r) => r.id === t.id);
    try {
      await undoable("Deleted tip topic", () => deleteTip(t.id));
      tips = tips.filter((x) => x.id !== t.id);
      selected = results[Math.min(i, results.length - 1)]?.id ?? null;
      opened = false;
    } catch (e) {
      error = (e as Error).message;
    }
  }
</script>

<svelte:window onkeydown={globalKeys} />

{#snippet lit(text: string)}{#each highlight(text, q.marks) as p, i (i)}{#if p.hit}<mark>{p.s}</mark>{:else}{p.s}{/if}{/each}{/snippet}

<section class="tips" class:opened>
  <div class="head">
    <div>
      <span class="eyebrow">Tips</span>
      <h1>Tips &amp; checklists</h1>
    </div>
    <button class="primary" onclick={() => create()}>+ New topic</button>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  <div class="panes">
    <div class="finder">
      <div class="search">
        <input bind:this={searchEl} value={query} oninput={(e) => { query = e.currentTarget.value; onQuery(); }} onkeydown={searchKeys} type="search"
               placeholder="Search titles, items and notes…" aria-label="Search tips" autocomplete="off" spellcheck="false" />
        {#if !query}<kbd title="Press / or Ctrl+K to search from anywhere in the tab">/</kbd>{/if}
      </div>
      <p class="syntax muted">
        words in any order · <code>"exact phrase"</code> · <code>a|b</code> either · <code>!word</code> not · ↑ ↓ to move, Enter to open
      </p>

      {#if categories.length}
        <div class="cats" role="group" aria-label="Category">
          <button class="chip" class:on={category === null} onclick={() => pickCategory(null)}>All <span>{tips.length}</span></button>
          {#each categories as [c, n] (c)}
            <button class="chip" class:on={category === c} onclick={() => pickCategory(c)}>{c} <span>{n}</span></button>
          {/each}
          {#if uncategorised}
            <button class="chip" class:on={category === NONE} onclick={() => pickCategory(NONE)}>No category <span>{uncategorised}</span></button>
          {/if}
        </div>
      {/if}

      <div class="status">
        <span class="muted">
          {#if loading}Loading…{:else}{results.length} of {tips.length} {tips.length === 1 ? "topic" : "topics"}{/if}
        </span>
        <label class="sort">Sort
          <select bind:value={sort}>
            <option value="az">A–Z</option>
            <option value="new">Newest</option>
            <option value="changed">Recently changed</option>
          </select>
        </label>
      </div>

      <ul class="results" bind:this={listEl}>
        {#each results as t (t.id)}
          {@const found = hits(t, q)}
          {@const done = t.items.filter((i) => i.done).length}
          <li>
            <button class="hit" class:sel={t.id === selected} data-id={t.id} aria-current={t.id === selected}
                    onclick={() => show(t.id, true)}>
              <span class="line">
                <span class="title">{@render lit(t.title)}</span>
                {#if t.category}<span class="cat">{@render lit(t.category)}</span>{/if}
                <span class="count muted" title="{done} of {t.items.length} ticked">{t.items.length ? `${done}/${t.items.length}` : ""}</span>
              </span>
              {#each found as s, i (i)}<span class="snip">{@render lit(s)}</span>{/each}
            </button>
          </li>
        {/each}
      </ul>

      {#if !loading && !results.length}
        {#if query.trim()}
          <p class="muted empty">Nothing matches.</p>
          <button onclick={() => create(query.trim().replace(/^"|"$/g, ""))}>+ Create “{query.trim().replace(/^"|"$/g, "")}” <kbd>Enter</kbd></button>
        {:else if tips.length}
          <p class="muted empty">No topics in this category.</p>
        {:else}
          <p class="muted empty">No topics yet. Start one — a checklist for submitting a paper, setting up a lab
            computer, examining a thesis — and find it again here by typing any word in it.</p>
        {/if}
      {/if}
    </div>

    <div class="detail">
      {#if current}
        <button class="back" onclick={() => (opened = false)}>← All topics</button>
        {#key current.id}
          <TipEditor tip={current} marks={q.marks} categories={categories.map(([c]) => c)} focus={focusOnOpen}
                     onupdate={(fields, label) => update(current.id, fields, label)}
                     ondelete={() => remove(current)} onfocused={() => (focusOnOpen = null)} />
        {/key}
      {:else if !loading && tips.length}
        <p class="muted">Pick a topic on the left.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
  .head h1 { margin: 0; }
  .panes { display: grid; grid-template-columns: minmax(0, 22rem) minmax(0, 1fr); gap: 1.5rem; align-items: start; }
  .finder { position: sticky; top: 4rem; display: flex; flex-direction: column; gap: 0.5rem; max-height: calc(100vh - 5rem); font-family: var(--font-ui); }
  .search { position: relative; }
  .search input { font-size: 1rem; padding: 0.55rem 2.2rem 0.55rem 0.7rem; }
  .search kbd { position: absolute; right: 0.55rem; top: 50%; transform: translateY(-50%); }
  kbd {
    font-family: var(--font-ui); font-size: 0.72rem; color: var(--ink-soft); border: 1px solid var(--rule);
    border-radius: 4px; padding: 0 0.35rem; background: var(--panel);
  }
  .syntax { margin: 0; font-size: 0.74rem; line-height: 1.4; }
  .syntax code { font-size: 0.72rem; background: var(--panel); padding: 0 0.2rem; border-radius: 3px; }
  .cats { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .chip { font-size: 0.78rem; padding: 0.15rem 0.6rem; border-radius: 999px; background: none; }
  .chip span { color: var(--ink-soft); margin-left: 0.15rem; }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .chip.on span { color: inherit; opacity: 0.8; }
  .status { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; font-size: 0.8rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.3rem; }
  .sort { display: flex; align-items: center; gap: 0.35rem; color: var(--ink-soft); }
  .sort select { width: auto; padding: 0.15rem 0.3rem; font-size: 0.8rem; }
  .results { list-style: none; margin: 0; padding: 0; overflow-y: auto; min-height: 0; }
  .hit {
    width: 100%; display: grid; gap: 0.1rem; text-align: left; background: none; border: none; border-radius: var(--radius);
    padding: 0.4rem 0.5rem; font-size: 0.9rem;
  }
  .hit:hover { background: var(--panel); }
  .hit.sel { background: var(--panel); box-shadow: inset 3px 0 0 var(--accent); }
  .line { display: flex; align-items: baseline; gap: 0.5rem; min-width: 0; }
  .title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cat { font-size: 0.72rem; color: var(--ink-soft); border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.45rem; white-space: nowrap; }
  .count { margin-left: auto; font-size: 0.75rem; font-variant-numeric: tabular-nums; }
  .snip { font-size: 0.8rem; color: var(--ink-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .snip::before { content: "· "; }
  .empty { font-size: 0.88rem; }
  :global(.tips mark) { background: color-mix(in srgb, var(--series-4) 40%, transparent); color: inherit; border-radius: 2px; padding: 0 1px; }
  .back { display: none; margin-bottom: 0.8rem; }
  @media (max-width: 48rem) {
    .panes { grid-template-columns: 1fr; }
    .finder { position: static; max-height: none; }
    .tips.opened .finder, .tips:not(.opened) .detail { display: none; }
    .back { display: inline-block; }
  }
</style>
