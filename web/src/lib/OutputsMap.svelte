<script lang="ts">
  // The group's outputs, schematically: a band for each category, time running
  // left to right by when each was developed, and drawn links between them.
  import { CATEGORIES, linkOutputs, catalogueYaml } from "./assets";
  import type { Output, OutputLink, Category } from "./assets";
  import type { Member } from "./group";
  import { monthStart, addMonths, fraction, fmtMonth } from "./pathways";
  import { today } from "./dates";
  import OutputEditor from "./OutputEditor.svelte";

  type Props = {
    outputs: Output[];
    links: OutputLink[];
    titles: Map<string, string>;
    members: Member[];
    me: string;
    supervisor: boolean;
    publications: { id: string; title: string }[]; // what can be linked as a publication
    readonly?: boolean; // previewing what a member sees
    onchanged: () => Promise<void>;
  };
  let { outputs, links, titles, members, me, supervisor, publications, readonly = false, onchanged }: Props = $props();

  const canEdit = (o: Output) => !readonly && (supervisor || o.user_id === me || o.contributors.includes(me));
  const nameOf = (uid: string) => members.find((m) => m.user_id === uid)?.display_name ?? "—";
  let error = $state("");
  let showRetired = $state(false);
  let who = $state(""); // a contributor to pick out, or "" for everyone
  const shown = $derived(outputs.filter((o) => showRetired || o.status !== "retired"));
  const contributorsOnMap = $derived([...new Set(outputs.flatMap((o) => o.contributors))].sort((a, b) => nameOf(a).localeCompare(nameOf(b))));

  // ---- layout: a band per category, x by date -------------------------------------
  const LABEL_W = 130, CARD_W = 190, CARD_H = 54, ROW_H = 66, PAD = 12, AXIS_H = 28;
  let width = $state(1000);
  const mapW = $derived(Math.max(width, 900));
  const span = $derived.by(() => {
    const dates = shown.map((o) => o.developed_on).filter((d): d is string => !!d).sort();
    const lo = [dates[0], addMonths(monthStart(today()), -12)].filter(Boolean).sort()[0]!;
    const hi = [dates[dates.length - 1], today()].filter(Boolean).sort().reverse()[0]!;
    return { from: monthStart(lo), to: addMonths(monthStart(hi), 2) };
  });
  const xOf = (iso: string | null) =>
    LABEL_W + Math.min(1, Math.max(0, fraction(iso ?? today(), span.from, span.to))) * (mapW - LABEL_W - CARD_W - 16);

  type Box = { o: Output; x: number; y: number };
  const layout = $derived.by(() => {
    const boxes: Box[] = [];
    const bands: { key: Category; label: string; top: number; height: number }[] = [];
    let y = AXIS_H;
    for (const c of CATEGORIES) {
      const inBand = shown.filter((o) => o.category === c.key).sort((a, b) => xOf(a.developed_on) - xOf(b.developed_on));
      const rows: number[] = []; // right edge of the last card in each row
      for (const o of inBand) {
        const x = xOf(o.developed_on);
        let r = rows.findIndex((right) => right + 10 <= x);
        if (r < 0) { r = rows.length; rows.push(0); }
        rows[r] = x + CARD_W;
        boxes.push({ o, x, y: y + PAD + r * ROW_H });
      }
      const height = Math.max(1, rows.length) * ROW_H + 2 * PAD;
      bands.push({ key: c.key, label: c.label, top: y, height });
      y += height;
    }
    return { boxes, bands, height: y + 8 };
  });
  const boxOf = $derived(new Map(layout.boxes.map((b) => [b.o.id, b])));

  const ticks = $derived.by(() => {
    const total = (+span.to.slice(0, 4) - +span.from.slice(0, 4)) * 12 + (+span.to.slice(5, 7) - +span.from.slice(5, 7));
    const step = total <= 18 ? 3 : total <= 48 ? 6 : 12;
    const out: { x: number; label: string }[] = [];
    for (let m = 0; m < total; m += step) {
      const iso = addMonths(span.from, m);
      out.push({ x: xOf(iso), label: fmtMonth(iso) });
    }
    return out;
  });

  // ---- links: forward from right edge to left edge; otherwise edge to edge ------------
  const drawn = $derived(
    links.map((l) => ({ l, a: boxOf.get(l.from_id), b: boxOf.get(l.to_id) }))
      .filter((x): x is { l: OutputLink; a: Box; b: Box } => !!x.a && !!x.b)
      .map(({ l, a, b }) => {
        if (b.x >= a.x + CARD_W + 30) {
          const ax = a.x + CARD_W, ay = a.y + CARD_H / 2, bx = b.x, by = b.y + CARD_H / 2;
          const dx = Math.max(40, (bx - ax) / 2);
          return { l, d: `M ${ax} ${ay} C ${ax + dx} ${ay}, ${bx - dx} ${by}, ${bx} ${by}` };
        }
        if (b.y !== a.y) {
          const down = b.y > a.y;
          const x1 = a.x + CARD_W / 2, x2 = b.x + CARD_W / 2;
          const y1 = down ? a.y + CARD_H : a.y, y2 = down ? b.y : b.y + CARD_H;
          const bend = Math.max(14, Math.abs(y2 - y1) / 2) * (down ? 1 : -1);
          return { l, d: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}` };
        }
        const x1 = a.x + CARD_W - 20, x2 = b.x + 20, yb = a.y + CARD_H;
        return { l, d: `M ${x1} ${yb} C ${x1} ${yb + 16}, ${x2} ${yb + 16}, ${x2} ${yb}` };
      }),
  );

  // ---- drag ○ onto another output to link them -------------------------------------------
  let mapEl = $state<HTMLDivElement | null>(null);
  let drawing = $state<{ id: string; x: number; y: number } | null>(null);
  const local = (ev: PointerEvent) => {
    const r = mapEl!.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  };
  function startLink(ev: PointerEvent, o: Output) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    drawing = { id: o.id, ...local(ev) };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }
  function onMove(ev: PointerEvent) {
    if (drawing && mapEl) drawing = { ...drawing, ...local(ev) };
  }
  async function onUp(ev: PointerEvent) {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    const d = drawing;
    drawing = null;
    if (!d) return;
    const el = (document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null)?.closest<HTMLElement>("[data-out]");
    const to = el?.dataset.out;
    if (!to || to === d.id) return;
    try { await linkOutputs(d.id, to); await onchanged(); } catch (e) { error = (e as Error).message; }
  }

  // ---- editing --------------------------------------------------------------------------
  let panel = $state<{ output: Output | null; category?: Category } | null>(null);
  let dialog = $state<HTMLDialogElement | null>(null);
  $effect(() => {
    if (!dialog) return;
    if (panel && !dialog.open) dialog.showModal();
    if (!panel && dialog.open) dialog.close();
  });
  async function saved() {
    panel = null;
    await onchanged();
  }

  let copied = $state(false);
  async function copyCatalogue() {
    try {
      await navigator.clipboard.writeText(catalogueYaml(outputs.filter((o) => o.status !== "retired"), links, nameOf,
        (id) => publications.find((p) => p.id === id)?.title ?? titles.get(id) ?? id));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch { copied = false; }
  }
</script>

<div class="om">
  <div class="om-bar">
    {#if !readonly}<button class="primary" onclick={() => (panel = { output: null })}>+ Output</button>{/if}
    <label class="small">Contributor
      <select bind:value={who}>
        <option value="">everyone</option>
        {#each contributorsOnMap as uid (uid)}<option value={uid}>{nameOf(uid)}</option>{/each}
      </select>
    </label>
    <label class="toggle"><input type="checkbox" bind:checked={showRetired} /> Show retired</label>
    <span class="spacer"></span>
    <button onclick={copyCatalogue} disabled={!outputs.length} title="Output cards as YAML — the start of a shared catalogue">{copied ? "Copied" : "Copy catalogue (YAML)"}</button>
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  <p class="muted hint">What the group has developed, by when. Drag an output's ○ onto another to connect them; click one to see or change it.</p>

  <div class="scroller" bind:clientWidth={width}>
    <div class="map" bind:this={mapEl} style:width={`${mapW}px`} style:height={`${layout.height}px`}>
      {#each layout.bands as band, i (band.key)}
        <div class="band" class:alt={i % 2 === 1} style:top={`${band.top}px`} style:height={`${band.height}px`}>
          <span class="band-label">{band.label}</span>
          {#if !readonly}<button class="band-add" title={`Add to ${band.label}`} onclick={() => (panel = { output: null, category: band.key })}>+</button>{/if}
        </div>
      {/each}
      {#each ticks as t (t.x)}
        <div class="tick" style:left={`${t.x}px`} style:height={`${layout.height - 6}px`}><span>{t.label}</span></div>
      {/each}
      <div class="now" style:left={`${xOf(today())}px`} style:height={`${layout.height - 6}px`}><span>now</span></div>

      <svg class="links" width={mapW} height={layout.height} aria-hidden="true">
        <defs>
          <marker id="out-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" class="ah" />
          </marker>
        </defs>
        {#each drawn as d (d.l.id)}<path d={d.d} class="lk" marker-end="url(#out-arrow)" />{/each}
        {#if drawing}
          {@const a = boxOf.get(drawing.id)}
          {#if a}<path class="lk drawing" d={`M ${a.x + CARD_W} ${a.y + CARD_H / 2} L ${drawing.x} ${drawing.y}`} />{/if}
        {/if}
      </svg>

      {#each layout.boxes as b (b.o.id)}
        {@const o = b.o}
        <div class="card st-{o.status}" class:faded={!!who && !o.contributors.includes(who)} data-out={o.id}
             role="button" tabindex="0" style:left={`${b.x}px`} style:top={`${b.y}px`} style:width={`${CARD_W}px`} style:height={`${CARD_H}px`}
             title={`${o.name}${o.purpose ? `\n${o.purpose}` : ""}`}
             onclick={() => (panel = { output: o })}
             onkeydown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); panel = { output: o }; } }}>
          <span class="c-name">{o.name}</span>
          <span class="c-sub">
            {o.developed_on ? fmtMonth(o.developed_on) : "undated"}{o.contributors.length ? ` · ${o.contributors.map(nameOf).join(", ")}` : ""}
          </span>
          <span class="c-sub">
            {o.status}{o.publications.length ? ` · ${o.publications.length} ${o.publications.length === 1 ? "publication" : "publications"}` : ""}
            {#if o.location}· <a href={o.location} target="_blank" rel="noopener noreferrer" onclick={(ev) => ev.stopPropagation()}>data ↗</a>{/if}
          </span>
          {#if canEdit(o)}
            <span class="connector" role="presentation" aria-hidden="true" title="Drag onto another output to connect them" onpointerdown={(ev) => startLink(ev, o)}>○</span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
  {#if !shown.length}<p class="muted">No outputs yet. Add the first: an inference algorithm, a dataset, a model, a simulator…</p>{/if}
</div>

<dialog bind:this={dialog} onclose={() => (panel = null)}>
  {#if panel}
    <h2>{panel.output ? panel.output.name : "New output"}</h2>
    {#key panel}
      <OutputEditor output={panel.output} draftCategory={panel.category ?? "other"} {outputs} {links} {members}
                    {publications} {titles} {canEdit} {me} onsaved={saved} oncancel={() => (panel = null)} />
    {/key}
  {/if}
</dialog>

<style>
  .om { font-family: var(--font-ui); }
  .om-bar { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin: 0.6rem 0 0.2rem; }
  .om-bar button { font-size: 0.85rem; padding: 0.35rem 0.7rem; }
  .om-bar select { width: auto; font-size: 0.82rem; padding: 0.2rem 0.4rem; }
  .small { font-size: 0.85rem; display: inline-flex; gap: 0.4rem; align-items: center; }
  .toggle { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.82rem; color: var(--ink-soft); }
  .toggle input { width: auto; }
  .spacer { flex: 1; }
  .hint { font-size: 0.78rem; margin: 0.2rem 0 0.6rem; }
  .scroller { overflow-x: auto; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); }
  .map { position: relative; }
  .band { position: absolute; left: 0; right: 0; border-top: 1px solid var(--rule); }
  .band.alt { background: color-mix(in srgb, var(--panel) 55%, transparent); }
  .band-label { position: absolute; left: 10px; top: 10px; max-width: 105px; font-size: 0.82rem; font-weight: 600; line-height: 1.25; color: var(--accent); }
  .band-add { position: absolute; left: 10px; bottom: 8px; font-size: 0.75rem; padding: 0 0.45rem; }
  .tick { position: absolute; top: 0; border-left: 1px dashed var(--rule); pointer-events: none; }
  .tick span { position: absolute; top: 6px; left: 4px; font-size: 0.7rem; color: var(--ink-soft); white-space: nowrap; }
  .now { position: absolute; top: 0; border-left: 2px solid var(--accent); pointer-events: none; opacity: 0.6; }
  .now span { position: absolute; top: 18px; left: 4px; font-size: 0.7rem; color: var(--accent); }
  .links { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
  .lk { fill: none; stroke: var(--ink-soft); stroke-width: 1.6; }
  .lk.drawing { stroke: var(--accent); stroke-dasharray: 3 3; }
  .ah { fill: var(--ink-soft); }
  .card {
    position: absolute; box-sizing: border-box; display: grid; align-content: center; gap: 1px; padding: 0.2rem 1.1rem 0.2rem 0.6rem;
    background: var(--paper); border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 6px; cursor: pointer;
  }
  .card:hover { box-shadow: 0 0 0 1px var(--ink-soft); z-index: 2; }
  .card.st-idea { border-style: dashed; border-left-style: solid; }
  .card.st-validated { border-width: 2px; border-left-width: 5px; }
  .card.st-retired { opacity: 0.5; }
  .card.faded { opacity: 0.25; }
  .c-name { font-size: 0.8rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .c-sub { font-size: 0.66rem; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .connector {
    position: absolute; right: -21px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px; display: grid; place-items: center;
    font-size: 0.75rem; color: var(--accent); background: var(--paper); border-radius: 50%; cursor: crosshair; opacity: 0; transition: opacity 0.1s;
  }
  .card:hover .connector { opacity: 1; }
  dialog {
    width: min(48rem, calc(100vw - 32px)); max-height: calc(100vh - 32px);
    border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); color: var(--ink); padding: 1.1rem 1.2rem;
  }
  dialog::backdrop { background: rgb(0 0 0 / 0.35); }
</style>
