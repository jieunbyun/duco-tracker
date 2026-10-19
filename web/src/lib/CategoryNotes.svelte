<script lang="ts">
  import { saveCategoryNote } from "./data";
  import type { Taxonomy, Category } from "./data";

  type Props = { tax: Taxonomy; onsaved: () => void };
  let { tax, onsaved }: Props = $props();

  const KIND: Record<string, string> = {
    routine: "routine",
    project: "project-based",
    mixed: "mixed",
    misc: "miscellaneous",
    email: "email",
  };

  let editing = $state<string | null>(null);
  let draft = $state("");
  let busy = $state(false);
  let error = $state("");

  function open(c: Category) {
    editing = c.id;
    draft = c.description ?? "";
    error = "";
  }

  async function save(c: Category) {
    busy = true;
    error = "";
    try {
      await saveCategoryNote(c.id, draft.trim() || null);
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
      <h3>{a.label}</h3>
      <ul>
        {#each tax.categories.filter((c) => c.area_id === a.id) as c (c.id)}
          <li>
            <div class="head">
              <span class="name">{c.label}</span>
              <span class="kind muted">{KIND[c.kind] ?? c.kind}</span>
              {#if editing !== c.id}
                <button class="edit" onclick={() => open(c)}>{c.description ? "Edit" : "+ Note"}</button>
              {/if}
            </div>
            {#if editing === c.id}
              <textarea rows="3" bind:value={draft} placeholder="What belongs here — e.g. tasks, examples, what does not"></textarea>
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
  .area h3 { font-size: 0.95rem; margin-bottom: 0.3rem; }
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
