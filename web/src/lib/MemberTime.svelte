<script lang="ts">
  // Where a member's time goes (the Members tab): for the period you choose, the
  // share that went to each shared project, overall and week by week. Only shares:
  // their hours are theirs, and can't be read here.
  import { addDays, fmtDay, today, weekStart } from "./dates";
  import { loadPeriodShares, loadTimeShares } from "./actionTime";
  import type { TimeShare } from "./actionTime";
  import type { GroupProject } from "./group";

  type Props = { userId: string; projects: GroupProject[] };
  let { userId, projects }: Props = $props();

  let period = $state("4w");
  let custom = $state({ from: addDays(today(), -27), to: today() });
  const range = $derived.by((): { from: string | null; to: string | null } => {
    if (period === "custom") return { from: custom.from || null, to: custom.to || null };
    if (period === "week") return { from: weekStart(today()), to: null };
    if (period === "4w") return { from: addDays(today(), -27), to: null };
    if (period === "3m") return { from: addDays(today(), -90), to: null };
    return { from: null, to: null };
  });

  let overall = $state<Omit<TimeShare, "week">[]>([]);
  let shares = $state<TimeShare[]>([]);
  let request = 0;
  $effect(() => {
    const id = ++request;
    const { from, to } = range;
    Promise.all([loadPeriodShares(userId, from, to), loadTimeShares(userId)]).then(([o, s]) => {
      if (id === request) [overall, shares] = [o, s];
    });
  });

  // the weeks that touch the period (each week's shares are of the whole week)
  const weeks = $derived([...new Set(shares.map((s) => s.week))]
    .filter((w) => (!range.from || addDays(w, 6) >= range.from) && (!range.to || w <= range.to)));
  const titleOf = (id: string) => projects.find((p) => p.id === id)?.title ?? "Shared project";
</script>

{#snippet table(rows: Omit<TimeShare, "week">[])}
  <table>
    <tbody>
      {#each rows as s (s.group_project_id)}
        <tr><td>{titleOf(s.group_project_id)}</td><td class="n">{s.share}%</td></tr>
      {/each}
    </tbody>
  </table>
{/snippet}

<div class="bar">
  <label>Period
    <select bind:value={period}>
      <option value="week">this week</option>
      <option value="4w">last 4 weeks</option>
      <option value="3m">last 3 months</option>
      <option value="all">all</option>
      <option value="custom">custom…</option>
    </select>
  </label>
  {#if period === "custom"}
    <input type="date" bind:value={custom.from} max={custom.to || undefined} aria-label="From" /> –
    <input type="date" bind:value={custom.to} min={custom.from || undefined} aria-label="To" />
  {/if}
</div>

{#if overall.length}
  <section class="week whole">
    <h3>The whole period</h3>
    {@render table(overall)}
  </section>
  {#if weeks.length > 1}
    {#each weeks as w (w)}
      <section class="week">
        <h3>Week of {fmtDay(w)}</h3>
        {@render table(shares.filter((s) => s.week === w))}
      </section>
    {/each}
  {/if}
{:else}
  <p class="muted">No time logged in this period.</p>
{/if}

<style>
  .bar { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin-bottom: 0.6rem; font-family: var(--font-ui); font-size: 0.8rem; }
  .bar select, .bar input { width: auto; }
  .week { border-top: 1px solid var(--rule); padding: 0.3rem 0; font-family: var(--font-ui); }
  .whole { padding-bottom: 0.6rem; }
  h3 { margin: 0 0 0.15rem; font-size: 0.8rem; font-weight: 500; color: var(--ink-soft); }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  td { padding: 0.1rem 0.5rem 0.1rem 0; overflow-wrap: anywhere; }
  .n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; width: 4rem; }
</style>
