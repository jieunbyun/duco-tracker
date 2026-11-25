<script module lang="ts">
  // kept while the app is open, so an undo (which reloads the tab) leaves you where you were
  const last = { selected: null as string | null, line: null as string | null };
</script>

<script lang="ts">
  // Budget: your grant and project budgets — the lines (what the money is for, its plan and
  // account code) and the expenses, from which what is used and what remains are added up.
  import { loadBudgets, saveBudget, saveLine, saveExpense, remove, money, parseBudgets, importBudget } from "../lib/budget";
  import type { Budget, Line, Expense, ParsedBudget } from "../lib/budget";
  import { readXlsx } from "../lib/xlsx";
  import { loadProjects } from "../lib/data";
  import type { Project } from "../lib/data";
  import { undoable } from "../lib/undo.svelte";
  import { fmtDay, today } from "../lib/dates";
  import { arrivedAt } from "../lib/dayBack.svelte";
  import { tick } from "svelte";

  let budgets = $state<Budget[]>([]);
  let lines = $state<Line[]>([]);
  let expenses = $state<Expense[]>([]);
  let projects = $state<Project[]>([]);
  let missing = $state(false);
  let loading = $state(true);
  let error = $state("");
  let selected = $state<string | null>(last.selected);
  let lineFilter = $state<string | null>(last.line); // show only this line's expenses
  let opened = $state(false); // on a phone: the budget is showing instead of the list

  $effect(() => {
    Object.assign(last, { selected, line: lineFilter });
  });

  async function load() {
    try {
      const [all, p] = await Promise.all([loadBudgets(), loadProjects().catch(() => [] as Project[])]);
      missing = all === null;
      budgets = all?.budgets ?? [];
      lines = all?.lines ?? [];
      expenses = all?.expenses ?? [];
      projects = p;
      if (!selected || !budgets.some((b) => b.id === selected)) selected = budgets[0]?.id ?? null;
      arrive();
      error = "";
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  load();

  // from the Day tab (#/budget?e=<expense>): its budget, the expense open to change
  const arrived = arrivedAt("budget");
  async function arrive() {
    const id = arrived.get("e");
    arrived.delete("e");
    const e = expenses.find((x) => x.id === id);
    if (!e) return;
    selected = e.budget_id;
    lineFilter = null;
    opened = true;
    lDraft = null;
    editExpense(e);
    await tick();
    document.querySelector(".expenses tr.editing")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  async function act(label: string, run: () => Promise<unknown>): Promise<boolean> {
    try {
      await undoable(label, run);
      await load();
      return true;
    } catch (e) {
      error = `Not saved: ${(e as Error).message}`;
      return false;
    }
  }

  // ---- figures -------------------------------------------------------------------------
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  const current = $derived(budgets.find((b) => b.id === selected) ?? null);
  const cur = $derived(current?.currency ?? "£");
  const m = (n: number | null | undefined) => money(n, cur);
  const linesOf = (id: string) => lines.filter((l) => l.budget_id === id);
  const spentOf = (id: string) => expenses.filter((e) => e.budget_id === id);
  const usedOn = (lineId: string) => sum(expenses.filter((e) => e.line_id === lineId).map((e) => e.amount));
  const usedIn = (id: string) => sum(spentOf(id).map((e) => e.amount));
  const lastOn = (lineId: string) => expenses.find((e) => e.line_id === lineId && e.spent_on)?.spent_on ?? null;
  const figures = $derived.by(() => {
    if (!current) return null;
    const used = usedIn(current.id);
    const planned = sum(linesOf(current.id).map((l) => l.plan ?? 0));
    const total = current.total ?? planned;
    return { total, used, remaining: total - used, planned, unallotted: current.total === null ? null : current.total - planned };
  });
  const pct = (part: number, whole: number) => (whole ? Math.round((100 * part) / whole) : null);

  // ---- a budget ------------------------------------------------------------------------
  type BudgetDraft = { id: string | null; name: string; total: string; currency: string; starts_on: string; ends_on: string; project_id: string | null; notes: string };
  let bDraft = $state<BudgetDraft | null>(null);
  function editBudget(b: Budget | null) {
    bDraft = {
      id: b?.id ?? null, name: b?.name ?? "", total: b?.total === null || b?.total === undefined ? "" : String(b.total), currency: b?.currency ?? "£",
      starts_on: b?.starts_on ?? "", ends_on: b?.ends_on ?? "", project_id: b?.project_id ?? null, notes: b?.notes ?? "",
    };
  }
  async function keepBudget(ev: SubmitEvent) {
    ev.preventDefault();
    const d = bDraft!;
    if (!d.name.trim()) return;
    let id = d.id;
    const fields = {
      name: d.name.trim(), total: d.total.trim() === "" ? null : +d.total, currency: d.currency.trim() || "£",
      starts_on: d.starts_on || null, ends_on: d.ends_on || null, project_id: d.project_id, notes: d.notes.trim() || null,
    };
    if (await act(d.id ? "Changed budget" : "Added budget", async () => { id = await saveBudget(d.id, fields); })) {
      bDraft = null;
      selected = id;
      opened = true;
    }
  }
  function removeBudget(b: Budget) {
    if (!confirm(`Delete the budget “${b.name}”, its lines and its ${spentOf(b.id).length} expenses? (Undo brings it back.)`)) return;
    act("Deleted budget", () => remove("budget", b.id));
  }

  // ---- a line --------------------------------------------------------------------------
  type LineDraft = { id: string | null; name: string; plan: string; account: string };
  let lDraft = $state<LineDraft | null>(null);
  const editLine = (l: Line | null) =>
    (lDraft = { id: l?.id ?? null, name: l?.name ?? "", plan: l?.plan === null || l?.plan === undefined ? "" : String(l.plan), account: l?.account ?? "" });
  async function keepLine() {
    const d = lDraft!;
    if (!d.name.trim() || !current) return;
    const order = Math.max(0, ...linesOf(current.id).map((l) => l.sort_order)) + 10;
    const fields = { budget_id: current.id, name: d.name.trim(), plan: d.plan.trim() === "" ? null : +d.plan, account: d.account.trim() || null, ...(d.id ? {} : { sort_order: order }) };
    if (await act(d.id ? "Changed budget line" : "Added budget line", () => saveLine(d.id, fields))) lDraft = null;
  }
  function removeLine(l: Line) {
    const n = expenses.filter((e) => e.line_id === l.id).length;
    if (!confirm(`Delete the line “${l.name}”?${n ? ` Its ${n} expenses stay, without a line.` : ""}`)) return;
    act("Deleted budget line", () => remove("budget_line", l.id));
  }

  // ---- an expense ------------------------------------------------------------------------
  type ExpenseDraft = { id: string | null; spent_on: string; line_id: string | null; item: string; detail: string; amount: string };
  const blankExpense = (): ExpenseDraft => ({ id: null, spent_on: today(), line_id: lineFilter, item: "", detail: "", amount: "" });
  let eDraft = $state<ExpenseDraft>(blankExpense());
  let editingExpense = $state<string | null>(null);
  function editExpense(e: Expense) {
    editingExpense = e.id;
    eDraft = { id: e.id, spent_on: e.spent_on ?? "", line_id: e.line_id, item: e.item ?? "", detail: e.detail ?? "", amount: String(e.amount) };
  }
  async function keepExpense(ev?: SubmitEvent) {
    ev?.preventDefault();
    const d = eDraft;
    if (!current || d.amount.trim() === "" || Number.isNaN(+d.amount)) return;
    const fields = { budget_id: current.id, line_id: d.line_id, spent_on: d.spent_on || null, amount: +d.amount, item: d.item.trim() || null, detail: d.detail.trim() || null };
    if (await act(d.id ? "Changed expense" : "Added expense", () => saveExpense(d.id, fields))) {
      editingExpense = null;
      eDraft = { ...blankExpense(), line_id: d.id ? lineFilter : d.line_id, spent_on: d.id ? today() : d.spent_on };
    }
  }
  function removeExpense(e: Expense) {
    act("Deleted expense", () => remove("budget_expense", e.id));
  }
  const shownExpenses = $derived(current ? spentOf(current.id).filter((e) => lineFilter === null || e.line_id === lineFilter) : []);
  const lineName = (id: string | null) => lines.find((l) => l.id === id)?.name ?? "—";

  // ---- import ----------------------------------------------------------------------------
  let incoming = $state<ParsedBudget[] | null>(null);
  let importing = $state(false);
  async function readFile(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    try {
      const found = parseBudgets(await readXlsx(await file.arrayBuffer()));
      if (!found.length) error = `No budget found in ${file.name}: it needs a header row with “Plan” and “Used”.`;
      else incoming = found;
    } catch (e) {
      error = `Could not read ${file.name}: ${(e as Error).message}`;
    }
  }
  async function doImport() {
    const list = incoming!;
    importing = true;
    let first: string | null = null;
    if (await act(`Imported ${list.length} ${list.length === 1 ? "budget" : "budgets"}`, async () => {
      for (const p of list) first ??= await importBudget(p);
    })) {
      incoming = null;
      selected = first;
      lineFilter = null;
    }
    importing = false;
  }
</script>

<section class="budget" class:opened>
  <div class="head">
    <div>
      <span class="eyebrow">Budget</span>
      <h1>Budgets</h1>
    </div>
    {#if !missing}
      <span class="head-acts">
        <label class="file-btn">Import .xlsx…<input type="file" accept=".xlsx" onchange={readFile} /></label>
        <button class="primary" onclick={() => editBudget(null)}>+ New budget</button>
      </span>
    {/if}
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if missing}
    <p class="muted">Budget needs its tables first: run <code>web/db/0061_budget.sql</code> in the Supabase SQL editor, then reload.</p>
  {:else}
    {#if incoming}
      <div class="panel">
        <h2>Import</h2>
        {#each incoming as p, i (i)}
          {@const n = p.lines.reduce((a, l) => a + l.expenses.length, 0) + p.unassigned.length}
          <div class="import-row">
            <label>Budget name <input bind:value={p.name} /></label>
            <span class="muted small">Sheet “{p.sheet}” · total {money(p.total)} · {p.lines.length} lines · {n} expenses
              ({money(p.lines.reduce((a, l) => a + l.expenses.reduce((x, e) => x + e.amount, 0), 0) + p.unassigned.reduce((x, e) => x + e.amount, 0))} used)</span>
            {#each p.notes as note (note)}<span class="warn small">⚠ {note}</span>{/each}
            {#if p.unassigned.length}<span class="muted small">{p.unassigned.length} expenses match no line; they come in without one.</span>{/if}
          </div>
        {/each}
        <div class="buttons">
          <button class="primary" disabled={importing} onclick={doImport}>{importing ? "Importing…" : "Import"}</button>
          <button onclick={() => (incoming = null)}>Cancel</button>
        </div>
      </div>
    {/if}

    {#if bDraft}
      <form class="panel budget-form" onsubmit={keepBudget}>
        <div class="grid">
          <label class="wide">Name <input bind:value={bDraft.name} required placeholder="e.g. DAFNI fellowship" /></label>
          <label>Total <input type="number" step="0.01" min="0" bind:value={bDraft.total} placeholder="10000" /></label>
          <label>Currency <input bind:value={bDraft.currency} maxlength="4" /></label>
          <label>Starts <input type="date" bind:value={bDraft.starts_on} /></label>
          <label>Ends <input type="date" bind:value={bDraft.ends_on} /></label>
          <label class="wide">Project <span class="muted small">(optional)</span>
            <select bind:value={bDraft.project_id}>
              <option value={null}>None</option>
              {#each projects as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
            </select>
          </label>
          <label class="full">Notes <textarea rows="2" bind:value={bDraft.notes}></textarea></label>
        </div>
        <div class="buttons">
          <button class="primary" type="submit">{bDraft.id ? "Save" : "Add budget"}</button>
          <button type="button" onclick={() => (bDraft = null)}>Cancel</button>
        </div>
      </form>
    {/if}

    <div class="panes">
      <aside class="list">
        <ul>
          {#each budgets as b (b.id)}
            {@const used = usedIn(b.id)}
            {@const total = b.total ?? sum(linesOf(b.id).map((l) => l.plan ?? 0))}
            <li>
              <button class:sel={b.id === selected} onclick={() => { selected = b.id; lineFilter = null; opened = true; lDraft = null; editingExpense = null; }}>
                <span class="name">{b.name}</span>
                <span class="muted small">{money(used, b.currency)} of {money(total, b.currency)}</span>
                <span class="meter" aria-hidden="true"><span style:width={`${Math.min(100, pct(used, total) ?? 0)}%`} class:over={used > total}></span></span>
              </button>
            </li>
          {/each}
        </ul>
        {#if !budgets.length}<p class="muted small">No budgets yet. Import your spreadsheet, or add one.</p>{/if}
      </aside>

      <div class="detail">
        <button class="back" onclick={() => (opened = false)}>← All budgets</button>
        {#if current && figures}
          <div class="b-head">
            <div>
              <h2>{current.name}</h2>
              <span class="muted small">
                {[current.starts_on && current.ends_on ? `${fmtDay(current.starts_on)} – ${fmtDay(current.ends_on)}` : current.ends_on ? `until ${fmtDay(current.ends_on)}` : "",
                  current.project_id ? projects.find((p) => p.id === current.project_id)?.name ?? "" : ""].filter(Boolean).join(" · ")}
              </span>
            </div>
            <span class="tools">
              <button onclick={() => editBudget(current)}>Edit</button>
              <button class="del" onclick={() => removeBudget(current)}>Delete</button>
            </span>
          </div>
          {#if current.notes}<p class="notes">{current.notes}</p>{/if}

          <div class="tiles">
            <div class="tile"><span class="t-label">Total</span><span class="t-value">{m(figures.total)}</span>
              <span class="t-sub">{figures.unallotted === null ? "the lines' plans added up" : figures.unallotted >= 0 ? `${m(figures.unallotted)} not yet in a line` : `lines plan ${m(-figures.unallotted)} more than the total`}</span></div>
            <div class="tile"><span class="t-label">Used</span><span class="t-value">{m(figures.used)}</span>
              <span class="t-sub">{pct(figures.used, figures.total) ?? "–"}% of the total</span></div>
            <div class="tile" class:over={figures.remaining < 0}><span class="t-label">Remaining</span><span class="t-value">{m(figures.remaining)}</span>
              <span class="t-sub">{figures.remaining < 0 ? "⚠ over the total" : `${pct(figures.remaining, figures.total) ?? "–"}% left`}</span></div>
          </div>

          <h3>Lines <span class="muted small">click a line to see only its expenses</span></h3>
          <table class="lines">
            <thead><tr><th>Line</th><th>Account</th><th class="num">Plan</th><th class="num">Used</th><th class="num">Remaining</th><th class="bar-col"></th><th></th></tr></thead>
            <tbody>
              {#each linesOf(current.id) as l (l.id)}
                {@const used = usedOn(l.id)}
                {@const left = l.plan === null ? null : l.plan - used}
                {#if lDraft?.id === l.id}
                  {@render lineEditor()}
                {:else}
                  <tr class:on={lineFilter === l.id} class:over={left !== null && left < 0}>
                    <td><button class="link" onclick={() => (lineFilter = lineFilter === l.id ? null : l.id)}>{l.name}</button>
                      {#if lastOn(l.id)}<span class="muted small"> · last {fmtDay(lastOn(l.id)!)}</span>{/if}</td>
                    <td class="small">{l.account ?? ""}</td>
                    <td class="num">{m(l.plan)}</td>
                    <td class="num">{m(used)}</td>
                    <td class="num">{left === null ? "–" : m(left)}{left !== null && left < 0 ? " ⚠" : ""}<span class="muted small">{l.plan ? ` · ${pct(Math.max(0, left!), l.plan)}%` : ""}</span></td>
                    <td class="bar-col"><span class="meter"><span style:width={`${Math.min(100, l.plan ? (100 * used) / l.plan : 0)}%`} class:over={left !== null && left < 0}></span></span></td>
                    <td class="row-acts"><button class="mini" onclick={() => editLine(l)}>Edit</button></td>
                  </tr>
                {/if}
              {/each}
              {#if lDraft && !lDraft.id}{@render lineEditor()}{/if}
            </tbody>
            <tfoot>
              <tr><td colspan="2"><button class="link small" onclick={() => editLine(null)}>+ Line</button></td>
                <td class="num">{m(figures.planned)}</td><td class="num">{m(sum(linesOf(current.id).map((l) => usedOn(l.id))))}</td><td colspan="3"></td></tr>
            </tfoot>
          </table>

          <h3>Expenses
            {#if lineFilter}<span class="filter">on {lineName(lineFilter)} <button class="link small" onclick={() => (lineFilter = null)}>show all</button></span>{/if}
          </h3>
          {#if !editingExpense}
            <form class="add-expense" onsubmit={keepExpense}>
              <input type="date" bind:value={eDraft.spent_on} aria-label="Date" />
              <select bind:value={eDraft.line_id} aria-label="Line">
                <option value={null}>No line</option>
                {#each linesOf(current.id) as l (l.id)}<option value={l.id}>{l.name}</option>{/each}
              </select>
              <input bind:value={eDraft.item} placeholder="What (e.g. Kick-off meeting)" aria-label="What" />
              <input bind:value={eDraft.detail} placeholder="Detail (e.g. Train)" aria-label="Detail" />
              <input type="number" step="0.01" bind:value={eDraft.amount} placeholder="Amount" aria-label="Amount" required />
              <button class="primary" type="submit">Add</button>
            </form>
          {/if}
          <table class="expenses">
            <thead><tr><th>Date</th><th>Line</th><th>What</th><th>Detail</th><th class="num">Amount</th><th></th></tr></thead>
            <tbody>
              {#each shownExpenses as e (e.id)}
                {#if editingExpense === e.id}
                  <tr class="editing"><td colspan="6">
                    <form class="add-expense" onsubmit={keepExpense}>
                      <input type="date" bind:value={eDraft.spent_on} aria-label="Date" />
                      <select bind:value={eDraft.line_id} aria-label="Line">
                        <option value={null}>No line</option>
                        {#each linesOf(current.id) as l (l.id)}<option value={l.id}>{l.name}</option>{/each}
                      </select>
                      <input bind:value={eDraft.item} placeholder="What" aria-label="What" />
                      <input bind:value={eDraft.detail} placeholder="Detail" aria-label="Detail" />
                      <input type="number" step="0.01" bind:value={eDraft.amount} aria-label="Amount" required />
                      <button class="primary" type="submit">Save</button>
                      <button type="button" onclick={() => { editingExpense = null; eDraft = blankExpense(); }}>Cancel</button>
                      <button type="button" class="del" onclick={() => removeExpense(e)}>Delete</button>
                    </form>
                  </td></tr>
                {:else}
                  <tr>
                    <td class="small nowrap">{e.spent_on ? fmtDay(e.spent_on) : "—"}</td>
                    <td class="small">{lineName(e.line_id)}</td>
                    <td>{e.item ?? ""}</td>
                    <td class="small">{e.detail ?? ""}</td>
                    <td class="num">{m(e.amount)}</td>
                    <td class="row-acts"><button class="mini" onclick={() => editExpense(e)}>Edit</button></td>
                  </tr>
                {/if}
              {/each}
            </tbody>
            {#if shownExpenses.length}
              <tfoot><tr><td colspan="4" class="muted small">{shownExpenses.length} {shownExpenses.length === 1 ? "expense" : "expenses"}</td>
                <td class="num">{m(sum(shownExpenses.map((e) => e.amount)))}</td><td></td></tr></tfoot>
            {/if}
          </table>
          {#if !shownExpenses.length}<p class="muted small">No expenses{lineFilter ? " on this line" : ""} yet.</p>{/if}
        {:else if budgets.length}
          <p class="muted">Pick a budget on the left.</p>
        {/if}
      </div>
    </div>
  {/if}
</section>

{#snippet lineEditor()}
  {#if lDraft}
    <tr class="editing">
      <td><input bind:value={lDraft.name} placeholder="Line, e.g. Conference" aria-label="Line name"
                 onkeydown={(ev) => { if (ev.key === "Enter") { ev.preventDefault(); keepLine(); } }} /></td>
      <td><input bind:value={lDraft.account} placeholder="Account code" aria-label="Account code" /></td>
      <td><input type="number" step="0.01" min="0" bind:value={lDraft.plan} placeholder="Plan" aria-label="Plan" /></td>
      <td colspan="4" class="row-acts">
        <button class="mini primary" onclick={keepLine}>Save</button>
        <button class="mini" onclick={() => (lDraft = null)}>Cancel</button>
        {#if lDraft.id}{@const l = lines.find((x) => x.id === lDraft!.id)}{#if l}<button class="mini del" onclick={() => removeLine(l)}>Delete</button>{/if}{/if}
      </td>
    </tr>
  {/if}
{/snippet}

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .head h1 { margin: 0; }
  .head-acts { display: flex; gap: 0.5rem; align-items: center; }
  .file-btn { border: 1px solid var(--rule); background: var(--panel); border-radius: var(--radius); padding: 0.45rem 0.9rem; cursor: pointer; font-family: var(--font-ui); font-size: 0.9rem; }
  .file-btn input { display: none; }
  .small { font-size: 0.8rem; }
  .nowrap { white-space: nowrap; }
  .link { background: none; border: none; padding: 0; color: var(--accent); cursor: pointer; font: inherit; text-align: left; }
  .warn { color: var(--danger); }
  .panel { background: var(--panel); border-radius: var(--radius); padding: 0.9rem; display: grid; gap: 0.6rem; margin-bottom: 1rem; }
  .panel h2 { margin: 0; font-size: 1.1rem; }
  .panel label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.6rem; }
  .grid .wide { grid-column: span 2; }
  .grid .full { grid-column: 1 / -1; }
  .import-row { display: grid; gap: 0.25rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--rule); }
  .buttons { display: flex; gap: 0.5rem; }

  .panes { display: grid; grid-template-columns: minmax(0, 15rem) minmax(0, 1fr); gap: 1.5rem; align-items: start; }
  .list { position: sticky; top: 4rem; font-family: var(--font-ui); }
  .list ul { list-style: none; margin: 0; padding: 0; }
  .list li button { width: 100%; display: grid; gap: 0.15rem; text-align: left; background: none; border: none; border-radius: var(--radius); padding: 0.5rem 0.55rem; }
  .list li button:hover { background: var(--panel); }
  .list li button.sel { background: var(--panel); box-shadow: inset 3px 0 0 var(--accent); }
  .name { font-weight: 600; font-size: 0.9rem; }
  .meter { display: block; height: 0.4rem; background: var(--rule); border-radius: 999px; overflow: hidden; }
  .meter > span { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
  .meter > span.over { background: var(--danger); }
  .back { display: none; margin-bottom: 0.8rem; }

  .b-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.6rem; align-items: flex-start; }
  .b-head h2 { margin: 0; }
  .tools { display: flex; gap: 0.3rem; }
  .tools button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }
  .del { color: var(--danger); }
  .notes { margin: 0.5rem 0 0; white-space: pre-wrap; color: var(--ink-soft); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: 0.6rem; margin: 1rem 0; font-family: var(--font-ui); }
  .tile { background: var(--panel); border-radius: var(--radius); padding: 0.6rem 0.8rem; display: grid; gap: 0.1rem; }
  .tile.over .t-value { color: var(--danger); }
  .t-label { font-size: 0.78rem; color: var(--ink-soft); }
  .t-value { font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .t-sub { font-size: 0.75rem; color: var(--ink-soft); }
  h3 { font-size: 1rem; margin: 1.4rem 0 0.5rem; display: flex; flex-wrap: wrap; gap: 0.3rem 0.7rem; align-items: baseline; }
  h3 .small { font-weight: 400; }
  .filter { font-family: var(--font-ui); font-size: 0.82rem; font-weight: 400; color: var(--ink-soft); }

  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th { text-align: left; font-family: var(--font-ui); font-size: 0.75rem; font-weight: 600; color: var(--ink-soft); padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--rule); }
  td { padding: 0.35rem 0.4rem; border-bottom: 1px solid var(--rule); vertical-align: middle; }
  tfoot td { border-bottom: none; font-weight: 600; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .lines tr.on td { background: var(--panel); }
  .lines tr.over .num:nth-child(5) { color: var(--danger); }
  .bar-col { width: 18%; min-width: 4rem; }
  .row-acts { text-align: right; white-space: nowrap; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.5rem; }
  tr.editing td { background: var(--panel); }
  tr.editing input { font-size: 0.85rem; padding: 0.25rem 0.4rem; }
  .add-expense { display: grid; grid-template-columns: 9rem minmax(0, 1fr) minmax(0, 1.3fr) minmax(0, 1fr) 7rem auto auto auto; gap: 0.35rem; margin-bottom: 0.6rem; align-items: center; }
  .add-expense input, .add-expense select { font-size: 0.85rem; padding: 0.3rem 0.4rem; }
  .add-expense button { font-size: 0.82rem; padding: 0.3rem 0.7rem; }

  @media (max-width: 48rem) {
    .panes { grid-template-columns: 1fr; }
    .list { position: static; }
    .budget.opened .list, .budget:not(.opened) .detail { display: none; }
    .back { display: inline-block; }
    .grid { grid-template-columns: 1fr 1fr; }
    .add-expense { grid-template-columns: 1fr 1fr; }
    .bar-col, th:nth-child(2), .lines td:nth-child(2) { display: none; }
    .expenses th:nth-child(4), .expenses td:nth-child(4) { display: none; }
  }
</style>
