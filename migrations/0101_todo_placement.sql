-- 0101_todo_placement.sql
--
-- Place a to-do the same way every other piece of work in the app is placed:
-- category -> project -> milestone. Until now a to-do carried only a
-- project_id, chosen from a flat list of every project, so the work it
-- belonged to had to be re-chosen from scratch when the sitting was logged.
--
--   * category_id lets a to-do be categorised with no project at all
--     ("Mark lab reports" is Teaching, and belongs to no project).
--   * milestone_id lets it accrue against the milestone it advances.
--
-- Both are OPTIONAL and default to null, so every to-do that exists today is
-- unchanged and still valid — nothing to backfill. They are used to pre-fill
-- the log panel when a sitting is ticked off, so a to-do that was placed when
-- it was written needs no choosing at all when it is logged.
--
-- Deleting a category or milestone must not delete someone's to-do, so both
-- are ON DELETE SET NULL: the to-do survives, simply unplaced.
--
-- A NOTE ON TYPES. A foreign key column must have the same type as the key it
-- points at, and this schema does not use one type throughout: `todo`,
-- `app_user` and `work_session` have uuid keys, while `category` is a small
-- lookup table with a smallint key. Writing `uuid` here fails with
--
--   ERROR: foreign key constraint "todo_category_id_fkey" cannot be
--   implemented — Key columns "category_id" and "id" are of incompatible
--   types: uuid and smallint.
--
-- So each column below takes its type FROM the table it references, read out
-- of the catalog, rather than one being assumed. That makes this migration
-- correct whichever key types your database actually uses.
--
-- Apply this in the Supabase SQL editor BEFORE deploying the app code that
-- uses it, or the app will request columns the database does not have.
-- Re-running it is harmless: every step checks first.

do $$
declare
    cat_type text;
    ms_type  text;
begin
    select format_type(a.atttypid, a.atttypmod)
      into cat_type
      from pg_attribute a
     where a.attrelid = 'public.category'::regclass
       and a.attname  = 'id'
       and a.attnum > 0
       and not a.attisdropped;

    select format_type(a.atttypid, a.atttypmod)
      into ms_type
      from pg_attribute a
     where a.attrelid = 'public.project_milestone'::regclass
       and a.attname  = 'id'
       and a.attnum > 0
       and not a.attisdropped;

    if cat_type is null or ms_type is null then
        raise exception
            'could not read the key types (category=%, project_milestone=%)',
            cat_type, ms_type;
    end if;

    raise notice 'category.id is %, project_milestone.id is %',
        cat_type, ms_type;

    if not exists (select 1 from information_schema.columns
                    where table_schema = 'public'
                      and table_name   = 'todo'
                      and column_name  = 'category_id') then
        execute format(
            'alter table public.todo add column category_id %s '
            'references public.category(id) on delete set null', cat_type);
    end if;

    if not exists (select 1 from information_schema.columns
                    where table_schema = 'public'
                      and table_name   = 'todo'
                      and column_name  = 'milestone_id') then
        execute format(
            'alter table public.todo add column milestone_id %s '
            'references public.project_milestone(id) on delete set null',
            ms_type);
    end if;
end
$$;

create index if not exists todo_category_idx on public.todo (category_id);
create index if not exists todo_milestone_idx on public.todo (milestone_id);

-- No RLS change is needed: these are columns on `todo`, which is already
-- owner-only, and they are read and written through the same policy.

-- Confirm what landed. Expect two rows, both nullable = YES, with the same
-- types the notice above reported.
select column_name, data_type, is_nullable
  from information_schema.columns
 where table_schema = 'public'
   and table_name   = 'todo'
   and column_name in ('category_id', 'milestone_id')
 order by column_name;

-- Existing to-dos that already name a project can be given that project's
-- category in one pass, if you would like them to arrive pre-placed too.
-- Optional, and safe to skip:
--
--   update public.todo t
--      set category_id = p.category_id
--     from public.project p
--    where t.project_id = p.id
--      and t.category_id is null
--      and p.category_id is not null;
