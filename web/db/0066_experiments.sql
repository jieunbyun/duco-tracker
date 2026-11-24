-- 0066_experiments.sql — Experiments ("Life is experiments"): one place for what were
-- Tips, Failures, Practice and Diary.
--
-- exp_topic  an umbrella topic, or a subtopic under one (parent_id; one level deep),
--            in your own order
-- exp_note   a note under a topic or subtopic, in your own order, with one or more
--            tags (tip, hypothesis, practice, self) and a tick for "outdated"
--
-- Yours alone. Safe to re-run.
--
-- The end of this file copies what you already had in Tips, Failures, Practice and
-- Diary into topics and notes, once per person: someone who already has topics here is
-- left alone. The old tables are not touched, so nothing there is lost; what does not
-- fit a note (mood numbers, ratings, a formulation's diagram) is written out as text.
create table if not exists exp_topic (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  parent_id   uuid,
  title       text not null check (btrim(title) <> ''),
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  unique (id, user_id),
  -- a subtopic only under your own topic, and goes with it
  foreign key (parent_id, user_id) references exp_topic (id, user_id) on delete cascade
);
create index if not exists exp_topic_of on exp_topic (user_id, parent_id, sort_order);

create table if not exists exp_note (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  topic_id    uuid not null,
  body        text not null check (btrim(body) <> ''),
  tags        text[] not null check (cardinality(tags) >= 1 and tags <@ array['tip', 'hypothesis', 'practice', 'self']),
  outdated    boolean not null default false,
  noted_on    date not null default current_date,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  foreign key (topic_id, user_id) references exp_topic (id, user_id) on delete cascade
);
create index if not exists exp_note_of on exp_note (topic_id, user_id, sort_order);

alter table exp_topic enable row level security;
alter table exp_note  enable row level security;
drop policy if exists owner_all on exp_topic;
create policy owner_all on exp_topic for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists owner_all on exp_note;
create policy owner_all on exp_note for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table exp_topic, exp_note to authenticated;

-- undo, for your own changes only (as 0052)
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['exp_topic', 'exp_note'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;

-- ---- copy Tips, Failures, Practice and Diary in ------------------------------------
--   Tips      a topic per category ("Tips" when none), a subtopic per tip; its notes and
--             each checklist item a note                                  tagged Tip
--   Failures  a topic per theme, a subtopic per hypothesis; its test, lessons, dates and
--             each observation or calibration a note                       tagged Hypothesis
--   Practice  one topic, a subtopic per practice; its goal, formulation and each
--             session a note                                              tagged Practice
--   Diary     one topic, a subtopic per month; its reflection and each day a note
--                                                                         tagged Self
do $$
declare
  u    uuid;
  top  uuid;
  sub  uuid;
  n    integer;   -- topic order
  k    integer;   -- subtopic order
  j    integer;   -- note order
  r    record;
  s    record;
  x    record;
  txt  text;
  has_tables boolean := to_regclass('tip') is not null and to_regclass('failure_note') is not null
                        and to_regclass('practice_session') is not null and to_regclass('diary_month') is not null;
begin
  if not has_tables then return; end if;

  for u in
    select user_id from tip union select user_id from failure_theme union select user_id from practice
    union select user_id from diary_day union select user_id from diary_month
  loop
    continue when exists (select 1 from exp_topic where user_id = u);
    n := 0;

    -- Tips
    for r in select distinct coalesce(nullif(btrim(category), ''), 'Tips') as c from tip where user_id = u order by 1 loop
      insert into exp_topic (user_id, title, sort_order) values (u, r.c, n) returning id into top;
      n := n + 10; k := 0;
      for s in select * from tip where user_id = u and coalesce(nullif(btrim(category), ''), 'Tips') = r.c
               order by lower(title) loop
        insert into exp_topic (user_id, parent_id, title, sort_order) values (u, top, s.title, k) returning id into sub;
        k := k + 10; j := 0;
        if btrim(coalesce(s.notes, '')) <> '' then
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, s.notes, array['tip'], s.created_at::date, j);
          j := j + 10;
        end if;
        for x in select e->>'text' as t from jsonb_array_elements(s.items) with ordinality as a(e, i) order by i loop
          continue when btrim(coalesce(x.t, '')) = '';
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, x.t, array['tip'], s.created_at::date, j);
          j := j + 10;
        end loop;
      end loop;
    end loop;

    -- Failures
    for r in select * from failure_theme where user_id = u order by created_at loop
      insert into exp_topic (user_id, title, sort_order) values (u, r.name, n) returning id into top;
      n := n + 10; k := 0;
      for s in select * from failure where user_id = u and theme_id = r.id order by created_on, created_at loop
        insert into exp_topic (user_id, parent_id, title, sort_order) values (u, top, s.hypothesis, k) returning id into sub;
        k := k + 10; j := 0;
        txt := concat_ws(' · ', 'Started ' || to_char(s.created_on, 'FMDD Mon YYYY'),
                         'deadline ' || to_char(s.due_on, 'FMDD Mon YYYY'),
                         'completed ' || to_char(s.done_on, 'FMDD Mon YYYY'));
        insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
          values (u, sub, txt, array['hypothesis'], s.created_on, j);
        j := j + 10;
        if btrim(coalesce(s.test, '')) <> '' then
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, 'Test: ' || s.test, array['hypothesis'], s.created_on, j);
          j := j + 10;
        end if;
        if btrim(coalesce(s.lesson, '')) <> '' then
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, 'Lessons from failure: ' || s.lesson, array['hypothesis'], coalesce(s.done_on, s.created_on), j);
          j := j + 10;
        end if;
        for x in select * from failure_note where user_id = u and failure_id = s.id order by noted_on, created_at loop
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, initcap(x.kind) || ': ' || x.body, array['hypothesis'], x.noted_on, j);
          j := j + 10;
        end loop;
      end loop;
    end loop;

    -- Practice
    if exists (select 1 from practice where user_id = u) then
      insert into exp_topic (user_id, title, sort_order) values (u, 'Practice', n) returning id into top;
      n := n + 10; k := 0;
      for s in select * from practice where user_id = u order by started_on, created_at loop
        insert into exp_topic (user_id, parent_id, title, sort_order) values (u, top, s.title, k) returning id into sub;
        k := k + 10; j := 0;
        txt := concat_ws(E'\n', 'Goal: ' || nullif(btrim(s.goal), ''),
                         concat_ws(' · ', 'Started ' || to_char(s.started_on, 'FMDD Mon YYYY'),
                                   'finished ' || to_char(s.done_on, 'FMDD Mon YYYY')));
        insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
          values (u, sub, txt, array['practice'], s.started_on, j);
        j := j + 10;
        if s.formulation is not null and btrim(coalesce(s.formulation->>'question', '')) <> '' then
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, 'Formulation — question: ' || (s.formulation->>'question'), array['practice'], s.started_on, j);
          j := j + 10;
        end if;
        if s.formulation is not null and jsonb_typeof(s.formulation->'views') = 'array' then
          for x in select v, i from jsonb_array_elements(s.formulation->'views') with ordinality as a(v, i) order by i loop
            txt := concat_ws(E'\n', 'Formulation — view: ' || coalesce(nullif(btrim(x.v->>'name'), ''), 'unnamed'),
                     'Objectives: ' || (select string_agg(o->>'text' || coalesce(' (measure: ' || nullif(btrim(o->>'measure'), '') || ')', ''), '; ')
                                        from jsonb_array_elements(case when jsonb_typeof(x.v->'objectives') = 'array' then x.v->'objectives' else '[]' end) o
                                        where btrim(coalesce(o->>'text', '')) <> ''),
                     'Assumptions: ' || (select string_agg(a->>'text', '; ')
                                         from jsonb_array_elements(case when jsonb_typeof(x.v->'assumptions') = 'array' then x.v->'assumptions' else '[]' end) a
                                         where btrim(coalesce(a->>'text', '')) <> ''));
            insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
              values (u, sub, txt, array['practice'], s.started_on, j);
            j := j + 10;
          end loop;
        end if;
        for x in select * from practice_session where user_id = u and practice_id = s.id order by done_on, created_at loop
          txt := concat_ws(E'\n',
                   initcap(x.skill) || coalesce(' · ' || x.minutes || ' min', ''),
                   'Did: ' || nullif(btrim(x.did), ''),
                   'Went well: ' || nullif(btrim(x.went_well), ''),
                   'To fix: ' || nullif(btrim(x.to_fix), ''),
                   'Next focus: ' || nullif(btrim(x.next_focus), ''),
                   'Ratings: ' || (select string_agg(key || ' ' || value || '/5', ', ' order by key) from jsonb_each_text(x.ratings)));
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, txt, array['practice'], x.done_on, j);
          j := j + 10;
        end loop;
      end loop;
    end if;

    -- Diary
    if exists (select 1 from diary_day where user_id = u) or exists (select 1 from diary_month where user_id = u) then
      insert into exp_topic (user_id, title, sort_order) values (u, 'Diary', n) returning id into top;
      n := n + 10; k := 0;
      for r in select m from (select date_trunc('month', day)::date as m from diary_day where user_id = u
                              union select month from diary_month where user_id = u) a order by m loop
        insert into exp_topic (user_id, parent_id, title, sort_order)
          values (u, top, to_char(r.m, 'FMMonth YYYY'), k) returning id into sub;
        k := k + 10; j := 0;
        for x in select reflection from diary_month where user_id = u and month = r.m and btrim(coalesce(reflection, '')) <> '' loop
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, 'Reflection on the month: ' || x.reflection, array['self'], r.m, j);
          j := j + 10;
        end loop;
        for x in select * from diary_day where user_id = u and date_trunc('month', day)::date = r.m order by day loop
          txt := concat_ws(E'\n',
                   'Mood ' || x.mood || '/10',
                   'Best' || coalesce(' (' || nullif(btrim(x.best_area), '') || ')', '') || case when x.best_star then ' ★' else '' end
                     || ': ' || nullif(btrim(x.best), '') || coalesce(' — why: ' || nullif(btrim(x.best_why), ''), ''),
                   'Worst' || coalesce(' (' || nullif(btrim(x.worst_area), '') || ')', '') || case when x.worst_star then ' ★' else '' end
                     || ': ' || nullif(btrim(x.worst), ''));
          continue when btrim(txt) = '';
          insert into exp_note (user_id, topic_id, body, tags, noted_on, sort_order)
            values (u, sub, txt, array['self'], x.day, j);
          j := j + 10;
        end loop;
      end loop;
    end if;
  end loop;
end $$;
