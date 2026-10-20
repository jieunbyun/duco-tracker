-- 0011_assets.sql — Pathways stage 2: the information system. Asset cards
-- (algorithms, models, datasets, software, knowledge) with what they take in
-- and give out; assets connect wherever one's output is another's input.
-- The fields mirror a plain "asset card" so the set can later seed a shared
-- group repository.
create table pw_asset (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users on delete cascade,
  name             text not null,
  kind             text not null default 'algorithm'
                   check (kind in ('algorithm', 'model', 'dataset', 'software', 'knowledge', 'other')),
  status           text not null default 'idea' check (status in ('idea', 'prototype', 'validated', 'retired')),
  purpose          text,
  inputs           text[] not null default '{}',
  outputs          text[] not null default '{}',
  owner_node_id    uuid references pw_node on delete set null,   -- a person on the map
  project_node_id  uuid references pw_node on delete set null,   -- the project that produces it
  location         text,                                          -- where it lives: repository, DOI…
  created_at       timestamptz not null default now()
);

create index on pw_asset (user_id);

alter table pw_asset enable row level security;
create policy owner_all on pw_asset for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
