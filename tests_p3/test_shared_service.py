"""P3 shared-case contract tests. No API key or paid model calls."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from silverfile_extraction.privacy import SafeInputError
from src.p3.shared_service import SharedExtractionService

CASE = "SF-482-735"


class FakeTools:
    def __init__(self):
        self.reader = object()
        self.calls = 0

    def upload(self, data, synthetic_confirmed):
        self.calls += 1
        if data == b"bad":
            raise SafeInputError("Unreadable image.")
        return {
            "id": "doc-" + data.decode(),
            "kind": "W-2",
            "image_ref": data.decode(),
            "synthetic_confirmed": True,
        }


class FakeGraph:
    def __init__(self, values):
        self.values = copy.deepcopy(values)
        self.next = ()
        self.interrupts = ()
        self.updates = []

    def get_state(self, config):
        return SimpleNamespace(
            values=copy.deepcopy(self.values),
            next=self.next,
            interrupts=self.interrupts,
        )

    def update_state(self, config, update):
        self.updates.append(copy.deepcopy(update))
        self.values.update(copy.deepcopy(update))


class SharedCaseTests(unittest.TestCase):
    def setUp(self):
        self.graph = FakeGraph({
            "case_id": CASE,
            "facts": {
                "taxpayer_birth_date": {
                    "value": "1951-04-02",
                    "source": "user",
                }
            },
            "messages": [
                {"role": "user", "content": "single"}
            ],
            "pending_question": "Do you have a W-2?",
            "intake_complete": False,
            "documents": [
                {"id": "older-doc", "kind": "SSA-1099"}
            ],
        })
        self.tools = FakeTools()
        self.service = SharedExtractionService(
            self.graph, self.tools
        )

    def test_preserves_answers_and_existing_documents(self):
        before = copy.deepcopy(self.graph.values)

        self.service.submit(
            CASE, b"one", synthetic_confirmed=True
        )

        for key in (
            "facts", "messages",
            "pending_question", "intake_complete",
        ):
            self.assertEqual(
                self.graph.values[key], before[key]
            )

        self.assertEqual(
            [d["id"] for d in self.graph.values["documents"]],
            ["older-doc", "doc-one"],
        )
        self.assertEqual(
            set(self.graph.updates[0]), {"documents"}
        )

    def test_multiple_documents_and_duplicate(self):
        self.service.submit(
            CASE, b"one", synthetic_confirmed=True
        )
        again = self.service.submit(
            CASE, b"one", synthetic_confirmed=True
        )
        self.service.submit(
            CASE, b"two", synthetic_confirmed=True
        )

        self.assertFalse(again["added"])
        self.assertEqual(
            len(self.graph.values["documents"]), 3
        )
        self.assertEqual(len(self.graph.updates), 2)

    def test_missing_case_is_not_created(self):
        self.graph.values = {}

        with self.assertRaises(SafeInputError):
            self.service.submit(
                CASE, b"one", synthetic_confirmed=True
            )

        self.assertEqual(self.tools.calls, 0)

    def test_demo_id_is_rejected(self):
        with self.assertRaises(SafeInputError):
            self.service.submit(
                "demo", b"one", synthetic_confirmed=True
            )

        self.assertEqual(self.tools.calls, 0)

    def test_closed_computed_or_pending_cases_are_rejected(self):
        original = copy.deepcopy(self.graph.values)

        blocked_states = (
            {"done": True},
            {"status": "complete"},
            {"status": "halted_by_human"},
            {"computed": {"line_1z": {"value": 12}}},
            {"escalation": {"pending": True}},
        )

        for update in blocked_states:
            with self.subTest(update=update):
                self.graph.values = {**original, **update}

                with self.assertRaises(SafeInputError):
                    self.service.submit(
                        CASE, b"one",
                        synthetic_confirmed=True,
                    )

        self.assertEqual(self.tools.calls, 0)

    def test_pending_task_is_not_overwritten(self):
        self.graph.next = ("extraction",)

        with self.assertRaises(SafeInputError):
            self.service.submit(
                CASE, b"one", synthetic_confirmed=True
            )

    def test_missing_reader_and_consent(self):
        with self.assertRaises(SafeInputError):
            self.service.submit(
                CASE, b"one", synthetic_confirmed=False
            )

        self.service.reader = None

        with self.assertRaises(SafeInputError):
            self.service.submit(
                CASE, b"one", synthetic_confirmed=True
            )

        self.assertEqual(self.tools.calls, 0)

    def test_bad_image_does_not_change_case(self):
        before = copy.deepcopy(self.graph.values)

        with self.assertRaises(SafeInputError):
            self.service.submit(
                CASE, b"bad", synthetic_confirmed=True
            )

        self.assertEqual(self.graph.values, before)


@unittest.skipUnless(
    importlib.util.find_spec("langgraph"),
    "LangGraph is required",
)
class PersistenceTests(unittest.TestCase):
    def test_shared_saver_survives_reopen(self):
        from langgraph.graph import StateGraph, START, END
        from silverfile_extraction.checkpointer import (
            sqlite_checkpointer,
        )
        from src.state import SilverState

        def team_state_graph(saver):
            builder = StateGraph(SilverState)
            builder.add_node("idle", lambda state: {})
            builder.add_edge(START, "idle")
            builder.add_edge("idle", END)
            return builder.compile(checkpointer=saver)

        config = {
            "configurable": {"thread_id": CASE}
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "team_checkpoints.sqlite"

            with sqlite_checkpointer(path) as saver:
                graph = team_state_graph(saver)
                graph.invoke(
                    {
                        "case_id": CASE,
                        "facts": {
                            "name": {
                                "value": "Test",
                                "source": "user",
                            }
                        },
                        "intake_complete": False,
                    },
                    config,
                )

                service = SharedExtractionService(
                    graph, FakeTools()
                )
                service.submit(
                    CASE, b"one", synthetic_confirmed=True
                )

            with sqlite_checkpointer(path) as saver:
                values = team_state_graph(
                    saver
                ).get_state(config).values

                self.assertEqual(
                    values["documents"][0]["id"], "doc-one"
                )
                self.assertEqual(
                    values["facts"]["name"]["value"], "Test"
                )
                self.assertFalse(values["intake_complete"])


class FactoryTests(unittest.TestCase):
    """make_shared_service wires the real chat graph to the chat's own trace folder."""

    def test_traces_go_where_the_chat_and_the_dashboards_read(self):
        from langgraph.checkpoint.memory import InMemorySaver

        from src.p3.shared_service import make_shared_service
        from src.ui import chat_session as chat

        with tempfile.TemporaryDirectory() as directory:
            runtime, traces = Path(directory) / "runtime", Path(directory) / "traces"
            service = make_shared_service(InMemorySaver(), runtime=runtime, trace_dir=traces)
            chat.start(service.graph, CASE)

            self.assertTrue((traces / f"{CASE}.jsonl").exists())
            self.assertFalse((runtime / "traces").exists())

    def test_the_default_trace_folder_is_the_chats(self):
        import inspect

        from src.p3.shared_service import make_shared_service

        self.assertEqual(inspect.signature(make_shared_service).parameters["trace_dir"].default, "traces")

    def test_the_graph_runs_the_real_intake(self):
        from langgraph.checkpoint.memory import InMemorySaver

        from src.p3.shared_service import make_shared_service
        from src.ui import chat_session as chat

        with tempfile.TemporaryDirectory() as directory:
            service = make_shared_service(InMemorySaver(), runtime=directory, trace_dir=Path(directory) / "t")
            chat.start(service.graph, CASE)
            # the placeholder Intake asks "STUB QUESTION: ..." and records no progress; the real one
            # opens the interview and keeps its progress in the case facts
            values = service.graph.get_state({"configurable": {"thread_id": CASE}}).values
            self.assertNotIn("STUB", values.get("pending_question") or "STUB")
            self.assertIn("intake_progress", values.get("facts", {}))


if __name__ == "__main__":
    unittest.main()