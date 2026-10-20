-- 0015_group.sql — the group: your students (later, collaborators) sign in to
-- the same app and see only what is theirs: their projects, with milestones,
-- and their logbook, where you comment. Everything that was here before stays
-- yours alone (every older table is owner-only and none of that changes).
--
-- group_member         who is in the group, and as what; you are the supervisor
-- group_project        a shared project (a student can have several)
-- group_project_member who is on it
-- group_milestone      its milestones; you and its members can change them
-- logbook_entry        a student's dated record: what they did, results, next,
--                      and links (files stay on the institution's OneDrive)
-- logbook_revision     every earlier version of an edited entry, kept for good
-- logbook_comment      your comments on an entry, and their replies
--
-- To add a student: invite them in Supabase (Authentication › Users › Invite
-- user), then add them by email in the app's Supervision tab.

create table group_member (
  user_id       uuid primary key references auth.users on delete cascade,
  role          text not null check (role in ('supervisor', 'student', 'collaborator')),
  display_name  text not null,
  email         text,
  active        boolean not null default true,
  joined_on     date not null default current_date
);

create table group_project (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  aim         text,
  status      text not null default 'active' check (status in ('active', 'paused', 'done')),
  start_on    date,
  end_on      date,
  created_at  timestamptz not null default now(),
  check (end_on is null or start_on is null or end_on >= start_on)
);

create table group_project_member (
  project_id  uuid not null references group_project on delete cascade,
  user_id     uuid not null references group_member on delete cascade,
  primary key (project_id, user_id)
);

create table group_milestone (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references group_project on delete cascade,
  title       text not null,
  due_on      date,
  done        boolean not null default false,
  done_on     date,
  sort_order  int not null default 0
);

create table logbook_entry (
  id          uuid primary key default gen_random_uuid(),
  author_id   uuid not null default auth.uid() references auth.users on delete cascade,
  project_id  uuid references group_project on delete set null,
  entry_date  date not null default current_date,
  kind        text not null default 'entry' check (kind in ('entry', 'weekly')),
  did         text,      -- weekly: done
  results     text,      -- weekly: blocked on
  next        text,
  links       text[] not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table logbook_revision (
  id         uuid primary key default gen_random_uuid(),
  entry_id   uuid not null references logbook_entry on delete cascade,
  editor_id  uuid default auth.uid(),
  changed_at timestamptz not null default now(),
  old_row    jsonb not null    -- the entry as it was before this edit
);

create table logbook_comment (
  id          uuid primary key default gen_random_uuid(),
  entry_id    uuid not null references logbook_entry on delete cascade,
  author_id   uuid not null default auth.uid() references auth.users on delete cascade,
  body        text not null,
  created_at  timestamptz not null default now()
);

create index on group_project_member (user_id);
create index on group_milestone (project_id, sort_order);
create index on logbook_entry (author_id, entry_date);
create index on logbook_entry (project_id, entry_date);
create index on logbook_revision (entry_id, changed_at);
create index on logbook_comment (entry_id, created_at);

-- a Pathways item can stand for a shared project, as it can for a Planning one
alter table pw_node add column if not exists group_project_id uuid references group_project on delete set null;

-- you: whoever owns the planner (its areas) is the supervisor
insert into group_member (user_id, role, display_name)
select distinct user_id, 'supervisor', 'Supervisor' from area
on conflict (user_id) do nothing;

-- ---- who may see what ------------------------------------------------------------
-- These look past row-level security (security definer), so the policies that
-- use them do not loop back on themselves. Each answers only about the caller.
create function is_supervisor() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from group_member where user_id = auth.uid() and role = 'supervisor' and active)
$$;
create function is_group_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from group_member where user_id = auth.uid() and active)
$$;
create function is_on_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from group_project_member m join group_member g on g.user_id = m.user_id
    where m.project_id = p and m.user_id = auth.uid() and g.active
  )
$$;

alter table group_member         enable row level security;
alter table group_project        enable row level security;
alter table group_project_member enable row level security;
alter table group_milestone      enable row level security;
alter table logbook_entry        enable row level security;
alter table logbook_revision     enable row level security;
alter table logbook_comment      enable row level security;

