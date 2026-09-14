"""Logging a to-do sitting against a project or milestone that doesn't exist
yet.

The panel behind a card's ✓ offers "+ New project…" (with an optional first
milestone) and "+ New milestone…", as Add block and the Log tab already do.
This suite DRIVES that panel — picks the option, types the name, presses
"Log it — more to do" — against a recording data layer, and pins down:

  * what gets created, in what order, and that the session is then logged
    against the new ids;
  * the privacy rule at the moment of creation: a new project is PRIVATE and
    owned by the person logging, never anyone else;
  * a missing name creates nothing and logs nothing;
  * a life category never offers a project at all;
  * a to-do with no project is filed under the one just made for it, and a
    to-do that already has one is left alone.

Run it directly (no pytest needed):
    python tests/test_log_sitting_new_project.py
Or, if you have pytest:
    pytest tests/test_log_sitting_new_project.py
"""
import datetime as dt
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_streamlit  # noqa: E402
import test_week_renders as W  # noqa: E402  (installs the fake, has fixtures)

st = W.st
tracker = W.tracker

LOG_IT = "Log it — more to do"
WRITES = ("get_or_create_project", "add_milestone", "log_session",
          "set_slot_session", "move_todo_slot", "update_todo",
          "set_todo_done", "set_slot_cancelled", "delete_todo_slot")


def recording_db():
    """W's read-only fake, with every write recorded instead of forbidden."""
    m = W.fake_db()
    m.calls = []

    def rec(name, result=None):
        def _fn(*a, **kw):
            m.calls.append((name, a, kw))
            return result
        return _fn

    for name in WRITES:
        setattr(m, name, rec(name))
    m.get_or_create_project = rec("get_or_create_project", ("p-new", True))
    m.add_milestone = rec("add_milestone",
                          types.SimpleNamespace(data=[{"id": "m-new"}]))
    m.log_session = rec("log_session",
                        types.SimpleNamespace(data=[{"id": "s-new"}]))
    return m


def drive(slot_id, answers, click=None):
    """Open slot_id's panel, answer its widgets, optionally press one button.
    Returns (recording db, everything drawn)."""
    st.log.clear()
    st.session_state.clear()
    st.session_state["wk_panel"] = ("log", slot_id)
    st.answers = dict(answers)
    st.clicked = {click} if click else set()
    fake = recording_db()
    tracker.db = fake

    class PinnedDate(dt.date):
        @classmethod
        def today(cls):
            return W.TODAY

    class PinnedDt(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.combine(W.TODAY, dt.time(12, 0))

    tracker.dt = types.SimpleNamespace(
        date=PinnedDate, datetime=PinnedDt, timedelta=dt.timedelta,
        time=dt.time, timezone=dt.timezone)
    try:
        with fake_streamlit.rendering():
            tracker.view_week(W.ME)
    finally:
        tracker.dt = dt
        st.answers, st.clicked = {}, set()
    out = "\n".join(f"{kind}: {body}" for kind, body in st.log)
    return fake, out


def names(fake):
    return [c[0] for c in fake.calls]


def call(fake, name):
    found = [c for c in fake.calls if c[0] == name]
    assert len(found) == 1, f"expected one {name}() call, got {names(fake)}"
    return found[0]


# ==========================================================================
# A new project, with its first milestone, then the session against both.
# ==========================================================================
def test_a_new_project_and_first_milestone_are_logged_against():
    fake, _ = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Flood app",
                             "lgnewmsp_sl-b": "Beta release"}, LOG_IT)
    _, a, kw = call(fake, "get_or_create_project")
    assert a[0] == "Flood app"
    assert kw.get("category_id") == "c-res", (
        "the new project must land in the category chosen in the panel")
    _, a, _ = call(fake, "add_milestone")
    assert a == ("p-new", "Beta release"), (
        "the first milestone must be created ON the new project")
    _, _, kw = call(fake, "log_session")
    assert kw["project_id"] == "p-new" and kw["milestone_id"] == "m-new", (
        "the session was not logged against what was just created")
    order = names(fake)
    assert (order.index("get_or_create_project") < order.index("add_milestone")
            < order.index("log_session")), f"wrong order: {order}"
    assert call(fake, "set_slot_session")[1] == ("sl-b", "s-new")


