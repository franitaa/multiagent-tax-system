"""P3: one document per worker, scoped tools, no direct logs or agent calls."""
from silverfile_extraction.privacy import SafeInputError
from src.state import EXTRACTION_REVIEW, OUT_OF_SCOPE


def run(view, tools):
    documents = view.get('documents', [])
    if len(documents) != 1:
        raise ValueError('Extraction requires exactly one document per parallel worker.')
    doc = documents[0]
    if doc.get('kind') != 'W-2':
        return {'escalation': {'pending': True, 'condition': OUT_OF_SCOPE,
                'reason': 'This extraction component supports W-2 only; human handling required.',
                'raised_by': 'extraction', 'document_id': doc['id']},
                'handoff_request': {'to': 'human', 'reason': 'unsupported extraction document'}}
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
