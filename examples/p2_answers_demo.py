"""MEM-2/3: demonstrate an answer surviving a separately launched process."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from silverfile_extraction.case_memory import CaseMemory

parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=["save", "resume"])
parser.add_argument("--db", default="runtime/answers-demo.sqlite")
args = parser.parse_args()
memory = CaseMemory(args.db)
if args.phase == "save":
    memory.save_answer("CASE-DEMO", "Q1", "yes", actor="demo-taxpayer", event_id="demo-q1-answer",
                       next_question_id="Q2", expected_revision=0)
print(json.dumps(memory.get_resume_context("CASE-DEMO"), indent=2))

