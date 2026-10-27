"""Typed P3 evidence adapted to the team's five-field monetary contract."""
import hashlib
import re
from pathlib import Path

from silverfile_extraction.extractor import extract_w2
from silverfile_extraction.image_input import prepare_image, save_source
from silverfile_extraction.models import Document, ExtractionRecord, HumanDecision, money_string
from silverfile_extraction.privacy import SafeInputError, SSN
from silverfile_extraction.review import apply_human_decision


def team_record(doc_id, document, record):
    fields = {
        'box_' + box: {'value': float(amount.value), 'formula': 'Transcribed from W-2 box ' + box,
                      'inputs': {'evidence': amount.source.model_dump(mode='json')},
                      'source': f'{doc_id}:page1:box{box}:sha256:{document.sha256}',
                      'tool': 'p3_human_verified' if record.status == 'ready_for_rules' else ('p3_anthropic_vision' if record.backend == 'anthropic-direct' else 'p3_openai_vision')}
        for box, amount in record.fields.items()}
    return {'doc_id': doc_id, 'kind': record.document_type, 'fields': fields,
            'status': record.status, 'revision': record.revision,
            'document': document.model_dump(mode='json'), 'record': record.model_dump(mode='json'),
            'usage': {**record.usage.model_dump(mode='json'),
                      'provider': 'anthropic' if record.backend == 'anthropic-direct' else 'openai'}}


def verify_w2(envelope, decision):
    """Called by the orchestrator-owned human gate, not by another agent."""
    original = ExtractionRecord.model_validate(envelope['record'])
    if original.status != 'needs_review':
        raise SafeInputError('This extraction is no longer awaiting review.')
    document = Document.model_validate(envelope['document'])
    updated = apply_human_decision(document, original, HumanDecision.model_validate(decision))
    return team_record(envelope['doc_id'], document, updated)


def extract_text_fixture(document, history=None):
    """Deterministic test-only path. Never infer amounts from an arbitrary TEST DATA label."""
    if document.get('fixture_format') != 'synthetic-w2-v1' or document.get('synthetic_confirmed') is not True:
        raise SafeInputError('Upload a confirmed synthetic W-2 image. Plain text is not an image.')
    text = document.get('text', '')
    if SSN.search(text):
        raise SafeInputError('Text fixtures must not include identifiers.')
    pairs = re.findall(r'^Box (1|2): ([0-9]+\.[0-9]{2})$', text, re.M)
    if len(pairs) != 2 or {box for box, value in pairs} != {'1', '2'}:
        raise SafeInputError('The deterministic fixture must explicitly contain boxes 1 and 2.')
    digest = hashlib.sha256(text.encode()).hexdigest()
    return {'doc_id': document['id'], 'kind': document['kind'], 'status': 'test_fixture',
            'fields': {'box_' + box: {'value': money_string(value),
                       'formula': 'Exact transcription of explicit synthetic text fixture',
                       'inputs': {'observed_text': value, 'box': box, 'sha256': digest},
                       'source': document['id'], 'tool': 'p3_text_fixture'} for box, value in pairs}}


class P3Tools:
    """Per-session reader and evidence directory. Credentials never enter graph state."""
    def __init__(self, runtime, reader=None):
        self.runtime = Path(runtime)
        self.reader = reader

    def upload(self, data, synthetic_confirmed):
        doc, png = prepare_image(data, synthetic_confirmed=synthetic_confirmed)
        handle = hashlib.sha256(png).hexdigest()
        directory = self.runtime / 'uploads'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (handle + '.png')
        path.write_bytes(png)
        return {'id': 'doc_' + handle, 'kind': 'W-2', 'text': '', 'image_ref': handle,
                'synthetic_confirmed': True}

    def extract(self, document, history=None):
        if 'image_ref' not in document:
            return extract_text_fixture(document)
        if document.get('synthetic_confirmed') is not True:
            raise SafeInputError('Synthetic-data confirmation is required.')
        handle = document['image_ref']
        if not isinstance(handle, str) or not re.fullmatch(r'[0-9a-f]{64}', handle):
            raise SafeInputError('Invalid image reference.')
        if document['id'] != 'doc_' + handle:
            raise SafeInputError('Document ID does not match its source reference.')
        if self.reader is None:
            raise SafeInputError('Enter an API key before starting image extraction.')
        data = (self.runtime / 'uploads' / (handle + '.png')).read_bytes()
        if hashlib.sha256(data).hexdigest() != handle:
            raise SafeInputError('Source image integrity check failed.')
        doc, record, png = extract_w2(data, self.reader, synthetic_confirmed=True, records=history or {},
                                      context_strategy=history is None)
        save_source(doc, png, self.runtime / 'documents')
        return team_record(document['id'], doc, record)

    def registry(self):
        return {'p3_extract_w2': self.extract, 'p3_verify_w2': verify_w2}
