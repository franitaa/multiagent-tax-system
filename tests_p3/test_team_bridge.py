"""Real image bytes, explicitly mocked API reader, no network calls."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from p3_helpers import FakeReader
from silverfile_extraction.models import HumanDecision
from silverfile_extraction.privacy import SafeInputError
from src.p3.bridge import P3Tools, extract_text_fixture, verify_w2
from src.state import merge_extracted
from src.agents.extraction import run
from src.orchestration.access import ToolBox
from src.scenarios import document

ROOT = Path(__file__).resolve().parents[1]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = P3Tools(self.temp.name, FakeReader())
        self.data = (ROOT / 'data/fixtures/w2_01.jpg').read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def extract(self):
        ref = self.runtime.upload(self.data, True)
        update = run({'documents': [ref]}, ToolBox('extraction', self.runtime.registry()))
        return ref, update['extracted'][ref['id']], update

    def test_image_extraction_uses_team_contract_and_gate(self):
        ref, record, update = self.extract()
        self.assertEqual(update['escalation']['condition'], 'EXTRACTION_REVIEW')
        self.assertEqual(update['escalation']['document_id'], ref['id'])
        field = record['fields']['box_1']
        self.assertEqual(set(field), {'value', 'formula', 'inputs', 'source', 'tool'})
        self.assertEqual(field['value'], 30000.0)  # numeric in the team handoff (Computation needs numbers)
        for key in ['source', 'formula', 'tool']:
            self.assertIsInstance(field[key], str)
        self.assertEqual(record['status'], 'needs_review')

    def test_revision_merge_preserves_approval_and_history(self):
        ref, record, _ = self.extract()
        updated = verify_w2(record, HumanDecision(action='accept', reviewer='test', reason='Checked',
                            confirmed_w2=True, corrections={'1': '29000.00'}).model_dump())
        self.assertEqual(updated['fields']['box_1']['value'], 29000.0)
        self.assertEqual(updated['record']['review_history'][0]['previous_fields']['1']['value'], '30000.00')
        old, new = {ref['id']: record}, {ref['id']: updated}
        self.assertEqual(merge_extracted(old, new), new)
        self.assertEqual(merge_extracted(new, old), new)

    def test_same_revision_conflict_is_rejected(self):
        ref, record, _ = self.extract()
        with self.assertRaises(ValueError):
            merge_extracted({ref['id']: record}, {ref['id']: {**record, 'status': 'ready_for_rules'}})

    def test_no_approval_without_visual_confirmation(self):
        _, record, _ = self.extract()
        with self.assertRaises(SafeInputError):
            verify_w2(record, {'action': 'accept', 'reviewer': 'test', 'reason': 'Checked'})

    def test_evidence_hash_matches_saved_png(self):
        _, record, _ = self.extract()
        path = Path(self.temp.name) / 'documents' / record['document']['image_file']
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['document']['sha256'])

    def test_path_traversal_and_modified_upload_rejected(self):
        ref = self.runtime.upload(self.data, True)
        with self.assertRaises(SafeInputError):
            self.runtime.extract({**ref, 'image_ref': '../secret'})
        (Path(self.temp.name) / 'uploads' / (ref['image_ref'] + '.png')).write_bytes(b'changed')
        with self.assertRaises(SafeInputError):
            self.runtime.extract(ref)

    def test_consent_precedes_persistence(self):
        with self.assertRaises(SafeInputError):
            self.runtime.upload(self.data, False)
        self.assertFalse((Path(self.temp.name) / 'uploads').exists())

    def test_tool_usage_recorded_without_credentials(self):
        ref = self.runtime.upload(self.data, True)
        tools = ToolBox('extraction', self.runtime.registry())
        update = run({'documents': [ref]}, tools)
        self.assertEqual(tools.usage[0]['api_input_tokens'], 100)
        self.assertNotIn(self.runtime.reader.secret, json.dumps(update))

    def test_text_requires_explicit_amounts_and_fixture_marker(self):
        result = extract_text_fixture(document())
        self.assertEqual(result['fields']['box_1']['value'], '1000.00')
        with self.assertRaises(SafeInputError):
            extract_text_fixture({'id': 'x', 'kind': 'W-2', 'text': 'TEST DATA'})

    def test_non_w2_does_not_call_model(self):
        update = run({'documents': [{'id': 'x', 'kind': '1099-R'}]}, ToolBox('extraction', self.runtime.registry()))
        self.assertEqual(update['escalation']['condition'], 'OUT_OF_SCOPE')
        self.assertEqual(len(self.runtime.reader.calls), 0)

    def test_previous_review_does_not_approve_new_document(self):
        ref = self.runtime.upload(self.data, True)
        update = run({'documents': [ref], 'human_decisions': [{'condition': 'EXTRACTION_REVIEW',
                     'decision': 'continue'}]}, ToolBox('extraction', self.runtime.registry()))
        self.assertEqual(update['escalation']['document_id'], ref['id'])

    def test_unscoped_baseline_replays_history(self):
        ref, record, _ = self.extract()
        run({'documents': [ref], 'extracted': {'previous': record}}, ToolBox('extraction', self.runtime.registry()))
        self.assertIn('HISTORICAL_TRANSCRIPTIONS', self.runtime.reader.calls[-1][1])


@unittest.skipUnless(importlib.util.find_spec('langgraph') is not None, 'LangGraph dependencies required')
class TeamGraphTests(unittest.TestCase):
    def test_restart_resume_updates_team_state(self):
        from src.p3.service import ExtractionService
        with tempfile.TemporaryDirectory() as folder:
            with ExtractionService(folder, FakeReader()) as service:
                result = service.submit('case', (ROOT / 'data/fixtures/w2_01.jpg').read_bytes(), synthetic_confirmed=True)
                self.assertTrue(result['pending'])
                values = service.graph.get_state({'configurable': {'thread_id': 'case'}}).values
                # Reducer-backed channels may exist as empty dictionaries before any calculation.
                # Require no calculated amounts AND no dispatch to computation before approval.
                self.assertEqual(values.get('computed', {}), {})
                self.assertEqual(values['status'], 'awaiting_human')
                self.assertEqual(values['escalation']['condition'], 'EXTRACTION_REVIEW')
                self.assertNotIn('computation', [entry['to'] for entry in values['handoff_log']])
            with ExtractionService(folder) as service:
                result = service.resolve('case', HumanDecision(action='accept', reviewer='test', reason='Checked',
                                         confirmed_w2=True, corrections={'1': '29000.00'}))
                self.assertFalse(result['pending'])
                self.assertEqual(result['summary']['ready_for_rules'], 1)
                values = service.graph.get_state({'configurable': {'thread_id': 'case'}}).values
                self.assertEqual(next(iter(values['extracted'].values()))['fields']['box_1']['value'], 29000.0)

    def test_parallel_documents_need_separate_approvals(self):
        from langgraph.types import Command
        from src.graph import build_graph
        with tempfile.TemporaryDirectory() as folder:
            tools = P3Tools(folder, FakeReader())
            docs = [tools.upload((ROOT / f'data/fixtures/w2_0{i}.jpg').read_bytes(), True) for i in [1, 2]]
            graph = build_graph(trace_dir=Path(folder) / 'traces', tool_registry=tools.registry())
            config = {'configurable': {'thread_id': 'parallel'}}
            result = graph.invoke({'documents': docs, 'intake_complete': True,
                'facts': {'age': {'value': 70}, 'filing_status_claim': {'value': 'single'}}}, config)
            first_id = result['__interrupt__'][0].value['document_id']
            for index in range(2):
                payload = result['__interrupt__'][0].value
                result = graph.invoke(Command(resume={'decision': 'continue', 'note': 'Verified source',
                    'resolution': {'document_id': payload['document_id'], 'review': {'action': 'accept',
                        'reviewer': 'test', 'reason': 'Verified source', 'confirmed_w2': True}}}), config)
                if index == 0:
                    self.assertNotEqual(result['__interrupt__'][0].value['document_id'], first_id)
            self.assertTrue(all(r['status'] == 'ready_for_rules' for r in result['extracted'].values()))
            self.assertEqual(len(result['human_decisions']), 2)

class ResumeTests(unittest.TestCase):
    def test_read_only_summary_omits_sensitive_fact_values(self):
        from types import SimpleNamespace
        from src.memory import load_resume_context
        class Graph:
            def get_state(self, config):
                assert config['configurable']['thread_id'] == 'CASE-1'
                return SimpleNamespace(values={'facts': {'taxpayer_dob': {'value': '1950-01-01'},
                    'filing_status_claim': {'value': 'single'}}, 'pending_question': 'Next question',
                    'status': 'awaiting_user'})
        context = load_resume_context(Graph(), 'CASE-1')
        self.assertNotIn('1950-01-01', context['summary'])
        self.assertEqual(context['pending_question'], 'Next question')
        self.assertFalse(context['awaiting_human'])

    def test_waiting_summary_does_not_expose_escalation_reason(self):
        from types import SimpleNamespace
        from src.memory import load_resume_context
        class Graph:
            def get_state(self, config):
                return SimpleNamespace(values={'escalation': {'pending': True, 'reason': 'sensitive detail'}})
        context = load_resume_context(Graph(), 'CASE-2')
        self.assertTrue(context['awaiting_human'])
        self.assertNotIn('sensitive detail', context['summary'])


@unittest.skipUnless(importlib.util.find_spec('streamlit') is not None, 'Streamlit dependency required')
class UIStartupTests(unittest.TestCase):
    def test_page_loads_without_key_or_network_call(self):
        import os
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SILVERFILE_RUNTIME': folder}):
            app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
