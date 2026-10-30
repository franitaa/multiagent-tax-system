"""scripts/verify_chat_extraction.py, offline: a test double stands in for the model.

The script is what we run by hand with a real provider key, so its own logic (the interview, the upload at
the right moment, the volunteer review, the comparisons) is tested here with no network and no key.
"""
from p3_helpers import FakeReader, good_result

from scripts.verify_chat_extraction import answer_for, run
from silverfile_extraction.vision import VisionField, VisionResult

IMAGE = "data/fixtures/w2_01.jpg"  # expected: box 1 = 30,000.00, box 2 = 2,000.00


def quiet(lines):
    return lines.append


def test_a_correct_reading_passes_every_check(tmp_path):
    lines = []
    assert run(FakeReader(), IMAGE, folder=tmp_path, log=quiet(lines))
    text = "\n".join(lines)
    assert "MISMATCH" not in text and "ALL CHECKS PASSED" in text


def test_a_wrong_amount_is_reported_as_a_mismatch(tmp_path):
    wrong = VisionResult(document_type="W-2", tax_year=2025, ssn_status="test_only", ssn_prefixes=["901"],
                         fields=[VisionField(box="1", observed_text="31,000.00", confidence="high"),
                                 VisionField(box="2", observed_text="2,000.00", confidence="high")],
                         unreadable_boxes=[], other_boxes="blank")
    lines = []
    assert not run(FakeReader(wrong), IMAGE, folder=tmp_path, log=quiet(lines))
    text = "\n".join(lines)
    assert "MISMATCH box 1 read as 30000.00" in text and "SOME CHECKS FAILED" in text


def test_the_script_never_writes_into_the_repository_folders(tmp_path):
    from pathlib import Path

    before = {p for p in Path("runtime").rglob("*")} if Path("runtime").exists() else set()
    run(FakeReader(), IMAGE, folder=tmp_path, log=lambda _: None)
    after = {p for p in Path("runtime").rglob("*")} if Path("runtime").exists() else set()
    assert after == before


def test_the_interview_answers_follow_the_question_text():
    assert answer_for("Did you get a W-2 from an employer?") == "yes"
    assert answer_for("Did you get a form called an SSA-1099?") == "no"
    assert answer_for("What is your date of birth?") == "March 4, 1950"
    assert answer_for("Something we have never asked") == "no"
