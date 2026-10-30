"""SilverFile start page: one command opens both the taxpayer chat and the volunteer dashboard.
Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the single place to start the app, for graders and for the demo.
Run it with:  streamlit run src/ui/silverfile_home.py      (then open http://localhost:8501)

What it does:
  - A start page with two choices: "I'm a taxpayer" (the chat, src/ui/taxpayer_chat.py) and
    "I'm a Kushim volunteer" (the dashboard, src/ui/volunteer_dashboard.py).
  - Both pages run in ONE app, so they always share the same saved-sessions file and audit
    log. This matters in Docker: two separate containers would each have their own files,
    and the dashboard would not see the chat's cases.
  - The page menu is hidden, so a taxpayer is not shown a link to the volunteer pages.

What is still missing:
  - No login: anyone who opens the start page can choose "volunteer" (classroom demo).
  - Each page still runs on its own too (streamlit run src/ui/taxpayer_chat.py, etc.).
"""
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent


STYLE = """
<style>
.msym { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1;
        letter-spacing: normal; text-transform: none; white-space: nowrap; direction: ltr;
        font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased; }
.stApp { background: #f4f7fc; color: #111111; }
html, body, [class*="css"], .stMarkdown, p, li { font-size: 21px !important; }
.block-container { max-width: 1100px; padding-top: 4.5rem; }
.hero { box-sizing: border-box; max-width: 100%; background: linear-gradient(135deg, #1f4e9a 0%, #2f6bc4 100%); color: #ffffff;
        border-radius: 18px; padding: 36px 40px; margin-bottom: 28px; }
.hero h1 { color: #ffffff !important; font-size: 46px !important; margin: 0 0 8px 0; padding: 0; }
.hero p { color: #e8efff !important; font-size: 23px !important; margin: 0; }
.st-key-card-taxpayer, .st-key-card-volunteer {
    box-sizing: border-box; max-width: 100%; background: #ffffff; border-radius: 16px; padding: 28px 30px 24px 30px;
    box-shadow: 0 2px 10px rgba(31, 78, 154, 0.12); border-top: 8px solid #1f4e9a; }
.st-key-card-volunteer { border-top-color: #1d6b3a; }
.icon { display: inline-flex; align-items: center; justify-content: center; width: 64px; height: 64px;
        border-radius: 50%; margin-bottom: 10px; }
.icon .msym { font-size: 36px; }
.icon.blue { background: #e3ecfa; color: #1f4e9a; } .icon.green { background: #e2f3e8; color: #1d6b3a; }
.card-title { font-size: 30px !important; font-weight: 800; color: #111111; margin: 4px 0 6px 0; }
.card-who { color: #444444 !important; margin-bottom: 10px; }
.card ul { padding-left: 1.2em; margin: 0 0 18px 0; } .card li { margin: 6px 0; color: #222222; }
[data-testid="stPageLink"] a { display: flex; justify-content: center; border-radius: 10px;
    padding: 14px 18px; background: #1f4e9a; font-weight: 800; text-decoration: none; }
[data-testid="stPageLink"] a p, [data-testid="stPageLink"] a span { color: #ffffff !important; font-size: 21px !important; }
.st-key-card-volunteer [data-testid="stPageLink"] a { background: #1d6b3a; }
[data-testid="stPageLink"] a:hover { filter: brightness(1.12); }
[data-testid="stPageLink"] a:focus { outline: 4px solid #f2a900; outline-offset: 3px; }
.promises-panel { background: #ffffff; border-radius: 16px; padding: 26px 30px; margin-top: 30px;
                  box-shadow: 0 2px 10px rgba(31, 78, 154, 0.08); }
.promises-panel h2 { font-size: 26px !important; color: #111111 !important; margin: 0 0 18px 0; padding: 0; }
.promises { display: flex; gap: 18px; flex-wrap: wrap; align-items: stretch; }
.promise { flex: 1 1 260px; display: flex; gap: 14px; align-items: flex-start;
           background: #fffaf0; border: 1px solid #f3dfb0; border-radius: 12px; padding: 18px 18px; }
.promise .badge { flex: 0 0 48px; height: 48px; border-radius: 50%; background: #f2a900; color: #111111;
                  display: flex; align-items: center; justify-content: center; font-weight: 800; }
.promise .badge .msym { font-size: 26px; }
.promise h3 { font-size: 22px !important; color: #111111 !important; margin: 2px 0 4px 0; padding: 0; }
.promise p { font-size: 19px !important; color: #333333 !important; margin: 0; line-height: 1.45; }
</style>
"""


def card(key: str, icon: str, colour: str, title: str, who: str, points: list[str], page, label: str) -> None:
    with st.container(key=key):
        items = "".join(f"<li>{p}</li>" for p in points)
        st.markdown(f'<div class="card"><span class="icon {colour}" aria-hidden="true"><span class="msym">{icon}</span></span>'
                    f'<h2 class="card-title">{title}</h2><div class="card-who">{who}</div>'
                    f"<ul>{items}</ul></div>", unsafe_allow_html=True)
        st.page_link(page, label=label)


def start_page() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>SilverFile</h1>'
                "<p>Help with a draft of your 2025 tax form, one question at a time.</p></div>",
                unsafe_allow_html=True)
    taxpayer, volunteer = st.columns(2, gap="large")
    with taxpayer:
        card("card-taxpayer", "receipt_long", "blue", "I'm a taxpayer", "For the person whose taxes these are.",
             ["Simple questions, one at a time", "Say “I'm not sure” whenever you need to",
              "Stop any time and come back with your case ID"],
             TAXPAYER, "Start or continue my questions")
    with volunteer:
        card("card-volunteer", "volunteer_activism", "green", "I'm a Kushim volunteer", "For Kushim staff and volunteers.",
             ["See every case and where it stands", "Help when a taxpayer needs a person",
              "Check each draft form and where its numbers came from"],
             VOLUNTEER, "Open the volunteer dashboard")
    promises = [
        ("description", "Nothing is filed", "You get a draft. A volunteer checks it with you before anything else happens."),
        ("forum", "No tax advice", "Questions about what you should do are noted for a volunteer to answer."),
        ("lock", "Your answers are kept", "Stop any time. Come back any day with your case ID and carry on."),
    ]
    items = "".join(f'<div class="promise"><span class="badge" aria-hidden="true"><span class="msym">{icon}</span></span>'
                    f"<div><h3>{title}</h3><p>{text}</p></div></div>" for icon, title, text in promises)
    st.markdown(f'<section class="promises-panel"><h2>Our promises to you</h2>'
                f'<div class="promises">{items}</div></section>', unsafe_allow_html=True)


START = st.Page(start_page, title="SilverFile", default=True)
TAXPAYER = st.Page(str(HERE / "taxpayer_chat.py"), title="SilverFile - Tax questions", url_path="taxpayer")
VOLUNTEER = st.Page(str(HERE / "volunteer_dashboard.py"), title="Kushim - Volunteer dashboard",
                    url_path="volunteer")

st.navigation([START, TAXPAYER, VOLUNTEER], position="hidden").run()
