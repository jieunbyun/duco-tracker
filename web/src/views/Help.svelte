<script lang="ts">
  import { loadTaxonomy } from "../lib/data";
  import type { Taxonomy } from "../lib/data";
  import { PACE_DAYS } from "../lib/horizon";

  let tax = $state<Taxonomy | null>(null);
  loadTaxonomy().then((t) => (tax = t)).catch(() => {});
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
</script>

<section class="help">
  <span class="eyebrow">Help</span>
  <h1>How the tracker works</h1>

  <p class="lede">
    Time is organised the way the yearly allocation is:
    <strong>area</strong> (Research, Teaching, Admin, Outreach) › <strong>category</strong>
    (Supervision, Publications, Email…) › <strong>project</strong> › <strong>milestone</strong>.
    Each category is routine, project-based, mixed, miscellaneous or email, which decides how it is planned.
  </p>

  <h2>The views</h2>
  <dl>
    <dt>Log</dt>
    <dd>
      Record a session against a category, and optionally a project and milestone — new ones can be created on
      the spot. Give start and end times (an end of 00:00 means midnight) or just minutes. The form starts where
      today's last entry ended. Click a recent entry to edit, delete, copy it to another date, or turn it into a
      CV achievement.
    </dd>

    <dt>Week</dt>
    <dd>
      Plan a chosen week. <em>Meetings</em> have a day and clock times (add them by hand, repeat weekly, or import
      invites from an <code>.ics</code> file). <em>To-dos</em> belong to the week and can be planned onto one or
      more days; mark them must-do or flexible. <em>✓ Log</em> on a card opens the log form already filled in and
      ties the logged time back to the plan. Open to-dos from earlier weeks are carried into the current week until
      done or cancelled. A red edge marks a planned day that has passed without being logged.
      <em>Cancel</em> on a card keeps it on its day, struck through and restorable, as a record of what was
      planned; <em>✕</em> takes it off the calendar altogether (for a meeting, deletes it).
    </dd>

    <dt>Planning</dt>
    <dd>
      Projects under each project-based category, with dates, planned hours and milestones, against the hours
      logged. Above them, how much of the planning horizon is still free per area. Below, the weekly targets and
      settings.
    </dd>

    <dt>Time</dt>
    <dd>
      Where the time went over a period: hours against target per area, and a breakdown you can click into — all
      work › area › category › project › milestone.
    </dd>

    <dt>CV</dt>
    <dd>
      Achievement records by CV section, with a tailored form for supervision, and a LaTeX export
      (<code>jobshort</code>/<code>joblong</code>) for your CV source.
    </dd>
  </dl>

  <h2>How the numbers are worked out</h2>
  <dl>
    <dt>Targets</dt>
    <dd>
      Each area has weekly hours for its own work and for email
      {#if tax}— {tax.weeksPerYear} working weeks a year{/if}. A period's target spreads the year's total evenly
      over the calendar, and a period still under way is judged only on the days so far. Changing a target applies
      from a chosen date, so earlier periods keep the target they had.
    </dd>

    <dt>Remaining time (Planning)</dt>
    <dd>
      Capacity over the horizon{#if tax} ({tax.horizonMonths} months){/if}, minus
      <em>routine</em> time — non-project categories, projected at your pace over the last {PACE_DAYS / 7} weeks —
      minus hours <em>committed</em> to live projects: each project's planned hours less what is already logged,
      spread evenly to its end date, counting only the part inside the horizon. What is left is free.
      Projects in routine categories (such as one per supervised student) count through routine time, not twice.
    </dd>

    <dt>Weeks</dt>
    <dd>Weeks start on {tax ? DAYS[tax.weekStartsOn] : "the day set in Planning"} (change it under Planning › Allocation).</dd>

    <dt>Clock times</dt>
    <dd>
      Times are stored as diary times — 09:00 is 09:00 whatever the season — so days split at midnight and
      there are no 23- or 25-hour days when the clocks change. Imported invites are converted to your own time.
    </dd>
  </dl>

  <h2>Privacy</h2>
  <p>
    Everything is yours alone. The database only returns rows you own, and that rule lives in the database
    itself, not just in this app.
  </p>
</section>

<style>
  .help { max-width: 46rem; }
  .lede { font-size: 1.02rem; }
  .help h2 { margin-top: 2rem; }
  dl { margin: 0; }
  dt { font-weight: 600; margin-top: 1rem; }
  dd { margin: 0.2rem 0 0; color: var(--ink); }
</style>
