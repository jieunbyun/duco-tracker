<script lang="ts">
  // The actions ticked off, newest first, by month: when, which project (and
  // milestone), and the thread of comments and links each gathered.
  import { loadActionComments } from "./actions";
  import type { Action, ActionComment } from "./actions";
  import type { GroupProject, GroupMilestone, Member, PlanningRef } from "./group";
  import { linkName } from "./group";
  import { fmtDay } from "./dates";

  type Props = {
    load: () => Promise<Action[]>; // fetched when first opened
    projects: GroupProject[];
    planning?: PlanningRef[];
    groupMilestones?: GroupMilestone[];
    members?: Member[];
    me?: string;
    filter: string; // "g:<id>", "p:<id>", or "" for all
  };
  let { load, projects, planning = [], groupMilestones = [], members = [], me = "", filter }: Props = $props();

  let done = $state<Action[] | null>(null);
  let thread = $state<ActionComment[]>([]);
  let error = $state("");
  async function open(ev: Event) {
    if (!(ev.target as HTMLDetailsElement).open || done) return;
    try {
      const all = (await load()).filter((a) => a.is_done);
      thread = await loadActionComments(all.map((a) => a.id));
      done = all.sort((a, b) => (b.done_at ?? "").localeCompare(a.done_at ?? ""));
    } catch (e) {
      error = (e as Error).message;
    }
  }

  const keyOf = (a: Action) => (a.project_id ? `p:${a.project_id}` : a.group_project_id ? `g:${a.group_project_id}` : "");
  const shown = $derived((done ?? []).filter((a) => !filter || keyOf(a) === filter));
  const months = $derived.by(() => {
    const out: { label: string; items: Action[] }[] = [];
    for (const a of shown) {
      const label = new Date(a.done_at ?? a.created_at).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
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
    const m = groupMilestones.find((x) => x.id === a.group_milestone_id);
    return `${projects.find((x) => x.id === a.group_project_id)?.title ?? "Shared project"}${m ? ` › ${m.title}` : ""}`;
  }
  const nameOf = (uid: string) => (uid === me ? "you" : members.find((m) => m.user_id === uid)?.display_name ?? "—");
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
              {#if !filter}<span class="muted small">{where(a)}</span>{/if}
              {#each thread.filter((c) => c.action_id === a.id) as c (c.id)}
                <span class="cmt">{c.created_at.slice(0, 10)}{c.author_id !== me ? ` · ${nameOf(c.author_id)}` : ""}: {c.body ?? ""}
                  {#each c.links as l (l)}<a href={l} target="_blank" rel="noopener noreferrer" title={l}> ↗ {linkName(l)}</a>{/each}</span>
              {/each}
            </span>
          </li>
        {/each}
      </ul>
    {/each}
  {/if}
</details>

<style>
  .history { margin: 1rem 0; font-family: var(--font-ui); }
  summary { cursor: pointer; font-size: 0.9rem; font-weight: 600; }
  h3 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-soft); margin: 0.7rem 0 0.2rem; }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: grid; grid-template-columns: 5.5rem 1fr; gap: 0.6rem; padding: 0.25rem 0; border-top: 1px solid var(--rule); font-size: 0.86rem; }
  .when { color: var(--ink-soft); font-size: 0.8rem; }
  .what { display: grid; gap: 0.1rem; }
  .name { font-weight: 500; }
  .cmt { font-size: 0.8rem; color: var(--ink-soft); }
  .small { font-size: 0.8rem; }
</style>
