-- 0010_pathways.sql — the Pathways map: long-term goals, near-term objectives,
-- existing and potential projects, people and knowledge gaps, laid out in
-- lanes over time and linked across lanes.
--
-- pw_node      one item on the map
-- pw_link      a link between two items (feeds into / advances / works on /
--              needs to learn)
-- pw_revision  how a goal's wording changed, and why
-- user_setting.pathway_years   how far ahead the map reaches (adjustable)

create table pw_node (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  kind        text not null check (kind in ('goal', 'objective', 'project', 'person', 'gap')),
  lane        text not null check (lane in ('research', 'teaching', 'outreach', 'supervision')),
  title       text not null,
  detail      text,                       -- description; for a person, their original strengths
  status      text not null default 'active' check (status in ('active', 'done', 'retired')),
  potential   boolean not null default false,   -- a project not started yet
  project_id  uuid references project on delete set null,  -- the real project, once it exists
  reading_id  uuid references reading on delete set null,  -- for a knowledge gap
  start_on    date,
  end_on      date,
  effort_pm   numeric check (effort_pm is null or effort_pm >= 0),  -- person-months it needs
  cost        numeric check (cost is null or cost >= 0),            -- money it needs
  fte         numeric check (fte is null or (fte >= 0 and fte <= 1)), -- a person's share of time
  lane_row    smallint not null default 0,  -- position within its lane on the map
  created_at  timestamptz not null default now(),
  check (end_on is null or start_on is null or end_on >= start_on)
);

create table pw_link (
  id       uuid primary key default gen_random_uuid(),
  user_id  uuid not null default auth.uid() references auth.users on delete cascade,
  from_id  uuid not null references pw_node on delete cascade,
  to_id    uuid not null references pw_node on delete cascade,
  kind     text not null default 'feeds' check (kind in ('feeds', 'advances', 'works_on', 'learns')),
  unique (from_id, to_id),
  check (from_id <> to_id)
);

create table pw_revision (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  node_id     uuid not null references pw_node on delete cascade,
  changed_at  timestamptz not null default now(),
  old_title   text not null,
  old_detail  text,
  reason      text
);

create index on pw_node (user_id, lane);
create index on pw_link (from_id);
create index on pw_link (to_id);
create index on pw_revision (node_id, changed_at);

alter table pw_node     enable row level security;
alter table pw_link     enable row level security;
alter table pw_revision enable row level security;
create policy owner_all on pw_node     for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on pw_link     for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on pw_revision for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

alter table user_setting
  add column if not exists pathway_years smallint not null default 5 check (pathway_years between 1 and 20);
