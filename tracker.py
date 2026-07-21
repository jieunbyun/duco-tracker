"""
tracker.py — the research group time & project tracker.

Run locally:
    pip install streamlit supabase
    cd app && streamlit run tracker.py

Sections:
    Log       — fast session entry (the thing you do daily)
    Projects  — time spent per project vs estimate (the tracker)
    Time      — proportion of time by high category, + project forecast

All data is scoped by Row-Level Security to the signed-in user.
"""
from __future__ import annotations
import datetime as dt
import streamlit as st
import plotly.graph_objects as go
import db
from streamlit_local_storage import LocalStorage

st.set_page_config(page_title="Group Tracker", page_icon="◳", layout="wide")

# ---------------------------------------------------------------------------
# Signature styling: measured rules, monospace numerals, quiet chrome.
# One bold place (the section eyebrow + rule); everything else disciplined.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  /* tabular monospace for all the numbers that matter */
  [data-testid="stMetricValue"] { font-family: "SF Mono", ui-monospace, monospace;
      font-weight: 600; letter-spacing: -0.02em; }
  /* eyebrow label above each section */
  .eyebrow { font-family: ui-monospace, monospace; font-size: 0.72rem;
      letter-spacing: 0.18em; text-transform: uppercase; color: #3A5A78;
      border-top: 2px solid #1F2933; padding-top: 6px; margin: 6px 0 2px 0;
      display: inline-block; }
  .section-title { font-family: Georgia, serif; font-size: 1.55rem;
      font-weight: 600; color: #1F2933; margin: 0 0 2px 0; }
  .section-sub { color: #6b7280; font-size: 0.9rem; margin-bottom: 14px; }
  /* hairline dividers, no rounded chrome */
  hr { border: none; border-top: 1px solid #d9d5cc; margin: 1.2rem 0; }
  /* progress bars in the slate accent */
  .stProgress > div > div > div > div { background-color: #3A5A78; }
</style>
""", unsafe_allow_html=True)


def edit_session_widget(s, key_prefix):
    """A compact editor for one session: category, project, date, start, end,
    delete. `s` is a row from recent_sessions/sessions_in_range with id,
    category_label, project_name, started_at, ended_at. Returns True if a
    change was made (caller should rerun)."""
    sid = s["id"]
    try:
        cur_start = dt.datetime.fromisoformat(s["started_at"]) \
            if s.get("started_at") else None
    except Exception:
        cur_start = None
    try:
        cur_end = dt.datetime.fromisoformat(s["ended_at"]) \
            if s.get("ended_at") else None
    except Exception:
        cur_end = None

    # category + project selectors, prefilled to the current values
    cats = db.categories()  # all domains, so any session's category resolves
    cat_labels = {c["label"]: c["id"] for c in cats}
    cur_cat = s.get("category_label")
    cat_keys = list(cat_labels.keys())
    cat_idx = cat_keys.index(cur_cat) if cur_cat in cat_keys else 0

    cc1, cc2 = st.columns(2)
    with cc1:
        new_cat = st.selectbox("Category", cat_keys, index=cat_idx,
                               key=f"{key_prefix}_cat_{sid}")
    # project list filtered to the chosen category (one category per project)
    matching = db.projects_for_category(cat_labels[new_cat])
    proj_labels = {"— none —": None}
    proj_labels.update({p["name"]: p["id"] for p in matching})
    cur_proj = s.get("project_name") or "— none —"
    proj_keys = list(proj_labels.keys())
    # if the session's current project isn't in this category's list, still
    # show it so we don't misrepresent the current value
    if cur_proj not in proj_keys:
        proj_keys = [cur_proj] + proj_keys
        proj_labels[cur_proj] = None  # resolved on save only if changed
    proj_idx = proj_keys.index(cur_proj) if cur_proj in proj_keys else 0
    with cc2:
        new_proj = st.selectbox("Project", proj_keys, index=proj_idx,
                                key=f"{key_prefix}_proj_{sid}")

    # milestone selector, filtered to the chosen project's milestones
    new_ms_id = s.get("milestone_id")
    chosen_pid = proj_labels.get(new_proj)
    if chosen_pid:
        pms = db.project_milestones(chosen_pid)
        ms_labels = {"— none —": None}
        # include open milestones, plus the currently-assigned one (even if done)
        for m in pms:
            if m["status"] != "done" or m["id"] == s.get("milestone_id"):
                ms_labels[m["title"]] = m["id"]
        cur_ms_title = s.get("milestone_title") or "— none —"
        ms_keys = list(ms_labels.keys())
        if cur_ms_title not in ms_keys:
            cur_ms_title = "— none —"
        ms_idx = ms_keys.index(cur_ms_title)
        ms_pick = st.selectbox("Milestone", ms_keys, index=ms_idx,
                               key=f"{key_prefix}_ms_{sid}")
        new_ms_id = ms_labels[ms_pick]
    else:
        # no project selected -> no milestone
        new_ms_id = None

    # the selectors above stay live (category filters projects -> milestones).
    # the date/time fields you type into go in a form, so typing doesn't re-run
    # the page on every keystroke.
    with st.form(f"{key_prefix}_editform_{sid}"):
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            new_date = st.date_input(
                "Date", value=(cur_start.date() if cur_start
                               else dt.date.fromisoformat(s["session_date"])),
                key=f"{key_prefix}_date_{sid}")
        with ec2:
            _sp = st.time_input(
                "Start", value=(cur_start.time() if cur_start
                                else dt.time(9, 0)),
                key=f"{key_prefix}_start_{sid}")
            _st_raw = st.text_input(
                "or type", key=f"{key_prefix}_starttype_{sid}",
                placeholder="0930")
            new_start = parse_time_str(_st_raw) or _sp
        with ec3:
            _ep = st.time_input(
                "End", value=(cur_end.time() if cur_end else dt.time(10, 0)),
                key=f"{key_prefix}_end_{sid}")
            _et_raw = st.text_input(
                "or type", key=f"{key_prefix}_endtype_{sid}",
                placeholder="1100")
            new_end = parse_time_str(_et_raw) or _ep
        save_change = st.form_submit_button("Save change", type="primary")

    b1, b2 = st.columns(2)
    with b1:
        if save_change:
            started, ended, err = resolve_block_times(
                new_date, new_start, new_end)
            if err:
                st.error(err)
            else:
                # only write fields the user actually changed, so editing one
                # thing (e.g. category) never disturbs another (e.g. project)
                changes = {}
                if new_cat != cur_cat:
                    changes["category_id"] = cat_labels[new_cat]
                if new_proj != cur_proj:
                    changes["project_id"] = proj_labels[new_proj]
                    # if the project changed, the old milestone no longer
                    # applies; set whatever the milestone selector now shows
                    changes["milestone_id"] = new_ms_id
                elif new_ms_id != s.get("milestone_id"):
                    changes["milestone_id"] = new_ms_id
                # times: write only if the date or either time moved
                orig_start_iso = (cur_start.isoformat() if cur_start else None)
                orig_end_iso = (cur_end.isoformat() if cur_end else None)
                if started != orig_start_iso or ended != orig_end_iso:
                    changes["started_at"] = started
                    changes["ended_at"] = ended
                    changes["manual_minutes"] = None
                if not changes:
                    st.info("Nothing changed.")
                else:
                    try:
                        db.update_session(sid, changes)
                        st.success("Updated.")
                        db.clear_user_caches()
                        return True
                    except Exception as e:
                        st.error(f"Could not update. {e}")
    with b2:
        if st.button("Delete", key=f"{key_prefix}_del_{sid}"):
            try:
                db.delete_session(sid)
                st.success("Deleted.")
                db.clear_user_caches()
                return True
            except Exception as e:
                st.error(f"Could not delete. {e}")

    # ---- duplicate this session (optionally to another date) ----
    with st.popover("Duplicate", use_container_width=False):
        st.caption("Make a copy, optionally on another date. Same category, "
                   "project, time, and note.")
        dup_date = st.date_input(
            "Copy to date",
            value=(cur_start.date() if cur_start
                   else dt.date.fromisoformat(s["session_date"])),
            key=f"{key_prefix}_dupdate_{sid}")
        if st.button("Create copy", key=f"{key_prefix}_dup_{sid}",
                     type="primary"):
            try:
                db.duplicate_session(sid, dup_date.isoformat())
                st.success("Copied.")
                db.clear_user_caches()
                return True
            except Exception as e:
                st.error(f"Could not duplicate. {e}")
    return False


def parse_time_str(raw):
    """Parse a flexibly-typed time string into a dt.time, or None if blank /
    unparseable. Accepts '0930', '9:30', '930', '9', '09:30', '9.30', '9 30'."""
    if not raw or not raw.strip():
        return None
    s = raw.strip().replace(".", ":").replace(" ", ":")
    try:
        if ":" in s:
            parts = s.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 0
        else:
            digits = "".join(ch for ch in s if ch.isdigit())
            if len(digits) <= 2:           # "9" or "09" -> 09:00
                h, m = int(digits), 0
            elif len(digits) == 3:         # "930" -> 9:30
                h, m = int(digits[0]), int(digits[1:])
            else:                          # "0930"/"1430" -> hh:mm
                h, m = int(digits[:2]), int(digits[2:4])
        if h == 24 and m == 0:
            return dt.time(0, 0)           # midnight end-of-day
        if 0 <= h <= 23 and 0 <= m <= 59:
            return dt.time(h, m)
    except (ValueError, IndexError):
        return None
    return None


def time_field(label, default, key):
    """A time picker plus a small 'or type' box accepting 0930 / 9:30 / 930.
    If the type box is filled and valid, it wins; otherwise the picker value
    is used. Returns a dt.time. Stacks vertically so it is safe inside an
    existing column (Streamlit disallows nesting columns more than one deep)."""
    picked = st.time_input(label, value=default, key=f"{key}_pick")
    typed_raw = st.text_input("or type", key=f"{key}_type",
                              placeholder="0930",
                              label_visibility="collapsed")
    typed = parse_time_str(typed_raw)
    if typed_raw and typed is None:
        st.caption(f"⚠ couldn't read “{typed_raw}”")
    return typed or picked


def resolve_block_times(day, start, end):
    """Return (started_iso, ended_iso, error). An end time of 00:00 is treated
    as midnight at the END of the day (so 23:00–00:00 is a one-hour block).
    Any other end at or before the start is an error."""
    start_dt = dt.datetime.combine(day, start)
    if end == dt.time(0, 0):
        # midnight at the end of the day
        end_dt = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0))
    else:
        end_dt = dt.datetime.combine(day, end)
    if end_dt <= start_dt:
        return None, None, "End must be after start (use 00:00 for midnight)."
    return start_dt.isoformat(), end_dt.isoformat(), None



CV_DESTINATIONS = {
    "Impact — Software, Tools, and Datasets":
        ("Impact", "Software, Tools, and Datasets"),
    "Impact — Community & Stakeholder Engagement and Outreach":
        ("Impact", "Community & Stakeholder Engagement and Outreach"),
    "Impact — Knowledge Transfer and Capacity Building":
        ("Impact", "Knowledge Transfer and Capacity Building"),
    "Impact — Commercialisation":
        ("Impact", "Commercialisation"),
    "Impact — Policy and Practice Influence":
        ("Impact", "Policy and Practice Influence"),
    "Teaching — Courses":
        ("Teaching", "Courses"),
    "Leadership — University Leadership Roles":
        ("Leadership, Management & Engagement", "University Leadership Roles"),
    "Leadership — Conference Session Organisation":
        ("Leadership, Management & Engagement", "Conference Session Organisation"),
    "Leadership — Development of Team, Staff & Students":
        ("Leadership, Management & Engagement", "Development of Team, Staff & Students"),
    "Esteem — Honours and Awards":
        ("Esteem", "Honours and Awards"),
    "Esteem — Invited Talks & Keynotes":
        ("Esteem", "Invited Talks & Keynotes"),
    "Esteem — Editorial and Reviewing Roles":
        ("Esteem", "Editorial and Reviewing Roles"),
    "Esteem — Professional Service":
        ("Esteem", "Professional Service to Learned Societies & Public Bodies"),
    "Esteem — Media coverage":
        ("Esteem", "Media coverage"),
    "Esteem — Hosting":
        ("Esteem", "Hosting"),
    "Grants":
        ("Grants", None),
    "Grants — Submitted":
        ("Grants - Submitted", None),
    "Supervision":
        ("Supervision", None),
    "Publications":
        ("Publications", None),
    "Training":
        ("Training", None),
    "Admin — University": 
        ("Admin", "University"),
    "Admin — External": 
        ("Admin", "External"),
    "Other":
        ("Other", None),
}
CV_STATUS_OPTIONS = ["draft", "ready", "added_to_cv", "archived"]
CV_SOURCE_OPTIONS = ["manual", "session", "milestone", "project"]


def cv_destination_parts(label):
    return CV_DESTINATIONS.get(label, ("Other", None))


def cv_destination_label(section_name, subsection_name=None):
    for label, (sec, sub) in CV_DESTINATIONS.items():
        if sec == section_name and sub == subsection_name:
            return label
    for label, (sec, _sub) in CV_DESTINATIONS.items():
        if sec == section_name:
            return label
    return "Other"


def tex_escape(value):
    """Minimal LaTeX escaping for copied CV snippets."""
    if value is None:
        return ""
    s = str(value)
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
        "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in s)


def cv_entry_latex(entry):
    title = tex_escape(entry.get("title"))
    date_label = tex_escape(entry.get("entry_date") or str(entry.get("cv_year") or ""))
    bullets = []
    for key in ("description", "outcome", "metrics"):
        val = (entry.get(key) or "").strip()
        if val:
            bullets.extend([line.strip(" -") for line in val.splitlines()
                            if line.strip()])
    if entry.get("evidence_url"):
        bullets.append("Evidence: \\url{" + tex_escape(entry["evidence_url"]) + "}")
    if len(bullets) <= 1:
        body = tex_escape(bullets[0]) if bullets else ""
        return f"\\begin{{jobshort}}{{{title}}}{{{date_label}}}\n{body}\n\\end{{jobshort}}"
    lines = [f"\\begin{{joblong}}{{{title}}}{{{date_label}}}"]
    lines.extend([f"\\item {tex_escape(b)}" for b in bullets])
    lines.append("\\end{joblong}")
    return "\n".join(lines)


def cv_entries_latex(entries):
    if not entries:
        return ""
    # Preserve the CV's section/subsection hierarchy in the export.
    grouped = {}
    for e in entries:
        grouped.setdefault((e.get("cv_section") or "Other",
                            e.get("cv_subsection") or ""), []).append(e)
    chunks = []
    current_section = None
    for (sec, sub), rows in sorted(grouped.items()):
        if sec != current_section:
            chunks.append(f"\\section{{{tex_escape(sec)}}}")
            current_section = sec
        if sub:
            chunks.append(f"\\subsection*{{{tex_escape(sub)}}}")
        chunks.extend(cv_entry_latex(e) for e in rows)
    return "\n\n".join(chunks)


def save_cv_entry_from_values(user_id, entry_date, destination_label, title,
                              organisation=None, location=None, role=None,
                              description=None, outcome=None, metrics=None,
                              evidence_url=None, status="draft",
                              source_type="manual", session_id=None,
                              milestone_id=None, project_id=None):
    section_name, subsection_name = cv_destination_parts(destination_label)
    return db.add_cv_entry(
        user_id=user_id,
        entry_date=entry_date.isoformat() if hasattr(entry_date, "isoformat") else entry_date,
        cv_section=section_name,
        cv_subsection=subsection_name,
        title=title,
        organisation=organisation,
        location=location,
        role=role,
        description=description,
        outcome=outcome,
        metrics=metrics,
        evidence_url=evidence_url,
        status=status,
        source_type=source_type,
        session_id=session_id,
        milestone_id=milestone_id,
        project_id=project_id,
    )


def section(eyebrow: str, title: str, sub: str = ""):
    st.markdown(f'<span class="eyebrow">{eyebrow}</span>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="section-sub">{sub}</div>', unsafe_allow_html=True)


def period_range(choice, today=None):
    """Return (from_date, to_date, label) for a named period.

    Week runs Saturday to Friday (matching the Week calendar). Month and Year
    are the calendar month/year containing today. 'Custom' is handled by the
    caller with date pickers.
    """
    today = today or dt.date.today()
    if choice == "This week":
        # most recent Saturday: weekday() has Mon=0..Sat=5, so days since the
        # last Saturday = (weekday - 5) mod 7.
        days_since_sat = (today.weekday() - 5) % 7
        start = today - dt.timedelta(days=days_since_sat)     # Saturday
        end = start + dt.timedelta(days=6)                    # following Friday
        return start, end, f"{start:%d %b} - {end:%d %b %Y}"
    if choice == "This month":
        start = today.replace(day=1)
        nxt = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        end = nxt - dt.timedelta(days=1)
        return start, end, f"{start:%B %Y}"
    if choice == "This year":
        return dt.date(today.year, 1, 1), dt.date(today.year, 12, 31), str(today.year)
    return None, None, "Custom"


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
def auth_gate():
    section("Sign in", "Group Tracker",
            "Time and project tracking for the research group.")
    localS = LocalStorage()
    saved_email = localS.getItem("tracker_email")

    tab_in, tab_up = st.tabs(["Sign in", "Create account"])
    with tab_in:
        email = st.text_input("Email", value=saved_email or "", key="in_email")
        pw = st.text_input("Password", type="password", key="in_pw")
        if st.button("Sign in", type="primary"):
            try:
                db.sign_in(email, pw)
                localS.setItem("tracker_email", email)  # remember for next time
                st.rerun()
            except Exception as e:
                st.error(f"Could not sign in. {e}")
                
    with tab_up:
        email2 = st.text_input("Email", key="up_email")
        pw2 = st.text_input("Password", type="password", key="up_pw",
                            help="At least 6 characters.")
        if st.button("Create account"):
            try:
                db.sign_up(email2, pw2)
                st.success("Account created. Check your email if confirmation is on, "
                           "then sign in.")
            except Exception as e:
                st.error(f"Could not create account. {e}")


def link_gate(_app_user_none):
    """Signed in to Supabase but no app_user row is linked to this login yet."""
    section("One-time setup", "Link your login",
            "Your sign-in needs to be connected to a person in the group.")
    users = db.client().table("app_user").select("id,full_name,email,auth_user_id") \
        .execute().data or []
    unlinked = [u for u in users if not u.get("auth_user_id")]
    if not unlinked:
        st.info("No unlinked person records. Ask the group lead to add you to "
                "app_user, then sign in again.")
        return
    labels = {f'{u["full_name"]} ({u.get("email") or "no email"})': u["id"]
              for u in unlinked}
    choice = st.selectbox("Which person are you?", list(labels.keys()))
    if st.button("Link my login", type="primary"):
        try:
            db.link_my_login(labels[choice])
            st.success("Linked. Loading your tracker…")
            st.rerun()
        except Exception as e:
            st.error(f"Could not link. {e}")


# ---------------------------------------------------------------------------
# Section: Log a session
# ---------------------------------------------------------------------------
def view_log(me):
    section("Log", "Log a session", "Record time as you finish a block of work.")

    # work/life toggle — life is the lead's private domain only
    is_lead = me.get("role") == "lead"
    log_domain = "work"
    if is_lead:
        log_domain = st.radio("Domain", ["Work", "Life"], horizontal=True,
                              key="log_domain",
                              help="Life categories are personal and private "
                                   "to you.").lower()

    cats = db.categories(domain=log_domain)
    cat_labels = {c["label"]: c["id"] for c in cats}
    life_mode = (log_domain == "life")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.selectbox("Category", list(cat_labels.keys()))
        chosen_cat_id = cat_labels[cat]
        # project list is filtered to the chosen category (one category per
        # project). Life is never project-tied.
        proj = "— none —"
        new_proj_name = ""
        new_proj_vis = "private"
        milestone_id = None
        if not life_mode:
            matching = db.projects_for_category(chosen_cat_id)
            proj_labels = {"— none —": None}
            proj_labels.update({p["name"]: p["id"] for p in matching})
            proj_labels["+ New project…"] = "__new__"
            proj = st.selectbox(
                "Project", list(proj_labels.keys()),
                help="Shows projects in the chosen category. New projects are "
                     "auto-linked to this category.")
            if proj == "+ New project…":
                new_proj_name = st.text_input("New project name",
                                              placeholder="e.g. DAFNI Fellowship")
                new_proj_vis = st.radio("Visibility", ["private", "group"],
                                        horizontal=True, key="newproj_vis",
                                        help="This project will belong to the "
                                             "'" + cat + "' category. Add details "
                                             "in the Projects tab later.")
            elif proj != "— none —":
                # inline high-importance toggle for the chosen project
                cur_imp = next((p.get("high_importance") for p in matching
                                if p["name"] == proj), False)
                new_imp = st.checkbox("⭐ High importance", value=bool(cur_imp),
                                      key=f"imp_log_{proj_labels[proj]}",
                                      help="Highlights this project's hours in "
                                           "the Time tab.")
                if new_imp != bool(cur_imp):
                    db.set_project_importance(proj_labels[proj], new_imp)
                    db.clear_user_caches()
                    st.rerun()
        # optional milestone, filtered to the chosen existing project.
        new_ms_name = ""
        if not life_mode and proj not in ("— none —", "+ New project…"):
            chosen_pid = proj_labels[proj]
            ms = db.project_milestones(chosen_pid)
            open_ms = [m for m in ms if m["status"] != "done"]
            ms_labels = {"— none —": None}
            ms_labels.update({m["title"]: m["id"] for m in open_ms})
            ms_labels["+ New milestone…"] = "__new__"
            ms_pick = st.selectbox("Milestone (optional)",
                                   list(ms_labels.keys()),
                                   help="Tag this session to a milestone to "
                                        "accumulate your own hours toward it.")
            if ms_pick == "+ New milestone…":
                new_ms_name = st.text_input("New milestone name",
                                            placeholder="e.g. First draft",
                                            key="log_new_ms")
                milestone_id = "__new__"
            else:
                milestone_id = ms_labels[ms_pick]

    # The selectors above stay live (category filters projects, etc). The
    # fields you TYPE into go in a form, so typing no longer re-runs the page
    # on every keystroke — the page only re-runs when you click Save.
    with col2:
        log_cv_enabled = st.checkbox(
            "Record this session as a CV achievement",
            key="log_cv_enabled",
            help="Optional. Saved as a private CV record linked to this session.")
        with st.form("log_entry_form"):
            day = st.date_input("Date", value=dt.date.today())
            mode = st.radio("Duration", ["Start & end time", "Just minutes"],
                            horizontal=True)
            t_start = time_field("Start", dt.time(9, 0), "log_start")
            t_end = time_field("End", dt.time(10, 0), "log_end")
            minutes_val = st.number_input(
                "Minutes (used if 'Just minutes' is chosen)", min_value=1,
                max_value=960, value=30, step=5)
            desc = st.text_input("Note (optional)")
            log_cv_dest = log_cv_title = log_cv_desc = log_cv_outcome = None
            log_cv_metrics = log_cv_evidence = log_cv_status = None
            if log_cv_enabled:
                st.markdown("**CV achievement**")
                log_cv_dest = st.selectbox(
                    "CV destination", list(CV_DESTINATIONS.keys()),
                    key="log_cv_dest")
                log_cv_title = st.text_input(
                    "Achievement title", key="log_cv_title",
                    placeholder="e.g. Delivered stakeholder meeting with Network Rail")
                log_cv_desc = st.text_area(
                    "Description / draft bullet", key="log_cv_desc", height=80,
                    placeholder="Short note you may later polish into a CV bullet.")
                log_cv_outcome = st.text_input(
                    "Outcome (optional)", key="log_cv_outcome",
                    placeholder="e.g. agreed data access route, workshop delivered")
                log_cv_metrics = st.text_input(
                    "Metrics (optional)", key="log_cv_metrics",
                    placeholder="e.g. audience c. 30, £10,000, 2-day tutorial")
                log_cv_evidence = st.text_input(
                    "Evidence URL (optional)", key="log_cv_evidence")
                log_cv_status = st.selectbox(
                    "Status", CV_STATUS_OPTIONS, index=0, key="log_cv_status")
            submitted = st.form_submit_button("Save session", type="primary")
        if mode == "Start & end time":
            minutes = None
        else:
            minutes = minutes_val
            t_end = None

    if submitted:
        if t_end is not None:
            # timed mode: resolve with midnight-aware helper
            started, ended, err = resolve_block_times(day, t_start, t_end)
            if err:
                st.error(err)
                return
        else:
            # manual-minutes mode: no end time
            started = dt.datetime.combine(day, t_start).isoformat()
            ended = None

        # resolve the project: life mode has none; work mode resolves the pick
        project_id = None
        if not life_mode:
            project_id = proj_labels[proj]
            if proj == "+ New project…":
                if not new_proj_name.strip():
                    st.error("Give the new project a name, or pick an existing one.")
                    return
                try:
                    # auto-link the new project to the chosen category
                    project_id, created = db.get_or_create_project(
                        new_proj_name, me["id"], new_proj_vis,
                        category_id=chosen_cat_id)
                    if created:
                        st.info(f"Created project “{new_proj_name.strip()}” "
                                f"in the '{cat}' category. Add its estimate and "
                                f"milestones in the Projects tab whenever you like.")
                except Exception as e:
                    st.error(f"Could not create the project. {e}")
                    return

        # create a new milestone inline if "+ New milestone" was chosen
        if milestone_id == "__new__":
            if not new_ms_name.strip():
                st.error("Give the new milestone a name, or pick one.")
                return
            try:
                res = db.add_milestone(project_id, new_ms_name.strip())
                milestone_id = res.data[0]["id"]
            except Exception as e:
                st.error(f"Could not create the milestone. {e}")
                return

        try:
            res = db.log_session(
                user_id=me["id"], category_id=cat_labels[cat],
                started_at=started, ended_at=ended, manual_minutes=minutes,
                project_id=project_id, description=desc or None,
                milestone_id=milestone_id)
            cv_saved = False
            if log_cv_enabled:
                session_id = (res.data or [{}])[0].get("id") if res else None
                title_source = (log_cv_title or "").strip() or (desc or "").strip()
                if not title_source:
                    title_source = (new_ms_name.strip() if milestone_id else "") or                         (new_proj_name.strip() if proj == "+ New project…" else proj)
                title_source = title_source if title_source and title_source != "— none —" else cat
                save_cv_entry_from_values(
                    user_id=me["id"], entry_date=day,
                    destination_label=log_cv_dest or "Other",
                    title=title_source,
                    description=log_cv_desc,
                    outcome=log_cv_outcome,
                    metrics=log_cv_metrics,
                    evidence_url=log_cv_evidence,
                    status=log_cv_status or "draft",
                    source_type="session" if session_id else "manual",
                    session_id=session_id,
                    milestone_id=milestone_id,
                    project_id=project_id)
                cv_saved = True
            st.success("Session saved" + (" and CV achievement recorded." if cv_saved else "."))
            db.clear_user_caches()
        except Exception as e:
            st.error(f"Could not save. {e}")

    st.markdown("<hr>", unsafe_allow_html=True)
    rows = db.recent_sessions(12)
    # work/life split of these recent sessions
    if rows:
        cat_domain = {c["id"]: c.get("domain", "work") for c in db.categories()}
        w = sum((r.get("hours") or 0) for r in rows
                if cat_domain.get(r.get("category_id")) != "life")
        l = sum((r.get("hours") or 0) for r in rows
                if cat_domain.get(r.get("category_id")) == "life")
        if me.get("role") == "lead":
            mc1, mc2 = st.columns(2)
            mc1.metric("Work (recent)", f"{w:g} h")
            mc2.metric("Life (recent)", f"{l:g} h")
    st.markdown("**Recent sessions** — select one to edit or delete it")
    if rows:
        labels = {}
        for s in rows:
            when = s.get("session_date", "")
            t = ""
            if s.get("started_at") and s.get("ended_at"):
                t = f" {s['started_at'][11:16]}–{s['ended_at'][11:16]}"
            label = (f"{when}{t} · {s.get('category_label','')}"
                     + (f" · {s['project_name']}" if s.get("project_name") else "")
                     + f" · {s.get('hours','')}h")
            labels[label] = s
        pick = st.selectbox("Recent session", list(labels.keys()),
                            key="recent_session_pick")
        chosen = labels[pick]
        if chosen.get("description"):
            st.caption(chosen["description"])
        if chosen.get("started_at") and chosen.get("ended_at"):
            if edit_session_widget(chosen, "log"):
                st.rerun()
        else:
            st.caption("This was logged as minutes (no clock time), so it "
                       "can't be edited on the time grid. Delete and re-add "
                       "it if the time is wrong.")
            if st.button("Delete", key=f"logdel_{chosen['id']}"):
                db.delete_session(chosen["id"])
                db.clear_user_caches()
                st.rerun()
    else:
        st.caption("No sessions yet. Your first one will appear here.")


# ---------------------------------------------------------------------------
# Section: Week (look ahead, plan, keep actuals current)
# ---------------------------------------------------------------------------
def view_week(me):
    section("Week", "Plan & track the week",
            "Future blocks are plans; past blocks are what happened. "
            "One calendar, kept current.")

    # week navigation, Saturday-anchored (week runs Sat -> Fri)
    if "week_offset" not in st.session_state:
        st.session_state.week_offset = 0
    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("← Previous"):
            st.session_state.week_offset -= 1
    with nav3:
        if st.button("Next →"):
            st.session_state.week_offset += 1
    today = dt.date.today()
    # most recent Saturday: Python weekday() has Mon=0..Sun=6, Sat=5.
    # days since the last Saturday = (weekday - 5) mod 7.
    days_since_sat = (today.weekday() - 5) % 7
    week_start = today - dt.timedelta(days=days_since_sat) \
        + dt.timedelta(weeks=st.session_state.week_offset)
    week_end = week_start + dt.timedelta(days=6)   # the following Friday
    days = [week_start + dt.timedelta(days=i) for i in range(7)]
    with nav2:
        st.markdown(f"<div style='text-align:center;font-weight:600;'>"
                    f"{week_start:%d %b} – {week_end:%d %b %Y}</div>",
                    unsafe_allow_html=True)
        if st.session_state.week_offset != 0:
            if st.button("Jump to this week", use_container_width=True):
                st.session_state.week_offset = 0
                st.rerun()

    rows = db.sessions_in_range(week_start.isoformat(), week_end.isoformat())
    is_lead = me.get("role") == "lead"

    # Domain (work/life) per session, via the category map. Life categories are
    # private to the lead, so non-lead users only load work categories here.
    domain_cats = db.categories() if is_lead else db.categories(domain="work")
    cat_domain = {c["id"]: c.get("domain", "work") for c in domain_cats}
    for r in rows:
        r["domain"] = cat_domain.get(r.get("category_id"), "work")
    # group blocks by day
    by_day = {d.isoformat(): [] for d in days}
    for r in rows:
        d = r.get("session_date")
        if d in by_day and r.get("started_at") and r.get("ended_at"):
            by_day[d].append(r)

    # render the 7 days as columns
    cols = st.columns(7)
    for i, d in enumerate(days):
        with cols[i]:
            is_today = d == today
            is_future = d > today
            head = f"{d:%a}<br><span style='font-size:1.3em'>{d.day}</span>"
            colour = "#3A5A78" if is_today else "#6b7280"
            st.markdown(f"<div style='text-align:center;color:{colour};"
                        f"font-family:ui-monospace,monospace;font-size:0.8rem;"
                        f"border-top:2px solid {colour};padding-top:4px'>"
                        f"{head}</div>", unsafe_allow_html=True)
            day_rows = sorted(by_day[d.isoformat()],
                              key=lambda x: x["started_at"])
            day_total = 0
            day_work = 0
            day_life = 0
            for r in day_rows:
                t0 = r["started_at"][11:16]
                t1 = r["ended_at"][11:16]
                hrs = r.get("hours") or 0
                day_total += hrs
                is_life = r.get("domain") == "life"
                if is_life:
                    day_life += hrs
                else:
                    day_work += hrs
                tag = "plan" if is_future else "actual"
                label = r.get("project_name") or r.get("category_label")
                # work = blue (prominent), life = grey (recessive);
                # future (planned) is a lighter shade of each
                if is_life:
                    bar = "#9aa5b1" if not is_future else "#c4cad1"
                    bg = "#F2F2F0"
                else:
                    bar = "#3A5A78" if not is_future else "#9fb2c4"
                    bg = "#EAF0F6"
                st.markdown(
                    f"<div style='background:{bg};border-left:3px solid "
                    f"{bar};padding:3px 6px;"
                    f"margin:3px 0;font-size:0.72rem;border-radius:2px'>"
                    f"<b>{t0}-{t1}</b><br>{label}"
                    f"<br><span style='color:#9aa5b1'>{tag}</span></div>",
                    unsafe_allow_html=True)
            if day_total:
                # total with work/life split, e.g. "24h (12h / 12h)"
                split = (f" <span style='color:#9aa5b1'>"
                         f"({day_work:g} / {day_life:g})</span>"
                         if day_life else "")
                st.markdown(f"<div style='text-align:center;font-size:0.72rem;"
                            f"color:#6b7280'>{day_total:g} h{split}</div>",
                            unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ---- weekly to-do list ----
    st.markdown("**To-do this week**")
    todos = db.todos_in_range(week_start.isoformat(), week_end.isoformat())
    proj_name = {p["id"]: p["name"] for p in db.my_projects()}
    if todos:
        # ensure distinct order values so up/down swaps are unambiguous
        if len({t.get("sort_order") for t in todos}) < len(todos):
            for i, t in enumerate(todos):
                db.set_todo_order(t["id"], i)
                t["sort_order"] = i
        n = len(todos)
        for i, t in enumerate(todos):
            tc1, tc2, tc3, tc4 = st.columns([4.2, 1.9, 1.4, 1.8])
            overdue = (not t["is_done"]
                       and dt.date.fromisoformat(t["due_on"]) < week_start)
            important = bool(t.get("is_important"))
            with tc1:
                label = ("⭐ " + t["title"]) if important else t["title"]
                checked = st.checkbox(
                    label, value=t["is_done"], key=f"todo_{t['id']}")
                if checked != t["is_done"]:
                    db.set_todo_done(t["id"], checked)
                    db.clear_user_caches()
                    st.rerun()
                if t.get("note"):
                    st.markdown(
                        f"<div style='font-size:0.72rem;color:#6b7280;"
                        f"margin:-6px 0 4px 28px'>{t['note']}</div>",
                        unsafe_allow_html=True)
            with tc2:
                bits = []
                if overdue:
                    bits.append("carried")
                est = t.get("est_hours")
                if est:
                    bits.append(f"{est:g}h")
                pn = proj_name.get(t.get("project_id"))
                if pn:
                    bits.append(pn)
                if bits:
                    st.caption(" · ".join(bits))
            with tc3:
                # up / down reorder, side by side to save vertical space
                ua, da = st.columns(2)
                with ua:
                    up = st.button("↑", key=f"tdup_{t['id']}",
                                   disabled=(i == 0), help="Move up")
                with da:
                    dn = st.button("↓", key=f"tddn_{t['id']}",
                                   disabled=(i == n - 1), help="Move down")
                if up and i > 0:
                    above = todos[i - 1]
                    db.set_todo_order(t["id"], above["sort_order"])
                    db.set_todo_order(above["id"], t["sort_order"])
                    db.clear_user_caches()
                    st.rerun()
                if dn and i < n - 1:
                    below = todos[i + 1]
                    db.set_todo_order(t["id"], below["sort_order"])
                    db.set_todo_order(below["id"], t["sort_order"])
                    db.clear_user_caches()
                    st.rerun()
            with tc4:
                sr, ed, dl = st.columns(3)
                with sr:
                    star = "★" if important else "☆"
                    if st.button(star, key=f"tdimp_{t['id']}",
                                 help="Toggle high importance"):
                        db.set_todo_important(t["id"], not important)
                        db.clear_user_caches()
                        st.rerun()
                with ed:
                    edit_pop = st.popover("✎", help="Edit")
                with dl:
                    if st.button("✕", key=f"tddel_{t['id']}", help="Delete"):
                        db.delete_todo(t["id"])
                        db.clear_user_caches()
                        st.rerun()
                with edit_pop:
                    with st.form(f"tded_form_{t['id']}"):
                        e_title = st.text_input("Title", value=t["title"],
                                                key=f"tded_title_{t['id']}")
                        e_note = st.text_area("Note", value=t.get("note") or "",
                                              key=f"tded_note_{t['id']}",
                                              height=70)
                        e_hours = st.number_input(
                            "Estimated hours", min_value=0.0, step=0.5,
                            value=float(t.get("est_hours") or 0),
                            key=f"tded_hours_{t['id']}")
                        e_projs = {"— no project —": None}
                        e_projs.update({p["name"]: p["id"]
                                        for p in db.my_projects()})
                        cur_pn = proj_name.get(t.get("project_id")) \
                            or "— no project —"
                        e_keys = list(e_projs.keys())
                        e_idx = e_keys.index(cur_pn) if cur_pn in e_keys else 0
                        e_proj = st.selectbox("Project", e_keys, index=e_idx,
                                              key=f"tded_proj_{t['id']}")
                        e_imp = st.checkbox("⭐ High importance",
                                            value=important,
                                            key=f"tded_imp_{t['id']}")
                        # start-week picker: Saturday-anchored weeks around
                        # this to-do's current week (8 back, 26 ahead). Moving
                        # it re-files the to-do under the chosen week.
                        _d = dt.date.fromisoformat(t["due_on"])
                        cur_week = _d - dt.timedelta(
                            days=(_d.weekday() - 5) % 7)
                        week_opts = [cur_week + dt.timedelta(weeks=w)
                                     for w in range(-8, 27)]
                        e_week = st.selectbox(
                            "Start week", week_opts, index=8,
                            format_func=lambda w: f"{w:%d %b} – "
                            f"{w + dt.timedelta(days=6):%d %b %Y}",
                            key=f"tded_week_{t['id']}")
                        tded_submit = st.form_submit_button(
                            "Save", type="primary")
                        if tded_submit and e_title.strip():
                            db.update_todo(t["id"], {
                                "title": e_title.strip(),
                                "note": e_note.strip() or None,
                                "est_hours": e_hours or None,
                                "project_id": e_projs[e_proj],
                                "is_important": e_imp,
                                "due_on": e_week.isoformat()})
                            db.clear_user_caches()
                            st.rerun()
                        elif tded_submit:
                            st.error("Title can't be empty.")
        # estimated-hours totals (all, and just what's still open)
        est_all = sum((t.get("est_hours") or 0) for t in todos)
        est_open = sum((t.get("est_hours") or 0) for t in todos
                       if not t["is_done"])
        est_done = est_all - est_open
        if est_all:
            st.caption(f"Estimated effort: {est_open:g} h remaining "
                       f"of {est_all:g} h planned ({est_done:g} h done)")
        # high-importance subset, shown alongside the overall totals
        if any(t.get("is_important") for t in todos):
            est_imp = sum((t.get("est_hours") or 0) for t in todos
                          if t.get("is_important"))
            est_imp_open = sum((t.get("est_hours") or 0) for t in todos
                               if t.get("is_important") and not t["is_done"])
            est_imp_done = est_imp - est_imp_open
            st.caption(f"⭐ High importance: {est_imp_open:g} h remaining "
                       f"of {est_imp:g} h planned ({est_imp_done:g} h done)")
    else:
        st.caption("No to-dos for this week yet.")

    st.caption(f"New to-dos are filed under the week you're viewing: "
               f"{week_start:%d %b} – {week_end:%d %b %Y}.")
    with st.form("add_todo", clear_on_submit=True):
        tc1, tc2, tc3 = st.columns([5, 1, 2])
        with tc1:
            td_title = st.text_input("New to-do", key="td_title",
                                     label_visibility="collapsed",
                                     placeholder="New to-do…")
        with tc2:
            td_hours = st.number_input("Est. h", min_value=0.0, step=0.5,
                                       value=0.0, key="td_hours",
                                       label_visibility="collapsed",
                                       help="Estimated hours (optional)")
        with tc3:
            td_projs = {"— no project —": None}
            td_projs.update({p["name"]: p["id"] for p in db.my_projects()})
            td_proj = st.selectbox("Project", list(td_projs.keys()),
                                   key="td_proj", label_visibility="collapsed")
        td_note = st.text_input("Note (optional)", key="td_note",
                                placeholder="optional note shown under the title")
        td_imp = st.checkbox("⭐ High importance", key="td_important")
        if st.form_submit_button("Add to-do"):
            if td_title.strip():
                try:
                    # due_on is the task's start week: it defaults to the
                    # week currently being viewed (week_start), so adding a
                    # to-do while looking at a future/past week files it under
                    # that week. Used only for weekly scoping, not shown as a
                    # date in the UI.
                    db.add_todo(me["id"], td_title.strip(),
                                week_start.isoformat(), td_projs[td_proj],
                                est_hours=td_hours or None,
                                note=td_note.strip() or None,
                                important=td_imp)
                    db.clear_user_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not add. {e}")
            else:
                st.error("Give the to-do a title.")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ---- add a time block ----
    st.markdown("**Add a time block**")
    wk_cv_enabled = st.checkbox(
        "Record this block as a CV achievement",
        key="wk_cv_enabled",
        help="Optional. Saved as a private CV record linked to the time block.")
    is_lead = me.get("role") == "lead"
    # one category list: work first, then life (life only shown to the lead).
    # The chosen category determines the domain — no separate toggle.
    work_cats = db.categories(domain="work")
    life_cats = db.categories(domain="life") if is_lead else []
    cat_labels = {}
    cat_domain_of = {}
    for c in work_cats:
        cat_labels[c["label"]] = c["id"]
        cat_domain_of[c["label"]] = "work"
    # a visual separator between the two groups (non-selectable sentinel)
    if life_cats:
        sep = "──── Life ────"
        cat_labels[sep] = None
        cat_domain_of[sep] = None
        for c in life_cats:
            cat_labels[c["label"]] = c["id"]
            cat_domain_of[c["label"]] = "life"

    a1, a2, a3 = st.columns(3)
    with a1:
        b_day = st.selectbox("Day", days,
                             format_func=lambda d: f"{d:%a %d %b}")
        b_cat = st.selectbox("Category", list(cat_labels.keys()), key="wk_cat",
                             help="Work categories first, then life. Life "
                                  "categories are personal and private to you.")
    wk_life = (cat_domain_of.get(b_cat) == "life")
    sep_picked = (cat_labels.get(b_cat) is None and b_cat.startswith("────"))
    with a2:
        b_start = time_field("Start", dt.time(9, 0), "wk_start")
        b_end = time_field("End", dt.time(11, 0), "wk_end")
    with a3:
        # project filtered to the chosen category; life is never project-tied
        b_proj = "— none —"
        wk_new_name = ""
        wk_milestone_id = None
        wk_new_ms = ""
        if not wk_life and not sep_picked:
            matching = db.projects_for_category(cat_labels[b_cat])
            proj_labels = {"— none —": None}
            proj_labels.update({p["name"]: p["id"] for p in matching})
            proj_labels["+ New project…"] = "__new__"
            b_proj = st.selectbox("Project", list(proj_labels.keys()),
                                  key="wk_proj",
                                  help="Projects in the chosen category. New "
                                       "ones are auto-linked to it.")
            if b_proj == "+ New project…":
                wk_new_name = st.text_input("New project name",
                                            placeholder="e.g. DAFNI Fellowship",
                                            key="wk_newproj")
            elif b_proj != "— none —":
                cur_imp = next((p.get("high_importance") for p in matching
                                if p["name"] == b_proj), False)
                new_imp = st.checkbox("⭐ High importance", value=bool(cur_imp),
                                      key=f"imp_wk_{proj_labels[b_proj]}",
                                      help="Highlights this project's hours in "
                                           "the Time tab.")
                if new_imp != bool(cur_imp):
                    db.set_project_importance(proj_labels[b_proj], new_imp)
                    db.clear_user_caches()
                    st.rerun()
                # milestone dropdown with inline creation
                wk_pid = proj_labels[b_proj]
                wms = [m for m in db.project_milestones(wk_pid)
                       if m["status"] != "done"]
                wms_labels = {"— none —": None}
                wms_labels.update({m["title"]: m["id"] for m in wms})
                wms_labels["+ New milestone…"] = "__new__"
                wms_pick = st.selectbox("Milestone (optional)",
                                        list(wms_labels.keys()), key="wk_ms")
                if wms_pick == "+ New milestone…":
                    wk_new_ms = st.text_input("New milestone name",
                                              placeholder="e.g. First draft",
                                              key="wk_new_ms_name")
                    wk_milestone_id = "__new__"
                else:
                    wk_milestone_id = wms_labels[wms_pick]
        # the selectors and time pickers above stay live (category switches
        # work/life and filters projects). The note goes in a form so typing
        # it doesn't re-run the page each keystroke.
        with st.form("wk_addblock_form", clear_on_submit=True):
            b_note = st.text_input("What will you work on?", key="wk_note")
            wk_cv_dest = wk_cv_title = wk_cv_desc = wk_cv_outcome = None
            wk_cv_metrics = wk_cv_evidence = wk_cv_status = None
            if wk_cv_enabled:
                st.markdown("**CV achievement**")
                wk_cv_dest = st.selectbox(
                    "CV destination", list(CV_DESTINATIONS.keys()),
                    key="wk_cv_dest")
                wk_cv_title = st.text_input(
                    "Achievement title", key="wk_cv_title")
                wk_cv_desc = st.text_area(
                    "Description / draft bullet", key="wk_cv_desc", height=80)
                wk_cv_outcome = st.text_input(
                    "Outcome (optional)", key="wk_cv_outcome")
                wk_cv_metrics = st.text_input(
                    "Metrics (optional)", key="wk_cv_metrics")
                wk_cv_evidence = st.text_input(
                    "Evidence URL (optional)", key="wk_cv_evidence")
                wk_cv_status = st.selectbox(
                    "Status", CV_STATUS_OPTIONS, index=0, key="wk_cv_status")
            addblock_submit = st.form_submit_button("Add block",
                                                    type="primary")
    if addblock_submit:
        started, ended, time_err = resolve_block_times(b_day, b_start, b_end)
        if sep_picked:
            st.error("That's a divider, not a category — pick a real category.")
        elif time_err:
            st.error(time_err)
        else:
            # resolve project (work mode only)
            project_id = None
            ok = True
            if not wk_life:
                project_id = proj_labels[b_proj]
                if b_proj == "+ New project…":
                    if not wk_new_name.strip():
                        st.error("Give the new project a name, or pick one.")
                        ok = False
                    else:
                        try:
                            project_id, created = db.get_or_create_project(
                                wk_new_name, me["id"], "private",
                                category_id=cat_labels[b_cat])
                            if created:
                                st.info(f"Created “{wk_new_name.strip()}” in "
                                        f"'{b_cat}'.")
                        except Exception as e:
                            st.error(f"Could not create project. {e}")
                            ok = False
            if ok:
                # create a new milestone inline if chosen
                ms_id = wk_milestone_id
                if ms_id == "__new__":
                    if not wk_new_ms.strip():
                        st.error("Give the new milestone a name, or pick one.")
                        ok = False
                    else:
                        try:
                            mres = db.add_milestone(project_id,
                                                    wk_new_ms.strip())
                            ms_id = mres.data[0]["id"]
                        except Exception as e:
                            st.error(f"Could not create milestone. {e}")
                            ok = False
            if ok:
                try:
                    res = db.log_session(user_id=me["id"],
                                   category_id=cat_labels[b_cat],
                                   started_at=started, ended_at=ended,
                                   project_id=project_id,
                                   description=b_note or None,
                                   milestone_id=ms_id)
                    if wk_cv_enabled:
                        session_id = (res.data or [{}])[0].get("id") if res else None
                        title_source = (wk_cv_title or "").strip() or (b_note or "").strip()
                        if not title_source:
                            title_source = (wk_new_ms.strip() if ms_id else "") or                                 (wk_new_name.strip() if b_proj == "+ New project…" else b_proj)
                        title_source = title_source if title_source and title_source != "— none —" else b_cat
                        save_cv_entry_from_values(
                            user_id=me["id"], entry_date=b_day,
                            destination_label=wk_cv_dest or "Other",
                            title=title_source,
                            description=wk_cv_desc,
                            outcome=wk_cv_outcome,
                            metrics=wk_cv_metrics,
                            evidence_url=wk_cv_evidence,
                            status=wk_cv_status or "draft",
                            source_type="session" if session_id else "manual",
                            session_id=session_id,
                            milestone_id=ms_id,
                            project_id=project_id)
                    st.success("Block added" + (" and CV achievement recorded." if wk_cv_enabled else "."))
                    db.clear_user_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not add. {e}")

    # ---- edit an existing block this week ----
    editable = [r for r in rows
                if r.get("started_at") and r.get("ended_at")]
    if editable:
        st.markdown("**Edit a block**")
        # step 1: pick a day that has blocks
        days_with_blocks = sorted(
            {r["session_date"] for r in editable})
        ed1, ed2 = st.columns(2)
        with ed1:
            pick_day = st.selectbox(
                "Day", days_with_blocks,
                format_func=lambda ds: f"{dt.date.fromisoformat(ds):%a %d %b}",
                key="wk_edit_day")
        # step 2: pick a block on that day
        day_blocks = [r for r in editable if r["session_date"] == pick_day]

        def block_label(r):
            return (f"{r['started_at'][11:16]}–{r['ended_at'][11:16]} "
                    f"· {r.get('project_name') or r.get('category_label')}")
        blabels = {block_label(r): r for r in
                   sorted(day_blocks, key=lambda x: x["started_at"])}
        with ed2:
            pick = st.selectbox("Block", list(blabels.keys()),
                                key="wk_edit_pick")
        if pick and edit_session_widget(blabels[pick], "wk"):
            st.rerun()

    # ---- summaries ----
    st.markdown("<hr>", unsafe_allow_html=True)
    work_rows = [r for r in rows if r.get("domain") != "life"]
    life_rows = [r for r in rows if r.get("domain") == "life"] if is_lead else []

    work_total = sum((r.get("hours") or 0) for r in work_rows)
    life_total = sum((r.get("hours") or 0) for r in life_rows)

    # Non-lead users never see life totals. Their planned/done numbers are
    # computed from work rows only, so the summary contains no hidden life data.
    summary_rows = rows if is_lead else work_rows
    future_total = sum((r.get("hours") or 0) for r in summary_rows
                       if r.get("session_date") and
                       dt.date.fromisoformat(r["session_date"]) > today)
    summary_total = sum((r.get("hours") or 0) for r in summary_rows)

    if is_lead:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Work", f"{work_total:g} h")
        s2.metric("Life", f"{life_total:g} h")
        s3.metric("Planned (ahead)", f"{future_total:g} h")
        s4.metric("Done (so far)", f"{summary_total - future_total:g} h")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("Work", f"{work_total:g} h")
        s2.metric("Planned (ahead)", f"{future_total:g} h")
        s3.metric("Done (so far)", f"{summary_total - future_total:g} h")

    def rollup(source, key):
        agg = {}
        for r in source:
            k = r.get(key) or "—"
            agg[k] = agg.get(k, 0) + (r.get("hours") or 0)
        return agg

    # Category display order (matches the logging dropdown order). Non-lead
    # users should not load life categories just to draw the work chart.
    all_cats = db.categories() if is_lead else db.categories(domain="work")
    cat_order = {c["label"]: c.get("sort_order", 999) for c in all_cats}
    # label -> code, so we can colour each bar by its shared category group
    cat_code_of = {c["label"]: c.get("code") for c in all_cats}

    def category_colour_for_label(label):
        """The shared group colour for a work category label, so the Week
        chart matches the occupancy chart. Falls back to neutral."""
        code = cat_code_of.get(label)
        group = OCC_GROUP_OF.get(code)
        return OCC_GROUP_COLOUR.get(group, "#cfc8bd")

    def category_bar_chart(source_rows, title, fallback_colour):
        """Draw one domain's hours-by-category bar chart, ordered by the
        category dropdown order (sort_order), labelled with hours and %.
        Work bars are coloured by the shared category-group palette so they
        match the occupancy chart; Life bars use the fallback colour."""
        agg = rollup(source_rows, "category_label")
        if not agg:
            st.caption(f"No {title.lower()} time this week yet.")
            return
        # order by the dropdown's sort_order, then label
        items = sorted(agg.items(),
                       key=lambda kv: (cat_order.get(kv[0], 999), kv[0]))
        labels = [k for k, _ in items]
        values = [v for _, v in items]
        grand = sum(values) or 1
        texts = [f"{v:g}h · {round(100*v/grand)}%" for v in values]
        # work categories get group colours; life keeps the single grey
        is_work = title.lower().startswith("work")
        if is_work:
            bar_colours = [category_colour_for_label(k) for k in labels]
        else:
            bar_colours = fallback_colour
        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color=bar_colours,
            text=texts, textposition="outside",
            hovertemplate="%{x}<br>%{y:g} h<extra></extra>"))
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=30, b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="hours", showgrid=True, gridcolor="#e6e2d8"),
            xaxis=dict(tickangle=-30, categoryorder="array",
                       categoryarray=labels),
            font=dict(family="Georgia, serif", color="#1F2933"),
            uniformtext=dict(minsize=8, mode="hide"))
        st.markdown(f"**{title}**")
        st.plotly_chart(fig, use_container_width=True,
                        key=f"chart_{title}")

    # ---- charts: work for everyone, life only for the lead ----
    category_bar_chart(work_rows, "Work — hours by category", "#3A5A78")
    if is_lead:
        category_bar_chart(life_rows, "Life — hours by category", "#9aa5b1")

    # by-project remains a short text list
    pr = sorted(rollup(work_rows, "project_name").items(),
                key=lambda kv: -kv[1])
    pr = [(k, v) for k, v in pr if k != "—"]
    if pr:
        st.markdown("**Work — by project**")
        for k, v in pr:
            st.markdown(f"{k} &nbsp;·&nbsp; **{v:g} h**", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gantt chart of active projects, with milestone markers + manual ordering
# ---------------------------------------------------------------------------
def project_gantt_segments(project, milestones):
    """Compute the project row as a list of (start, due) date segments, one per
    milestone, using the fallback rules:
      start = milestone.start_on
              else precondition's due_on
              else project start
      due   = milestone.due_on
              else the start of the next milestone that depends on this one
              else project end
    Overlapping segments are merged so genuine gaps (no active milestone)
    show as breaks. Milestones that resolve no usable dates are skipped.
    Returns a sorted list of (date, date) tuples."""
    p_start = dt.date.fromisoformat(project["started_on"]) \
        if project.get("started_on") else None
    p_end = dt.date.fromisoformat(project["due_on"]) \
        if project.get("due_on") else None
    by_id = {m["id"]: m for m in milestones}
    # map each milestone to the milestone that depends on it (its "next")
    next_of = {}
    for m in milestones:
        pre = m.get("precondition_id")
        if pre:
            next_of[pre] = m

    def d(val):
        return dt.date.fromisoformat(val) if val else None

    segments = []
    for m in milestones:
        # effective start
        s = d(m.get("start_on"))
        if s is None:
            pre = by_id.get(m.get("precondition_id"))
            s = d(pre["due_on"]) if pre and pre.get("due_on") else p_start
        # effective due
        e = d(m.get("due_on"))
        if e is None:
            nxt = next_of.get(m["id"])
            e = d(nxt["start_on"]) if nxt and nxt.get("start_on") else p_end
        if s and e and e >= s:
            segments.append((s, e))
    if not segments:
        return []
    # merge overlapping/adjacent segments so only real gaps remain
    segments.sort()
    merged = [list(segments[0])]
    for s, e in segments[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def render_gantt(me):
    section("Timeline", "Project Gantt",
            "Active projects across time, with milestones. Projects you lead "
            "are shown first, then those you participate in.")
    projects = db.active_projects_for_gantt()
    if not projects:
        st.caption("No active projects to chart yet.")
        return

    led = [p for p in projects if p.get("i_lead")]
    part = [p for p in projects if p.get("i_participate")]
    other = [p for p in projects if not p.get("i_lead")
             and not p.get("i_participate")]

    # ordered for the chart: led first, then participant, then any other
    chart_projects = led + part + other
    dated = [p for p in chart_projects
             if p.get("started_on") and p.get("due_on")]
    undated = [p for p in chart_projects
               if not (p.get("started_on") and p.get("due_on"))]

    if dated:
        # One bulk milestone query for the whole Gantt instead of one query
        # inside the project loop.
        gantt_ms_by_project = db.project_milestones_bulk([p["id"] for p in dated])
        fig = go.Figure()
        names = [p["name"] for p in dated]
        n = len(dated)
        for idx, p in enumerate(dated):
            y = n - idx
            start = dt.date.fromisoformat(p["started_on"])
            due = dt.date.fromisoformat(p["due_on"])
            # leader bars solid slate; participant bars lighter
            colour = "#3A5A78" if p.get("i_lead") else "#9aa5b1"
            role = "lead" if p.get("i_lead") else (
                "participant" if p.get("i_participate") else "overseeing")
            ms = gantt_ms_by_project.get(p["id"], [])
            # draw the project row as milestone-derived segments, so gaps
            # between milestones show as breaks in the bar
            segments = project_gantt_segments(p, ms)
            if not segments:
                # no milestone dates to segment by: fall back to one full bar
                segments = [(start, due)]
            for seg_start, seg_due in segments:
                fig.add_trace(go.Scatter(
                    x=[seg_start, seg_due], y=[y, y], mode="lines",
                    line=dict(color=colour, width=16),
                    hovertemplate=f"<b>{p['name']}</b> ({role})<br>"
                                  f"{seg_start:%d %b %Y} → "
                                  f"{seg_due:%d %b %Y}<extra></extra>",
                    hoverlabel=dict(namelength=-1),
                    showlegend=False))
            # group markers by kind: deliverable = blue, internal = grey
            groups = {}
            for m in ms:
                if not m.get("due_on"):
                    continue
                key = m.get("kind") or "internal"
                groups.setdefault(key, {"x": [], "t": []})
                groups[key]["x"].append(dt.date.fromisoformat(m["due_on"]))
                pctv = db.milestone_percent(m)
                pctv = 0 if pctv is None else pctv
                groups[key]["t"].append(f"{m['title']} ({pctv}% done)")
            for kind, g in groups.items():
                colour = "#3A5A78" if kind == "deliverable" else "#9aa5b1"
                fig.add_trace(go.Scatter(
                    x=g["x"], y=[y] * len(g["x"]), mode="markers",
                    marker=dict(color=colour, size=14, symbol="diamond",
                                line=dict(color="white", width=1.5)),
                    text=g["t"],
                    hovertemplate="%{text}<br>%{x|%d %b %Y}<extra></extra>",
                    hoverlabel=dict(namelength=-1),
                    cliponaxis=False, showlegend=False))
        # divider line between led and participant groups
        if led and (part or other):
            boundary = n - len(led) + 0.5
            fig.add_hline(y=boundary, line=dict(color="#d9d5cc", width=1))
        today = dt.date.today()
        fig.add_vline(x=today, line=dict(color="#9aa5b1", width=1, dash="dot"))
        # user picks the window start; always show exactly 12 months from there
        default_start = dt.date(today.year, today.month, 1)
        win_start = st.date_input(
            "Show 1 year from", value=default_start, key="gantt_start",
            help="The Gantt always shows a 12-month window from this date.")
        win_end = dt.date(win_start.year + 1, win_start.month, win_start.day) \
            if (win_start.month, win_start.day) != (2, 29) \
            else dt.date(win_start.year + 1, 3, 1)
        fig.update_layout(
            height=110 + 46 * n,
            margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            hovermode="closest",
            yaxis=dict(tickmode="array",
                       tickvals=list(range(n, 0, -1)),
                       ticktext=names, showgrid=False, fixedrange=True),
            xaxis=dict(showgrid=True, gridcolor="#e6e2d8", type="date",
                       range=[win_start, win_end]),
            font=dict(family="Georgia, serif", color="#1F2933"))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Blue diamonds: deliverables. Grey diamonds: internal "
                   "milestones. Shows a 12-month window from the date you pick "
                   "above. Dotted line is today.")
    else:
        st.caption("No active projects have both a start and due date yet — "
                   "add dates in a project's details to place it on the timeline.")

    if undated:
        st.caption("Not shown (missing start or due date): "
                   + ", ".join(p["name"] for p in undated))

    # ---- my daily time occupancy (from milestone planned hours) ----
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("**Your daily occupancy**")
    st.caption("Your active milestones' planned hours, spread across the "
               "days you chose for each, shown as a 3-month window from a "
               "start date you pick. Paused, completed, or abandoned projects "
               "and completed milestones are excluded. A milestone that "
               "depends on another starts the day after that one is due.")
    # gather only my milestones from active projects. The Gantt already uses
    # db.active_projects_for_gantt(), which filters project.status by the
    # canonical "active" status code. Reuse that filtered project list here so
    # paused, completed, or abandoned projects do not contribute to occupancy.
    occ_projects = [p for p in projects
                    if p.get("i_lead") or p.get("i_participate")]
    all_my_ms = db.milestones_for_projects([p["id"] for p in occ_projects])
    # planned hours are private now; pull the caller's own plans and attach
    my_plans = db.my_milestone_plans()
    for _m in all_my_ms:
        _plan = my_plans.get(_m["id"])
        _m["planned_hours"] = _plan["planned_hours"] if _plan else None
    occ, breakdown, by_group, by_group_detail = compute_daily_occupancy(
        all_my_ms, me["id"])
    if occ:
        # own start-date picker; show a fixed 3-month window from it
        today = dt.date.today()
        occ_start = st.date_input(
            "Show 3 months from", value=today, key="occ_start",
            help="The occupancy chart shows a 3-month window from this date.")
        mth = occ_start.month - 1 + 3
        occ_end = dt.date(occ_start.year + mth // 12, mth % 12 + 1, 1) \
            - dt.timedelta(days=1)
        lo, hi = occ_start.isoformat(), occ_end.isoformat()
        days = [d for d in sorted(occ.keys()) if lo <= d <= hi]
        if not days:
            st.caption("No planned milestone work falls in this 3-month "
                       "window. Pick another start date.")
        else:
            # one stacked trace per category group that actually appears
            groups_present = [g for g in OCC_GROUP_ORDER
                              if any(g in by_group.get(d, {}) for d in days)]
            fig2 = go.Figure()
            for g in groups_present:
                yvals = [round(by_group.get(d, {}).get(g, 0), 2)
                         for d in days]
                # per-day hover: each milestone in this category + its project
                htext = []
                for d in days:
                    lines = []
                    for proj, title, h in sorted(
                            by_group_detail.get(d, {}).get(g, []),
                            key=lambda x: -x[2]):
                        label = f"{title} · {proj}" if proj else title
                        lines.append(f"{label}: {h:.1f} h")
                    htext.append(
                        f"<b>{d}</b> · {g} · "
                        f"{by_group.get(d, {}).get(g, 0):.1f} h<br>"
                        + "<br>".join(lines)
                        + f"<br><span style='color:#999'>day total "
                          f"{occ[d]:.1f} h</span>")
                fig2.add_trace(go.Bar(
                    name=g, x=days, y=yvals,
                    marker_color=OCC_GROUP_COLOUR.get(g, "#cfc8bd"),
                    customdata=htext,
                    hovertemplate="%{customdata}<extra></extra>"))
            fig2.add_hline(y=8,
                           line=dict(color="#C2703D", width=1, dash="dot"))
            fig2.update_layout(
                barmode="stack", height=340,
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(title="planned hours / day", showgrid=True,
                           gridcolor="#e6e2d8"),
                xaxis=dict(type="date", range=[lo, hi]),
                legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
                font=dict(family="Georgia, serif", color="#1F2933"))
            st.plotly_chart(fig2, use_container_width=True)
            st.caption("Each day's bar is stacked by category over a 3-month "
                       "window from the date above. Dotted line marks 8 h. "
                       "Hover a segment for the milestones and day total.")
    else:
        st.caption("No occupancy to show yet — assign yourself milestones with "
                   "planned hours and due dates to see your daily load.")

    st.markdown("<hr>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Section: Projects (the tracker)
# ---------------------------------------------------------------------------
# Colour groups for occupancy: each raw category code maps to one of nine
# high-level groups, each with a muted, distinct hue that sits calmly against
# the app's serif aesthetic.
OCC_GROUP_OF = {
    "planning": "Planning",
    "innovation": "Innovation / learning",
    "learning": "Innovation / learning",
    "supervision": "Supervision",
    "proposal": "Proposal",
    "broadcasting": "Outreach / teaching-support",
    "networking": "Outreach / teaching-support",
    "presentation": "Outreach / teaching-support",
    "training_delivery": "Outreach / teaching-support",
    "teaching": "Teaching",
    "membership": "Membership",
    "project_mgmt": "Project management / lead",
    "admin": "Admin / email / volunteering",
    "email_check": "Admin / email / volunteering",
    "volunteering": "Admin / email / volunteering",
}
OCC_GROUP_COLOUR = {
    "Planning":                     "#4E79A7",
    "Innovation / learning":        "#76B7B2",
    "Supervision":                  "#59A14F",
    "Proposal":                     "#B07AA1",
    "Outreach / teaching-support":  "#E15759",
    "Teaching":                     "#F28E2B",
    "Membership":                   "#EDC948",
    "Project management / lead":    "#9C755F",
    "Admin / email / volunteering": "#9aa5b1",
    "Other":                        "#cfc8bd",
}
OCC_GROUP_ORDER = ["Planning", "Innovation / learning", "Supervision",
                   "Proposal", "Outreach / teaching-support", "Teaching",
                   "Membership", "Project management / lead",
                   "Admin / email / volunteering", "Other"]


def compute_daily_occupancy(milestones, me_id):
    """For the caller's milestones, spread each one's planned hours evenly
    across its chosen working days within its window. A milestone's window
    opens the day after its precondition's due date (or today if none) and
    closes on its own due date. Each milestone's work_days (Mon=0..Sun=6)
    selects which weekdays it uses; empty falls back to Mon-Fri.
    Returns (totals, breakdown, by_group):
      totals: {date_iso: hours}
      breakdown: {date_iso: [(milestone_title, hours), ...]}
      by_group: {date_iso: {group_label: hours}}"""
    by_id = {m["id"]: m for m in milestones}
    totals = {}
    breakdown = {}
    by_group = {}
    by_group_detail = {}
    today = dt.date.today()
    for m in milestones:
        if m.get("contributor_id") != me_id:
            continue
        # Occupancy is forward-looking capacity planning, so completed/done
        # milestones should not keep consuming planned hours. Project-level
        # inactive statuses are filtered before this function is called.
        if str(m.get("status") or "").lower() in {"done", "completed"}:
            continue
        planned = m.get("planned_hours")
        if not planned or not m.get("due_on"):
            continue
        due = dt.date.fromisoformat(m["due_on"])
        # window start: explicit start_on if set; else precondition due + 1;
        # else today
        start = today
        pre_id = m.get("precondition_id")
        if m.get("start_on"):
            start = dt.date.fromisoformat(m["start_on"])
        elif pre_id and pre_id in by_id and by_id[pre_id].get("due_on"):
            start = dt.date.fromisoformat(by_id[pre_id]["due_on"]) \
                + dt.timedelta(days=1)
        wd = m.get("work_days")
        work_set = set(wd) if wd else {0, 1, 2, 3, 4}
        if due < start:
            chosen = [due]
        else:
            chosen = []
            d = start
            while d <= due:
                if d.weekday() in work_set:
                    chosen.append(d)
                d += dt.timedelta(days=1)
            if not chosen:
                chosen = [due]
        per_day = planned / len(chosen)
        title = m.get("title") or "milestone"
        proj = m.get("project_name") or ""
        group = OCC_GROUP_OF.get(m.get("effective_category_code"), "Other")
        for d in chosen:
            iso = d.isoformat()
            totals[iso] = totals.get(iso, 0) + per_day
            breakdown.setdefault(iso, []).append((title, per_day))
            g = by_group.setdefault(iso, {})
            g[group] = g.get(group, 0) + per_day
            # fullest detail: per day, per group, each milestone + its project
            gd = by_group_detail.setdefault(iso, {}).setdefault(group, [])
            gd.append((proj, title, per_day))
    return totals, breakdown, by_group, by_group_detail


def render_milestone_progress_bars(pid, key_suffix, rows=None):
    """Per-milestone published-progress bar chart for a project. Bars at each
    milestone's shared %, with binary-fallback bars (no published %) flagged
    in a lighter tone and marked. Shown to everyone; no hours involved.

    rows can be preloaded by db.milestone_progress_bars_bulk() so the Projects
    page does not make one progress query per project.
    """
    rows = db.milestone_progress_bars(pid) if rows is None else rows
    if not rows:
        return
    titles = [r["title"] for r in rows]
    vals = [r["pct"] for r in rows]
    # published bars in blue; binary-fallback bars in muted grey, with a mark
    colours = ["#9aa5b1" if r["fallback"] else "#3A5A78" for r in rows]
    texts = [(f"{r['pct']}%" + (" *" if r["fallback"] else "")) for r in rows]
    fig = go.Figure(go.Bar(
        x=titles, y=vals, marker_color=colours,
        text=texts, textposition="outside",
        hovertemplate="%{x}<br>%{y}%<extra></extra>"))
    fig.update_layout(
        height=260, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[0, 100], title="% complete", showgrid=True,
                   gridcolor="#e6e2d8"),
        xaxis=dict(tickangle=-30),
        font=dict(family="Georgia, serif", color="#1F2933"),
        uniformtext=dict(minsize=8, mode="hide"))
    st.plotly_chart(fig, use_container_width=True,
                    key=f"msprog_{key_suffix}")
    if any(r["fallback"] for r in rows):
        st.caption("Bars marked * have no published progress yet, so they show "
                   "binary 0 or 100% (done). The rest show the contributor's "
                   "published completion %.")


def render_project_details_and_milestones(r, me, is_lead):
    """Render the expensive project editor for one selected project only.

    This used to live inside every project row's expander. Streamlit computes
    closed expanders too, so rendering it for every project made ordinary page
    interactions slow. Keeping it as a separate helper lets view_projects render
    the full editor only for the project currently selected by the user.
    """
    pid = r["project_id"]
    est = r.get("estimated_hours")
    statuses = db.project_statuses()
    st_labels = {s["label"]: s["id"] for s in statuses}
    det = db.project_detail(pid) or {}
    with st.form(f"projdet_form_{pid}"):
        new_name = st.text_input("Project name",
                                 value=r.get("project_name") or "",
                                 key=f"name_{pid}")
        # category (one per project) — filters the logging dropdown
        all_cats = db.categories(domain="work")
        cat_by_id = {c["id"]: c["label"] for c in all_cats}
        cat_label_to_id = {c["label"]: c["id"] for c in all_cats}
        cur_cat_id = det.get("category_id")
        cat_options = ["— none —"] + list(cat_label_to_id.keys())
        cur_cat_label = cat_by_id.get(cur_cat_id, "— none —")
        cat_index = cat_options.index(cur_cat_label) \
            if cur_cat_label in cat_options else 0
        new_proj_cat = st.selectbox(
            "Category (one per project)", cat_options, index=cat_index,
            key=f"projcat_{pid}",
            help="Determines which category this project appears under "
                 "when logging.")
        new_importance = st.checkbox(
            "⭐ High importance",
            value=bool(det.get("high_importance")),
            key=f"projimp_{pid}",
            help="Highlights this project's hours in the Time tab.")
        ec1, ec2 = st.columns(2)
        with ec1:
            if is_lead:
                if est:
                    st.metric("Estimate (from milestones)",
                              f"{est:g} h")
                else:
                    st.caption("Estimate: set milestone planned hours "
                               "below")
        with ec2:
            cur_status = r.get("status") or list(st_labels.keys())[0]
            idx = list(st_labels.keys()).index(cur_status) \
                if cur_status in st_labels else 0
            new_status = st.selectbox(
                "Status", list(st_labels.keys()),
                index=idx, key=f"status_{pid}")
        dc1, dc2 = st.columns(2)
        with dc1:
            cur_started = det.get("started_on")
            new_started = st.date_input(
                "Start date",
                value=dt.date.fromisoformat(cur_started)
                if cur_started else None, key=f"start_{pid}")
        with dc2:
            cur_due = det.get("due_on")
            new_due = st.date_input(
                "Due date",
                value=dt.date.fromisoformat(cur_due) if cur_due
                else None, key=f"due_{pid}")
        savedet_submit = st.form_submit_button("Save details")
    if savedet_submit:
        if not new_name.strip():
            st.error("Project name can't be empty.")
        else:
            try:
                db.update_project(pid, {
                    "name": new_name.strip(),
                    "status_id": st_labels[new_status],
                    "started_on": new_started.isoformat()
                    if new_started else None,
                    "due_on": new_due.isoformat() if new_due else None,
                    "category_id": (cat_label_to_id.get(new_proj_cat)
                                    if new_proj_cat != "— none —"
                                    else None),
                    "high_importance": new_importance,
                })
                st.success("Saved.")
                db.clear_user_caches()
                st.rerun()
            except Exception as e:
                st.error(f"Could not save. {e}")

    # ---- planning fields ----
    det = db.project_detail(pid) or {}
    st.markdown("**Planning**")
    with st.form(f"projplan_form_{pid}"):
        purpose = st.text_area("Purpose",
                               value=det.get("purpose") or "",
                               key=f"purpose_{pid}",
                               help="Why the project exists.")
        outcomes = st.text_area("Final outcomes",
                                value=det.get("final_outcomes") or "",
                                key=f"outcomes_{pid}")
        stake = st.text_area("Stakeholders / users",
                             value=det.get("stakeholders") or "",
                             key=f"stake_{pid}")
        risks = st.text_area("Risks", value=det.get("risks") or "",
                             key=f"risks_{pid}")
        saveplan_submit = st.form_submit_button("Save planning")
    if saveplan_submit:
        try:
            db.update_project(pid, {
                "purpose": purpose or None,
                "final_outcomes": outcomes or None,
                "stakeholders": stake or None,
                "risks": risks or None,
            })
            st.success("Planning saved.")
            db.clear_user_caches()
            st.rerun()
        except Exception as e:
            st.error(f"Could not save planning. {e}")

    # ---- people in charge ----
    st.markdown("**People in charge**")
    leads = db.project_leads(pid)
    users = db.all_users()
    uname = {u["id"]: u["full_name"] for u in users}
    current_leader = next((L["user_id"] for L in leads
                           if L.get("is_leader")), None)
    for L in leads:
        lc1, lc2, lc3 = st.columns([3, 1, 1])
        with lc1:
            crown = "★ " if L.get("is_leader") else ""
            st.caption(f"{crown}{uname.get(L['user_id'], 'Unknown')}"
                       + (f" — {L['role']}" if L.get("role") else ""))
        with lc2:
            if not L.get("is_leader"):
                if st.button("Make leader",
                             key=f"mklead_{pid}_{L['user_id']}"):
                    db.set_project_leader(pid, L["user_id"])
                    db.clear_user_caches()
                    st.rerun()
        with lc3:
            if st.button("Remove", key=f"rmlead_{pid}_{L['user_id']}"):
                db.remove_project_lead(pid, L["user_id"])
                db.clear_user_caches()
                st.rerun()
    if not current_leader:
        st.caption("⚠ No leader set — assign one so this project is "
                   "grouped correctly.")
    with st.form(f"add_lead_{pid}", clear_on_submit=True):
        u_labels = {u["full_name"]: u["id"] for u in users}
        who = st.selectbox("Add person", list(u_labels.keys()),
                           key=f"who_{pid}")
        role_in = st.text_input("Role (optional)", key=f"role_{pid}",
                                placeholder="PI, co-lead, student lead")
        as_leader = st.checkbox("Make this person the leader",
                                key=f"asld_{pid}")
        if st.form_submit_button("Add person"):
            try:
                if as_leader:
                    db.set_project_leader(pid, u_labels[who])
                    if role_in.strip():
                        db.update_project_lead_role(
                            pid, u_labels[who], role_in.strip())
                else:
                    db.add_project_lead(pid, u_labels[who],
                                        role_in.strip() or None)
                db.clear_user_caches()
                st.rerun()
            except Exception as e:
                st.error(f"Could not add. {e}")

    # ---- links ----
    st.markdown("**Links** (references, resources, outcomes)")
    for lk in db.project_links(pid):
        kc1, kc2 = st.columns([5, 1])
        with kc1:
            st.markdown(
                f"[{lk.get('label') or lk['url']}]({lk['url']}) "
                f"· _{lk['kind']}_")
        with kc2:
            if st.button("Remove", key=f"rmlink_{lk['id']}"):
                db.delete_project_link(lk["id"])
                db.clear_user_caches()
                st.rerun()
    with st.form(f"add_link_{pid}", clear_on_submit=True):
        lu = st.text_input("URL", key=f"lu_{pid}",
                           placeholder="https://…")
        ll = st.text_input("Label (optional)", key=f"ll_{pid}")
        lk_kind = st.selectbox("Type",
                               ["reference", "resource", "outcome", "other"],
                               key=f"lk_{pid}")
        if st.form_submit_button("Add link"):
            if lu.strip():
                try:
                    db.add_project_link(pid, lu.strip(),
                                        ll.strip() or None, lk_kind)
                    db.clear_user_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not add link. {e}")
            else:
                st.error("Give the link a URL.")

    # ---- budget summary (lead only; full editing in the Budget tab) --
    if is_lead:
        st.markdown("**Budget** (private to you)")
        items = db.budget_items(pid)
        if items:
            plan = sum(i.get("plan_amount") or 0 for i in items)
            used = sum(i.get("used") or 0 for i in items)
            cur = items[0].get("currency") or ""
            bm1, bm2, bm3 = st.columns(3)
            bm1.metric("Planned", f"{plan:g} {cur}")
            bm2.metric("Used", f"{used:g} {cur}")
            bm3.metric("Remaining", f"{plan - used:g} {cur}")
            if plan:
                st.progress(min(used / plan, 1.0),
                            text=f"{round(100*used/plan)}% spent")
            st.caption("Plan items and payments are managed in the "
                       "Budget tab.")
        else:
            st.caption("No budget yet — set it up in the Budget tab.")

    # ---- history ----
    with st.expander("Edit history"):
        hist = db.project_history(pid)
        if hist:
            for h in hist:
                when = (h["changed_at"] or "")[:16].replace("T", " ")
                st.caption(f"{when} · {h['table_name']} {h['action'].lower()}"
                           + (f" · {h['changed_by']}"
                              if h.get("changed_by") else ""))
        else:
            st.caption("No history yet.")

    st.markdown("**Milestones**")
    ms = db.project_milestones(pid)
    my_ms_hours = db.my_milestone_hours()
    members = db.group_members()
    member_name = {u["id"]: u["full_name"] for u in members}
    ms_title = {m["id"]: m["title"] for m in ms}

    # personal view (non-lead): show only my milestones, PLUS any that
    # mine depend on, so preconditions stay meaningful.
    if not is_lead:
        mine = {m["id"] for m in ms
                if m.get("contributor_id") == me["id"]}
        # pull in preconditions of mine (one hop is enough in practice)
        needed = set(mine)
        for m in ms:
            if m["id"] in mine and m.get("precondition_id"):
                needed.add(m["precondition_id"])
        ms = [m for m in ms if m["id"] in needed]
        if not ms:
            st.caption("You have no milestones in this project.")

    if ms:
        for m in ms:
            mc1, mc2, mc3 = st.columns([4, 2, 1])
            done = m["status"] == "done"
            with mc1:
                st.markdown(("~~" + m["title"] + "~~") if done
                            else m["title"])
                bits = []
                if m.get("due_on"):
                    bits.append(f"due {m['due_on']}")
                if m.get("contributor_id"):
                    bits.append(member_name.get(m["contributor_id"],
                                                "someone"))
                if m.get("precondition_id"):
                    bits.append("after: " + ms_title.get(
                        m["precondition_id"], "another milestone"))
                hrs = my_ms_hours.get(m["id"]) or 0
                planned = m.get("planned_hours")
                # computed completion %, works for both tracking units
                pctv = db.milestone_percent(m, my_hours=hrs)
                if pctv is not None:
                    bits.append(f"{pctv}% complete")
                # hours shown to the lead only; never in the shared view
                if is_lead:
                    if planned:
                        bits.append(f"your hours: {hrs:g} of "
                                    f"{planned:g} planned")
                    elif hrs:
                        bits.append(f"your hours: {hrs:g}")
                if bits:
                    st.caption(" · ".join(bits))
                # progress bar from the computed %
                if pctv is not None:
                    st.progress(min(pctv / 100, 1.0))
                if m.get("hypothesis"):
                    st.caption(f"Hypothesis: {m['hypothesis']}")
                if m.get("success_measure"):
                    st.caption(f"Success measure: {m['success_measure']}")
                # progress notes (shown to everyone who sees the project)
                for up in db.milestone_updates(m["id"]):
                    when = (up["created_at"] or "")[:10]
                    who = member_name.get(up.get("author_id"), "")
                    uc1, uc2 = st.columns([6, 1])
                    with uc1:
                        st.caption(f"📝 {when} · {who}: {up['note']}")
                    with uc2:
                        if st.button("✕", key=f"updel_{up['id']}",
                                     help="Remove note"):
                            db.delete_milestone_update(up["id"])
                            db.clear_user_caches()
                            st.rerun()
                with st.popover("Add note"):
                    with st.form(f"upnote_form_{m['id']}",
                                 clear_on_submit=True):
                        un = st.text_input(
                            "Progress note", key=f"upnote_{m['id']}",
                            placeholder="e.g. first pass done")
                        upnote_submit = st.form_submit_button(
                            "Save note", type="primary")
                    if upnote_submit:
                        if un.strip():
                            try:
                                db.add_milestone_update(
                                    m["id"], me["id"], un.strip())
                                db.clear_user_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not add note. {e}")
                        else:
                            st.error("Write a note first.")
                # milestone links
                mlinks = db.milestone_links(m["id"])
                for lk in mlinks:
                    lkc1, lkc2 = st.columns([6, 1])
                    with lkc1:
                        st.caption(
                            f"🔗 [{lk.get('label') or lk['url']}]"
                            f"({lk['url']}) · {lk['kind']}")
                    with lkc2:
                        if st.button("✕", key=f"mlk_del_{lk['id']}",
                                     help="Remove link"):
                            db.delete_project_link(lk["id"])
                            db.clear_user_caches()
                            st.rerun()
                with st.popover("Add link", use_container_width=False):
                    lu = st.text_input("URL", key=f"mlu_{m['id']}",
                                       placeholder="https://…")
                    ll = st.text_input("Label (optional)",
                                       key=f"mll_{m['id']}")
                    lk_kind = st.selectbox(
                        "Type",
                        ["reference", "resource", "outcome", "other"],
                        key=f"mlk_{m['id']}")
                    if st.button("Save link", key=f"mlk_save_{m['id']}",
                                 type="primary"):
                        if lu.strip():
                            try:
                                db.add_project_link(
                                    pid, lu.strip(), ll.strip() or None,
                                    lk_kind, milestone_id=m["id"])
                                db.clear_user_caches()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not add link. {e}")
                        else:
                            st.error("Give the link a URL.")
            with mc2:
                st.caption(m["status"])
            with mc3:
                if st.button("✓" if not done else "↺",
                             key=f"ms_toggle_{m['id']}",
                             help="Mark done / reopen"):
                    db.update_milestone(m["id"], {
                        "status": "planned" if done else "done"})
                    db.clear_user_caches()
                    st.rerun()
                with st.popover("✎", help="Edit milestone"):
                    with st.form(f"editms_form_{m['id']}"):
                        e_title = st.text_input(
                            "Title", value=m["title"],
                            key=f"editms_title_{m['id']}")
                        cur_start = m.get("start_on")
                        e_start = st.date_input(
                            "Start (optional)",
                            value=dt.date.fromisoformat(cur_start)
                            if cur_start else None,
                            key=f"editms_start_{m['id']}",
                            help="If set, used as the window start for "
                                 "occupancy and the Gantt segment. "
                                 "Otherwise falls back to the prior "
                                 "milestone's due, then the project start.")
                        cur_due = m.get("due_on")
                        e_due = st.date_input(
                            "Due (optional)",
                            value=dt.date.fromisoformat(cur_due)
                            if cur_due else None,
                            key=f"editms_due_{m['id']}")
                        # contributor (one person)
                        contrib_labels = {"— none —": None}
                        contrib_labels.update(
                            {u["full_name"]: u["id"] for u in members})
                        cur_contrib = member_name.get(
                            m.get("contributor_id"), "— none —")
                        ck = list(contrib_labels.keys())
                        e_contrib = st.selectbox(
                            "Contributor", ck,
                            index=ck.index(cur_contrib)
                            if cur_contrib in ck else 0,
                            key=f"editms_contrib_{m['id']}")
                        # precondition (another milestone in this project)
                        pre_labels = {"— none —": None}
                        pre_labels.update(
                            {mm["title"]: mm["id"]
                             for mm in db.project_milestones(pid)
                             if mm["id"] != m["id"]})
                        cur_pre = ms_title.get(m.get("precondition_id"),
                                               "— none —")
                        pk = list(pre_labels.keys())
                        e_pre = st.selectbox(
                            "Depends on (precondition)", pk,
                            index=pk.index(cur_pre) if cur_pre in pk else 0,
                            key=f"editms_pre_{m['id']}")
                        e_hyp = st.text_input(
                            "Hypothesis / expected outcome",
                            value=m.get("hypothesis") or "",
                            key=f"editms_hyp_{m['id']}")
                        e_sm = st.text_input(
                            "Success measure",
                            value=m.get("success_measure") or "",
                            key=f"editms_sm_{m['id']}")
                        st.caption("Estimated hours and tracking choice are "
                                   "private — set them in the Planning tab.")
                        editms_submit = st.form_submit_button(
                            "Save", type="primary")
                        if editms_submit and e_title.strip():
                            db.update_milestone(m["id"], {
                                "title": e_title.strip(),
                                "due_on": e_due.isoformat()
                                if e_due else None,
                                "start_on": e_start.isoformat()
                                if e_start else None,
                                "contributor_id":
                                    contrib_labels[e_contrib],
                                "precondition_id": pre_labels[e_pre],
                                "hypothesis": e_hyp.strip() or None,
                                "success_measure": e_sm.strip() or None,
                            })
                            db.clear_user_caches()
                            st.rerun()
                        elif editms_submit:
                            st.error("Title can't be empty.")
    else:
        st.caption("No milestones yet.")

    add_ms_cv = st.checkbox("Also add a private CV achievement",
                            key=f"addms_cv_{pid}")
    with st.form(f"add_ms_{pid}", clear_on_submit=True):
        mt = st.text_input("New milestone", key=f"mt_{pid}")
        md = st.date_input("Due (optional)", value=None, key=f"md_{pid}")
        mh = st.text_input("Hypothesis / expected outcome (optional)",
                           key=f"mh_{pid}")
        msm = st.text_input("Success measure (optional)", key=f"msm_{pid}")
        add_ms_cv_dest = add_ms_cv_desc = add_ms_cv_status = None
        if add_ms_cv:
            add_ms_cv_dest = st.selectbox(
                "CV destination", list(CV_DESTINATIONS.keys()),
                key=f"addms_cv_dest_{pid}")
            add_ms_cv_desc = st.text_area(
                "CV description / draft bullet", height=70,
                key=f"addms_cv_desc_{pid}")
            add_ms_cv_status = st.selectbox(
                "CV status", CV_STATUS_OPTIONS, index=0,
                key=f"addms_cv_status_{pid}")
        if st.form_submit_button("Add milestone"):
            if mt.strip():
                try:
                    res = db.add_milestone(
                        pid, mt.strip(),
                        due_on=md.isoformat() if md else None,
                        hypothesis=mh.strip() or None,
                        success_measure=msm.strip() or None)
                    if add_ms_cv:
                        milestone_id = (res.data or [{}])[0].get("id") if res else None
                        save_cv_entry_from_values(
                            user_id=me["id"],
                            entry_date=md or dt.date.today(),
                            destination_label=add_ms_cv_dest or "Other",
                            title=mt.strip(),
                            description=add_ms_cv_desc or msm or mh,
                            status=add_ms_cv_status or "draft",
                            source_type="milestone" if milestone_id else "project",
                            milestone_id=milestone_id,
                            project_id=pid)
                    db.clear_user_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not add milestone. {e}")
            else:
                st.error("Give the milestone a title.")


def view_projects(me):
    section("Projects", "Project tracker",
            "Time spent against estimate, per project.")
    render_gantt(me)
    rows = db.project_tracker()
    active = rows  # show all visible projects, including freshly created ones
    if not active:
        st.caption("No projects yet. Log a session and choose “+ New project…”, "
                   "or add one below.")
    is_lead = me.get("role") == "lead"
    sorted_active = sorted(active, key=lambda x: -(x.get("hours_logged") or 0))
    project_ids = [r["project_id"] for r in sorted_active]
    progress_bars_by_project = db.milestone_progress_bars_bulk(project_ids)
    progress_stats_by_project = db.milestone_progress_bulk(project_ids)

    # Keep a single project selected for the expensive editor. The summary list
    # remains cheap; details, milestones, links, people, budget and history are
    # rendered only for this selected project.
    valid_ids = {r["project_id"] for r in sorted_active}
    if sorted_active and st.session_state.get("projects_selected_id") not in valid_ids:
        st.session_state["projects_selected_id"] = sorted_active[0]["project_id"]

    for r in sorted_active:
        logged = r.get("hours_logged") or 0
        est = r.get("estimated_hours")
        pct = r.get("completion_pct")
        pid = r["project_id"]
        selected = st.session_state.get("projects_selected_id") == pid
        if is_lead:
            # full view: hours logged vs estimate (hours)
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1.5])
            with c1:
                st.markdown(f"**{r['project_name']}**")
                st.caption(r.get("status") or "")
            with c2:
                st.metric("Hours logged", f"{logged:g}")
            with c3:
                if est:
                    st.metric("Estimate", f"{est:g}",
                              delta=f"{r.get('hours_remaining'):g} left"
                              if r.get("hours_remaining") is not None else None,
                              delta_color="off")
            with c4:
                if st.button("Open ✓" if selected else "Open",
                             key=f"open_proj_details_{pid}"):
                    st.session_state["projects_selected_id"] = pid
                    selected = True
            if est and pct is not None:
                st.progress(min(pct / 100, 1.0),
                            text=f"{pct:g}% complete")
            render_milestone_progress_bars(
                pid, f"lead_{pid}", progress_bars_by_project.get(pid, []))
        else:
            # shared view: milestone completion only, NO hours anywhere
            mp = progress_stats_by_project.get(
                pid, {"done": 0, "total": 0, "pct": None})
            c1, c2, c3 = st.columns([3, 3, 1.5])
            with c1:
                st.markdown(f"**{r['project_name']}**")
                st.caption(r.get("status") or "")
            with c2:
                if mp["total"]:
                    st.caption(f"{mp['done']} of {mp['total']} milestones done")
            with c3:
                if st.button("Open ✓" if selected else "Open",
                             key=f"open_proj_details_{pid}"):
                    st.session_state["projects_selected_id"] = pid
                    selected = True
            if mp["pct"] is not None:
                st.progress(min(mp["pct"] / 100, 1.0),
                            text=f"{mp['pct']}% of milestones complete")
            else:
                st.caption("No milestones set yet.")
            render_milestone_progress_bars(
                pid, f"shared_{pid}", progress_bars_by_project.get(pid, []))

        st.markdown("<hr>", unsafe_allow_html=True)

    selected_id = st.session_state.get("projects_selected_id")
    selected_project = next((r for r in sorted_active
                             if r["project_id"] == selected_id), None)
    if selected_project:
        with st.expander(
                f"Details & milestones — {selected_project.get('project_name') or 'project'}",
                expanded=True):
            render_project_details_and_milestones(selected_project, me, is_lead)

    with st.expander("Add a project"):
        name = st.text_input("Project name")
        statuses = db.project_statuses()
        st_labels = {s["label"]: s["id"] for s in statuses}
        status = st.selectbox("Status", list(st_labels.keys()))
        vis = st.radio("Visibility", ["private", "group"], horizontal=True,
                       help="group = visible to the whole group; private = just you.")
        st.caption("The project's estimate comes from the sum of its milestone "
                   "planned hours, which you set after creating it.")
        if st.button("Create project", type="primary"):
            if not name.strip():
                st.error("Give the project a name.")
            else:
                try:
                    db.create_project(name.strip(), st_labels[status], vis,
                                      None, me["id"])
                    st.success("Project created.")
                    db.clear_user_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not create project. {e}")


# ---------------------------------------------------------------------------
# Section: Time (high-category proportion + forecast)
# ---------------------------------------------------------------------------


def view_time(me):
    section("Time", "Where the time goes",
            "Proportion by high category, like your yearly summary.")
    choice = st.radio("Period", ["This week", "This month", "This year", "Custom"],
                      horizontal=True, index=1)
    if choice == "Custom":
        c1, c2 = st.columns(2)
        with c1:
            d_from = st.date_input("From",
                                   value=dt.date(dt.date.today().year, 1, 1),
                                   key="t_from")
        with c2:
            d_to = st.date_input("To", value=dt.date.today(), key="t_to")
        label = f"{d_from:%d %b %Y} - {d_to:%d %b %Y}"
    else:
        d_from, d_to, label = period_range(choice)
    st.caption(f"Showing: {label}")

    is_lead = me.get("role") == "lead"
    view_domain = "both"
    if is_lead:
        view_domain = st.radio("Show", ["Work", "Life", "Both"],
                               horizontal=True, key="time_domain").lower()

    rows = db.time_by_high_category(d_from.isoformat(), d_to.isoformat())
    # filter by domain (students only ever have work rows anyway)
    if view_domain != "both":
        rows = [r for r in rows if r.get("domain") == view_domain]

    # Show the selected-period total before the category breakdown.
    # This respects the Work/Life/Both filter above for the lead, and is
    # work-only for non-lead users.
    total_hours = sum((r.get("total_hours") or 0) for r in rows)
    st.metric("Total hours", f"{total_hours:g} h")

    if rows:
        # recompute proportions within the filtered set so they sum to 100
        total = total_hours or 1
        st.markdown("**Proportion of time by high category**")
        for r in sorted(rows, key=lambda x: -(x.get("total_hours") or 0)):
            label_cat = r["high_category"]
            hours = r.get("total_hours") or 0
            pct = round(100 * hours / total, 1)
            st.markdown(f"{label_cat} &nbsp; · &nbsp; **{hours:g} h** &nbsp; ({pct:g}%)",
                        unsafe_allow_html=True)
            st.progress(min(pct / 100, 1.0))
    else:
        st.caption("No time logged in this range yet.")

    # ---- high-importance projects ----
    hi = db.high_importance_hours(d_from.isoformat(), d_to.isoformat())
    if hi:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("**⭐ High-importance projects** — your hours this period")
        hi_total = sum(h["hours"] for h in hi) or 1
        for h in hi:
            pct = round(100 * h["hours"] / hi_total)
            st.markdown(f"⭐ {h['name']} &nbsp;·&nbsp; **{h['hours']:g} h**",
                        unsafe_allow_html=True)
            st.progress(min(h["hours"] / hi_total, 1.0))

    st.markdown("<hr>", unsafe_allow_html=True)
    section("Forecast", "Project load forecast",
            "How a project is tracking, and when it may finish at your recent pace.")
    projs = db.my_projects()
    if projs:
        plabels = {p["name"]: p["id"] for p in projs}
        pick = st.selectbox("Project", list(plabels.keys()))
        if st.button("Run forecast", type="primary"):
            res = db.project_load_forecast(plabels[pick])
            if res:
                f = res[0]
                m1, m2, m3 = st.columns(3)
                m1.metric("Logged", f"{(f.get('hours_logged') or 0):g} h")
                m2.metric("Remaining", f"{(f.get('remaining_hours') or 0):g} h")
                wk = f.get("recent_weekly_hours")
                m3.metric("Recent pace", f"{wk:g} h/wk" if wk else "—")
                end = f.get("expected_end_date")
                if end:
                    st.info(f"At your recent pace, expected finish around **{end}** "
                            f"({f.get('weeks_needed'):g} weeks of work remaining).")
                if f.get("note"):
                    st.caption(f.get("note"))
            else:
                st.caption("No forecast available.")
    else:
        st.caption("No projects to forecast yet.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _reset_picker_if_options_changed(key, options):
    """Drop a keyed selectbox's stored choice when its options were rebuilt.

    Streamlit stores a keyed selectbox's choice as an *index* into the options
    list, and that index wins over the `index=` argument on the next rerun. So
    any rebuild that reorders or relabels the options leaves the index pointing
    at a different row. The milestone picker is sorted by due date, so editing
    a due date reorders it and the edit looks like it never saved; adding or
    removing a project or milestone shifts either picker the same way.

    Clearing the widget state on an options change lets the `index=` the caller
    computes from the id we remember ourselves take effect again. Detecting the
    change here rather than clearing at each write site means a new write path
    can't quietly reintroduce the bug."""
    fingerprint_key = f"{key}__options"
    fingerprint = tuple(options)
    if st.session_state.get(fingerprint_key) != fingerprint:
        st.session_state[fingerprint_key] = fingerprint
        st.session_state.pop(key, None)


def render_milestone_block(m, me, members, member_name, ms_title_map,
                           project_id, my_hours, hist=None):
    """Render one milestone with progress, edit popover, and combined history
    (audit + notes, last 5). Used by the Milestones tab. `hist` may be passed
    in pre-fetched (bulk) to avoid a per-milestone query; if None, it is
    fetched individually."""
    done = m["status"] == "done"
    c1, c2, c3 = st.columns([4, 2, 1])
    with c1:
        st.markdown(("~~" + m["title"] + "~~") if done else m["title"])
        bits = []
        if m.get("contributor_id"):
            bits.append(member_name.get(m["contributor_id"], "someone"))
        if m.get("due_on"):
            bits.append(f"due {m['due_on']}")
        if m.get("precondition_id"):
            bits.append("after: " + ms_title_map.get(
                m["precondition_id"], "another milestone"))
        pctv = db.milestone_percent(m, my_hours=my_hours)
        if pctv is not None:
            bits.append(f"{pctv}% complete")
        if bits:
            st.caption(" · ".join(bits))
        if pctv is not None:
            st.progress(min(pctv / 100, 1.0))
        # combined history: last 5 of (edits + notes)
        if hist is None:
            hist = db.milestone_history_combined(m["id"], limit=5)
        if hist:
            with st.expander("Recent history (5)"):
                for h in hist:
                    when = (h["when"] or "")[:16].replace("T", " ")
                    who = member_name.get(h.get("who"), "")
                    if h["kind"] == "note":
                        st.caption(f"📝 {when} · {who}: {h['note']}")
                    else:
                        st.caption(f"✎ {when} · {who} · "
                                   f"{(h.get('action') or '').lower()}")
        with st.popover("Add note", use_container_width=False):
            with st.form(f"msvnote_form_{m['id']}", clear_on_submit=True):
                un = st.text_input("Progress note", key=f"msv_note_{m['id']}",
                                   placeholder="e.g. first pass done")
                msvnote_submit = st.form_submit_button(
                    "Save note", type="primary")
            if msvnote_submit:
                if un.strip():
                    db.add_milestone_update(m["id"], me["id"], un.strip())
                    db.clear_user_caches()
                    st.rerun()
                else:
                    st.error("Write a note first.")
        with st.popover("CV", use_container_width=False,
                        help="Add this milestone to your private CV record."):
            default_date = dt.date.fromisoformat(m["due_on"]) if m.get("due_on") else dt.date.today()
            with st.form(f"msv_cv_form_{m['id']}", clear_on_submit=True):
                cv_date = st.date_input("Date", value=default_date,
                                        key=f"msv_cv_date_{m['id']}")
                cv_dest = st.selectbox(
                    "CV destination", list(CV_DESTINATIONS.keys()),
                    key=f"msv_cv_dest_{m['id']}")
                cv_title = st.text_input(
                    "Achievement title", value=m.get("title") or "",
                    key=f"msv_cv_title_{m['id']}")
                cv_desc = st.text_area(
                    "Description / draft bullet", height=80,
                    value=m.get("success_measure") or m.get("hypothesis") or "",
                    key=f"msv_cv_desc_{m['id']}")
                cv_outcome = st.text_input("Outcome (optional)",
                                           key=f"msv_cv_outcome_{m['id']}")
                cv_metrics = st.text_input("Metrics (optional)",
                                           key=f"msv_cv_metrics_{m['id']}")
                cv_evidence = st.text_input("Evidence URL (optional)",
                                            key=f"msv_cv_evidence_{m['id']}")
                cv_status = st.selectbox("Status", CV_STATUS_OPTIONS,
                                         index=0, key=f"msv_cv_status_{m['id']}")
                save_msv_cv = st.form_submit_button("Save CV entry",
                                                    type="primary")
            if save_msv_cv:
                if cv_title.strip():
                    save_cv_entry_from_values(
                        user_id=me["id"], entry_date=cv_date,
                        destination_label=cv_dest,
                        title=cv_title.strip(),
                        description=cv_desc,
                        outcome=cv_outcome,
                        metrics=cv_metrics,
                        evidence_url=cv_evidence,
                        status=cv_status,
                        source_type="milestone",
                        milestone_id=m["id"],
                        project_id=project_id)
                    db.clear_user_caches()
                    st.success("CV entry saved.")
                else:
                    st.error("Give the CV entry a title.")
    with c2:
        st.caption(m["status"])
    with c3:
        if st.button("✓" if not done else "↺", key=f"msv_toggle_{m['id']}",
                     help="Mark done / reopen"):
            db.update_milestone(m["id"], {
                "status": "planned" if done else "done"})
            db.clear_user_caches()
            st.rerun()
        with st.popover("✎", help="Edit milestone"):
            with st.form(f"msv_editform_{m['id']}"):
                e_title = st.text_input("Title", value=m["title"],
                                        key=f"msv_title_{m['id']}")
                cur_start = m.get("start_on")
                e_start = st.date_input(
                    "Start (optional)",
                    value=dt.date.fromisoformat(cur_start) if cur_start else None,
                    key=f"msv_start_{m['id']}",
                    help="If set, used as the window start for occupancy and the "
                         "Gantt segment. Otherwise falls back to the prior "
                         "milestone's due, then the project start.")
                cur_due = m.get("due_on")
                e_due = st.date_input(
                    "Due (optional)",
                    value=dt.date.fromisoformat(cur_due) if cur_due else None,
                    key=f"msv_due_{m['id']}")
                contrib_labels = {"— none —": None}
                contrib_labels.update({u["full_name"]: u["id"] for u in members})
                cur_contrib = member_name.get(m.get("contributor_id"), "— none —")
                ck = list(contrib_labels.keys())
                e_contrib = st.selectbox(
                    "Contributor", ck,
                    index=ck.index(cur_contrib) if cur_contrib in ck else 0,
                    key=f"msv_contrib_{m['id']}")
                pre_labels = {"— none —": None}
                pre_labels.update({mm["title"]: mm["id"]
                                   for mm in db.project_milestones(project_id)
                                   if mm["id"] != m["id"]})
                cur_pre = ms_title_map.get(m.get("precondition_id"), "— none —")
                pk = list(pre_labels.keys())
                e_pre = st.selectbox(
                    "Depends on (precondition)", pk,
                    index=pk.index(cur_pre) if cur_pre in pk else 0,
                    key=f"msv_pre_{m['id']}")
                # optional category override
                cat_labels = {"— inherit project —": None}
                cat_labels.update({c["label"]: c["id"]
                                   for c in db.categories(domain="work")})
                cur_cat_label = next((lbl for lbl, cid in cat_labels.items()
                                      if cid == m.get("category_id")),
                                     "— inherit project —")
                cak = list(cat_labels.keys())
                e_cat = st.selectbox(
                    "Category (overrides project)", cak,
                    index=cak.index(cur_cat_label)
                    if cur_cat_label in cak else 0,
                    key=f"msv_cat_{m['id']}")
                e_kind = st.radio(
                    "Kind", ["deliverable", "internal"],
                    index=0 if m.get("kind") == "deliverable" else 1,
                    horizontal=True, key=f"msv_kind_{m['id']}",
                    help="Deliverable (external, blue) or internal (grey).")
                # which days you work on this milestone (Sat..Fri), for occupancy
                st.caption("Days you work on this (for occupancy):")
                day_order = [("Sat", 5), ("Sun", 6), ("Mon", 0), ("Tue", 1),
                             ("Wed", 2), ("Thu", 3), ("Fri", 4)]
                cur_days = set(m.get("work_days") or [])
                dcols = st.columns(7)
                chosen_days = []
                for (lbl, num), dc in zip(day_order, dcols):
                    with dc:
                        on = st.checkbox(lbl, value=(num in cur_days),
                                         key=f"msv_day_{m['id']}_{num}")
                        if on:
                            chosen_days.append(num)
                e_hyp = st.text_input("Hypothesis / expected outcome",
                                      value=m.get("hypothesis") or "",
                                      key=f"msv_hyp_{m['id']}")
                e_sm = st.text_input("Success measure",
                                     value=m.get("success_measure") or "",
                                     key=f"msv_sm_{m['id']}")
                st.caption("Estimated hours and the percent/hours tracking choice "
                           "are private — set them in the Planning tab.")
                msv_submit = st.form_submit_button("Save", type="primary")
                if msv_submit and e_title.strip():
                    db.update_milestone(m["id"], {
                        "title": e_title.strip(),
                        "due_on": e_due.isoformat() if e_due else None,
                        "start_on": e_start.isoformat() if e_start else None,
                        "contributor_id": contrib_labels[e_contrib],
                        "precondition_id": pre_labels[e_pre],
                        "category_id": cat_labels[e_cat],
                        "kind": e_kind,
                        "work_days": chosen_days or None,
                        "hypothesis": e_hyp.strip() or None,
                        "success_measure": e_sm.strip() or None})
                    db.clear_user_caches()
                    st.rerun()
                elif msv_submit:
                    st.error("Title can't be empty.")


def view_milestones(me):
    section("Milestones", "All milestones",
            "Every milestone across the projects you take part in.")
    parts = db.projects_i_participate_in()
    if not parts:
        st.caption("You're not part of any projects yet.")
        return
    pids = [p["id"] for p in parts]
    all_ms = db.milestones_for_projects(pids)
    if not all_ms:
        st.caption("No milestones in your projects yet.")
        return
    members = db.group_members()
    member_name = {u["id"]: u["full_name"] for u in members}
    ms_title = {m["id"]: m["title"] for m in all_ms}
    my_ms_hours = db.my_milestone_hours()

    # ---- bar chart: MY milestones' completion % (filtered to me) ----
    mine = [m for m in all_ms if m.get("contributor_id") == me["id"]]
    chart_rows = []
    for m in mine:
        pctv = db.milestone_percent(m, my_hours=my_ms_hours.get(m["id"]) or 0)
        if pctv is not None:
            chart_rows.append((m["title"], pctv))
    if chart_rows:
        chart_rows.sort(key=lambda x: -x[1])
        labels = [t for t, _ in chart_rows]
        values = [v for _, v in chart_rows]
        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color="#3A5A78",
            text=[f"{v}%" for v in values], textposition="outside",
            hovertemplate="%{x}<br>%{y}%<extra></extra>"))
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=30, b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="% complete", range=[0, 100],
                       showgrid=True, gridcolor="#e6e2d8"),
            xaxis=dict(tickangle=-30),
            font=dict(family="Georgia, serif", color="#1F2933"),
            uniformtext=dict(minsize=8, mode="hide"))
        st.markdown("**Your milestones — completion**")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("You have no milestones with a completion figure yet.")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ---- compact overview, then render only the selected milestone editor ----
    by_proj = {}
    for m in all_ms:
        by_proj.setdefault((m["project_name"], m["project_id"]), []).append(m)

    st.markdown("**Milestone overview**")
    for (pname, proj_id), mlist in sorted(by_proj.items()):
        total = len(mlist)
        done = sum(1 for m in mlist if m.get("status") == "done")
        next_due = next((m.get("due_on") for m in sorted(
            mlist, key=lambda x: (x.get("due_on") is None,
                                  x.get("due_on") or ""))
                         if m.get("status") != "done" and m.get("due_on")), None)
        bits = [f"{done}/{total} done"]
        if next_due:
            bits.append(f"next due {next_due}")
        st.caption(f"**{pname}** · " + " · ".join(bits))

    st.markdown("**Edit milestone**")
    project_labels = {pname: proj_id for (pname, proj_id) in sorted(by_proj.keys())}
    if not project_labels:
        st.caption("No milestone to edit.")
        return
    saved_proj_id = st.session_state.get("milestones_selected_project_id")
    saved_proj_name = next((name for name, pid in project_labels.items()
                            if pid == saved_proj_id), None)
    project_names = list(project_labels.keys())
    proj_index = project_names.index(saved_proj_name) if saved_proj_name in project_names else 0
    _reset_picker_if_options_changed("milestones_project_pick", project_names)
    pick_proj = st.selectbox("Project", project_names, index=proj_index,
                             key="milestones_project_pick")
    proj_id = project_labels[pick_proj]
    st.session_state["milestones_selected_project_id"] = proj_id
    mlist = sorted(by_proj[(pick_proj, proj_id)],
                   key=lambda x: (x.get("due_on") is None, x.get("due_on") or ""))
    mlabels = {}
    for m in mlist:
        suffix = f" · due {m['due_on']}" if m.get("due_on") else ""
        status = " · done" if m.get("status") == "done" else ""
        label = f"{m['title']}{suffix}{status}"
        # ensure uniqueness if titles repeat
        if label in mlabels:
            label = f"{label} · {m['id'][:8]}"
        mlabels[label] = m
    saved_mid = st.session_state.get("milestones_selected_id")
    saved_label = next((label for label, m in mlabels.items()
                        if m["id"] == saved_mid), None)
    mkeys = list(mlabels.keys())
    midx = mkeys.index(saved_label) if saved_label in mkeys else 0
    _reset_picker_if_options_changed("milestones_milestone_pick", mkeys)
    pick_m = st.selectbox("Milestone", mkeys, index=midx,
                          key="milestones_milestone_pick")
    selected = mlabels[pick_m]
    st.session_state["milestones_selected_id"] = selected["id"]

    with st.expander(f"Selected milestone — {selected['title']}", expanded=True):
        render_milestone_block(selected, me, members, member_name, ms_title,
                               proj_id, my_ms_hours.get(selected["id"]) or 0)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ---- milestone history (reconstructed from the audit log) ----
    st.markdown("**Milestone history**")
    st.caption("How completion looked at past points in time, reconstructed "
               "from the edit history. Milestones and their due dates may "
               "differ between points as the plan was revised.")
    hc1, hc2 = st.columns(2)
    with hc1:
        hist_proj = st.selectbox("Project", [p["name"] for p in parts],
                                 key="hist_proj")
    with hc2:
        interval = st.selectbox("Interval", ["Monthly", "Every 2 months",
                                             "Weekly"], key="hist_interval")
    hist_pid = next((p["id"] for p in parts if p["name"] == hist_proj), None)
    if hist_pid and st.button("Show history", key="hist_show"):
        audit = db.project_milestone_audit(hist_pid)
        if not audit:
            st.caption("No recorded history for this project yet.")
        else:
            # build interval points from the first audit date to today
            first = (audit[0].get("changed_at") or "")[:10]
            start = dt.date.fromisoformat(first)
            today = dt.date.today()
            step = {"Monthly": 1, "Every 2 months": 2, "Weekly": 0}[interval]
            points = []
            if interval == "Weekly":
                d = start
                while d <= today:
                    points.append(d)
                    d += dt.timedelta(days=7)
            else:
                d = dt.date(start.year, start.month, 1)
                while d <= today:
                    points.append(d)
                    mth = d.month - 1 + step
                    d = dt.date(d.year + mth // 12, mth % 12 + 1, 1)
            if points and points[-1] != today:
                points.append(today)

            # reconstruct each point, gather milestone %s
            # rows: one trace per milestone title, value at each point
            series = {}   # title -> {point_iso: pct}
            for pt in points:
                state = db.reconstruct_milestones_at(audit, pt.isoformat())
                for mid, ms in state.items():
                    if ms["status"] == "done":
                        pct = 100
                    elif ms.get("track_unit") == "percent":
                        pc = ms.get("percent_complete")
                        pct = float(pc) if pc is not None else 0
                    else:
                        pct = 0  # hours-tracked history isn't reconstructable
                    series.setdefault(ms["title"] or mid, {})[
                        pt.isoformat()] = pct

            if not series:
                st.caption("No milestones existed in this window.")
            else:
                fig = go.Figure()
                xlabels = [p.isoformat() for p in points]
                for title, vals in series.items():
                    fig.add_trace(go.Bar(
                        name=title, x=xlabels,
                        y=[vals.get(x) for x in xlabels]))
                fig.update_layout(
                    barmode="group", height=360,
                    margin=dict(l=10, r=10, t=30, b=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="% complete", range=[0, 100],
                               showgrid=True, gridcolor="#e6e2d8"),
                    xaxis=dict(title="as of"),
                    legend=dict(orientation="h", y=1.12),
                    font=dict(family="Georgia, serif", color="#1F2933"))
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Note: milestones tracked in hours show as 0 here, "
                           "since past hours aren't reconstructed; percent-"
                           "tracked and completed milestones are accurate.")




