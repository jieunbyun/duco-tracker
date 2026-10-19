<script lang="ts">
  import { saveCategory, addCategory } from "./data";
  import type { Taxonomy, Category, Area } from "./data";

  type Props = { tax: Taxonomy; onsaved: () => void };
  let { tax, onsaved }: Props = $props();

  const KIND: Record<string, string> = {
    routine: "routine",
    project: "project-based",
    mixed: "mixed",
    misc: "miscellaneous",
    email: "email",
  };

  // adding a category to an area
  let addingTo = $state<string | null>(null);
  let newLabel = $state("");
  let newKind = $state("project");

  async function add(a: Area) {
    if (!newLabel.trim()) return (error = "Give the category a name.");
    busy = true;
    error = "";
    try {
      await addCategory(a, newLabel, newKind, tax.categories);
      addingTo = null;
      newLabel = "";
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  let editing = $state<string | null>(null);
  let draft = $state("");
  let draftLabel = $state("");
  let draftKind = $state("project");
  let busy = $state(false);
  let error = $state("");

  function open(c: Category) {
    editing = c.id;
    draft = c.description ?? "";
    draftLabel = c.label;
    draftKind = c.kind;
    error = "";
  }

  async function save(c: Category) {
    if (!draftLabel.trim()) return (error = "The category needs a name.");
    busy = true;
    error = "";
    try {
      await saveCategory(c.id, { label: draftLabel.trim(), kind: draftKind, description: draft.trim() || null });
      editing = null;
      onsaved();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="notes">
  {#each tax.areas as a (a.id)}
    <div class="area">
      <div class="area-head">
        <h3>{a.label}</h3>
        {#if addingTo !== a.id}
          <button class="edit" onclick={() => { addingTo = a.id; newLabel = ""; newKind = "project"; error = ""; }}>+ Category</button>
        {/if}
      </div>
      {#if addingTo === a.id}
        <div class="new">
          <input bind:value={newLabel} placeholder="Name, e.g. Project lead" aria-label="Category name" />
          <select bind:value={newKind} aria-label="Kind">
            <option value="project">project-based — planned with projects and hours</option>
            <option value="routine">routine — counted at your recent pace</option>
            <option value="mixed">mixed</option>
            <option value="misc">miscellaneous</option>
          </select>
          {#if error}<p class="error">{error}</p>{/if}
          <div class="actions">
            <button class="primary" disabled={busy} onclick={() => add(a)}>Add</button>
            <button disabled={busy} onclick={() => (addingTo = null)}>Cancel</button>
          </div>
        </div>
      {/if}
      <ul>
        {#each tax.categories.filter((c) => c.area_id === a.id) as c (c.id)}
          <li>
            <div class="head">
              <span class="name">{c.label}</span>
              <span class="kind muted">{KIND[c.kind] ?? c.kind}</span>
              {#if editing !== c.id}
                <button class="edit" onclick={() => open(c)}>Edit</button>
              {/if}
            </div>
            {#if editing === c.id}
              <div class="fields">
                <input bind:value={draftLabel} aria-label="Name" />
                {#if c.kind === "email"}
                  <span class="muted fixed">email — shared equally across the areas</span>
                {:else}
                  <select bind:value={draftKind} aria-label="Kind">
                    <option value="project">project-based — planned with projects and hours</option>
                    <option value="routine">routine — counted at your recent pace</option>
                    <option value="mixed">mixed</option>
                    <option value="misc">miscellaneous</option>
                  </select>
                {/if}
              </div>
              {#if draftKind !== c.kind}
                <p class="muted small">
                  {draftKind === "routine" || draftKind === "misc"
                    ? "Its projects will count through routine time from now on, not as planned commitments."
                    : "Its projects will count as planned commitments from now on."}
                </p>
              {/if}
              <textarea rows="3" bind:value={draft} placeholder="Note: what belongs here — e.g. tasks, examples, what does not"></textarea>
              {#if error}<p class="error">{error}</p>{/if}
              <div class="actions">
                <button class="primary" disabled={busy} onclick={() => save(c)}>Save</button>
                <button disabled={busy} onclick={() => (editing = null)}>Cancel</button>
              </div>
            {:else if c.description}
              <p class="desc">{c.description}</p>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
  {/each}
</div>

<style>
  .notes { display: grid; gap: 1rem; font-family: var(--font-ui); }
  .area h3 { font-size: 0.95rem; margin: 0; }
  .area-head { display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.3rem; }
  .area-head .edit { margin-left: 0; }
  .new { display: grid; gap: 0.4rem; max-width: 30rem; margin: 0.2rem 0 0.6rem; }
  .fields { display: grid; grid-template-columns: minmax(10rem, 1fr) minmax(12rem, 1.4fr); gap: 0.4rem; margin-top: 0.4rem; }
  .fixed { font-size: 0.8rem; align-self: center; }
  .small { font-size: 0.78rem; margin: 0.3rem 0 0; }
  @media (max-width: 40rem) { .fields { grid-template-columns: 1fr; } }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.15rem; }
  li { padding: 0.4rem 0.5rem; border-radius: var(--radius); }
  li:hover { background: var(--panel); }
  .head { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
  .name { font-weight: 600; font-size: 0.9rem; }
  .kind { font-size: 0.75rem; }
  .edit { margin-left: auto; font-size: 0.75rem; padding: 0.1rem 0.5rem; }
  .desc { margin: 0.2rem 0 0; font-size: 0.85rem; white-space: pre-line; color: var(--ink); }
  textarea { margin-top: 0.4rem; font-size: 0.88rem; }
  .actions { display: flex; gap: 0.5rem; margin-top: 0.4rem; }
</style>
