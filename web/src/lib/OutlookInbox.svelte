<script lang="ts">
  import { saveTodo, saveSlot, fmtHours } from "./data";
  import type { Taxonomy, Project, Todo, Slot } from "./data";
  import { dismissOutlook } from "./outlook";
  import { parse } from "./dates";
  import { LIVE_STATUSES } from "./plan";

  type Props = {
    todos: Todo[];
    slots: Slot[];
    tax: Taxonomy;
    projects: Project[];
    onchange: () => void;
    remember: (label: string, undo: () => Promise<unknown>) => void;
  };
  let { todos, slots, tax, projects, onchange, remember }: Props = $props();

  // Per-item choices, kept while you work down the list.
  type Draft = { category_id: string; project_id: string; start: string; end: string; hours: number | null };
  let drafts = $state<Record<string, Draft>>({});
  let busy = $state<string | null>(null);
  let error = $state("");

  const slotOf = (t: Todo) => slots.find((s) => s.todo_id === t.id) ?? null;

  // A draft per item, made before drawing (state may not change mid-render).
  $effect.pre(() => {
    for (const t of todos) {
      if (drafts[t.id]) continue;
      const s = slotOf(t);
      drafts[t.id] = {
        category_id: t.category_id ?? "",
        project_id: t.project_id ?? "",
        start: s?.start_time?.slice(0, 5) ?? "",
        end: s?.end_time?.slice(0, 5) ?? "",
        hours: t.est_hours,
      };
    }
  });

  const groups = $derived(tax.areas.map((a) => ({ area: a, cats: tax.categories.filter((c) => c.area_id === a.id) })));
  const projectsFor = (categoryId: string) =>
    projects.filter((p) => (!categoryId || p.category_id === categoryId) && LIVE_STATUSES.has(p.status))
      .sort((a, b) => a.name.localeCompare(b.name));

  const day = (d: string) => parse(d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  const repeats = (t: Todo) => !!t.source_key?.includes("|");
  const snap = <T extends object>(x: T): T => ({ ...($state.snapshot(x) as object) }) as T;

  async function run(t: Todo, fn: () => Promise<void>) {
    busy = t.id;
    error = "";
    try {
      await fn();
      delete drafts[t.id];
      onchange();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = null;
    }
  }

  function keep(t: Todo) {
    const d = drafts[t.id];
    if (!d) return;
    const s = slotOf(t);
    if (!t.source_all_day && !(d.start && d.end && d.end > d.start)) return void (error = "The end time must be after the start.");
    const before = snap(t);
    const slotBefore = s ? snap(s) : null;
    return run(t, async () => {
      const len = t.source_all_day ? d.hours : Math.round(((+d.end.slice(0, 2) * 60 + +d.end.slice(3) - +d.start.slice(0, 2) * 60 - +d.start.slice(3)) / 60) * 100) / 100;
      await saveTodo(t.id, { category_id: d.category_id || null, project_id: d.project_id || null, est_hours: len, reviewed: true });
      if (s) {
        await saveSlot(s.id, t.source_all_day
          ? { planned_hours: null }
          : { start_time: d.start, end_time: d.end, planned_hours: len });
      }
      remember(`Kept “${t.title}”`, async () => {
        await saveTodo(t.id, { category_id: before.category_id, project_id: before.project_id, est_hours: before.est_hours, reviewed: false });
        if (slotBefore) {
          await saveSlot(slotBefore.id, { start_time: slotBefore.start_time, end_time: slotBefore.end_time, planned_hours: slotBefore.planned_hours });
        }
      });
    });
  }

  /** Irrelevant: this occurrence, or (all) every occurrence of the series, now and on later syncs. */
  function dismiss(t: Todo, all: boolean) {
    const s = slotOf(t);
    return run(t, async () => {
      const undo = await dismissOutlook(snap(t), s ? snap(s) : null, all);
      remember(all ? `Ignored “${t.title}” and its repeats` : `Ignored “${t.title}”`, undo);
    });
  }
</script>

<div class="inbox">
  {#if error}<p class="error">{error}</p>{/if}
  <ul>
    {#each todos as t (t.id)}
      {@const d = drafts[t.id]}
      {#if d}
      <li class:busy={busy === t.id}>
        <div class="what">
          <span class="when">{day(t.due_on)} · {t.source_all_day ? "all day" : `${d.start}–${d.end}`}</span>
          <strong class="title">{t.title}</strong>
          {#if t.source_free}<span class="tag">Free</span>{/if}
          {#if t.source_all_day}<span class="tag">all day</span>{/if}
          {#if repeats(t)}<span class="tag">repeats</span>{/if}
          {#if t.note}<span class="muted where">{t.note}</span>{/if}
        </div>
        <div class="how">
          <select bind:value={d.category_id} aria-label="Category" onchange={() => (d.project_id = "")}>
            <option value="">Category…</option>
            {#each groups as g (g.area.id)}
              <optgroup label={g.area.label}>
                {#each g.cats as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
              </optgroup>
            {/each}
          </select>
          <select bind:value={d.project_id} aria-label="Project">
            <option value="">— no project —</option>
            {#each projectsFor(d.category_id) as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
          </select>
          {#if t.source_all_day}
            <label class="hrs">h <input type="number" min="0" step="0.25" bind:value={d.hours} aria-label="Hours" /></label>
          {:else}
            <input type="time" step="300" bind:value={d.start} aria-label="Start" />
            <input type="time" step="300" bind:value={d.end} aria-label="End" />
          {/if}
        </div>
        <div class="acts">
          <button class="primary" disabled={busy === t.id} onclick={() => keep(t)}>Keep</button>
          <button disabled={busy === t.id} onclick={() => dismiss(t, false)}>Irrelevant</button>
          {#if repeats(t)}
            <button disabled={busy === t.id} onclick={() => dismiss(t, true)} title="Ignore every occurrence, now and in future syncs">Irrelevant — all repeats</button>
          {/if}
        </div>
      </li>
      {/if}
    {/each}
  </ul>
  {#if todos.some((t) => t.est_hours)}
    <p class="muted small">Unreviewed events: {fmtHours(todos.reduce((s, t) => s + (t.est_hours ?? 0), 0))} — not counted as planned until kept.</p>
  {/if}
</div>

<style>
  .inbox { font-family: var(--font-ui); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
  li {
    display: grid;
    grid-template-columns: minmax(12rem, 1.2fr) minmax(16rem, 2fr) auto;
    gap: 0.4rem 0.8rem;
    align-items: center;
    background: var(--panel);
    border: 1px dashed var(--rule);
    border-radius: var(--radius);
    padding: 0.5rem 0.7rem;
  }
  li.busy { opacity: 0.6; }
  .what { display: flex; flex-wrap: wrap; gap: 0.2rem 0.5rem; align-items: baseline; min-width: 0; }
  .when { font-size: 0.78rem; color: var(--ink-soft); width: 100%; font-variant-numeric: tabular-nums; }
  .title { font-size: 0.9rem; overflow-wrap: anywhere; }
  .tag { font-size: 0.68rem; border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.4rem; color: var(--ink-soft); }
  .where { font-size: 0.75rem; width: 100%; }
  .how { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .how select { width: auto; max-width: 12rem; font-size: 0.8rem; padding: 0.25rem 0.35rem; }
  .how input[type="time"] { width: 6.5rem; font-size: 0.8rem; padding: 0.25rem 0.35rem; }
  .hrs { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; color: var(--ink-soft); }
  .hrs input { width: 4.5rem; font-size: 0.8rem; padding: 0.25rem 0.35rem; }
  .acts { display: flex; flex-wrap: wrap; gap: 0.3rem; justify-content: flex-end; }
  .acts button { font-size: 0.8rem; padding: 0.3rem 0.6rem; }
  .small { font-size: 0.8rem; margin: 0.4rem 0 0; }
  @media (max-width: 60rem) {
    li { grid-template-columns: 1fr; }
    .acts { justify-content: flex-start; }
  }
</style>
