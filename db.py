"""
db.py — data access layer for the tracker app.

Wraps the Supabase Python client so the UI code stays readable. All queries
run as the signed-in user, so Row-Level Security automatically scopes results
(you see your own sessions; the lead sees their own). The app authenticates
with Supabase Auth, then every call carries that user's token.

Connection settings come from Streamlit secrets (.streamlit/secrets.toml):
    SUPABASE_URL  = "https://YOURPROJECT.supabase.co"
    SUPABASE_ANON_KEY = "your-anon-public-key"   # the public anon key, NOT service role
"""
from __future__ import annotations
import datetime as dt
import streamlit as st
from supabase import create_client, Client


def _new_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def client() -> Client:
    """Return a Supabase client that is UNIQUE to this browser session.

    A shared (st.cache_resource) client would hold one auth session in server
    memory and leak it across all visitors — so a new/incognito visitor would
    inherit whoever last signed in. Instead we keep one client per Streamlit
    session in st.session_state, and re-apply this session's saved auth tokens
    to it on every run so the client always acts as THIS user (and nobody
    else)."""
    c = st.session_state.get("_sb_client")
    if c is None:
        c = _new_client()
        st.session_state["_sb_client"] = c
    # re-apply this browser session's tokens (survives Streamlit reruns)
    tokens = st.session_state.get("_sb_tokens")
    if tokens:
        try:
            c.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        except Exception:
            # tokens expired/invalid: drop them so the user is treated as
            # signed out rather than wrongly authenticated
            st.session_state.pop("_sb_tokens", None)
    return c


def _store_tokens(resp):
    """Persist the access/refresh tokens from a sign-in into this session."""
    sess = getattr(resp, "session", None)
    if sess and getattr(sess, "access_token", None):
        st.session_state["_sb_tokens"] = {
            "access_token": sess.access_token,
            "refresh_token": sess.refresh_token,
        }


# ---- auth -----------------------------------------------------------------
def sign_in(email: str, password: str):
    """Sign in; store this session's tokens; returns the auth response."""
    resp = client().auth.sign_in_with_password(
        {"email": email, "password": password})
    _store_tokens(resp)
    return resp


def sign_up(email: str, password: str):
    return client().auth.sign_up({"email": email, "password": password})


def sign_out():
    try:
        client().auth.sign_out()
    except Exception:
        pass
    # clear this browser session's auth so the next run shows the login page
    st.session_state.pop("_sb_tokens", None)
    st.session_state.pop("_sb_client", None)


def current_session():
    # only consider ourselves signed in if THIS session has stored tokens
    if not st.session_state.get("_sb_tokens"):
        return None
    try:
        return client().auth.get_session()
    except Exception:
        return None


def _uid():
    """Current auth user id for THIS browser session, or '' if signed out.
    Used as a per-user cache key so cached reads never leak across users."""
    sess = current_session()
    if sess and getattr(sess, "user", None):
        return sess.user.id or ""
    return ""





def clear_user_caches():
    """Clear cached per-user reads after writes.

    This is deliberately broad and simple. It is only called after mutations,
    not during normal page reads, so it avoids stale dashboards without adding
    overhead to navigation.
    """
    st.cache_data.clear()


# ---- app_user resolution --------------------------------------------------
def my_app_user():
    """The app_user row for the signed-in auth user, or None if unlinked."""
    res = client().table("app_user").select("*").execute()
    rows = res.data or []
    # RLS lets a user read the directory; find the row linked to this login
    sess = current_session()
    if not sess or not sess.user:
        return None
    uid = sess.user.id
    for r in rows:
        if r.get("auth_user_id") == uid:
            return r
    return None


def link_my_login(app_user_id: str):
    """Attach the current auth uid to an existing app_user row (first sign-in)."""
    sess = current_session()
    if not sess or not sess.user:
        raise RuntimeError("Not signed in.")
    return (client().table("app_user")
            .update({"auth_user_id": sess.user.id})
            .eq("id", app_user_id).execute())


# ---- reference data -------------------------------------------------------
@st.cache_data(ttl=300)
def categories(domain=None):
    """Active categories. domain=None returns all; 'work' or 'life' filters.
    Life categories exist only for personal use by the lead; callers should
    pass domain='work' for students."""
    q = client().table("category").select("id,code,label,sort_order,domain") \
        .eq("is_active", True)
    if domain:
        q = q.eq("domain", domain)
    return q.order("sort_order").execute().data or []


@st.cache_data(ttl=300)
def project_statuses():
    return client().table("project_status").select("*").execute().data or []


# ---- projects -------------------------------------------------------------
@st.cache_data(ttl=30)
def _my_projects(_u):
    res = client().table("project").select(
        "id,name,status_id,visibility,estimated_hours,category_id,"
        "high_importance") \
        .order("name").execute()
    return res.data or []


def my_projects():
    return _my_projects(_uid())


def projects_for_category(category_id):
    """Projects whose single category matches category_id, for the filtered
    logging dropdown."""
    res = client().table("project").select(
        "id,name,category_id,high_importance") \
        .eq("category_id", category_id).order("name").execute()
    return res.data or []


def set_project_importance(project_id, high):
    return client().table("project").update({"high_importance": bool(high)}) \
        .eq("id", project_id).execute()