-- the group's names are visible to its members; only you change them
create policy read  on group_member for select to authenticated using (is_group_member());
create policy write on group_member for all    to authenticated using (is_supervisor()) with check (is_supervisor());

-- projects: you see all; a student sees the ones they are on and may update them
create policy read   on group_project for select to authenticated using (is_supervisor() or is_on_project(id));
create policy add    on group_project for insert to authenticated with check (is_supervisor());
create policy change on group_project for update to authenticated using (is_supervisor() or is_on_project(id))
                                                                with check (is_supervisor() or is_on_project(id));
create policy remove on group_project for delete to authenticated using (is_supervisor());

create policy read  on group_project_member for select to authenticated
  using (is_supervisor() or user_id = auth.uid() or is_on_project(project_id));
create policy write on group_project_member for all to authenticated using (is_supervisor()) with check (is_supervisor());

create policy all_of on group_milestone for all to authenticated
  using (is_supervisor() or is_on_project(project_id)) with check (is_supervisor() or is_on_project(project_id));

-- a logbook is its author's: you read it and comment, but only they write it.
-- An entry can be deleted on the day it is written; after that, edits only,
-- and every edit keeps the version before it.
create policy read   on logbook_entry for select to authenticated using (author_id = auth.uid() or is_supervisor());
create policy add    on logbook_entry for insert to authenticated
  with check (author_id = auth.uid() and is_group_member() and (project_id is null or is_on_project(project_id) or is_supervisor()));
create policy change on logbook_entry for update to authenticated using (author_id = auth.uid())
  with check (author_id = auth.uid() and (project_id is null or is_on_project(project_id) or is_supervisor()));
create policy remove on logbook_entry for delete to authenticated
  using (author_id = auth.uid() and created_at > now() - interval '1 day');

create policy read on logbook_revision for select to authenticated
  using (exists (select 1 from logbook_entry e where e.id = entry_id));

create policy read   on logbook_comment for select to authenticated
  using (exists (select 1 from logbook_entry e where e.id = entry_id));
create policy add    on logbook_comment for insert to authenticated
  with check (author_id = auth.uid() and exists (select 1 from logbook_entry e where e.id = entry_id));
create policy remove on logbook_comment for delete to authenticated using (author_id = auth.uid());

-- ---- edit history ------------------------------------------------------------------
create function keep_entry_history() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- who wrote it and when are fixed (so an old entry cannot be made deletable again)
  new.author_id := old.author_id;
  new.created_at := old.created_at;
  if (old.project_id, old.entry_date, old.kind, old.did, old.results, old.next, old.links)
     is distinct from (new.project_id, new.entry_date, new.kind, new.did, new.results, new.next, new.links) then
    insert into logbook_revision (entry_id, editor_id, old_row) values (old.id, auth.uid(), to_jsonb(old));
    new.updated_at := now();
  end if;
  return new;
end $$;
create trigger logbook_history before update on logbook_entry
  for each row execute function keep_entry_history();

-- ---- adding a student --------------------------------------------------------------
-- After inviting them in Supabase, add them by the email they were invited with.
create function add_group_member(p_email text, p_name text, p_role text default 'student') returns uuid
language plpgsql security definer set search_path = public as $$
declare uid uuid;
begin
  if not is_supervisor() then
    raise exception 'Only the supervisor can add people to the group.';
  end if;
  if p_role not in ('student', 'collaborator') then
    raise exception 'Unknown role %.', p_role;
  end if;
  select id into uid from auth.users where lower(email) = lower(trim(p_email));
  if uid is null then
    raise exception 'No account for % yet. Invite them first in Supabase (Authentication › Users › Invite user).', trim(p_email);
  end if;
  insert into group_member (user_id, role, display_name, email)
  values (uid, p_role, trim(p_name), lower(trim(p_email)))
  on conflict (user_id) do update set display_name = excluded.display_name, role = excluded.role, active = true;
  return uid;
end $$;

-- ---- undo covers these too (not the history, which stays) ----------------------------
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['group_member', 'group_project', 'group_project_member', 'group_milestone',
                             'logbook_entry', 'logbook_comment'] loop
      execute format('create trigger undo_log after insert or update or delete on %I
                        for each row execute function log_change()', t);
    end loop;
  end if;
end $$;
