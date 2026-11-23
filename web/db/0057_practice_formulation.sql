-- 0057_practice_formulation.sql — Problem formulation, in Practice: a practice can hold
-- the formulation of a debate, kept with it as one document:
--   { "question": "...",
--     "views":     [{ "id", "name", "objectives": [{ "id", "text", "measure" }], "assumptions": [{ "id", "text" }] }],
--     "conflicts": [{ "id", "a", "b", "why" }],            -- a, b: objective ids
--     "data":      [{ "id", "name", "source", "notes", "tests": [objective or assumption ids] }] }
-- and a session can be spent on it: the skill "formulation". Yours alone, as the
-- practice. Safe to re-run.
alter table practice add column if not exists formulation jsonb
  check (formulation is null or jsonb_typeof(formulation) = 'object');

alter table practice_session drop constraint if exists practice_session_skill_check;
alter table practice_session add constraint practice_session_skill_check
  check (skill in ('reading', 'writing', 'speaking', 'formulation'));
