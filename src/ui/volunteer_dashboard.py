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
    h1 { font-size: 32px !important; } h2 { font-size: 26px !important; } h3 { font-size: 21px !important; }
    .stApp { background: #ffffff; color: #111111; }
    label, h1, h2, h3, p, li, .stMarkdown { color: #111111 !important; }
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
        st.header("Volunteer")
        name = st.text_input("Your name (shown in the case record)", key="volunteer")
        if st.button("Refresh"):
            st.rerun()
        st.caption("Cases appear here as taxpayers use the chat page. Open a case to see it and "
                   "to resolve its alarm.")
    return name


def list_screen(graph) -> None:
    st.title("Kushim SilverFile – Volunteer dashboard")
    rows = dash.all_cases(graph)
    counts = dash.counts(rows)
    for column, label in zip(st.columns(5), [*dash.STATUS_ORDER, dash.OPEN_QUESTIONS]):
        column.metric(label, counts[label])
    if not rows:
        st.info("No cases yet. They appear here when a taxpayer starts a session on the chat page.")
        return
    widths = [1.2, 1.6, 1.5, 3.4, 1.2, 0.9]
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
            st.session_state.case_id = row["case_id"]
            st.rerun()


def resolve_form(graph, case_id: str, waiting: dict, volunteer: str) -> None:
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
        del st.session_state.case_id
        st.rerun()
    row = dash.case_summary(graph, case_id)
    st.title(f"{case_id} – {row['name']}")
    st.markdown(f'{badge(row["status"])} <span class="muted">Last active {dash.time_ago(row["last_active"])}</span>',
                unsafe_allow_html=True)
    if volunteer.strip() and st.session_state.get("viewed") != (case_id, volunteer):
        dash.record_view(case_id, volunteer.strip())  # the audit log records who opened the case
        st.session_state.viewed = (case_id, volunteer)

    waiting = dash.pending(graph, case_id)
    if waiting:
        resolve_form(graph, case_id, waiting, volunteer)

    notes = dash.volunteer_notes(graph, case_id)
    if notes:
        st.subheader("Notes for the volunteer")
        for n in notes:
            words = f'<br>Taxpayer said: "{html.escape(n["taxpayer_words"])}"' if n.get("taxpayer_words") else ""
            done = " (answered later)" if n.get("resolved") else ""
            st.markdown(f'<div class="note"><b>{html.escape(n.get("question_text") or n.get("question", ""))}</b>'
                        f'<br>{html.escape(n.get("reason", ""))}{done}{words}</div>', unsafe_allow_html=True)

    st.subheader("Answers so far")
    answers = dash.answers(graph, case_id)
    if answers:
        st.dataframe([{"Question": a["question"], "Answer": a["answer"]} for a in answers],
                     hide_index=True, use_container_width=True)
    else:
        st.write("No answers yet.")

    page = dash.draft_form_html(graph, case_id)
    if page:
        st.subheader("Draft tax form")
        st.download_button("Download the draft form", page, file_name=f"{case_id}_1040sr.html", mime="text/html")
        with st.expander("Show the draft form (click any amount to see where it came from)"):
            components.html(page, height=800, scrolling=True)

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
if "case_id" in st.session_state:
    case_screen(graph, st.session_state.case_id, volunteer)
else:
    list_screen(graph)
