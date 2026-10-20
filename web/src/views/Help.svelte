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

  <p class="muted">Your data: <em>Planning › Your data</em> exports everything in the app as one file for OneDrive.</p>

  <p class="lede">
    Time is organised the way the yearly allocation is:
    <strong>area</strong> (Research, Teaching, Admin, Outreach) › <strong>category</strong>
    (Supervision, Publications, Email…) › <strong>project</strong> › <strong>milestone</strong>.
    Each category is routine, project-based, mixed, miscellaneous or email, which decides how it is planned.
  </p>

  <h2>The views</h2>
  <dl>
    <dt>Week</dt>
    <dd>
      Log time and plan a chosen week, in one place. <em>+ Log</em> (top, or under any day) records a session
      against a category, and optionally a project and milestone — new ones can be created on the spot — by start
      and end times (an end of 00:00 means midnight) or by minutes. It starts where that day's last entry ended.
      Click a logged entry on a day to edit, delete, copy it to another date, or turn it into a CV achievement.
      <em>+ From milestones</em> lists the milestones whose dates fall in the week (and any overdue), each with this
      week's share of its remaining hours — spread evenly to its due date, as in Planning — and turns the ones you tick
      into to-dos linked to the milestone, its project and category; overdue and due-this-week ones are pre-ticked,
      unless the milestone already has an open to-do this week (named in the list; you can still add another).
      <em>To think about</em>, at the end of the to-do list, holds ideas jotted down as they come — a conference
      title, an angle to explore: not tied to a week and never counted as planned time. A web address pasted into an
      idea or its notes shows as a short underlined “link”. Ideas are listed oldest first; drag the ⠿ handle (or
      press ↑ ↓ on it) to rearrange them. Edit one to develop it with notes; turn it into a to-do, mark it done once thought through, or delete it.
      <em>Meetings</em> have a day and clock times (add them by hand, repeat weekly, or import
      invites from an <code>.ics</code> file). <em>To-dos</em> belong to the week and can be planned onto one or
      more days; mark them must-do or flexible. Once a to-do is on a day it shows on the calendar only, and the list
      below keeps the ones not yet placed. <em>✓ Log</em> on a card opens the log form already filled in and
      ties the logged time back to the plan. Open to-dos from earlier weeks are carried into the current week, under Must do or Flexible
      like the rest and marked “from week of …”, until done or cancelled. Cancel keeps a to-do in the list, struck
      through and restorable; Delete removes it. A red edge marks a planned day that has passed without being logged.
      Click or right-click a meeting or duty on the calendar for its actions: log time, move it a day, cancel it
      (it stays on its day, struck through and restorable, as a record of what was planned), edit it, or take it off
      the calendar (for a meeting, delete it). For a duty, the menu also marks the to-do done or reopens it.
      Moving a card onto a day that already has the same to-do merges them into one card with the hours added; a
      day partly logged offers to move its remaining hours to the next day, keeping what was done.
      <em>Plan across days…</em> (on a duty's menu, or in the to-do list) lets you tick several days and give the
      total hours, which are split evenly over them; each card then shows its share.
      <em>✉ Create email checks</em>, under the calendar, adds a 1.5-hour “Email check” to-do on each weekday;
      each day is its own to-do, so any one can be edited, moved or cancelled. The bar that appears at the bottom
      after a change offers to undo it.
    </dd>

    <dt>Undo</dt>
    <dd>
      <em>↶ Undo</em> at the top right, or Ctrl+Z, takes back your latest change in any tab — an edit, an addition
      or a deletion (a deleted item comes back with its links, notes and everything else deleted along with it).
      Press it again to go further back, through the changes of this session; hover over it to see what it will
      undo. Changes made within a second of each other count as one. The Outlook sync is not something it undoes.
    </dd>

    <dt>Outlook</dt>
    <dd>
      Connect your published Outlook calendar (Week › Connect Outlook calendar). It syncs when you open Week, if
      the last sync is a few hours old, and with Sync now — for this week, or further ahead if you choose
      so in the Outlook settings. New events
      wait under <em>From Outlook — to review</em>, dashed on the calendar and not counted as planned: give each a
      category (and project), adjust its times or hours, then <em>Keep</em> it, or mark it <em>Irrelevant</em> —
      this one, or every repeat — and it never comes back. <em>Tentative</em> keeps it on the calendar, dotted and not
      counted as planned, until you confirm it from its card's menu; events Outlook shows as tentative (or not yet
      accepted) arrive tagged so, and the mark follows when you accept or decline there. Any meeting can be marked
      tentative from its menu. Events moved in Outlook move here too unless already
      logged; events removed there disappear if unreviewed, or are struck through if kept. Ignored events can be
      brought back in the Outlook settings. The calendar link stays in your database.
    </dd>

    <dt>Planning</dt>
    <dd>
      Projects under each project-based category, with dates, planned hours and milestones, against the hours
      logged. Above them, how much of the planning horizon is still free per area. Below, the weekly targets and
      settings.
    </dd>

    <dt>Pathways</dt>
    <dd>
      A map of where your work is heading: rows for Goals &amp; Objectives, Awards, Publications &amp; code/database, Teaching, Outreach and Grant
      Writing, time running
      from now to a horizon you choose (3–20 years), and long-term goals on the right. Add goals, near-term
      objectives, projects (linked to a Planning project — + From Planning brings several at once, each into its
      area's lane with its dates — or potential, dashed, with person-months and cost),
      people (with their strengths and share of time) and knowledge gaps (linked to Reading). Drag an item to move
      it in time or across lanes, drag its right edge to stretch it, drag its ○ onto another item to link them (an
      arrow from one to the other), and click it to edit. A goal without dates sits in the goals column; give it dates (or drag it onto the timeline) and it sits
      in its lane over that span — drag it back to the column to clear them. Rewording a goal keeps its earlier
      wording and your reason. An item linked to a Planning project shows that project's name and dates, and
      moving it on the map moves the project too.
      Mark a project <em>hands-on</em> (✋, in its editor or on its row in the List) when your own research time
      goes into it substantially; it stands out on the map, bolder and shaded.
      Dates on Pathways are months: an item runs from the start of its first month to the end of its last
      (a linked Planning project keeps its exact days, but shows months here too).
      An item can list its <em>contributors</em> from your group (in its editor). Each member then sees, in their
      own Pathways tab, a read-only chart of the items they contribute to and the goals and objectives those lead
      to — titles, dates and stages only, never your notes, costs or effort.
      An <em>award</em> (in the Awards row) goes through the same stages as a grant.
      The <em>Grant Writing</em> row holds grant applications: writing period up to the deadline, stage
      (drafting, submitted, awarded, declined) and, if you like, the amount sought. Link a grant to whatever it
      would fund, in any lane; that item reads “funding pending” until the grant is awarded, then “funded”. Projects under Proposals in Planning arrive here as grants.
      <em>List</em> (the second view) shows every item by lane, with quick entry at the top — kind, title, lane and
      optional dates, Enter to add and straight on to the next — and each item's links, which you can add
      or remove right there. <em>Outputs</em> (the third view) is the group's map of what it has developed, in three bands —
      inference algorithms; data, models &amp; simulators; others — with time running left to right by when each
      was developed. Each output has its contributors, the publications it belongs to (picked from Publications
      &amp; code/database), and a link to where its data or code lives. Drag an output's ○ onto another to connect
      them; pick a contributor to bring their outputs forward. Every member sees this map (in their Pathways tab)
      and adds their own outputs; an output can be changed by whoever added it, its contributors, and you.
      “Copy catalogue” gives the cards as YAML, ready to seed a shared repository.
    </dd>

    <dt>Members</dt>
    <dd>
      Your group's members (students, collaborators) sign in to this same app and see only tabs of their own:
      <em>Logbook</em>, <em>Projects</em> and <em>Pathways</em> (their own chart, and the group's outputs). Nothing else here — your planning, time, targets, Pathways — is
      visible to them. To add a member: invite them in Supabase (<em>Authentication › Users › Invite user</em>; they
      get an email to choose a password), then <em>+ Add a member</em> here: pick them from your Planning projects
      under Research › Supervision (their name then follows Planning) or, for anyone else, type a name.
      You come first in the list, with the projects you lead.
      The <em>Logbook</em> is built on actions: each project's actions, milestone by milestone, each with its own dated
      thread of comments and links. Tick off what is done, add what comes up under a milestone, drag the ⠿ handle to
      put them in order, click an action to rename it, and use <em>comment / link</em> to add to its thread. Your
      Logbook covers the projects you lead and your Planning projects; a member's covers their shared projects. Under
      each member are their projects (several each; you create them and choose who leads, and both of you tick off
      milestones) and their Logbook, where you read their threads and reply. A comment can be taken back on the day it
      was written; after that it stays. Actions are not to-dos and never appear on Week's lists, but the same actions
      appear when you log a block in Week, to tick, add, comment on and reorder there; time is logged there, never per
      action. <em>Actions done</em> keeps the history of every action ticked off, by month, with its thread.
      <em>Export logbook</em> saves it as a Markdown file, to keep on OneDrive or take along when they leave; entries
      written before the Logbook moved to actions stay readable under <em>Earlier entries</em>.
      <em>Take out of the group</em> ends their access but keeps their logbook. <em>See what they see</em> shows their
      tabs exactly as they see them, read-only, until you go back to your view. On the Pathways map, a project can
      stand for a member's project, and then shows how many comments its actions had this week.
    </dd>

    <dt>Time</dt>
    <dd>
      Where the time went over a period: hours against target per area, and a breakdown you can click into — all
      work › area › category › project › milestone.
    </dd>

    <dt>Reading</dt>
    <dd>
      Journal articles, books, chapters and reports you read: details (a DOI fills them in from Crossref), status —
      reading, to read, finished, abandoned — with start and finish dates, an optional project, dated notes (with a
      page if you like), a citation and BibTeX to copy, and a link to its PDF on OneDrive. (PDFs uploaded here before still
      open; once a PDF is on OneDrive and linked, its stored copy can be removed.)
    </dd>

    <dt>CV</dt>
    <dd>
      Achievement records by CV section, with a tailored form for supervision, and a LaTeX export
      (<code>jobshort</code>/<code>joblong</code>) for your CV source.
    </dd>
  </dl>

  <h2>Categories</h2>
  <p class="muted small">
    Your own notes, kept in your database. Under Planning › Categories you can add, rename, change the kind of, and
    remove categories: one nothing uses is deleted; one with history is retired — gone from every list, but past
    hours keep its name, and it can be restored. A category with live projects must be emptied first.
  </p>
  {#if tax}
    {#each tax.areas as a (a.id)}
      <h3>{a.label}</h3>
      <dl class="cats">
        {#each tax.categories.filter((c) => c.area_id === a.id) as c (c.id)}
          <dt>{c.label} <span class="muted kind">{c.kind}</span></dt>
          <dd>{#if c.description}{c.description}{:else}<span class="muted">No note yet.</span>{/if}</dd>
        {/each}
      </dl>
    {/each}
  {/if}

  <h2>How the numbers are worked out</h2>
  <dl>
    <dt>Targets</dt>
    <dd>
      Each area has weekly hours for its own work and for email
      {#if tax}— {tax.weeksPerYear} working weeks a year{/if}. A period's target spreads the year's total evenly
      over the calendar, and a period still under way is judged only on the days so far. Changing a target applies
      from a chosen date, so earlier periods keep the target they had.
    </dd>

    <dt>Email</dt>
    <dd>
      Email is one shared pot: time logged under any Email category counts in equal shares to every area that has
      an Email category (Teaching, Admin and Outreach), in Time and in Planning alike. Log it under whichever Email
      category you like.
    </dd>

    <dt>Remaining time (Planning)</dt>
    <dd>
      Capacity over the period chosen with the buttons in Planning (2 weeks to 24 months), minus
      <em>routine</em> time — non-project categories, projected at your pace over the last {PACE_DAYS / 7} weeks —
      minus hours <em>committed</em> to live projects: each project's planned hours less what is already logged,
      spread evenly to its end date, counting only the part inside the horizon. What is left is free.
      Projects in routine categories (such as one per supervised student) count through routine time, not twice.
      A project's planned hours are the sum of its milestones' hours — marked Σ — when every milestone (other than
      dropped ones) has hours, or when the project has no figure of its own; otherwise its own figure. With no end date, a project ends with its latest
      milestone. When the plan comes from milestones, each milestone's remaining hours are spread over
      its own dates (start to due, falling back to the project's), so work due soon weighs on the near term.
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
  dd { margin: 0.2rem 0 0; color: var(--ink); white-space: pre-line; }
  .help h3 { margin-top: 1.2rem; font-size: 1rem; }
  .cats dt { margin-top: 0.6rem; }
  .kind { font-weight: 400; font-size: 0.8rem; font-family: var(--font-ui); }
  .small { font-size: 0.85rem; font-family: var(--font-ui); }
</style>
