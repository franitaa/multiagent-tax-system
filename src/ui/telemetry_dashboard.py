"""Telemetry dashboard. Owner: Francesca Rondinella (orchestration). Bonus work.

SUMMARY FOR THE TEAM
In one line: a read-only page that shows whether the system is behaving, from the traces and the audit log.

What it shows (spec: docs/telemetry-dashboard-spec.md):
  - Overview: cases by outcome, how many needed a volunteer, alerts, broken audit chains.
  - Cases: one row per case, and the step-by-step timeline of the one you pick.
  - Agents: calls, time and tokens per agent (estimated and provider-reported kept apart).
  - Escalations: per condition, how each ended and how long a volunteer took.
  - Review loop: send-backs from Review to Computation, and runs that hit the bound.
  - Safety checks: things that should never happen (an agent writing outside its allow-list, a tax tool
    run in the agent's own process, a flagged document, a clean halt on an error). Empty is good.
  - Audit integrity: the tamper check for every audited case.

What it never does: write a file, call a tool or a model, or show an answer, an amount or document text.
Traces hold field names and the audit log holds events and actors, so there is nothing else to show.
Staff only, by address, no login (classroom demo): anyone who has the address can open it, including a taxpayer.
It is not linked from the taxpayer page. It shows names, counts and times only, never answers or amounts.

Run it with the rest of the app (one container, so it sees the traces the chat writes):
  streamlit run src/ui/silverfile_home.py       then open http://localhost:8501/telemetry
or on its own:  streamlit run src/ui/telemetry_dashboard.py --server.port 8503
The folder is SILVERFILE_TRACE_DIR (default "traces"). It is fixed: a visitor cannot point the page at another
folder. To let the sidebar change it (for local debugging), set SILVERFILE_TELEMETRY_ANY_FOLDER=1.
"Refresh" re-reads it.

All logic is in src/telemetry.py; this file only draws the page.
"""
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # so "src." imports work

from src import telemetry as T  # noqa: E402

