-- 0017_pathways_rows.sql — the Pathways rows become Goals & Objectives (was
-- Research), Awards (new), Publications & code/database (was Projects),
-- Teaching, Outreach and Grant Writing. An award is an item of its own, with
-- the same stages as a grant. Items can list contributors from the group, and
-- each member sees a read-only chart of their own items and the goals they
-- lead to — titles, dates and stages only, never your notes, costs or effort.
alter table pw_node drop constraint if exists pw_node_lane_check;
update pw_node set lane = 'goals'        where lane = 'research';
update pw_node set lane = 'publications' where lane = 'projects';
alter table pw_node add constraint pw_node_lane_check
  check (lane in ('goals', 'awards', 'publications', 'teaching', 'outreach', 'grants'));

alter table pw_node drop constraint if exists pw_node_kind_check;
alter table pw_node add constraint pw_node_kind_check
  check (kind in ('goal', 'objective', 'project', 'person', 'gap', 'grant', 'award'));

-- who contributes to an item (you list them; only you see this table)
create table pw_contributor (
  node_id   uuid not null references pw_node on delete cascade,
  user_id   uuid not null references group_member on delete cascade,
  owner_id  uuid not null default auth.uid() references auth.users on delete cascade,
  primary key (node_id, user_id)
);
alter table pw_contributor enable row level security;
create policy owner_all on pw_contributor for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid() and exists (select 1 from pw_node n where n.id = node_id and n.user_id = auth.uid()));

-- ---- what a member sees: their items, and the goals and objectives they lead to ----
create function member_visible_nodes() returns setof uuid
language sql stable security definer set search_path = public as $$
  with recursive mine as (
    select c.node_id as id from pw_contributor c join pw_node n on n.id = c.node_id and n.user_id = c.owner_id
    where c.user_id = auth.uid() and is_group_member()
  ), ahead(id) as (
    -- onward along links, only through goals and objectives, so every goal she
    -- sees is joined to her items by links she sees too
    select id from mine
    union
    select l.to_id from pw_link l join ahead a on l.from_id = a.id
      join pw_node t on t.id = l.to_id and t.kind in ('goal', 'objective')
  )
  select id from ahead
$$;

create function member_map() returns table (
  id uuid, kind text, lane text, title text, start_on date, end_on date, status text,
  grant_stage text, lane_row smallint, mine boolean
)
language sql stable security definer set search_path = public as $$
  select n.id, n.kind, n.lane, coalesce(p.name, n.title),
         coalesce(p.start_on, n.start_on), coalesce(p.end_on, n.end_on),
         case when p.status in ('done', 'dropped') then 'done' else n.status end,
         n.grant_stage, n.lane_row,
         exists (select 1 from pw_contributor c where c.node_id = n.id and c.user_id = auth.uid())
  from pw_node n left join project p on p.id = n.project_id
  where n.id in (select member_visible_nodes())
$$;

create function member_map_links() returns table (id uuid, from_id uuid, to_id uuid)
language sql stable security definer set search_path = public as $$
  select l.id, l.from_id, l.to_id from pw_link l
  where l.from_id in (select member_visible_nodes()) and l.to_id in (select member_visible_nodes())
$$;

do $$
begin
  if to_regprocedure('log_change()') is not null then
    create trigger undo_log after insert or update or delete on pw_contributor
      for each row execute function log_change();
  end if;
end $$;