def high_importance_hours(date_from, date_to):
    """Hours the caller logged on high-importance projects in the range.
    Returns list of {name, hours} sorted by hours desc."""
    hi = client().table("project").select("id,name") \
        .eq("high_importance", True).execute().data or []
    if not hi:
        return []
    hi_ids = {p["id"]: p["name"] for p in hi}
    sess = (client().table("v_session_detail")
            .select("project_id,hours,session_date")
            .gte("session_date", date_from)
            .lte("session_date", date_to).execute().data or [])
    agg = {}
    for s in sess:
        pid = s.get("project_id")
        if pid in hi_ids:
            agg[pid] = agg.get(pid, 0) + (s.get("hours") or 0)
    out = [{"name": hi_ids[pid], "hours": h} for pid, h in agg.items()]
    return sorted(out, key=lambda x: -x["hours"])


# ---- to-do items ----------------------------------------------------------
def todos_in_range(date_from, date_to, include_open_before=True):
    """The caller's todos with due_on in [date_from, date_to], ordered by
    sort_order. If include_open_before, also include todos due before
    date_from that are either still open (carried over) or were completed
    within [date_from, date_to] (so this week's "done" hours capture carried
    tasks finished this week)."""
    cols = ("id,title,note,due_on,is_done,project_id,est_hours,"
            "sort_order,done_at,is_important")
    rows = (client().table("todo").select(cols)
            .gte("due_on", date_from).lte("due_on", date_to)
            .order("sort_order").order("due_on").execute().data or [])
    if include_open_before:
        carried = (client().table("todo").select(cols)
                   .lt("due_on", date_from).eq("is_done", False)
                   .order("sort_order").order("due_on").execute().data or [])
        # carried tasks completed within this range: their done_at is a
        # timestamp, so bound it by [date_from, day after date_to).
        done_upper = (dt.date.fromisoformat(date_to)
                      + dt.timedelta(days=1)).isoformat()
        carried_done = (client().table("todo").select(cols)
                        .lt("due_on", date_from).eq("is_done", True)
                        .gte("done_at", date_from).lt("done_at", done_upper)
                        .order("sort_order").order("due_on").execute().data
                        or [])
        # Merge everything into one list sorted by a single global sort_order
        # so items can be reordered freely across the boundary (carried items
        # are no longer pinned above the current week). New todos with a null
        # sort_order fall to the bottom, then by due_on.
        rows = sorted(
            carried + carried_done + rows,
            key=lambda t: (t.get("sort_order") if t.get("sort_order")
                           is not None else 10**9, t.get("due_on") or ""))
    return rows


def set_todo_order(todo_id, sort_order):
    return client().table("todo").update({"sort_order": sort_order}) \
        .eq("id", todo_id).execute()


def update_todo(todo_id, fields: dict):
    return client().table("todo").update(fields).eq("id", todo_id).execute()


def add_todo(user_id, title, due_on, project_id=None, est_hours=None,
             note=None, important=False):
    payload = {"user_id": user_id, "title": title, "due_on": due_on,
               "is_important": bool(important)}
    if project_id:
        payload["project_id"] = project_id
    if est_hours:
        payload["est_hours"] = est_hours
    if note:
        payload["note"] = note
    return client().table("todo").insert(payload).execute()


def set_todo_done(todo_id, done):
    import datetime as _dt
    fields = {"is_done": bool(done),
              "done_at": _dt.datetime.now().isoformat() if done else None}
    return client().table("todo").update(fields).eq("id", todo_id).execute()


def set_todo_important(todo_id, important):
    return client().table("todo").update({"is_important": bool(important)}) \
        .eq("id", todo_id).execute()


def delete_todo(todo_id):
    return client().table("todo").delete().eq("id", todo_id).execute()


def set_project_category(project_id, category_id):
    return client().table("project").update({"category_id": category_id}) \
        .eq("id", project_id).execute()


def create_project(name, status_id, visibility, estimated_hours, owner_id):
    payload = {
        "name": name, "status_id": status_id, "visibility": visibility,
        "owner_id": owner_id,
    }
    if estimated_hours:
        payload["estimated_hours"] = estimated_hours
    return client().table("project").insert(payload).execute()


def default_active_status_id():
    """The id of the 'active' project status, for quick on-the-fly creation."""
    rows = project_statuses()
    for s in rows:
        if s.get("code") == "active":
            return s["id"]
    return rows[0]["id"] if rows else None


def get_or_create_project(name, owner_id, visibility="private",
                          category_id=None):
    """Return the id of a project with this name owned by the user, creating a
    minimal one (active status, no estimate) if it does not exist yet. If
    creating and category_id is given, the project is auto-linked to that
    category. Returns (project_id, created)."""
    name = name.strip()
    existing = client().table("project").select("id,name,owner_id,category_id") \
        .eq("owner_id", owner_id).eq("name", name).execute().data or []
    if existing:
        return existing[0]["id"], False
    payload = {
        "name": name,
        "owner_id": owner_id,
        "status_id": default_active_status_id(),
        "visibility": visibility,
    }
    if category_id:
        payload["category_id"] = category_id
    res = client().table("project").insert(payload).execute()
    return res.data[0]["id"], True


def update_project(project_id, fields: dict):
    """Update editable fields on a project (status_id, visibility,
    estimated_hours, name, purpose, final_outcomes, stakeholders, risks)."""
    return client().table("project").update(fields).eq("id", project_id).execute()


def project_detail(project_id):
    rows = client().table("project").select(
        "id,name,status_id,visibility,estimated_hours,started_on,due_on,"
        "purpose,final_outcomes,stakeholders,risks,category_id,"
        "high_importance") \
        .eq("id", project_id).execute().data or []
    return rows[0] if rows else None