def view_cv(me):
    section("CV", "CV records",
            "Private achievement records you can later polish into CV entries.")

    with st.expander("Add standalone CV entry", expanded=False):
        with st.form("cv_manual_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                entry_date = st.date_input("Date", value=dt.date.today(),
                                           key="cv_manual_date")
                dest = st.selectbox("CV destination",
                                    list(CV_DESTINATIONS.keys()),
                                    key="cv_manual_dest")
                title = st.text_input("Title", key="cv_manual_title",
                                      placeholder="e.g. Editorial Board Member, Structural Safety")
                organisation = st.text_input("Organisation / funder / host",
                                             key="cv_manual_org")
                location = st.text_input("Location (optional)",
                                         key="cv_manual_loc")
            with c2:
                role = st.text_input("Role (optional)", key="cv_manual_role")
                status = st.selectbox("Status", CV_STATUS_OPTIONS, index=0,
                                      key="cv_manual_status")
                evidence = st.text_input("Evidence URL (optional)",
                                         key="cv_manual_evidence")
                metrics = st.text_input("Metrics (optional)",
                                        key="cv_manual_metrics",
                                        placeholder="e.g. c. 100 attendees, £10,000")
            description = st.text_area("Description / draft bullet(s)",
                                       key="cv_manual_desc", height=90)
            outcome = st.text_area("Outcome / significance (optional)",
                                   key="cv_manual_outcome", height=70)
            submitted = st.form_submit_button("Save CV entry", type="primary")
        if submitted:
            if title.strip():
                try:
                    save_cv_entry_from_values(
                        user_id=me["id"], entry_date=entry_date,
                        destination_label=dest, title=title.strip(),
                        organisation=organisation, location=location, role=role,
                        description=description, outcome=outcome,
                        metrics=metrics, evidence_url=evidence,
                        status=status, source_type="manual")
                    db.clear_user_caches()
                    st.success("CV entry saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not save CV entry. {e}")
            else:
                st.error("Give the CV entry a title.")

    summary = db.cv_entry_summary()
    if not summary:
        st.caption("No CV records yet. Add one above or tick the CV option when logging sessions/milestones.")
        return

    # ---- compact summary by year and destination ----
    st.markdown("**Summary by year**")
    by_year = {}
    for r in summary:
        year = r.get("cv_year") or "—"
        sec = r.get("cv_section") or "Other"
        by_year.setdefault(year, {})[sec] = by_year.setdefault(year, {}).get(sec, 0) + 1
    years_sorted = sorted(by_year.keys(), reverse=True)
    metric_cols = st.columns(min(4, max(1, len(years_sorted))))
    for idx, year in enumerate(years_sorted[:4]):
        total = sum(by_year[year].values())
        metric_cols[idx % len(metric_cols)].metric(str(year), f"{total} entries")
    for year in years_sorted:
        with st.expander(f"{year} — {sum(by_year[year].values())} entries"):
            for sec, count in sorted(by_year[year].items()):
                st.caption(f"{sec}: {count}")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("**Review and export**")
    years = ["All"] + [str(y) for y in years_sorted]
    sections = ["All"] + sorted({r.get("cv_section") or "Other" for r in summary})
    statuses = ["All"] + CV_STATUS_OPTIONS
    f1, f2, f3 = st.columns(3)
    with f1:
        year_pick = st.selectbox("Year", years, key="cv_filter_year")
    with f2:
        section_pick = st.selectbox("Section", sections, key="cv_filter_section")
    with f3:
        status_pick = st.selectbox("Status", statuses, key="cv_filter_status")
    entries = db.cv_entries(
        year=None if year_pick == "All" else int(year_pick),
        status=None if status_pick == "All" else status_pick,
        section=None if section_pick == "All" else section_pick)

    if not entries:
        st.caption("No entries match these filters.")
        return

    for e in entries:
        with st.expander(f"{e.get('entry_date')} · {e.get('title')} · {e.get('status')}"):
            st.caption(
                f"{e.get('cv_section') or 'Other'}"
                + (f" → {e.get('cv_subsection')}" if e.get('cv_subsection') else "")
                + f" · source: {e.get('source_type') or 'manual'}")
            if e.get("organisation") or e.get("role") or e.get("location"):
                st.write(" · ".join(v for v in [e.get("role"), e.get("organisation"), e.get("location")] if v))
            for label, key in [("Description", "description"),
                               ("Outcome", "outcome"),
                               ("Metrics", "metrics"),
                               ("Evidence", "evidence_url")]:
                if e.get(key):
                    st.markdown(f"**{label}:** {e.get(key)}")

            with st.form(f"cv_edit_{e['id']}"):
                ec1, ec2 = st.columns(2)
                with ec1:
                    edit_date = st.date_input(
                        "Date", value=dt.date.fromisoformat(e["entry_date"]),
                        key=f"cv_date_{e['id']}")
                    edit_dest_label = cv_destination_label(
                        e.get("cv_section"), e.get("cv_subsection"))
                    dest_keys = list(CV_DESTINATIONS.keys())
                    edit_dest = st.selectbox(
                        "CV destination", dest_keys,
                        index=dest_keys.index(edit_dest_label)
                        if edit_dest_label in dest_keys else 0,
                        key=f"cv_dest_{e['id']}")
                    edit_title = st.text_input("Title", value=e.get("title") or "",
                                               key=f"cv_title_{e['id']}")
                    edit_status = st.selectbox(
                        "Status", CV_STATUS_OPTIONS,
                        index=CV_STATUS_OPTIONS.index(e.get("status"))
                        if e.get("status") in CV_STATUS_OPTIONS else 0,
                        key=f"cv_status_{e['id']}")
                with ec2:
                    edit_org = st.text_input(
                        "Organisation / funder / host",
                        value=e.get("organisation") or "",
                        key=f"cv_org_{e['id']}")
                    edit_role = st.text_input("Role", value=e.get("role") or "",
                                              key=f"cv_role_{e['id']}")
                    edit_loc = st.text_input("Location", value=e.get("location") or "",
                                             key=f"cv_loc_{e['id']}")
                    edit_evidence = st.text_input(
                        "Evidence URL", value=e.get("evidence_url") or "",
                        key=f"cv_evidence_{e['id']}")
                edit_desc = st.text_area(
                    "Description / draft bullet(s)", value=e.get("description") or "",
                    height=90, key=f"cv_desc_{e['id']}")
                edit_outcome = st.text_area(
                    "Outcome / significance", value=e.get("outcome") or "",
                    height=70, key=f"cv_outcome_{e['id']}")
                edit_metrics = st.text_input(
                    "Metrics", value=e.get("metrics") or "",
                    key=f"cv_metrics_{e['id']}")
                save_edit = st.form_submit_button("Save changes", type="primary")
                if save_edit:
                    if edit_title.strip():
                        sec, sub = cv_destination_parts(edit_dest)
                        db.update_cv_entry(e["id"], {
                            "entry_date": edit_date.isoformat(),
                            "cv_section": sec,
                            "cv_subsection": sub,
                            "title": edit_title.strip(),
                            "organisation": edit_org,
                            "location": edit_loc,
                            "role": edit_role,
                            "description": edit_desc,
                            "outcome": edit_outcome,
                            "metrics": edit_metrics,
                            "evidence_url": edit_evidence,
                            "status": edit_status,
                        })
                        db.clear_user_caches()
                        st.success("Updated.")
                        st.rerun()
                    else:
                        st.error("Title can't be empty.")
            if st.button("Delete entry", key=f"cv_delete_{e['id']}"):
                db.delete_cv_entry(e["id"])
                db.clear_user_caches()
                st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("**LaTeX preview**")
    latex = cv_entries_latex(entries)
    st.text_area("Copy into your CV source", value=latex, height=300,
                 key="cv_latex_export")


