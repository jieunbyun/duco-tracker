-- 01_export_from_old.sql — run in the OLD Supabase project's SQL editor.
-- Read-only. Returns one cell of JSON holding your own rows from the old app:
-- your projects (owned, or ones you logged time / to-dos / CV entries
-- against), their milestones, your milestone plans, time sessions, to-dos,
-- to-do slots and CV entries. Other people's sessions and to-dos are left out.
with me as (
  select id from app_user where role = 'lead' order by created_at limit 1  -- you, as the old app's lead
),
projs as (
  select id from project where owner_id = (select id from me)
  union select project_id from work_session where user_id = (select id from me) and project_id is not null
  union select project_id from todo         where user_id = (select id from me) and project_id is not null
  union select project_id from cv_entry     where user_id = (select id from me) and project_id is not null
)
select json_build_object(
  'me',             (select json_build_object('id', u.id, 'full_name', u.full_name)
                     from app_user u where u.id = (select id from me)),
  'project',        (select json_agg(row_to_json(x)) from (
                       select p.*, s.code as status_code
                       from project p join project_status s on s.id = p.status_id
                       where p.id in (select id from projs)) x),
  'milestone',      (select json_agg(row_to_json(m)) from project_milestone m
                     where m.project_id in (select id from projs)),
  'milestone_plan', (select json_agg(row_to_json(mp)) from milestone_plan mp
                     where mp.owner_id = (select id from me)),
  'work_session',   (select json_agg(row_to_json(w)) from work_session w
                     where w.user_id = (select id from me)),
  'todo',           (select json_agg(row_to_json(t)) from todo t
                     where t.user_id = (select id from me)),
  'todo_slot',      (select json_agg(row_to_json(ts)) from todo_slot ts
                     where ts.user_id = (select id from me)),
  'cv_entry',       (select json_agg(row_to_json(c)) from cv_entry c
                     where c.user_id = (select id from me)),
  'counts',         json_build_object(
                      'projects', (select count(*) from projs),
                      'sessions', (select count(*) from work_session where user_id = (select id from me)),
                      'todos',    (select count(*) from todo where user_id = (select id from me)))
) as export;
