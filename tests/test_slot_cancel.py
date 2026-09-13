"""What happens when ONE planned day of a to-do is cancelled.

A plan is a guess, and the Week tab lets a task be spread over several days.
When one of those days turns out not to be needed, the board drops just that
sitting — the task itself, and every other day of it, stands. The rules this
suite pins down are the ones a user would notice immediately if they broke:

  * the sitting is KEPT, flagged, never deleted — cancelling is a record, not
    an erasure, and it can be undone;
  * for a task spread over several days, the dropped day's planned hours come
    OFF the task's estimate, because what is left to do is what the remaining
    days hold;
  * for a task with a single day, the estimate is UNTOUCHED — dropping its
    only day plans it out of the week, it does not shrink the job to nothing;
  * restoring is the exact inverse, so cancel-then-restore always lands back
    where it started, however many days are dropped in between;
  * a LOGGED sitting cannot be cancelled at all: its hours are already real;
  * and none of it ever reaches across users.

Run it directly (no pytest needed):
    python tests/test_slot_cancel.py
Or, if you have pytest:
    pytest tests/test_slot_cancel.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_supabase  # noqa: E402

db = fake_supabase.load_db()

ME = "u-me"
THEM = "u-them"

WEEK_FROM, WEEK_TO = "2026-08-01", "2026-08-07"

T_SPLIT = "t-split"          # 8 h over four days, 2 h each (one of them logged)
T_ONE = "t-one"              # 2 h on a single day
T_OPEN = "t-open"            # planned over two days with no hours at all
T_NOEST = "t-noest"          # two days, no estimate to subtract from
T_THEIRS = "t-theirs"        # someone else's, same shape


def slot(sid, todo_id, user_id, day, hours=None, session_id=None,
         cancelled=False):
    return {"id": sid, "todo_id": todo_id, "user_id": user_id,
            "planned_on": day, "planned_hours": hours,
            "session_id": session_id, "sort_order": 0,
            "is_cancelled": cancelled}


def seed():
    """A fresh copy of the tables for each test (every test writes)."""
    return {
        "todo_slot": [
            slot("sl-1", T_SPLIT, ME, "2026-08-03", 2),
            slot("sl-2", T_SPLIT, ME, "2026-08-05", 2),
            slot("sl-3", T_SPLIT, ME, "2026-08-06", 2),
            slot("sl-one", T_ONE, ME, "2026-08-04", 2),
            slot("sl-open-1", T_OPEN, ME, "2026-08-03"),
            slot("sl-open-2", T_OPEN, ME, "2026-08-04"),
            slot("sl-noest-1", T_NOEST, ME, "2026-08-03", 2),
            slot("sl-noest-2", T_NOEST, ME, "2026-08-04", 2),
            # logged: its hours are real, so it must refuse to be cancelled
            slot("sl-logged", T_SPLIT, ME, "2026-08-07", 2, "s-mine"),
            # theirs, same shape — cancelling it must be impossible for me
            slot("sl-them", T_THEIRS, THEM, "2026-08-03", 8),
        ],
        "todo": [
            {"id": T_SPLIT, "user_id": ME, "est_hours": 8},
            {"id": T_ONE, "user_id": ME, "est_hours": 2},
            {"id": T_OPEN, "user_id": ME, "est_hours": 4},
            {"id": T_NOEST, "user_id": ME, "est_hours": None},
            {"id": T_THEIRS, "user_id": THEM, "est_hours": 40},
        ],
    }


def use(tables, uid=ME):
    db.client = lambda: fake_supabase.FakeSupabase(tables)
    db.my_app_user_id = lambda: uid
    db._uid = lambda: uid or ""


def est_of(tables, todo_id):
    return next(t["est_hours"] for t in tables["todo"] if t["id"] == todo_id)


def row(tables, slot_id):
    return next((s for s in tables["todo_slot"] if s["id"] == slot_id), None)


# ==========================================================================
# The common case: one day of a several-day task is dropped.
# ==========================================================================
def test_cancelling_one_day_of_a_split_task_subtracts_its_hours():
    tables = seed()
    use(tables)
    left = db.set_slot_cancelled("sl-2", True)
    assert left == 6, f"estimate should drop 8 h -> 6 h, got {left}"
    assert est_of(tables, T_SPLIT) == 6, "the to-do row was not updated"


def test_a_cancelled_sitting_is_kept_not_deleted():
    tables = seed()
    use(tables)
    db.set_slot_cancelled("sl-2", True)
    kept = row(tables, "sl-2")
    assert kept is not None, ("cancelling deleted the sitting instead of "
                              "flagging it")
    assert kept["is_cancelled"] is True
    assert kept["planned_on"] == "2026-08-05", "the day was altered"
    assert kept["planned_hours"] == 2, (
        "the sitting must keep its hours — they are the record of what was "
        "planned, and what to give back on restore")


def test_restoring_puts_the_hours_back():
    tables = seed()
    use(tables)
    db.set_slot_cancelled("sl-2", True)
    back = db.set_slot_cancelled("sl-2", False)
    assert back == 8, f"restore should return the estimate to 8 h, got {back}"
    assert row(tables, "sl-2")["is_cancelled"] is False


def test_cancelling_every_day_in_turn_never_zeroes_the_task():
    """Each cancel subtracts only while other days remain, so the last day
    standing keeps its hours — and undoing them all lands back on 8 h."""
    tables = seed()
    use(tables)
    db.set_slot_session("sl-logged", None)      # so it can be cancelled too
    order = ["sl-1", "sl-2", "sl-3", "sl-logged"]
    for sid in order[:-1]:
        db.set_slot_cancelled(sid, True)
    assert est_of(tables, T_SPLIT) == 2, (
        "three 2 h days off an 8 h task should leave the last day's 2 h")
    last = db.set_slot_cancelled("sl-logged", True)
    assert last == 2, "the final remaining day must not subtract itself away"
    for sid in reversed(order):
        db.set_slot_cancelled(sid, False)
    assert est_of(tables, T_SPLIT) == 8, (
        "cancel-then-restore must be an exact round trip")


# ==========================================================================
# The cases where nothing should move.
# ==========================================================================
def test_cancelling_the_only_day_of_a_task_leaves_the_estimate_alone():
    tables = seed()
    use(tables)
    left = db.set_slot_cancelled("sl-one", True)
    assert left == 2, (
        "a one-sitting task is planned out of the week, not shrunk to "
        f"nothing — estimate should stay 2 h, got {left}")
    assert row(tables, "sl-one")["is_cancelled"] is True


def test_cancelling_a_day_planned_with_no_hours_changes_no_estimate():
    tables = seed()
    use(tables)
    left = db.set_slot_cancelled("sl-open-1", True)
    assert left == 4, f"nothing to subtract, estimate stays 4, got {left}"


def test_an_estimate_smaller_than_the_plan_clamps_at_zero():
    """An estimate can be smaller than the days planned against it — the two
    are edited separately. Subtraction stops at 0 rather than going negative,
    and it stops at a real 0 rather than at "no estimate", so the day's hours
    are still given back when it is restored."""
    tables = seed()
    use(tables)
    db.update_todo(T_SPLIT, {"est_hours": 1})
    assert db.set_slot_cancelled("sl-2", True) == 0, (
        "an estimate must not go negative")
    assert db.set_slot_cancelled("sl-2", False) == 2, (
        "restoring must hand back the day's hours, even when the estimate had "
        "been driven to zero")


def test_a_task_with_no_estimate_survives_a_cancel():
    tables = seed()
    use(tables)
    left = db.set_slot_cancelled("sl-noest-1", True)
    assert left is None, f"there is no estimate to report, got {left}"
    assert row(tables, "sl-noest-1")["is_cancelled"] is True


# ==========================================================================
# Logged work is real work.
# ==========================================================================
def test_a_logged_sitting_refuses_to_be_cancelled():
    tables = seed()
    use(tables)
    try:
        db.set_slot_cancelled("sl-logged", True)
    except ValueError:
        pass
    else:
        raise AssertionError("a logged sitting was cancelled — its hours are "
                             "already on the calendar")
    assert row(tables, "sl-logged")["is_cancelled"] is False
    assert est_of(tables, T_SPLIT) == 8, "the estimate moved anyway"


def test_reopening_a_logged_sitting_makes_it_cancellable():
    tables = seed()
    use(tables)
    db.set_slot_session("sl-logged", None)
    assert db.set_slot_cancelled("sl-logged", True) == 6


# ==========================================================================
# Privacy: the same rule as every other slot writer.
# ==========================================================================
def test_i_cannot_cancel_someone_elses_sitting():
    tables = seed()
    use(tables, ME)
    assert db.set_slot_cancelled("sl-them", True) is None
    assert row(tables, "sl-them")["is_cancelled"] is False, (
        "another person's plan was changed")
    assert est_of(tables, T_THEIRS) == 40, "another person's estimate moved"


def test_a_signed_out_user_cancels_nothing():
    tables = seed()
    use(tables, None)
    assert db.set_slot_cancelled("sl-1", True) is None
    assert row(tables, "sl-1")["is_cancelled"] is False
    assert est_of(tables, T_SPLIT) == 8


# ==========================================================================
# Re-planning: ticking a dropped day again brings that sitting back.
# ==========================================================================
def test_replanning_a_cancelled_day_revives_its_sitting():
    tables = seed()
    use(tables)
    db.set_slot_cancelled("sl-2", True)
    db.set_todo_plan(T_SPLIT, ME, WEEK_FROM, WEEK_TO,
                     {"2026-08-03": 2, "2026-08-05": 3, "2026-08-06": 2})
    revived = row(tables, "sl-2")
    assert revived is not None, ("re-planning the day deleted and re-created "
                                 "the sitting instead of reviving it")
    assert revived["is_cancelled"] is False, (
        "a day that is planned again must not stay struck through")
    assert revived["planned_hours"] == 3, "the new hours were not applied"


def test_replanning_without_a_cancelled_day_drops_it_for_good():
    tables = seed()
    use(tables)
    db.set_slot_cancelled("sl-2", True)
    db.set_todo_plan(T_SPLIT, ME, WEEK_FROM, WEEK_TO,
                     {"2026-08-03": 2, "2026-08-06": 2})
    assert row(tables, "sl-2") is None, (
        "a cancelled day left out of a re-plan should be gone, not lingering")


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
