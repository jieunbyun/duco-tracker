<script lang="ts">
  import { supabase } from "./supabase";

  let email = $state("");
  let password = $state("");
  let busy = $state(false);
  let error = $state("");

  async function signIn(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = "";
    const { error: err } = await supabase.auth.signInWithPassword({ email, password });
    busy = false;
    if (err) error = err.message;
  }
</script>

<main class="login">
  <span class="eyebrow">Duco Tracker</span>
  <h1>Sign in</h1>
  <form onsubmit={signIn}>
    <label>Email <input type="email" bind:value={email} autocomplete="email" required /></label>
    <label>
      Password
      <input type="password" bind:value={password} autocomplete="current-password" required />
    </label>
    {#if error}<p class="error">{error}</p>{/if}
    <button class="primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
  </form>
</main>

<style>
  .login {
    max-width: 22rem;
    margin: 12vh auto 0;
    padding: 0 16px;
  }
  form { display: grid; gap: 0.9rem; margin-top: 1rem; }
  label { display: grid; gap: 0.3rem; font-family: var(--font-ui); font-size: 0.9rem; }
</style>
