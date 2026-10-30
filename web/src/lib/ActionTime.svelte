<script lang="ts">
  // Your time on one of your actions, on its card in the Logbook: what it has taken
  // so far, the hours you project for it, and logging time, by start and end, or
  // just hours. Nobody else sees these; your supervisor gets each project's share only.
  import { fmtHours } from "./data";
  import { fmtDay, today } from "./dates";
  import { saveActionPlan, addTimeLog, deleteTimeLog, hoursBetween } from "./actionTime";
  import type { ActionTimes } from "./actionTime";
  import type { Action } from "./actions";

  type Props = { action: Action; times: ActionTimes; onchanged: () => Promise<void> };
  let { action, times, onchanged }: Props = $props();

  const logs = $derived(times.logs.filter((x) => x.action_id === action.id));
  const spent = $derived(logs.reduce((n, x) => n + x.hours, 0));
  const planned = $derived(times.plans.get(action.id) ?? null);

  let open = $state(false);
  let error = $state("");
  let draft = $state({ day: today(), mode: "times" as "times" | "hours", start: "09:00", end: "10:00", hours: null as number | null });
  const act = async (f: () => Promise<unknown>) => {
    try { error = ""; await f(); await onchanged(); return true; } catch (e) { error = (e as Error).message; return false; }
  };
  const draftHours = $derived(draft.mode === "times" ? hoursBetween(draft.start, draft.end) : draft.hours ?? 0);

  function savePlan(ev: Event) {
    const v = (ev.target as HTMLInputElement).value;
    return act(() => saveActionPlan(action.id, v === "" ? null : Number(v)));
  }
  async function log(ev: SubmitEvent) {
    ev.preventDefault();
    if (draftHours <= 0) return;
    const ok = await act(() => addTimeLog({
      action_id: action.id, worked_on: draft.day, hours: draftHours,
      start_time: draft.mode === "times" ? draft.start : null, end_time: draft.mode === "times" ? draft.end : null,
    }));
    if (ok) draft.hours = null;
  }
</script>

<div class="at">
  <button class="sum" aria-expanded={open} onclick={() => (open = !open)} title="Log time">
    ⏱ {spent ? `${fmtHours(spent)} logged` : "log time"}
  </button>
  <label class="planned"><input type="number" min="0" step="0.25" value={planned ?? ""} onchange={savePlan} aria-label={`Projected hours for ${action.title}`} /> h projected</label>
</div>
{#if error}<p class="error">{error}</p>{/if}

{#if open}
  <div class="panel">
    <form class="log" onsubmit={log}>
      <input type="date" bind:value={draft.day} required aria-label="Date" />
      <span class="modes">
        <button type="button" class:on={draft.mode === "times"} onclick={() => (draft.mode = "times")}>start & end</button>
        <button type="button" class:on={draft.mode === "hours"} onclick={() => (draft.mode = "hours")}>hours</button>
      </span>
      {#if draft.mode === "times"}
        <input type="time" bind:value={draft.start} step="300" aria-label="Start" />–<input type="time" bind:value={draft.end} step="300" aria-label="End" />
      {:else}
        <input type="number" min="0.25" step="0.25" bind:value={draft.hours} aria-label="Hours" /> h
      {/if}
      <button class="mini primary" type="submit" disabled={draftHours <= 0}>Log{draftHours ? ` ${fmtHours(draftHours)}` : ""}</button>
    </form>
    {#if logs.length}
      <ul>
        {#each logs as x (x.id)}
          <li>
            <span>{fmtDay(x.worked_on)}</span>
            {#if x.start_time && x.end_time}<span class="muted">{x.start_time.slice(0, 5)}–{x.end_time.slice(0, 5)}</span>{/if}
            <span>{fmtHours(x.hours)}</span>
            <button class="x" aria-label="Delete this time" title="Delete" onclick={() => act(() => deleteTimeLog(x.id))}>✕</button>
          </li>
        {/each}
      </ul>
    {/if}
    <p class="muted note">Your hours are yours alone. Your supervisor sees only the share of each week that went to each project.</p>
  </div>
{/if}

<style>
  .at { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline; margin: 0.1rem 0 0 1.5rem; }
  .sum { background: none; border: none; padding: 0; font-size: 0.78rem; color: var(--ink-soft); cursor: pointer; }
  .panel { display: grid; gap: 0.35rem; margin: 0.25rem 0 0.35rem 1.5rem; padding: 0.4rem 0.6rem; border-left: 2px solid var(--rule); font-size: 0.82rem; }
  .planned { font-size: 0.78rem; color: var(--ink-soft); }
  input[type="number"] { width: 4.2rem; font-size: 0.78rem; padding: 0.05rem 0.25rem; }
  .log { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
  .log input { width: auto; font-size: 0.82rem; padding: 0.1rem 0.3rem; }
  .modes { display: inline-flex; }
  .modes button { font-size: 0.75rem; padding: 0.1rem 0.45rem; background: none; }
  .modes button.on { background: var(--panel); font-weight: 600; }
  .mini { font-size: 0.75rem; padding: 0.15rem 0.55rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.1rem; }
  li { display: flex; gap: 0.6rem; align-items: baseline; }
  .x { background: none; border: none; color: var(--ink-soft); font-size: 0.7rem; padding: 0 0.2rem; }
  .note { margin: 0; font-size: 0.75rem; }
</style>
