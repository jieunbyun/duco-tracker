<script lang="ts">
  import { loadTaxonomy, loadEntryHours, targetOn, fmtHours, loadCoreTarget } from "../lib/data";
  import type { Taxonomy, EntryHours } from "../lib/data";
  import { PRESETS, presetRange, addDays, today, daysIn, fmtDay, weekStart } from "../lib/dates";
  import type { Preset, Range } from "../lib/dates";
  import { shareEmail } from "../lib/email";

  // ---- period ------------------------------------------------------------
  const PRESET_KEY = "time.preset";
  function savedPreset(): Preset {
    try {
      const p = localStorage.getItem(PRESET_KEY);
      if (p && PRESETS.some((x) => x.key === p)) return p as Preset;
    } catch {}
    return "this-month";
  }
  let preset = $state<Preset>(savedPreset());
  // A custom period starts on 17 October 2026 unless changed, and runs to today.
  const CUSTOM_FROM = "2026-10-17";
  let custom = $state<Range>({ from: CUSTOM_FROM <= today() ? CUSTOM_FROM : addDays(today(), -29), to: today() });
  const range = $derived(presetRange(preset, custom));

  function choose(p: Preset) {
    preset = p;
    try { localStorage.setItem(PRESET_KEY, p); } catch {}
  }

  // ---- data --------------------------------------------------------------
  let tax = $state<Taxonomy | null>(null);
  let entries = $state<EntryHours[]>([]);
  let loading = $state(true);
  let error = $state("");
  let request = 0;

  loadTaxonomy().then((t) => (tax = t)).catch((e) => (error = e.message));
  let coreWeekly = $state<number | null>(null); // your weekly target for core hours
  loadCoreTarget().then((v) => (coreWeekly = v ?? null));

  $effect(() => {
    const { from, to } = range;
    if (!from || !to || from > to) return;
    const id = ++request;
    loading = true;
    loadEntryHours(from, to)
      .then((rows) => { if (id === request) { entries = rows; error = ""; } })
      .catch((e) => { if (id === request) error = e.message; })
      .finally(() => { if (id === request) loading = false; });
  });

  // Email counts in equal shares to every area with an Email category.
  const shared = $derived(tax ? shareEmail(entries, tax) : entries);

  // Colour follows the area (its place in the area order), never its rank.
  const areaIndex = $derived(new Map((tax?.areas ?? []).map((a, i) => [a.id, i])));
  function areaColor(areaId: string): string {
    const i = areaIndex.get(areaId) ?? 99;
    return i < 4 ? `var(--series-${i + 1})` : "var(--ink-soft)";
  }

  // ---- plan vs actual ----------------------------------------------------
  // Targets accrue day by day up to today: an annual allocation of
  // (weekly + email) × weeks_per_year spread over 365 days. A period that runs
  // into the future is judged on the days already lived.
  const elapsed = $derived.by(() => {
    const end = range.to < today() ? range.to : today();
    return end < range.from ? 0 : daysIn({ from: range.from, to: end });
  });
  const targetEnd = $derived(range.to < today() ? range.to : today());

  // Targets measured so far (the days lived) or for the whole period
  const BASIS_KEY = "time.basis";
  let basis = $state<"sofar" | "full">((() => { try { return localStorage.getItem(BASIS_KEY) === "full" ? "full" : "sofar"; } catch { return "sofar"; } })());
  function chooseBasis(b: "sofar" | "full") {
    basis = b;
    try { localStorage.setItem(BASIS_KEY, b); } catch {}
  }
  const targetDays = $derived(basis === "full" ? daysIn(range) : elapsed);
  const targetUntil = $derived(basis === "full" ? range.to : targetEnd); // the last day a target counts
  const basisWord = $derived(basis === "full" ? "for the period" : "to date");

  const plan = $derived.by(() => {
    if (!tax) return [];
    const perDay = tax.weeksPerYear / 365;
    return tax.areas.map((a) => {
      const t = targetOn(tax!.targets, a.id, targetEnd);
      const rows = shared.filter((e) => e.area_id === a.id);
      const actual = rows.reduce((s, e) => s + e.hours, 0);
      const email = rows.filter((e) => e.category_kind === "email").reduce((s, e) => s + e.hours, 0);
      const target = t ? (t.weekly_hours + t.email_weekly_hours) * perDay * targetDays : 0;
      const emailTarget = t ? t.email_weekly_hours * perDay * targetDays : 0;
      return { area: a, actual, target, email, emailTarget };
    });
  });
  // Teaching and Admin also shown together: a combined row of the two, stacked.
  const COMBINED = ["TEA", "ADM"];
  const combo = $derived.by(() => {
    const parts = COMBINED.map((code) => plan.find((p) => p.area.code === code)).filter((p) => !!p);
    if (parts.length < 2) return null;
    return {
      parts,
      label: parts.map((p) => p!.area.label).join(" + "),
      actual: parts.reduce((s, p) => s + p!.actual, 0),
      target: parts.reduce((s, p) => s + p!.target, 0),
    };
  });
  const planMax = $derived(Math.max(1, ...plan.map((p) => Math.max(p.actual, p.target)), combo?.actual ?? 0, combo?.target ?? 0));

  const totals = $derived.by(() => {
    const logged = entries.reduce((s, e) => s + e.hours, 0);
    const core = entries.filter((e) => e.is_core).reduce((s, e) => s + e.hours, 0);
    const target = plan.reduce((s, p) => s + p.target, 0);
    return { logged, core, target, perWeek: elapsed ? (logged / elapsed) * 7 : 0, corePerWeek: elapsed ? (core / elapsed) * 7 : 0 };
  });

  // ---- core hours: against a weekly target, spread over every day of the week ----
  const coreTarget = $derived(coreWeekly ? (coreWeekly / 7) * targetDays : 0);
  /** Each week of the period: core hours, and the target for its days (so far, or all of them). */
  const coreWeeks = $derived.by(() => {
    const out: { start: string; label: string; hours: number; target: number; partial: boolean }[] = [];
    if (elapsed <= 0) return out;
    for (let ws = weekStart(range.from); ws <= targetUntil; ws = addDays(ws, 7)) {
      const from = ws < range.from ? range.from : ws;
      const we = addDays(ws, 6);
      const to = we > targetUntil ? targetUntil : we;
      const days = daysIn({ from, to });
      const hours = entries.filter((e) => e.is_core && e.entry_date >= from && e.entry_date <= to).reduce((s, e) => s + e.hours, 0);
      out.push({ start: ws, label: fmtDay(ws), hours, target: coreWeekly ? (coreWeekly / 7) * days : 0, partial: days < 7 });
    }
    return out;
  });
  const coreMax = $derived(Math.max(1, coreWeekly ?? 0, ...coreWeeks.map((w) => w.hours)));

  // ---- composition drill-down -------------------------------------------
  // all work > area > category > project > milestone
  type Node = {
    key: string;
    label: string;
    sub: string;
    hours: number;
    count: number;
    areaId: string;
    none: boolean; // the "No project" / "No milestone" remainder
    children: Map<string, Node>;
  };

  function node(key: string, label: string, sub: string, areaId: string, none = false): Node {
    return { key, label, sub, hours: 0, count: 0, areaId, none, children: new Map() };
  }

  const tree = $derived.by(() => {
    const root = node("all", "All work", "", "");
    if (!tax) return root;
    const cats = new Map(tax.allCategories.map((c) => [c.id, c]));
    for (const a of tax.areas) root.children.set(a.id, node(a.id, a.label, "", a.id));
    for (const e of shared) {
      const area = root.children.get(e.area_id);
      if (!area) continue;
      const c = cats.get(e.category_id);
      const cat = getOr(area, e.category_id, () => node(e.category_id, c?.label ?? "Category", c?.kind ?? "", e.area_id));
      const pKey = e.project_id ?? "none";
      const proj = getOr(cat, pKey, () =>
        node(pKey, e.project_name ?? "No project", e.project_id ? "project" : "", e.area_id, !e.project_id));
      const path = [root, area, cat, proj];
      if (e.project_id) {
        const mKey = e.milestone_id ?? "none";
        path.push(getOr(proj, mKey, () =>
          node(mKey, e.milestone_title ?? "No milestone", e.milestone_id ? "milestone" : "", e.area_id, !e.milestone_id)));
      }
      for (const n of path) { n.hours += e.hours; n.count += 1; }
    }
    return root;
  });

  function getOr(parent: Node, key: string, make: () => Node): Node {
    let n = parent.children.get(key);
    if (!n) parent.children.set(key, (n = make()));
    return n;
  }

  let path = $state<string[]>([]);

  // Walk as far down the chosen path as this period's data allows.
  const trail = $derived.by(() => {
    const out = [tree];
    for (const k of path) {
      const next = out[out.length - 1].children.get(k);
      if (!next) break;
      out.push(next);
    }
    return out;
  });
  const current = $derived(trail[trail.length - 1]);
  const rows = $derived(
    [...current.children.values()].sort((p, q) => q.hours - p.hours || p.label.localeCompare(q.label)),
  );
  const rowMax = $derived(Math.max(1e-9, ...rows.map((r) => r.hours)));

  function drillable(n: Node): boolean {
    const kids = [...n.children.values()];
    return kids.length > 0 && !(kids.length === 1 && kids[0].none);
  }
  function drill(n: Node) {
    if (drillable(n)) path = [...trail.slice(1).map((t) => t.key), n.key];
  }
  function upTo(i: number) {
    path = trail.slice(1, i + 1).map((t) => t.key);
  }

  function pct(part: number, whole: number): string {
    return whole > 0 ? `${Math.round((100 * part) / whole)}%` : "—";
  }