def view_budget(me):
    section("Budget", "Budget", "Plan items and payments, per project.")
    projs = db.my_projects()
    if not projs:
        st.caption("No projects yet.")
        return
    pick = st.selectbox("Project", [p["name"] for p in projs],
                        key="budget_proj")
    pid = next((p["id"] for p in projs if p["name"] == pick), None)
    if not pid:
        return

    items = db.budget_items(pid)

    # ---- plan items table (Plan / Used / Remaining / Remaining %) ----
    st.markdown("**Plan items**")
    if items:
        cur = items[0].get("currency") or ""
        # header
        h = st.columns([3, 2, 2, 2, 2, 1])
        for col, t in zip(h, ["Item", "Plan", "Used", "Remaining",
                              "Remaining %", ""]):
            col.caption(f"**{t}**")
        for i in items:
            c = st.columns([3, 2, 2, 2, 2, 1])
            c[0].write(i["label"])
            c[1].write(f"{i['plan_amount']:g}")
            c[2].write(f"{i['used']:g}")
            c[3].write(f"{i['remaining']:g}")
            c[4].write("—" if i["remaining_pct"] is None
                       else f"{i['remaining_pct']:g}%")
            if c[5].button("✕", key=f"bi_del_{i['id']}", help="Remove item"):
                db.delete_budget_item(i["id"])
                db.clear_user_caches()
                st.rerun()
        plan_tot = sum(i["plan_amount"] or 0 for i in items)
        used_tot = sum(i["used"] or 0 for i in items)
        s = st.columns([3, 2, 2, 2, 2, 1])
        s[0].write("**Sum**")
        s[1].write(f"**{plan_tot:g}**")
        s[2].write(f"**{used_tot:g}**")
        s[3].write(f"**{plan_tot - used_tot:g}**")
        s[4].write(f"**{round(100*(plan_tot-used_tot)/plan_tot,1):g}%**"
                   if plan_tot else "—")
    else:
        st.caption("No plan items yet — add one below.")

    with st.form(f"add_item_{pid}", clear_on_submit=True):
        ic = st.columns([3, 2, 2])
        with ic[0]:
            it_label = st.text_input("Item", key=f"itlabel_{pid}",
                                     placeholder="e.g. Conference")
        with ic[1]:
            it_plan = st.number_input("Plan amount", min_value=0.0, step=100.0,
                                      key=f"itplan_{pid}")
        with ic[2]:
            it_cur = st.selectbox("Currency", ["GBP", "USD", "EUR", "KRW"],
                                  key=f"itcur_{pid}")
        if st.form_submit_button("Add plan item"):
            if it_label.strip():
                db.add_budget_item(pid, it_label.strip(), it_plan, it_cur)
                db.clear_user_caches()
                st.rerun()
            else:
                st.error("Give the item a name.")

    # ---- payments (each linked to a plan item) ----
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("**Payments**")
    pays = db.budget_payments(pid)
    if pays:
        for p in pays:
            pc = st.columns([3, 3, 2, 2, 1])
            pc[0].write(p.get("detail1") or "—")
            pc[1].write(p.get("detail2") or "")
            pc[2].write(f"{p['amount']:g}")
            pc[3].write(p.get("paid_on") or "")
            pc4 = pc[4]
            pc[0].caption(f"→ {p['item_label']}")
            if pc4.button("✕", key=f"pay_del_{p['id']}", help="Remove"):
                db.delete_budget_payment(p["id"])
                db.clear_user_caches()
                st.rerun()
    else:
        st.caption("No payments logged yet.")

    if items:
        with st.form(f"add_pay_{pid}", clear_on_submit=True):
            item_labels = {i["label"]: i["id"] for i in items}
            pcol = st.columns([2, 3, 3, 2, 2])
            with pcol[0]:
                pay_item = st.selectbox("Links to", list(item_labels.keys()),
                                        key=f"payitem_{pid}")
            with pcol[1]:
                pay_d1 = st.text_input("Detail 1", key=f"payd1_{pid}",
                                       placeholder="e.g. Kick-off meeting")
            with pcol[2]:
                pay_d2 = st.text_input("Detail 2", key=f"payd2_{pid}",
                                       placeholder="e.g. Train")
            with pcol[3]:
                pay_amt = st.number_input("Amount", min_value=0.0, step=10.0,
                                          key=f"payamt_{pid}")
            with pcol[4]:
                pay_date = st.date_input("Date", value=dt.date.today(),
                                         key=f"paydate_{pid}")
            if st.form_submit_button("Add payment"):
                if pay_amt > 0:
                    db.add_budget_payment(
                        item_labels[pay_item], pay_amt,
                        detail1=pay_d1.strip() or None,
                        detail2=pay_d2.strip() or None,
                        paid_on=pay_date.isoformat())
                    db.clear_user_caches()
                    st.rerun()
                else:
                    st.error("Enter a non-zero amount.")

    # ---- spent % vs milestone % vs time elapsed % ----
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("**Spend against progress**")
    plan_tot = sum(i["plan_amount"] or 0 for i in items) if items else 0
    used_tot = sum(i["used"] or 0 for i in items) if items else 0
    spent_pct = round(100 * used_tot / plan_tot) if plan_tot else None
    prog = db.milestone_progress(pid)
    prog_pct = prog["pct"]
    time_pct = db.project_time_elapsed_pct(pid)
    bars = []
    if spent_pct is not None:
        bars.append(("Budget spent", spent_pct, "#C2703D"))
    if prog_pct is not None:
        bars.append(("Milestones done", prog_pct, "#3A5A78"))
    if time_pct is not None:
        bars.append(("Time elapsed", time_pct, "#9aa5b1"))
    if bars:
        fig = go.Figure(go.Bar(
            x=[b[0] for b in bars], y=[b[1] for b in bars],
            marker_color=[b[2] for b in bars],
            text=[f"{b[1]}%" for b in bars], textposition="outside"))
        fig.update_layout(
            height=300, margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[0, 100], title="%", showgrid=True,
                       gridcolor="#e6e2d8"),
            showlegend=False,
            font=dict(family="Georgia, serif", color="#1F2933"))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Compare how much budget is spent against how far the work "
                   "has progressed and how much of the timeline has passed. "
                   "Spend running ahead of progress and time may signal "
                   "overspend; behind may signal underspend.")
    else:
        st.caption("Add plan items, milestones, and project dates to compare "
                   "spend against progress.")


