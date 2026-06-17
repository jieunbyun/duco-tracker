# Research Group Tracker

A lightweight web app for a research group to plan projects, track time, and
follow milestone progress together. Built with [Streamlit](https://streamlit.io)
on top of a [Supabase](https://supabase.com) (PostgreSQL) database.

It is designed around a simple privacy principle: each person's exact hours and
estimates are private to them, while milestone progress (as a percentage) is
shared within a project. Projects are visible only to the people involved in
them.

## What it does

- **Log** time against categories, projects, and milestones.
- **Week** view of the current week, with hours by category and a weekly
  to-do list.
- **Projects** timeline (Gantt) showing each project's milestones and a daily
  occupancy forecast.
- **Milestones** list with per-milestone progress and edit history.
- **Planning** (private) for each person's own estimated hours and progress.
- **Time** summaries over a chosen period.
- **Budget** (lead only) with planned items, payments, and spend-vs-progress.
- **Help** explaining how it works and what is private.

## How privacy works

- A person's logged hours and estimated hours are visible only to themselves.
- What others in a project see is each milestone's completion percentage, not
  the hours behind it.
- A project is visible only to its owner and the people added to it, so private
  work can be kept private simply by not sharing the project.

Privacy is enforced at the database level through PostgreSQL row-level security,
not only in the interface. The app connects with the Supabase **anon** key so
those rules always apply.

## Repository layout

```
app/            Streamlit app (tracker.py, db.py) and requirements.txt
migrations/     Numbered SQL migrations defining the database schema
seed/           Optional seed data for a fresh database
docs/           Design notes and a fuller app guide
```

This repository contains **code only**. It holds no secrets and no data. The
Supabase URL and key are supplied separately (see Setup) and must never be
committed.

## Setup

### 1. Create the database

Create a Supabase project. In the Supabase SQL editor, run every file in
`migrations/` **in numeric order**, one at a time, clearing the editor between
each. The files are numbered to apply in sequence (the numbering skips a few
values where interim versions were superseded; just run the files that are
present, lowest to highest). A migration that creates tables or columns returns
"Success. No rows returned" — that is the normal, successful result.

Optionally, apply a seed file from `seed/` to start with example data.

### 2. Configure secrets

The app reads its Supabase connection from Streamlit secrets. Copy the template
and fill in your own values:

```
app/.streamlit/secrets.toml.template  ->  app/.streamlit/secrets.toml
```

Use the project's **anon / public** key, not the service key, so that
row-level security is enforced. The real `secrets.toml` is git-ignored and must
not be committed.

### 3. Run locally

```bash
cd app
pip install -r requirements.txt
streamlit run tracker.py
```

## Deploying

The simplest free route is **Streamlit Community Cloud**, which deploys from a
GitHub repository:

1. Push this repository to GitHub (confirm `secrets.toml` is git-ignored and
   absent from the repo).
2. At [share.streamlit.io](https://share.streamlit.io), create an app pointing
   at this repo, your branch, and `app/tracker.py`.
3. Under **Advanced settings**, paste the contents of your `secrets.toml` into
   the Secrets field.
4. Deploy, then share the resulting URL.

For current, authoritative deployment instructions, see the
[Streamlit Community Cloud docs](https://docs.streamlit.io/deploy/streamlit-community-cloud).

## Adding people

Each member needs:

1. A Supabase **Auth** account (email or Google sign-in).
2. A matching row in the `app_user` table, with their `auth_user_id` linked and
   a role of `lead`, `student`, or `viewer`.
3. To be added to the projects they work on (the `project_lead` table). Because
   visibility is membership-based, a person who is not a member of any project
   will see an empty app until they are added.

## A note on migrations

Keep the database ahead of the app. When schema changes, apply the new
migration **before** deploying app code that uses it; otherwise the app will
request columns the database does not yet have. Applying them in numeric order,
and confirming each landed, avoids the common pitfalls.

## License and use

Internal research-group tool. Adapt as needed for your own group.