</script>

<section class="time">
  <span class="eyebrow">Time</span>
  <h1>Where the time goes</h1>

  <div class="filters" role="group" aria-label="Period">
    {#each PRESETS as p (p.key)}
      <button class:on={preset === p.key} aria-pressed={preset === p.key} onclick={() => choose(p.key)}>{p.label}</button>
    {/each}
  </div>
  {#if preset === "custom"}
    <div class="custom">
      <label>From <input type="date" bind:value={custom.from} max={custom.to} /></label>
      <label>To <input type="date" bind:value={custom.to} min={custom.from} /></label>
    </div>
  {/if}
  <p class="muted period">
    {fmtDay(range.from)} – {fmtDay(range.to)}
    {#if loading}<span class="loading">· loading…</span>{/if}
  </p>

  {#if error}
    <p class="error">{error}</p>
  {:else if tax}
    <!-- KPI row -->
    <div class="kpis">
      <div class="kpi">
        <span class="kpi-label">Logged</span>
        <span class="kpi-value">{fmtHours(totals.logged)}</span>
        <span class="kpi-sub">{pct(totals.logged, totals.target)} of target {basisWord}</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Target {basisWord}</span>
        <span class="kpi-value">{fmtHours(totals.target)}</span>
        <span class="kpi-sub">{elapsed} of {daysIn(range)} days elapsed</span>
        <div class="basis" role="group" aria-label="Targets measured">
          <button class:on={basis === "sofar"} aria-pressed={basis === "sofar"} onclick={() => chooseBasis("sofar")}>So far</button>
          <button class:on={basis === "full"} aria-pressed={basis === "full"} onclick={() => chooseBasis("full")}>Full period</button>
        </div>
      </div>
      <div class="kpi">
        <span class="kpi-label">Weekly average</span>
        <span class="kpi-value">{fmtHours(totals.perWeek)}</span>
        <span class="kpi-sub">per week, over days elapsed</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Core</span>
        <span class="kpi-value">{fmtHours(totals.core)}</span>
        <span class="kpi-sub">
          {coreWeekly ? `${pct(totals.core, coreTarget)} of core target ${basisWord} · ` : ""}{pct(totals.core, totals.logged)} of logged
        </span>
      </div>
    </div>

    <!-- Core hours -->
    <h2>Core hours</h2>
    {#if coreWeekly}
      <p class="muted note">Hours flagged core, against {fmtHours(coreWeekly)} a week spread over every day. Each bar is a week; the tick is its target{basis === "full" ? "" : " (a part week's, for the days so far)"}.</p>
      <div class="plan">
        <div class="plan-row" title={`Core: ${fmtHours(totals.core)} logged, target ${fmtHours(coreTarget)}`}>
          <span class="name">Core</span>
          <div class="track" aria-hidden="true">
            <div class="bar core-bar" style:width={`${(100 * totals.core) / Math.max(1, totals.core, coreTarget)}%`}></div>
            {#if coreTarget > 0}<div class="tick" style:left={`${(100 * coreTarget) / Math.max(1, totals.core, coreTarget)}%`}></div>{/if}
          </div>
          <span class="value">
            <strong>{fmtHours(totals.core)}</strong> of {fmtHours(coreTarget)}
            <span class="muted">· {pct(totals.core, coreTarget)}</span>
          </span>
          <span class="email muted">{fmtHours(totals.corePerWeek)} a week on average</span>
        </div>
      </div>
    {:else}
      <p class="muted note">{fmtHours(totals.core)} flagged core in this period, {fmtHours(totals.corePerWeek)} a week. Set a weekly core target under Planning › Edit targets and settings to track it here.</p>
    {/if}
    {#if coreWeeks.length > 1}
      <div class="weeks" role="img" aria-label="Core hours per week">
        {#each coreWeeks as w (w.start)}
          <div class="wk" title={`Week of ${w.label}: ${fmtHours(w.hours)} core${w.target ? ` of ${fmtHours(w.target)}` : ""}${w.partial ? " (part week)" : ""}`}>
            <div class="wk-col">
              <div class="wk-bar" class:met={w.target > 0 && w.hours >= w.target} style:height={`${(100 * w.hours) / coreMax}%`}></div>
              {#if w.target > 0}<div class="wk-tick" style:bottom={`${(100 * w.target) / coreMax}%`}></div>{/if}
            </div>
            <span class="wk-h">{w.hours ? Math.round(w.hours) : ""}</span>
            <span class="wk-label">{w.label.replace(/ \d{4}$/, "")}</span>
          </div>
        {/each}
      </div>
    {/if}

    <!-- Plan vs actual -->
    <h2>Plan vs actual</h2>
    <p class="muted note">Bars are hours logged; the tick is the target {basis === "full" ? "for the whole period" : "for the days elapsed"}.</p>
    <div class="plan">
      {#each plan as p (p.area.id)}
        <div class="plan-row" title={`${p.area.label}: ${fmtHours(p.actual)} logged, target ${fmtHours(p.target)}`}>
          <span class="name">{p.area.label}</span>
          <div class="track" aria-hidden="true">
            <div class="bar" style:width={`${(100 * p.actual) / planMax}%`} style:background={areaColor(p.area.id)}></div>
            {#if p.target > 0}<div class="tick" style:left={`${(100 * p.target) / planMax}%`}></div>{/if}
          </div>
          <span class="value">
            <strong>{fmtHours(p.actual)}</strong> of {fmtHours(p.target)}
            <span class="muted">· {pct(p.actual, p.target)}</span>
          </span>
          {#if p.emailTarget > 0 || p.email > 0}
            <span class="email muted">email {fmtHours(p.email)} of {fmtHours(p.emailTarget)}</span>
          {/if}
        </div>
      {/each}
      {#if combo}
        <div class="plan-row combo" title={`${combo.label}: ${fmtHours(combo.actual)} logged, target ${fmtHours(combo.target)}`}>
          <span class="name"><em>{combo.label}</em> <small class="tag">combined</small></span>
          <div class="track thin" aria-hidden="true">
            <div class="stack">
              {#each combo.parts as part (part!.area.id)}
                <span class="seg" style:width={`${(100 * part!.actual) / planMax}%`} style:background={areaColor(part!.area.id)}></span>
              {/each}
            </div>
            {#if combo.target > 0}<div class="tick" style:left={`${(100 * combo.target) / planMax}%`}></div>{/if}
          </div>
          <span class="value">
            <strong>{fmtHours(combo.actual)}</strong> of {fmtHours(combo.target)}
            <span class="muted">· {pct(combo.actual, combo.target)}</span>
          </span>
          <span class="email muted">
            {combo.parts.map((part) => `${part!.area.label} ${fmtHours(part!.actual)}`).join(" + ")}
          </span>
        </div>
      {/if}
    </div>

    <!-- Composition -->
    <h2>Composition</h2>
    <nav class="crumbs" aria-label="Drill-down level">
      {#each trail as t, i (t.key + i)}
        {#if i > 0}<span class="sep" aria-hidden="true">›</span>{/if}
        {#if i < trail.length - 1}
          <button class="crumb" onclick={() => upTo(i)}>{t.label}</button>
        {:else}
          <span class="crumb here" aria-current="location">{t.label}</span>
        {/if}
      {/each}
      <span class="muted crumb-total">{fmtHours(current.hours)}</span>
    </nav>

    {#if !rows.length || current.hours === 0}
      <p class="muted">Nothing logged here in this period.</p>
    {:else}
      <ol class="rows">
        {#each rows as r (r.key)}
          {@const canDrill = drillable(r)}
          <li>
            <button
              class="row"
              class:none={r.none}
              disabled={!canDrill}
              onclick={() => drill(r)}
              title={`${r.label}: ${fmtHours(r.hours)}, ${r.count} ${r.count === 1 ? "entry" : "entries"}`}
            >
              <span class="name">
                {r.label}
                {#if r.sub}<small>{r.sub}</small>{/if}
              </span>
              <span class="track" aria-hidden="true">
                <span class="bar" style:width={`${(100 * r.hours) / rowMax}%`} style:background={areaColor(r.areaId)}></span>
              </span>
              <span class="value"><strong>{fmtHours(r.hours)}</strong> <span class="muted">· {pct(r.hours, current.hours)}</span></span>
              <span class="chev" aria-hidden="true">{canDrill ? "›" : ""}</span>
            </button>
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
</section>

<style>
  .time h2 { margin-top: 2.2rem; }
  .filters { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 1rem; }
  .filters button { font-size: 0.88rem; padding: 0.35rem 0.75rem; }
  .filters button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .custom { display: flex; gap: 0.75rem; margin-top: 0.6rem; max-width: 26rem; }
  .custom label { flex: 1; display: grid; gap: 0.2rem; font-family: var(--font-ui); font-size: 0.82rem; color: var(--ink-soft); }
  .period { font-family: var(--font-ui); font-size: 0.88rem; margin: 0.6rem 0 0; }
  .note { font-family: var(--font-ui); font-size: 0.85rem; margin: -0.2rem 0 0.8rem; }

  .core-bar { background: var(--accent); }
  .weeks { display: flex; gap: 4px; align-items: flex-end; overflow-x: auto; padding: 0.4rem 0 0.2rem; font-family: var(--font-ui); }
  .wk { flex: 1 0 1.6rem; max-width: 3.2rem; display: grid; justify-items: center; gap: 2px; }
  .wk-col { position: relative; width: 100%; height: 6rem; background: color-mix(in srgb, var(--panel) 60%, transparent); border-radius: 3px; }
  .wk-bar { position: absolute; left: 15%; right: 15%; bottom: 0; background: color-mix(in srgb, var(--accent) 55%, var(--paper)); border-radius: 3px 3px 0 0; }
  .wk-bar.met { background: var(--accent); }
  .wk-tick { position: absolute; left: 0; right: 0; border-top: 2px solid var(--ink); }
  .wk-h { font-size: 0.7rem; color: var(--ink); min-height: 0.9rem; }
  .wk-label { font-size: 0.62rem; color: var(--ink-soft); white-space: nowrap; }
  .basis { display: inline-flex; margin-top: 0.35rem; }
  .basis button { font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 0; }
  .basis button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .basis button:last-child { border-radius: 0 var(--radius) var(--radius) 0; margin-left: -1px; }
  .basis button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: 0.75rem;
    margin-top: 1.25rem;
  }
  .kpi {
    display: grid;
    gap: 0.15rem;
    background: var(--panel);
    border-radius: var(--radius);
    padding: 0.8rem 1rem;
    font-family: var(--font-ui);
  }
  .kpi-label { font-size: 0.78rem; color: var(--ink-soft); }
  .kpi-value { font-size: 1.6rem; font-weight: 600; line-height: 1.2; }
  .kpi-sub { font-size: 0.78rem; color: var(--ink-soft); }

  /* shared bar anatomy: thin, rounded data end, anchored to the left */
  .track { position: relative; display: block; height: 10px; background: var(--track); border-radius: 0 4px 4px 0; }
  .bar { position: absolute; inset: 0 auto 0 0; display: block; border-radius: 0 4px 4px 0; min-width: 2px; }

  .plan { display: grid; gap: 0.9rem; font-family: var(--font-ui); font-size: 0.92rem; }
  /* the combined row: set apart, thinner, stacked from its areas' own colours */
  .plan-row.combo { border-top: 1px dashed var(--rule); padding-top: 0.8rem; }
  .plan-row.combo .name { font-weight: 400; }
  .plan-row.combo .tag { font-size: 0.68rem; color: var(--ink-soft); border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.35rem; font-style: normal; }
  .track.thin { height: 6px; }
  .track.thin .tick { top: -5px; bottom: -5px; }
  .stack { position: absolute; inset: 0; display: flex; gap: 2px; }
  .stack .seg { display: block; height: 100%; min-width: 0; }
  .stack .seg:last-child { border-radius: 0 4px 4px 0; }
  .plan-row {
    display: grid;
    grid-template-columns: 7rem 1fr 11rem;
    grid-template-areas: "name track value" ". email email";
    align-items: center;
    column-gap: 0.9rem;
  }
  .plan-row .name { grid-area: name; font-weight: 600; }
  .plan-row .track { grid-area: track; }
  .plan-row .value { grid-area: value; font-variant-numeric: tabular-nums; }
  .plan-row .email { grid-area: email; font-size: 0.8rem; }
  .tick {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 2px;
    margin-left: -1px;
    background: var(--ink);
  }

  .crumbs {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.35rem;
    font-family: var(--font-ui);
    font-size: 0.92rem;
    margin-bottom: 0.6rem;
  }
  .crumb { background: none; border: none; padding: 0.15rem 0.2rem; color: var(--accent); text-decoration: underline; }
  .crumb.here { font-weight: 600; color: var(--ink); }
  .sep { color: var(--ink-soft); }
  .crumb-total { margin-left: auto; }

  .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .row {
    width: 100%;
    display: grid;
    grid-template-columns: minmax(8rem, 16rem) 1fr 9rem 1rem;
    align-items: center;
    column-gap: 0.9rem;
    text-align: left;
    background: none;
    border: none;
    border-radius: var(--radius);
    padding: 0.55rem 0.5rem;
    font-family: var(--font-ui);
    font-size: 0.92rem;
  }
  .row:not(:disabled):hover { background: var(--panel); }
  .row:disabled { cursor: default; opacity: 1; }
  .row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row .name small { color: var(--ink-soft); margin-left: 0.4rem; font-size: 0.75rem; }
  .row.none .name { color: var(--ink-soft); font-style: italic; }
  .row.none .bar { opacity: 0.45; }
  .row .value { font-variant-numeric: tabular-nums; text-align: right; }
  .chev { color: var(--ink-soft); }

  @media (max-width: 40rem) {
    .plan-row {
      grid-template-columns: 1fr auto;
      grid-template-areas: "name value" "track track" "email email";
      row-gap: 0.35rem;
    }
    .row {
      grid-template-columns: 1fr auto 1rem;
      grid-template-areas: "name value chev" "track track track";
      row-gap: 0.35rem;
    }
    .row .name { grid-area: name; }
    .row .track { grid-area: track; }
    .row .value { grid-area: value; }
    .row .chev { grid-area: chev; }
  }
</style>
