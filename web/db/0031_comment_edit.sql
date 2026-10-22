-- 0031_comment_edit.sql — you can edit your own comments in the Logbook, at any
-- time. Only the text and links change; an edited comment keeps its date and
-- shows that it was edited. Safe to re-run.
alter table action_comment add column if not exists edited_at timestamptz;

drop policy if exists edit on action_comment;
create policy edit on action_comment for update to authenticated
  using (author_id = auth.uid())
  with check (author_id = auth.uid() and can_see_action(action_id));

create or replace function action_comment_edited() returns trigger
language plpgsql as $$
begin
  if current_setting('app.undoing', true) = 'on' then
    return new; -- Undo puts the comment back exactly as it was
  end if;
  new.action_id := old.action_id;
  new.author_id := old.author_id;
  new.created_at := old.created_at;
  if new.body is distinct from old.body or new.links is distinct from old.links then
    new.edited_at := now();
  else
    new.edited_at := old.edited_at;
  end if;
  return new;
end $$;

drop trigger if exists edited on action_comment;
create trigger edited before update on action_comment
  for each row execute function action_comment_edited();
