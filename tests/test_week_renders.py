"""Smoke tests that actually RENDER the Week tab's to-do board.

The other suites check what db.py returns. This one runs view_week() itself
against a fake Streamlit and a fake data layer, so a name that only exists in
one branch — a logged sitting, a task split over three days, a stale sitting in
the past, an untimed session — is executed rather than merely written.

It also checks the board against the privacy rule at the level the user sees:
the page must not print another person's task title or hours anywhere, no
matter what the data layer hands back. Here the fake db deliberately hands back
ONLY the current user's rows (as the real, scoped functions do) and the test
asserts the foreign strings never appear in the rendered output — so if a
future change starts calling an unscoped reader, this fails alongside the
db-level tests.

Run it directly (no pytest needed):
    python tests/test_week_renders.py
Or, if you have pytest:
    pytest tests/test_week_renders.py
"""
import datetime as dt
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_streamlit  # noqa: E402

st = fake_streamlit.install()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import tracker  # noqa: E402

ME = {"id": "u-me", "role": "lead", "full_name": "Me"}

# The week the fixtures live in, anchored on a Saturday so it matches the
# tab's Sat->Fri week. "Today" is pinned to the Wednesday.
WEEK_START = dt.date(2026, 9, 5)          # Saturday
TODAY = dt.date(2026, 9, 9)               # Wednesday
DAY = {i: (WEEK_START + dt.timedelta(days=i)).isoformat() for i in range(7)}

FOREIGN_TITLE = "SOMEONE-ELSES-SECRET-TASK"
FOREIGN_HOURS = "97.5"

CATS = [{"id": "c-res", "code": "research", "label": "Research",
         "domain": "work", "sort_order": 1},
        {"id": "c-adm", "code": "admin", "label": "Admin",
         "domain": "work", "sort_order": 2},
        {"id": "c-life", "code": "life", "label": "Allotment",
         "domain": "life", "sort_order": 3}]

PROJECTS = [{"id": "p-1", "name": "Resilience Review", "category_id": "c-res",
             "high_importance": True, "estimated_hours": 40}]

# Sessions: one timed block from a to-do, one plain block, one UNTIMED
# (minutes only, no ended_at) which must land in the new dashed strip.
SESSIONS = [
    {"id": "s-1", "session_date": DAY[3], "category_id": "c-res",
     "category_label": "Research", "project_id": "p-1",
     "project_name": "Resilience Review", "hours": 2.5,
     "started_at": DAY[3] + "T09:30:00", "ended_at": DAY[3] + "T12:00:00",
     "is_core": True, "milestone_id": None, "description": "draft"},
    {"id": "s-2", "session_date": DAY[2], "category_id": "c-adm",
     "category_label": "Admin", "project_id": None, "project_name": None,
     "hours": 2, "started_at": DAY[2] + "T13:00:00",
     "ended_at": DAY[2] + "T15:00:00", "is_core": False,
     "milestone_id": None, "description": None},
    {"id": "s-untimed", "session_date": DAY[3], "category_id": "c-res",
     "category_label": "Research", "project_id": "p-1",
     "project_name": "Resilience Review", "hours": 0.33,
     "started_at": DAY[3] + "T09:00:00", "ended_at": None,
     "is_core": False, "milestone_id": None, "description": "quick reply"},
]

