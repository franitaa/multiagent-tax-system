"""Synthetic model responses for offline tests, not evidence of model accuracy."""
from silverfile_extraction.models import Usage
from silverfile_extraction.vision import VisionResult, VisionField


def good_result():
    return VisionResult(document_type='W-2', tax_year=2025, ssn_status='test_only', ssn_prefixes=['901'],
                        fields=[VisionField(box='1', observed_text='30,000.00', confidence='high'),
                                VisionField(box='2', observed_text='2,000.00', confidence='high')],
                        unreadable_boxes=[], other_boxes='blank')


class FakeReader:
    """Test injection only. It is never selectable in the workbench."""
    def __init__(self, result=None):
        self.result = result or good_result()
        self.calls = []
        self.secret = 'TEST-SECRET-NEVER-PERSIST'

    def read(self, png, context):
        self.calls.append((png, context))
        return self.result, Usage(prompt_text_tokens=None, api_input_tokens=100,
                                   api_output_tokens=40, model='mock-only', request_id='mock-only')
