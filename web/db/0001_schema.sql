-- 0001_schema.sql — personal tracker, fresh Supabase project.
--
-- Taxonomy (mirrors the yearly allocation sheet):
--
--   area        Research / Teaching / Admin / Outreach (+ life areas)
--     └ category   Supervision, Publications, CPD, Email, ...  (kind says how
--                  it is planned: routine, project, mixed, misc, email)
--         └ project    planned period + planned hours
--             └ milestone  planned period + planned hours
--
-- area_target holds the weekly hours per area (time and email separately),
-- versioned by effective_from so next year's allocation does not rewrite
-- this year's history. user_setting holds weeks per year and the horizon.
--
-- Every table carries user_id (default auth.uid()) and one RLS policy:
-- a row is visible and writable only by its owner.
--
-- Time convention (kept from the old app): timestamps hold WALL-CLOCK time
-- labelled UTC. 09:00 in the diary is stored as 09:00+00 whatever the season,
-- so days split at 00:00+00 and there are no 23- or 25-hour days.

-- ---- taxonomy ----------------------------------------------------------
create table area (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  code        text not null,
  label       text not null,
  domain      text not null default 'work' check (domain in ('work', 'life')),
  sort_order  smallint not null default 100,
  is_active   boolean not null default true,
  unique (user_id, code)
);

create table area_target (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null default auth.uid() references auth.users on delete cascade,
  area_id             uuid not null references area on delete cascade,
  effective_from      date not null,
  weekly_hours        numeric not null default 0 check (weekly_hours >= 0),
  email_weekly_hours  numeric not null default 0 check (email_weekly_hours >= 0),
  unique (area_id, effective_from)
);

create table category (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  area_id     uuid not null references area on delete restrict,
  code        text not null,
  label       text not null,
  kind        text not null check (kind in ('routine', 'project', 'mixed', 'misc', 'email')),
  sort_order  smallint not null default 100,
  is_active   boolean not null default true,
  unique (user_id, code)
);

create table user_setting (
  user_id         uuid primary key default auth.uid() references auth.users on delete cascade,
  weeks_per_year  numeric not null default 52 check (weeks_per_year > 0 and weeks_per_year <= 52),
  horizon_months  smallint not null default 12 check (horizon_months between 1 and 36),
  week_starts_on  smallint not null default 1 check (week_starts_on between 0 and 6)  -- 1 = Monday
);

-- ---- projects ----------------------------------------------------------
create table project (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  category_id    uuid not null references category on delete restrict,
  name           text not null,
  status         text not null default 'active'
                 check (status in ('planned', 'active', 'paused', 'done', 'dropped')),
  start_on       date,
  end_on         date,
  planned_hours  numeric check (planned_hours is null or planned_hours >= 0),
  is_important   boolean not null default false,
  notes          text,
  created_at     timestamptz not null default now(),
  check (end_on is null or start_on is null or end_on >= start_on)
);

create table milestone (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  project_id     uuid not null references project on delete cascade,
  title          text not null,
  status         text not null default 'planned'
                 check (status in ('planned', 'active', 'done', 'dropped')),
  start_on       date,
  due_on         date,
  planned_hours  numeric check (planned_hours is null or planned_hours >= 0),
  hard_deadline  boolean not null default false,
  sort_order     smallint not null default 100,
  notes          text,
  created_at     timestamptz not null default now(),
  check (due_on is null or start_on is null or due_on >= start_on)
);

-- ---- logged time -------------------------------------------------------
create table time_entry (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users on delete cascade,
  category_id     uuid not null references category on delete restrict,
  project_id      uuid references project on delete set null,
  milestone_id    uuid references milestone on delete set null,
  started_at      timestamptz not null,
  ended_at        timestamptz,
  manual_minutes  integer check (manual_minutes is null or manual_minutes >= 0),
  minutes         numeric generated always as (
                    coalesce(manual_minutes,
                             extract(epoch from (ended_at - started_at)) / 60)
                  ) stored,
  description     text,
  is_core         boolean not null default false,
  created_at      timestamptz not null default now(),
  check (ended_at is not null or manual_minutes is not null),
  check (ended_at is null or ended_at > started_at)
);

-- A milestone implies its project, and a project implies its category, so the
-- drill-down area > category > project > milestone can never disagree with
-- itself. Applied to every table that can point at a project or milestone.
create function fill_placement() returns trigger
language plpgsql as $$
begin
  if new.milestone_id is not null then
    select project_id into new.project_id from milestone where id = new.milestone_id;
  end if;
  if new.project_id is not null then
    select category_id into new.category_id from project where id = new.project_id;
  end if;
  return new;
end $$;

create trigger time_entry_placement before insert or update on time_entry
  for each row execute function fill_placement();