TODOS = [
    # split over three days: Tue logged, Wed and Thu still open
    {"id": "t-split", "title": "Draft review section 3", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": "p-1",
     "est_hours": 6, "sort_order": 0, "done_at": None,
     "is_important": False, "is_cancelled": False},
    # planned with NO hours at all, on a day that has already passed: the
    # "stale" branch on the card
    {"id": "t-nohours", "title": "Mark lab reports", "note": "20 of them",
     "due_on": DAY[0], "is_done": False, "project_id": None,
     "est_hours": None, "sort_order": 1, "done_at": None,
     "is_important": True, "is_cancelled": False},
    # finished, with its sitting logged
    {"id": "t-done", "title": "Re-run flood scenarios", "note": None,
     "due_on": DAY[0], "is_done": True, "project_id": "p-1",
     "est_hours": 2, "sort_order": 2, "done_at": DAY[2] + "T15:00:00",
     "is_important": False, "is_cancelled": False},
    # never planned: belongs in the list under the board
    {"id": "t-unplanned", "title": "Ethics form", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": "p-1",
     "est_hours": 1.5, "sort_order": 3, "done_at": None,
     "is_important": False, "is_cancelled": False},
    # cancelled: struck through in the list, never on the board
    {"id": "t-cancelled", "title": "Pilot survey", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": None,
     "est_hours": 3, "sort_order": 4, "done_at": None,
     "is_important": False, "is_cancelled": True},
    # alive, but one of its two planned days has been dropped: the estimate
    # below is what is left after that day's 2 h came off
    {"id": "t-dropday", "title": "Rebuild the flood mesh", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": "p-1",
     "est_hours": 2, "sort_order": 5, "done_at": None,
     "is_important": False, "is_cancelled": False},
    # every one of its days dropped: the task itself still stands, so it must
    # come back to the list where it can be given fresh days
    {"id": "t-noday", "title": "Chase the archive request", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": None,
     "est_hours": 1, "sort_order": 6, "done_at": None,
     "is_important": False, "is_cancelled": False},
]

SLOTS = [
    {"id": "sl-a", "todo_id": "t-split", "user_id": "u-me",
     "planned_on": DAY[3], "planned_hours": 2, "session_id": "s-1",
     "sort_order": 0},
    {"id": "sl-b", "todo_id": "t-split", "user_id": "u-me",
     "planned_on": DAY[4], "planned_hours": 2, "session_id": None,
     "sort_order": 1},
    {"id": "sl-c", "todo_id": "t-split", "user_id": "u-me",
     "planned_on": DAY[5], "planned_hours": 2, "session_id": None,
     "sort_order": 2},
    {"id": "sl-d", "todo_id": "t-nohours", "user_id": "u-me",
     "planned_on": DAY[1], "planned_hours": None, "session_id": None,
     "sort_order": 0},
    {"id": "sl-e", "todo_id": "t-done", "user_id": "u-me",
     "planned_on": DAY[2], "planned_hours": 2, "session_id": "s-2",
     "sort_order": 0},
    # a cancelled task keeps its sitting but must never occupy the board
    {"id": "sl-f", "todo_id": "t-cancelled", "user_id": "u-me",
     "planned_on": DAY[4], "planned_hours": 3, "session_id": None,
     "sort_order": 0},
    # one live day and one cancelled day of the same living task: the
    # cancelled day stays on the board struck through, counting nothing
    {"id": "sl-g", "todo_id": "t-dropday", "user_id": "u-me",
     "planned_on": DAY[5], "planned_hours": 2, "session_id": None,
     "sort_order": 0, "is_cancelled": False},
    {"id": "sl-h", "todo_id": "t-dropday", "user_id": "u-me",
     "planned_on": DAY[6], "planned_hours": 2, "session_id": None,
     "sort_order": 1, "is_cancelled": True},
    # the task's one and only day, dropped: no plan left at all
    {"id": "sl-i", "todo_id": "t-noday", "user_id": "u-me",
     "planned_on": DAY[1], "planned_hours": 1, "session_id": None,
     "sort_order": 0, "is_cancelled": True},
]


