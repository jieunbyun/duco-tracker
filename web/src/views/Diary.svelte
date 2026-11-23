<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { day: "", starredOnly: false };
</script>

<script lang="ts">
  // Diary: a day's happiest moment (and why), worst moment and mood; and, for its month,
  // a look back — mood over the month and its statistics, the moments, where they come
  // from, where the time went, and your reflection.
  import { AREAS, areaLabel, loadDays, saveDay, deleteDay, setStar, loadMonth, saveMonth } from "../lib/diary";
  import type { DiaryDay, DiaryFields, LifeArea } from "../lib/diary";
  import { loadEntriesBetween, loadTaxonomy } from "../lib/data";
  import type { Taxonomy, TimeEntry } from "../lib/data";
  import { undoable } from "../lib/undo.svelte";
  import { addDays, today, parse, fmtDay } from "../lib/dates";

  // ---- dates ----------------------------------------------------------------------
  const monthOf = (d: string) => `${d.slice(0, 7)}-01`;
  const shiftMonth = (m: string, n: number) => {
    const d = parse(m);
    d.setMonth(d.getMonth() + n, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
  };
  const monthEnd = (m: string) => addDays(shiftMonth(m, 1), -1);
  const monthName = (m: string) => parse(m).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const short = (d: string) => parse(d).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

  // ---- state ----------------------------------------------------------------------
  let day = $state(last.day || today());
  const month = $derived(monthOf(day));
  let days = $state<DiaryDay[]>([]); // this month and the one before (for the comparison)
  let entries = $state<TimeEntry[]>([]);
  let tax = $state<Taxonomy | null>(null);
  let reflection = $state("");
  let savedReflection = $state("");
  let missing = $state(false);
  let loading = $state(true);
  let error = $state("");
  let starredOnly = $state(last.starredOnly);
  let request = 0;

  $effect(() => {
    Object.assign(last, { day, starredOnly });
  });

  async function load() {
    const id = ++request;
    const m = month;
    try {
      const [d, mo, e, t] = await Promise.all([
        loadDays(shiftMonth(m, -1), monthEnd(m)), loadMonth(m),
        loadEntriesBetween(m, monthEnd(m)).catch(() => [] as TimeEntry[]), tax ? Promise.resolve(tax) : loadTaxonomy(),
      ]);
      if (id !== request) return;
      missing = d === null;
      days = d ?? [];
      entries = e;
      tax = t;
      reflection = savedReflection = mo.reflection ?? "";
      error = "";
    } catch (e) {
      if (id === request) error = (e as Error).message;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void month;
    load();
  });

  // ---- the day being written ----------------------------------------------------------
  const blank = (d: string): DiaryFields => ({
    day: d, mood: null, best: null, best_why: null, best_area: null, best_star: false,
    worst: null, worst_area: null, worst_star: false,
  });
  const stored = $derived(days.find((x) => x.day === day) ?? null);
  let draft = $state<DiaryFields>(blank(today()));
  let draftOf = $state(""); // which day (and version) the draft was taken from
  $effect(() => {
    const key = `${day}|${JSON.stringify(stored)}`;
    if (key === draftOf) return;
    draftOf = key;
    const { id: _, ...fields } = stored ?? { id: "", ...blank(day) };
    draft = { ...fields };
  });
  const asStored = $derived(JSON.stringify((() => { const { id: _, ...f } = stored ?? { id: "", ...blank(day) }; return f; })()));
  const dirty = $derived(JSON.stringify(draft) !== asStored);
  let saving = $state(false);

  function go(d: string) {
    if (d === day) return;
    if (dirty && !confirm("Leave this day without saving what you wrote?")) return;
    day = d;
  }
  const text = (v: string | null) => (v?.trim() ? v.trim() : null);
  async function save() {
    saving = true;
    try {
      const f = { ...draft, best: text(draft.best), best_why: text(draft.best_why), worst: text(draft.worst) };
      const empty = !f.best && !f.best_why && !f.worst && f.mood === null;
      await undoable(empty ? `Cleared the diary for ${fmtDay(day)}` : `Wrote the diary for ${fmtDay(day)}`,
        () => (empty ? (stored ? deleteDay(day) : Promise.resolve()) : saveDay(f)));
      await load();
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
    } finally {
      saving = false;
    }
  }
  const pickArea = (which: "best_area" | "worst_area", a: LifeArea) => (draft[which] = draft[which] === a ? null : a);
  const pickMood = (n: number) => (draft.mood = draft.mood === n ? null : n);

  // ---- the month --------------------------------------------------------------------
  const monthDays = $derived.by(() => {
    const out: string[] = [];
    for (let d = month; d <= monthEnd(month); d = addDays(d, 1)) out.push(d);
    return out;
  });
  const inMonth = $derived(days.filter((x) => x.day >= month && x.day <= monthEnd(month)));
  const prevMonth = $derived(days.filter((x) => x.day < month));
  const byDay = $derived(new Map(inMonth.map((x) => [x.day, x])));

  // mood statistics
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  const moodsOf = (xs: DiaryDay[]) => xs.filter((x) => x.mood !== null).map((x) => x.mood!);
  const stats = $derived.by(() => {
    const rated = inMonth.filter((x) => x.mood !== null);
    const moods = rated.map((x) => x.mood!);
    const avg = mean(moods);
    const before = mean(moodsOf(prevMonth));
    const sorted = [...moods].sort((a, b) => a - b);
    const median = sorted.length ? (sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2) : null;
    const high = rated.length ? Math.max(...moods) : null;
    const low = rated.length ? Math.min(...moods) : null;
    return {
      avg, before, median, high, low, rated: rated.length,
      highDays: rated.filter((x) => x.mood === high).map((x) => x.day),
      lowDays: rated.filter((x) => x.mood === low).map((x) => x.day),
      written: inMonth.length,
      good: moods.filter((m) => m >= 7).length,
      hard: moods.filter((m) => m <= 4).length,
    };
  });
  const fmt1 = (n: number | null) => (n === null ? "–" : n.toFixed(1));
  const dateList = (ds: string[]) =>
    ds.length > 3 ? `${ds.slice(0, 3).map((d) => parse(d).getDate()).join(", ")} and ${ds.length - 3} more` : ds.map((d) => short(d)).join(", ");

  // mood over the month: one point a rated day; the line breaks where a day has no mood
  let plotW = $state(640); // the chart is drawn at its real width, so its text is never stretched
  const W = $derived(Math.max(260, plotW));
  const H = 170, PAD = { l: 26, r: 10, t: 10, b: 22 };
  const xOf = (i: number) => PAD.l + (monthDays.length <= 1 ? 0 : (i * (W - PAD.l - PAD.r)) / (monthDays.length - 1));
  const yOf = (m: number) => PAD.t + ((10 - m) * (H - PAD.t - PAD.b)) / 9;
  const segments = $derived.by(() => {
    const out: string[] = [];
    let run: string[] = [];
    monthDays.forEach((d, i) => {
      const m = byDay.get(d)?.mood;
      if (m == null) {
        if (run.length > 1) out.push(run.join(" "));
        run = [];
      } else run.push(`${xOf(i)},${yOf(m)}`);
    });
    if (run.length > 1) out.push(run.join(" "));
    return out;
  });
  let hover = $state<number | null>(null);
  const hovered = $derived(hover === null ? null : { d: monthDays[hover], x: byDay.get(monthDays[hover]) });

  // the moments
  const moments = $derived(inMonth.filter((x) => x.best || x.worst)
    .filter((x) => !starredOnly || x.best_star || x.worst_star).slice().reverse());
  async function star(x: DiaryDay, which: "best" | "worst") {
    const on = which === "best" ? !x.best_star : !x.worst_star;
    days = days.map((y) => (y.id === x.id ? { ...y, [`${which}_star`]: on } : y)); // at once
    try {
      await undoable(on ? "Starred a moment" : "Unstarred a moment", () => setStar(x.id, which, on));
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
      await load();
    }
  }

  // where the moments come from, and the mood on days whose happiest moment was there
  const areas = $derived.by(() => {
    const rows = AREAS.map((a) => {
      const best = inMonth.filter((x) => x.best && x.best_area === a);
      return { a, best: best.length, worst: inMonth.filter((x) => x.worst && x.worst_area === a).length, mood: mean(moodsOf(best)) };
    }).filter((r) => r.best || r.worst);
    const untagged = { best: inMonth.filter((x) => x.best && !x.best_area).length, worst: inMonth.filter((x) => x.worst && !x.worst_area).length };
    return { rows, untagged, max: Math.max(1, ...rows.flatMap((r) => [r.best, r.worst])) };
  });

  // where the time went: hours logged in Week and Time, by area
  const time = $derived.by(() => {
    if (!tax) return { rows: [] as { label: string; hours: number }[], total: 0 };
    const areaOfCat = new Map(tax.allCategories.map((c) => [c.id, c.area_id]));
    const hours = new Map<string, number>();
    for (const e of entries) {
      const a = areaOfCat.get(e.category_id) ?? "";
      hours.set(a, (hours.get(a) ?? 0) + e.minutes / 60);
    }
    const rows = tax.areas.map((a) => ({ label: a.label, hours: hours.get(a.id) ?? 0 })).filter((r) => r.hours > 0);
    if (hours.get("")) rows.push({ label: "Other", hours: hours.get("")! });
    return { rows, total: rows.reduce((s, r) => s + r.hours, 0) };
  });
  const maxHours = $derived(Math.max(1, ...time.rows.map((r) => r.hours)));

  let savingReflection = $state(false);
  async function keepReflection() {
    savingReflection = true;
    try {
      const r = reflection.trim() || null;
      await undoable(`Saved the reflection on ${monthName(month)}`, () => saveMonth(month, r));
      savedReflection = reflection;
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
    } finally {
      savingReflection = false;
    }
  }
</script>

<section class="diary">
  <div class="head">
    <div>
      <span class="eyebrow">Diary</span>
      <h1>Your days</h1>
    </div>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading && !days.length && !missing}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">The diary needs its tables first: run <code>web/db/0059_diary.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    <!-- ================= the day ================= -->
    <div class="card day-card">
      <div class="day-nav">
        <button aria-label="The day before" onclick={() => go(addDays(day, -1))}>‹</button>
        <input type="date" value={day} aria-label="Day" onchange={(ev) => ev.currentTarget.value && go(ev.currentTarget.value)} />
        <button aria-label="The day after" onclick={() => go(addDays(day, 1))}>›</button>
        {#if day !== today()}<button class="link" onclick={() => go(today())}>Today</button>{/if}
        <span class="when">{short(day)}{stored ? "" : " · not written yet"}</span>
      </div>

      <div class="moments-form">
        <div class="moment">
          <label>Happiest moment <textarea rows="2" bind:value={draft.best} placeholder="What was the best part of the day?"></textarea></label>
          <label>Why it happened <textarea rows="1" bind:value={draft.best_why} placeholder="What made it happen — you, someone, luck?"></textarea></label>
          {@render areaPick("best_area")}
        </div>
        <div class="moment">
          <label>Worst moment <textarea rows="2" bind:value={draft.worst} placeholder="What was the hardest part of the day?"></textarea></label>
          {@render areaPick("worst_area")}
        </div>
      </div>

      <div class="mood" role="group" aria-label="Mood, 1 to 10">
        <span class="label">Mood</span>
        {#each Array.from({ length: 10 }, (_, i) => i + 1) as n (n)}
          <button class:on={draft.mood === n} aria-pressed={draft.mood === n} onclick={() => pickMood(n)}>{n}</button>
        {/each}
      </div>

      <div class="buttons">
        <button class="primary" disabled={!dirty || saving} onclick={save}>{saving ? "Saving…" : "Save"}</button>
        {#if dirty}<span class="muted small">Unsaved</span>{/if}
      </div>
    </div>

    <!-- ================= the month ================= -->
    <div class="month-head">
      <button aria-label="The month before" onclick={() => go(shiftMonth(month, -1))}>‹</button>
      <h2>{monthName(month)}</h2>
      <button aria-label="The month after" onclick={() => go(shiftMonth(month, 1))}>›</button>
    </div>

    <div class="tiles">
      <div class="tile">
        <span class="t-label">Average mood</span>
        <span class="t-value">{fmt1(stats.avg)}</span>
        <span class="t-sub">{#if stats.avg !== null && stats.before !== null}{#if Math.abs(stats.avg - stats.before) < 0.05}same as last month ({fmt1(stats.before)}){:else}{stats.avg > stats.before ? "▲" : "▼"} {Math.abs(stats.avg - stats.before).toFixed(1)} on last month ({fmt1(stats.before)}){/if}{:else if stats.avg !== null}median {fmt1(stats.median)}{:else}no mood yet{/if}</span>
      </div>
      <div class="tile">
        <span class="t-label">Highest</span>
        <span class="t-value">{stats.high ?? "–"}</span>
        <span class="t-sub">{dateList(stats.highDays)}</span>
      </div>
      <div class="tile">
        <span class="t-label">Lowest</span>
        <span class="t-value">{stats.low ?? "–"}</span>
        <span class="t-sub">{dateList(stats.lowDays)}</span>
      </div>
      <div class="tile">
        <span class="t-label">Days written</span>
        <span class="t-value">{stats.written}<span class="of"> / {monthDays.length}</span></span>
        <span class="t-sub">{stats.rated ? `${stats.good} good (7+) · ${stats.hard} hard (4 or less)` : ""}</span>
      </div>
    </div>

    <figure class="chart">
      <figcaption>Mood, day by day</figcaption>
      <div class="plot" bind:clientWidth={plotW} onmouseleave={() => (hover = null)} role="img" aria-label={`Mood over ${monthName(month)}: average ${fmt1(stats.avg)}, from ${stats.low ?? "–"} to ${stats.high ?? "–"}`}>
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
          {#each [1, 5, 10] as g (g)}
            <line class="grid" x1={PAD.l} x2={W - PAD.r} y1={yOf(g)} y2={yOf(g)} />
            <text class="axis" x={PAD.l - 6} y={yOf(g) + 4} text-anchor="end">{g}</text>
          {/each}
          {#if stats.avg !== null}
            <line class="avg" x1={PAD.l} x2={W - PAD.r} y1={yOf(stats.avg)} y2={yOf(stats.avg)} />
          {/if}
          {#each monthDays as d, i (d)}
            {#if i === 0 || (i + 1) % 5 === 0}<text class="axis" x={xOf(i)} y={H - 6} text-anchor="middle">{i + 1}</text>{/if}
          {/each}
          {#if hover !== null}<line class="cross" x1={xOf(hover)} x2={xOf(hover)} y1={PAD.t} y2={H - PAD.b} />{/if}
          {#each segments as pts, i (i)}<polyline class="line" points={pts} />{/each}
          {#each monthDays as d, i (d)}
            {@const m = byDay.get(d)?.mood}
            {#if m != null}<circle class="dot" class:on={hover === i} cx={xOf(i)} cy={yOf(m)} r="4" />{/if}
          {/each}
          {#each monthDays as d, i (d)}
            <rect class="hit" x={xOf(i) - (W - PAD.l - PAD.r) / Math.max(1, monthDays.length - 1) / 2} y="0"
                  width={(W - PAD.l - PAD.r) / Math.max(1, monthDays.length - 1)} height={H}
                  role="button" tabindex="-1" aria-label={`Open ${short(d)}`}
                  onmouseenter={() => (hover = i)} onclick={() => go(d)} onkeydown={() => {}} />
          {/each}
        </svg>
        {#if hovered}
          {@const hx = xOf(hover!)}
          <div class="tip" style:left={hx <= W / 2 ? `${hx + 12}px` : null} style:right={hx > W / 2 ? `${W - hx + 12}px` : null}>
            <strong>{short(hovered.d)}</strong>
            {#if hovered.x}
              <span>Mood {hovered.x.mood ?? "–"}</span>
              {#if hovered.x.best}<span class="t-best">☀ {hovered.x.best}</span>{/if}
              {#if hovered.x.worst}<span class="t-worst">☁ {hovered.x.worst}</span>{/if}
            {:else}<span class="muted">Not written</span>{/if}
            <span class="muted small">Click to open</span>
          </div>
        {/if}
      </div>
      <p class="muted small legend-line">Dashed line: the month's average. A gap means a day without a mood.</p>
    </figure>

    <section class="block">
      <div class="block-head">
        <h3>The moments</h3>
        <label class="small"><input type="checkbox" bind:checked={starredOnly} /> Starred only</label>
      </div>
      {#if !moments.length}
        <p class="muted small">{starredOnly ? "No starred moments this month. Click ☆ beside one to star it." : "Nothing written this month yet."}</p>
      {:else}
        <table class="moments">
          <thead><tr><th>Day</th><th>Happiest</th><th>Worst</th><th class="num">Mood</th></tr></thead>
          <tbody>
            {#each moments as x (x.id)}
              <tr>
                <td><button class="link" onclick={() => go(x.day)}>{short(x.day)}</button></td>
                <td>
                  {#if x.best}
                    <button class="star" class:on={x.best_star} aria-pressed={x.best_star} aria-label="Star this moment" onclick={() => star(x, "best")}>{x.best_star ? "★" : "☆"}</button>
                    {x.best}{#if x.best_why}<span class="why"> — {x.best_why}</span>{/if}
                    {#if x.best_area}<span class="tag">{areaLabel(x.best_area)}</span>{/if}
                  {/if}
                </td>
                <td>
                  {#if x.worst}
                    <button class="star" class:on={x.worst_star} aria-pressed={x.worst_star} aria-label="Star this moment" onclick={() => star(x, "worst")}>{x.worst_star ? "★" : "☆"}</button>
                    {x.worst}{#if x.worst_area}<span class="tag">{areaLabel(x.worst_area)}</span>{/if}
                  {/if}
                </td>
                <td class="num">{x.mood ?? ""}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <div class="two">
      <section class="block">
        <h3>Where the moments come from</h3>
        {#if !areas.rows.length}
          <p class="muted small">Tag a moment with a life area to see it here.</p>
        {:else}
          <table class="bars">
            <thead><tr><th>Area</th><th><span class="sw best"></span>Happiest</th><th><span class="sw worst"></span>Worst</th><th class="num" title="Average mood on days whose happiest moment was in this area">Mood</th></tr></thead>
            <tbody>
              {#each areas.rows as r (r.a)}
                <tr>
                  <td>{areaLabel(r.a)}</td>
                  <td>{#if r.best}<span class="bar best" style:width={`calc(${r.best / areas.max} * (100% - 3.5rem))`}></span>{/if}<span class="n">{r.best}</span></td>
                  <td>{#if r.worst}<span class="bar worst" style:width={`calc(${r.worst / areas.max} * (100% - 3.5rem))`}></span>{/if}<span class="n">{r.worst}</span></td>
                  <td class="num">{fmt1(r.mood)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if areas.untagged.best || areas.untagged.worst}
            <p class="muted small">Not tagged: {areas.untagged.best} happiest, {areas.untagged.worst} worst.</p>
          {/if}
        {/if}
      </section>

      <section class="block">
        <h3>Where the time went</h3>
        {#if !time.rows.length}
          <p class="muted small">No time logged this month.</p>
        {:else}
          <table class="bars">
            <tbody>
              {#each time.rows as r (r.label)}
                <tr>
                  <td>{r.label}</td>
                  <td><span class="bar time" style:width={`calc(${r.hours / maxHours} * (100% - 4.5rem))`}></span><span class="n">{r.hours.toFixed(1)} h</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
          <p class="muted small">{time.total.toFixed(1)} h logged in all, from Week and Time.</p>
        {/if}
      </section>
    </div>

    <section class="block">
      <h3>Looking back on {monthName(month)}</h3>
      <textarea rows="4" bind:value={reflection} placeholder="What did you notice this month? What would you keep, and what would you change next month?"></textarea>
      <div class="buttons">
        <button class="primary" disabled={reflection === savedReflection || savingReflection} onclick={keepReflection}>{savingReflection ? "Saving…" : "Save reflection"}</button>
      </div>
    </section>
  {/if}
</section>

{#snippet areaPick(which: "best_area" | "worst_area")}
  <div class="areas" role="group" aria-label="Life area">
    {#each AREAS as a (a)}
      <button class="chip" class:on={draft[which] === a} aria-pressed={draft[which] === a} onclick={() => pickArea(which, a)}>{areaLabel(a)}</button>
    {/each}
  </div>
{/snippet}

<style>
  .head { margin-bottom: 1rem; }
  .head h1 { margin: 0; }
  .small { font-size: 0.8rem; }
  .card { background: var(--panel); border-radius: var(--radius); padding: 1rem; display: grid; gap: 0.9rem; }
  .day-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; font-family: var(--font-ui); }
  .day-nav input { width: auto; }
  .day-nav button:not(.link) { padding: 0.35rem 0.7rem; }
  .when { color: var(--ink-soft); font-size: 0.88rem; margin-left: 0.3rem; }
  .link { background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; font: inherit; text-align: left; }
  .moments-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; }
  .moment { display: grid; gap: 0.45rem; align-content: start; }
  .moment label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  textarea { color: var(--ink); resize: vertical; }
  .areas { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .chip { font-size: 0.75rem; padding: 0.12rem 0.6rem; border-radius: 999px; background: none; font-family: var(--font-ui); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .mood { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem; font-family: var(--font-ui); }
  .mood .label { font-size: 0.85rem; color: var(--ink-soft); margin-right: 0.4rem; }
  .mood button { width: 2.2rem; padding: 0.35rem 0; font-variant-numeric: tabular-nums; }
  .mood button.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
  .buttons { display: flex; align-items: center; gap: 0.6rem; }

  .month-head { display: flex; align-items: center; gap: 0.6rem; margin: 2rem 0 0.8rem; }
  .month-head h2 { margin: 0; min-width: 11rem; text-align: center; }
  .month-head button { padding: 0.3rem 0.7rem; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: 0.6rem; font-family: var(--font-ui); }
  .tile { background: var(--panel); border-radius: var(--radius); padding: 0.6rem 0.8rem; display: grid; gap: 0.1rem; }
  .t-label { font-size: 0.78rem; color: var(--ink-soft); }
  .t-value { font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--ink); }
  .t-value .of { font-size: 0.9rem; font-weight: 400; color: var(--ink-soft); }
  .t-sub { font-size: 0.75rem; color: var(--ink-soft); min-height: 1em; }

  .chart { margin: 1rem 0 0; background: var(--panel); border-radius: var(--radius); padding: 0.8rem; }
  figcaption { font-family: var(--font-ui); font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; }
  .plot { position: relative; }
  svg { display: block; overflow: visible; }
  .grid { stroke: var(--rule); stroke-width: 1; }
  .avg { stroke: var(--ink-soft); stroke-width: 1; stroke-dasharray: 4 4; }
  .cross { stroke: var(--ink-soft); stroke-width: 1; }
  .axis { fill: var(--ink-soft); font-family: var(--font-ui); font-size: 11px; }
  .line { fill: none; stroke: var(--accent); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .dot { fill: var(--accent); stroke: var(--panel); stroke-width: 2; }
  .dot.on { r: 6; }
  .hit { fill: transparent; cursor: pointer; outline: none; }
  .tip {
    position: absolute; top: 0; pointer-events: none; z-index: 2;
    display: grid; gap: 0.1rem; max-width: 16rem; padding: 0.45rem 0.6rem; border-radius: var(--radius);
    background: var(--paper); border: 1px solid var(--rule); box-shadow: 0 4px 14px rgb(0 0 0 / 0.15);
    font-family: var(--font-ui); font-size: 0.78rem; color: var(--ink);
  }
  .tip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-line { margin: 0.3rem 0 0; }

  .block { margin-top: 1.4rem; }
  .block h3 { font-size: 1rem; margin: 0 0 0.5rem; }
  .block-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
  .block-head label { display: flex; gap: 0.3rem; align-items: center; font-family: var(--font-ui); color: var(--ink-soft); }
  .block-head input { width: auto; }
  .block textarea { width: 100%; margin-bottom: 0.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th { text-align: left; font-family: var(--font-ui); font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--rule); }
  td { padding: 0.35rem 0.4rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .moments td:first-child { white-space: nowrap; font-family: var(--font-ui); font-size: 0.8rem; }
  .why { color: var(--ink-soft); }
  .tag { font-family: var(--font-ui); font-size: 0.7rem; color: var(--ink-soft); border: 1px solid var(--rule); border-radius: 999px; padding: 0 0.45rem; margin-left: 0.35rem; white-space: nowrap; }
  .star { background: none; border: none; padding: 0 0.25rem 0 0; color: var(--ink-soft); font-size: 0.95rem; line-height: 1; }
  .star.on { color: var(--series-4); }
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 0 1.5rem; }
  .bars td { vertical-align: middle; font-family: var(--font-ui); font-size: 0.82rem; }
  .bars td { white-space: nowrap; }
  .bars td:first-child, .bars th:first-child { width: 6.5rem; }
  .bars .num { width: 3.5rem; }
  .bar { display: inline-block; height: 0.55rem; border-radius: 0 4px 4px 0; vertical-align: middle; }
  .bar.best, .sw.best { background: var(--series-1); }
  .bar.worst, .sw.worst { background: var(--series-2); }
  .bar.time { background: var(--accent); }
  .n { margin-left: 0.35rem; font-variant-numeric: tabular-nums; color: var(--ink); }
  .sw { display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 2px; margin-right: 0.3rem; vertical-align: baseline; }
  @media (max-width: 40rem) {
    .moments thead { display: none; }
    .moments tr { display: grid; grid-template-columns: 1fr auto; padding: 0.4rem 0; border-bottom: 1px solid var(--rule); }
    .moments td { border: none; padding: 0.1rem 0; }
    .moments td:nth-child(2), .moments td:nth-child(3) { grid-column: 1 / -1; }
    .moments td.num { grid-row: 1; grid-column: 2; }
  }
</style>
