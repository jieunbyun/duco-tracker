"""Placing a to-do: category -> project -> milestone, the same way every other
piece of work in the app is placed.

Two things are under test here.

The PICKER (work_placement_picker) only reports a choice. It must never write:
browsing to "+ New project…" and changing your mind has to leave the database
untouched, or idly opening a dropdown would litter the Projects tab. Every
create function raises in this suite, so any write during a render fails.

The RESOLVER (resolve_work_placement) does the writing, once, when the form is
submitted — and must refuse cleanly rather than half-create: a new milestone
with no project, a "+ New …" left blank, or the non-selectable Life divider
chosen as if it were a category.

Run it directly (no pytest needed):
    python tests/test_todo_placement.py
Or, if you have pytest:
    pytest tests/test_todo_placement.py
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

ME = "u-me"

CATS = [{"id": "c-res", "code": "research", "label": "Research",
         "domain": "work", "sort_order": 1},
        {"id": "c-teach", "code": "teaching", "label": "Teaching",
         "domain": "work", "sort_order": 2},
        {"id": "c-life", "code": "life", "label": "Allotment",
         "domain": "life", "sort_order": 3}]

PROJECTS = [{"id": "p-1", "name": "Resilience Review", "category_id": "c-res"},
            {"id": "p-2", "name": "MSc Teaching", "category_id": "c-teach"}]

MILESTONES = {"p-1": [{"id": "m-1", "title": "Stakeholder round 1",
                       "status": "open"},
                      {"id": "m-done", "title": "Scoping", "status": "done"}],
              "p-2": []}


def stub_db(created=None):
    """A data layer that reads, and records anything it is asked to create."""
    m = types.SimpleNamespace()
    m.categories = lambda domain=None: [
        c for c in CATS if domain is None or c["domain"] == domain]
    m.projects_for_category = lambda cid: [
        dict(p) for p in PROJECTS if p["category_id"] == cid]
    m.project_milestones = lambda pid: [dict(x) for x in MILESTONES.get(pid, [])]
    m.my_projects = lambda: [dict(p) for p in PROJECTS]
    m.clear_user_caches = lambda: None

    if created is None:
        def _no_writes(name):
            def _fn(*a, **kw):
                raise AssertionError(
                    f"db.{name}() was called while only BROWSING the pickers "
                    f"— nothing may be created until the form is submitted")
            return _fn
        m.get_or_create_project = _no_writes("get_or_create_project")
        m.add_milestone = _no_writes("add_milestone")
    else:
        def _mk_proj(name, owner, vis="private", category_id=None):
            created.append(("project", name, category_id))
            return "p-new", True

        def _mk_ms(pid, title):
            created.append(("milestone", title, pid))
            return types.SimpleNamespace(data=[{"id": "m-new"}])
        m.get_or_create_project = _mk_proj
        m.add_milestone = _mk_ms
    return m


def pick(answers, *, is_lead=True, category_id=None, project_id=None,
         milestone_id=None, created=None):
    """Run the picker with the dropdowns answered as given."""
    st.log.clear()
    st.answers = dict(answers)
    tracker.db = stub_db(created)
    try:
        return tracker.work_placement_picker(
            "tst", is_lead, category_id=category_id, project_id=project_id,
            milestone_id=milestone_id)
    finally:
        st.answers = {}


def drawn():
    """The labels the picker drew, in order."""
    return [body for kind, body in st.log if kind == "selectbox"]


# ==========================================================================
# The cascade: each level appears only once the level above is answered.
# ==========================================================================
def test_only_the_category_is_offered_until_one_is_chosen():
    pick({})
    assert drawn() == ["Category"], (
        "the project list must wait for a category — an unfiltered list of "
        "every project is what this replaced")


def test_choosing_a_category_offers_that_categorys_projects():
    p = pick({"tst_cat": "Research"})
    assert drawn() == ["Category", "Project"]
    assert p["category_id"] == "c-res"


def test_choosing_a_project_offers_its_milestones():
    p = pick({"tst_cat": "Research", "tst_proj": "Resilience Review"})
    assert drawn() == ["Category", "Project", "Milestone (optional)"]
    assert p["project_id"] == "p-1"


def offered(key):
    """The options a dropdown actually put in front of the user."""
    for kind, body in st.log:
        if kind == "options" and body.startswith(f"{key}="):
            return body[len(key) + 1:].split(" | ")
    return []


def test_a_project_from_another_category_is_not_offered():
    pick({"tst_cat": "Research"})
    opts = offered("tst_proj")
    assert "Resilience Review" in opts, opts
    assert "MSc Teaching" not in opts, (
        "the project list is not filtered by category — this is the flat "
        "list of every project that the cascade replaced")


def test_the_milestone_list_is_limited_to_the_chosen_project():
    pick({"tst_cat": "Research", "tst_proj": "Resilience Review"})
    opts = offered("tst_ms")
    assert "Stakeholder round 1" in opts, opts
    assert tracker.NEW_MILESTONE in opts, "no way to create one here"
    assert "Scoping" not in opts, "a finished milestone was offered"


# ==========================================================================
# Life work is personal and never project-tied, and the group divider in the
# category list is a label, not a choice.
# ==========================================================================
def test_a_life_category_offers_no_project():
    p = pick({"tst_cat": "Allotment"})
    assert drawn() == ["Category"]
    assert p["is_life"] and p["project_id"] is None


def test_life_categories_are_hidden_from_everyone_but_the_lead():
    pick({}, is_lead=False)
    opts = offered("tst_cat")
    assert "Research" in opts, opts
    assert "Allotment" not in opts, (
        "a life category was offered to someone who is not the lead — they "
        "are personal and private")
    # the divider only exists when there are life categories to divide off
    assert tracker.LIFE_SEPARATOR not in opts, opts


def test_the_lead_sees_life_categories_below_a_divider():
    pick({}, is_lead=True)
    opts = offered("tst_cat")
    assert tracker.LIFE_SEPARATOR in opts, opts
    assert opts.index("Research") < opts.index(tracker.LIFE_SEPARATOR)         < opts.index("Allotment"), (
        "work first, then the divider, then life — the same grouping as the "
        "Add a time block form")


def test_the_life_divider_is_refused_as_a_category():
    p = pick({"tst_cat": tracker.LIFE_SEPARATOR})
    assert p["is_separator"]
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert err and "divider" in err
    assert (cat, proj, ms) == (None, None, None)


# ==========================================================================
# Pre-selection: a to-do that was placed when it was written must come back
# showing that placement, or editing it would silently re-file the work.
# ==========================================================================
def test_the_pickers_preselect_what_the_todo_already_has():
    pick({}, category_id="c-res", project_id="p-1", milestone_id="m-1")
    chose = dict(b.split("=", 1) for k, b in st.log if k == "selected")
    assert chose["tst_cat"] == "Research"
    assert chose["tst_proj"] == "Resilience Review"
    assert chose["tst_ms"] == "Stakeholder round 1"


def test_a_finished_milestone_still_shows_if_it_is_the_one_in_use():
    """Done milestones are normally hidden. The one already attached must
    still appear, or saving the form would quietly detach it."""
    pick({}, category_id="c-res", project_id="p-1", milestone_id="m-done")
    chose = dict(b.split("=", 1) for k, b in st.log if k == "selected")
    assert chose["tst_ms"] == "Scoping"


# ==========================================================================
# Browsing writes nothing. Every create raises in stub_db() by default.
# ==========================================================================
def test_browsing_to_new_project_creates_nothing():
    p = pick({"tst_cat": "Research", "tst_proj": tracker.NEW_PROJECT,
              "tst_newproj": "Flood Atlas"})
    assert p["project_id"] == "__new__"
    assert p["new_project"] == "Flood Atlas"


def test_browsing_to_new_milestone_creates_nothing():
    p = pick({"tst_cat": "Research", "tst_proj": "Resilience Review",
              "tst_ms": tracker.NEW_MILESTONE, "tst_newms": "First draft"})
    assert p["milestone_id"] == "__new__"
    assert p["new_milestone"] == "First draft"


# ==========================================================================
# The resolver: creates once, on submit, and refuses rather than half-creates.
# ==========================================================================
def test_resolving_creates_the_new_project_in_the_chosen_category():
    made = []
    p = pick({"tst_cat": "Research", "tst_proj": tracker.NEW_PROJECT,
              "tst_newproj": "Flood Atlas"}, created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert not err
    assert (cat, proj) == ("c-res", "p-new")
    assert made == [("project", "Flood Atlas", "c-res")], made


def test_resolving_creates_a_new_project_and_its_first_milestone_together():
    made = []
    p = pick({"tst_cat": "Research", "tst_proj": tracker.NEW_PROJECT,
              "tst_newproj": "Flood Atlas", "tst_newprojms": "First draft"},
             created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert not err and ms == "m-new"
    assert made == [("project", "Flood Atlas", "c-res"),
                    ("milestone", "First draft", "p-new")], made


def test_resolving_creates_a_new_milestone_on_an_existing_project():
    made = []
    p = pick({"tst_cat": "Research", "tst_proj": "Resilience Review",
              "tst_ms": tracker.NEW_MILESTONE, "tst_newms": "Round 2"},
             created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert not err and (proj, ms) == ("p-1", "m-new")
    assert made == [("milestone", "Round 2", "p-1")], made


def test_a_blank_new_project_name_is_refused_and_creates_nothing():
    made = []
    p = pick({"tst_cat": "Research", "tst_proj": tracker.NEW_PROJECT},
             created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert err and "name" in err
    assert made == [], "a nameless project was created anyway"


def test_a_blank_new_milestone_name_is_refused_after_the_project_exists():
    made = []
    p = pick({"tst_cat": "Research", "tst_proj": "Resilience Review",
              "tst_ms": tracker.NEW_MILESTONE}, created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert err and "name" in err
    assert made == []


def test_resolving_an_untouched_picker_places_nothing_and_creates_nothing():
    made = []
    p = pick({}, created=made)
    cat, proj, ms, err = tracker.resolve_work_placement(p, ME)
    assert not err
    assert (cat, proj, ms) == (None, None, None), (
        "a to-do written without placing it must stay unplaced")
    assert made == []


# ==========================================================================
# The New to-do form is a FRAGMENT. It has to be: its pickers cascade, so they
# cannot sit inside st.form, and every widget outside a form reruns the script
# — which for this tab means redrawing the calendar, the board and the charts,
# and re-issuing every query behind them, three times over just to place one
# to-do. Inside a fragment, browsing the dropdowns reruns only the form.
#
# The bug a fragment brings with it is the opposite: a write that reruns only
# the fragment, so the rest of the page never learns anything changed. Adding
# a to-do must therefore ask for a whole-page rerun, and that is asserted here.
# ==========================================================================
WEEK_START = dt.date(2026, 8, 1)


def writing_db(added):
    m = stub_db(created=[])
    m.add_todo = lambda *a, **kw: added.append((a, kw))
    m.clear_user_caches = lambda: None
    return m


def submit_new_todo(answers):
    """Fill the New to-do form in and press Add to-do."""
    added = []
    st.log.clear()
    st.answers = dict(answers)
    st.clicked = {"Add to-do"}
    tracker.db = writing_db(added)
    try:
        with fake_streamlit.rendering():
            tracker.add_todo_form({"id": ME}, True, WEEK_START)
    finally:
        st.answers, st.clicked = {}, set()
    return added


def test_the_new_todo_form_is_isolated_in_a_fragment():
    assert "add_todo_form" in st.fragments, (
        "the New to-do form is not a fragment, so choosing a category "
        "redraws the whole Week tab")


def test_adding_a_todo_reruns_the_WHOLE_page_not_just_the_form():
    added = submit_new_todo({"td_title": "Write the abstract"})
    assert added, "the to-do was not saved"
    assert ("rerun", "app") in st.log, (
        "a fragment-scoped rerun would leave the new to-do invisible: the "
        "board above it is not redrawn")


def test_the_placement_reaches_the_saved_todo():
    added = submit_new_todo({"td_title": "Write the abstract",
                             "td_cat": "Research",
                             "td_proj": "Resilience Review",
                             "td_ms": "Stakeholder round 1"})
    assert added, "the to-do was not saved"
    args, kwargs = added[0]
    assert kwargs.get("category_id") == "c-res", kwargs
    assert args[3] == "p-1", args          # project_id
    assert kwargs.get("milestone_id") == "m-1", kwargs


def test_a_to_do_with_no_title_is_refused_and_nothing_is_saved():
    added = submit_new_todo({"td_title": ""})
    assert added == []
    assert any(k == "error" for k, _ in st.log)


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