def active_projects_for_gantt():
    """Active projects with dates and status, each annotated with whether the
    current user leads it. Ordered: led-by-me first, then participant, then by
    due date. Used by both the Gantt and the grouped project list."""
    statuses = {s["id"]: s for s in project_statuses()}
    active_ids = [sid for sid, s in statuses.items() if s.get("code") == "active"]
    if not active_ids:
        return []
    rows = client().table("project").select(
        "id,name,started_on,due_on,status_id").execute().data or []
    rows = [r for r in rows if r.get("status_id") in active_ids]
    me_id = my_app_user_id()
    # who leads each project
    leads = client().table("project_lead").select(
        "project_id,user_id,is_leader").execute().data or []
    leader_of = {L["project_id"]: L["user_id"]
                 for L in leads if L.get("is_leader")}
    member_of = {}
    for L in leads:
        member_of.setdefault(L["project_id"], set()).add(L["user_id"])
    for r in rows:
        r["i_lead"] = leader_of.get(r["id"]) == me_id
        r["i_participate"] = (me_id in member_of.get(r["id"], set())
                              and not r["i_lead"])
    rows.sort(key=lambda r: (not r["i_lead"], not r["i_participate"],
                             r.get("due_on") or "9999"))
    return rows


def my_app_user_id():
    me = my_app_user()
    return me["id"] if me else None


@st.cache_data(ttl=60)
def _projects_i_participate_in(_u):
    """Projects where I am a lead or participant (via project_lead).
    Returns [{id, name}] for use in the milestones overview and selectors."""
    me_id = my_app_user_id()
    leads = (client().table("project_lead")
             .select("project_id,user_id").execute().data or [])
    my_pids = {L["project_id"] for L in leads if L["user_id"] == me_id}
    if not my_pids:
        return []
    projs = (client().table("project")
             .select("id,name,status_id").execute().data or [])
    return [{"id": p["id"], "name": p["name"]}
            for p in projs if p["id"] in my_pids]


def projects_i_participate_in():
    return _projects_i_participate_in(_uid())


def milestones_for_projects(project_ids):
    """All milestones across the given projects, with project name and the
    effective category code (milestone's own category if set, else the
    project's category)."""
    if not project_ids:
        return []
    projs = (client().table("project").select("id,name,category_id")
             .execute().data or [])
    pname = {p["id"]: p["name"] for p in projs}
    pcat = {p["id"]: p.get("category_id") for p in projs}
    cats = (client().table("category").select("id,code,label").execute().data
            or [])
    cat_code = {c["id"]: c["code"] for c in cats}
    out = []
    for pid in project_ids:
        for m in project_milestones(pid):
            m = dict(m)
            m["project_name"] = pname.get(pid, "")
            m["project_id"] = pid
            eff_cat = m.get("category_id") or pcat.get(pid)
            m["effective_category_code"] = cat_code.get(eff_cat)
            out.append(m)
    return out


def project_leads(project_id):
    rows = client().table("project_lead") \
        .select("user_id,role,is_leader").eq("project_id", project_id) \
        .execute().data or []
    return rows


def set_project_leader(project_id, user_id):
    """Make user_id the sole leader of the project: clear any existing leader,
    ensure the user is a member, then flag them leader."""
    # clear current leader flag(s)
    client().table("project_lead").update({"is_leader": False}) \
        .eq("project_id", project_id).execute()
    # ensure membership row exists
    existing = client().table("project_lead").select("user_id") \
        .eq("project_id", project_id).eq("user_id", user_id).execute().data or []
    if existing:
        client().table("project_lead").update({"is_leader": True}) \
            .eq("project_id", project_id).eq("user_id", user_id).execute()
    else:
        client().table("project_lead").insert({
            "project_id": project_id, "user_id": user_id,
            "is_leader": True}).execute()


# ---- people in charge -----------------------------------------------------
def add_project_lead(project_id, user_id, role=None):
    return client().table("project_lead").insert({
        "project_id": project_id, "user_id": user_id, "role": role}).execute()


def remove_project_lead(project_id, user_id):
    return (client().table("project_lead").delete()
            .eq("project_id", project_id).eq("user_id", user_id).execute())


def update_project_lead_role(project_id, user_id, role):
    return (client().table("project_lead").update({"role": role})
            .eq("project_id", project_id).eq("user_id", user_id).execute())


def all_users():
    return client().table("app_user").select("id,full_name,email") \
        .eq("is_active", True).order("full_name").execute().data or []


# ---- project links --------------------------------------------------------
def project_links(project_id):
    # project-level links only (milestone_id is null)
    return (client().table("project_link")
            .select("id,url,label,kind,milestone_id")
            .eq("project_id", project_id).is_("milestone_id", "null")
            .execute().data or [])


def add_project_link(project_id, url, label=None, kind="reference",
                     milestone_id=None):
    payload = {"project_id": project_id, "url": url,
               "label": label, "kind": kind}
    if milestone_id:
        payload["milestone_id"] = milestone_id
    return client().table("project_link").insert(payload).execute()


def milestone_links(milestone_id):
    return (client().table("project_link")
            .select("id,url,label,kind")
            .eq("milestone_id", milestone_id).execute().data or [])


def delete_project_link(link_id):
    return client().table("project_link").delete().eq("id", link_id).execute()


# ---- history --------------------------------------------------------------
def project_history(project_id):
    return (client().table("v_project_history")
            .select("changed_at,table_name,action,changed_by")
            .eq("project_id", project_id)
            .order("changed_at", desc=True).limit(50).execute().data or [])


