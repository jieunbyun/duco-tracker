<script module lang="ts">
  // kept while the app is open, so coming back (or an undo, which reloads the tab) finds the same day
  const last = { day: "" };
</script>

<script lang="ts">
  // Day: everything you wrote down on one day, across the tabs — the diary, time, the calendar,
  // to-dos and small tasks, meetings, notes of every kind, the Logbook, expenses — to read back
  // like a diary. Click anything to change it in its own tab; "Back to Day" brings you back.
  import { loadDay, diaryLines } from "../lib/day";
  import type { DayLog } from "../lib/day";
  import { openFromDay, arrivedAt } from "../lib/dayBack.svelte";
  import { addDays, today, parse } from "../lib/dates";

  const arrivedDay = arrivedAt("day").get("d");
  let day = $state(arrivedDay && /^\d{4}-\d\d-\d\d$/.test(arrivedDay) ? arrivedDay : last.day || today());
  $effect(() => {
    last.day = day;
  });

  let log = $state<DayLog | null>(null);
  let loading = $state(true);
  let error = $state("");
  let request = 0;
  async function load(d: string) {
    const id = ++request;
    loading = true;
    try {
      const l = await loadDay(d);
      if (id !== request) return;
      log = l;
      error = "";
    } catch (e) {
      if (id === request) error = (e as Error).message;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    load(day);
  });

  const long = (d: string) => parse(d).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const go = (d: string) => (day = d);
  const isToday = $derived(day === today());
  const empty = $derived(!!log && !log.diary && !log.sections.length);

  function open(ev: MouseEvent, href: string) {
    if (ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey) return; // a new tab: the link as it is
    ev.preventDefault();
    openFromDay(day, href);
  }

  // ← and → move a day, unless you are typing or a dialog is open
  function keys(ev: KeyboardEvent) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey || ev.shiftKey) return;
    if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
    const el = document.activeElement as HTMLElement | null;
    if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
    if (document.querySelector("dialog[open]")) return;
    ev.preventDefault();
    go(addDays(day, ev.key === "ArrowLeft" ? -1 : 1));
  }
</script>

<svelte:window onkeydown={keys} />

<section class="day">
  <div class="head">
    <span class="eyebrow">Day</span>
    <h1>{long(day)}</h1>
    <div class="nav">
      <button aria-label="The day before" title="The day before (←)" onclick={() => go(addDays(day, -1))}>‹</button>
      <input type="date" value={day} aria-label="Day" onchange={(ev) => ev.currentTarget.value && go(ev.currentTarget.value)} />
      <button aria-label="The day after" title="The day after (→)" onclick={() => go(addDays(day, 1))}>›</button>
      {#if !isToday}<button onclick={() => go(today())}>Today</button>{/if}
      {#if loading && log}<span class="muted small">Loading…</span>{/if}
    </div>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if !log}
    <p class="muted">Loading…</p>
  {:else}
    <div class:fading={loading}>
      {#if !log.diaryMissing}
        <div class="diary">
          <h2>Diary</h2>
          {#if log.diary}
            {@const d = log.diary}
            <a class="item" href={`#/diary?d=${day}`} onclick={(ev) => open(ev, `#/diary?d=${day}`)}>
              {#if d.mood !== null}<span class="mood">Mood <strong>{d.mood}</strong>/10</span>{/if}
              {#each diaryLines(d) as m (m.label)}
                <span class="moment">
                  <span class="label">{m.label}{m.star ? " ★" : ""}</span>
                  <span class="text">{m.text}{#if m.why}<span class="muted"> — {m.why}</span>{/if}</span>
                  {#if m.area}<span class="meta">{m.area}</span>{/if}
                </span>
              {/each}
            </a>
          {:else}
            <p class="muted">Nothing in the diary for this day.
              <a href={`#/diary?d=${day}`} onclick={(ev) => open(ev, `#/diary?d=${day}`)}>Write it</a></p>
          {/if}
        </div>
      {/if}

      {#each log.sections as s (s.key)}
        {@const timed = s.items.some((it) => it.when)}
        <div class="part">
          <h2>{s.title} {#if s.total}<span class="muted total">{s.total}</span>{/if}</h2>
          <ul>
            {#each s.items as it (it.key)}
              <li>
                <a class="item" href={it.href ?? "#"} onclick={(ev) => it.href && open(ev, it.href)} title="Click to change it in its tab">
                  {#if timed}<span class="when">{it.when ?? ""}</span>{/if}
                  <span class="main">
                    {#if it.meta}<span class="meta">{it.meta}</span>{/if}
                    {#if it.done !== undefined}<span class="tick" class:on={it.done} aria-label={it.done ? "Done" : "Not done"}>{it.done ? "✓" : "○"}</span>{/if}
                    <span class="text" class:done={it.done}>{it.text}</span>
                    {#if it.more}<span class="more muted">{it.more}</span>{/if}
                  </span>
                </a>
              </li>
            {/each}
          </ul>
        </div>
      {/each}

      {#if empty}
        <p class="muted nothing">Nothing written down on this day.</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .day { max-width: 46rem; }
  .head { margin-bottom: 1.2rem; }
  .head h1 { margin: 0 0 0.6rem; }
  .nav { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  .nav input { width: auto; }
  .nav button { padding: 0.35rem 0.8rem; }
  .small { font-size: 0.8rem; }
  .fading { opacity: 0.6; transition: opacity 0.15s; }

  h2 {
    font-size: 0.8rem; font-family: var(--font-ui); text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--ink-soft); margin: 0 0 0.3rem; padding-bottom: 0.25rem; border-bottom: 1px solid var(--rule);
  }
  .total { text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: 0.4rem; }
  .diary, .part { margin-bottom: 1.4rem; }
  ul { list-style: none; margin: 0; padding: 0; }

  /* each entry is a link to where it is changed */
  .item {
    display: flex; gap: 0.8rem; align-items: baseline; padding: 0.35rem 0.4rem; margin: 0 -0.4rem;
    border-radius: var(--radius); color: inherit; text-decoration: none;
  }
  .item:hover, .item:focus-visible { background: var(--panel); }
  .when {
    flex: none; width: 6.5rem; font-family: var(--font-ui); font-size: 0.82rem; color: var(--ink-soft);
    font-variant-numeric: tabular-nums;
  }
  .main { flex: 1; min-width: 0; display: flow-root; }
  .text { white-space: pre-line; overflow-wrap: anywhere; }
  .text.done { color: var(--ink-soft); }
  /* where it belongs, at the right of its last line when there is room */
  .meta {
    float: right; margin: 0.15rem 0 0 0.8rem; max-width: 50%;
    font-family: var(--font-ui); font-size: 0.75rem; color: var(--ink-soft); text-align: right;
  }
  .more {
    display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
    clear: both; white-space: pre-line; font-size: 0.9rem; margin-top: 0.15rem;
  }
  .tick { font-family: var(--font-ui); color: var(--ink-soft); margin-right: 0.35rem; }
  .tick.on { color: var(--accent); }

  .diary .item { flex-direction: column; align-items: stretch; gap: 0.3rem; }
  .mood { font-family: var(--font-ui); font-size: 0.9rem; }
  .moment { display: flow-root; width: 100%; }
  .moment .label {
    font-family: var(--font-ui); font-size: 0.8rem; color: var(--ink-soft); margin-right: 0.5rem;
  }
  .nothing { margin-top: 1rem; }

  @media (max-width: 36rem) {
    .item { flex-direction: column; align-items: stretch; gap: 0.1rem; }
    .when { width: auto; }
    .when:empty { display: none; }
    .meta { max-width: 60%; }
  }
</style>
