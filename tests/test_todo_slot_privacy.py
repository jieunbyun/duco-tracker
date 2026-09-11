"""Regression tests for to-do *sittings* — the Week tab's day board.

A sitting (todo_slot) says what one person is working on and when. That is at
least as private as the to-do it belongs to, so the rule this suite enforces is
blunt:

  * no slot reader ever returns a row belonging to someone else;
  * no slot reader ever returns anything at all to a signed-out user;
  * whole-task progress (todo_logged_hours) never picks up another person's
    session hours, even when a slot row names that session's id — which is the
    subtle leak, because hours are the one thing this app keeps private even
    from the group lead;
  * re-planning a task only ever touches the caller's own rows.

The seed data deliberately puts MINE and THEIRS side by side in every table,
with THEIRS holding the larger, more obviously wrong numbers, so a dropped
user_id filter shows up as a value rather than as an empty list.

Run it directly (no pytest needed):
    python tests/test_todo_slot_privacy.py
Or, if you have pytest:
    pytest tests/test_todo_slot_privacy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_supabase  # noqa: E402

db = fake_supabase.load_db()

ME = "u-me"
THEM = "u-them"

# Saturday-anchored weeks: LAST is the week before THIS.
LAST_FROM, LAST_TO = "2026-07-25", "2026-07-31"
THIS_FROM, THIS_TO = "2026-08-01", "2026-08-07"

T_MINE = "t-mine"            # my task, planned over three days this week
T_MINE_2 = "t-mine-2"        # my task, planned last week only
T_MINE_3 = "t-mine-3"        # my task, whose sitting names THEIR session
T_THEIRS = "t-theirs"        # their task, planned this week

# My own sessions are small; theirs are large, so a leak is unmistakable.
SESSIONS = [
    {"id": "s-mine-1", "user_id": ME, "hours": 2.5},
    {"id": "s-mine-2", "user_id": ME, "hours": 1.5},
    {"id": "s-theirs", "user_id": THEM, "hours": 99},
]


def slot(sid, todo_id, user_id, day, hours=None, session_id=None):
    return {"id": sid, "todo_id": todo_id, "user_id": user_id,
            "planned_on": day, "planned_hours": hours,
            "session_id": session_id, "sort_order": 0}


def seed():
    """A fresh copy of the tables for each test (writes mutate them)."""
    return {
        "todo_slot": [
            slot("sl-1", T_MINE, ME, "2026-08-03", 2, "s-mine-1"),
            slot("sl-2", T_MINE, ME, "2026-08-05", 2),
            slot("sl-3", T_MINE, ME, "2026-08-06", 2),
            slot("sl-last", T_MINE_2, ME, "2026-07-27", 3, "s-mine-2"),
            # theirs, same week, same shape — must never surface for me
            slot("sl-them", T_THEIRS, THEM, "2026-08-03", 8, "s-theirs"),
            # the nasty ones, both sharing MY todo_id so only the user_id
            # filter separates them from my own rows:
            #   - logged, so it must stay out of my progress figure
            #   - OPEN, so a re-plan with no user filter would DELETE it
            slot("sl-cross", T_MINE, THEM, "2026-08-04", 8, "s-theirs"),
            slot("sl-cross-open", T_MINE, THEM, "2026-08-05", 8),
            # my own row pointing at THEIR session id — a stale or forged
            # pointer. The hours lookup must refuse to resolve it.
            slot("sl-forged", T_MINE_3, ME, "2026-08-06", 1, "s-theirs"),
        ],
        "v_session_detail": [dict(s) for s in SESSIONS],
    }


_CURRENT = {"uid": None}


def use(tables, uid):
    db.client = lambda: fake_supabase.FakeSupabase(tables)
    db.my_app_user_id = lambda: uid
    db._uid = lambda: uid or ""
    _CURRENT["uid"] = uid


# Every function that hands sittings (or figures derived from them) to the UI.
# Extend this when you add another — the invariant test then covers it.
READERS = {
    "todo_slots_in_range": lambda: db.todo_slots_in_range(THIS_FROM, THIS_TO),
    "todo_slots_for": lambda: db.todo_slots_for(
        [T_MINE, T_MINE_2, T_MINE_3, T_THEIRS]),
}


# ==========================================================================
# The core invariant: no reader ever hands back someone else's sitting.
# ==========================================================================
def test_no_reader_returns_another_users_sitting():
    tables = seed()
    for uid in (ME, THEM):
        use(tables, uid)
        for name, fn in READERS.items():
            for row in fn():
                assert row["user_id"] == uid, (
                    f"{name} leaked slot {row['id']} "
                    f"(owned by {row['user_id']}) to {uid}")


def test_signed_out_user_gets_nothing():
    tables = seed()
    use(tables, None)
    for name, fn in READERS.items():
        assert fn() == [], f"{name} returned rows for a signed-out user"
    assert db.todo_logged_hours([T_MINE]) == {}


def test_my_board_shows_only_my_sittings_this_week():
    tables = seed()
    use(tables, ME)
    got = {s["id"] for s in db.todo_slots_in_range(THIS_FROM, THIS_TO)}
    assert got == {"sl-1", "sl-2", "sl-3", "sl-forged"}, got


# ==========================================================================
# Hours are the app's most private figure. A slot row naming someone else's
# session must not pull that session's hours into my progress bar.
# ==========================================================================
def test_progress_hours_never_include_another_users_session():
    tables = seed()
    use(tables, ME)
    got = db.todo_logged_hours([T_MINE, T_MINE_2, T_THEIRS])
    # sl-1 (2.5h) is mine; sl-cross names the same task but is THEIR row and
    # points at THEIR 99h session, so it must contribute nothing.
    assert got.get(T_MINE) == 2.5, got
    assert got.get(T_MINE_2) == 1.5, got
    assert T_THEIRS not in got, "their task's hours surfaced in my board"
    assert 99 not in got.values(), "another user's session hours leaked"


def test_a_sitting_pointing_at_someone_elses_session_resolves_to_nothing():
    """sl-forged is MY row naming THEIR session. The hours lookup is scoped to
    me as well, so the pointer simply does not resolve — my task shows no
    hours rather than their 99."""
    tables = seed()
    use(tables, ME)
    got = db.todo_logged_hours([T_MINE_3])
    assert got == {}, f"resolved another user's session hours: {got}"


def test_their_progress_is_their_own():
    tables = seed()
    use(tables, THEM)
    got = db.todo_logged_hours([T_MINE, T_MINE_2, T_THEIRS])
    assert got.get(T_THEIRS) == 99
    # sl-cross is theirs, on my task id — they see it, I do not
    assert got.get(T_MINE) == 99
    assert T_MINE_2 not in got
    assert T_MINE_3 not in got


# ==========================================================================
# Week scoping: a sitting planned in another week is not on this week's board.
# This is what makes a carried-over task arrive UNPLANNED rather than silently
# landing on last week's weekday.
# ==========================================================================
def test_a_sitting_from_another_week_is_not_on_this_board():
    tables = seed()
    use(tables, ME)
    ids = {s["id"] for s in db.todo_slots_in_range(THIS_FROM, THIS_TO)}
    assert "sl-last" not in ids
    ids = {s["id"] for s in db.todo_slots_in_range(LAST_FROM, LAST_TO)}
    assert ids == {"sl-last"}


def test_whole_task_progress_still_counts_other_weeks():
    """The board is week-scoped, but a task's progress is not: hours logged in
    an earlier week must still count towards the task's total."""
    tables = seed()
    use(tables, ME)
    assert db.todo_logged_hours([T_MINE_2]).get(T_MINE_2) == 1.5


