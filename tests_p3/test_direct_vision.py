"""No API calls and no OCR executables. Vision responses are explicitly mocked."""
import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image
from p3_helpers import FakeReader, good_result
from silverfile_extraction.extractor import extract_w2
from silverfile_extraction.handoff import UserAmountClaim, flag_document_conflicts, to_p5_provenance
from silverfile_extraction.image_input import prepare_image, save_source
from silverfile_extraction.models import HumanDecision, money_string
from silverfile_extraction.privacy import SafeInputError
from silverfile_extraction.review import apply_human_decision
from silverfile_extraction.vision import VisionField, build_context, request_messages


class DirectVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (ROOT / 'data/fixtures/w2_01.jpg').read_bytes()

    def extract(self, result=None):
        return extract_w2(self.data, FakeReader(result), synthetic_confirmed=True)

    def test_real_image_encoded_without_subprocess(self):
        with patch('subprocess.run', side_effect=AssertionError('No external OCR is permitted')):
            doc, record, png = self.extract()
        self.assertEqual(Image.open(io.BytesIO(png)).size, (doc.image_width, doc.image_height))
        self.assertEqual(record.fields['1'].value, '30000.00')  # mocked model, not measured accuracy

    def test_provider_input_contains_original_normalized_image(self):
        doc, png = prepare_image(self.data, synthetic_confirmed=True)
        messages = request_messages(png, 'current image')
        image_url = messages[1]['content'][1]['image_url']
        self.assertEqual(base64.b64decode(image_url.split(',')[1]), png)
        self.assertEqual(doc.tokens, [])
        self.assertEqual(doc.sha256, hashlib.sha256(png).hexdigest())

    def test_invalid_optional_amount_requires_explicit_correction(self):
        result = good_result()
        result.fields.append(VisionField(box='10', observed_text='unreadable', confidence='low'))
        doc, record, _ = self.extract(result)
        with self.assertRaises(SafeInputError):
            apply_human_decision(doc, record, HumanDecision(action='accept', reviewer='test',
                reason='Checked source', confirmed_w2=True))

    def test_no_zero_from_missing_box(self):
        result = good_result()
        result.fields = result.fields[:1]
        _, record, _ = self.extract(result)
        self.assertNotIn('2', record.fields)
        self.assertEqual(record.status, 'needs_review')

    def test_source_is_honest_about_model_reading(self):
        doc, record, _ = self.extract()
        source = record.fields['1'].source
        self.assertEqual(source.method, 'vision_transcription')
        self.assertEqual(source.document_sha256, doc.sha256)
        self.assertIsNone(source.bbox)
        self.assertEqual(source.token_ids, [])
        self.assertIsNone(record.fields['1'].ocr_confidence)

    def test_every_read_requires_human_verification(self):
        _, record, _ = self.extract()
        self.assertEqual(record.status, 'needs_review')
        self.assertIn('VISION_REVIEW_REQUIRED', [i.code for i in record.issues])
        with self.assertRaises(SafeInputError):
            to_p5_provenance(record)

    def test_duplicate_box_not_silently_selected(self):
        result = good_result()
        result.fields.append(VisionField(box='1', observed_text='90.00', confidence='high'))
        _, record, _ = self.extract(result)
        self.assertNotIn('1', record.fields)

    def test_bad_money_not_in_fields(self):
        for value in ['', '30000', '-1.00', 'NaN', '1,23.00']:
            result = good_result()
            result.fields[0].observed_text = value
            with self.subTest(value=value):
                _, record, _ = self.extract(result)
                self.assertNotIn('1', record.fields)

    def test_non_test_ssn_and_unreadable_identifier_are_blocked(self):
        for status in ['non_test', 'unreadable']:
            result = good_result()
            result.ssn_status = status
            with self.assertRaises(SafeInputError):
                self.extract(result)

    def test_bad_or_inconsistent_prefix_blocked(self):
        for prefixes in [[], ['123'], ['901-00-0001'], ['abc']]:
            result = good_result()
            result.ssn_prefixes = prefixes
            with self.assertRaises(SafeInputError):
                self.extract(result)

    def test_unexpected_identifier_in_amount_blocked(self):
        result = good_result()
        result.fields[0].observed_text = '123-00-0000'
        with self.assertRaises(SafeInputError):
            self.extract(result)

    def test_absent_ssn_can_be_reviewed(self):
        result = good_result()
        result.ssn_status = 'absent'
        result.ssn_prefixes = []
        _, record, _ = self.extract(result)
        self.assertEqual(record.status, 'needs_review')

    def test_no_upload_without_explicit_confirmation(self):
        reader = FakeReader()
        with self.assertRaises(SafeInputError):
            extract_w2(self.data, reader, synthetic_confirmed=False)
        self.assertEqual(reader.calls, [])

    def test_invalid_image_never_reaches_provider(self):
        reader = FakeReader()
        with self.assertRaises(SafeInputError):
            extract_w2(b'bad file', reader, synthetic_confirmed=True)
        self.assertEqual(reader.calls, [])

    def test_image_limit_before_provider(self):
        with self.assertRaises(SafeInputError):
            prepare_image(b'x' * (12 * 1024 * 1024 + 1), synthetic_confirmed=True)

    def test_source_saved_exactly_and_stably(self):
        doc, _, png = self.extract()
        with tempfile.TemporaryDirectory() as tmp:
            save_source(doc, png, Path(tmp))
            self.assertEqual((Path(tmp) / doc.image_file).read_bytes(), png)
        doc2, _ = prepare_image(self.data, synthetic_confirmed=True)
        self.assertEqual(doc.document_id, doc2.document_id)

    def test_low_confidence_and_other_entries_are_not_lost(self):
        result = good_result()
        result.fields[0].confidence = 'low'
        result.other_boxes = 'populated'
        _, record, _ = self.extract(result)
        self.assertIn('LOW_VISION_CONFIDENCE', [i.code for i in record.issues])
        self.assertEqual(record.observations['boxes_12_to_20'], 'populated')

    def test_human_approval_keeps_source_and_history(self):
        doc, record, _ = self.extract()
        approved = apply_human_decision(doc, record, HumanDecision(
            action='accept', reviewer='tester', reason='Compared original image.', confirmed_w2=True))
        self.assertEqual(approved.status, 'ready_for_rules')
        self.assertEqual(record.status, 'needs_review')
        self.assertTrue(approved.review_history)
        self.assertEqual(set(to_p5_provenance(approved)['1']), {'value','formula','inputs','source','tool'})

    def test_missing_box_cannot_be_approved_as_zero(self):
        result = good_result()
        result.fields = result.fields[:1]
        doc, record, _ = self.extract(result)
        with self.assertRaises(SafeInputError):
            apply_human_decision(doc, record, HumanDecision(
                action='accept', reviewer='tester', reason='Checked.', confirmed_w2=True))

    def test_conflict_requires_explicit_resolution_and_preserves_both(self):
        doc, record, _ = self.extract()
        claim = UserAmountClaim(document_id=doc.document_id, box='1', value='35000.00',
                                entered_by='tester', recorded_at='2026-10-26T00:00:00Z')
        record = flag_document_conflicts(record, [claim])
        with self.assertRaises(SafeInputError):
            apply_human_decision(doc, record, HumanDecision(
                action='accept', reviewer='tester', reason='Checked.', confirmed_w2=True))
        approved = apply_human_decision(doc, record, HumanDecision(
            action='accept', reviewer='tester', reason='Document is correct.', confirmed_w2=True,
            corrections={'1':'30000.00'}))
        self.assertEqual(approved.fields['1'].source.method, 'human_transcription')
        self.assertEqual(len(approved.review_history[0]['previous_conflicts']), 1)

    def test_selective_recall_omits_prior_values(self):
        _, record, _ = self.extract()
        records = {record.document_id: record.model_dump(mode='json')}
        enabled = build_context(records, context_strategy=True)
        disabled = build_context(records, context_strategy=False)
        self.assertNotIn('30,000.00', enabled)
        self.assertIn('30,000.00', disabled)
        self.assertEqual(record.fields['1'].value, '30000.00')

    def test_money_remains_exact(self):
        self.assertEqual(money_string('$30,001.09'), '30001.09')
