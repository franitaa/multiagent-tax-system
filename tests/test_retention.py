"""Retention: deleting a case everywhere, expiring idle cases, clearing stale uploads."""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from scripts import purge_cases
from silverfile_extraction.case_memory import CaseMemory
from src.draft_form import write_draft_form
from src.graph import build_graph
from src.retention import (Layout, known_cases, purge_case, purge_expired, purge_stale_uploads)
from src.scenarios import clean_case
from tests.helpers import cfg


@pytest.fixture
def site(tmp_path):
    """Two finished cases with data in every store; case B's document image is also used by A."""
    layout = Layout(runtime=tmp_path / "runtime", trace_dirs=[tmp_path / "runtime" / "traces"],
                    output_dir=tmp_path / "output")
    layout.documents.mkdir(parents=True)
    layout.uploads.mkdir(parents=True)
    memory = CaseMemory(layout.intake_memory)
    with SqliteSaver.from_conn_string(str(layout.checkpoints)) as saver:
        graph = build_graph(saver, trace_dir=layout.trace_dirs[0])
        for case_id, images in (("case-a", ["doc_own_a.png", "doc_shared.png"]),
                                ("case-b", ["doc_own_b.png", "doc_shared.png"])):
            case = clean_case(case_id)
            case["documents"] = [{**case["documents"][0], "id": f"doc-{i}", "image_file": name}
                                 for i, name in enumerate(images)]
            result = graph.invoke(case, cfg(case_id))
            write_draft_form(result, layout.output_dir, case_id)
            memory.save_answer(case_id, "Q1", "yes", actor="taxpayer", event_id="e1",
                               next_question_id="Q2", expected_revision=0)
            for name in images:
                (layout.documents / name).write_bytes(b"fake png")
    return layout


def files(layout, case_id):
    return {
        "trace": [p for d in layout.trace_dirs for p in d.glob(f"{case_id}.jsonl")],
        "form": list(layout.output_dir.glob(f"{case_id}_1040sr.html")),
    }


def checkpoint_ids(layout):
    from src.retention import _thread_ids
    return _thread_ids(layout)


def test_purge_removes_a_case_from_every_store_and_leaves_the_others(site):
    report = purge_case("case-a", site, actor="volunteer:Pat", reason="taxpayer asked")["removed"]

    assert report["checkpoints"] > 0 and report["intake_answers"] == 2  # a case row and an answer event
    assert report["traces"] == 1 and report["draft_forms"] == 1
    assert report["document_images"] == 1  # its own image only
    assert checkpoint_ids(site) == {"case-b"}
    assert not files(site, "case-a")["trace"] and not files(site, "case-a")["form"]
    assert not (site.documents / "doc_own_a.png").exists()
    assert (site.documents / "doc_shared.png").exists() and (site.documents / "doc_own_b.png").exists()
    assert CaseMemory(site.intake_memory).load_case("case-a")["answers"] == {}
    assert CaseMemory(site.intake_memory).load_case("case-b")["answers"]
    assert files(site, "case-b")["trace"] and files(site, "case-b")["form"]


def test_the_last_case_using_a_shared_image_deletes_it(site):
    purge_case("case-a", site)
    purge_case("case-b", site)
    assert list(site.documents.iterdir()) == []


def test_purge_leaves_an_audit_entry_with_counts_and_no_personal_data(site):
    purge_case("case-a", site, actor="volunteer:Pat", reason="taxpayer asked")
    entries = site.audit.read("case-a")
    purged = entries[-1]
    assert purged["event"] == "case_purged" and purged["actor"] == "volunteer:Pat"
    assert purged["details"]["reason"] == "taxpayer asked" and purged["details"]["traces"] == 1
    assert site.audit.verify("case-a") == []


def test_dry_run_reports_but_deletes_nothing(site):
    report = purge_case("case-a", site, dry_run=True)
    assert report["dry_run"] and report["removed"]["checkpoints"] > 0 and report["removed"]["traces"] == 1
    assert checkpoint_ids(site) == {"case-a", "case-b"}
    assert files(site, "case-a")["trace"] and (site.documents / "doc_own_a.png").exists()
    assert not any(e["event"] == "case_purged" for e in site.audit.read("case-a"))


@pytest.mark.parametrize("bad", ["../case-a", "case a", "", "a" * 65, "case-a/../../x", None])
def test_a_case_id_that_could_reach_other_files_is_refused(site, bad):
    with pytest.raises(ValueError):
        purge_case(bad, site)
    assert checkpoint_ids(site) == {"case-a", "case-b"}