# ==========================================================================
# Re-planning writes. set_todo_plan deletes, updates and inserts in one go, so
# it is the one place a missing user_id filter would destroy someone's data
# rather than merely expose it.
# ==========================================================================
def _my_slots(tables, todo_id):
    return sorted([r for r in tables["todo_slot"]
                   if r["todo_id"] == todo_id and r["user_id"] == ME],
                  key=lambda r: r["planned_on"])


def test_replanning_matches_the_days_asked_for():
    tables = seed()
    use(tables, ME)
    db.set_todo_plan(T_MINE, ME, THIS_FROM, THIS_TO,
                     {"2026-08-03": 1, "2026-08-07": 1})
    days = [r["planned_on"] for r in _my_slots(tables, T_MINE)]
    # 08-05 and 08-06 were open and are no longer wanted: gone.
    # 08-03 is LOGGED, so it survives even though it wasn't re-listed.
    assert days == ["2026-08-03", "2026-08-07"], days


def test_replanning_never_drops_or_rewrites_a_logged_sitting():
    tables = seed()
    use(tables, ME)
    db.set_todo_plan(T_MINE, ME, THIS_FROM, THIS_TO, {"2026-08-07": 4})
    logged = [r for r in _my_slots(tables, T_MINE)
              if r["planned_on"] == "2026-08-03"]
    assert logged, "re-planning deleted a sitting that had already been logged"
    assert logged[0]["session_id"] == "s-mine-1"
    assert logged[0]["planned_hours"] == 2, "logged sitting was re-houred"


def test_replanning_leaves_hours_open_when_none_given():
    tables = seed()
    use(tables, ME)
    db.set_todo_plan(T_MINE, ME, THIS_FROM, THIS_TO, {"2026-08-07": None})
    new = [r for r in _my_slots(tables, T_MINE)
           if r["planned_on"] == "2026-08-07"]
    assert new and not new[0].get("planned_hours"), (
        "a day planned with no hours must stay that way")


def test_replanning_my_task_cannot_touch_another_users_rows():
    tables = seed()
    use(tables, ME)
    before = [dict(r) for r in tables["todo_slot"]
              if r["user_id"] == THEM]
    db.set_todo_plan(T_MINE, ME, THIS_FROM, THIS_TO, {})
    after = [dict(r) for r in tables["todo_slot"] if r["user_id"] == THEM]
    assert before == after, (
        "re-planning my task modified another user's sittings — "
        "sl-cross shares my todo_id, so only the user_id filter protects it")


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
