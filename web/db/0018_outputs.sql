-- 0018_outputs.sql — the information system becomes the group's map of
-- outputs: what has been developed, by whom, when, for which publications, and
-- where its data or code lives, in three categories: inference algorithms;
-- data, models and simulators; and others. Outputs are joined by drawn links.
-- Every member sees the whole map and adds their own outputs; an output can be
-- changed by whoever added it, its contributors, and you.
--
-- Existing assets keep their place: algorithms become inference algorithms,
-- models and datasets become data/models/simulators, the rest others; and
-- wherever one's output matched another's input, that becomes a drawn link.
alter table pw_asset add column if not exists category text not null default 'other'
  check (category in ('inference', 'data_model', 'other'));
alter table pw_asset add column if not exists developed_on date;
update pw_asset set category = case kind when 'algorithm' then 'inference'
                                         when 'model' then 'data_model'
                                         when 'dataset' then 'data_model'
                                         else 'other' end;

create table asset_contributor (
  asset_id  uuid not null references pw_asset on delete cascade,
  user_id   uuid not null references group_member on delete cascade,
  primary key (asset_id, user_id)
);
create table asset_publication (
  asset_id  uuid not null references pw_asset on delete cascade,
  node_id   uuid not null references pw_node on delete cascade,   -- an item in Publications & code/database
  primary key (asset_id, node_id)
);
create table asset_link (
  id       uuid primary key default gen_random_uuid(),
  from_id  uuid not null references pw_asset on delete cascade,
  to_id    uuid not null references pw_asset on delete cascade,
  unique (from_id, to_id),
  check (from_id <> to_id)
);
create index on asset_contributor (user_id);
create index on asset_link (to_id);

insert into asset_link (from_id, to_id)
select distinct a.id, b.id
from pw_asset a, pw_asset b, unnest(a.outputs) o, unnest(b.inputs) i
where a.id <> b.id and lower(trim(o)) = lower(trim(i))
on conflict do nothing;

-- ---- who may see and change outputs ---------------------------------------------------
create function can_edit_asset(a uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from pw_asset where id = a and (user_id = auth.uid() or is_supervisor()))
      or exists (select 1 from asset_contributor c join group_member g on g.user_id = c.user_id
                 where c.asset_id = a and c.user_id = auth.uid() and g.active)
$$;

drop policy if exists owner_all on pw_asset;
create policy read   on pw_asset for select to authenticated using (user_id = auth.uid() or is_group_member());
create policy add    on pw_asset for insert to authenticated with check (user_id = auth.uid());
create policy change on pw_asset for update to authenticated using (can_edit_asset(id)) with check (can_edit_asset(id));
create policy remove on pw_asset for delete to authenticated using (can_edit_asset(id));

alter table asset_contributor enable row level security;
alter table asset_publication enable row level security;
alter table asset_link        enable row level security;
create policy read  on asset_contributor for select to authenticated
  using (is_group_member() or can_edit_asset(asset_id));
create policy write on asset_contributor for all to authenticated
  using (can_edit_asset(asset_id)) with check (can_edit_asset(asset_id));
create policy read  on asset_publication for select to authenticated
  using (is_group_member() or can_edit_asset(asset_id));
create policy write on asset_publication for all to authenticated
  using (can_edit_asset(asset_id)) with check (can_edit_asset(asset_id));
create policy read  on asset_link for select to authenticated
  using (is_group_member() or can_edit_asset(from_id));
create policy write on asset_link for all to authenticated
  using (can_edit_asset(from_id)) with check (can_edit_asset(from_id));

-- the titles of the publications outputs are linked to (your Pathways items
-- stay yours; only these titles are shown to the group)
create function output_publications() returns table (node_id uuid, title text)
language sql stable security definer set search_path = public as $$
  select distinct n.id, coalesce(p.name, n.title)
  from asset_publication ap join pw_node n on n.id = ap.node_id left join project p on p.id = n.project_id
  where is_group_member() or n.user_id = auth.uid()
$$;

do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['asset_contributor', 'asset_publication', 'asset_link'] loop
      execute format('create trigger undo_log after insert or update or delete on %I
                        for each row execute function log_change()', t);
    end loop;
  end if;
end $$;
