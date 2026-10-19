<script lang="ts">
  import { untrack } from "svelte";
  import { saveSettings, saveTargets, targetOn } from "./data";
  import type { Taxonomy } from "./data";
  import { today, weekStart } from "./dates";

  type Props = { tax: Taxonomy; onsaved: () => void; oncancel: () => void };
  let { tax, onsaved, oncancel }: Props = $props();

  const t0 = untrack(() => tax);
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  let week_starts_on = $state(t0.weekStartsOn);
  let weeks_per_year = $state(t0.weeksPerYear);
  const horizon_months = t0.horizonMonths; // the period is now chosen with Planning's buttons
  let from = $state(weekStart(today()));
  let targets = $state(
    t0.areas.map((a) => {
      const t = targetOn(t0.targets, a.id, today());
      return { area: a, weekly: t?.weekly_hours ?? 0, email: t?.email_weekly_hours ?? 0 };
    }),
  );
  let busy = $state(false);
  let error = $state("");

  const changed = $derived(
    targets.some((r) => {
      const t = targetOn(t0.targets, r.area.id, today());
      return (t?.weekly_hours ?? 0) !== r.weekly || (t?.email_weekly_hours ?? 0) !== r.email;
    }),
  );

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = "";
    try {
      await saveSettings({ week_starts_on, weeks_per_year, horizon_months });
      if (changed) {
        await saveTargets(targets.map((r) => ({
          area_id: r.area.id, effective_from: from, weekly_hours: r.weekly || 0, email_weekly_hours: r.email || 0,
        })));
      }
      onsaved();
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<form class="settings" onsubmit={save}>
  <div class="row">
    <label>Week starts on
      <select bind:value={week_starts_on}>
        {#each DAYS as d, i (d)}<option value={i}>{d}</option>{/each}
      </select>
    </label>
    <label>Working weeks per year <input type="number" min="1" max="52" step="1" bind:value={weeks_per_year} /></label>
  </div>

  <table>
    <thead><tr><th>Area</th><th>Time h/wk</th><th>Email h/wk</th></tr></thead>
    <tbody>
      {#each targets as r (r.area.id)}
        <tr>
          <td>{r.area.label}</td>
          <td><input type="number" min="0" step="0.5" bind:value={r.weekly} aria-label={`${r.area.label} hours per week`} /></td>
          <td><input type="number" min="0" step="0.5" bind:value={r.email} aria-label={`${r.area.label} email hours per week`} /></td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if changed}
    <label class="from">New targets apply from <input type="date" bind:value={from} required /></label>
    <p class="muted small">Time before that date keeps the targets it had.</p>
  {/if}

  {#if error}<p class="error">{error}</p>{/if}
  <div class="actions">
    <button class="primary" type="submit" disabled={busy}>Save settings</button>
    <button type="button" onclick={oncancel} disabled={busy}>Cancel</button>
  </div>
</form>

<style>
  .settings { display: grid; gap: 0.9rem; font-family: var(--font-ui); max-width: 40rem; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: 0.75rem 1rem; }
  label { display: grid; gap: 0.25rem; font-size: 0.82rem; color: var(--ink-soft); }
  .from { max-width: 14rem; }
  table { border-collapse: collapse; font-size: 0.9rem; }
  th { text-align: left; color: var(--ink-soft); font-weight: 500; padding: 0.3rem 0.5rem; }
  td { padding: 0.25rem 0.5rem; }
  td input { width: 7rem; }
  .small { font-size: 0.8rem; margin: -0.6rem 0 0; }
  .actions { display: flex; gap: 0.5rem; }
</style>