def view_planning(me):
    section("Planning", "Planning",
            "Your private estimated hours and progress. Only you see this — "
            "not the lead. What others see is each milestone's completion %.")
    parts = db.projects_i_participate_in()
    mine = [m for m in db.milestones_for_projects([p["id"] for p in parts])
            if m.get("contributor_id") == me["id"]]
    if not mine:
        st.caption("No milestones are attributed to you yet.")
        return
    plans = db.my_milestone_plans()
    by_proj = {}
    for m in mine:
        by_proj.setdefault(m["project_name"], []).append(m)

    st.markdown("**Your assigned milestones**")
    for pname, mlist in sorted(by_proj.items()):
        total = len(mlist)
        planned = sum(1 for m in mlist if plans.get(m["id"], {}).get("planned_hours"))
        st.caption(f"**{pname}** · {planned}/{total} with private hour estimates")

    st.markdown("**Plan milestone**")
    project_names = sorted(by_proj.keys())
    saved_project = st.session_state.get("planning_selected_project")
    pidx = project_names.index(saved_project) if saved_project in project_names else 0
    pname = st.selectbox("Project", project_names, index=pidx,
                         key="planning_project_pick")
    st.session_state["planning_selected_project"] = pname
    mlist = sorted(by_proj[pname], key=lambda x: (x.get("due_on") is None,
                                                  x.get("due_on") or ""))
    mlabels = {}
    for m in mlist:
        label = m["title"] + (f" · due {m['due_on']}" if m.get("due_on") else "")
        if label in mlabels:
            label = f"{label} · {m['id'][:8]}"
        mlabels[label] = m
    saved_mid = st.session_state.get("planning_selected_milestone_id")
    saved_label = next((label for label, m in mlabels.items()
                        if m["id"] == saved_mid), None)
    mkeys = list(mlabels.keys())
    midx = mkeys.index(saved_label) if saved_label in mkeys else 0
    pick = st.selectbox("Milestone", mkeys, index=midx,
                        key="planning_milestone_pick")
    m = mlabels[pick]
    st.session_state["planning_selected_milestone_id"] = m["id"]
    plan = plans.get(m["id"], {})

    with st.expander(f"Selected milestone — {m['title']}", expanded=True):
        unit = st.radio(
            "Track progress as", ["percent", "hours"],
            index=0 if plan.get("track_unit") != "hours" else 1,
            horizontal=True, key=f"pl_unit_{m['id']}")
        ph = st.number_input(
            "Estimated hours (private)", min_value=0.0, step=1.0,
            value=float(plan.get("planned_hours") or 0),
            key=f"pl_ph_{m['id']}",
            help="Only you see this. Used for your occupancy view.")
        # progress: either a direct % or hours-derived %
        if unit == "percent":
            pc = st.number_input(
                "Percent complete", min_value=0.0, max_value=100.0,
                step=5.0, value=float(plan.get("percent_complete") or 0),
                key=f"pl_pct_{m['id']}")
            derived = pc
        else:
            logged = db.my_milestone_hours().get(m["id"]) or 0
            derived = (min(round(100 * logged / ph), 100) if ph else 0)
            st.caption(f"From your logged {logged:g} h against "
                       f"{ph:g} planned: {derived}% (this % is shared; "
                       f"the hours are not).")
            pc = None
        if st.button("Save", key=f"pl_save_{m['id']}", type="primary"):
            db.upsert_milestone_plan(m["id"], me["id"], ph or None, unit, pc)
            # publish only the % to the shared milestone row
            db.set_milestone_shared_percent(m["id"], derived)
            db.clear_user_caches()
            st.rerun()
        st.caption(f"Shared completion now: {m.get('shared_percent') or 0:g}%")



