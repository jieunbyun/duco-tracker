-- 0019_folders.sql — the app as an index into OneDrive: Planning projects,
-- shared projects and Pathways items can each point to their OneDrive folder,
-- and a reading points to its PDF on OneDrive instead of a copy stored here.
-- Files live on OneDrive; the app keeps only the links.
alter table project       add column if not exists folder_url text;
alter table group_project add column if not exists folder_url text;
alter table pw_node       add column if not exists folder_url text;
alter table reading       add column if not exists pdf_url text;

-- a member's chart shows their items' folders too
drop function if exists member_map();
create function member_map() returns table (
  id uuid, kind text, lane text, title text, start_on date, end_on date, status text,
  grant_stage text, lane_row smallint, mine boolean, folder_url text
)
language sql stable security definer set search_path = public as $$
  select n.id, n.kind, n.lane, coalesce(p.name, n.title),
         coalesce(p.start_on, n.start_on), coalesce(p.end_on, n.end_on),
         case when p.status in ('done', 'dropped') then 'done' else n.status end,
         n.grant_stage, n.lane_row,
         exists (select 1 from pw_contributor c where c.node_id = n.id and c.user_id = auth.uid()),
         coalesce(n.folder_url, p.folder_url)
  from pw_node n left join project p on p.id = n.project_id
  where n.id in (select member_visible_nodes())
$$;
