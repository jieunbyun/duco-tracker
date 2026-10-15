"""Turn the old app's export (01_export_from_old.sql) into SQL for the new project.

    python convert.py <export file> [out_dir]

The export file is whatever the Supabase SQL editor downloaded: JSON
([{"export": {...}}]), CSV (one "export" column), or the bare object.

Only rows that fit the new taxonomy come across:
  * a category is kept if CATEGORY_MAP has it; Innovation, Project
    management / lead, Learning and every life category are deliberately
    absent;
  * a project is kept if its category (or, lacking one, its sessions' most
    common category) is kept;
  * a session or to-do is kept if its project is kept, or failing that its own
    category is; it then sits under its project's category;
  * every CV entry is kept; links to rows that did not come across are cleared.

Old ids are reused so the links between projects, milestones, sessions, to-dos
and CV entries survive. The output holds personal data: out/ is git-ignored.
"""
import csv
import json
import secrets
import sys
from collections import Counter
from pathlib import Path

# old category id -> new category code (from 0002_seed_taxonomy.sql)
CATEGORY_MAP = {
    1: "RES_PLAN",   # planning
    3: "RES_SUP",    # supervision
    4: "RES_PROP",   # proposal
    7: "RES_PRES",   # presentation
    11: "TEA_MOD",   # teaching
    12: "ADM_GEN",   # admin
    13: "ADM_MAIL",  # email check
    9: "ADM_GEN",    # membership
    5: "OUT_GEN",    # broadcasting
    6: "OUT_GEN",    # networking
    8: "OUT_GEN",    # training delivery
    14: "OUT_GEN",   # volunteering
}

PROJECT_STATUS = {
    "planned": "planned", "proposed": "planned", "idea": "planned", "pipeline": "planned",
    "active": "active", "ongoing": "active", "in_progress": "active", "open": "active",
    "paused": "paused", "on_hold": "paused", "hold": "paused", "dormant": "paused",
    "done": "done", "completed": "done", "complete": "done", "closed": "done", "finished": "done",
    "cancelled": "dropped", "canceled": "dropped", "dropped": "dropped", "abandoned": "dropped",
    "archived": "done",
}
MILESTONE_STATUS = {"planned": "planned", "in_progress": "active", "blocked": "active", "done": "done"}

ROWS_PER_FILE = 800


def new_code(old_id):
    return CATEGORY_MAP.get(old_id)


