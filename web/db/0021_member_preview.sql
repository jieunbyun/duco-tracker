-- 0021_member_preview.sql — "See what they see": you can look at a member's
-- Pathways chart exactly as it appears to them. The member's own functions
-- (member_map, member_map_links) now answer for any member when you ask, and
-- still only for themselves when a member asks.
create function member_visible_nodes_for(p uuid) returns setof uuid
language sql stable security definer set search_path = public as $$
  with recursive mine as (
    select c.node_id as id from pw_contributor c join pw_node n on n.id = c.node_id and n.user_id = c.owner_id
    where c.user_id = p
      and ((p = auth.uid() and is_group_member()) or is_supervisor())
      and exists (select 1 from group_member g where g.user_id = p and g.active)
  ), ahead(id) as (
    select id from mine
    union
    select l.to_id from pw_link l join ahead a on l.from_id = a.id
      join pw_node t on t.id = l.to_id and t.kind in ('goal', 'objective')
  )
  select id from ahead
$$;

create or replace function member_visible_nodes() returns setof uuid
language sql stable security definer set search_path = public as $$
  select member_visible_nodes_for(auth.uid())
$$;

create function member_map_for(p uuid) returns table (
  id uuid, kind text, lane text, title text, start_on date, end_on date, status text,
  grant_stage text, lane_row smallint, mine boolean, folder_url text
)
language sql stable security definer set search_path = public as $$
  select n.id, n.kind, n.lane, coalesce(pr.name, n.title),
         coalesce(pr.start_on, n.start_on), coalesce(pr.end_on, n.end_on),
         case when pr.status in ('done', 'dropped') then 'done' else n.status end,
         n.grant_stage, n.lane_row,
         exists (select 1 from pw_contributor c where c.node_id = n.id and c.user_id = p),
         coalesce(n.folder_url, pr.folder_url)
  from pw_node n left join project pr on pr.id = n.project_id
  where n.id in (select member_visible_nodes_for(p))
$$;

create function member_map_links_for(p uuid) returns table (id uuid, from_id uuid, to_id uuid)
language sql stable security definer set search_path = public as $$
  select l.id, l.from_id, l.to_id from pw_link l
  where l.from_id in (select member_visible_nodes_for(p)) and l.to_id in (select member_visible_nodes_for(p))
$$;
