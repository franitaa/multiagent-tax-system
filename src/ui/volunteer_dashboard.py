"""Volunteer dashboard (Kushim). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the page where a Kushim volunteer sees every case and resolves the alarms.
Run it next to the chat page:  streamlit run src/ui/volunteer_dashboard.py --server.port 8502

What it does:
  - "All cases": counts at the top (needs a volunteer / answering questions / draft ready /
    stopped / open questions) and one row per case, those needing a volunteer first, with an
    Open button. "Needs" also shows quiet requests, e.g. "Asked to talk to a volunteer".
  - One case: what the alarm is about in plain words, the taxpayer's own words, their answers
    (SSNs masked), the draft form when there is one, and the case history from the audit log.
  - Resolving: only the choices the human gate allows (e.g. pressure can only be stopped, and
    the page says why), a note, and a list of valid answers where one is needed (filing
    status, a "not sure" answer). The volunteer's name is required and goes in the audit log.
  - Same saved-sessions file as the chat page, so a paused chat appears here straight away;
    after a decision the taxpayer presses "Check again" on their page and carries on.

What is still missing:
  - Approving a W-2 reading is done on JiWon's W-2 page.
  - No login: a classroom demo on one computer. In real use only staff should see this page,
    because it shows taxpayers' own words about possible pressure or abuse.

All logic is in src/ui/dashboard_data.py; this file only draws the page.
"""
import html
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # so "src." imports work

from src import state as S  # noqa: E402
from src.ui import dashboard_data as dash  # noqa: E402

