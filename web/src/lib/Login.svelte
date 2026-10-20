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

  // a forgotten password: a link by email that leads back here to set a new one
  let sent = $state(false);
  async function reset() {
    if (!email) return (error = "Enter your email first.");
    busy = true;
    error = "";
    const { error: err } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: location.origin + location.pathname });
    busy = false;
    if (err) error = err.message;
    else sent = true;
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
    {#if sent}<p class="muted">If there is an account for that email, a link to set a new password is on its way.</p>
    {:else}<button type="button" class="link" onclick={reset} disabled={busy}>Forgot your password?</button>{/if}
  </form>
</main>

<style>
  .login {
    max-width: 22rem;
    margin: 12vh auto 0;
    padding: 0 16px;
  }
  form { display: grid; gap: 0.9rem; margin-top: 1rem; }
  .link { background: none; border: none; color: var(--accent); text-decoration: underline; padding: 0; justify-self: start; font-size: 0.85rem; }
  label { display: grid; gap: 0.3rem; font-family: var(--font-ui); font-size: 0.9rem; }
</style>
