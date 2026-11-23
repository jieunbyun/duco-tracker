-- 0062_network.sql — Network: the people you know, in place of the spreadsheet.
--
-- contact              a person: names, where they are, what they work on, how to reach
--                      them, and tags of your own (Industry, Academia…), any number
-- contact_interaction  each time you met or talked: when (if known) and what about
-- opportunity          a scheme or call and its deadline
-- organisation         a body you deal with (people are linked by their institution's name)
--
-- Yours alone: nobody else sees them. Safe to re-run.
create table if not exists contact (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  name         text not null check (btrim(name) <> ''),
  other_name   text,   -- in another script, or as written elsewhere
  alias        text,
  country      text,
  institution  text,
  unit         text,   -- department, team
  title        text,
  email        text,
  keywords     text,
  tags         text[] not null default '{}',
  notes        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (id, user_id)
);
create index if not exists contact_user on contact (user_id, name);

create table if not exists contact_interaction (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  contact_id  uuid not null,
  met_on      date,
  body        text not null check (btrim(body) <> ''),
  created_at  timestamptz not null default now(),
  foreign key (contact_id, user_id) references contact (id, user_id) on delete cascade
);
create index if not exists contact_interaction_of on contact_interaction (contact_id, user_id, met_on desc);

create table if not exists opportunity (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (btrim(name) <> ''),
  deadline    date,
  notes       text,
  done        boolean not null default false,
  created_at  timestamptz not null default now()
);

create table if not exists organisation (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (btrim(name) <> ''),
  notes       text,
  created_at  timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['contact', 'contact_interaction', 'opportunity', 'organisation'] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists owner_all on %I', t);
    execute format('create policy owner_all on %I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
    execute format('grant select, insert, update, delete on table %I to authenticated', t);
  end loop;
  -- undo, for your own changes only (as 0052)
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['contact', 'contact_interaction', 'opportunity', 'organisation'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
