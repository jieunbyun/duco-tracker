-- 0081_ambitions_in_experiments.sql — your ambitions become subtopics in Experiments, under one theme
-- that is always there (its title yours to change as the theme moves on; it cannot be deleted). Notes on
-- an ambition are that subtopic's notes, added in Experiments or at the side of Pathways. What serves
-- an ambition (the ticks, 0080) now names the subtopic.
--
-- Each ambition you had on Pathways (a goal serving no other goal) is copied in, once per person, in
-- your order and keeping its place in the colours: its title; "outdated" if it was done or retired;
-- its description, its Thoughts (those no longer valid as outdated notes, with why) and its earlier
-- wordings as notes. Arrows straight to an ambition, from an item with no ticks, become ticks; a goal
-- that stepped towards one is ticked for it (and one stepping towards such a goal gets an arrow to it).
-- The old goals stay in the table, marked as copied (ambition_topic_id), and are no longer shown;
-- the goals left are goals like any other.
--
-- Run after 0066, 0068, 0070 and 0080_pw_node_ambition.sql. Safe to re-run.
do $$
begin
  if to_regclass('public.pw_node_ambition') is null then
    raise exception 'Run 0080_pw_node_ambition.sql first';
  end if;
end $$;

-- the theme: one per person, an umbrella topic
alter table exp_topic add column if not exists ambitions boolean not null default false;
create unique index if not exists exp_topic_ambitions_one on exp_topic (user_id) where ambitions;
alter table exp_topic drop constraint if exists exp_topic_ambitions_top;
alter table exp_topic add constraint exp_topic_ambitions_top check (not ambitions or parent_id is null);

-- an old ambition, copied into Experiments
alter table pw_node add column if not exists ambition_topic_id uuid references exp_topic on delete set null;

-- the ticks name subtopics from now on
alter table pw_node_ambition drop constraint if exists pw_node_ambition_ambition_id_fkey;

do $$
declare
  u      uuid;
  theme  uuid;
  sub    uuid;
  a      record;
  x      record;
  k      integer;
  j      integer;
begin
  for u in select distinct user_id from pw_node where kind = 'goal' and ambition_id is null and ambition_topic_id is null loop
    continue when exists (select 1 from exp_topic where user_id = u and ambitions); -- copied already
    insert into exp_topic (user_id, title, tags, ambitions, sort_order)
      values (u, 'Innovation ambitions', array['innovation'], true,
              coalesce((select min(sort_order) from exp_topic where user_id = u and parent_id is null), 10) - 10)
      returning id into theme;

    -- the items with no ticks yet, before any are added here
    create temp table if not exists tickless (id uuid primary key) on commit drop;
    delete from tickless;
    insert into tickless select n.id from pw_node n where n.user_id = u
      and not exists (select 1 from pw_node_ambition t where t.node_id = n.id);

    k := 0;
    for a in select * from pw_node where user_id = u and kind = 'goal' and ambition_id is null and ambition_topic_id is null
             order by ambition_order nulls last, lane_row, created_at loop
      k := k + 10;
      insert into exp_topic (user_id, parent_id, title, tags, outdated, sort_order, created_at)
        values (u, theme, a.title, '{}', a.status <> 'active', k, a.created_at)
        returning id into sub;

      j := 0;
      if btrim(coalesce(a.detail, '')) <> '' then
        insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
          values (u, sub, a.detail, array['innovation'], a.created_at::date, j);
        j := j + 10;
      end if;
      if to_regclass('public.pw_thought') is not null then
        for x in select * from pw_thought where node_id = a.id order by noted_on desc, created_at desc loop
          insert into exp_note (user_id, topic_id, body, tags, outdated, noted_on, sort_order)
            values (u, sub,
                    x.body || case when not x.valid then E'\n— no longer valid'
                                     || coalesce(' since ' || to_char(x.invalid_on, 'FMDD Mon YYYY'), '')
                                     || coalesce(': ' || nullif(btrim(x.why), ''), '') else '' end,
                    array['innovation'], not x.valid, x.noted_on, j);
          j := j + 10;
        end loop;
      end if;
      for x in select * from pw_revision where node_id = a.id order by changed_at desc loop
        insert into exp_note (user_id, topic_id, body, tags, outdated, noted_on, sort_order)
          values (u, sub,
                  'Earlier wording: ' || x.old_title || coalesce(' — ' || nullif(btrim(x.old_detail), ''), '')
                    || coalesce(E'\nChanged because: ' || nullif(btrim(x.reason), ''), ''),
                  array['innovation'], true, x.changed_at::date, j);
        j := j + 10;
      end loop;

      -- arrows straight to it, from an item that had no ticks, become ticks; so does a goal stepping towards it
      insert into pw_node_ambition (user_id, node_id, ambition_id)
        select distinct u, l.from_id, sub from pw_link l join tickless t on t.id = l.from_id
        where l.to_id = a.id
        on conflict do nothing;
      insert into pw_node_ambition (user_id, node_id, ambition_id)
        select u, g.id, sub from pw_node g where g.ambition_id = a.id
        on conflict do nothing;
      update pw_node set ambition_id = null where ambition_id = a.id;

      -- its ticks, onto the subtopic
      update pw_node_ambition set ambition_id = sub where ambition_id = a.id;
      update pw_node set ambition_topic_id = sub where id = a.id;
    end loop;
  end loop;
end $$;

-- a goal still stepping towards another goal (a step towards a step, from before) is an arrow to it now
insert into pw_link (user_id, from_id, to_id)
  select g.user_id, g.id, g.ambition_id from pw_node g
  where g.kind = 'goal' and g.ambition_id is not null and g.ambition_id <> g.id
    and exists (select 1 from exp_topic e where e.user_id = g.user_id and e.ambitions)
  on conflict do nothing;
update pw_node g set ambition_id = null
  where g.ambition_id is not null and exists (select 1 from exp_topic e where e.user_id = g.user_id and e.ambitions);

-- anything still ticked for something that is not a subtopic goes; then the ticks point at subtopics
delete from pw_node_ambition t where not exists (select 1 from exp_topic e where e.id = t.ambition_id);
alter table pw_node_ambition add constraint pw_node_ambition_ambition_id_fkey
  foreign key (ambition_id) references exp_topic on delete cascade;
