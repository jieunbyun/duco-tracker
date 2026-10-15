-- 0002_seed_taxonomy.sql — the work taxonomy (areas and categories). Run once
-- in the SQL editor AFTER creating your login in the new project
-- (Authentication > Users); it seeds for the only user there.
--
-- Targets start at 0 hours: set your weekly hours per area in the app, under
-- Planning > Allocation > Edit targets and settings. They are kept out of this
-- file because the repository is public.
do $$
declare
  me uuid;
  n  int;
begin
  select count(*), min(id::text)::uuid into n, me from auth.users;
  if n <> 1 then
    raise exception 'expected exactly one user in auth.users, found %', n;
  end if;

  insert into user_setting (user_id) values (me) on conflict do nothing;

  insert into area (user_id, code, label, domain, sort_order) values
    (me, 'RES', 'Research', 'work', 10),
    (me, 'TEA', 'Teaching', 'work', 20),
    (me, 'ADM', 'Admin',    'work', 30),
    (me, 'OUT', 'Outreach', 'work', 40);

  insert into area_target (user_id, area_id, effective_from, weekly_hours, email_weekly_hours)
  select me, a.id, date '2026-01-01', t.weekly, t.email
  from (values ('RES', 0, 0), ('TEA', 0, 0), ('ADM', 0, 0), ('OUT', 0, 0))
         as t(code, weekly, email)
  join area a on a.code = t.code and a.user_id = me;

  insert into category (user_id, area_id, code, label, kind, sort_order)
  select me, a.id, c.code, c.label, c.kind, c.sort_order
  from (values
    -- Research
    ('RES', 'RES_SUP',  'Supervision',     'routine', 10),
    ('RES', 'RES_PLAN', 'Planning',        'routine', 20),
    ('RES', 'RES_MEET', 'Meetings',        'routine', 30),
    ('RES', 'RES_PUB',  'Publications',    'project', 40),
    ('RES', 'RES_PROP', 'Proposals',       'project', 50),
    ('RES', 'RES_TEXT', 'Textbooks',       'project', 60),
    ('RES', 'RES_SOFT', 'Software',        'project', 70),
    ('RES', 'RES_PRES', 'Presentations',   'project', 80),
    ('RES', 'RES_WEB',  'Web publication', 'mixed',   90),
    ('RES', 'RES_MISC', 'Miscellaneous',   'misc',    99),
    -- Teaching
    ('TEA', 'TEA_MEET', 'Meetings',        'routine', 10),
    ('TEA', 'TEA_CPD',  'CPD',             'project', 40),
    ('TEA', 'TEA_MOD',  'Modules',         'project', 50),
    ('TEA', 'TEA_MSC',  'MSc programme',   'project', 60),
    ('TEA', 'TEA_MAIL', 'Email',           'email',   95),
    ('TEA', 'TEA_MISC', 'Miscellaneous',   'misc',    99),
    -- Admin
    ('ADM', 'ADM_MEET', 'Meetings',        'routine', 10),
    ('ADM', 'ADM_GEN',  'General',         'project', 40),
    ('ADM', 'ADM_MAIL', 'Email',           'email',   95),
    ('ADM', 'ADM_MISC', 'Miscellaneous',   'misc',    99),
    -- Outreach
    ('OUT', 'OUT_MEET', 'Meetings',        'routine', 10),
    ('OUT', 'OUT_GEN',  'General',         'project', 40),
    ('OUT', 'OUT_MAIL', 'Email',           'email',   95),
    ('OUT', 'OUT_MISC', 'Miscellaneous',   'misc',    99)
  ) as c(area_code, code, label, kind, sort_order)
  join area a on a.code = c.area_code and a.user_id = me;
end $$;