-- Moving a milestone to another project, or a project to another category,
-- carries its logged time and to-dos with it.
create function cascade_placement() returns trigger
language plpgsql as $$
begin
  if tg_table_name = 'milestone' then
    update time_entry set project_id = new.project_id where milestone_id = new.id;
    update todo       set project_id = new.project_id where milestone_id = new.id;
  else
    update time_entry set category_id = new.category_id where project_id = new.id;
    update todo       set category_id = new.category_id where project_id = new.id;
  end if;
  return null;
end $$;

create trigger milestone_moved after update of project_id on milestone
  for each row when (old.project_id is distinct from new.project_id)
  execute function cascade_placement();
create trigger project_moved after update of category_id on project
  for each row when (old.category_id is distinct from new.category_id)
  execute function cascade_placement();

-- ---- week planning -----------------------------------------------------
-- A to-do is a duty for a week; a meeting is a to-do of kind 'meeting' whose
-- slot carries clock times. A slot places a to-do on a day.
create table todo (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users on delete cascade,
  kind            text not null default 'task' check (kind in ('task', 'meeting')),
  title           text not null,
  due_on          date not null default current_date,
  category_id     uuid references category on delete set null,
  project_id      uuid references project on delete set null,
  milestone_id    uuid references milestone on delete set null,
  est_hours       numeric check (est_hours is null or est_hours >= 0),
  is_core         boolean not null default false,
  must_this_week  boolean not null default false,
  is_done         boolean not null default false,
  done_at         timestamptz,
  is_cancelled    boolean not null default false,
  sort_order      integer not null default 100,
  note            text,
  created_at      timestamptz not null default now()
);

create trigger todo_placement before insert or update on todo
  for each row execute function fill_placement();

create table todo_slot (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  todo_id        uuid not null references todo on delete cascade,
  planned_on     date not null,
  start_time     time,
  end_time       time,
  planned_hours  numeric check (planned_hours is null or planned_hours >= 0),
  entry_id       uuid references time_entry on delete set null,
  is_cancelled   boolean not null default false,
  sort_order     integer,
  created_at     timestamptz not null default now(),
  check (end_time is null or start_time is null or end_time > start_time)
);

-- ---- CV ----------------------------------------------------------------
create table cv_entry (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users on delete cascade,
  entry_date     date not null default current_date,
  cv_year        integer,
  cv_section     text not null,
  cv_subsection  text,
  title          text not null,
  organisation   text,
  location       text,
  role           text,
  description    text,
  outcome        text,
  metrics        text,
  evidence_url   text,
  student_level  text,
  start_on       date,
  end_on         date,
  status         text not null default 'draft'
                 check (status in ('draft', 'ready', 'added_to_cv', 'archived')),
  source_type    text not null default 'manual'
                 check (source_type in ('manual', 'entry', 'milestone', 'project')),
  entry_id       uuid references time_entry on delete set null,
  milestone_id   uuid references milestone on delete set null,
  project_id     uuid references project on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- ---- indexes -----------------------------------------------------------
create index on time_entry (user_id, started_at);
create index on time_entry (project_id);
create index on time_entry (milestone_id);
create index on milestone (project_id);
create index on project (category_id);
create index on category (area_id);
create index on todo (user_id, due_on);
create index on todo_slot (user_id, planned_on);
create index on todo_slot (todo_id);
create index on cv_entry (user_id, entry_date);

-- ---- row-level security: owner only ------------------------------------
-- Written out per table (not in a loop) so the Supabase SQL editor can see
-- that every table is covered.
alter table area         enable row level security;
alter table area_target  enable row level security;
alter table category     enable row level security;
alter table user_setting enable row level security;
alter table project      enable row level security;
alter table milestone    enable row level security;
alter table time_entry   enable row level security;
alter table todo         enable row level security;
alter table todo_slot    enable row level security;
alter table cv_entry     enable row level security;

create policy owner_all on area         for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on area_target  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on category     for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on user_setting for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on project      for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on milestone    for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on time_entry   for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on todo         for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on todo_slot    for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on cv_entry     for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- reporting view ----------------------------------------------------
-- One row per entry with its whole placement and hours; the dashboard reads
-- this and aggregates in the browser. security_invoker keeps RLS in force.
create view entry_hours with (security_invoker = true) as
select e.id,
       e.started_at,
       (e.started_at at time zone 'UTC')::date as entry_date,
       e.minutes / 60.0 as hours,
       e.is_core,
       e.description,
       a.id  as area_id,      a.label as area_label,  a.domain,
       c.id  as category_id,  c.label as category_label, c.kind as category_kind,
       p.id  as project_id,   p.name  as project_name,
       m.id  as milestone_id, m.title as milestone_title
from time_entry e
join category c on c.id = e.category_id
join area a     on a.id = c.area_id
left join project p   on p.id = e.project_id
left join milestone m on m.id = e.milestone_id;
