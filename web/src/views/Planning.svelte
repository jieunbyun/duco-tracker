<script lang="ts">
  import { loadTaxonomy, loadProjects, loadAllHours, targetOn, fmtHours } from "../lib/data";
  import type { Taxonomy, Project, HourRow, Category } from "../lib/data";
  import { horizonRange, projectLoad, areaHorizons, PLANNABLE_KINDS, PACE_DAYS } from "../lib/horizon";
  import type { ProjectLoad } from "../lib/horizon";
  import { fmtDay, today } from "../lib/dates";
  import ProjectEditor from "../lib/ProjectEditor.svelte";
  import Milestones from "../lib/Milestones.svelte";

  let tax = $state<Taxonomy | null>(null);
  let projects = $state<Project[]>([]);
  let hours = $state<HourRow[]>([]);
  let loading = $state(true);
  let error = $state("");

  async function load() {
    try {
      const [t, p, h] = await Promise.all([loadTaxonomy(), loadProjects(), loadAllHours()]);
      tax = t;
      projects = p;
      hours = h;
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // ---- derived figures ----------------------------------------------------
  const horizon = $derived(horizonRange(tax?.horizonMonths ?? 12));

  const actualByProject = $derived.by(() => {
    const m = new Map<string, number>();
    for (const h of hours) if (h.project_id) m.set(h.project_id, (m.get(h.project_id) ?? 0) + h.hours);
    return m;
  });
  const actualByMilestone = $derived.by(() => {
    const m = new Map<string, number>();
    for (const h of hours) if (h.milestone_id) m.set(h.milestone_id, (m.get(h.milestone_id) ?? 0) + h.hours);
    return m;
  });
  const loads = $derived(
    new Map(projects.map((p) => [p.id, projectLoad(p, actualByProject.get(p.id) ?? 0, horizon)] as const)),
  );
  const areaRows = $derived(tax ? areaHorizons(tax, hours, projects, loads, horizon) : []);
  const scale = $derived(Math.max(1, ...areaRows.map((r) => Math.max(r.capacity, r.routine + r.committed))));
  const total = $derived(
    areaRows.reduce(
      (s, r) => ({ capacity: s.capacity + r.capacity, routine: s.routine + r.routine,
                   committed: s.committed + r.committed, free: s.free + r.free }),
      { capacity: 0, routine: 0, committed: 0, free: 0 },
    ),
  );

  const areaIndex = $derived(new Map((tax?.areas ?? []).map((a, i) => [a.id, i])));
  function areaColor(areaId: string): string {
    const i = areaIndex.get(areaId) ?? 99;
    return i < 4 ? `var(--series-${i + 1})` : "var(--ink-soft)";
  }

  // ---- project list ---------------------------------------------------------
  let showFinished = $state(false);
  let expanded = $state<string | null>(null);
  let addingTo = $state<string | null>(null); // category id

  const visible = $derived(projects.filter((p) => showFinished || !["done", "dropped"].includes(p.status)));
  const editorCategories = $derived(
    (tax?.categories ?? []).map((c) => ({
      category: c,
      areaLabel: tax!.areas.find((a) => a.id === c.area_id)?.label ?? "",
    })),
  );

  function projectsIn(c: Category): Project[] {
    return visible
      .filter((p) => p.category_id === c.id)
      .sort((a, b) => Number(b.is_important) - Number(a.is_important) || (a.end_on ?? "9").localeCompare(b.end_on ?? "9"));
  }

  function toggle(id: string) {
    expanded = expanded === id ? null : id;
    addingTo = null;
  }
  function startAdding(categoryId: string) {
    addingTo = categoryId;
    expanded = null;
  }
  async function changed() {
    addingTo = null;
    await load();
  }

  function flagText(l: ProjectLoad, p: Project): string {
    switch (l.flag) {
      case "no-plan": return "no planned hours";
      case "no-end": return "no end date — all remaining hours counted now";
      case "overdue": return `past end date · ${fmtHours(l.remaining)} left`;
      case "over-budget": return `over plan by ${fmtHours(l.actual - (p.planned_hours ?? 0))}`;
      default: return l.perWeek ? `needs ${fmtHours(l.perWeek)}/wk to finish` : "";
    }
  }
  const warn = (l: ProjectLoad) => l.flag === "overdue" || l.flag === "over-budget";

  function period(p: Project): string {
    if (!p.start_on && !p.end_on) return "no dates";
    return `${p.start_on ? fmtDay(p.start_on) : "…"} – ${p.end_on ? fmtDay(p.end_on) : "…"}`;
  }
</script>

<section class="planning">
  <span class="eyebrow">Planning</span>
  <h1>Planning</h1>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if tax}
    <!-- ================= horizon ================= -->
    <h2>Remaining time · next {tax.horizonMonths} months</h2>
    <p class="muted note">
      {fmtDay(horizon.from)} – {fmtDay(horizon.to)}. Routine time is projected at your pace over the last
      {PACE_DAYS / 7} weeks; projects count their remaining planned hours, spread to their end date.
    </p>
    <div class="legend" aria-hidden="true">
      <span><i class="sw routine"></i>Routine (projected)</span>
      <span><i class="sw committed"></i>Committed to projects</span>
      <span><i class="sw free"></i>Free</span>
      <span><i class="sw cap"></i>Capacity</span>
    </div>

    <div class="horizon">
      {#each areaRows as r (r.area.id)}
        {@const over = r.free < 0}
        <div class="h-row">
          <span class="name">{r.area.label}</span>
          <div class="stack" aria-hidden="true">
            <span class="seg routine" style:width={`${(100 * r.routine) / scale}%`}></span>
            <span class="seg committed" style:width={`${(100 * r.committed) / scale}%`} style:background={areaColor(r.area.id)}></span>
            {#if !over}<span class="seg free" style:width={`${(100 * r.free) / scale}%`}></span>{/if}
            <span class="cap" style:left={`${(100 * r.capacity) / scale}%`}></span>
          </div>
          <span class="value" class:over>
            {#if over}
              <strong>⚠ over by {fmtHours(-r.free)}</strong>
            {:else}
              <strong>{fmtHours(r.free)} free</strong>
              <span class="muted">· ≈ {fmtHours(r.freePerWeek)}/wk</span>
            {/if}
          </span>
          <span class="detail muted">
            capacity {fmtHours(r.capacity)} · routine {fmtHours(r.routine)} · projects {fmtHours(r.committed)}
          </span>
        </div>
      {/each}
      <div class="h-total">
        <span class="name">All work</span>
        <span>
          capacity <strong>{fmtHours(total.capacity)}</strong> · routine {fmtHours(total.routine)} ·
          projects {fmtHours(total.committed)} ·
          {#if total.free >= 0}<strong>{fmtHours(total.free)} free</strong>{:else}<strong class="over">⚠ over by {fmtHours(-total.free)}</strong>{/if}
        </span>
      </div>
    </div>

    <!-- ================= projects ================= -->
    <div class="projects-head">
      <h2>Projects</h2>
      <label class="toggle"><input type="checkbox" bind:checked={showFinished} /> Show done and dropped</label>
    </div>

    {#each tax.areas as a (a.id)}
      {@const cats = tax.categories.filter((c) => c.area_id === a.id)}
      {@const plannable = cats.filter((c) => PLANNABLE_KINDS.has(c.kind))}
      {@const other = cats.filter((c) => !PLANNABLE_KINDS.has(c.kind) && projectsIn(c).length)}
      <div class="area" style:--area={areaColor(a.id)}>
        <h3>{a.label}</h3>

        {#snippet projectList(c: Category)}
          {#each projectsIn(c) as p (p.id)}
            {@const l = loads.get(p.id)!}
            <div class="project" class:open={expanded === p.id}>
              <button class="p-row" onclick={() => toggle(p.id)} aria-expanded={expanded === p.id}>
                <span class="p-name">
                  {#if p.is_important}<span class="star" title="Important">★</span>{/if}{p.name}
                  <span class="chip status-{p.status}">{p.status}</span>
                </span>
                <span class="p-dates muted">{period(p)}</span>
                <span class="meter" aria-hidden="true">
                  {#if p.planned_hours}
                    <span class="fill" style:width={`${Math.min(100, (100 * l.actual) / p.planned_hours)}%`}></span>
                  {/if}
                </span>
                <span class="p-hours">
                  <strong>{fmtHours(l.actual)}</strong>
                  {#if p.planned_hours !== null}<span class="muted"> of {fmtHours(p.planned_hours)}</span>{/if}
                </span>
                <span class="p-flag" class:warn={warn(l)}>{warn(l) ? "⚠ " : ""}{flagText(l, p)}</span>
              </button>
              {#if expanded === p.id}
                <div class="p-body">
                  <ProjectEditor project={p} categories={editorCategories} categoryId={p.category_id}
                                 onsaved={changed} oncancel={() => (expanded = null)} />
                  <Milestones project={p} {actualByMilestone} onchange={load} />
                </div>
              {/if}
            </div>
          {/each}
        {/snippet}

        {#each plannable as c (c.id)}
          <div class="cat">
            <div class="cat-head">
              <span class="cat-name">{c.label}</span>
              <button class="add" onclick={() => startAdding(c.id)}>+ Project</button>
            </div>
            {#if addingTo === c.id}
              <div class="p-body new">
                <ProjectEditor project={null} categories={editorCategories} categoryId={c.id}
                               onsaved={changed} oncancel={() => (addingTo = null)} />
              </div>
            {/if}
            {@render projectList(c)}
            {#if !projectsIn(c).length && addingTo !== c.id}<p class="muted empty">No projects.</p>{/if}
          </div>
        {/each}

        {#if other.length}
          <details class="other">
            <summary>Projects in routine categories ({other.reduce((s, c) => s + projectsIn(c).length, 0)}) — counted in routine time, not the plan</summary>
            {#each other as c (c.id)}
              <div class="cat">
                <div class="cat-head"><span class="cat-name">{c.label}</span></div>
                {@render projectList(c)}
              </div>
            {/each}
          </details>
        {/if}
      </div>
    {/each}

    <!-- ================= allocation ================= -->
    <h2>Allocation</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Area</th><th class="num">Time h/wk</th><th class="num">Email h/wk</th><th class="num">h/year</th></tr>
        </thead>
        <tbody>
          {#each tax.areas as a (a.id)}
            {@const t = targetOn(tax.targets, a.id, today())}
            <tr>
              <td>{a.label}</td>
              <td class="num">{t ? t.weekly_hours : "—"}</td>
              <td class="num">{t ? t.email_weekly_hours : "—"}</td>
              <td class="num">{t ? Math.round((t.weekly_hours + t.email_weekly_hours) * tax.weeksPerYear) : "—"}</td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td>Total · {tax.weeksPerYear} weeks</td>
            <td class="num">{tax.areas.reduce((s, a) => s + (targetOn(tax!.targets, a.id, today())?.weekly_hours ?? 0), 0)}</td>
            <td class="num">{tax.areas.reduce((s, a) => s + (targetOn(tax!.targets, a.id, today())?.email_weekly_hours ?? 0), 0)}</td>
            <td class="num">{Math.round(tax.areas.reduce((s, a) => {
              const t = targetOn(tax!.targets, a.id, today());
              return s + (t ? (t.weekly_hours + t.email_weekly_hours) * tax!.weeksPerYear : 0);
            }, 0))}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  {/if}
</section>

<style>
  .planning h2 { margin-top: 2.2rem; }
  .note { font-family: var(--font-ui); font-size: 0.85rem; margin: -0.2rem 0 0.6rem; max-width: 46rem; }

  /* ---- horizon ---- */
  .legend { display: flex; flex-wrap: wrap; gap: 1rem; font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); margin-bottom: 0.9rem; }
  .legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
  .sw { display: inline-block; width: 12px; height: 10px; border-radius: 2px; }
  .sw.routine { background: var(--ink-soft); opacity: 0.55; }
  .sw.committed { background: linear-gradient(90deg, var(--series-1) 0 25%, var(--series-2) 25% 50%, var(--series-3) 50% 75%, var(--series-4) 75%); }
  .sw.free { background: var(--track); border: 1px solid var(--rule); }
  .sw.cap { width: 2px; height: 14px; background: var(--ink); border-radius: 0; }

  .horizon { display: grid; gap: 1rem; font-family: var(--font-ui); font-size: 0.92rem; }
  .h-row {
    display: grid;
    grid-template-columns: 7rem 1fr 12rem;
    grid-template-areas: "name stack value" ". detail detail";
    column-gap: 0.9rem;
    row-gap: 0.25rem;
    align-items: center;
  }
  .h-row .name { grid-area: name; font-weight: 600; }
  .stack { grid-area: stack; position: relative; display: flex; gap: 2px; height: 12px; }
  .seg { display: block; height: 100%; min-width: 0; }
  .seg:first-child { border-radius: 2px 0 0 2px; }
  .seg:nth-last-child(2) { border-radius: 0 4px 4px 0; }
  .seg.routine { background: var(--ink-soft); opacity: 0.55; }
  .seg.free { background: var(--track); }
  .cap { position: absolute; top: -4px; bottom: -4px; width: 2px; margin-left: -1px; background: var(--ink); }
  .h-row .value { grid-area: value; font-variant-numeric: tabular-nums; }
  .h-row .detail { grid-area: detail; font-size: 0.8rem; }
  .over, .value.over strong { color: var(--danger); }
  .h-total { display: flex; gap: 0.9rem; flex-wrap: wrap; border-top: 1px solid var(--rule); padding-top: 0.7rem; }
  .h-total .name { width: 7rem; font-weight: 600; }

  /* ---- projects ---- */
  .projects-head { display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
  .projects-head h2 { margin-bottom: 0.4rem; }
  .toggle { display: inline-flex; align-items: center; gap: 0.4rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  .toggle input { width: auto; }

  .area { margin-top: 1.4rem; }
  .area h3 { font-size: 1.05rem; border-left: 4px solid var(--area); padding-left: 0.5rem; }
  .cat { margin: 0.8rem 0 0 0.9rem; }
  .cat-head { display: flex; align-items: center; gap: 0.75rem; font-family: var(--font-ui); }
  .cat-name { font-weight: 600; font-size: 0.9rem; color: var(--ink-soft); }
  .add { font-size: 0.8rem; padding: 0.15rem 0.6rem; }
  .empty { font-family: var(--font-ui); font-size: 0.82rem; margin: 0.2rem 0 0; }

  .project { border-radius: var(--radius); }
  .project.open { background: var(--panel); }
  .p-row {
    width: 100%;
    display: grid;
    grid-template-columns: minmax(10rem, 1.6fr) 12rem minmax(5rem, 1fr) 8.5rem;
    grid-template-areas: "name dates meter hours" "flag flag flag flag";
    column-gap: 0.9rem;
    align-items: center;
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 0.5rem 0.5rem;
    font-size: 0.9rem;
  }
  .p-row:hover { background: var(--panel); }
  .p-name { grid-area: name; }
  .star { color: var(--ink); margin-right: 0.3rem; }
  .p-dates { grid-area: dates; font-size: 0.8rem; }
  .meter { grid-area: meter; position: relative; display: block; height: 8px; background: var(--track); border-radius: 0 4px 4px 0; }
  .fill { position: absolute; inset: 0 auto 0 0; background: var(--area); border-radius: 0 4px 4px 0; min-width: 2px; }
  .p-hours { grid-area: hours; text-align: right; font-variant-numeric: tabular-nums; }
  .p-flag { grid-area: flag; font-size: 0.78rem; color: var(--ink-soft); }
  .p-flag:empty { display: none; }
  .p-flag.warn { color: var(--danger); }
  .p-body { padding: 0.4rem 0.6rem 1rem; }
  .p-body.new { background: var(--panel); border-radius: var(--radius); margin: 0.4rem 0; padding-top: 0.8rem; }

  .other { margin: 1rem 0 0 0.9rem; font-family: var(--font-ui); }
  .other summary { cursor: pointer; font-size: 0.85rem; color: var(--ink-soft); }

  /* ---- allocation ---- */
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; max-width: 36rem; font-family: var(--font-ui); font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--rule); }
  th { color: var(--ink-soft); font-weight: 500; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  tfoot td { border-bottom: none; font-weight: 600; }

  @media (max-width: 44rem) {
    .h-row { grid-template-columns: 1fr auto; grid-template-areas: "name value" "stack stack" "detail detail"; }
    .p-row {
      grid-template-columns: 1fr auto;
      grid-template-areas: "name hours" "meter meter" "dates dates" "flag flag";
      row-gap: 0.3rem;
    }
  }
</style>
