<script lang="ts">
  import { LANES, NODE_KINDS, LINK_KINDS, saveLink, setLinkKind, deleteLink, inferLinkKind } from "./pathways";
  import type { PwNode, PwLink, LinkKind, NodeKind, Lane } from "./pathways";

  type Props = {
    shown: PwNode[]; // the items to list (respecting "show done and retired")
    all: PwNode[]; // every item, as link targets
    links: PwLink[];
    sub: (n: PwNode) => string;
    onedit: (n: PwNode) => void;
    onadd: (kind: NodeKind, lane: Lane, title: string, start: string | null, end: string | null) => Promise<void>;
    onchanged: () => Promise<void>;
  };
  let { shown, all, links, sub, onedit, onadd, onchanged }: Props = $props();

  const KIND_ORDER = NODE_KINDS.map((k) => k.key) as string[];
  const ICON: Record<string, string> = { goal: "◎", objective: "◆", project: "▭", person: "●", gap: "?", grant: "✎" };
  const kindLabel = (k: string) => NODE_KINDS.find((x) => x.key === k)?.label ?? k;
  const linkLabel = (k: string) => LINK_KINDS.find((x) => x.key === k)?.label ?? k;
  const byId = $derived(new Map(all.map((n) => [n.id, n])));
  const titleOf = (id: string) => byId.get(id)?.title ?? "?";

  const groups = $derived(
    LANES.map((l) => ({
      lane: l,
      items: shown
        .filter((n) => n.lane === l.key)
        .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)
          || (a.start_on ?? "").localeCompare(b.start_on ?? "") || a.title.localeCompare(b.title)),
    })),
  );

  // ---- quick entry ------------------------------------------------------------------
  let q = $state({ kind: "project" as NodeKind, lane: "research" as Lane, title: "", start: "", end: "" });
  let laneTouched = $state(false);
  let adding = $state(false);
  let error = $state("");
  let titleEl = $state<HTMLInputElement | null>(null);
  function onKind() {
    if (!laneTouched) q.lane = (NODE_KINDS.find((k) => k.key === q.kind)?.lane ?? "research") as Lane;
  }
  async function add(ev: SubmitEvent) {
    ev.preventDefault();
    if (!q.title.trim()) return;
    if (q.start && q.end && q.end < q.start) return (error = "It ends before it starts.");
    adding = true;
    error = "";
    try {
      await onadd(q.kind, q.lane, q.title.trim(), q.start || null, q.end || null);
      q.title = "";
      titleEl?.focus(); // ready for the next one
    } catch (e) {
      error = (e as Error).message;
    } finally {
      adding = false;
    }
  }

  // ---- links on each row ----------------------------------------------------------
  let linking = $state<{ from: string; to: string; kind: LinkKind } | null>(null);
  function startLink(n: PwNode) {
    linking = { from: n.id, to: "", kind: n.kind === "grant" ? "funds" : "feeds" };
  }
  function onTarget() {
    if (!linking) return;
    const a = byId.get(linking.from), b = byId.get(linking.to);
    if (a && b) linking.kind = inferLinkKind(a, b);
  }
  async function act(f: () => Promise<void>) {
    try { await f(); await onchanged(); } catch (e) { error = (e as Error).message; }
  }
  async function link() {
    const l = linking;
    if (!l?.to) return;
    await act(() => saveLink(l.from, l.to, l.kind));
    linking = null;
  }
</script>