st.set_page_config(page_title="Kushim - Volunteer dashboard", page_icon=None, layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, p, label, input, textarea, button { font-size: 18px !important; }
    h1 { font-size: 32px !important; } h2 { font-size: 26px !important; } h3 { font-size: 22px !important; }
    .stApp { background: #f4f7fc; color: #111111; }
    label, h1, h2, h3, p, li, .stMarkdown { color: #111111 !important; }
    .msym { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
            letter-spacing: normal; text-transform: none; white-space: nowrap; direction: ltr;
            font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; }
    .hero { background: linear-gradient(135deg, #1d6b3a 0%, #2e8b57 100%); border-radius: 16px;
            padding: 26px 32px; margin-bottom: 22px; }
    .hero h1 { color: #ffffff !important; margin: 0 0 4px 0; padding: 0; font-size: 36px !important; }
    .hero p { color: #e4f4ea !important; margin: 0; font-size: 20px !important; }
    /* White cards: the summary cards, the case list and each section of a case */
    [class*="st-key-card-"], .st-key-cases-card, [class*="st-key-sec-"], .st-key-case-head {
        box-sizing: border-box; max-width: 100%; background: #ffffff; border-radius: 14px; padding: 20px 24px; border: 1px solid #e3e8f0;
        box-shadow: 0 2px 10px rgba(31, 78, 154, 0.06); }
    [class*="st-key-card-"] { height: 100%; }
    .card-title { font-size: 22px; font-weight: 700; margin: 0 0 14px 0; color: #111111; }
    /* Summary card: an icon circle, a label and a number per line */
    .stat { display: flex; align-items: center; gap: 14px; margin: 0 0 14px 0; }
    .stat .dot { flex: 0 0 52px; height: 52px; border-radius: 50%; display: flex; align-items: center;
                 justify-content: center; color: #ffffff; }
    .stat .dot .msym { font-size: 28px; }
    .stat .label { font-size: 16px; color: #555555; display: block; }
    .stat .value { font-size: 26px; font-weight: 800; color: #111111; line-height: 1.1; }
    /* Donut: total in the middle, a key with the numbers beside it (so it does not rely on colour) */
    .donut-row { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
    .donut { flex: 0 0 170px; width: 170px; height: 170px; border-radius: 50%; display: flex;
             align-items: center; justify-content: center; }
    .hole { width: 112px; height: 112px; border-radius: 50%; background: #ffffff; display: flex;
            flex-direction: column; align-items: center; justify-content: center; }
    .hole span { font-size: 15px; color: #555555; } .hole b { font-size: 34px; color: #111111; line-height: 1.1; }
    .legend { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 22px; flex: 1 1 200px; }
    .legend div { font-size: 16px; color: #444444; }
    .legend i { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 7px; }
    .legend b { display: block; font-size: 22px; color: #111111; margin-left: 18px; }
    .st-key-sec-decision { border-top: 8px solid #d98c00; }
    .st-key-case-head { border-left: 8px solid #1d6b3a; }
    .case-name { font-size: 30px; font-weight: 800; margin: 0; }
    .case-id { font-size: 18px; color: #555555; letter-spacing: 1px; }
    .head { background: #eef2f8; border-radius: 8px; padding: 8px 10px; }
    /* Filter buttons above the case list */
    [data-testid="stButtonGroup"] button { font-size: 17px !important; }
    /* Sidebar */
    [data-testid="stSidebar"] { background: #eef5f0; border-right: 1px solid #d3e6da; }
    .side-head { background: linear-gradient(135deg, #1d6b3a 0%, #2e8b57 100%); color: #ffffff;
                 border-radius: 14px; padding: 18px 18px; margin-bottom: 16px; }
    .side-head .who-icon { font-size: 36px; display: block; margin-bottom: 4px; color: #ffffff; }
    .side-head b { color: #ffffff; font-size: 22px; display: block; }
    .side-head span { color: #e4f4ea; font-size: 16px; }
    .signed-in { background: #ffffff; border: 1px solid #a7d8b8; border-radius: 10px; padding: 10px 12px;
                 margin: 6px 0 14px 0; font-size: 17px; }
    .signed-in.missing { border-color: #e3a3a3; background: #fff5f5; }
    .st-key-refresh .stButton button { background: #1d6b3a !important; color: #ffffff !important; border: none !important;
                             width: 100%; }
    .st-key-refresh .stButton button * { color: #ffffff !important; }
    .st-key-refresh .stButton button:hover { background: #24804a !important; }
    .side-help { background: #ffffff; border-radius: 10px; padding: 12px 14px; margin-top: 16px;
                 font-size: 16px; color: #333333; line-height: 1.5; }
    .side-help b { display: block; margin-bottom: 4px; }
    .badge { display: inline-block; padding: 2px 12px; border-radius: 12px; font-weight: 700; font-size: 16px; }
    .needs { background: #fde8e8; color: #8a1c1c; border: 1px solid #e3a3a3; }
    .answering { background: #eef3fb; color: #1f4e9a; border: 1px solid #b7c8e6; }
    .ready { background: #e7f5ec; color: #1d6b3a; border: 1px solid #a7d8b8; }
    .stopped { background: #f1f1f1; color: #444444; border: 1px solid #cccccc; }
    .row { padding: 6px 0; border-top: 1px solid #e3e3e3; }
    .head { font-weight: 700; color: #444444; }
    .muted { color: #555555; }
    .card { padding: 14px 18px; border-radius: 10px; background: #fff7e6; border-left: 6px solid #d98c00; margin: 8px 0; }
    .note { padding: 10px 14px; border-radius: 8px; background: #f6f6f6; margin: 6px 0; }
    .stButton button, .stFormSubmitButton button {
        min-height: 2.6rem; font-weight: 700; border: 2px solid #1f4e9a;
        background: #ffffff !important; color: #111111 !important;
    }
    .stButton button:hover, .stFormSubmitButton button:hover { background: #eef3fb !important; }
    input, textarea, [data-baseweb="input"] > div, [data-baseweb="select"] > div,
    [data-baseweb="textarea"] > div { background: #ffffff !important; color: #111111 !important; }
    .stButton button:focus, .stFormSubmitButton button:focus, input:focus, textarea:focus {
        outline: 4px solid #f2a900 !important; outline-offset: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

BADGE = {dash.NEEDS_VOLUNTEER: "needs", dash.ANSWERING: "answering", dash.DRAFT_READY: "ready",
         dash.STOPPED: "stopped"}
DECISION_WORDS = {"continue": "Continue: the taxpayer carries on", "stop": "Stop the case"}


@st.cache_resource
def get_graph():
    """One graph for the app, reading the same saved-sessions file as the chat page."""
    return dash.open_graph()


def badge(status: str) -> str:
    return f'<span class="badge {BADGE[status]}">{html.escape(status)}</span>'


def local_time(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime("%b %d, %H:%M")


def sidebar() -> str:
    with st.sidebar:
        st.markdown('<div class="side-head"><span class="who-icon msym" aria-hidden="true">volunteer_activism</span>'
                    "<b>Volunteer</b><span>Kushim SilverFile</span></div>", unsafe_allow_html=True)
        name = st.text_input("Your name (shown in the case record)", key="volunteer")
        if name.strip():
            st.markdown(f'<div class="signed-in"><span class="msym" aria-hidden="true" style="color:#1d6b3a;vertical-align:-5px">check_circle</span> Working as <b>{html.escape(name.strip())}</b></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="signed-in missing">Type your name to resolve cases.</div>',
                        unsafe_allow_html=True)
        if st.button("Refresh cases", key="refresh", icon=":material/refresh:"):
            st.rerun()
        st.caption(f"Last updated {datetime.now().strftime('%H:%M:%S')}")
        st.markdown('<div class="side-help"><b>How it works</b>Cases appear as taxpayers use the chat. '
                    "Red ones need a person: open the case, read what happened, and save your decision. "
                    "The taxpayer then carries on.</div>", unsafe_allow_html=True)
    return name


STATUS_COLOURS = {dash.NEEDS_VOLUNTEER: "#c0392b", dash.ANSWERING: "#1f4e9a", dash.DRAFT_READY: "#1d6b3a",
                  dash.STOPPED: "#9a9a9a"}
NEED_COLOURS = ["#e8590c", "#d6336c", "#7048e8", "#1c7ed6", "#0ca678", "#f59f00", "#868e96", "#ae3ec9", "#495057"]


def donut(parts: list[tuple[str, int, str]], centre: str) -> str:
    """A ring split by `parts` (label, number, colour) with the total in the middle and a key with
    the numbers beside it. Drawn with CSS only; screen readers get the same numbers as text."""
    total = sum(n for _, n, _ in parts)
    stops, start = [], 0.0
    for _, n, colour in parts:
        if n:
            end = start + 100 * n / total
            stops.append(f"{colour} {start:.2f}% {end:.2f}%")
            start = end
    ring = f"conic-gradient({', '.join(stops)})" if stops else "#e6e9ef"
    summary = ", ".join(f"{label}: {n}" for label, n, _ in parts) or "none"
    key = "".join(f'<div><i style="background:{colour}"></i>{html.escape(label)}<b>{n}</b></div>'
                  for label, n, colour in parts)
    return (f'<div class="donut-row"><div class="donut" style="background:{ring}" role="img" '
            f'aria-label="{html.escape(centre)} {total}. {html.escape(summary)}">'
            f'<div class="hole"><span>{html.escape(centre)}</span><b>{total}</b></div></div>'
            f'<div class="legend">{key}</div></div>')


def summary_cards(rows: list[dict]) -> None:
    counts = dash.counts(rows)
    left, middle, right = st.columns([1.15, 1.35, 1.35], gap="medium")
    with left, st.container(key="card-summary"):
        stats = [("folder_open", "#1f4e9a", "Total cases", len(rows)),
                 ("notifications_active", "#c0392b", "Need a volunteer now", counts[dash.NEEDS_VOLUNTEER]),
                 ("help", "#d98c00", "Open questions", counts[dash.OPEN_QUESTIONS]),
                 ("task_alt", "#1d6b3a", "Drafts ready", counts[dash.DRAFT_READY])]
        lines = "".join(f'<div class="stat"><span class="dot" style="background:{colour}" aria-hidden="true"><span class="msym">{icon}</span></span>'
                        f'<div><span class="label">{label}</span><span class="value">{n}</span></div></div>'
                        for icon, colour, label, n in stats)
        st.markdown(f'<div class="card-title">Summary</div>{lines}', unsafe_allow_html=True)
    with middle, st.container(key="card-status"):
        parts = [(s, counts[s], STATUS_COLOURS[s]) for s in dash.STATUS_ORDER]
        st.markdown(f'<div class="card-title">Cases by status</div>{donut(parts, "Total")}', unsafe_allow_html=True)
    with right, st.container(key="card-needs"):
        needs = dash.needs_breakdown(rows)
        parts = [(label, n, NEED_COLOURS[i % len(NEED_COLOURS)]) for i, (label, n) in enumerate(needs.items())]
        body = donut(parts, "Waiting") if parts else '<p class="muted">Nobody is waiting for a volunteer.</p>'
        st.markdown(f'<div class="card-title">What volunteers are needed for</div>{body}', unsafe_allow_html=True)


def list_screen(graph) -> None:
    st.markdown('<div class="hero"><h1>Kushim volunteer dashboard</h1>'
                "<p>Every SilverFile case, and the ones that need a person.</p></div>", unsafe_allow_html=True)
    rows = dash.all_cases(graph)
    summary_cards(rows)
    st.write("")
    with st.container(key="cases-card"):
        st.subheader("All cases")
        if not rows:
            st.info("No cases yet. They appear here when a taxpayer starts a session on the chat page.")
            return
        show = st.pills("Show", ["All", *dash.STATUS_ORDER, dash.OPEN_QUESTIONS], default="All",
                        key="show") or "All"
        search = st.columns([1.2, 2])[0].text_input("Search by case ID or name", key="search")
        shown = [r for r in rows if dash.matches(r, show, search)]
        if shown:
            case_rows(shown)
        else:
            st.write("No cases match.")


def case_rows(rows: list[dict]) -> None:
    widths = [1.25, 1.5, 1.6, 3.0, 1.15, 1.0]
    for column, title in zip(st.columns(widths), ["Case ID", "Taxpayer", "Status", "Needs", "Last active", ""]):
        column.markdown(f'<div class="head">{title}</div>', unsafe_allow_html=True)
    for row in rows:
        cells = st.columns(widths, vertical_alignment="center")
        cells[0].markdown(f'<div class="row"><b>{html.escape(row["case_id"])}</b></div>', unsafe_allow_html=True)
        cells[1].markdown(f'<div class="row">{html.escape(row["name"])}</div>', unsafe_allow_html=True)
        cells[2].markdown(f'<div class="row">{badge(row["status"])}</div>', unsafe_allow_html=True)
        needs = " · ".join(p for p in (row["alarm"], dash.open_questions_text(row)) if p) or "–"
        cells[3].markdown(f'<div class="row">{html.escape(needs)}</div>', unsafe_allow_html=True)
        cells[4].markdown(f'<div class="row muted">{dash.time_ago(row["last_active"])}</div>', unsafe_allow_html=True)
        if cells[5].button("Open", key=f"open-{row['case_id']}"):
            st.session_state.open_case = row["case_id"]
            st.rerun()


def resolve_form(graph, case_id: str, waiting: dict, volunteer: str) -> None:
    with st.container(key="sec-decision"):
        decision_box(graph, case_id, waiting, volunteer)


def decision_box(graph, case_id: str, waiting: dict, volunteer: str) -> None:
    st.subheader("Needs your decision")
    alarm = dash.ALARMS.get(waiting["condition"], waiting["condition"])
    st.markdown(f'<div class="card"><b>{html.escape(alarm)}</b><br>'
                f'<span class="muted">Reason recorded: {html.escape(waiting.get("reason") or "–")}</span></div>',
                unsafe_allow_html=True)
    if waiting.get("also_pending"):
        more = ", ".join(dash.ALARMS.get(c, c) for c in waiting["also_pending"])
        st.info(f"After this, {len(waiting['also_pending'])} more alarm(s) for this case: {more}")
    if waiting.get("error"):
        st.error(waiting["error"])
    if waiting["condition"] == S.EXTRACTION_REVIEW:
        st.info("This W-2 reading is checked and approved on the W-2 page.")
        return
    options = waiting["options"]
    if options == ["stop"]:
        st.info(dash.STOP_ONLY_WHY)
    with st.form("resolve"):
        decision = st.radio("Your decision", options, format_func=DECISION_WORDS.get)
        resolution = {}
        choices = dash.choices(waiting)
        if choices and "continue" in options:
            field = "filing_status" if waiting["condition"] == S.FILING_STATUS_AMBIGUITY else waiting["resolution_fields"][0]
            picked = st.selectbox(f"If you continue: the correct {field.replace('_', ' ')}", list(choices),
                                  format_func=choices.get, index=None, placeholder="Choose one")
            if picked:
                resolution = {field: picked}
        elif waiting["condition"] == S.SOURCE_CONFLICT:
            fact = st.text_input("If you continue: the answer name to correct (optional)")
            value = st.text_input("Its correct value")
            if fact.strip() and value.strip():
                resolution = {fact.strip(): value.strip()}
        note = st.text_area("Note for the record (required to continue)")
        if st.form_submit_button("Save decision"):
            error = dash.resolve(graph, case_id, decision, note,
                                 volunteer, resolution if decision == "continue" else None)
            if error:
                st.error(error)
            else:
                st.session_state.saved = f"Decision saved for {case_id}."
                st.rerun()


def case_screen(graph, case_id: str, volunteer: str) -> None:
    if st.button("← Back to all cases"):
        del st.session_state.open_case
        st.rerun()
    row = dash.case_summary(graph, case_id)
    with st.container(key="case-head"):
        needs = " · ".join(p for p in (row["alarm"], dash.open_questions_text(row)) if p)
        st.markdown(f'<div class="case-id">{html.escape(case_id)}</div>'
                    f'<h1 class="case-name">{html.escape(row["name"])}</h1>'
                    f'{badge(row["status"])} <span class="muted">Last active {dash.time_ago(row["last_active"])}'
                    f'{" · " + html.escape(needs) if needs else ""}</span>', unsafe_allow_html=True)
    if volunteer.strip() and st.session_state.get("viewed") != (case_id, volunteer):
        dash.record_view(case_id, volunteer.strip())  # the audit log records who opened the case
        st.session_state.viewed = (case_id, volunteer)

    waiting = dash.pending(graph, case_id)
    if waiting:
        resolve_form(graph, case_id, waiting, volunteer)

    left, right = st.columns([1, 1], gap="medium")
    with left, st.container(key="sec-notes"):
        st.subheader("Notes for the volunteer")
        notes = dash.volunteer_notes(graph, case_id)
        for n in notes:
            words = f'<br>Taxpayer said: "{html.escape(n["taxpayer_words"])}"' if n.get("taxpayer_words") else ""
            done = " (answered later)" if n.get("resolved") else ""
            st.markdown(f'<div class="note"><b>{html.escape(n.get("question_text") or n.get("question", ""))}</b>'
                        f'<br>{html.escape(n.get("reason", ""))}{done}{words}</div>', unsafe_allow_html=True)
        if not notes:
            st.write("No notes.")
    with right, st.container(key="sec-answers"):
        st.subheader("Answers so far")
        answers = dash.answers(graph, case_id)
        if answers:
            st.dataframe([{"Question": a["question"], "Answer": a["answer"]} for a in answers],
                         hide_index=True, use_container_width=True)
        else:
            st.write("No answers yet.")

    page = dash.draft_form_html(graph, case_id)
    if page:
        with st.container(key="sec-draft"):
            st.subheader("Draft tax form")
            st.download_button("Download the draft form", page, file_name=f"{case_id}_1040sr.html", mime="text/html")
            with st.expander("Show the draft form (click any amount to see where it came from)"):
                components.html(page, height=800, scrolling=True)

    with st.container(key="sec-history"):
        st.subheader("Case history")
        rows = dash.history(case_id)
        if rows:
            st.dataframe([{"When": local_time(r["when"]), "Who": r["who"], "What": r["what"], "Detail": r["detail"]}
                          for r in rows], hide_index=True, use_container_width=True)
            st.caption("Record intact: no entries changed." if dash.history_intact(case_id)
                       else "Warning: this record has been changed.")
        else:
            st.write("Nothing recorded yet.")


graph = get_graph()
volunteer = sidebar()
if st.session_state.get("saved"):
    st.success(st.session_state.pop("saved"))
if "open_case" in st.session_state:  # not "case_id": that is the chat page's own session
    case_screen(graph, st.session_state.open_case, volunteer)
else:
    list_screen(graph)
