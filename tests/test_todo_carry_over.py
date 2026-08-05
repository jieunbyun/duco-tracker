"""Regression tests for which to-dos a week shows.

The rule the Week tab depends on:
  * open to-dos from earlier weeks carry forward into the current week;
  * to-dos completed earlier but ticked off during this week show here too
    (so this week's "done" hours include carried tasks finished this week);
  * CANCELLED to-dos never carry forward. They stay in their own week, where
    the UI strikes them through, and are invisible to every later week.

Run it directly (no pytest needed):
    python tests/test_todo_carry_over.py
Or, if you have pytest:
    pytest tests/test_todo_carry_over.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_supabase  # noqa: E402

db = fake_supabase.load_db()

# Two Saturday-anchored weeks: LAST is the week before THIS.
LAST_FROM, LAST_TO = "2026-07-25", "2026-07-31"
THIS_FROM, THIS_TO = "2026-08-01", "2026-08-07"


def todo(tid, due_on, *, done=False, done_at=None, cancelled=False):
    return {"id": tid, "title": tid, "due_on": due_on, "is_done": done,
            "done_at": done_at, "is_cancelled": cancelled, "sort_order": 0,
            "note": None, "project_id": None, "est_hours": 1,
            "is_important": False}


TODOS = [
    todo("open-this", THIS_FROM),
    todo("cancelled-this", THIS_FROM, cancelled=True),
    todo("open-last", LAST_FROM),                       # carries forward
    todo("cancelled-last", LAST_FROM, cancelled=True),  # must NOT carry
    todo("done-last-week", LAST_FROM, done=True,
         done_at=LAST_FROM + "T10:00:00"),              # stays in its week
    todo("done-this-week", LAST_FROM, done=True,
         done_at=THIS_FROM + "T10:00:00"),              # surfaces here
]

db.client = lambda: fake_supabase.FakeSupabase({"todo": TODOS})


def ids(date_from, date_to):
    return {t["id"] for t in db.todos_in_range(date_from, date_to)}


def test_cancelled_todo_stays_in_its_own_week():
    assert "cancelled-this" in ids(THIS_FROM, THIS_TO)
    assert "cancelled-last" in ids(LAST_FROM, LAST_TO)


def test_cancelled_todo_does_not_carry_forward():
    assert "cancelled-last" not in ids(THIS_FROM, THIS_TO)


def test_open_todo_still_carries_forward():
    assert "open-last" in ids(THIS_FROM, THIS_TO)


def test_carried_task_finished_this_week_shows_here():
    got = ids(THIS_FROM, THIS_TO)
    assert "done-this-week" in got
    assert "done-last-week" not in got


def test_this_weeks_view_is_exactly_what_we_expect():
    assert ids(THIS_FROM, THIS_TO) == {
        "open-this", "cancelled-this", "open-last", "done-this-week"}


# ---- plain-python runner (so `python tests/...` works without pytest) -----
if __name__ == "__main__":
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        except Exception:                       # noqa: BLE001
            failures += 1
            print(f"ERROR {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
