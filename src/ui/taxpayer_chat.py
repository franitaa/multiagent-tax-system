"""Taxpayer chat page (card INT-6). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the web page where an older taxpayer talks to Intake.
Run it with:  streamlit run src/ui/taxpayer_chat.py

What it does:
  - Start screen: "Start a new session" (shows a case ID to write down) or "Continue a
    session" (type the case ID; shows "Welcome back, so far we've covered...").
  - Shows the conversation and the current question, one question at a time.
  - Large text (22px+), strong contrast, big buttons, visible labels, and plain-text
    speaker names ("SilverFile says:" / "You said:") so screen readers announce who is
    speaking. The newest question is in a live region, so it is read out when it appears.
  - Big buttons for "Go back", "I'm not sure", "Please explain" and "Talk to a volunteer".
  - Date questions get three labelled boxes: Month (a list showing "3 - March", so the
    person can scroll, or type the name or the number), Day and Year. No grey placeholder
    format like MM/DD/YYYY: labels stay visible, and day-first vs month-first cannot mix.
  - A "Question N" heading above the answer box. N counts only the questions this person
    is asked (no gaps for skipped ones) and matches the numbers in "Your answers so far".
  - "Your answers so far": a numbered list with a "Change answer N" button for each, so the
    person can jump from question 10 straight back to question 3 and check their answers.
  - While a volunteer is needed, shows a calm waiting message and accepts no new messages.
  - Never files anything: the last screen says the draft goes to a volunteer to review.

What is still missing:
  - Sessions last only while the app is running, until Shruti's checkpointer is plugged
    into chat_session.make_graph().
  - The volunteer side (resolving a pause) lives in the Kushim dashboard, not here.

All logic is in src/ui/chat_session.py; this file only draws the page.
"""
import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # so "src." imports work

from src.ui import chat_session as chat  # noqa: E402

st.set_page_config(page_title="SilverFile - Tax questions", page_icon=None, layout="centered")