def test_a_new_project_is_private_and_owned_by_the_person_logging():
    fake, _ = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Flood app"}, LOG_IT)
    _, a, kw = call(fake, "get_or_create_project")
    assert a[1] == W.ME["id"], (
        "the project must be owned by whoever is logging — the name lookup "
        "is scoped to that owner, which is what stops a same-named project "
        "of someone else's being handed back")
    assert a[2] == "private", "a project made while logging must be private"
    assert "add_milestone" not in names(fake), (
        "no first milestone was named, so none may be created")
    assert call(fake, "log_session")[2]["milestone_id"] is None


def test_the_session_itself_is_logged_as_me():
    fake, _ = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Flood app"}, LOG_IT)
    assert call(fake, "log_session")[2]["user_id"] == W.ME["id"]


# ==========================================================================
# A new milestone on a project that already exists.
# ==========================================================================
def test_a_new_milestone_goes_on_the_chosen_existing_project():
    fake, _ = drive("sl-b", {"lgms_sl-b": tracker.NEW_MILESTONE,
                             "lgnewms_sl-b": "Stakeholder round 2"}, LOG_IT)
    assert "get_or_create_project" not in names(fake), (
        "an existing project was picked; no project may be created")
    assert call(fake, "add_milestone")[1] == ("p-1", "Stakeholder round 2")
    _, _, kw = call(fake, "log_session")
    assert (kw["project_id"], kw["milestone_id"]) == ("p-1", "m-new")


# ==========================================================================
# A missing name writes nothing at all.
# ==========================================================================
def test_a_blank_new_project_name_creates_and_logs_nothing():
    fake, out = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                               "lgnewproj_sl-b": "   ",
                               "lgnewmsp_sl-b": "Beta release"}, LOG_IT)
    assert fake.calls == [], f"a blank name still wrote: {names(fake)}"
    assert "Give the new project a name" in out


def test_a_blank_new_milestone_name_creates_and_logs_nothing():
    fake, out = drive("sl-b", {"lgms_sl-b": tracker.NEW_MILESTONE,
                               "lgnewms_sl-b": ""}, LOG_IT)
    assert fake.calls == [], f"a blank name still wrote: {names(fake)}"
    assert "Give the new milestone a name" in out


def test_merely_choosing_the_option_writes_nothing():
    fake, _ = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Flood app",
                             "lgnewmsp_sl-b": "Beta release"})
    assert fake.calls == [], (
        f"picking + New project… without logging wrote: {names(fake)}")


# ==========================================================================
# Life is never project-tied.
# ==========================================================================
def test_a_life_category_offers_no_new_project():
    fake, _ = drive("sl-b", {"lgcat_sl-b": "Allotment",
                             "lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Should not exist"}, LOG_IT)
    assert "get_or_create_project" not in names(fake), (
        "a life category offered + New project… and created one")
    assert call(fake, "log_session")[2]["project_id"] is None


# ==========================================================================
# Filing the to-do itself.
# ==========================================================================
def test_a_task_with_no_project_is_filed_under_the_new_one():
    fake, _ = drive("sl-d", {"lgproj_sl-d": tracker.NEW_PROJECT,
                             "lgnewproj_sl-d": "Teaching admin"}, LOG_IT)
    assert call(fake, "update_todo")[1] == (
        "t-nohours", {"project_id": "p-new"})


def test_a_task_that_has_a_project_keeps_it():
    fake, _ = drive("sl-b", {"lgproj_sl-b": tracker.NEW_PROJECT,
                             "lgnewproj_sl-b": "Flood app"}, LOG_IT)
    assert "update_todo" not in names(fake), (
        "the to-do was moved off the project it was already filed under")


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