def view_help(me):
    is_lead = me.get("role") == "lead"
    section("Help", "How this works",
            "A short guide to tracking your time and milestones.")

    st.markdown(
        "This app helps the group plan projects, track time, and follow "
        "milestone progress together. Here is the most important thing to "
        "know first.")

    st.markdown("### Recording your work")
    st.markdown("How to put information into the tracker.")

    with st.expander("1. Record your week's work"):
        st.markdown(
            "Use the **Log** tab to record a block of time you have worked. "
            "Choose the category, and (for work) optionally the project and "
            "milestone it belongs to. Set the day and either a start and end "
            "time, or just a number of minutes. You can type a time directly, "
            "for example 0930 or 9:30. Add a short note if you like, then "
            "click **Save session**.\n\n"
            "The **Week** tab is a faster way to fill in a whole week. Pick a "
            "day, a category, the times, and what you worked on, then **Add "
            "block**. It also keeps a weekly to-do list, where you can jot "
            "tasks, give each an estimated number of hours, tick them off, and "
            "carry unfinished ones into next week.")

    with st.expander("2. Record a new project with milestones"):
        st.markdown(
            "You can create a project on the fly while logging (choose **+ New "
            "project…** in the project dropdown), or in the **Projects** tab. "
            "In the project's **Details & milestones** panel you can set its "
            "name, category, status, start and due dates, and who is involved. "
            "A project is visible only to its owner and the people added to "
            "it, so a project you keep to yourself stays private.\n\n"
            "Within the same panel, add **milestones** to the project. Each "
            "milestone has a title and an optional due date, and you can also "
            "set who is in charge of it, whether it depends on another "
            "milestone finishing first, an optional start date, and whether it "
            "is a *deliverable* (shown in blue on the timeline) or an "
            "*internal* step (shown in grey).")

    with st.expander("3. Plan and track each milestone"):
        st.markdown(
            "Use the **Planning** tab to plan and follow your own milestones. "
            "For each one you set an estimated number of hours and choose how "
            "to track it.\n\n"
            "If you track by **percent**, you simply type how far along you "
            "are. If you track by **hours**, the percentage is worked out "
            "automatically from the hours you have logged against your "
            "estimate, and it updates as you log more time.\n\n"
            "Either way, only the resulting **percentage** is shared with the "
            "group. Your estimated hours, your logged hours, and your choice "
            "of tracking method stay private to you.")

    st.markdown("### Monitoring progress")
    st.markdown("Where to look to see how things are going.")

    with st.expander("Week — your week at a glance"):
        st.markdown(
            "The **Week** tab shows the selected week as blocks across the "
            "days, with your hours split by category in a chart, alongside "
            "your weekly to-do list. It is the quickest way to see how a week "
            "is filling up and what is left to do.")

    with st.expander("Projects — timelines and progress"):
        st.markdown(
            "The **Projects** tab shows a timeline (Gantt) of the projects you "
            "are part of. Each project's milestones appear as diamonds on "
            "their due dates, and the bar shows each milestone's active period "
            "(with gaps where nothing is scheduled). Below each project is a "
            "bar chart of its milestones' completion. The **Your daily "
            "occupancy** chart spreads your planned milestone hours across the "
            "coming weeks, coloured by category, so you can spot days that "
            "look overloaded.")

    with st.expander("Milestones — the full list and history"):
        st.markdown(
            "The **Milestones** tab lists every milestone across the projects "
            "you take part in, grouped by project, with each one's completion "
            "and recent progress notes. You can mark a milestone done, add a "
            "note, or open it to edit its details. It is the place to follow "
            "milestone-level progress across everything you are involved in.")

    with st.expander("Planning — your private plan and progress"):
        st.markdown(
            "The **Planning** tab is also where you monitor your own plan: the "
            "estimated hours, tracking method, and current percentage for each "
            "of your milestones, all in one place. Only you see this view of "
            "your own numbers.")

    with st.expander("Time — where your hours have gone"):
        st.markdown(
            "The **Time** tab summarises your recorded hours over a period you "
            "choose (week, month, year, or a custom range). It shows how your "
            "time splits across categories and highlights the hours on "
            "projects you have marked as high importance, so you can see "
            "whether your effort matches your priorities.")

    if is_lead:
        with st.expander("Budget (lead only)"):
            st.markdown(
                "The **Budget** tab, visible only to you, lets you plan budget "
                "items per project, record payments against them, and compare "
                "how much is spent against how far the work has progressed and "
                "how much of the timeline has passed.")

    st.markdown("#### Your privacy")
    st.markdown(
        "Your exact hours are private to you. The estimated hours you set for "
        "a milestone, and whether you track it in hours or percent, live in "
        "the **Planning** tab and only you can see them. Not even the group "
        "lead sees your hours. What everyone in a project sees is each "
        "milestone's **completion percentage**, never the hours behind it.\n\n"
        "Projects are private to the people involved in them. You see a "
        "project only if you own it or have been added to it. You can keep "
        "your own projects to yourself simply by not adding anyone else.")

    st.markdown("#### A note on what others see")
    st.markdown(
        "Within a project you share with others, everyone can see the "
        "project's milestones, who is in charge of each, and their completion "
        "percentages and progress notes. Nobody sees anyone else's hours or "
        "estimates. If something here is unclear or doesn't match what you "
        "expected, tell the group lead.")


