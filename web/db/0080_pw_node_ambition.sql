-- 0080_pw_node_ambition.sql — an item on Pathways can serve several ambitions (a goal that serves no
-- other goal), not just one: a tick per item and ambition, set in the Ambitions view of Pathways or in
-- the item's editor. Each item's one ambition so far (pw_node.ambition_id, 0075) becomes its first tick,
-- and the column is then left to goals only. Yours alone.
-- Run after 0075_pw_ambition.sql. Safe to re-run.
create table if not exists pw_node_ambition (
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  node_id      uuid not null references pw_node on delete cascade,
  ambition_id  uuid not null references pw_node on delete cascade,
  created_at   timestamptz not null default now(),
  primary key (node_id, ambition_id)
);
create index if not exists pw_node_ambition_ambition on pw_node_ambition (ambition_id);

alter table pw_node_ambition enable row level security;
drop policy if exists owner_all on pw_node_ambition;
create policy owner_all on pw_node_ambition for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table pw_node_ambition to authenticated;

-- each item's ambition so far (through any goal that stepped towards one) becomes a tick
insert into pw_node_ambition (user_id, node_id, ambition_id)
with recursive up (user_id, node_id, cur, depth) as (
  select n.user_id, n.id, n.ambition_id, 0 from pw_node n where n.kind <> 'goal' and n.ambition_id is not null
  union all
  select u.user_id, u.node_id, g.ambition_id, u.depth + 1
  from up u join pw_node g on g.id = u.cur
  where g.ambition_id is not null and u.depth < 20
)
select distinct u.user_id, u.node_id, u.cur
from up u join pw_node a on a.id = u.cur
where a.kind = 'goal' and a.ambition_id is null
on conflict do nothing;
update pw_node set ambition_id = null where kind <> 'goal' and ambition_id is not null;

-- undo, for your own changes only (as 0076)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on pw_node_ambition;
    create trigger undo_log after insert or update on pw_node_ambition
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on pw_node_ambition;
    create trigger undo_log_delete after delete on pw_node_ambition
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
