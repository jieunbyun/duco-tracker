"""Regression tests for the project-visibility rule.

A project must be visible ONLY to its owner or to someone who is the contributor
on one of its milestones. This suite locks that in against every project-listing
function in db.py, so a future change that drops a filter fails loudly here.

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
STU_B = "u-student-b"     # owns nothing, contributes to nothing

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

TABLES = {"project": PROJECTS, "project_milestone": MILESTONES,
          "v_project_tracker": V_TRACKER}

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
    owner of the project OR contributor on one of its milestones."""
    owned = {p["id"] for p in PROJECTS if p["owner_id"] == uid}
    contributed = {m["project_id"] for m in MILESTONES
                   if m["contributor_id"] == uid}
    return owned | contributed


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

ALL_USERS = [SUP, STU_A, STU_B]


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
