<script lang="ts">
  // Reached from an email link: a new student's invitation (first password) or
  // a password reset. They are already signed in by the link.
  import { supabase } from "./supabase";

  let { first, ondone }: { first: boolean; ondone: () => void } = $props();
  let password = $state("");
  let again = $state("");
  let busy = $state(false);
  let error = $state("");

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (password.length < 8) return (error = "Use at least 8 characters.");
    if (password !== again) return (error = "The two don't match.");
    busy = true;
    error = "";
    const { error: err } = await supabase.auth.updateUser({ password });
    busy = false;
    if (err) error = err.message;
    else ondone();
  }
</script>

<main class="setpw">
  <span class="eyebrow">Duco Tracker</span>
  <h1>{first ? "Welcome — choose a password" : "Choose a new password"}</h1>
  <form onsubmit={save}>
    <label>Password <input type="password" bind:value={password} autocomplete="new-password" required /></label>
    <label>Again <input type="password" bind:value={again} autocomplete="new-password" required /></label>
    {#if error}<p class="error">{error}</p>{/if}
    <button class="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save and continue"}</button>
  </form>
</main>

<style>
  .setpw { max-width: 22rem; margin: 12vh auto 0; padding: 0 16px; }
  form { display: grid; gap: 0.9rem; margin-top: 1rem; }
  label { display: grid; gap: 0.3rem; font-family: var(--font-ui); font-size: 0.9rem; }
</style>