@st.cache_data(ttl=30)
def _project_milestones(project_id, _u):
    rows = (client().table("project_milestone")
            .select("id,title,detail,due_on,start_on,status,sort_order,"
                    "hypothesis,success_measure,"
                    "precondition_id,contributor_id,"
                    "shared_percent,category_id,kind,"
                    "work_days")
            .eq("project_id", project_id)
            .order("sort_order").execute().data or [])
    # sort by due date, with undated milestones last
    rows.sort(key=lambda m: (m.get("due_on") is None,
                             m.get("due_on") or ""))
    return rows


def project_milestones(project_id):
    return _project_milestones(project_id, _uid())


@st.cache_data(ttl=30)
def _project_milestones_bulk(project_ids_key, _u):
    """Milestones for many projects in one query, grouped by project_id.

    Used by the Gantt chart so the Projects tab does not issue one
    project_milestones() query per project. The _u argument keeps the cache
    scoped to the signed-in user.
    """
    project_ids = list(project_ids_key)
    if not project_ids:
        return {}
    rows = (client().table("project_milestone")
            .select("id,project_id,title,detail,due_on,start_on,status,sort_order,"
                    "hypothesis,success_measure,"
                    "precondition_id,contributor_id,"
                    "shared_percent,category_id,kind,"
                    "work_days")
            .in_("project_id", project_ids)
            .order("sort_order")
            .execute().data or [])
    grouped = {pid: [] for pid in project_ids}
    for r in rows:
        grouped.setdefault(r.get("project_id"), []).append(r)
    for pid in grouped:
        grouped[pid].sort(key=lambda m: (m.get("due_on") is None,
                                         m.get("due_on") or "",
                                         m.get("sort_order") or 0))
    return grouped


def project_milestones_bulk(project_ids):
    ids = tuple(sorted({pid for pid in project_ids if pid}))
    return _project_milestones_bulk(ids, _uid())


def my_milestone_plans():
    """The caller's private milestone plans, keyed by milestone_id. RLS means
    this only ever returns the caller's own rows."""
    rows = (client().table("milestone_plan")
            .select("milestone_id,planned_hours,track_unit,percent_complete")
            .execute().data or [])
    return {r["milestone_id"]: r for r in rows}


def upsert_milestone_plan(milestone_id, owner_id, planned_hours, track_unit,
                          percent_complete):
    """Create or update the caller's private plan for a milestone."""
    existing = (client().table("milestone_plan").select("id")
                .eq("milestone_id", milestone_id)
                .eq("owner_id", owner_id).execute().data or [])
    payload = {"planned_hours": planned_hours, "track_unit": track_unit,
               "percent_complete": percent_complete}
    if existing:
        return (client().table("milestone_plan").update(payload)
                .eq("id", existing[0]["id"]).execute())
    payload.update({"milestone_id": milestone_id, "owner_id": owner_id})
    return client().table("milestone_plan").insert(payload).execute()


def set_milestone_shared_percent(milestone_id, pct):
    """Update the public completion % shown to everyone (no hours exposed)."""
    return (client().table("project_milestone")
            .update({"shared_percent": pct}).eq("id", milestone_id).execute())


def refresh_shared_percent_from_hours(milestone_id, owner_id):
    """If the owner tracks this milestone in hours, recompute its shared % as
    their logged hours / planned hours (capped 0..100) and publish it. No-op
    for percent-tracked milestones (those are set manually) or when there's no
    plan/estimate. Called after the owner logs, edits, or deletes a session
    tagged to the milestone, so the public % stays current without exposing
    the underlying hours.

    Returns the new percent, or None if nothing was changed."""
    if not milestone_id or not owner_id:
        return None
    # don't override a milestone that's been marked done
    ms = (client().table("project_milestone").select("status")
          .eq("id", milestone_id).execute().data or [])
    if ms and ms[0].get("status") == "done":
        return None
    plan = (client().table("milestone_plan")
            .select("planned_hours,track_unit")
            .eq("milestone_id", milestone_id)
            .eq("owner_id", owner_id).execute().data or [])
    if not plan:
        return None
    p = plan[0]
    if p.get("track_unit") != "hours":
        return None
    planned = p.get("planned_hours")
    if not planned:
        return None
    # the owner's own logged hours toward this milestone
    hrs = _my_milestone_hours_uncached().get(milestone_id) or 0
    pct = max(0, min(100, int(round(100 * hrs / planned))))
    set_milestone_shared_percent(milestone_id, pct)
    return pct


def milestone_shared_progress(project_id):
    """Each milestone's public completion %, for the shared per-project chart.
    Uses the published shared_percent when present; otherwise binary (100 if
    the milestone is marked done, else 0). No hours involved. Returns a list of
    {title, pct, status} ordered by due date then title."""
    ms = (client().table("project_milestone")
          .select("id,title,status,due_on,shared_percent")
          .eq("project_id", project_id).execute().data or [])
    out = []
    for m in ms:
        if m.get("status") == "done":
            pct = 100
        elif m.get("shared_percent") is not None:
            pct = int(round(m["shared_percent"]))
        else:
            pct = 0
        out.append({"title": m["title"], "pct": pct,
                    "status": m.get("status"), "due_on": m.get("due_on")})
    out.sort(key=lambda x: (x.get("due_on") is None, x.get("due_on") or "",
                            x["title"]))
    return out


def milestone_updates(milestone_id):
    return (client().table("milestone_update")
            .select("id,note,author_id,created_at")
            .eq("milestone_id", milestone_id)
            .order("created_at", desc=True).execute().data or [])