def main():
    sess = db.current_session()
    if not sess or not getattr(sess, "user", None):
        auth_gate()
        return

    me = db.my_app_user()
    if not me:
        link_gate(None)
        return

    # header
    left, right = st.columns([5, 1])
    with left:
        st.markdown(f"<span class='eyebrow'>Signed in</span>",
                    unsafe_allow_html=True)
        st.markdown(f"<div class='section-title'>{me['full_name']}</div>",
                    unsafe_allow_html=True)
    with right:
        if st.button("Sign out"):
            db.sign_out()
            st.rerun()

    is_lead = me.get("role") == "lead"
    view_funcs = {
        "Log": view_log,
        "Week": view_week,
        "Projects": view_projects,
        "Milestones": view_milestones,
        "Planning": view_planning,
        "Time": view_time,
        "CV": view_cv,
    }
    if is_lead:
        view_funcs["Budget"] = view_budget
    view_funcs["Help"] = view_help

    # Use a normal radio selector instead of st.tabs. Streamlit tabs compute
    # every tab body on every run; this renders only the selected section.
    names = list(view_funcs.keys())
    current = st.session_state.get("main_section", "Log")
    if current not in names:
        current = names[0]
        st.session_state["main_section"] = current
    index = names.index(current)
    page = st.radio("Section", names, index=index, horizontal=True,
                    key="main_section")
    st.markdown("<hr>", unsafe_allow_html=True)
    view_funcs[page](me)


if __name__ == "__main__":
    main()
