<script lang="ts">
  // Pathways' Ambitions view: every activity once, as a row under its type of work; your ambitions as
  // columns, a tick where an activity serves one. Each type's heading counts what serves each ambition,
  // so a gap (0) stands out, with + to fill it. Filtered to the active ones (or all) and to a period.
  import { LANES, NODE_KINDS, staged, fmtMonth, monthStart, monthEnd, addMonths } from "./pathways";
  import type { PwNode, Lane } from "./pathways";
  import { today } from "./dates";

  export type CovAmbition = { id: string; title: string; detail: string | null; active: boolean; colour: string };
  type Props = {
    items: PwNode[]; // every item but the ambitions, as shown (a linked project's name and dates)
    ambitions: CovAmbition[]; // in your order
    ticks: Map<string, string[]>; // the ambitions each item is ticked for
    via: Map<string, string[]>; // for an item without ticks: the ambitions its links lead to
    projectName: (id: string) => string;
    ready: boolean; // the ticks' table is there (0080)
    readonly?: boolean;
    onopen: (id: string) => void; // an activity, or an ambition, in the side sheet
    ontick: (nodeId: string, ambitionId: string) => void;
    onadd: (lane: Lane, ambitionId: string) => void;
    onnewamb: () => void;
    onreorder: (ids: string[]) => void;
  };
  let { items, ambitions, ticks, via, projectName, ready, readonly = false, onopen, ontick, onadd, onnewamb, onreorder }: Props = $props();

  // ---- the filters, remembered on this computer ----
  const KEY = "pathways.coverage";
  type Show = "active" | "all";
  type Period = "year" | "12m" | "custom" | "all";
  function saved(): { show: Show; period: Period; from: string; to: string } {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) ?? "{}");
      return {
        show: v.show === "all" ? "all" : "active",
        period: ["year", "12m", "custom", "all"].includes(v.period) ? v.period : "all",
        from: typeof v.from === "string" ? v.from : "", to: typeof v.to === "string" ? v.to : "",
      };
    } catch {
      return { show: "active", period: "all", from: "", to: "" };
    }
  }
  const s0 = saved();
  let show = $state<Show>(s0.show);
  let period = $state<Period>(s0.period);
  let from = $state(s0.from); // "YYYY-MM"
  let to = $state(s0.to);
  $effect(() => {
    const v = JSON.stringify({ show, period, from, to });
    try { localStorage.setItem(KEY, v); } catch {}
  });

  /** The period as first and last days; null for all time. */
  const range = $derived.by((): [string, string] | null => {
    const t = today();
    if (period === "year") return [`${t.slice(0, 4)}-01-01`, `${t.slice(0, 4)}-12-31`];
    if (period === "12m") return [t, monthEnd(addMonths(monthStart(t), 11))];
    if (period === "custom") return [from ? `${from}-01` : "0000-01-01", to ? monthEnd(`${to}-01`) : "9999-12-31"];
    return null;
  });
  const periodLabel = $derived(period === "year" ? `in ${today().slice(0, 4)}` : period === "12m" ? "in the next 12 months" : period === "custom" ? "in this period" : "");

  const isActive = (n: PwNode) => n.status === "active" && n.grant_stage !== "declined";
  /** Its dates overlap the period (one without an end runs on; one without dates always shows). */
  function inPeriod(n: PwNode): boolean {
    if (!range) return true;
    const s = n.start_on, e = n.end_on;
    if (!s && !e) return true;
    return (s ?? e!) <= range[1] && (e ?? "9999-12-31") >= range[0];
  }

  const cols = $derived(ambitions.filter((a) => show === "all" || a.active));
  /** The ambitions it serves: ticked, or (none ticked) where its links lead. */
  function serves(n: PwNode): { ids: string[]; via: boolean } {
    const t = ticks.get(n.id) ?? [];
    return t.length ? { ids: t, via: false } : { ids: via.get(n.id) ?? [], via: true };
  }

  const GROUPS: { lane: Lane; label: string; always: boolean }[] = [
    { lane: "publications", label: LANES.find((l) => l.key === "publications")!.label, always: true },
    { lane: "grants", label: LANES.find((l) => l.key === "grants")!.label, always: true },
    { lane: "awards", label: LANES.find((l) => l.key === "awards")!.label, always: true },
    { lane: "teaching", label: LANES.find((l) => l.key === "teaching")!.label, always: true },
    { lane: "outreach", label: LANES.find((l) => l.key === "outreach")!.label, always: false },
    { lane: "goals", label: "Objectives & knowledge gaps", always: false },
  ];
  const sortKey = (n: PwNode) => n.start_on ?? n.end_on ?? "9999-99";
  const groups = $derived.by(() => {
    const shown = items.filter((n) => (show === "all" || isActive(n)) && inPeriod(n));
    return GROUPS.map((g) => ({
      ...g,
      rows: shown.filter((n) => n.lane === g.lane).sort((a, b) => sortKey(a).localeCompare(sortKey(b)) || a.title.localeCompare(b.title)),
    })).filter((g) => g.always || g.rows.length);
  });
  const count = (rows: PwNode[], a: string) => rows.filter((n) => serves(n).ids.includes(a)).length;

  function when(n: PwNode): string {
    const s = n.start_on, e = n.end_on;
    if (staged(n.kind) && e) return `deadline ${fmtMonth(e)}`;
    if (s && e) return s.slice(0, 7) === e.slice(0, 7) ? fmtMonth(s) : `${fmtMonth(s)} → ${fmtMonth(e)}`;
    if (s) return `from ${fmtMonth(s)}`;
    if (e) return `by ${fmtMonth(e)}`;
    return "no dates";
  }
  function stage(n: PwNode): string {
    if (n.status !== "active") return n.status;
    if (staged(n.kind)) return n.grant_stage ?? "drafting";
    return n.potential ? "potential" : "";
  }
  function note(n: PwNode): string {
    if (n.milestone_id && n.project_id) return `milestone of ${projectName(n.project_id)}`;
    if (n.kind === "person" || n.kind === "gap" || n.kind === "objective" || n.kind === "goal") {
      return NODE_KINDS.find((k) => k.key === n.kind)?.label.toLowerCase() ?? "";
    }
    return n.kind === "project" && n.hands_on ? "hands-on" : "";
  }
  function tickTitle(n: PwNode, a: CovAmbition, on: boolean, isVia: boolean): string {
    if (!on) return `Serves “${a.title}”? Click to tick`;
    return isVia ? `Serves “${a.title}” through its links. Click to tick it` : `Serves “${a.title}”. Click to untick`;
  }

  // ---- your order of the ambitions: drag a column's ⠿ (or ← → on it) ----
  let colDrag = $state<{ id: string; x: number; mids: Map<string, number> } | null>(null);
  let tableEl = $state<HTMLTableElement | null>(null);
  const dropAt = $derived.by(() => {
    if (!colDrag) return null;
    const d = colDrag;
    const others = cols.filter((a) => a.id !== d.id);
    const k = others.filter((a) => (d.mids.get(a.id) ?? 0) < d.x).length;
    return { k, before: others[k]?.id ?? null, last: others[others.length - 1]?.id ?? null };
  });
  function colStart(ev: PointerEvent, id: string) {
    if (ev.button !== 0 || readonly) return;
    ev.preventDefault();
    const mids = new Map<string, number>();
    for (const el of tableEl?.querySelectorAll<HTMLElement>("[data-amb-col]") ?? []) {
      const r = el.getBoundingClientRect();
      mids.set(el.dataset.ambCol!, r.left + r.width / 2);
    }
    colDrag = { id, x: ev.clientX, mids };
    window.addEventListener("pointermove", colMove);
    window.addEventListener("pointerup", colUp);
    window.addEventListener("pointercancel", colUp);
  }
  function colMove(ev: PointerEvent) {
    if (colDrag) colDrag = { ...colDrag, x: ev.clientX };
  }
  function colUp(ev: PointerEvent) {
    window.removeEventListener("pointermove", colMove);
    window.removeEventListener("pointerup", colUp);
    window.removeEventListener("pointercancel", colUp);
    const d = colDrag, at = dropAt;
    colDrag = null;
    if (!d || !at || ev.type === "pointercancel") return;
    const ids = cols.map((a) => a.id).filter((id) => id !== d.id);
    ids.splice(at.k, 0, d.id);
    if (ids.join() !== cols.map((a) => a.id).join()) onreorder(ids);
  }
  function colKey(ev: KeyboardEvent, id: string) {
    if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
    ev.preventDefault();
    const ids = cols.map((a) => a.id);
    const i = ids.indexOf(id), j = i + (ev.key === "ArrowLeft" ? -1 : 1);
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    onreorder(ids);
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-col-grip="${id}"]`)?.focus());
  }
</script>

<div class="cov">
  <div class="cov-bar">
    <div class="seg" role="group" aria-label="Which activities">
      <button class:on={show === "active"} aria-pressed={show === "active"} onclick={() => (show = "active")}>Active</button>
      <button class:on={show === "all"} aria-pressed={show === "all"} onclick={() => (show = "all")}>All</button>
    </div>
    <div class="seg" role="group" aria-label="Period">
      <span class="muted">Period</span>
      <button class:on={period === "year"} aria-pressed={period === "year"} onclick={() => (period = "year")}>This year</button>
      <button class:on={period === "12m"} aria-pressed={period === "12m"} onclick={() => (period = "12m")}>Next 12 months</button>
      <button class:on={period === "custom"} aria-pressed={period === "custom"} onclick={() => (period = "custom")}>From … to …</button>
      <button class:on={period === "all"} aria-pressed={period === "all"} onclick={() => (period = "all")}>All time</button>
    </div>
    {#if period === "custom"}
      <span class="custom">
        <label>from <input type="month" bind:value={from} max={to || undefined} /></label>
        <label>to <input type="month" bind:value={to} min={from || undefined} /></label>
      </span>
    {/if}
    <span class="spacer"></span>
    {#if !readonly}<button class="primary" onclick={onnewamb}>+ Ambition</button>{/if}
  </div>
  {#if !ready}
    <p class="note-sql">Ticking an activity for more than one ambition needs <code>web/db/0080_pw_node_ambition.sql</code> run first, in the Supabase SQL editor. Until then each shows the one ambition it had.</p>
  {/if}

  {#if !cols.length}
    <p class="muted">No {show === "active" && ambitions.length ? "active " : ""}ambitions yet. Add your two or three big ones with <em>+ Ambition</em>: each becomes a column, to tick what serves it.</p>
  {:else}
    <div class="cov-scroll">
      <table bind:this={tableEl} class:dragging={!!colDrag}>
        <thead>
          <tr>
            <th class="c-name" scope="col">Activity</th>
            <th class="c-when" scope="col">When</th>
            <th class="c-stage" scope="col">Stage</th>
            {#each cols as a (a.id)}
              <th class="c-amb" scope="col" data-amb-col={a.id} style:--amb={a.colour} class:lifting={colDrag?.id === a.id}
                  class:drop-before={!!colDrag && dropAt?.before === a.id} class:drop-after={!!colDrag && dropAt?.before === null && dropAt?.last === a.id}
                  class:retired={!a.active}>
                <div class="amb-h">
                  {#if !readonly && cols.length > 1}
                    <span class="grip" role="button" tabindex="0" data-col-grip={a.id} aria-label={`Move “${a.title}” (drag, or the arrow keys)`}
                          title="Drag to put the ambitions in your order" onpointerdown={(ev) => colStart(ev, a.id)} onkeydown={(ev) => colKey(ev, a.id)}>⠿</span>
                  {/if}
                  <button class="amb-name" title={`${a.title}${a.detail ? `\n${a.detail}` : ""}\nClick to change it`} onclick={() => onopen(a.id)}>{a.title}</button>
                </div>
                {#if a.detail}<span class="amb-detail">{a.detail}</span>{/if}
              </th>
            {/each}
          </tr>
        </thead>
        {#each groups as g (g.lane)}
          <tbody class="lane-{g.lane}">
            <tr class="g-head">
              <th scope="rowgroup" colspan="3">{g.label} <span class="muted">{g.rows.length}</span></th>
              {#each cols as a (a.id)}
                {@const k = count(g.rows, a.id)}
                <td class="g-count" class:gap={!k} style:--amb={a.colour}>
                  <span title={`${k} ${g.label.toLowerCase()} serving “${a.title}”${periodLabel ? ` ${periodLabel}` : ""}`}>{k}</span>
                  {#if !readonly}
                    <button class="plus" title={`Add to ${g.label} for “${a.title}”`} aria-label={`Add to ${g.label} for “${a.title}”`}
                            onclick={() => onadd(g.lane, a.id)}>+</button>
                  {/if}
                </td>
              {/each}
            </tr>
            {#each g.rows as n (n.id)}
              {@const sv = serves(n)}
              <tr class:off={!isActive(n)}>
                <td class="c-name">
                  <button class="act" onclick={() => onopen(n.id)} title="Open it at the side">{n.milestone_id ? "◆ " : ""}{n.title}</button>
                  {#if note(n)}<span class="act-note">{note(n)}</span>{/if}
                </td>
                <td class="c-when" class:undated={!n.start_on && !n.end_on}>{when(n)}</td>
                <td class="c-stage">{stage(n)}</td>
                {#each cols as a (a.id)}
                  {@const on = sv.ids.includes(a.id)}
                  <td class="c-tick">
                    <button class="tick" class:on={on && !sv.via} class:via={on && sv.via} style:--amb={a.colour}
                            aria-pressed={on && !sv.via} disabled={readonly}
                            aria-label={`${n.title} serves ${a.title}`} title={tickTitle(n, a, on, sv.via)}
                            onclick={() => ontick(n.id, a.id)}></button>
                  </td>
                {/each}
              </tr>
            {:else}
              <tr class="empty"><td colspan={3 + cols.length} class="muted">Nothing here{periodLabel ? ` ${periodLabel}` : ""}.</td></tr>
            {/each}
          </tbody>
        {/each}
      </table>
    </div>
    <p class="hint muted">
      Click a cell to tick or untick it · a hollow square: it serves that ambition through its links (click to tick it) ·
      a <strong>0</strong> in a heading is a gap: <strong>+</strong> adds an activity there, new or from Planning · click a name to open it ·
      drag an ambition's ⠿ to reorder them{period !== "all" ? " · an activity shows if its dates overlap the period; one without dates always shows" : ""}.
    </p>
  {/if}
</div>

<style>
  .cov { font-family: var(--font-ui); }
  .cov-bar { display: flex; flex-wrap: wrap; gap: 0.5rem 0.9rem; align-items: center; margin: 0.8rem 0 0.6rem; font-size: 0.82rem; }
  .seg { display: flex; flex-wrap: wrap; gap: 0.2rem; align-items: center; }
  .seg .muted { margin-right: 0.2rem; }
  .seg button { font-size: 0.8rem; padding: 0.25rem 0.6rem; }
  .seg button.on { background: var(--ink); border-color: var(--ink); color: var(--paper); }
  .custom { display: inline-flex; gap: 0.5rem; align-items: center; }
  .custom label { display: inline-flex; gap: 0.3rem; align-items: center; color: var(--ink-soft); }
  .custom input { width: auto; font-size: 0.8rem; padding: 0.15rem 0.3rem; }
  .spacer { flex: 1; }
  .cov-bar .primary { font-size: 0.85rem; padding: 0.35rem 0.7rem; }
  .note-sql { font-size: 0.8rem; color: var(--accent); margin: 0 0 0.6rem; }

  .cov-scroll { overflow-x: auto; border: 1px solid var(--rule); background: var(--paper); }
  table { border-collapse: collapse; width: 100%; font-size: 0.84rem; }
  table.dragging { cursor: grabbing; user-select: none; }
  th, td { padding: 0.3rem 0.55rem; text-align: left; vertical-align: middle; border-bottom: 1px solid var(--rule); }
  thead th { font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); background: var(--panel); vertical-align: bottom; }
  .c-name { min-width: 14rem; }
  .c-when { white-space: nowrap; color: var(--ink-soft); font-size: 0.8rem; }
  .c-when.undated { font-style: italic; }
  .c-stage { white-space: nowrap; color: var(--ink-soft); font-size: 0.8rem; }
  .c-amb, .c-tick, .g-count { text-align: center; width: 9rem; min-width: 7rem; }
  thead .c-amb { border-top: 4px solid var(--amb); background: color-mix(in srgb, var(--amb) 10%, var(--panel)); color: var(--ink); text-align: center; }
  .c-amb.retired { opacity: 0.55; }
  .c-amb.lifting { opacity: 0.45; }
  .c-amb.drop-before { box-shadow: inset 3px 0 0 var(--accent); }
  .c-amb.drop-after { box-shadow: inset -3px 0 0 var(--accent); }
  .amb-h { display: flex; align-items: center; justify-content: center; gap: 0.3rem; }
  .amb-name {
    background: none; border: none; padding: 0; font: inherit; font-weight: 700; color: var(--amb); cursor: pointer;
    max-width: 12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .amb-name:hover { text-decoration: underline; }
  .amb-detail {
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    font-weight: 400; font-size: 0.72rem; color: var(--ink-soft); margin-top: 0.15rem;
  }
  .grip { cursor: grab; color: var(--ink-soft); user-select: none; touch-action: none; font-weight: 400; }
  .grip:focus-visible { outline: 2px solid var(--accent); }

  .g-head th, .g-head td { background: color-mix(in srgb, var(--panel) 60%, var(--paper)); border-top: 2px solid var(--rule); }
  .g-head th { font-size: 0.82rem; font-weight: 700; border-left: 4px solid var(--lane-goals); }
  .lane-publications .g-head th { border-left-color: var(--lane-publications); }
  .lane-grants .g-head th { border-left-color: var(--lane-grants); }
  .lane-awards .g-head th { border-left-color: var(--lane-awards); }
  .lane-teaching .g-head th { border-left-color: var(--lane-teaching); }
  .lane-outreach .g-head th { border-left-color: var(--lane-outreach); }
  .g-count { font-weight: 700; white-space: nowrap; }
  .g-count.gap span { color: var(--danger); }
  .plus { font-size: 0.75rem; line-height: 1; padding: 0.1rem 0.4rem; margin-left: 0.35rem; opacity: 0.35; }
  .g-count.gap .plus, .g-head:hover .plus, .plus:focus-visible { opacity: 1; }

  .act { background: none; border: none; padding: 0; font: inherit; color: var(--ink); text-align: left; cursor: pointer; }
  .act:hover { text-decoration: underline; }
  .act-note { display: block; font-size: 0.72rem; color: var(--ink-soft); }
  tr.off .act, tr.off .c-when, tr.off .c-stage { opacity: 0.5; }
  tr.empty td { font-size: 0.8rem; font-style: italic; }

  .tick {
    width: 1.15rem; height: 1.15rem; padding: 0; border: 1px solid transparent; border-radius: 0; background: none;
    cursor: pointer; vertical-align: middle;
  }
  .tick:hover:not(:disabled) { border-color: var(--amb); }
  .tick.on { background: var(--amb); border-color: var(--amb); }
  .tick.via { border: 2px solid var(--amb); background: none; }
  .tick:not(.on):not(.via)::after { content: "·"; color: var(--rule); font-size: 1rem; line-height: 1; }
  .tick:disabled { cursor: default; }
  .tick:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .hint { font-size: 0.76rem; margin: 0.5rem 0 0; }
</style>