def milestone_audit(milestone_id):
    """Automatic field-change audit entries for one milestone."""
    return (client().table("audit_log")
            .select("action,changed_by,changed_at,old_row,new_row")
            .eq("table_name", "project_milestone")
            .eq("row_id", milestone_id)
            .order("changed_at", desc=True).limit(20).execute().data or [])


def milestone_history_combined(milestone_id, limit=5):
    """Merge the automatic edit audit and the human progress notes into one
    time-ordered list (most recent first), capped at `limit`. Each item is
    {kind: 'edit'|'note', when, who, detail}."""
    items = []
    for a in milestone_audit(milestone_id):
        items.append({"kind": "edit",
                      "when": a.get("changed_at") or "",
                      "who": a.get("changed_by"),
                      "action": a.get("action"),
                      "old_row": a.get("old_row"),
                      "new_row": a.get("new_row")})
    for u in milestone_updates(milestone_id):
        items.append({"kind": "note",
                      "when": u.get("created_at") or "",
                      "who": u.get("author_id"),
                      "note": u.get("note")})
    items.sort(key=lambda x: x["when"], reverse=True)
    return items[:limit]


@st.cache_data(ttl=30)
def _milestone_history_bulk(milestone_ids_key, _u, limit=5):
    """Combined edit+note history for MANY milestones in just two queries.
    Returns {milestone_id: [history items]} (each capped at `limit`, newest
    first). Replaces calling milestone_history_combined once per milestone,
    which was two queries each (the main first-load slowdown)."""
    ids = list(milestone_ids_key)
    if not ids:
        return {}
    audits = (client().table("audit_log")
              .select("row_id,action,changed_by,changed_at,old_row,new_row")
              .eq("table_name", "project_milestone")
              .in_("row_id", ids)
              .order("changed_at", desc=True).execute().data or [])
    notes = (client().table("milestone_update")
             .select("milestone_id,note,author_id,created_at")
             .in_("milestone_id", ids)
             .order("created_at", desc=True).execute().data or [])
    by_ms = {i: [] for i in ids}
    for a in audits:
        by_ms.setdefault(a["row_id"], []).append({
            "kind": "edit", "when": a.get("changed_at") or "",
            "who": a.get("changed_by"), "action": a.get("action"),
            "old_row": a.get("old_row"), "new_row": a.get("new_row")})
    for u in notes:
        by_ms.setdefault(u["milestone_id"], []).append({
            "kind": "note", "when": u.get("created_at") or "",
            "who": u.get("author_id"), "note": u.get("note")})
    for mid in by_ms:
        by_ms[mid].sort(key=lambda x: x["when"], reverse=True)
        by_ms[mid] = by_ms[mid][:limit]
    return by_ms


def milestone_history_bulk(milestone_ids, limit=5):
    # tuple key so st.cache_data can hash it; per-user via _uid()
    return _milestone_history_bulk(tuple(sorted(milestone_ids)), _uid(), limit)


def add_milestone_update(milestone_id, author_id, note):
    return client().table("milestone_update").insert({
        "milestone_id": milestone_id, "author_id": author_id,
        "note": note}).execute()


def delete_milestone_update(update_id):
    return (client().table("milestone_update").delete()
            .eq("id", update_id).execute())


def milestone_percent(m, my_hours=None):
    """Public completion % for a milestone, shown to everyone. Reads the
    shared_percent the contributor publishes (derived privately from their
    hours, or set directly). Marking the milestone done forces 100.
    my_hours is accepted for backward compatibility but no longer used, since
    hours are private."""
    if m.get("status") == "done":
        return 100
    sp = m.get("shared_percent")
    return int(round(sp)) if sp is not None else None


@st.cache_data(ttl=120)
def _group_members(_u):
    """Active people who can be milestone contributors."""
    return (client().table("app_user")
            .select("id,full_name,role,is_active")
            .eq("is_active", True).order("full_name").execute().data or [])


def group_members():
    return _group_members(_uid())


def project_milestone_audit(project_id):
    """All audit rows for milestones belonging to a project, oldest first.
    Used to reconstruct historical state. Returns rows with action, changed_at,
    row_id, and the new_row JSON snapshot."""
    # milestone ids currently or formerly in this project: we match on the
    # new_row/old_row project_id inside the audit JSON.
    rows = (client().table("audit_log")
            .select("row_id,action,changed_at,old_row,new_row")
            .eq("table_name", "project_milestone")
            .order("changed_at").execute().data or [])
    out = []
    for r in rows:
        nr = r.get("new_row") or {}
        orow = r.get("old_row") or {}
        pid = nr.get("project_id") or orow.get("project_id")
        if str(pid) == str(project_id):
            out.append(r)
    return out


def reconstruct_milestones_at(audit_rows, as_of_iso):
    """Given a project's milestone audit rows (oldest first) and a cutoff
    datetime (ISO date string), return the state of each milestone as of that
    date: {id: {title, due_on, status, percent_complete, planned_hours,
    track_unit}}. A milestone whose latest entry by then is DELETE, or which
    has no entry yet, is omitted."""
    state = {}
    for r in audit_rows:
        when = (r.get("changed_at") or "")[:10]
        if when > as_of_iso:
            continue
        rid = r["row_id"]
        if r["action"] == "DELETE":
            state.pop(rid, None)
            continue
        nr = r.get("new_row") or {}
        state[rid] = {
            "id": rid,
            "title": nr.get("title"),
            "due_on": nr.get("due_on"),
            "status": nr.get("status"),
            "percent_complete": nr.get("percent_complete"),
            "planned_hours": nr.get("planned_hours"),
            "track_unit": nr.get("track_unit"),
        }
    return state


