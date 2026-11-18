<script lang="ts">
  // One topic: its title, category, checklist and notes, edited where they stand.
  // Each change saves as you leave the field (or tick the box).
  import { onMount, tick } from "svelte";
  import Sortable from "./Sortable.svelte";
  import { linesToItems, tipAsText } from "./tips";
  import type { Tip, TipItem, TipFields } from "./tips";

  type Props = {
    tip: Tip;
    marks: string[]; // search words, to light up the items they are in
    categories: string[];
    focus: "title" | "add" | null;
    onupdate: (fields: Partial<TipFields>, label: string) => void;
    ondelete: () => void;
    onfocused: () => void;
  };
  let { tip, marks, categories, focus, onupdate, ondelete, onfocused }: Props = $props();

  let root = $state<HTMLElement>();
  let titleEl = $state<HTMLInputElement>();
  let addEl = $state<HTMLTextAreaElement>();
  let adding = $state("");
  let copied = $state(false);

  const done = $derived(tip.items.filter((i) => i.done).length);
  const lit = (text: string) => marks.length > 0 && marks.some((w) => text.toLowerCase().includes(w));

  onMount(() => {
    if (focus === "title") titleEl?.select();
    else if (focus === "add") addEl?.focus();
    if (focus) onfocused();
  });

  const setItems = (items: TipItem[], label: string) => onupdate({ items }, label);

  function focusItem(id: string | undefined, atEnd = true) {
    tick().then(() => {
      const el = id ? root?.querySelector<HTMLTextAreaElement>(`textarea[data-item="${id}"]`) : addEl;
      el?.focus();
      if (el && atEnd) el.setSelectionRange(el.value.length, el.value.length);
    });
  }

  function saveTitle(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement;
    const v = el.value.trim();
    if (!v) el.value = tip.title;
    else if (v !== tip.title) onupdate({ title: v }, "Renamed tip topic");
  }
  function saveCategory(ev: Event) {
    const v = (ev.currentTarget as HTMLInputElement).value.trim() || null;
    if (v !== (tip.category ?? null)) onupdate({ category: v }, "Changed tip category");
  }
  function saveNotes(ev: Event) {
    const v = (ev.currentTarget as HTMLTextAreaElement).value.trim() || null;
    if (v !== (tip.notes ?? null)) onupdate({ notes: v }, "Changed tip notes");
  }

  function toggle(id: string) {
    const was = tip.items.find((i) => i.id === id)?.done;
    setItems(tip.items.map((i) => (i.id === id ? { ...i, done: !i.done } : i)), was ? "Unticked item" : "Ticked item");
  }
  function saveItem(id: string, text: string) {
    const v = text.trim();
    const item = tip.items.find((i) => i.id === id);
    if (!item) return;
    if (!v) return removeItem(id);
    if (v !== item.text) setItems(tip.items.map((i) => (i.id === id ? { ...i, text: v } : i)), "Changed item");
  }
  function removeItem(id: string) {
    setItems(tip.items.filter((i) => i.id !== id), "Removed item");
  }
  function itemKeys(ev: KeyboardEvent, id: string) {
    const el = ev.currentTarget as HTMLTextAreaElement;
    const at = tip.items.findIndex((i) => i.id === id);
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      const next = tip.items[at + 1]?.id;
      saveItem(id, el.value);
      focusItem(next);
    } else if (ev.key === "Backspace" && el.value === "") {
      ev.preventDefault();
      const prev = tip.items[at - 1]?.id;
      removeItem(id);
      focusItem(prev);
    } else if (ev.key === "Escape") {
      el.value = tip.items[at]?.text ?? el.value;
      el.blur();
    }
  }

  function add(text: string) {
    const items = linesToItems(text);
    if (!items.length) return;
    setItems([...tip.items, ...items], items.length > 1 ? `Added ${items.length} items` : "Added item");
    adding = "";
    focusItem(undefined);
  }
  function addKeys(ev: KeyboardEvent) {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      add(adding);
    }
  }
  // A pasted list (several lines) becomes several items at once.
  function addPaste(ev: ClipboardEvent) {
    const text = ev.clipboardData?.getData("text/plain") ?? "";
    if (!/\r?\n/.test(text.trim())) return;
    ev.preventDefault();
    add(adding ? `${adding}\n${text}` : text);
  }

  function reorder(ids: string[]) {
    const by = new Map(tip.items.map((i) => [i.id, i]));
    setItems(ids.map((id) => by.get(id)!).filter(Boolean), "Reordered items");
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(tipAsText(tip));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }
</script>