# Large, high-contrast, screen-reader friendly styling.
st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, p, label, input, button { font-size: 22px !important; }
    h1 { font-size: 40px !important; }
    h2 { font-size: 30px !important; }
    .stApp { background: #ffffff; color: #111111; }
    .bubble { padding: 14px 18px; margin: 10px 0; border-radius: 10px; line-height: 1.5; }
    .from-silverfile { background: #eef3fb; border-left: 6px solid #1f4e9a; }
    .from-you { background: #f3f3f3; border-left: 6px solid #555555; }
    .speaker { font-weight: 700; display: block; margin-bottom: 4px; }
    .case-id { font-size: 30px; font-weight: 700; letter-spacing: 2px; }
    .answer-row { padding: 10px 0 4px 0; border-top: 1px solid #cccccc; line-height: 1.5; }
    .stButton button, .stFormSubmitButton button {
        min-height: 3.2rem; width: 100%; font-weight: 700; border: 2px solid #1f4e9a;
    }
    .stButton button:focus, .stFormSubmitButton button:focus, input:focus {
        outline: 4px solid #f2a900 !important; outline-offset: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

WAITING_TEXT = (
    "Thank you. A volunteer is looking at your answers now. You don't need to do anything. "
    "You can close this page and come back later with your case ID."
)
FINISHED_TEXT = (
    "Thank you, that's all for now. Your answers are saved. A volunteer will review your "
    "draft tax form with you. Nothing has been filed."
)
STOPPED_TEXT = "Thank you. A volunteer will be in touch with you about the next steps."


@st.cache_resource
def get_graph():
    """One graph for the whole app, so sessions are kept while the app is running."""
    return chat.make_graph()


def bubble(role: str, text: str, live: bool = False) -> None:
    speaker, css = ("SilverFile says:", "from-silverfile") if role == "assistant" else ("You said:", "from-you")
    aria = ' role="status" aria-live="polite"' if live else ""
    st.markdown(
        f'<div class="bubble {css}"{aria}><span class="speaker">{speaker}</span>{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def start_screen(graph) -> None:
    st.title("SilverFile")
    st.write("Welcome. We will ask you some questions about your 2025 taxes, one at a time.")
    st.header("New here?")
    if st.button("Start a new session"):
        case_id = chat.new_case_id()
        chat.start(graph, case_id)
        st.session_state.case_id = case_id
        st.session_state.is_new = True
        st.rerun()
    st.header("Coming back?")
    with st.form("continue"):
        typed = st.text_input("Your case ID, for example SF-482-735")
        if st.form_submit_button("Continue my session"):
            case_id = chat.clean_case_id(typed)
            if case_id and chat.exists(graph, case_id):
                st.session_state.case_id = case_id
                st.session_state.is_new = False
                st.rerun()
            st.error("Sorry, I couldn't find that case ID. Please check it and try again.")


def date_form(graph, case_id: str) -> None:
    """Three boxes with labels that stay visible: no placeholder text, no day/month mix-ups."""
    with st.form("date", clear_on_submit=True):
        st.markdown("**Month:** click the box and choose a month. You can also type its name or "
                    "number, for example \"March\" or \"3\".")
        month = st.selectbox("Month", chat.MONTH_OPTIONS, index=None, placeholder="Choose a month")
        day_col, year_col = st.columns(2)
        day = day_col.number_input("Day (1 to 31)", min_value=1, max_value=31, value=None, step=1)
        year = year_col.number_input("Year, for example 1950", min_value=1900, max_value=2025,
                                     value=None, step=1)
        if st.form_submit_button("Send this date"):
            answer = chat.date_answer(month, day, year)
            if answer:
                chat.send(graph, case_id, answer)
                st.rerun()
            st.error("Please fill in the month, the day and the year.")


def chat_screen(graph, case_id: str) -> None:
    st.title("SilverFile")
    st.markdown(f'Your case ID: <span class="case-id">{case_id}</span>', unsafe_allow_html=True)
    if st.session_state.get("is_new"):
        st.info("Please write this case ID down. You will need it to continue later.")
    else:
        st.info(chat.welcome_back(graph, case_id))

    messages = chat.transcript(graph, case_id)
    for i, message in enumerate(messages):
        bubble(message["role"], message["content"], live=(i == len(messages) - 1))

    screen = chat.screen(graph, case_id)
    if screen == chat.WAITING_FOR_VOLUNTEER:
        st.warning(WAITING_TEXT)
        return
    if screen == chat.FINISHED:
        st.success(FINISHED_TEXT)
        return
    if screen == chat.STOPPED:
        st.info(STOPPED_TEXT)
        return

    st.header(f"Question {chat.question_number(graph, case_id)}")
    if chat.asking_for_a_date(graph, case_id):
        date_form(graph, case_id)

    with st.form("answer", clear_on_submit=True):
        label = "Or type the date here" if chat.asking_for_a_date(graph, case_id) else "Type your answer here"
        answer = st.text_input(label)
        if st.form_submit_button("Send my answer") and answer.strip():
            chat.send(graph, case_id, answer)
            st.rerun()

    st.write("Or choose one of these:")
    quick = {"Go back": "go back", "I'm not sure": "I'm not sure",
             "Please explain": "I don't understand", "Talk to a volunteer": "Can I talk to a real person?"}
    columns = st.columns(2)
    for i, (label, text) in enumerate(quick.items()):
        if columns[i % 2].button(label):
            chat.send(graph, case_id, text)
            st.rerun()

    rows = chat.answers(graph, case_id)
    if rows:
        st.header("Your answers so far")
        st.write("You can check your answers here. To change one, press its Change button.")
        for number, row in enumerate(rows, start=1):
            st.markdown(
                f'<div class="answer-row"><b>{number}. {html.escape(row["question"])}</b><br>'
                f'Your answer: {html.escape(row["answer"])}</div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Change answer {number}", key=f"change-{row['key']}"):
                chat.change(graph, case_id, row["question"])
                st.rerun()

    if st.button("Leave and continue later"):
        st.session_state.clear()
        st.rerun()


graph = get_graph()
if "case_id" in st.session_state:
    chat_screen(graph, st.session_state.case_id)
else:
    start_screen(graph)