def add_milestone(project_id, title, detail=None, due_on=None, status="planned",
                  hypothesis=None, success_measure=None, planned_hours=None):
    # planned_hours is now private (milestone_plan); ignored here, kept in the
    # signature for backward compatibility.
    payload = {"project_id": project_id, "title": title, "status": status}
    if detail:
        payload["detail"] = detail
    if due_on:
        payload["due_on"] = due_on
    if hypothesis:
        payload["hypothesis"] = hypothesis
    if success_measure:
        payload["success_measure"] = success_measure
    return client().table("project_milestone").insert(payload).execute()


def update_milestone(milestone_id, fields: dict):
    return (client().table("project_milestone")
            .update(fields).eq("id", milestone_id).execute())


def delete_milestone(milestone_id):
    return (client().table("project_milestone")
            .delete().eq("id", milestone_id).execute())


def _my_milestone_hours_uncached():
    """Fresh (uncached) map of milestone_id -> the caller's own hours toward it.
    Used by the shared-% recompute, which runs right after a session write and
    must see the just-written hours, not a cached snapshot."""
    rows = client().table("v_my_milestone_hours") \
        .select("milestone_id,my_hours").execute().data or []
    return {r["milestone_id"]: r["my_hours"] for r in rows}


@st.cache_data(ttl=30)
def _my_milestone_hours_cached(_u):
    """Map of milestone_id -> the current user's own hours toward it.
    Cached per-user; cleared on writes."""
    return _my_milestone_hours_uncached()


def my_milestone_hours():
    return _my_milestone_hours_cached(_uid())


# ---- sessions -------------------------------------------------------------
def log_session(user_id, category_id, started_at, ended_at=None,
                manual_minutes=None, project_id=None, description=None,
                milestone_id=None):
    payload = {
        "user_id": user_id,
        "category_id": category_id,
        "started_at": started_at,
    }
    if ended_at:
        payload["ended_at"] = ended_at
    if manual_minutes is not None:
        payload["manual_minutes"] = manual_minutes
    if project_id:
        payload["project_id"] = project_id
    if milestone_id:
        payload["milestone_id"] = milestone_id
    if description:
        payload["description"] = description
    res = client().table("work_session").insert(payload).execute()
    # auto-publish the shared % for an hours-tracked milestone
    if milestone_id:
        refresh_shared_percent_from_hours(milestone_id, user_id)
    return res


def recent_sessions(limit=20):
    res = client().table("v_session_detail") \
        .select("id,session_date,category_id,category_label,project_id,"
                "project_name,hours,description,started_at,ended_at,"
                "milestone_id,milestone_title") \
        .order("started_at", desc=True).limit(limit).execute()
    return res.data or []


def sessions_in_range(date_from, date_to):
    """All of the caller's timed sessions overlapping [date_from, date_to].
    Returns rows with start/end so the week view can place them."""
    res = (client().table("v_session_detail")
           .select("id,session_date,category_id,category_label,project_id,"
                   "project_name,hours,description,started_at,ended_at,"
                   "milestone_id,milestone_title")
           .gte("session_date", date_from)
           .lte("session_date", date_to)
           .order("started_at").execute())
    return res.data or []


def _session_owner_and_milestone(session_id):
    """Return (user_id, milestone_id) for a session, or (None, None)."""
    rows = (client().table("work_session")
            .select("user_id,milestone_id").eq("id", session_id)
            .execute().data or [])
    if not rows:
        return None, None
    return rows[0].get("user_id"), rows[0].get("milestone_id")


def update_session(session_id, fields: dict):
    # capture the milestone before the change (it may move or clear)
    owner_before, ms_before = _session_owner_and_milestone(session_id)
    res = (client().table("work_session").update(fields)
           .eq("id", session_id).execute())
    owner_after, ms_after = _session_owner_and_milestone(session_id)
    # refresh both the old and new milestone so neither is left stale
    for mid, owner in {(ms_before, owner_before), (ms_after, owner_after)}:
        if mid and owner:
            refresh_shared_percent_from_hours(mid, owner)
    return res


def delete_session(session_id):
    owner, mid = _session_owner_and_milestone(session_id)
    res = (client().table("work_session").delete()
           .eq("id", session_id).execute())
    if mid and owner:
        refresh_shared_percent_from_hours(mid, owner)
    return res


def duplicate_session(session_id, new_date=None):
    """Create a copy of a session. If new_date (ISO date string) is given, the
    copy is moved to that date, preserving the time-of-day; otherwise it lands
    on the same date. Returns the new row."""
    src = client().table("work_session").select(
        "user_id,category_id,project_id,milestone_id,started_at,ended_at,"
        "manual_minutes,description").eq("id", session_id).execute().data
    if not src:
        return None
    s = dict(src[0])
    if new_date and s.get("started_at"):
        # keep the time-of-day, shift to the new date
        s["started_at"] = new_date + s["started_at"][10:]
        if s.get("ended_at"):
            # if the original ended on the next day (midnight block), keep that
            same_day = s["ended_at"][:10] == src[0]["started_at"][:10]
            if same_day:
                s["ended_at"] = new_date + s["ended_at"][10:]
            else:
                nd = (dt.date.fromisoformat(new_date) + dt.timedelta(days=1))
                s["ended_at"] = nd.isoformat() + s["ended_at"][10:]
    payload = {k: v for k, v in s.items() if v is not None}
    return client().table("work_session").insert(payload).execute()