<form class="quick" onsubmit={add}>
  <select bind:value={q.kind} onchange={onKind} aria-label="Kind">
    {#each NODE_KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
  </select>
  <input class="q-title" bind:this={titleEl} bind:value={q.title} placeholder={`New ${kindLabel(q.kind).toLowerCase()}…`} aria-label="Title" />
  <select bind:value={q.lane} onchange={() => (laneTouched = true)} aria-label="Lane">
    {#each LANES as l (l.key)}<option value={l.key}>{l.label}</option>{/each}
  </select>
  <label class="q-date">{q.kind === "grant" ? "writing from" : "from"} <input type="date" bind:value={q.start} /></label>
  <label class="q-date">{q.kind === "grant" ? "deadline" : q.kind === "goal" ? "by" : "to"} <input type="date" bind:value={q.end} min={q.start || undefined} /></label>
  <button class="primary" type="submit" disabled={adding || !q.title.trim()}>{adding ? "Adding…" : "Add"}</button>
</form>
<p class="muted q-hint">
  Type a title and press Enter; it stays ready for the next one. Dates are optional —
  {q.kind === "goal" ? "a goal without them sits in the goals column" : "without them it starts this month"}.
  Click an item to edit its details.
</p>
{#if error}<p class="error">{error}</p>{/if}

{#each groups as g (g.lane.key)}
  <section class="grp lane-{g.lane.key}">
    <h2>{g.lane.label} <span class="muted">{g.items.length}</span></h2>
    {#each g.items as n (n.id)}
      {@const out = links.filter((l) => l.from_id === n.id)}
      {@const inc = links.filter((l) => l.to_id === n.id)}
      <div class="row" class:inactive={n.status !== "active"}>
        <span class="icon kind-{n.kind}" title={kindLabel(n.kind)}>{ICON[n.kind] ?? "·"}</span>
        <div class="main">
          <button class="name" onclick={() => onedit(n)}>{n.title}</button>
          <span class="sub muted">{n.status !== "active" ? `${n.status} · ` : ""}{sub(n)}</span>
          <div class="chips">
            {#each out as l (l.id)}
              <span class="chip out lk-{l.kind}">
                <select value={l.kind} aria-label="Link kind" onchange={(ev) => act(() => setLinkKind(l.id, (ev.target as HTMLSelectElement).value as LinkKind))}>
                  {#each LINK_KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
                </select>
                <span class="to">{titleOf(l.to_id)}</span>
                <button class="x" aria-label="Remove link" onclick={() => act(() => deleteLink(l.id))}>✕</button>
              </span>
            {/each}
            {#each inc as l (l.id)}
              <span class="chip in lk-{l.kind}" title={`${titleOf(l.from_id)} ${linkLabel(l.kind)} this`}>
                ← {titleOf(l.from_id)} <span class="muted">{linkLabel(l.kind)} this</span>
              </span>
            {/each}
            {#if linking?.from === n.id}
              <span class="adder">
                <select bind:value={linking.kind} aria-label="Link kind">
                  {#each LINK_KINDS as k (k.key)}<option value={k.key}>{k.label}</option>{/each}
                </select>
                <select bind:value={linking.to} onchange={onTarget} aria-label="Link to">
                  <option value="">choose an item…</option>
                  {#each LANES as lane (lane.key)}
                    <optgroup label={lane.label}>
                      {#each all.filter((x) => x.lane === lane.key && x.id !== n.id) as x (x.id)}<option value={x.id}>{x.title}</option>{/each}
                    </optgroup>
                  {/each}
                </select>
                <button class="mini primary" disabled={!linking.to} onclick={link}>Link</button>
                <button class="mini" onclick={() => (linking = null)}>Cancel</button>
              </span>
            {:else}
              <button class="mini add-link" onclick={() => startLink(n)}>+ link</button>
            {/if}
          </div>
        </div>
      </div>
    {:else}
      <p class="muted empty">Nothing here yet.</p>
    {/each}
  </section>
{/each}

<style>
  .quick {
    display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.8rem 0 0.2rem; font-family: var(--font-ui);
    padding: 0.55rem 0.6rem; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--panel);
  }
  .quick select, .quick input, .quick button { font-size: 0.85rem; width: auto; padding: 0.35rem 0.5rem; }
  .quick .q-title { flex: 1 1 16rem; min-width: 12rem; }
  .q-date { display: flex; gap: 0.3rem; align-items: center; font-size: 0.78rem; color: var(--ink-soft); }
  .q-hint { font-size: 0.78rem; margin: 0.2rem 0 0.8rem; font-family: var(--font-ui); }

  .grp { margin: 0 0 1rem; font-family: var(--font-ui); border-left: 4px solid var(--lane-research); padding-left: 0.7rem; }
  .grp.lane-teaching { border-left-color: var(--lane-teaching); }
  .grp.lane-outreach { border-left-color: var(--lane-outreach); }
  .grp.lane-supervision { border-left-color: var(--lane-supervision); }
  .grp.lane-grants { border-left-color: var(--lane-grants); }
  .grp h2 { font-size: 1rem; margin: 0 0 0.3rem; }
  .grp h2 .muted { font-size: 0.8rem; font-weight: 400; }
  .empty { font-size: 0.82rem; margin: 0.2rem 0 0.4rem; }

  .row { display: flex; gap: 0.55rem; padding: 0.4rem 0; border-top: 1px solid var(--rule); }
  .row.inactive { opacity: 0.55; }
  .icon { width: 1.2rem; text-align: center; color: var(--ink-soft); font-size: 0.9rem; line-height: 1.5; }
  .icon.kind-goal { color: var(--accent); }
  .icon.kind-grant { color: var(--lane-grants); }
  .main { display: grid; gap: 0.15rem; min-width: 0; flex: 1; }
  .name { background: none; border: none; padding: 0; text-align: left; font-size: 0.92rem; font-weight: 600; color: var(--ink); cursor: pointer; }
  .name:hover { text-decoration: underline; }
  .sub { font-size: 0.75rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .chip {
    display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.75rem; padding: 0.05rem 0.35rem;
    border: 1px solid var(--rule); border-left: 3px solid var(--lk-feeds); border-radius: 4px; background: var(--paper);
  }
  .chip select { width: auto; font-size: 0.72rem; padding: 0 0.1rem; border: none; background: transparent; color: var(--ink-soft); }
  .chip.in { border-style: dashed; border-left-style: solid; color: var(--ink-soft); }
  .chip.lk-advances { border-left-color: var(--lk-advances); }
  .chip.lk-works_on { border-left-color: var(--lk-works_on); }
  .chip.lk-learns { border-left-color: var(--lk-learns); }
  .chip.lk-funds { border-left-color: var(--lk-funds); }
  .to { font-weight: 500; max-width: 22rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .x { background: none; border: none; padding: 0 0.1rem; color: var(--ink-soft); font-size: 0.7rem; cursor: pointer; }
  .x:hover { color: var(--danger); }
  .mini { font-size: 0.72rem; padding: 0.05rem 0.45rem; }
  .add-link { color: var(--accent); }
  .adder { display: inline-flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .adder select { width: auto; max-width: 22rem; font-size: 0.75rem; padding: 0.15rem 0.3rem; }
</style>
