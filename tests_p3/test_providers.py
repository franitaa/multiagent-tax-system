"""Provider routing tests with fake SDKs. No live credentials or network calls."""
import base64
import io
import sys
import types
import unittest
from unittest.mock import patch
from PIL import Image

from silverfile_extraction.vision import VisionReader, VisionResult, DEFAULT_MODELS
from silverfile_extraction.privacy import SafeInputError
from silverfile_extraction.extractor import extract_w2
from src.p3.bridge import team_record


def result():
    return VisionResult(document_type='W-2', tax_year=2025, ssn_status='test_only',
        ssn_prefixes=['901'], fields=[{'box':'1', 'observed_text':'1000.00', 'confidence':'high'},
        {'box':'2', 'observed_text':'100.00', 'confidence':'high'}], unreadable_boxes=[], other_boxes='blank')


def sdk(name, parsed=None, stop='end_turn', error=None):
    module = types.ModuleType(name)
    module.calls = []
    for label in ['AuthenticationError', 'RateLimitError', 'BadRequestError', 'NotFoundError',
                  'APIConnectionError', 'APIStatusError']:
        setattr(module, label, type(label, (Exception,), {}))
    class Client:
        def __init__(self, **kwargs):
            module.init = kwargs
            self.responses = self.messages = self
        def parse(self, **kwargs):
            module.calls.append(kwargs)
            if error:
                raise getattr(module, error)('sensitive provider diagnostic')
            value = parsed if parsed is not None else result()
            return types.SimpleNamespace(output_parsed=value, parsed_output=value, stop_reason=stop,
                usage=types.SimpleNamespace(input_tokens=120, output_tokens=20,
                    cache_creation_input_tokens=10, cache_read_input_tokens=5),
                model=kwargs['model'], id='mock-response')
        def close(self):
            module.closed = True
    module.OpenAI = module.Anthropic = Client
    return module


class ProviderTests(unittest.TestCase):
    def setUp(self):
        image = io.BytesIO()
        Image.new('RGB', (20, 20), 'white').save(image, 'PNG')
        self.png = image.getvalue()

    def test_openai_default_is_backward_compatible(self):
        module = sdk('openai')
        with patch.dict(sys.modules, {'openai': module}):
            reader = VisionReader('example-key')
            _, usage = reader.read(self.png, 'context')
            reader.close()
        self.assertEqual(module.init['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(module.calls[0]['model'], DEFAULT_MODELS['openai'])
        self.assertFalse(module.calls[0]['store'])
        self.assertEqual(usage.api_input_tokens, 120)
        self.assertTrue(module.closed)

    def test_claude_uses_own_endpoint_and_native_image_payload(self):
        a, o = sdk('anthropic'), sdk('openai')
        with patch.dict(sys.modules, {'anthropic': a, 'openai': o}):
            reader = VisionReader('claude-example-key', provider='anthropic')
            parsed, usage = reader.read(self.png, 'context')
            reader.close()
        self.assertFalse(o.calls)
        self.assertEqual(a.init['base_url'], 'https://api.anthropic.com')
        self.assertEqual(a.init['api_key'], 'claude-example-key')
        call = a.calls[0]
        self.assertEqual(call['model'], DEFAULT_MODELS['anthropic'])
        self.assertIs(call['output_format'], VisionResult)
        self.assertNotIn('store', call)
        source = call['messages'][0]['content'][0]['source']
        self.assertEqual(base64.b64decode(source['data']), self.png)
        self.assertEqual(parsed.fields[0].observed_text, '1000.00')
        self.assertEqual(usage.api_input_tokens, 135)

    def test_key_not_sent_to_other_provider_on_error(self):
        a, o = sdk('anthropic', error='AuthenticationError'), sdk('openai')
        with patch.dict(sys.modules, {'anthropic': a, 'openai': o}):
            with self.assertRaises(SafeInputError) as error:
                VisionReader('private-key', provider='anthropic').read(self.png, 'context')
        self.assertNotIn('private-key', str(error.exception))
        self.assertNotIn('sensitive provider diagnostic', str(error.exception))
        self.assertFalse(o.calls)

    def test_recognizable_wrong_provider_keys_are_blocked(self):
        with self.assertRaises(SafeInputError):
            VisionReader('sk-ant-example', provider='openai')
        with self.assertRaises(SafeInputError):
            VisionReader('sk-proj-example', provider='anthropic')

    def test_invalid_provider_and_blank_key_are_rejected(self):
        with self.assertRaises(SafeInputError):
            VisionReader('key', provider='other')
        with self.assertRaises(SafeInputError):
            VisionReader(' ', provider='anthropic')

    def test_truncated_claude_response_is_not_accepted(self):
        with patch.dict(sys.modules, {'anthropic': sdk('anthropic', stop='max_tokens')}):
            with self.assertRaises(SafeInputError):
                VisionReader('key', provider='anthropic').read(self.png, 'context')

    def test_claude_refusal_is_not_accepted(self):
        with patch.dict(sys.modules, {'anthropic': sdk('anthropic', stop='refusal')}):
            with self.assertRaises(SafeInputError):
                VisionReader('key', provider='anthropic').read(self.png, 'context')

    def test_invalid_structured_response_is_rejected(self):
        with patch.dict(sys.modules, {'anthropic': sdk('anthropic', parsed={'unexpected': 3})}):
            with self.assertRaises(SafeInputError):
                VisionReader('key', provider='anthropic').read(self.png, 'context')

    def test_claude_keeps_review_and_correct_provider_in_provenance(self):
        with patch.dict(sys.modules, {'anthropic': sdk('anthropic')}):
            reader = VisionReader('key', provider='anthropic')
            doc, record, _ = extract_w2(self.png, reader, synthetic_confirmed=True)
        self.assertEqual(record.backend, 'anthropic-direct')
        self.assertEqual(record.status, 'needs_review')
        self.assertEqual(team_record(doc.document_id, doc, record)['fields']['box_1']['tool'], 'p3_anthropic_vision')

    def test_claude_rejects_oversized_image_before_call(self):
        module = sdk('anthropic')
        with patch.dict(sys.modules, {'anthropic': module}):
            reader = VisionReader('key', provider='anthropic')
            with self.assertRaises(SafeInputError):
                reader.read(b'x' * 8_000_000, 'context')
        self.assertFalse(module.calls)