# ---- inference (views + RPC functions) ------------------------------------
@st.cache_data(ttl=30)
def _project_tracker(_u):
    return client().table("v_project_tracker").select("*").execute().data or []


def project_tracker():
    return _project_tracker(_uid())


def milestone_progress(project_id):
    """Milestone-completion stats for a project, with NO hours. Returns
    {done, total, pct} where pct is the share of milestones marked done."""
    ms = (client().table("project_milestone")
          .select("id,status").eq("project_id", project_id)
          .execute().data or [])
    total = len(ms)
    done = sum(1 for m in ms if m.get("status") == "done")
    pct = round(100 * done / total) if total else None
    return {"done": done, "total": total, "pct": pct}


def milestone_progress_bars(project_id):
    """Per-milestone published progress for the project's bar chart. Each item
    is {title, pct, fallback}: pct is the published shared_percent; if none is
    published, pct falls back to binary (100 if done, else 0) and fallback is
    True so it can be flagged. Hours are never involved. Ordered by due date."""
    ms = (client().table("project_milestone")
          .select("title,status,shared_percent,due_on,sort_order")
          .eq("project_id", project_id).execute().data or [])
    ms.sort(key=lambda m: (m.get("due_on") is None, m.get("due_on") or "",
                           m.get("sort_order") or 0))
    out = []
    for m in ms:
        if m.get("status") == "done":
            out.append({"title": m["title"], "pct": 100, "fallback": False})
        elif m.get("shared_percent") is not None:
            out.append({"title": m["title"],
                        "pct": int(round(m["shared_percent"])),
                        "fallback": False})
        else:
            out.append({"title": m["title"], "pct": 0, "fallback": True})
    return out


@st.cache_data(ttl=30)
def _milestone_progress_bulk(project_ids_key, _u):
    """Milestone-completion stats for many projects in one query."""
    project_ids = list(project_ids_key)
    if not project_ids:
        return {}
    rows = (client().table("project_milestone")
            .select("project_id,status")
            .in_("project_id", project_ids)
            .execute().data or [])
    out = {pid: {"done": 0, "total": 0, "pct": None}
           for pid in project_ids}
    for m in rows:
        pid = m.get("project_id")
        if pid not in out:
            out[pid] = {"done": 0, "total": 0, "pct": None}
        out[pid]["total"] += 1
        if m.get("status") == "done":
            out[pid]["done"] += 1
    for pid, v in out.items():
        v["pct"] = round(100 * v["done"] / v["total"]) if v["total"] else None
    return out


def milestone_progress_bulk(project_ids):
    ids = tuple(sorted({pid for pid in project_ids if pid}))
    return _milestone_progress_bulk(ids, _uid())


@st.cache_data(ttl=30)
def _milestone_progress_bars_bulk(project_ids_key, _u):
    """Per-milestone progress bars for many projects in one query."""
    project_ids = list(project_ids_key)
    if not project_ids:
        return {}
    rows = (client().table("project_milestone")
            .select("project_id,title,status,shared_percent,due_on,sort_order")
            .in_("project_id", project_ids)
            .execute().data or [])
    grouped = {pid: [] for pid in project_ids}
    for m in rows:
        grouped.setdefault(m.get("project_id"), []).append(m)
    out = {}
    for pid, ms in grouped.items():
        ms.sort(key=lambda m: (m.get("due_on") is None,
                               m.get("due_on") or "",
                               m.get("sort_order") or 0))
        bars = []
        for m in ms:
            if m.get("status") == "done":
                bars.append({"title": m["title"], "pct": 100,
                             "fallback": False})
            elif m.get("shared_percent") is not None:
                bars.append({"title": m["title"],
                             "pct": int(round(m["shared_percent"])),
                             "fallback": False})
            else:
                bars.append({"title": m["title"], "pct": 0,
                             "fallback": True})
        out[pid] = bars
    return out


def milestone_progress_bars_bulk(project_ids):
    ids = tuple(sorted({pid for pid in project_ids if pid}))
    return _milestone_progress_bars_bulk(ids, _uid())


# ---- budget (lead-only via RLS) -------------------------------------------
def budget_items(project_id):
    """Plan items for a project, each with its Used (sum of payments),
    Remaining, and Remaining %."""
    items = (client().table("budget_item")
             .select("id,label,plan_amount,currency,sort_order")
             .eq("project_id", project_id)
             .order("sort_order").execute().data or [])
    # sum payments per item
    item_ids = [i["id"] for i in items]
    used = {}
    if item_ids:
        pays = (client().table("budget_payment")
                .select("budget_item_id,amount").execute().data or [])
        for p in pays:
            iid = p["budget_item_id"]
            if iid in item_ids:
                used[iid] = used.get(iid, 0) + (p["amount"] or 0)
    for i in items:
        plan = i.get("plan_amount") or 0
        u = used.get(i["id"], 0)
        i["used"] = u
        i["remaining"] = plan - u
        i["remaining_pct"] = (round(100 * (plan - u) / plan, 1)
                              if plan else None)
    return items


def add_budget_item(project_id, label, plan_amount, currency="GBP"):
    return client().table("budget_item").insert({
        "project_id": project_id, "label": label,
        "plan_amount": plan_amount, "currency": currency}).execute()


def update_budget_item(item_id, fields):
    return client().table("budget_item").update(fields) \
        .eq("id", item_id).execute()


