"""P3: one document per worker, scoped tools, no direct logs or agent calls."""
from silverfile_extraction.privacy import SafeInputError
from src.state import EXTRACTION_REVIEW, FORM_1099R_BOX_2B, OUT_OF_SCOPE

# Only the W-2 is read (vision). The other in-scope forms are skipped with a reason; their amounts are a
# known gap because Intake only asks yes/no. A 1099-R cannot be skipped quietly: its box 2b decides whether
# the return is in scope. Anything else is out of scope (business rule 5).
SKIPPED_IN_SCOPE = {'ssa-1099', 'ssa1099', '1099-int', '1099int', '1099-div', '1099div'}
FORM_1099R = {'1099-r', '1099r'}
MAX_KIND_CHARS = 30


def _label(kind) -> str:
    """The kind for a message: a short, plain label, never the raw text (it is document-controlled)."""
    text = ''.join(c for c in str(kind or '')[:MAX_KIND_CHARS] if c.isalnum() or c in ' -.')
    return text.strip() or 'unknown'


def _not_read(doc):
    kind = ' '.join(str(doc.get('kind') or '').split()).lower()
    record = {'doc_id': doc['id'], 'kind': doc.get('kind'), 'fields': {}, 'status': 'skipped'}
    if kind in SKIPPED_IN_SCOPE:
        record['reason'] = 'In-scope form that is not read yet; its amounts are not captured (known gap).'
        return {'extracted': {doc['id']: record},
                'handoff_request': {'to': 'rules', 'reason': 'Form not read; Rules must check document scope.'}}
    if kind in FORM_1099R:
        condition = FORM_1099R_BOX_2B
        reason = '1099-R box 2b cannot be read from this document; a volunteer must check it.'
    else:
        condition = OUT_OF_SCOPE
        reason = f'Unsupported document type: {_label(doc.get("kind"))}.'
    record['reason'] = reason
    return {'extracted': {doc['id']: record},
            'escalation': {'pending': True, 'condition': condition, 'reason': reason,
                           'raised_by': 'extraction', 'document_id': doc['id']},
            'handoff_request': {'to': 'human', 'reason': reason}}


def run(view, tools):
    documents = view.get('documents', [])
    if len(documents) != 1:
        raise ValueError('Extraction requires exactly one document per parallel worker.')
    doc = documents[0]
    if doc.get('kind') != 'W-2':
        return _not_read(doc)
    # Only the explicitly unscoped measurement baseline includes prior records.
    history = ({key: item['record'] for key, item in view.get('extracted', {}).items()
                if 'record' in item} if 'extracted' in view else None)
    result = tools.call('p3_extract_w2', document=doc, history=history)
    if result.get('status') == 'needs_review':
        return {'extracted': {doc['id']: result},
                'escalation': {'pending': True, 'condition': EXTRACTION_REVIEW,
                              'reason': 'Compare the extracted W-2 amounts with the source image.',
                              'raised_by': 'extraction', 'document_id': doc['id']},
                'handoff_request': {'to': 'human', 'reason': 'W-2 visual verification required'}}
    return {'extracted': {doc['id']: result},
            'handoff_request': {'to': 'rules', 'reason': 'explicit synthetic fixture transcribed'}}