def test_purging_an_unknown_case_does_nothing(site):
    report = purge_case("no-such-case", site)
    assert not any(report["removed"].values())
    assert checkpoint_ids(site) == {"case-a", "case-b"}


def test_known_cases_lists_every_store(site):
    assert known_cases(site) == {"case-a", "case-b"}


def test_expired_cases_are_purged_and_recent_ones_are_not(site):
    now = datetime.now(timezone.utc)
    assert [r for r in purge_expired(site, max_age_days=30, now=now + timedelta(days=5))
            if "removed" in r] == []
    assert checkpoint_ids(site) == {"case-a", "case-b"}

    results = purge_expired(site, max_age_days=30, now=now + timedelta(days=40))
    assert sorted(r["case_id"] for r in results) == ["case-a", "case-b"]
    assert checkpoint_ids(site) == set() and known_cases(site) == set()
    assert "idle more than 30 days" in site.audit.read("case-a")[-1]["details"]["reason"]


def test_expiry_dry_run_deletes_nothing(site):
    now = datetime.now(timezone.utc) + timedelta(days=40)
    assert len(purge_expired(site, now=now, dry_run=True)) == 2
    assert checkpoint_ids(site) == {"case-a", "case-b"}


def test_stale_uploads_are_deleted_and_fresh_ones_kept(site):
    old, fresh = site.uploads / "old.png", site.uploads / "fresh.png"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    two_days_ago = time.time() - 48 * 3600
    os.utime(old, (two_days_ago, two_days_ago))

    assert purge_stale_uploads(site, dry_run=True) == 1 and old.exists()
    assert purge_stale_uploads(site) == 1
    assert not old.exists() and fresh.exists()


def test_the_command_line_purges_one_case_and_refuses_a_bad_id(site, capsys):
    base = ["--runtime", str(site.runtime), "--trace-dir", str(site.trace_dirs[0]),
            "--output-dir", str(site.output_dir)]
    assert purge_cases.main(["--case", "case-a", "--dry-run", *base]) == 0
    assert "would remove" in capsys.readouterr().out and checkpoint_ids(site) == {"case-a", "case-b"}

    assert purge_cases.main(["--case", "case-a", "--reason", "test", *base]) == 0
    assert "removed" in capsys.readouterr().out and checkpoint_ids(site) == {"case-b"}

    assert purge_cases.main(["--case", "../x", *base]) == 2


def add_case_with_upload(layout, case_id, handle):
    """A case whose saved state points at an upload (image_ref), as a P3 document does."""
    upload = layout.uploads / f"{handle}.png"
    upload.write_bytes(b"png")
    with SqliteSaver.from_conn_string(str(layout.checkpoints)) as saver:
        graph = build_graph(saver, trace_dir=layout.trace_dirs[0])
        case = clean_case(case_id)
        case["documents"] = [{**case["documents"][0], "id": f"doc_{handle}", "image_ref": handle}]
        graph.invoke(case, cfg(case_id))
    return upload


def test_purge_removes_the_upload_the_case_was_read_from(site):
    upload = add_case_with_upload(site, "case-c", "a" * 64)

    assert purge_case("case-c", site)["removed"]["uploads"] == 1
    assert not upload.exists()


def test_an_upload_a_live_case_still_points_at_survives_the_stale_sweep(site):
    upload = add_case_with_upload(site, "case-c", "b" * 64)
    two_days_ago = time.time() - 48 * 3600
    os.utime(upload, (two_days_ago, two_days_ago))

    assert purge_stale_uploads(site) == 0 and upload.exists()
    assert purge_case("case-b", site)["removed"]["uploads"] == 0 and upload.exists()


def test_a_path_like_image_ref_removes_nothing_and_does_not_fail_the_purge(site):
    victim = site.runtime / "victim.png"  # what "../victim" points at from runtime/uploads
    victim.write_bytes(b"not an upload")
    with SqliteSaver.from_conn_string(str(site.checkpoints)) as saver:
        graph = build_graph(saver, trace_dir=site.trace_dirs[0])
        case = clean_case("case-d")
        case["documents"] = [{**case["documents"][0], "id": "doc-d", "image_ref": "../victim"}]
        graph.invoke(case, cfg("case-d"))

    assert purge_case("case-d", site)["removed"]["uploads"] == 0
    assert victim.exists()
