<script lang="ts">
  // The actions ticked off, newest first, by month: when, which project (and
  // milestone), and the comments and links each gathered on the way.
  import type { Action } from "./actions";
  import type { GroupProject, PlanningRef } from "./group";
  import { linkName } from "./group";
  import { fmtDay } from "./dates";

  type Props = {
    load: () => Promise<Action[]>; // fetched when first opened
    projects: GroupProject[];
    planning?: PlanningRef[];
    filter: string; // "g:<id>", "p:<id>", or "" for all
  };
  let { load, projects, planning = [], filter }: Props = $props();

  let done = $state<Action[] | null>(null);
  let error = $state("");
  async function open(ev: Event) {
    if (!(ev.target as HTMLDetailsElement).open || done) return;
    try { done = await load(); } catch (e) { error = (e as Error).message; }
  }

  const keyOf = (a: Action) => (a.project_id ? `p:${a.project_id}` : a.group_project_id ? `g:${a.group_project_id}` : "");
  const shown = $derived((done ?? []).filter((a) => a.is_done && (!filter || keyOf(a) === filter)));
  const months = $derived.by(() => {
    const out: { label: string; items: Action[] }[] = [];
    for (const a of shown) {
      const d = a.done_at ?? a.created_at;
      const label = new Date(d).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
      const m = out.find((x) => x.label === label) ?? (out.push({ label, items: [] }), out[out.length - 1]);
      m.items.push(a);
    }
    return out;
  });
  function where(a: Action): string {
    if (a.project_id) {
      const p = planning.find((x) => x.id === a.project_id);
      const m = p?.milestones.find((x) => x.id === a.milestone_id);
      return `${p?.name ?? "Planning project"}${m ? ` › ${m.title}` : ""}`;
    }
    return projects.find((x) => x.id === a.group_project_id)?.title ?? "Shared project";
  }
</script>

<details class="history" ontoggle={open}>
  <summary>Actions done{done ? ` (${shown.length})` : ""}{filter ? " on this project" : ""}</summary>
  {#if error}<p class="error">{error}</p>{/if}
  {#if !done}<p class="muted small">Loading…</p>
  {:else if !shown.length}<p class="muted small">No actions ticked off yet{filter ? " on this project" : ""}.</p>
  {:else}
    {#each months as m (m.label)}
      <h3>{m.label}</h3>
      <ul>
        {#each m.items as a (a.id)}
          <li>
            <span class="when">{a.done_at ? fmtDay(a.done_at.slice(0, 10)) : ""}</span>
            <span class="what">
              <span class="name">{a.title}</span>
              {#if !filter}<span class="muted small"> · {where(a)}</span>{/if}
              {#if a.note}<span class="note">{a.note}</span>{/if}
              {#if a.links.length}
                <span class="links">{#each a.links as l (l)}<a href={l} target="_blank" rel="noopener noreferrer" title={l}>↗ {linkName(l)}</a>{/each}</span>
              {/if}
            </span>
          </li>
        {/each}
      </ul>
    {/each}
  {/if}
</details>

<style>
  .history { margin: 0.4rem 0 1rem; font-family: var(--font-ui); }
  summary { cursor: pointer; font-size: 0.9rem; font-weight: 600; }
  h3 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-soft); margin: 0.7rem 0 0.2rem; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: grid; grid-template-columns: 5.5rem 1fr; gap: 0.6rem; padding: 0.25rem 0; border-top: 1px solid var(--rule); font-size: 0.86rem; }
  .when { color: var(--ink-soft); font-size: 0.8rem; }
  .what { display: grid; gap: 0.1rem; }
  .name { font-weight: 500; }
  .note { font-size: 0.8rem; color: var(--ink-soft); white-space: pre-wrap; }
  .links { display: flex; flex-wrap: wrap; gap: 0.3rem; font-size: 0.78rem; }
  .links a { padding: 0 0.4rem; border: 1px solid var(--rule); border-radius: 999px; text-decoration: none; }
  .small { font-size: 0.8rem; }
</style>
