<script lang="ts">
  // One session's form: the day, the skill, what you did, and your own evaluation.
  import { SKILLS, CRITERIA } from "./practice";
  import type { Session, SessionFields, Skill } from "./practice";
  import { today } from "./dates";

  let { session = null, skill: startSkill = "reading", focus = null, onsave, oncancel }: {
    session?: Session | null;
    skill?: Skill;
    focus?: string | null; // the focus you set last time, shown while you work
    onsave: (fields: Omit<SessionFields, "practice_id">) => Promise<void>;
    oncancel: () => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  const s = session;
  let done_on = $state(s?.done_on ?? today());
  // svelte-ignore state_referenced_locally
  let skill = $state<Skill>(s?.skill ?? startSkill);
  let minutes = $state(s?.minutes == null ? "" : String(s.minutes));
  let did = $state(s?.did ?? "");
  let went_well = $state(s?.went_well ?? "");
  let to_fix = $state(s?.to_fix ?? "");
  let next_focus = $state(s?.next_focus ?? "");
  let ratings = $state<Record<string, number>>({ ...(s?.ratings ?? {}) });
  let saving = $state(false);

  const rate = (c: string, n: number) => {
    const { [c]: _, ...rest } = ratings;
    ratings = ratings[c] === n ? rest : { ...rest, [c]: n }; // the same again clears it
  };
  const text = (v: string) => v.trim() || null;

  async function submit(ev: SubmitEvent) {
    ev.preventDefault();
    saving = true;
    try {
      const mins = minutes.trim() === "" ? null : Math.max(0, Math.round(Number(minutes)));
      await onsave({
        done_on, skill, minutes: Number.isFinite(mins) ? mins : null,
        did: text(did), went_well: text(went_well), to_fix: text(to_fix), next_focus: text(next_focus),
        // only this skill's criteria count
        ratings: Object.fromEntries(Object.entries(ratings).filter(([c]) => CRITERIA[skill].includes(c))),
      });
    } finally {
      saving = false;
    }
  }
</script>

<form class="session-form" onsubmit={submit}>
  {#if focus}<p class="focus"><span class="eyebrow">Your focus from last time</span>{focus}</p>{/if}

  <div class="row">
    <label>Date <input type="date" bind:value={done_on} required /></label>
    <fieldset class="skills">
      <legend>Skill</legend>
      {#each SKILLS as k (k.key)}
        <label class="pick" class:on={skill === k.key}><input type="radio" bind:group={skill} value={k.key} />{k.label}</label>
      {/each}
    </fieldset>
    <label class="mins">Minutes <input type="number" min="0" step="5" inputmode="numeric" bind:value={minutes} /></label>
  </div>

  <label>What you did <textarea rows="2" bind:value={did} placeholder="Read the discussion of …, drafted the methods section, rehearsed the talk…"></textarea></label>

  <fieldset class="ratings">
    <legend>How it went <span class="muted">1–5; click again to clear</span></legend>
    {#each CRITERIA[skill] as c (c)}
      <div class="criterion">
        <span>{c}</span>
        <span class="scale" role="group" aria-label={c}>
          {#each [1, 2, 3, 4, 5] as n (n)}
            <button type="button" class:on={(ratings[c] ?? 0) >= n} aria-pressed={ratings[c] === n}
                    onclick={() => rate(c, n)}>{n}</button>
          {/each}
        </span>
      </div>
    {/each}
  </fieldset>

  <label>Went well <textarea rows="2" bind:value={went_well}></textarea></label>
  <label>To fix <textarea rows="2" bind:value={to_fix}></textarea></label>
  <label>Focus next time <textarea rows="2" bind:value={next_focus}></textarea></label>

  <div class="buttons">
    <button class="primary" type="submit" disabled={saving}>{saving ? "Saving…" : session ? "Save" : "Add session"}</button>
    <button type="button" onclick={oncancel}>Cancel</button>
  </div>
</form>

<style>
  .session-form { display: grid; gap: 0.7rem; padding: 0.9rem; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); }
  label { display: grid; gap: 0.25rem; font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); }
  textarea { color: var(--ink); }
  .row { display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: end; }
  .row > label:first-child { width: 10rem; }
  .mins { width: 6rem; }
  fieldset { border: none; margin: 0; padding: 0; min-width: 0; }
  legend { font-family: var(--font-ui); font-size: 0.85rem; color: var(--ink-soft); padding: 0; margin-bottom: 0.25rem; }
  .skills { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .skills legend { width: 100%; }
  .pick { display: inline-flex; align-items: center; padding: 0.35rem 0.75rem; border: 1px solid var(--rule); border-radius: 999px;
          cursor: pointer; color: var(--ink); background: var(--panel); }
  .pick input { position: absolute; opacity: 0; pointer-events: none; }
  .pick.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .pick:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
  .ratings { display: grid; gap: 0.35rem; }
  .criterion { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.3rem 0.8rem; font-size: 0.92rem; }
  .scale { display: inline-flex; gap: 0.2rem; }
  .scale button { width: 2rem; padding: 0.25rem 0; font-size: 0.82rem; font-variant-numeric: tabular-nums; }
  .scale button.on { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
  .focus { margin: 0; padding: 0.5rem 0.7rem; border-left: 3px solid var(--accent); background: var(--panel); border-radius: var(--radius); }
  .focus .eyebrow { display: block; }
  .buttons { display: flex; gap: 0.5rem; }
</style>