def delete_budget_item(item_id):
    return client().table("budget_item").delete().eq("id", item_id).execute()


def budget_payments(project_id):
    """All payments for a project's items, with the item label, newest first."""
    items = (client().table("budget_item").select("id,label")
             .eq("project_id", project_id).execute().data or [])
    label = {i["id"]: i["label"] for i in items}
    if not label:
        return []
    pays = (client().table("budget_payment")
            .select("id,budget_item_id,detail1,detail2,amount,paid_on")
            .order("paid_on", desc=True).execute().data or [])
    out = []
    for p in pays:
        if p["budget_item_id"] in label:
            p["item_label"] = label[p["budget_item_id"]]
            out.append(p)
    return out


def add_budget_payment(budget_item_id, amount, detail1=None, detail2=None,
                       paid_on=None):
    payload = {"budget_item_id": budget_item_id, "amount": amount}
    if detail1:
        payload["detail1"] = detail1
    if detail2:
        payload["detail2"] = detail2
    if paid_on:
        payload["paid_on"] = paid_on
    return client().table("budget_payment").insert(payload).execute()


def delete_budget_payment(payment_id):
    return (client().table("budget_payment").delete()
            .eq("id", payment_id).execute())


def project_time_elapsed_pct(project_id):
    """How much of a project's start->due window has elapsed (0..100), or None
    if dates are missing."""
    p = (client().table("project").select("started_on,due_on")
         .eq("id", project_id).execute().data or [])
    if not p:
        return None
    s, d = p[0].get("started_on"), p[0].get("due_on")
    if not s or not d:
        return None
    import datetime as _dt
    s = _dt.date.fromisoformat(s)
    d = _dt.date.fromisoformat(d)
    today = _dt.date.today()
    total = (d - s).days
    if total <= 0:
        return 100
    elapsed = (today - s).days
    return max(0, min(100, round(100 * elapsed / total)))


def time_by_high_category(date_from=None, date_to=None):
    params = {}
    if date_from:
        params["p_from"] = date_from
    if date_to:
        params["p_to"] = date_to
    return client().rpc("time_by_high_category", params).execute().data or []


def hours_by_category(date_from=None, date_to=None):
    params = {}
    if date_from:
        params["p_from"] = date_from
    if date_to:
        params["p_to"] = date_to
    return client().rpc("hours_by_category", params).execute().data or []


def project_load_forecast(project_id, capacity=37.5, lookback_weeks=8):
    return client().rpc("project_load_forecast", {
        "p_project_id": project_id,
        "p_capacity_hours": capacity,
        "p_lookback_weeks": lookback_weeks,
    }).execute().data or []

# ---- CV achievement records -----------------------------------------------
CV_ENTRY_SELECT = (
    "id,user_id,entry_date,cv_year,cv_section,cv_subsection,title,"
    "organisation,location,role,description,outcome,metrics,evidence_url,"
    "status,source_type,session_id,milestone_id,project_id,created_at,updated_at"
)


def _clean_cv_payload(payload: dict) -> dict:
    """Drop blank strings while preserving explicit None for nullable fields."""
    clean = {}
    for k, v in payload.items():
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                continue
        if v is not None:
            clean[k] = v
    return clean


def add_cv_entry(user_id, entry_date, cv_section, title, cv_subsection=None,
                 organisation=None, location=None, role=None, description=None,
                 outcome=None, metrics=None, evidence_url=None, status="draft",
                 source_type="manual", session_id=None, milestone_id=None,
                 project_id=None):
    """Create a private CV/achievement record for the signed-in user.

    The record may link back to a session, milestone, or project, but can also
    stand alone. The CV tab is the only place that reads these records in bulk.
    """
    payload = _clean_cv_payload({
        "user_id": user_id,
        "entry_date": entry_date,
        "cv_section": cv_section,
        "cv_subsection": cv_subsection,
        "title": title,
        "organisation": organisation,
        "location": location,
        "role": role,
        "description": description,
        "outcome": outcome,
        "metrics": metrics,
        "evidence_url": evidence_url,
        "status": status or "draft",
        "source_type": source_type or "manual",
        "session_id": session_id,
        "milestone_id": milestone_id,
        "project_id": project_id,
    })
    return client().table("cv_entry").insert(payload).execute()


def update_cv_entry(entry_id, fields: dict):
    return (client().table("cv_entry")
            .update(_clean_cv_payload(fields)).eq("id", entry_id).execute())


def delete_cv_entry(entry_id):
    return client().table("cv_entry").delete().eq("id", entry_id).execute()


@st.cache_data(ttl=60)
def _cv_entry_summary(_u):
    """Small, fast summary for the CV tab landing view."""
    return (client().table("cv_entry")
            .select("id,cv_year,cv_section,cv_subsection,status,source_type")
            .order("cv_year", desc=True).execute().data or [])


def cv_entry_summary():
    return _cv_entry_summary(_uid())


@st.cache_data(ttl=60)
def _cv_entries(_u, year=None, status=None, section=None):
    q = client().table("cv_entry").select(CV_ENTRY_SELECT)
    if year not in (None, "All"):
        q = q.eq("cv_year", int(year))
    if status not in (None, "All"):
        q = q.eq("status", status)
    if section not in (None, "All"):
        q = q.eq("cv_section", section)
    return (q.order("entry_date", desc=True)
             .order("created_at", desc=True).execute().data or [])


def cv_entries(year=None, status=None, section=None):
    return _cv_entries(_uid(), year, status, section)