def fake_db():
    """Stands in for db.py, answering only with the current user's rows —
    exactly as the real, user-scoped functions do."""
    m = types.SimpleNamespace()
    m.sessions_in_range = lambda a, b: [dict(s) for s in SESSIONS]
    m.categories = lambda domain=None: [
        c for c in CATS if domain is None or c["domain"] == domain]
    m.todos_in_range = lambda a, b: [dict(t) for t in TODOS]
    m.todo_slots_in_range = lambda a, b: [
        dict(s) for s in SLOTS if a <= s["planned_on"] <= b]
    m.todo_logged_hours = lambda ids: {"t-split": 2.5, "t-done": 2}
    m.my_projects = lambda: [dict(p) for p in PROJECTS]
    m.projects_for_category = lambda cid: [
        dict(p) for p in PROJECTS if p["category_id"] == cid]
    m.project_milestones = lambda pid: [
        {"id": "m-1", "title": "Stakeholder round 1", "status": "open"}]
    m.clear_user_caches = lambda: None
    # Any write is a bug in a read-only render: nothing is clicked.
    for name in ("set_todo_order", "set_todo_done", "set_todo_important",
                 "set_todo_cancelled", "delete_todo", "update_todo",
                 "add_todo", "move_todo_slot", "delete_todo_slot",
                 "set_slot_cancelled",
                 "set_slot_session", "set_todo_plan", "log_session",
                 "add_milestone", "get_or_create_project",
                 "set_project_importance"):
        setattr(m, name, _forbidden(name))
    return m


def _forbidden(name):
    def _fn(*a, **kw):
        raise AssertionError(f"a plain render called db.{name}() — "
                             f"rendering must not write")
    return _fn


