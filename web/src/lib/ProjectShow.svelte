<script lang="ts">
  // Which projects to list, in Projects and the Logbook: the value is "" for the
  // current ones, "done", "all", or one project's id (see projectsToShow).
  import type { Snippet } from "svelte";
  import type { GroupProject } from "./group";

  type Props = { value: string; projects: GroupProject[]; children?: Snippet };
  let { value = $bindable(""), projects, children }: Props = $props();
  const done = $derived(projects.filter((p) => p.status === "done").length);
</script>

<label>Show
  <select bind:value>
    <option value="">current projects</option>
    <option value="done">done ({done})</option>
    <option value="all">all</option>
    {#if projects.length}
      <optgroup label="Per project">{#each projects as p (p.id)}<option value={p.id}>{p.title}</option>{/each}</optgroup>
    {/if}
    {@render children?.()}
  </select>
</label>

<style>
  label { font-size: 0.8rem; font-family: var(--font-ui); }
  select { width: auto; }
</style>
