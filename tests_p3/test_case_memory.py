"""P3/P2 contract tests. No model or LangGraph dependency is needed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from silverfile_extraction.case_memory import CaseMemory, StaleRevisionError
from silverfile_extraction.checkpointer import case_config
from silverfile_extraction.privacy import SafeInputError


class CaseMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'answers.sqlite'
        self.store = CaseMemory(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value='yes', **kwargs):
        args = dict(actor='test-taxpayer', event_id='event-1', next_question_id='Q2', expected_revision=0)
        args.update(kwargs)
        return self.store.save_answer('case-1', 'Q1', value, **args)

    def test_case_id_is_thread_id(self):
        self.assertEqual(case_config('CASE_001')['configurable']['thread_id'], 'CASE_001')
        with self.assertRaises(SafeInputError):
            case_config('../bad')

    def test_reopen_preserves_answer_and_cursor(self):
        self.save()
        state = CaseMemory(self.path).load_case('case-1')
        self.assertEqual(state['answers']['Q1']['value'], 'yes')
        self.assertEqual(state['next_question_id'], 'Q2')

    def test_new_python_process_reads_saved_answer(self):
        self.save()
        script = ('import sys,json; from silverfile_extraction.case_memory import CaseMemory; '
                  'print(json.dumps(CaseMemory(sys.argv[1]).get_resume_context("case-1")))')
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        result = subprocess.run([sys.executable, '-c', script, str(self.path)],
                                env=env, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)['next_question_id'], 'Q2')

    def test_retry_is_idempotent(self):
        self.save()
        self.save()
        self.assertEqual(len(self.store.load_case('case-1')['answer_history']), 1)

    def test_duplicate_event_id_with_changed_value_rejected(self):
        self.save()
        with self.assertRaises(SafeInputError):
            self.save('no')

    def test_reanswer_keeps_original_and_go_back_keeps_answers(self):
        self.save()
        self.save('no', event_id='event-2', expected_revision=1, next_question_id='Q3')
        state = self.store.set_progress('case-1', next_question_id='Q1', expected_revision=2)
        self.assertEqual(state['answers']['Q1']['value'], 'no')
        self.assertEqual(state['answer_history'][1]['previous']['value'], 'yes')
        self.assertEqual(len(state['answer_history']), 2)

    def test_stale_writer_is_rejected(self):
        self.save()
        with self.assertRaises(StaleRevisionError):
            self.save('no', event_id='event-2')
        self.assertEqual(self.store.load_case('case-1')['revision'], 1)

    def test_concurrent_tabs_do_not_overwrite(self):
        def write(event):
            try:
                self.save(event_id=event)
                return 'saved'
            except StaleRevisionError:
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['a', 'b']))
        self.assertCountEqual(results, ['saved', 'stale'])
        self.assertEqual(len(self.store.load_case('case-1')['answer_history']), 1)

    def test_cases_are_isolated(self):
        self.save()
        self.assertEqual(self.store.load_case('other')['answers'], {})

    def test_resume_summary_is_plain_language_without_sensitive_values(self):
        self.store.save_answer('case-1', 'Q4', '1955-03-10', actor='test', event_id='dob',
                               next_question_id='Q5', expected_revision=0)
        summary = self.store.get_resume_context('case-1')['summary']
        self.assertIn('birth dates and sight', summary)
        self.assertNotIn('1955', summary)

    def test_repeated_dependents_have_distinct_keys(self):
        for i in range(2):
            self.store.save_answer('case-1', f'Q9:dep{i}', f'Sample {i}', actor='test', event_id=f'dep{i}',
                                   next_question_id=f'Q10:dep{i}', expected_revision=i)
        self.assertEqual(len(self.store.load_case('case-1')['answers']), 2)

    def test_money_gets_p5_provenance(self):
        state = self.store.save_answer('case-1', 'Q19', '2,000.00', actor='test', event_id='money',
                                       next_question_id='Q20', expected_revision=0, monetary=True)
        proof = state['answers']['Q19']['provenance']
        self.assertEqual(set(proof), {'value', 'formula', 'inputs', 'source', 'tool'})
        self.assertEqual(proof['value'], '2000.00')
        self.assertEqual(proof['source']['event_id'], 'money')

    def test_payment_without_provenance_is_rejected(self):
        with self.assertRaises(SafeInputError):
            self.store.save_answer('case-1', 'Q19', '2,000.00', actor='test', event_id='money',
                                   next_question_id='Q20', expected_revision=0)

    def test_real_looking_and_unsolicited_ssn_never_saved(self):
        for text in ['123-00-0000', '901-00-0001']:
            with self.assertRaises(SafeInputError):
                self.save(text)
        self.assertEqual(self.store.load_case('case-1')['revision'], 0)
        self.assertNotIn(b'123-00-0000', self.path.read_bytes())

    def test_only_requested_fake_ssn_is_allowed(self):
        state = self.store.save_answer('case-1', 'Q12:dep1', '901-00-0001', actor='test', event_id='ssn',
                                       next_question_id='Q13', expected_revision=0)
        self.assertEqual(state['answers']['Q12:dep1']['value'], '901-00-0001')
        self.assertNotIn('901', self.store.get_resume_context('case-1')['summary'])

    def test_human_pause_flag_survives_restart(self):
        self.save()
        self.store.set_progress('case-1', next_question_id='Q2', expected_revision=1,
                                stage='paused', pending_review=['filing_status_uncertain'])
        context = CaseMemory(self.path).get_resume_context('case-1')
        self.assertEqual(context['stage'], 'paused')
        self.assertIn('volunteer', context['summary'])