def render_week(panel=None):
    """Render the Week tab once and return everything it drew, as one string.

    Pass panel=("log", slot_id) (or any other wk_panel value) to render with
    that card's panel already open, which is the only way those branches run —
    nothing is ever clicked here."""
    st.log.clear()
    st.session_state.clear()
    if panel:
        st.session_state["wk_panel"] = panel
    tracker.db = fake_db()

    real_date = dt.date

    class PinnedDate(real_date):
        @classmethod
        def today(cls):
            return TODAY

    class PinnedDt(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.combine(TODAY, dt.time(12, 0))

    stub = types.SimpleNamespace(
        date=PinnedDate, datetime=PinnedDt, timedelta=dt.timedelta,
        time=dt.time, timezone=dt.timezone)
    tracker.dt = stub
    try:
        with fake_streamlit.rendering():
            tracker.view_week(ME)
    finally:
        tracker.dt = dt
    return "\n".join(f"{kind}: {body}" for kind, body in st.log)


OUT = render_week()
# the same board with a sitting's panel open: once for a day of a task spread
# over three, once for a task whose only planned day it is
PANEL_SPLIT = render_week(("log", "sl-b"))
PANEL_ONLY = render_week(("log", "sl-g"))


# ==========================================================================
# It runs at all. Before this suite, nothing executed view_week().
# ==========================================================================
def test_the_week_tab_renders_without_error():
    assert OUT, "view_week produced no output at all"
    assert "To-do this week" in OUT


# ==========================================================================
# The board: one task across three days, numbered, with whole-task progress.
# ==========================================================================
def test_a_split_task_shows_a_card_in_each_planned_day():
    assert OUT.count("Draft review section 3") == 3, (
        "a task planned on three days must show a card in each column")
    for marker in ("1/3", "2/3", "3/3"):
        assert marker in OUT, f"sitting marker {marker} missing"


def test_a_split_task_shows_whole_task_progress():
    assert "2.5 h of 6 h" in OUT, "the progress bar's label is wrong or absent"


def test_a_logged_sitting_shows_the_time_it_took():
    assert "✓ 09:30–12:00" in OUT, "a logged sitting must show its times"


# ==========================================================================
# Hours are optional. This is the whole point of the redesign.
# ==========================================================================
def test_a_task_planned_with_no_hours_says_so():
    assert "no hours" in OUT, (
        "a sitting planned without hours must render, not crash or blank")


def test_a_day_with_only_hourless_tasks_counts_them_as_open():
    assert "1 open" in OUT, (
        "the lane footer must count hourless tasks instead of ignoring them")


def test_a_sitting_whose_day_has_passed_is_flagged():
    assert "not logged" in OUT, (
        "an unlogged sitting in the past must be flagged, not shown as normal")


# ==========================================================================
# The calendar above: blocks from to-dos, and untimed work.
# ==========================================================================
def test_a_block_created_from_a_todo_is_marked_as_such():
    assert "✓ from to-do" in OUT


def test_minute_logged_work_appears_in_the_untimed_strip():
    # 0.33 h -> 20 min. Before this change the calendar dropped such rows
    # while still counting their hours in the week totals.
    assert "⊙ 20 min" in OUT, (
        "work logged as minutes vanished from the calendar again")


# ==========================================================================
# Unplanned and cancelled to-dos.
# ==========================================================================
def test_an_unplanned_todo_is_listed_under_the_board():
    assert "Not yet planned" in OUT
    assert "Ethics form" in OUT


# ==========================================================================
# A single dropped day. The task lives on; only that sitting is struck out.
# ==========================================================================
def test_a_cancelled_sitting_stays_on_the_board_struck_through():
    assert "<s>Rebuild the flood mesh</s>" in OUT, (
        "a cancelled day must stay visible, struck through, so it can be "
        "restored")
    assert "⊘ cancelled" in OUT, "the cancelled card lost its label"
    assert OUT.count("Rebuild the flood mesh") == 2, (
        "the task has one live day and one dropped one — both cards show")


def test_a_cancelled_sitting_counts_towards_no_hours():
    assert "1 dropped" in OUT, (
        "a day holding only a cancelled sitting must say so rather than "
        "count its hours as planned")


def test_a_cancelled_sitting_is_not_numbered_among_the_live_ones():
    assert "1/1" not in OUT, (
        "sittings are numbered over the days still in the plan, so a task "
        "with one live day left is not numbered at all")


def test_a_task_whose_every_day_was_dropped_returns_to_the_list():
    assert "<s>Chase the archive request</s>" in OUT, (
        "its dropped day stays on the board as the record")
    assert OUT.count("Chase the archive request") == 2, (
        "a task with no live sitting left has no plan, so it must also be "
        "back under 'Not yet planned' where new days can be chosen")


def test_the_sitting_panel_offers_to_cancel_the_day():
    assert "⊘ Cancel this sitting" in PANEL_SPLIT, (
        "the panel behind ✓ must offer the other answer to 'what became of "
        "this day?'")


def test_the_panel_says_exactly_what_cancelling_takes_off_the_estimate():
    # sl-b is 2 h of a 6 h task planned over three days
    assert "spread over 3 days" in PANEL_SPLIT
    assert "6 h → 4 h" in PANEL_SPLIT, (
        "the subtraction must be spelled out before it happens, not "
        "discovered afterwards")


def test_the_panel_promises_no_subtraction_for_a_one_day_task():
    assert "⊘ Cancel this sitting" in PANEL_ONLY
    assert "only planned day" in PANEL_ONLY, (
        "dropping a task's only day must not claim to shrink its estimate")
    assert "→" not in PANEL_ONLY.split("only planned day")[0][-400:], (
        "no before/after figure belongs in the one-day case")


def test_a_cancelled_todo_is_struck_through_and_not_on_the_board():
    assert "<s>Pilot survey</s>" in OUT, "a cancelled to-do lost its strike"
    # it owns a sitting on DAY[4], which must not put it in a column
    assert OUT.count("Pilot survey") == 1, (
        "a cancelled to-do appeared on the board as well as in the list")


# ==========================================================================
# The privacy rule, at the level the user actually sees. The fake db returns
# only my rows; nothing another person owns may ever reach the page.
# ==========================================================================
def test_no_other_persons_task_or_hours_is_ever_printed():
    assert FOREIGN_TITLE not in OUT
    assert FOREIGN_HOURS not in OUT


def test_rendering_the_page_never_writes():
    """Every db write in fake_db() raises. Reaching here means a plain render
    — no button pressed — changed nothing, so merely opening the tab cannot
    reorder, complete or re-plan anything."""
    render_week()


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
