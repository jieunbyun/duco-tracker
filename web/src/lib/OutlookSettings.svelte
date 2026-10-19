<script lang="ts">
  import { loadFeed, saveFeedUrl, loadIgnores, removeIgnore } from "./outlook";
  import type { Ignore } from "./outlook";

  type Props = { onsaved: (linkChanged: boolean) => void; oncancel: () => void };
  let { onsaved, oncancel }: Props = $props();

  let url = $state("");
  let saved = $state("");
  let show = $state(false);
  let ignores = $state<Ignore[]>([]);
  let busy = $state(false);
  let error = $state("");

  Promise.all([loadFeed(), loadIgnores()])
    .then(([f, i]) => {
      url = saved = f?.ics_url ?? "";
      ignores = i;
    })
    .catch((e) => (error = e.message));

  async function save(event: SubmitEvent) {
    event.preventDefault();
    const clean = url.trim();
    if (clean && !/^(https|webcal):\/\//i.test(clean)) return (error = "Paste the ICS link: it starts with https:// (or webcal://).");
    busy = true;
    error = "";
    try {
      await saveFeedUrl(clean || null);
      onsaved(clean !== saved);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function bringBack(i: Ignore) {
    try {
      await removeIgnore(i.id);
      ignores = ignores.filter((x) => x.id !== i.id);
    } catch (e) {
      error = (e as Error).message;
    }
  }
</script>

<form class="outlook" onsubmit={save}>
  <p class="muted small">
    In Outlook on the web: Settings › Calendar › Shared calendars › Publish a calendar, “Can view all details”,
    then copy the <strong>ICS</strong> link. It is kept in your database only; anyone with it can read your calendar.
  </p>
  <label>
    Calendar link (ICS)
    <span class="row">
      <input type={show ? "text" : "password"} bind:value={url} placeholder="https://outlook.office365.com/owa/calendar/…/calendar.ics" autocomplete="off" />
      <button type="button" onclick={() => (show = !show)}>{show ? "Hide" : "Show"}</button>
    </span>
  </label>

  {#if ignores.length}
    <div class="ignores">
      <h3>Ignored events</h3>
      <ul>
        {#each ignores as i (i.id)}
          <li>
            <span>{i.title ?? i.uid} <span class="muted">{i.occurrence ? "(one occurrence)" : "(all repeats)"}</span></span>
            <button type="button" onclick={() => bringBack(i)}>Bring back</button>
          </li>
        {/each}
      </ul>
      <p class="muted small">Brought-back events return on the next sync.</p>
    </div>
  {/if}

  {#if error}<p class="error">{error}</p>{/if}
  <div class="actions">
    <button class="primary" type="submit" disabled={busy}>Save</button>
    <button type="button" onclick={oncancel} disabled={busy}>Close</button>
  </div>
</form>

<style>
  .outlook { display: grid; gap: 0.9rem; font-family: var(--font-ui); }
  label { display: grid; gap: 0.3rem; font-size: 0.82rem; color: var(--ink-soft); }
  .row { display: flex; gap: 0.4rem; }
  .row button { flex: none; }
  .small { font-size: 0.8rem; margin: 0; }
  h3 { font-size: 0.9rem; margin: 0 0 0.3rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.2rem; }
  li { display: flex; justify-content: space-between; gap: 0.6rem; align-items: center; font-size: 0.85rem; }
  li button { font-size: 0.75rem; padding: 0.15rem 0.5rem; }
  .actions { display: flex; gap: 0.5rem; }
</style>
