"""Taxpayer chat page (card INT-6). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the web page where an older taxpayer talks to Intake.
Run it with:  streamlit run src/ui/taxpayer_chat.py

What it does:
  - Start screen: "Start a new session" (shows a case ID to write down) or "Continue a
    session" (type the case ID; shows "Welcome back, so far we've covered...").
  - Shows one question at a time, once, in large text, with SilverFile's latest message
    above it (e.g. "Thank you" or a note about a removed number). No scrolling chat history,
    so nothing appears or is read out twice; earlier answers are under "Your answers so far".
  - Always the light theme (.streamlit/config.toml), whatever the computer's dark/light
    setting, with button and box colours also set here as a safety net, so it looks the
    same and stays readable everywhere, including Docker and a Mac in dark mode.
  - Large text (22px+), strong contrast, big buttons, visible labels, and plain-text
    speaker names ("SilverFile says:" / "You said:") so screen readers announce who is
    speaking. The newest question is in a live region, so it is read out when it appears.
  - Big buttons for "Go back", "I'm not sure", "Please explain" and "Talk to a volunteer".
  - Date questions get three labelled boxes: Month (a list of month names, so the
    person can scroll or type the first letters), Day and Year. Or the person types it in a
    box labelled "MM-DD-YYYY, for example: 03-04-1950" (a visible label, not grey text that
    disappears); 03-04-1950, 03/04/1950 and 03041950 all become "March 4, 1950", and Intake
    reads it back before saving.
  - Six parts, like an application form: a "Your progress" list at the top shows each part's
    status in words ("Done", "In progress", "Not started", "1 skipped", "1 noted for a
    volunteer"). Above the answer box: "Part 2 – Age and eyesight – Question 3" in words, then
    the question itself in the largest text. Questions are counted within each part.
    Numbers count only the questions this person is asked (no gaps).
  - "Skip for now": the question is set aside and asked again at the end. Skipping it a
    second time counts as "not sure", so it goes to a volunteer instead of staying blank.
  - "Your answers so far": a numbered list with a "Change answer N" button for each, so the
    person can jump from question 10 straight back to question 3 and check their answers.
  - While a volunteer is needed, shows a calm waiting message and accepts no new messages.
  - Never files anything: the last screen says the draft goes to a volunteer to review.
  - When finished, shows "Your draft tax form" (Sahana's PRV-3 page): click any amount to see
    where it came from, plus a "Download the draft form" button. It says plainly that nothing
    has been filed. If nothing is computed yet, it says the form is not ready.

  - Sessions are saved on disk (JiWon's SQLite checkpointer), so the case ID still works
    after the app restarts.

What is still missing:
  - The volunteer side (resolving a pause) lives in the Kushim dashboard, not here.

All logic is in src/ui/chat_session.py; this file only draws the page.
"""
import html
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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
    h3 { font-size: 26px !important; }  /* "Question 2.3" sits under "Part 2 of 6", so it is smaller */
    .stApp { background: #ffffff; color: #111111; }
    .bubble { padding: 14px 18px; margin: 10px 0; border-radius: 10px; line-height: 1.5; }
    .from-silverfile { background: #eef3fb; border-left: 6px solid #1f4e9a; }
    .from-you { background: #f3f3f3; border-left: 6px solid #555555; }
    .speaker { font-weight: 700; display: block; margin-bottom: 4px; }
    .case-id { font-size: 30px; font-weight: 700; letter-spacing: 2px; }
    .answer-row { padding: 10px 0 4px 0; border-top: 1px solid #cccccc; line-height: 1.5; }
    .progress li { margin: 4px 0; }
    .current-question { font-size: 30px !important; font-weight: 700; line-height: 1.4; margin: 24px 0 12px 0; }
    .current-question .part-label { display: block; font-size: 22px !important; font-weight: 600;
                                    color: #1f4e9a; margin-bottom: 6px; }
    .stButton button, .stFormSubmitButton button {
        min-height: 3.2rem; width: 100%; font-weight: 700; border: 2px solid #1f4e9a;
        background: #ffffff !important; color: #111111 !important;
    }
    .stButton button:hover, .stFormSubmitButton button:hover { background: #eef3fb !important; }
    /* Safety net if the light theme in .streamlit/config.toml is not picked up (e.g. a Mac in
       dark mode): keep every text box and list white with dark text, so it stays readable. */
    input, textarea, [data-baseweb="input"] > div, [data-baseweb="select"] > div {
        background: #ffffff !important; color: #111111 !important;
    }
    label, h1, h2, h3, p, li, .stMarkdown { color: #111111 !important; }
    .stButton button:focus, .stFormSubmitButton button:focus, input:focus {
        outline: 4px solid #f2a900 !important; outline-offset: 2px;
    }
    /* ---- Look: the same family as the start page (blue banner, white cards) ---- */
    .stApp { background: #f4f7fc; }
    .block-container { max-width: 860px; }
    .hero { box-sizing: border-box; max-width: 100%; background: linear-gradient(135deg, #1f4e9a 0%, #2f6bc4 100%); border-radius: 18px;
            padding: 26px 32px; margin-bottom: 22px; }
    .hero h1 { color: #ffffff !important; font-size: 40px !important; margin: 0; padding: 0; }
    .hero p { color: #e8efff !important; margin: 6px 0 0 0; }
    .hero .chip { display: inline-block; margin-top: 12px; background: #ffffff; color: #1f4e9a;
                  border-radius: 999px; padding: 6px 16px; font-weight: 800; letter-spacing: 2px; }
    [class*="st-key-tp-"] { box-sizing: border-box; max-width: 100%; background: #ffffff; border-radius: 16px; padding: 22px 26px;
                            border: 1px solid #e3e8f0; box-shadow: 0 2px 10px rgba(31, 78, 154, 0.07); }
    .st-key-tp-question { border-top: 8px solid #1f4e9a; }
    .st-key-tp-waiting { border-top: 8px solid #d98c00; }
    .st-key-tp-finished { border-top: 8px solid #1d6b3a; }
    /* Icons come from the icon font that ships with the app (not the computer's emoji), so
       they look the same on Windows, Mac and phones. */
    .msym { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
            letter-spacing: normal; text-transform: none; white-space: nowrap; direction: ltr;
            font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; font-size: 30px !important; }
    .card-top { display: flex; align-items: center; gap: 16px; margin: 0 0 4px 0; }
    .card-icon { flex: 0 0 56px; display: inline-flex; width: 56px; height: 56px; border-radius: 50%;
                 align-items: center; justify-content: center; background: #e3ecfa; color: #1f4e9a; }
    .card-icon.green { background: #e2f3e8; color: #1d6b3a; } .card-icon.amber { background: #fff1d6; color: #7a4d00; }
    .card-head { font-size: 28px !important; font-weight: 800; margin: 0 !important; padding: 0 !important; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    /* Progress: six steps, each with a numbered circle and its status in words */
    .steps { display: flex; gap: 6px; margin: 4px 0 4px 0; }
    .step { flex: 1 1 0; min-width: 0; overflow-wrap: anywhere; text-align: center; font-size: 15px; color: #444444; line-height: 1.25; }
    .step .num { display: flex; margin: 0 auto 6px auto; width: 40px; height: 40px; border-radius: 50%;
                 align-items: center; justify-content: center; font-weight: 800; font-size: 19px;
                 background: #e6e9ef; color: #444444; border: 3px solid #e6e9ef; }
    .step.done .num { background: #1d6b3a; border-color: #1d6b3a; color: #ffffff; }
    .step.current .num { background: #ffffff; border-color: #1f4e9a; color: #1f4e9a; }
    .step.attention .num { background: #fff1d6; border-color: #d98c00; color: #7a4d00; }
    .step.current { color: #1f4e9a; font-weight: 800; }
    .step small { display: block; font-size: 14px; color: #555555; font-weight: 400; }
    /* The send button stands out; everything else stays a white button with a blue edge */
    /* (more specific than ".stButton button" above, so it wins on every browser) */
    .stButton button[data-testid^="stBaseButton-primary"],
    .stFormSubmitButton button[data-testid^="stBaseButton-primary"] {
        background: #1f4e9a !important; border-color: #1f4e9a !important; color: #ffffff !important; }
    .stButton button[data-testid^="stBaseButton-primary"] *,
    .stFormSubmitButton button[data-testid^="stBaseButton-primary"] * { color: #ffffff !important; }
    .stButton button[data-testid^="stBaseButton-primary"]:hover,
    .stFormSubmitButton button[data-testid^="stBaseButton-primary"]:hover { background: #2a5fb3 !important; }
    .answer-row { border-top: none; background: #f7f9fc; border-radius: 10px; padding: 12px 16px; margin: 8px 0 4px 0; }
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
    """One graph for the whole app; sessions are saved on disk, so they survive a restart."""
    return chat.make_graph(chat.open_saved_sessions())


def bubble(role: str, text: str, live: bool = False) -> None:
    speaker, css = ("SilverFile says:", "from-silverfile") if role == "assistant" else ("You said:", "from-you")
    aria = ' role="status" aria-live="polite"' if live else ""
    st.markdown(
        f'<div class="bubble {css}"{aria}><span class="speaker">{speaker}</span>{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def card_top(icon: str, title: str, colour: str = "") -> None:
    """An icon circle (hidden from screen readers) beside a real heading, at the top of a card.
    `icon` is a Material Symbols name, e.g. "waving_hand"."""
    st.markdown(f'<div class="card-top"><span class="card-icon {colour}" aria-hidden="true">'
                f'<span class="msym">{icon}</span></span><h2 class="card-head">{html.escape(title)}</h2></div>',
                unsafe_allow_html=True)


def start_screen(graph) -> None:
    st.markdown('<div class="hero"><h1>SilverFile</h1>'
                "<p>Welcome. We will ask you some questions about your 2025 taxes, one at a time.</p></div>",
                unsafe_allow_html=True)
    with st.container(key="tp-new"):
        card_top("waving_hand", "New here?")
        st.write("Start a new session. You will get a case ID to come back with later.")
        if st.button("Start a new session", type="primary", icon=":material/play_arrow:"):
            case_id = chat.new_case_id()
            chat.start(graph, case_id)
            st.session_state.case_id = case_id
            st.session_state.is_new = True
            st.rerun()
    st.write("")
    with st.container(key="tp-back"):
        card_top("history", "Coming back?", "green")
        with st.form("continue"):
            typed = st.text_input("Your case ID, for example SF-482-735")
            if st.form_submit_button("Continue my session", icon=":material/login:"):
                case_id = chat.clean_case_id(typed)
                if case_id and chat.exists(graph, case_id):
                    st.session_state.case_id = case_id
                    st.session_state.is_new = False
                    st.rerun()
                st.error("Sorry, I couldn't find that case ID. Please check it and try again.")


def draft_form(graph, case_id: str) -> None:
    """The draft 1040-SR with click-to-see sources, and a copy to keep."""
    page = chat.draft_form_html(graph, case_id)
    if page is None:
        st.info("Your draft form is not ready yet. A volunteer will let you know.")
        return
    st.header("Your draft tax form", anchor=False)
    st.write("This is a draft for a volunteer to check with you. Nothing has been filed. "
             "Click any amount to see where it came from.")
    st.download_button("Download the draft form", page, file_name=f"{case_id}_1040sr.html",
                       mime="text/html", icon=":material/download:")
    components.html(page, height=900, scrolling=True)


def date_form(graph, case_id: str) -> None:
    """Three boxes with labels that stay visible: no placeholder text, no day/month mix-ups."""
    with st.form("date", clear_on_submit=True):
        st.markdown("**Month:** click the box and choose a month. You can also type the first "
                    "letters, for example \"Mar\" for March.")
        month = st.selectbox("Month", chat.MONTH_OPTIONS, index=None, placeholder="Choose a month")
        day_col, year_col = st.columns(2)
        day = day_col.number_input("Day (1 to 31)", min_value=1, max_value=31, value=None, step=1)
        year = year_col.number_input("Year, for example 1950", min_value=1900, max_value=2025,
                                     value=None, step=1)
        if st.form_submit_button("Send this date"):
            answer = chat.date_answer(month, day, year)
            problem = chat.date_problem(month, day, year)  # e.g. April 31: never sent
            if answer and not problem:
                chat.send(graph, case_id, answer)
                st.rerun()
            st.error(problem or "Please fill in the month, the day and the year.")


def progress_list(graph, case_id: str) -> None:
    """The six parts as numbered steps, each with its status in words (a screen reader hears
    "Part 2: Age and eyesight, In progress (you are here)"), like an application form."""
    steps = []
    for part in chat.overview(graph, case_id):
        status = part["status"]
        css = ("current" if part["current"] else "done" if status == "Done"
               else "" if status == "Not started" else "attention")
        mark = '<span class="msym" style="font-size:26px !important">check</span>' if css == "done" else str(part["number"])
        spoken = html.escape(f"Part {part['number']}: {part['title']}, {status}")
        spoken += " (you are here)" if part["current"] else ""
        steps.append(f'<li class="step {css}"><span class="num" aria-hidden="true">{mark}</span>'
                     f'<span aria-hidden="true">{html.escape(part["title"])}<small>{html.escape(status)}</small></span>'
                     f'<span class="sr-only">{spoken}</span></li>')
    with st.container(key="tp-progress"):
        st.subheader("Your progress", anchor=False)
        st.markdown(f'<ol class="steps" style="list-style:none;padding:0">{"".join(steps)}</ol>',
                    unsafe_allow_html=True)


QUICK = [("Go back", "go back", ":material/undo:"),
         ("Skip for now", "skip for now", ":material/skip_next:"),
         ("I'm not sure", "I'm not sure", ":material/help:"),
         ("Please explain", "I don't understand", ":material/lightbulb:"),
         ("Talk to a volunteer", "Can I talk to a real person?", ":material/support_agent:")]


def chat_screen(graph, case_id: str) -> None:
    st.markdown(f'<div class="hero"><h1>SilverFile</h1><span class="chip">Your case ID: {html.escape(case_id)}</span></div>',
                unsafe_allow_html=True)
    if st.session_state.get("is_new"):
        st.info("Please write this case ID down. You will need it to continue later.")
    else:
        st.info(chat.welcome_back(graph, case_id))
    progress_list(graph, case_id)
    st.write("")

    # Only SilverFile's latest message, without the question (it is shown once, in large text
    # below), so nothing appears twice. Earlier answers are under "Your answers so far".
    screen = chat.screen(graph, case_id)
    replies = [m["content"] for m in chat.transcript(graph, case_id) if m["role"] == "assistant"]
    latest = replies[-1] if replies else ""
    current = chat.question_label(graph, case_id) if screen == chat.ASKING else None
    if current and latest.endswith(current["text"]):
        latest = latest[: -len(current["text"])].strip()
    if screen == chat.WAITING_FOR_VOLUNTEER:
        with st.container(key="tp-waiting"):
            card_top("hourglass_top", "A volunteer is looking at this", "amber")
            if latest:
                bubble("assistant", latest, live=True)
            st.warning(WAITING_TEXT)
            if st.button("Check again", icon=":material/refresh:"):  # after the volunteer decides
                st.rerun()
        return
    if screen in (chat.FINISHED, chat.STOPPED):
        with st.container(key="tp-finished"):
            card_top("celebration" if screen == chat.FINISHED else "handshake", "Thank you", "green")
            if latest:
                bubble("assistant", latest, live=True)
            if screen == chat.FINISHED:
                st.success(FINISHED_TEXT)
                draft_form(graph, case_id)
            else:
                st.info(STOPPED_TEXT)
        return

    with st.container(key="tp-question"):
        if latest:
            bubble("assistant", latest, live=True)
        label = chat.question_label(graph, case_id)
        if label:
            # Where you are, in words ("Part 1 – Personal information – Question 3"), then the question itself,
            # which is the largest text on the page. One heading, so screen readers keep them together.
            where = f'Part {label["part"]} – {label["part_title"]} – Question {label["position"]}'
            st.markdown(
                f'<h2 class="current-question" role="status" aria-live="polite"><span class="part-label">{html.escape(where)}</span>'
                f'{html.escape(label["text"])}</h2>',
                unsafe_allow_html=True,
            )
        asking_date = chat.asking_for_a_date(graph, case_id)
        if asking_date:
            date_form(graph, case_id)
        with st.form("answer", clear_on_submit=True):
            label = "Or type the date here as MM-DD-YYYY, for example: 03-04-1950" if asking_date else "Type your answer here"
            answer = st.text_input(label)
            if st.form_submit_button("Send my answer", type="primary", icon=":material/send:") and answer.strip():
                chat.send(graph, case_id, chat.typed_date(answer) if asking_date else answer)
                st.rerun()

    st.write("")
    with st.container(key="tp-help"):
        st.subheader("Need help? Choose one of these:", anchor=False)
        columns = st.columns(2)
        for i, (label, text, icon) in enumerate(QUICK):
            if columns[i % 2].button(label, icon=icon):
                chat.send(graph, case_id, text)
                st.rerun()

    rows = chat.answers(graph, case_id)
    if rows:
        st.write("")
        with st.container(key="tp-answers"):
            st.header("Your answers so far", anchor=False)
            st.write("You can check your answers here. To change one, press its Change button.")
            for part, title in enumerate(chat.PARTS, start=1):
                part_rows = [row for row in rows if row["part"] == part]
                if not part_rows:
                    continue
                st.subheader(f"Part {part}: {title}", anchor=False)
                for row in part_rows:
                    st.markdown(
                        f'<div class="answer-row"><b>Question {row["position"]}: {html.escape(row["question"])}</b><br>'
                        f'Your answer: {html.escape(row["answer"])}</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Change Part {part}, question {row['position']}", key=f"change-{row['key']}",
                                 icon=":material/edit:"):
                        chat.change(graph, case_id, row["question"])
                        st.rerun()

    st.write("")
    if st.button("Leave and continue later", icon=":material/logout:"):
        st.session_state.clear()
        st.rerun()


graph = get_graph()
if "case_id" in st.session_state:
    chat_screen(graph, st.session_state.case_id)
else:
    start_screen(graph)
