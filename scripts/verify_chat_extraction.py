"""Check one W-2 reading end to end through the chat, with a real provider.

  python -m scripts.verify_chat_extraction --provider anthropic      # key from ANTHROPIC_API_KEY in .env
  python -m scripts.verify_chat_extraction --provider openai         # key from OPENAI_API_KEY in .env
  python -m scripts.verify_chat_extraction --provider anthropic --image data/fixtures/w2_02.jpg

What it does, in a temporary folder (nothing in runtime/ or traces/ is touched):
  1. starts a chat case on the real graph with the real Intake, using JiWon's shared service (src/p3/shared_service.py);
  2. answers the interview as a single filer (born 1950) who has one W-2;
  3. uploads the fictional W-2 image when the interview has recorded "yes" to the W-2 question;
  4. keeps answering to the end: the model reads the image when the interview ends (one paid call, a few seconds);
  5. checks that the case waits for a volunteer (EXTRACTION_REVIEW) and compares the boxes it read with
     data/fixtures/expected.json;
  6. accepts the review as a volunteer, and checks that the draft reaches "complete" with line 1a and line 25a
     equal to boxes 1 and 2.
It prints OK or MISMATCH for each check and exits 0 only if all pass. It never prints the key.

Use fictional fixtures only: the image is sent to the selected provider and may be billed to your account.
This is the path the chat's upload box has to follow (the box itself is Supriya's; see the issue with the to-do list).
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = "SF-482-735"

# Answers for a single filer born in 1950 with one W-2 and nothing else, matched on a phrase of the question.
ANSWERS = [
    ("full name", "Pat Taxpayer"), ("were you married", "no"), ("which of these fits you best", "single"),
    ("date of birth", "March 4, 1950"), ("legally blind", "no"), ("depend on you for support", "no"),
    ("w-2", "yes"), ("ssa-1099", "no"), ("1099-r", "no"), ("1099-int", "no"), ("1099-div", "no"),
    ("other tax forms", "no"), ("sell any stocks", "no"), ("own business", "no"),
    ("outside the united states", "no"), ("digital assets", "no"), ("tax payments to the irs", "no"),
    ("adjustments to your income", "no"), ("paid into a bank account or sent as a paper check", "paper check"),
    ("claim you as a dependent", "no"), ("spouse pass away", "no"), ("live in the united states", "yes"),
    ("answering these questions yourself", "yes"), ("is that right", "yes"), ("is that correct", "yes"),
]


def answer_for(question: str) -> str:
    text = question.lower()
    return next((reply for phrase, reply in ANSWERS if phrase in text), "no")


def make_reader(provider: str):
    from dotenv import dotenv_values

    from silverfile_extraction.vision import DEFAULT_MODELS, VisionReader

    config = dotenv_values(ROOT / ".env", interpolate=False)  # the file only, like the W-2 page
    key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    model_name = "OPENAI_MODEL" if provider == "openai" else "ANTHROPIC_MODEL"
    key = (config.get(key_name) or "").strip()
    if not key:
        raise SystemExit(f"Add {key_name} to the .env file in {ROOT}, save it, and run this again.")
    return VisionReader(key, (config.get(model_name) or "").strip() or DEFAULT_MODELS[provider], provider=provider)


def run(reader, image_path, *, folder=None, log=print) -> bool:
    """Drive one case. `reader` is a VisionReader (or a test double). Returns True if every check passed."""
    from langgraph.types import Command  # noqa: F401  (resume goes through the service)

    from silverfile_extraction.checkpointer import sqlite_checkpointer
    from src.p3.shared_service import make_shared_service
    from src.ui import chat_session as chat

    image_path = Path(image_path)
    expected = json.loads((ROOT / "data" / "fixtures" / "expected.json").read_text())[image_path.name]
    folder = Path(folder or tempfile.mkdtemp(prefix="silverfile-verify-"))
    config = {"configurable": {"thread_id": CASE}}
    results = []

    def check(label, ok, detail=""):
        results.append(bool(ok))
        log(f"  {'OK      ' if ok else 'MISMATCH'} {label}{': ' + detail if detail else ''}")

    log(f"Working folder (temporary): {folder}")
    with sqlite_checkpointer(folder / "sessions.sqlite") as saver:
        service = make_shared_service(saver, runtime=folder / "runtime", reader=reader, trace_dir=folder / "traces")
        graph = service.graph
        chat.start(graph, CASE)

        uploaded = False
        for _ in range(80):
            values = graph.get_state(config).values
            if chat.screen(graph, CASE) != chat.ASKING:
                break
            facts = values.get("facts", {})
            if not uploaded and (facts.get("has_w2") or {}).get("value") == "yes":
                receipt = service.submit(CASE, image_path.read_bytes(), synthetic_confirmed=True)
                uploaded = True
                log(f"Uploaded {image_path.name}: {receipt['document_id'][:12]}... added={receipt['added']}")
            question = values.get("pending_question") or ""
            if not question:
                break
            chat.send(graph, CASE, answer_for(question))

        check("the interview recorded the W-2 answer and the upload was accepted", uploaded)
        values = graph.get_state(config).values
        check("the case waits for a volunteer to check the reading",
              chat.screen(graph, CASE) == chat.WAITING_FOR_VOLUNTEER
              and (values.get("escalation") or {}).get("condition") == "EXTRACTION_REVIEW",
              f"status={values.get('status')}, escalation={(values.get('escalation') or {}).get('condition')}")

        records = service.records(CASE)
        read = next(iter(records.values()), {}).get("fields", {})
        for box, label in (("1", "box_1"), ("2", "box_2")):
            got = (read.get(label) or {}).get("value")
            want = expected[box]
            check(f"box {box} read as {want}", got is not None and abs(float(got) - float(want)) < 0.005,
                  f"read {got}")

        service.resolve(CASE, {"action": "accept", "reviewer": "verify script",
                               "reason": "Compared with the fixture's expected values.", "confirmed_w2": True})
        values = graph.get_state(config).values
        computed = values.get("computed") or {}
        check("the draft is complete after the review", values.get("status") == "complete",
              f"status={values.get('status')}")
        for line, box in (("line_1a", "1"), ("line_25a", "2")):
            got = (computed.get(line) or {}).get("value")
            check(f"{line} equals box {box}", got is not None and abs(float(got) - float(expected[box])) < 0.005,
                  f"{got}")
        check("the traces and audit log are in the chat's trace folder",
              (folder / "traces" / f"{CASE}.jsonl").exists() and (folder / "traces" / "audit" / f"{CASE}.jsonl").exists())

    passed = all(results)
    log("\nALL CHECKS PASSED" if passed else "\nSOME CHECKS FAILED")
    return passed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", choices=["openai", "anthropic"], required=True)
    parser.add_argument("--image", default="data/fixtures/w2_01.jpg")
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    image = Path(args.image)
    print(f"Provider: {args.provider}. Image: {image} (fictional fixture; it is sent to the provider).")
    return 0 if run(make_reader(args.provider), image) else 1


if __name__ == "__main__":
    sys.exit(main())
