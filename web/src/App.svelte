<script lang="ts">
  import type { Session } from "@supabase/supabase-js";
  import { supabase } from "./lib/supabase";
  import { loadTaxonomy } from "./lib/data";
  import Login from "./lib/Login.svelte";
  import Week from "./views/Week.svelte";
  import Planning from "./views/Planning.svelte";
  import Time from "./views/Time.svelte";
  import CV from "./views/CV.svelte";
  import Reading from "./views/Reading.svelte";
  import Help from "./views/Help.svelte";

  const views = { week: Week, planning: Planning, time: Time, reading: Reading, cv: CV, help: Help };
  const labels: Record<keyof typeof views, string> = {
    week: "Week", planning: "Planning", time: "Time", reading: "Reading", cv: "CV", help: "Help",
  };
  type Route = keyof typeof views;

  let session = $state<Session | null>(null);
  let ready = $state(false);
  let route = $state<Route>(routeFromHash());

  // Hash routing (#/week): no server rewrites needed, and the browser's
  // back button moves between views.
  function routeFromHash(): Route {
    const r = location.hash.replace(/^#\/?/, "");
    return r in views ? (r as Route) : "week"; // anything else, including the old #/log
  }

  $effect(() => {
    const onHash = () => (route = routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  $effect(() => {
    supabase.auth.getSession().then(({ data }) => {
      session = data.session;
      ready = true;
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => (session = s));
    return () => data.subscription.unsubscribe();
  });

  // Settings (week start, targets) load once after sign-in, before any view.
  let settingsReady = $state(false);
  let settingsError = $state("");
  $effect(() => {
    if (!session) return;
    loadTaxonomy()
      .then(() => (settingsReady = true))
      .catch((e) => (settingsError = e.message));
  });

  const View = $derived(views[route]);
</script>

{#if !ready}
  <p class="muted loading">Loading…</p>
{:else if !session}
  <Login />
{:else}
  <header>
    <nav>
      {#each Object.keys(views) as key (key)}
        <a href={`#/${key}`} class:active={route === key}>{labels[key as Route]}</a>
      {/each}
    </nav>
    <button onclick={() => supabase.auth.signOut()}>Sign out</button>
  </header>
  <main>
    {#if settingsError}
      <p class="error">{settingsError}</p>
    {:else if !settingsReady}
      <p class="muted">Loading…</p>
    {:else}
      <View />
    {/if}
  </main>
{/if}

<style>
  .loading { padding: 2rem 16px; }
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.6rem 16px;
    background: var(--paper);
    border-bottom: 1px solid var(--rule);
  }
  nav {
    display: flex;
    gap: 0.25rem;
    flex: 1;
    overflow-x: auto;
    font-family: var(--font-ui);
  }
  nav a {
    padding: 0.4rem 0.75rem;
    border-radius: var(--radius);
    color: var(--ink-soft);
    text-decoration: none;
    white-space: nowrap;
  }
  nav a.active {
    background: var(--panel);
    color: var(--ink);
    font-weight: 600;
  }
  main {
    max-width: 72rem;
    margin: 0 auto;
    padding: 1.5rem 16px 4rem;
  }
</style>