st.set_page_config(page_title="SilverFile - Telemetry", page_icon=None, layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, p, label, input, button { font-size: 20px !important; }
    h1 { font-size: 38px !important; } h2 { font-size: 28px !important; } h3 { font-size: 24px !important; }
    .stApp { background: #ffffff; color: #111111; }
    label, h1, h2, h3, p, li, .stMarkdown { color: #111111 !important; }
    .stButton button { min-height: 3rem; font-weight: 700; border: 2px solid #1f4e9a;
                       background: #ffffff !important; color: #111111 !important; }
    .stButton button:focus, input:focus { outline: 4px solid #f2a900 !important; outline-offset: 2px; }
    input, textarea { background: #ffffff !important; color: #111111 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

OUTCOME_WORDS = {
    T.COMPLETE: "Draft ready",
    T.STOPPED: "Stopped by a volunteer",
    T.HALTED: "ALERT: stopped by an error",
    T.WAITING: "Waiting for a volunteer",
    T.OPEN: "In progress",
}
ALERT_WORDS = {
    "access_violation": "ALERT: an agent wrote outside its allow-list",
    "local_tax_tool": "ALERT: a tax tool ran in the agent's own process (not over MCP)",
    "document_flagged": "ALERT: a document may hold hidden instructions",
    "halted_by_error": "ALERT: the case stopped on an error",
}


def seconds_text(value):
    return "" if value is None else f"{value:g} s"


def table(rows, empty="Nothing to show yet."):
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.write(empty)


with st.sidebar:
    st.header("Where to look")
    folder = os.environ.get("SILVERFILE_TRACE_DIR", "traces")
    if os.environ.get("SILVERFILE_TELEMETRY_ANY_FOLDER") == "1":  # local debugging only
        folder = st.text_input("Trace folder", value=folder)
    else:
        st.caption(f"Reading the trace folder: {folder}")
    st.button("Refresh")  # any click re-runs the page, which reads the files again
    st.caption("Read-only. This page shows names, counts and times. It never shows answers, amounts or "
               "document text, and it writes nothing.")

st.title("SilverFile telemetry")

snapshot = T.Snapshot(folder)
overview = T.overview(snapshot)
alerts = T.safety(snapshot)
chains = T.integrity(snapshot)
broken = [c for c in chains if not c["intact"]]

# What needs attention comes first.
if broken or alerts or overview["unreadable_lines"]:
    problems = []
    if broken:
        problems.append(f"ALERT: {len(broken)} audit log(s) fail the tamper check: "
                        + ", ".join(c["case_id"] for c in broken))
    if alerts:
        problems.append(f"ALERT: {len(alerts)} safety check(s) fired (see Safety checks below)")
    if overview["unreadable_lines"]:
        problems.append(f"{overview['unreadable_lines']} line(s) in the files could not be read and were skipped")
    st.error("  \n".join(problems))
else:
    st.success("No alerts. Every audit log passes the tamper check.")

st.header("Overview")
share = overview["share_needing_a_volunteer"]
columns = st.columns(4)
columns[0].metric("Cases", overview["cases"])
columns[1].metric("Needed a volunteer", "–" if share is None else f"{share:.0%}")
columns[2].metric("Safety alerts", overview["alerts"])
columns[3].metric("Broken audit logs", overview["broken_chains"])
table([{"Outcome": OUTCOME_WORDS.get(name, name), "Cases": count}
       for name, count in sorted(overview["by_outcome"].items())], "No cases found in this folder.")

st.header("Cases")
case_rows = T.runs(snapshot)
table([{"Case": r["case_id"], "Outcome": OUTCOME_WORDS.get(r["outcome"], r["outcome"]),
        "Agent calls": r["agent_calls"], "Time": seconds_text(r["seconds"]),
        "Input tokens": r["input_tokens"], "Output tokens": r["output_tokens"],
        "Token source": ", ".join(r["token_sources"]),
        "Escalations": ", ".join(str(c) for c in r["escalations"]),
        "Review send-backs": r["review_rounds"], "Alerts": r["alerts"]} for r in case_rows],
      "No cases found in this folder.")
st.caption("A blank token count means that case reported none. Token source \"estimate\" is a size estimate; "
           "any other value is the count the provider reported.")

with_trace = [r["case_id"] for r in case_rows if r["calls"]]
if with_trace:
    st.subheader("Timeline of one case")
    picked = st.selectbox("Case", with_trace)
    table([{"Step": t["step"], "Agent": t["agent"], "Time (ms)": t["duration_ms"],
            "Hands to": t["to"], "Why": t["reason"], "Tools": ", ".join(t["tools"]),
            "Tool transport": ", ".join(t["transports"]),
            "Paused for a volunteer": "yes" if t["paused_for_volunteer"] else "",
            "Problems": "; ".join(t["violations"] + ([f"error: {t['error']}"] if t["error"] else []))}
           for t in T.timeline(snapshot, picked)])

st.header("Agents")
table([{"Agent": a["agent"], "Calls": a["calls"], "Average (ms)": a["avg_ms"], "Slowest (ms)": a["max_ms"],
        "Input tokens (estimated)": a["input_estimated"], "Input tokens (reported)": a["input_reported"],
        "Output tokens (estimated)": a["output_estimated"], "Output tokens (reported)": a["output_reported"]}
       for a in T.agents(snapshot)])

st.header("Escalations")
table([{"Condition": e["condition"], "Raised": e["raised"], "Volunteer continued": e["continued"],
        "Volunteer stopped": e["stopped"], "Average wait": seconds_text(e["avg_wait_seconds"])}
       for e in T.escalations(snapshot)], "No escalations yet.")

st.header("Review loop")
loop = T.review_loop(snapshot)
st.write(f"Cases where Review sent the draft back to Computation: {loop['runs_with_send_back']}. "
         f"Cases that reached the limit and went to a volunteer: {loop['bound_exceeded']}.")
table([{"Case": case, "Send-backs": n} for case, n in sorted(loop["rounds"].items())], "No send-backs.")

st.header("Safety checks")
if alerts:
    table([{"Case": a["thread_id"], "Step": a["step"], "Agent": a["agent"],
            "What happened": ALERT_WORDS.get(a["kind"], a["kind"]), "Detail": a["detail"]} for a in alerts])
else:
    st.write("None fired. These are things that should never happen: an agent writing outside its "
             "allow-list, a tax tool running outside the tool server, a flagged document, or a stop on an error.")

st.header("Audit integrity")
table([{"Case": c["case_id"], "Entries": c["entries"], "Last event": c["last_event"],
        "Tamper check": "passes" if c["intact"] else "ALERT: fails — " + "; ".join(c["problems"])}
       for c in chains], "No audit logs found in this folder.")
