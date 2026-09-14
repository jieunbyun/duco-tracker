"""Regression tests for the project-visibility rule.

A project must be visible ONLY to someone with a deliberate relationship to it:

  * its owner (whoever created it), or
  * the contributor on one of its milestones, or
  * a person listed on the project itself, i.e. added under "People in charge".

Anyone else must see nothing — that is the leak this suite exists to catch, and
it is checked against EVERY project-listing function in db.py, so a future
change that drops a filter fails loudly here.

The three paths above are the whole rule; expected_visible() below recomputes
them straight from the seed data as an independent oracle. Widening access (as
membership did) means widening that oracle deliberately and keeping the
no-relationship user seeing nothing — not relaxing the invariant.

Run it directly (no pytest needed):
    python tests/test_project_visibility.py
Or, if you have pytest:
    pytest tests/test_project_visibility.py

When you add a NEW function that returns a list of projects to the UI, add it to
LISTERS below — that is what keeps the "no leak" invariant honest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_supabase  # noqa: E402

db = fake_supabase.load_db()

# ---- users ---------------------------------------------------------------
SUP = "u-supervisor"      # owns most projects (the "authority" account)
STU_A = "u-student-a"     # owns one project, contributes to a shared one
STU_B = "u-student-b"     # no relationship to anything: must see NOTHING
STU_C = "u-student-c"     # owns nothing, contributes nothing, but is LISTED
#                           on one project under "People in charge"

# ---- statuses ------------------------------------------------------------
STATUSES = [{"id": "s-active", "code": "active"},
            {"id": "s-done", "code": "done"}]

# ---- categories ----------------------------------------------------------
C_WORK = "c-work"
C_OTHER = "c-other"

# ---- projects ------------------------------------------------------------
# P_STUDENTA and P_SUP1 share C_WORK on purpose: the supervisor must NOT see the
# student-owned one in that category, and vice versa.
P_SUP1, P_SUP2, P_STUDENTA, P_SHARED = "p-sup1", "p-sup2", "p-studenta", "p-shared"
PROJECTS = [
    {"id": P_SUP1, "name": "Sup One", "owner_id": SUP,
     "status_id": "s-active", "category_id": C_WORK,
     "started_on": "2026-01-01", "due_on": "2026-06-01"},
    {"id": P_SUP2, "name": "Sup Two", "owner_id": SUP,
     "status_id": "s-done", "category_id": C_OTHER,          # not active
     "started_on": "2026-01-01", "due_on": "2026-03-01"},
    {"id": P_STUDENTA, "name": "Student A Own", "owner_id": STU_A,
     "status_id": "s-active", "category_id": C_WORK,
     "started_on": "2026-02-01", "due_on": "2026-07-01"},
    {"id": P_SHARED, "name": "Shared", "owner_id": SUP,
     "status_id": "s-active", "category_id": C_OTHER,
     "started_on": "2026-02-01", "due_on": "2026-08-01"},
]

# ---- milestones (project_id, contributor_id) -----------------------------
MILESTONES = [
    {"id": "m1", "project_id": P_SUP1, "contributor_id": SUP},
    {"id": "m2", "project_id": P_SHARED, "contributor_id": STU_A},
    {"id": "m3", "project_id": P_STUDENTA, "contributor_id": STU_A},
]

# v_project_tracker is an UNSCOPED view: it returns every project. The scoping
# must happen in db.project_tracker(), so we seed the view with all of them.
V_TRACKER = [{"project_id": p["id"], "project_name": p["name"],
              "status": "active", "hours_logged": 1} for p in PROJECTS]

# ---- people listed on a project ("People in charge") ---------------------
# STU_C is listed on the supervisor's project and has no other tie to it: that
# alone must grant visibility. SUP is listed on their own project too, which
# must not change anything (they already own it).
PROJECT_LEADS = [
    {"project_id": P_SUP1, "user_id": STU_C, "is_leader": False,
     "role": "student lead"},
    {"project_id": P_SUP1, "user_id": SUP, "is_leader": True, "role": "PI"},
]

TABLES = {"project": PROJECTS, "project_milestone": MILESTONES,
          "project_lead": PROJECT_LEADS, "v_project_tracker": V_TRACKER}

# ---- wire the fake backend into db --------------------------------------
_CURRENT = {"uid": None}
db.client = lambda: fake_supabase.FakeSupabase(TABLES)
db.my_app_user_id = lambda: _CURRENT["uid"]
db._uid = lambda: _CURRENT["uid"] or ""
db.project_statuses = lambda: STATUSES


def as_user(uid):
    _CURRENT["uid"] = uid


def expected_visible(uid):
    """Independent oracle for the rule, computed straight from the seed data:
    owner of the project, OR contributor on one of its milestones, OR listed
    on it under "People in charge"."""
    owned = {p["id"] for p in PROJECTS if p["owner_id"] == uid}
    contributed = {m["project_id"] for m in MILESTONES
                   if m["contributor_id"] == uid}
    listed = {L["project_id"] for L in PROJECT_LEADS if L["user_id"] == uid}
    return owned | contributed | listed


def _pid(row):
    """Project id from a listing row (some use 'id', tracker uses 'project_id')."""
    return row.get("id") or row.get("project_id")


# Every function that hands a list of projects to the UI. Extend this when you
# add a new one — the invariant test below then covers it automatically.
LISTERS = {
    "my_projects": lambda: db.my_projects(),
    "projects_i_participate_in": lambda: db.projects_i_participate_in(),
    "project_tracker": lambda: db.project_tracker(),
    "active_projects_for_gantt": lambda: db.active_projects_for_gantt(),
}

ALL_USERS = [SUP, STU_A, STU_B, STU_C]


# ==========================================================================
# The core invariant: no listing function ever returns a project the current
# user shouldn't see, for ANY user.
# ==========================================================================
def test_no_listing_function_leaks_for_any_user():
    for uid in ALL_USERS:
        as_user(uid)
        allowed = expected_visible(uid)
        for name, fn in LISTERS.items():
            got = {_pid(r) for r in fn()}
            leaked = got - allowed
            assert not leaked, (
                f"{name} leaked {sorted(leaked)} to {uid}; "
                f"allowed={sorted(allowed)}")


# ==========================================================================
# The exact reported bug: the authority saw a student-owned project.
# ==========================================================================
def test_supervisor_does_not_see_student_owned_project():
    as_user(SUP)
    for name, fn in LISTERS.items():
        ids = {_pid(r) for r in fn()}
        assert P_STUDENTA not in ids, f"{name} exposed the student's project"


def test_student_sees_only_owned_and_contributed():
    as_user(STU_A)
    assert {_pid(r) for r in db.project_tracker()} == {P_STUDENTA, P_SHARED}
    assert {_pid(r) for r in db.my_projects()} == {P_STUDENTA, P_SHARED}


def test_uninvolved_student_sees_nothing():
    as_user(STU_B)
    for name, fn in LISTERS.items():
        assert list(fn()) == [], f"{name} showed projects to an uninvolved user"


# ==========================================================================
# Being listed on a project ("People in charge") grants visibility, on its own
# — no ownership and no milestone needed. This is what people expect when they
# add someone to a project, and it is the ONLY thing membership grants: STU_C
# still sees nothing else, and STU_B (listed nowhere) still sees nothing.
# ==========================================================================
def test_listed_person_sees_the_project_they_are_listed_on():
    as_user(STU_C)
    for name, fn in LISTERS.items():
        assert {_pid(r) for r in fn()} == {P_SUP1}, (
            f"{name} did not show the project STU_C is listed on")


def test_membership_grants_that_project_and_nothing_more():
    as_user(STU_C)
    seen = {_pid(r) for r in db.project_tracker()}
    assert P_SUP2 not in seen and P_STUDENTA not in seen and P_SHARED not in seen


def test_listed_person_counts_as_participant_not_lead_on_the_gantt():
    """STU_C is on the project but does not own it, so the Gantt must file it
    under 'involved', not 'mine' — the owner is still the supervisor."""
    as_user(STU_C)
    rows = {r["id"]: r for r in db.active_projects_for_gantt()}
    assert P_SUP1 in rows, ("the Gantt hid the project STU_C is listed on — "
                            "membership no longer grants visibility")
    assert rows[P_SUP1]["i_participate"] and not rows[P_SUP1]["i_lead"]
    as_user(SUP)
    rows = {r["id"]: r for r in db.active_projects_for_gantt()}
    # SUP is listed on P_SUP1 as well, but owning it must win.
    assert rows[P_SUP1]["i_lead"] and not rows[P_SUP1]["i_participate"]


# ==========================================================================
# The category dropdown must intersect category AND visibility (this was one of
# the leaking paths: it filtered by category only).
# ==========================================================================
def test_category_dropdown_is_scoped_to_visible_projects():
    # C_WORK holds P_SUP1 (sup's) and P_STUDENTA (student's).
    as_user(SUP)
    assert {r["id"] for r in db.projects_for_category(C_WORK)} == {P_SUP1}
    as_user(STU_A)
    assert {r["id"] for r in db.projects_for_category(C_WORK)} == {P_STUDENTA}
    as_user(STU_B)
    assert db.projects_for_category(C_WORK) == []


# ==========================================================================
# Gantt: active-only, and roles derive from the rule (owner=lead, contributor
# but not owner=participant). No "overseeing everyone" rows.
# ==========================================================================
def test_gantt_is_active_only_and_visible_only():
    as_user(SUP)
    ids = {r["id"] for r in db.active_projects_for_gantt()}
    # P_SUP2 is done (excluded); P_STUDENTA not visible (excluded).
    assert ids == {P_SUP1, P_SHARED}


def test_gantt_roles_reflect_the_rule():
    as_user(SUP)
    roles = {r["id"]: r for r in db.active_projects_for_gantt()}
    assert roles[P_SUP1]["i_lead"] and not roles[P_SUP1]["i_participate"]
    assert roles[P_SHARED]["i_lead"]           # supervisor owns the shared one
    as_user(STU_A)
    roles = {r["id"]: r for r in db.active_projects_for_gantt()}
    # student contributes to the shared project but does not own it
    assert roles[P_SHARED]["i_participate"] and not roles[P_SHARED]["i_lead"]
    assert roles[P_STUDENTA]["i_lead"]         # student owns their own project


# ==========================================================================
# Creating a project on the fly (Log tab, Add block, logging a to-do sitting)
# goes through get_or_create_project. Its name lookup is the leak to guard:
# a name match on someone else's project must never hand theirs back.
# ==========================================================================
def test_a_new_project_named_like_someone_elses_is_my_own_and_private():
    import copy
    tables = copy.deepcopy(TABLES)
    real_client = db.client
    db.client = lambda: fake_supabase.FakeSupabase(tables)
    try:
        as_user(STU_B)
        # "Sup One" already exists, owned by the supervisor
        pid, created = db.get_or_create_project(
            "Sup One", STU_B, "private", category_id=C_WORK)
        assert pid != P_SUP1, (
            "typing an existing name handed back someone else's project — "
            "the session would be filed under a project the logger can't see")
        assert created, "a project of my own should have been created"
        row = next(p for p in tables["project"] if p["id"] == pid)
        assert row["owner_id"] == STU_B and row["visibility"] == "private"
        assert row["category_id"] == C_WORK
        # v_project_tracker is an unscoped view; a real one would now include
        # the new project, so the fake must too, or the leak check below
        # would pass trivially for project_tracker
        tables["v_project_tracker"].append(
            {"project_id": pid, "project_name": "Sup One",
             "status": "active", "hours_logged": 0})

        # the creator sees it where the logging dropdowns look for it ...
        assert pid in {_pid(r) for r in db.my_projects()}
        assert pid in {_pid(r) for r in db.project_tracker()}
        assert pid in {r["id"] for r in db.projects_for_category(C_WORK)}
        for uid in (SUP, STU_A, STU_C):
            as_user(uid)
            for name, fn in LISTERS.items():
                assert pid not in {_pid(r) for r in fn()}, (
                    f"{name} leaked {uid}'s view of STU_B's new project")
            assert pid not in {r["id"]
                               for r in db.projects_for_category(C_WORK)}

        # asking again finds my project rather than making a second one
        as_user(STU_B)
        again, created_again = db.get_or_create_project(
            "Sup One", STU_B, "private", category_id=C_WORK)
        assert (again, created_again) == (pid, False)
    finally:
        db.client = real_client


# ==========================================================================
# Signed-out / unresolved user must see nothing, never everything.
# ==========================================================================
def test_signed_out_user_sees_nothing():
    as_user(None)
    for name, fn in LISTERS.items():
        assert list(fn()) == [], f"{name} returned rows for a signed-out user"


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
