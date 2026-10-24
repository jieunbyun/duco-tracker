<script lang="ts">
  import type { Session } from "@supabase/supabase-js";
  import { supabase, arrival } from "./lib/supabase";
  import { loadTaxonomy } from "./lib/data";
  import { myRole } from "./lib/group";
  import type { Role } from "./lib/group";
  import type { Component } from "svelte";
  import Login from "./lib/Login.svelte";
  import SetPassword from "./lib/SetPassword.svelte";
  import { undo, undoLast } from "./lib/undo.svelte";
  import { preview } from "./lib/preview.svelte";

  // Each tab's code is fetched when the tab is first opened, so the app starts
  // with only what the opening tab needs.
  const views = {
    week: () => import("./views/Week.svelte"),
    planning: () => import("./views/Planning.svelte"),
    pathways: () => import("./views/Pathways.svelte"),
    supervision: () => import("./views/Supervision.svelte"),
    time: () => import("./views/Time.svelte"),
    reading: () => import("./views/Reading.svelte"),
    cv: () => import("./views/CV.svelte"),
    help: () => import("./views/Help.svelte"),
    logbook: () => import("./views/MyLogbook.svelte"),
    projects: () => import("./views/MyProjects.svelte"),
    chart: () => import("./views/MemberPathways.svelte"),
  };
  const labels: Record<keyof typeof views, string> = {
    week: "Week", planning: "Planning", pathways: "Pathways", supervision: "Members", time: "Time", reading: "Reading",
    cv: "CV", help: "Help", logbook: "Logbook", projects: "Projects", chart: "Pathways",
  };
  type Route = keyof typeof views;

  // Who sees which tabs: the planner is yours alone; a member sees only their
  // logbook, projects and their own reading list. You keep a logbook too, for
  // the projects you lead.
  const OWNER: Route[] = ["week", "planning", "time", "reading", "pathways", "cv"];
  const SUPERVISOR: Route[] = ["week", "planning", "time", "reading", "pathways", "cv", "supervision", "logbook"];
  const MEMBER: Route[] = ["logbook", "projects", "reading"];

  let session = $state<Session | null>(null);
  let ready = $state(false);
  let role = $state<Role | "none" | null | undefined>(undefined); // undefined: not known yet; null: the planner's owner, no group
  let needsPassword = $state(arrival === "invite" || arrival === "recovery");
  const member = $derived(role === "member");
  // while you preview a member ("See what they see"), their tabs
  const tabs = $derived(member || preview.as ? MEMBER : role === "supervisor" ? SUPERVISOR : OWNER);

  // Hash routing (#/week): no server rewrites needed, and the browser's
  // back button moves between views. Anything else (including the old #/log)
  // opens the first tab.
  const fromHash = () => location.hash.replace(/^#\/?/, "");
  let hash = $state(fromHash());
  // Help is not a tab; it opens from the ? in the header
  const route = $derived<Route>(
    tabs.includes(hash as Route) || (hash === "help" && !member && !preview.as) ? (hash as Route) : tabs[0],
  );

  $effect(() => {
    const onHash = () => (hash = fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  $effect(() => {
    supabase.auth.getSession().then(({ data }) => {
      session = data.session;
      ready = true;
    });
    const { data } = supabase.auth.onAuthStateChange((event, s) => {
      session = s;
      if (event === "PASSWORD_RECOVERY") needsPassword = true;
    });
    return () => data.subscription.unsubscribe();
  });

  $effect(() => {
    if (!session) return void (role = undefined);
    myRole().then((r) => (role = r)).catch(() => (role = null));
  });

  // Settings (week start, targets) load once after sign-in, before any view of the planner.
  let settingsReady = $state(false);
  let settingsError = $state("");
  $effect(() => {
    if (!session || role === undefined) return;
    if (member || role === "none") return void (settingsReady = true);
    loadTaxonomy()
      .then(() => (settingsReady = true))
      .catch((e) => (settingsError = e.message));
  });

  let View = $state<Component | null>(null);
  let viewError = $state("");
  $effect(() => {
    const r = route;
    if (role === undefined || role === "none") return;
    viewError = "";
    views[r]()
      .then((m) => { if (route === r) View = m.default as Component; })
      .catch((e) => (viewError = `Could not load this tab: ${(e as Error).message}`));
  });

  // Ctrl/Cmd+Z undoes the latest change, in any tab — unless you are typing
  // or a dialog is open.
  const lastAction = $derived(undo.actions[undo.actions.length - 1] ?? null);
  function keys(ev: KeyboardEvent) {
    if (!(ev.ctrlKey || ev.metaKey) || ev.shiftKey || ev.altKey || ev.key.toLowerCase() !== "z") return;
    const el = document.activeElement as HTMLElement | null;
    if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
    if (document.querySelector("dialog[open]")) return;
    ev.preventDefault();
    undoLast();
  }
</script>

<svelte:window onkeydown={keys} />

{#if !ready}
  <p class="muted loading">Loading…</p>
{:else if !session}
  <Login />
{:else if needsPassword}
  <SetPassword first={arrival === "invite"} ondone={() => { needsPassword = false; history.replaceState(null, "", location.pathname); hash = ""; }} />
{:else if role === "none"}
  <main class="waiting">
    <h1>Almost there</h1>
    <p>You're signed in as <strong>{session.user.email}</strong>, but you haven't been added to the group yet.
      Once they have, reload this page.</p>
    <button onclick={() => supabase.auth.signOut()}>Sign out</button>
  </main>
{:else}
  {#if preview.as}
    <div class="previewing" role="status">
      <span>Seeing what <strong>{preview.as.display_name}</strong> sees · read-only</span>
      <button onclick={() => { preview.as = null; location.hash = "#/supervision"; }}>Back to your view</button>
    </div>
  {/if}
  <header>
    <nav>
      {#each tabs as key (key)}
        <a href={`#/${key}`} class:active={route === key}>{labels[key]}</a>
      {/each}
    </nav>
    {#if !member && !preview.as}<a class="help" href="#/help" class:active={route === "help"} title="How the tracker works">?</a>{/if}
    <button class="undo" onclick={undoLast} disabled={!lastAction}
            title={lastAction ? `Undo: ${lastAction.label} (Ctrl+Z)` : "Nothing to undo"}>↶ Undo</button>
    <button onclick={() => supabase.auth.signOut()}>Sign out</button>
  </header>
  <main>
    {#if settingsError}
      <p class="error">{settingsError}</p>
    {:else if !settingsReady}
      <p class="muted">Loading…</p>
    {:else}
      {#if viewError}
        <p class="error">{viewError}</p>
      {:else if preview.as && route === "reading"}
        <!-- a member's reading list is theirs alone: even you cannot read it -->
        <p class="muted">{preview.as.display_name}'s Reading tab is private to them, so it can't be shown here.
          It works as yours does: their own list of readings, notes and PDFs.</p>
      {:else if View}
        {#key undo.version}<View />{/key}
      {:else}
        <p class="muted">Loading…</p>
      {/if}
    {/if}
  </main>
  {#if undo.toast}
    <div class="undo-toast" role="status">
      <span>{undo.toast}</span>
      {#if lastAction}<button onclick={undoLast}>Undo again</button>{/if}
      <button class="x" aria-label="Dismiss" onclick={() => (undo.toast = null)}>✕</button>
    </div>
  {/if}
{/if}

<style>
  .loading { padding: 2rem 16px; }
  .waiting { max-width: 32rem; margin: 12vh auto 0; padding: 0 16px; }
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
  .undo { white-space: nowrap; }
  .help {
    display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 50%; border: 1px solid var(--rule);
    color: var(--ink-soft); text-decoration: none; font-family: var(--font-ui); font-weight: 600;
  }
  .help.active, .help:hover { color: var(--ink); border-color: var(--ink-soft); }
  .previewing {
    display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: center; justify-content: center; padding: 0.45rem 16px;
    background: var(--accent); color: var(--accent-ink); font-family: var(--font-ui); font-size: 0.88rem;
  }
  .previewing button { font-size: 0.8rem; padding: 0.2rem 0.7rem; }
  .undo-toast {
    position: fixed; left: 50%; bottom: 1.2rem; transform: translateX(-50%); z-index: 30;
    display: flex; gap: 0.7rem; align-items: center; max-width: calc(100vw - 32px);
    padding: 0.55rem 0.8rem 0.55rem 1rem; border-radius: var(--radius); font-family: var(--font-ui); font-size: 0.88rem;
    background: var(--ink); color: var(--paper); box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
  }
  .undo-toast button { background: none; border: 1px solid var(--paper); color: var(--paper); padding: 0.2rem 0.7rem; font-size: 0.82rem; }
  .undo-toast button.x { border: none; padding: 0.2rem 0.4rem; opacity: 0.8; }
  main {
    max-width: 72rem;
    margin: 0 auto;
    padding: 1.5rem 16px 4rem;
  }
</style>
