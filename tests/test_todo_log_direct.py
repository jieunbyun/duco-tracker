"""Logging a to-do straight into the calendar, without planning it first.

Until now the only way to record time against a to-do was to give it a day
with 📅 first, and only then press ✓ on the card that appeared. For work that
is already done — the hour you just spent on the ethics form — that is a plan
written after the fact, purely to satisfy the UI.

The list's ✓ makes the sitting on the spot and opens the same log panel. What
this suite pins down is that the shortcut is a shortcut and nothing more:

  * ✓ and 📅 both stay, side by side, so planning first is still a choice;
  * the sitting it makes is PROVISIONAL — closing the panel without logging
    removes it again, and so does opening any other panel, so an abandoned
    shortcut never leaves an empty day on the board;
  * once it IS logged it stops being provisional and behaves like any sitting
    that was planned the long way round.

Run it directly (no pytest needed):
    python tests/test_todo_log_direct.py
Or, if you have pytest:
    pytest tests/test_todo_log_direct.py
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

WEEK_START = dt.date(2026, 9, 5)          # Saturday
TODAY = dt.date(2026, 9, 9)               # Wednesday
DAY = {i: (WEEK_START + dt.timedelta(days=i)).isoformat() for i in range(7)}

CATS = [{"id": "c-res", "code": "research", "label": "Research",
         "domain": "work", "sort_order": 1},
        {"id": "c-adm", "code": "admin", "label": "Admin",
         "domain": "work", "sort_order": 2}]

PROJECTS = [{"id": "p-1", "name": "Resilience Review", "category_id": "c-res",
             "high_importance": True, "estimated_hours": 40}]

TODOS = [
    # never planned, and has an estimate: the plain case for the shortcut
    {"id": "t-unplanned", "title": "Ethics form", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": "p-1",
     "category_id": "c-res", "milestone_id": None,
     "est_hours": 1.5, "sort_order": 0, "done_at": None,
     "is_important": False, "is_cancelled": False},
    # never planned, no estimate either: the shortcut must still open
    {"id": "t-noest", "title": "Chase the archive request", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": None,
     "category_id": "c-adm", "milestone_id": None,
     "est_hours": None, "sort_order": 1, "done_at": None,
     "is_important": False, "is_cancelled": False},
    # cancelled: struck through in the list, and offered neither way in
    {"id": "t-cancelled", "title": "Pilot survey", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": None,
     "category_id": None, "milestone_id": None,
     "est_hours": 3, "sort_order": 2, "done_at": None,
     "is_important": False, "is_cancelled": True},
    # already planned onto a day: it is on the board, not in the list
    {"id": "t-planned", "title": "Draft review section 3", "note": None,
     "due_on": DAY[0], "is_done": False, "project_id": "p-1",
     "category_id": "c-res", "milestone_id": None,
     "est_hours": 2, "sort_order": 3, "done_at": None,
     "is_important": False, "is_cancelled": False},
]

# The one sitting that exists before anything is clicked. "sl-prov" is added
# per-render by the fakes below when a test is standing in for the shortcut
# having already been taken.
SLOTS = [
    {"id": "sl-planned", "todo_id": "t-planned", "user_id": "u-me",
     "planned_on": DAY[4], "planned_hours": 2, "session_id": None,
     "sort_order": 0, "is_cancelled": False},
]

# What the shortcut creates: an unlogged sitting on today, carrying the
# to-do's estimate as its planned hours.
PROV_SLOT = {"id": "sl-prov", "todo_id": "t-unplanned", "user_id": "u-me",
             "planned_on": DAY[4], "planned_hours": 1.5, "session_id": None,
             "sort_order": 0, "is_cancelled": False}

# The same sitting after it has been logged — no longer provisional.
PROV_LOGGED = dict(PROV_SLOT, session_id="s-new")

LOGGED_SESSION = {
    "id": "s-new", "session_date": DAY[4], "category_id": "c-res",
    "category_label": "Research", "project_id": "p-1",
    "project_name": "Resilience Review", "hours": 1.5,
    "started_at": DAY[4] + "T09:00:00", "ended_at": DAY[4] + "T10:30:00",
    "is_core": False, "milestone_id": None, "description": "Ethics form"}


class _Res:
    """Stands in for a supabase insert response."""

    def __init__(self, rows):
        self.data = rows


def fake_db(writes, slots, sessions, todos):
    m = types.SimpleNamespace()
    m.sessions_in_range = lambda a, b: [dict(s) for s in sessions]
    m.categories = lambda domain=None: [
        c for c in CATS if domain is None or c["domain"] == domain]
    m.todos_in_range = lambda a, b: [dict(t) for t in todos]
    m.todo_slots_in_range = lambda a, b: [
        dict(s) for s in slots if a <= s["planned_on"] <= b]
    m.todo_logged_hours = lambda ids: {}
    m.my_projects = lambda: [dict(p) for p in PROJECTS]
    m.projects_for_category = lambda cid: [
        dict(p) for p in PROJECTS if p["category_id"] == cid]
    m.project_milestones = lambda pid: [
        {"id": "m-1", "title": "Stakeholder round 1", "status": "open"}]
    m.clear_user_caches = lambda: None

    def add_slot(todo_id, user_id, planned_on, planned_hours=None,
                 sort_order=None):
        writes.append(("add_todo_slot", todo_id, user_id, planned_on,
                       planned_hours, sort_order))
        return _Res([{"id": "sl-prov"}])

    def log_session(**kw):
        writes.append(("log_session", kw))
        return _Res([{"id": "s-new"}])

    m.add_todo_slot = add_slot
    m.log_session = log_session
    for name in ("delete_todo_slot", "set_slot_session", "set_todo_done",
                 "move_todo_slot", "set_slot_cancelled", "set_todo_order",
                 "set_todo_important", "set_todo_cancelled", "delete_todo",
                 "update_todo", "update_session", "set_todo_plan"):
        setattr(m, name, _record(writes, name))
    for name in ("add_todo", "delete_session", "add_milestone",
                 "get_or_create_project", "set_project_importance"):
        setattr(m, name, _forbidden(name))
    return m


def _record(writes, name):
    def _fn(*a, **kw):
        writes.append((name,) + a)
        return None
    return _fn


def _forbidden(name):
    def _fn(*a, **kw):
        raise AssertionError(f"this render called db.{name}(), which it "
                             f"had no business calling")
    return _fn


def only(*todo_ids):
    """Just these to-dos. The fake clicks every button with a given label,
    and ✓ is the board card's glyph as well as the list's, so aiming a click
    at one row means being the only row there is."""
    return [dict(t) for t in TODOS if t["id"] in todo_ids]


def render(panel=None, provisional=None, click=None, answers=None,
           slots=None, sessions=None, todos=None):
    """Render the Week tab once. Returns (output string, writes).

    provisional=<slot id> sets st.session_state.wk_provisional, standing in
    for the shortcut having been taken on a previous run.
    """
    st.log.clear()
    st.session_state.clear()
    st.clicked = {click} if click else set()
    if panel:
        st.session_state["wk_panel"] = panel
    if provisional:
        st.session_state["wk_provisional"] = provisional
    st.answers = dict(answers or {})
    writes = []
    tracker.db = fake_db(writes, slots if slots is not None else SLOTS,
                         sessions if sessions is not None else [],
                         todos if todos is not None else TODOS)

    real_date = dt.date

    class PinnedDate(real_date):
        @classmethod
        def today(cls):
            return TODAY

    class PinnedDt(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.combine(TODAY, dt.time(12, 0))

    tracker.dt = types.SimpleNamespace(
        date=PinnedDate, datetime=PinnedDt, timedelta=dt.timedelta,
        time=dt.time, timezone=dt.timezone)
    try:
        with fake_streamlit.rendering():
            tracker.view_week(ME)
    finally:
        tracker.dt = dt
    out = "\n".join(f"{kind}: {body}" for kind, body in st.log)
    return out, writes


OUT, _ = render()


# ==========================================================================
# Both ways in are offered, and the shortcut never replaces the planner.
# ==========================================================================
def test_the_list_still_offers_to_plan_across_days():
    assert "button: 📅" in OUT, (
        "the day picker must stay — planning first is still a way to work")


def test_the_list_offers_to_log_straight_away():
    assert "button: ✓" in OUT, (
        "an unplanned to-do must offer to be logged without planning first")


def test_the_caption_explains_both_ways_in():
    assert "goes straight to the calendar entry" in OUT, (
        "the list must say what the new button does")
    assert "several days at once" in OUT, (
        "the caption lost its explanation of the day picker")


def test_a_cancelled_todo_is_offered_neither():
    """A dropped to-do offers only ↺ and ✕. Logging one would quietly revive
    work that was deliberately abandoned."""
    out, writes = render(todos=only("t-cancelled"), slots=[], click="✓")
    assert "<s>Pilot survey</s>" in out, "the cancelled row did not render"
    assert "button: ✓" not in out, (
        "a cancelled to-do must not offer to be logged")
    assert not [w for w in writes if w[0] == "add_todo_slot"], (
        "clicking ✓ reached a cancelled to-do and planned a day for it")


def test_every_live_unplanned_todo_gets_the_shortcut():
    out, _ = render(slots=[])      # nothing planned: all four are in the list
    assert out.count("button: ✓") == 3, (
        "three of the four to-dos are alive and unplanned — each needs a ✓, "
        "and the cancelled one needs none")


def test_a_todo_already_on_the_board_is_not_in_the_list():
    """It has a day, so it has a card with its own ✓ — it must not appear in
    the list underneath as well."""
    assert "Draft review section 3" in OUT, "the planned task lost its card"
    assert OUT.count("Draft review section 3") == 1, (
        "a planned task must be on the board only, not in the list too")


# ==========================================================================
# What ✓ actually does: make the sitting, and open the log panel on it.
# ==========================================================================
def test_clicking_it_makes_a_sitting_on_today():
    _, writes = render(todos=only("t-unplanned"), slots=[], click="✓")
    added = [w for w in writes if w[0] == "add_todo_slot"]
    assert len(added) == 1, f"expected one sitting, got {added}"
    _, todo_id, user_id, planned_on, hours, _order = added[0]
    assert todo_id == "t-unplanned"
    assert user_id == "u-me", "the sitting must belong to the signed-in user"
    assert planned_on == DAY[4], (
        f"the sitting must land on today ({DAY[4]}), not {planned_on}")


def test_the_sitting_carries_the_todos_estimate_as_its_hours():
    _, writes = render(todos=only("t-unplanned"), slots=[], click="✓")
    hours = [w for w in writes if w[0] == "add_todo_slot"][0][4]
    assert hours == 1.5, (
        "the estimate is the best guess at how long it took, so it should "
        "pre-fill the hours rather than being thrown away")


def test_it_opens_the_log_panel_on_the_new_sitting():
    render(todos=only("t-unplanned"), slots=[], click="✓")
    assert st.session_state.get("wk_panel") == ("log", "sl-prov"), (
        "clicking ✓ must open the log panel on the sitting it just made")
    assert st.session_state.get("wk_provisional") == "sl-prov", (
        "the new sitting must be marked provisional, or closing the panel "
        "cannot know to remove it again")


def test_a_todo_with_no_estimate_can_still_be_logged():
    """'However long it takes' is a legitimate to-do. The shortcut must open
    for it too, with no hours rather than an invented number."""
    _, writes = render(todos=only("t-noest"), slots=[], click="✓")
    added = [w for w in writes if w[0] == "add_todo_slot"]
    assert len(added) == 1, f"the hourless to-do could not be logged: {added}"
    assert added[0][4] is None, (
        "there is no estimate to carry, so the sitting must be planned with "
        "no hours rather than a made-up number")


# ==========================================================================
# The panel it opens: a log form, not a plan.
# ==========================================================================
PANEL, _ = render(panel=("log", "sl-prov"), provisional="sl-prov",
                  slots=SLOTS + [PROV_SLOT])


def test_the_panel_says_it_is_logging_the_todo():
    assert "**Log this to-do** — Ethics form" in PANEL, (
        "the panel must read as logging the task, not as correcting a "
        "sitting that was planned")


def test_the_panel_says_closing_leaves_it_unplanned():
    assert "leaves the to-do unplanned" in PANEL, (
        "the panel must promise that backing out is free")


def test_the_panel_does_not_offer_to_cancel_a_day_nobody_planned():
    assert "⊘ Cancel this sitting" not in PANEL, (
        "there is no plan to drop: the sitting exists only to carry this "
        "panel, so cancelling it is a meaningless question")


def test_the_panel_still_offers_the_real_log_buttons():
    for label in ("Log it — more to do", "Log it & finish the task",
                  "Finish without logging time", "Close"):
        assert f"submit: {label}" in PANEL, f"the panel lost '{label}'"


def test_the_panel_preselects_the_todos_own_placement():
    assert "selected: lgcat_sl-prov=Research" in PANEL, (
        "the category the to-do was filed under must carry into the log")
    assert "selected: lgproj_sl-prov=Resilience Review" in PANEL, (
        "the project the to-do was filed under must carry into the log")


def test_the_panel_defaults_to_a_block_on_the_calendar():
    assert "selected: lgmode_sl-prov=Start & end" in PANEL, (
        "logging straight from the list should draw a block on the week "
        "calendar by default")
    assert "selected: lgday_sl-prov=" in PANEL, (
        "the day must remain a free choice, not be fixed to today")


# ==========================================================================
# Provisional means provisional: backing out leaves no trace.
# ==========================================================================
def test_closing_the_panel_removes_the_sitting_again():
    _, writes = render(panel=("log", "sl-prov"), provisional="sl-prov",
                       click="Close", slots=SLOTS + [PROV_SLOT])
    assert ("delete_todo_slot", "sl-prov") in writes, (
        "closing without logging must leave the to-do unplanned, not leave "
        "an empty day on the board")


def test_finishing_without_logging_removes_the_sitting_too():
    _, writes = render(panel=("log", "sl-prov"), provisional="sl-prov",
                       click="Finish without logging time",
                       slots=SLOTS + [PROV_SLOT])
    assert ("delete_todo_slot", "sl-prov") in writes, (
        "no time was recorded, so the sitting is an empty day — it goes")
    assert ("set_todo_done", "t-unplanned", True) in writes, (
        "the task itself must still be marked done")


def test_opening_another_panel_abandons_the_sitting():
    """The shortcut was taken, then something else was clicked. The sitting
    it made was never logged, so it must not survive on the board."""
    _, writes = render(panel=("edit", "t-planned"), provisional="sl-prov",
                       slots=SLOTS + [PROV_SLOT])
    assert ("delete_todo_slot", "sl-prov") in writes, (
        "an abandoned provisional sitting must be cleaned up")


def test_a_closed_panel_abandons_the_sitting():
    _, writes = render(provisional="sl-prov", slots=SLOTS + [PROV_SLOT])
    assert ("delete_todo_slot", "sl-prov") in writes, (
        "no panel is open at all, so the sitting has been abandoned")


def test_a_sitting_that_was_logged_is_never_cleaned_up():
    """The key can still be set when the log failed and the user navigated
    away. If the sitting HAS a block, it is real work and must survive."""
    _, writes = render(provisional="sl-prov",
                       slots=SLOTS + [PROV_LOGGED],
                       sessions=[LOGGED_SESSION])
    assert ("delete_todo_slot", "sl-prov") not in writes, (
        "a logged sitting must never be deleted as if it were abandoned — "
        "that would orphan the block on the calendar")


def test_nothing_is_cleaned_up_when_no_shortcut_was_taken():
    """The ordinary case: no provisional key, so the sweep must not fire."""
    _, writes = render()
    assert not [w for w in writes if w[0] == "delete_todo_slot"], (
        "a plain render deleted a sitting")


# ==========================================================================
# Logging it for real: the sitting stops being provisional.
# ==========================================================================
def test_logging_it_writes_the_session_and_keeps_the_sitting():
    _, writes = render(panel=("log", "sl-prov"), provisional="sl-prov",
                       click="Log it — more to do", slots=SLOTS + [PROV_SLOT])
    logged = [w for w in writes if w[0] == "log_session"]
    assert len(logged) == 1, f"expected one session logged, got {logged}"
    kw = logged[0][1]
    assert kw["user_id"] == "u-me"
    assert kw["category_id"] == "c-res", (
        "the to-do's own category must be what gets logged")
    assert kw["project_id"] == "p-1"
    assert kw["started_at"].startswith(DAY[4]), (
        "the block must land on the day chosen in the panel")
    assert ("set_slot_session", "sl-prov", "s-new") in writes, (
        "the sitting must be tied to the block, or the calendar cannot mark "
        "it '✓ from to-do'")
    assert ("delete_todo_slot", "sl-prov") not in writes, (
        "once logged, the sitting is real work and must be kept")


def test_logging_it_clears_the_provisional_mark():
    render(panel=("log", "sl-prov"), provisional="sl-prov",
           click="Log it — more to do", slots=SLOTS + [PROV_SLOT])
    assert "wk_provisional" not in st.session_state, (
        "a logged sitting is an ordinary sitting: leaving the mark behind "
        "would have the next render delete it")


def test_logging_and_finishing_marks_the_task_done():
    _, writes = render(panel=("log", "sl-prov"), provisional="sl-prov",
                       click="Log it & finish the task",
                       slots=SLOTS + [PROV_SLOT])
    assert [w for w in writes if w[0] == "log_session"], "nothing was logged"
    assert ("set_todo_done", "t-unplanned", True) in writes, (
        "'& finish the task' must finish the task")


# ==========================================================================
# An ordinary planned sitting is untouched by any of this.
# ==========================================================================
PLANNED_PANEL, _ = render(panel=("log", "sl-planned"))


def test_a_planned_sitting_still_reads_as_a_sitting():
    assert "**This sitting** — Draft review section 3" in PLANNED_PANEL, (
        "the panel for a genuinely planned day must be unchanged")


def test_a_planned_sitting_can_still_be_cancelled():
    assert "⊘ Cancel this sitting" in PLANNED_PANEL, (
        "dropping a planned day is still a real question and must stay")


# ---- plain-python runner (so `python tests/...` works without pytest) -----
if __name__ == "__main__":
    import traceback
    # Failure messages quote the UI's own glyphs, which a Windows console
    # (cp1252) cannot encode. Without this, a REAL failure dies in the print
    # and is reported as a crash instead of as the assertion it is.
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
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