{#snippet row(item: TipItem)}
  <div class="item" class:done={item.done} class:match={lit(item.text)}>
    <input type="checkbox" checked={item.done} onchange={() => toggle(item.id)} aria-label="Done" />
    <textarea rows="1" data-item={item.id} value={item.text} aria-label="Item"
              onchange={(e) => saveItem(item.id, e.currentTarget.value)} onkeydown={(e) => itemKeys(e, item.id)}></textarea>
    <button class="x" title="Remove this item" aria-label="Remove this item" onclick={() => removeItem(item.id)}>✕</button>
  </div>
{/snippet}

<article class="topic" bind:this={root}>
  <input class="title" bind:this={titleEl} value={tip.title} aria-label="Topic title"
         onchange={saveTitle} onkeydown={(e) => e.key === "Enter" && e.currentTarget.blur()} />

  <div class="meta">
    <label>Category
      <input value={tip.category ?? ""} list="tip-categories" placeholder="Your own, or pick one" onchange={saveCategory}
             onkeydown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
      <datalist id="tip-categories">{#each categories as c (c)}<option value={c}></option>{/each}</datalist>
    </label>
    <div class="tools">
      <button onclick={copy} title="Copy the checklist as Markdown">{copied ? "Copied" : "Copy"}</button>
      <button class="danger" onclick={ondelete}>Delete</button>
    </div>
  </div>

  <div class="progress">
    <h2>Checklist</h2>
    {#if tip.items.length}
      <span class="muted">{done} of {tip.items.length} ticked</span>
      <span class="bar" aria-hidden="true"><span style:width="{(100 * done) / tip.items.length}%"></span></span>
      {#if done}
        <button class="small" onclick={() => setItems(tip.items.map((i) => ({ ...i, done: false })), "Unticked all")}>Untick all</button>
      {/if}
    {/if}
  </div>

  <Sortable items={tip.items} {row} onreorder={reorder} />

  <textarea class="add" rows="1" bind:this={addEl} bind:value={adding} onkeydown={addKeys} onpaste={addPaste}
            placeholder="+ Add an item (Enter) — or paste a list to add every line"></textarea>

  <label class="notes">Notes
    <textarea rows="4" value={tip.notes ?? ""} onchange={saveNotes} placeholder="Background, links, why it matters…"></textarea>
  </label>

  <p class="muted stamp">
    Enter moves to the next item · Shift+Enter for a new line · Backspace on an empty item removes it · drag ⠿ to reorder
  </p>
</article>

<style>
  .topic { display: grid; gap: 0.8rem; font-family: var(--font-ui); }
  .title {
    font-family: var(--font); font-size: 1.5rem; font-weight: 600; border-color: transparent; background: none;
    padding: 0.2rem 0.4rem; margin-left: -0.4rem;
  }
  .title:hover { border-color: var(--rule); }
  .meta { display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: flex-end; justify-content: space-between; }
  .meta label { display: grid; gap: 0.2rem; font-size: 0.8rem; color: var(--ink-soft); width: min(18rem, 100%); }
  .tools { display: flex; gap: 0.4rem; }
  .danger { color: var(--danger); }
  .progress { display: flex; flex-wrap: wrap; align-items: center; gap: 0.7rem; font-size: 0.82rem; margin-top: 0.4rem; }
  .progress h2 { margin: 0; font-family: var(--font); }
  .bar { flex: 0 1 8rem; height: 6px; border-radius: 3px; background: var(--track); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .small { font-size: 0.78rem; padding: 0.15rem 0.6rem; }
  .item { display: flex; align-items: flex-start; gap: 0.5rem; border-radius: var(--radius); padding: 0.05rem 0.2rem; }
  .item.match { background: color-mix(in srgb, var(--series-4) 16%, transparent); }
  .item input[type="checkbox"] { width: 1.05rem; height: 1.05rem; margin: 0.45rem 0 0; flex: none; accent-color: var(--accent); cursor: pointer; }
  .item textarea, .add {
    resize: none; field-sizing: content; min-height: 0; border-color: transparent; background: none; padding: 0.25rem 0.4rem;
    line-height: 1.45; overflow: hidden;
  }
  .item textarea { flex: 1; }
  .item textarea:hover { border-color: var(--rule); }
  .item.done textarea { text-decoration: line-through; color: var(--ink-soft); }
  .x { background: none; border: none; color: var(--ink-soft); padding: 0.25rem 0.4rem; opacity: 0; }
  .item:hover .x, .x:focus-visible { opacity: 1; }
  .add { border: 1px dashed var(--rule); margin-left: 1.6rem; width: calc(100% - 1.6rem); }
  .notes { display: grid; gap: 0.25rem; font-size: 0.8rem; color: var(--ink-soft); margin-top: 0.6rem; }
  .notes textarea { font-size: 0.92rem; color: var(--ink); }
  .stamp { font-size: 0.74rem; margin: 0; }
  @media (hover: none) { .x { opacity: 1; } }
</style>