def load_export(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if path.lower().endswith(".csv"):
        csv.field_size_limit(1 << 30)
        row = next(csv.DictReader(text.splitlines(keepends=True)))
        data = json.loads(row.get("export") or next(iter(row.values())))
    else:
        data = json.loads(text)
    if isinstance(data, list):
        data = data[0]
    if "export" in data and isinstance(data["export"], (dict, str)):
        data = data["export"]
        if isinstance(data, str):
            data = json.loads(data)
    return {k: (v or []) if k not in ("me", "counts") else v for k, v in data.items()}


def dated_range(start, end):
    """Drop an end date that falls before its start (the new schema forbids it)."""
    if start and end and end < start:
        return start, None
    return start, end


def project_notes(p):
    parts = [(h, p.get(k)) for h, k in (("Purpose", "purpose"),
                                        ("Final outcomes", "final_outcomes"),
                                        ("Stakeholders", "stakeholders"),
                                        ("Risks", "risks"))]
    return "\n\n".join(f"{h}: {v.strip()}" for h, v in parts if v and v.strip()) or None


def milestone_notes(m):
    parts = [m.get("detail")]
    if m.get("hypothesis"):
        parts.append(f"Hypothesis: {m['hypothesis']}")
    if m.get("success_measure"):
        parts.append(f"Success measure: {m['success_measure']}")
    return "\n\n".join(p.strip() for p in parts if p and p.strip()) or None


def convert(ex):
    report = Counter()
    sessions = ex["work_session"]

    # ---- projects: own category, else the most common mapped session category
    by_proj = {}
    for s in sessions:
        code = new_code(s.get("category_id"))
        if s.get("project_id") and code:
            by_proj.setdefault(s["project_id"], Counter())[code] += 1
    projects, proj_code = [], {}
    unknown_status = Counter()
    for p in ex["project"]:
        code = new_code(p.get("category_id"))
        if code is None and p.get("category_id") is None and p["id"] in by_proj:
            code = by_proj[p["id"]].most_common(1)[0][0]
        if code is None:
            report["projects dropped (category not kept)"] += 1
            continue
        status = PROJECT_STATUS.get((p.get("status_code") or "").lower())
        if status is None:
            unknown_status[p.get("status_code")] += 1
            status = "active"
        start, end = dated_range(p.get("started_on"), p.get("due_on"))
        proj_code[p["id"]] = code
        projects.append({
            "id": p["id"], "category_code": code, "name": p["name"], "status": status,
            "start_on": start, "end_on": end, "planned_hours": p.get("estimated_hours"),
            "is_important": bool(p.get("high_importance")), "notes": project_notes(p),
            "created_at": p.get("created_at"),
        })
    report["projects kept"] = len(projects)
    for code, n in unknown_status.items():
        report[f"projects with unrecognised status {code!r} -> active"] = n

    # ---- milestones of kept projects, with your private planned hours
    plan_hours = {mp["milestone_id"]: mp.get("planned_hours") for mp in ex["milestone_plan"]}
    milestones, kept_ms = [], set()
    for m in ex["milestone"]:
        if m["project_id"] not in proj_code:
            continue
        start, due = dated_range(m.get("start_on"), m.get("due_on"))
        kept_ms.add(m["id"])
        milestones.append({
            "id": m["id"], "project_id": m["project_id"], "title": m["title"],
            "status": MILESTONE_STATUS.get(m.get("status"), "planned"),
            "start_on": start, "due_on": due, "planned_hours": plan_hours.get(m["id"]),
            "hard_deadline": bool(m.get("hard_deadline")), "sort_order": m.get("sort_order") or 100,
            "notes": milestone_notes(m), "created_at": m.get("created_at"),
        })
    report["milestones kept"] = len(milestones)

    def placement(row):
        """(category_code, project_id, milestone_id) or None when not kept."""
        pid = row.get("project_id") if row.get("project_id") in proj_code else None
        mid = row.get("milestone_id") if row.get("milestone_id") in kept_ms else None
        if mid and not pid:
            pid = next(m["project_id"] for m in milestones if m["id"] == mid)
        code = proj_code[pid] if pid else new_code(row.get("category_id"))
        return (code, pid, mid) if code else None

    # ---- sessions
    entries, kept_entries = [], set()
    for s in sessions:
        place = placement(s)
        if place is None:
            report["sessions dropped (category not kept)"] += 1
            continue
        mins = s.get("manual_minutes")
        if mins is None and (not s.get("ended_at") or s["ended_at"] <= s["started_at"]):
            report["sessions dropped (no duration)"] += 1
            continue
        kept_entries.add(s["id"])
        entries.append({
            "id": s["id"], "category_code": place[0], "project_id": place[1],
            "milestone_id": place[2], "started_at": s["started_at"], "ended_at": s.get("ended_at"),
            "manual_minutes": mins, "description": s.get("description"),
            "is_core": bool(s.get("is_core")), "created_at": s.get("created_at"),
        })
    report["sessions kept"] = len(entries)

    # ---- to-dos: kept when placed, or when they never had a placement at all
    todos, kept_todos = [], set()
    for t in ex["todo"]:
        unplaced = not any(t.get(k) for k in ("category_id", "project_id", "milestone_id"))
        place = (None, None, None) if unplaced else placement(t)
        if place is None:
            report["to-dos dropped (category not kept)"] += 1
            continue
        kept_todos.add(t["id"])
        todos.append({
            "id": t["id"], "title": t["title"], "due_on": t["due_on"],
            "category_code": place[0], "project_id": place[1], "milestone_id": place[2],
            "est_hours": t.get("est_hours"), "is_core": bool(t.get("is_core")),
            "must_this_week": bool(t.get("must_this_week")), "is_done": bool(t.get("is_done")),
            "done_at": t.get("done_at"), "is_cancelled": bool(t.get("is_cancelled")),
            "sort_order": t.get("sort_order") or 100, "note": t.get("note"),
            "created_at": t.get("created_at"),
        })
    report["to-dos kept"] = len(todos)

    slots = [{
        "id": s["id"], "todo_id": s["todo_id"], "planned_on": s["planned_on"],
        "planned_hours": s.get("planned_hours"),
        "entry_id": s.get("session_id") if s.get("session_id") in kept_entries else None,
        "is_cancelled": bool(s.get("is_cancelled")), "sort_order": s.get("sort_order"),
        "created_at": s.get("created_at"),
    } for s in ex["todo_slot"] if s["todo_id"] in kept_todos]
    report["to-do slots kept"] = len(slots)

    # ---- CV: all of it
    cv_cols = ("id", "entry_date", "cv_year", "cv_section", "cv_subsection", "title",
               "organisation", "location", "role", "description", "outcome", "metrics",
               "evidence_url", "student_level", "start_on", "end_on", "status",
               "created_at", "updated_at")
    cvs = []
    for c in ex["cv_entry"]:
        row = {k: c.get(k) for k in cv_cols}
        row["source_type"] = "entry" if c.get("source_type") == "session" else c.get("source_type") or "manual"
        row["entry_id"] = c.get("session_id") if c.get("session_id") in kept_entries else None
        row["milestone_id"] = c.get("milestone_id") if c.get("milestone_id") in kept_ms else None
        row["project_id"] = c.get("project_id") if c.get("project_id") in proj_code else None
        cvs.append(row)
    report["CV entries kept"] = len(cvs)

    return {"project": projects, "milestone": milestones, "time_entry": entries,
            "todo": todos, "todo_slot": slots, "cv_entry": cvs}, report


# ---- SQL output ----------------------------------------------------------
ME = "(select id from auth.users)"  # the new project has exactly one user

# table: (record columns with types, insert columns, select expressions, joins)
SPECS = {
    "project": (
        "id uuid, category_code text, name text, status text, start_on date, end_on date, "
        "planned_hours numeric, is_important boolean, notes text, created_at timestamptz",
        "id, user_id, category_id, name, status, start_on, end_on, planned_hours, is_important, notes, created_at",
        f"x.id, {ME}, c.id, x.name, x.status, x.start_on, x.end_on, x.planned_hours, x.is_important, x.notes, x.created_at",
        "join category c on c.code = x.category_code",
    ),
    "milestone": (
        "id uuid, project_id uuid, title text, status text, start_on date, due_on date, "
        "planned_hours numeric, hard_deadline boolean, sort_order smallint, notes text, created_at timestamptz",
        "id, user_id, project_id, title, status, start_on, due_on, planned_hours, hard_deadline, sort_order, notes, created_at",
        f"x.id, {ME}, x.project_id, x.title, x.status, x.start_on, x.due_on, x.planned_hours, x.hard_deadline, x.sort_order, x.notes, x.created_at",
        "",
    ),
    "time_entry": (
        "id uuid, category_code text, project_id uuid, milestone_id uuid, started_at timestamptz, "
        "ended_at timestamptz, manual_minutes integer, description text, is_core boolean, created_at timestamptz",
        "id, user_id, category_id, project_id, milestone_id, started_at, ended_at, manual_minutes, description, is_core, created_at",
        f"x.id, {ME}, c.id, x.project_id, x.milestone_id, x.started_at, x.ended_at, x.manual_minutes, x.description, x.is_core, x.created_at",
        "join category c on c.code = x.category_code",
    ),
    "todo": (
        "id uuid, title text, due_on date, category_code text, project_id uuid, milestone_id uuid, "
        "est_hours numeric, is_core boolean, must_this_week boolean, is_done boolean, done_at timestamptz, "
        "is_cancelled boolean, sort_order integer, note text, created_at timestamptz",
        "id, user_id, title, due_on, category_id, project_id, milestone_id, est_hours, is_core, "
        "must_this_week, is_done, done_at, is_cancelled, sort_order, note, created_at",
        f"x.id, {ME}, x.title, x.due_on, c.id, x.project_id, x.milestone_id, x.est_hours, x.is_core, "
        "x.must_this_week, x.is_done, x.done_at, x.is_cancelled, x.sort_order, x.note, x.created_at",
        "left join category c on c.code = x.category_code",
    ),
    "todo_slot": (
        "id uuid, todo_id uuid, planned_on date, planned_hours numeric, entry_id uuid, "
        "is_cancelled boolean, sort_order integer, created_at timestamptz",
        "id, user_id, todo_id, planned_on, planned_hours, entry_id, is_cancelled, sort_order, created_at",
        f"x.id, {ME}, x.todo_id, x.planned_on, x.planned_hours, x.entry_id, x.is_cancelled, x.sort_order, x.created_at",
        "",
    ),
    "cv_entry": (
        "id uuid, entry_date date, cv_year integer, cv_section text, cv_subsection text, title text, "
        "organisation text, location text, role text, description text, outcome text, metrics text, "
        "evidence_url text, student_level text, start_on date, end_on date, status text, "
        "source_type text, entry_id uuid, milestone_id uuid, project_id uuid, "
        "created_at timestamptz, updated_at timestamptz",
        "id, user_id, entry_date, cv_year, cv_section, cv_subsection, title, organisation, location, "
        "role, description, outcome, metrics, evidence_url, student_level, start_on, end_on, status, "
        "source_type, entry_id, milestone_id, project_id, created_at, updated_at",
        f"x.id, {ME}, x.entry_date, x.cv_year, x.cv_section, x.cv_subsection, x.title, x.organisation, "
        "x.location, x.role, x.description, x.outcome, x.metrics, x.evidence_url, x.student_level, "
        "x.start_on, x.end_on, x.status, x.source_type, x.entry_id, x.milestone_id, x.project_id, "
        "x.created_at, x.updated_at",
        "",
    ),
}


def insert_sql(table, rows):
    record, cols, exprs, join = SPECS[table]
    payload = json.dumps(rows, ensure_ascii=False)
    tag = "$d$"
    while tag in payload:
        tag = f"$d{secrets.token_hex(3)}$"
    return (f"insert into {table} ({cols})\n"
            f"select {exprs}\n"
            f"from json_to_recordset({tag}{payload}{tag}::json) as x({record})\n"
            f"{join};\n")


def write_files(data, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.sql"):
        old.unlink()
    files = []
    n = 1
    for table in ("project", "milestone", "time_entry", "todo", "todo_slot", "cv_entry"):
        rows = data[table]
        for i in range(0, len(rows), ROWS_PER_FILE):
            chunk = rows[i:i + ROWS_PER_FILE]
            part = f"_{i // ROWS_PER_FILE + 1}" if len(rows) > ROWS_PER_FILE else ""
            files.append((f"{n:02d}_{table}{part}.sql",
                          f"-- {table}: {len(chunk)} rows\n" + insert_sql(table, chunk)))
            n += 1
    for name, sql in files:
        (out / name).write_text(sql, encoding="utf-8")
    return [(name, len(sql.encode("utf-8"))) for name, sql in files]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ex = load_export(sys.argv[1])
    out_dir = sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / "out"
    data, report = convert(ex)
    if ex.get("me"):
        print(f"Export for {ex['me'].get('full_name')}")
    if ex.get("counts"):
        print("Old app counts:", ex["counts"])
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"\nRun these in the NEW project's SQL editor, in order ({out_dir}):")
    for name, size in write_files(data, out_dir):
        print(f"  {name}  ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
