"""Local-only dual-provider vision workbench. The API key is never saved to disk."""
import json
import os
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError
from silverfile_extraction.models import BOX_LABELS, HumanDecision
from silverfile_extraction.privacy import SafeInputError
from src.p3.service import ExtractionService
from src.memory import load_resume_context
from silverfile_extraction.vision import DEFAULT_MODELS, PROVIDER_LABELS, VisionReader

load_dotenv(ROOT / '.env')
st.set_page_config(page_title='SilverFile · W-2 Vision', page_icon='📄', layout='wide')
st.title('SilverFile · Document Extraction')
st.caption('Read a W-2 image with OpenAI or Claude. No Tesseract installation required.')
st.warning('P3 TEAM INTEGRATION DEMO: uses synthetic age 70 / Single inputs. Team computation and final review are still stubs. No completed return is produced.')
runtime = Path(os.getenv('SILVERFILE_RUNTIME', str(ROOT / 'runtime')))


def clear_key():
    st.session_state['openai_api_key'] = ''
    st.session_state['anthropic_api_key'] = ''


with st.sidebar:
    st.header('1. Choose an AI provider')
    provider = st.selectbox('AI provider', ['openai', 'anthropic'],
                            format_func=lambda name: PROVIDER_LABELS[name], key='selected_provider')
    provider_label = PROVIDER_LABELS[provider]
    key_env = 'OPENAI_API_KEY' if provider == 'openai' else 'ANTHROPIC_API_KEY'
    key_slot = provider + '_api_key'
    if key_slot not in st.session_state:
        st.session_state[key_slot] = os.getenv(key_env, '')
    api_key = st.text_input(provider_label + ' API key', type='password', key=key_slot,
                           help='Only the selected provider receives its key and image. Keys are not saved to files.')
    st.button('Clear API keys', on_click=clear_key)
    st.caption('API calls use the selected provider account and may incur charges.')
    with st.expander('Advanced settings'):
        model_env = 'OPENAI_MODEL' if provider == 'openai' else 'ANTHROPIC_MODEL'
        model = st.text_input('Vision model', value=os.getenv(model_env, DEFAULT_MODELS[provider]),
                              key=provider + '_model')
        selective_recall = True
        st.caption('Each extraction worker receives only its current document.')
    st.header('2. Choose a case')
    case_id = st.text_input('Case ID', value='demo', max_chars=64,
                            help='Use the same ID when you come back. This is also the thread ID.')
    st.button('Reload saved case', use_container_width=True)
    st.caption('Use a new case ID for each new W-2 in this demo.')
    st.caption('Your key stays in memory for this page session. Saved case data stays on this computer.')

try:
    with ExtractionService(runtime) as service:
        saved = service.snapshot(case_id)
        st.info(load_resume_context(service.graph, case_id)['summary'])
        a, b, c = st.columns(3)
        a.metric('Documents', saved['summary']['documents'])
        b.metric('Ready for rules', saved['summary']['ready_for_rules'])
        c.metric('Needs human review', saved['summary']['needs_review'])
        st.subheader('3. Upload a synthetic W-2')
        st.caption(f'The whole image is sent to {provider_label}. Use only fictional classroom documents. '
                   'Identifier screening happens after the model reads the image, not before upload.')
        with st.form('upload'):
            upload = st.file_uploader('Choose a PNG or JPEG image', type=['png', 'jpg', 'jpeg'])
            confirmed = st.checkbox(f'This image contains only fictional test data, and I agree to send it to {provider_label}.', key='consent_' + provider)
            submitted = st.form_submit_button('Read W-2 image', disabled=saved['pending'])
        if submitted:
            if not upload:
                raise SafeInputError('Choose an image first. Try data/fixtures/w2_01.jpg.')
            if not confirmed:
                raise SafeInputError('Confirm fictional data and image transmission before continuing.')
            with closing(VisionReader(api_key, model, provider=provider)) as reader:
                service.reader = reader
                with st.spinner(f'{provider_label} is reading the image…'):
                    service.submit(case_id, upload.getvalue(), synthetic_confirmed=True,
                                   context_strategy=selective_recall)
            st.rerun()

        st.caption('Team graph status: ' + saved['team_status'])
        if saved['pending'] and saved['escalation'].get('condition') != 'EXTRACTION_REVIEW':
            st.warning('This case needs a different team human review. Resolve it in the team dashboard.')
        current_id = saved['current_document_id']
        current = saved['records'].get(current_id, {})
        if saved['pending'] and current and saved['escalation'].get('condition') == 'EXTRACTION_REVIEW':
            st.subheader('4. Check the extracted amounts')
            st.warning('AI can misread numbers. Compare each amount with the source before accepting.')
            image_col, form_col = st.columns([1.3, 1])
            with image_col:
                st.image(str(runtime / 'documents' / saved['documents'][current_id]['image_file']),
                         caption='Original synthetic source, orientation normalized. Not automatically redacted.')
            with form_col:
                for issue in current['issues']:
                    st.write('• ' + issue['message'] + (f" (Box {issue['box']})" if issue['box'] else ''))
                required_corrections = {x['box'] for x in current['issues'] if x['box'] and x['code'] in {
                    'MISSING_OR_UNREADABLE_BOX', 'AMBIGUOUS_BOX', 'UNREADABLE_AMOUNT', 'DOCUMENT_USER_CONFLICT'}}
                boxes = sorted(set(current['fields']) | {'1', '2'} | required_corrections, key=int)
                with st.form('review'):
                    action = st.radio('Decision', ['accept', 'reject'], horizontal=True)
                    amounts = {box: st.text_input(f'Box {box} · {BOX_LABELS[box]}',
                               value=current['fields'].get(box, {}).get('value', ''), key=f'{current_id}-{box}')
                               for box in boxes}
                    reviewer = st.text_input('Reviewer identifier', placeholder='demo-volunteer')
                    reason = st.text_input('Review note / source for corrections',
                                           placeholder='Compared each amount with the original W-2.')
                    year = st.number_input('Printed tax year', min_value=1900, max_value=2100,
                                           value=current.get('tax_year') or 2025)
                    checked = st.checkbox('I checked this is a W-2 and visually verified every amount.')
                    if st.form_submit_button('Save review and continue'):
                        corrections = {box: value for box, value in amounts.items()
                                       if value.strip() and (value != current['fields'].get(box, {}).get('value')
                                                            or box in required_corrections)}
                        service.resolve(case_id, HumanDecision(action=action, reviewer=reviewer,
                                        reason=reason, corrections=corrections,
                                        confirmed_w2=checked, tax_year=int(year)))
                        st.rerun()
        if saved['records']:
            st.subheader('Saved results and sources')
            for doc_id, record in saved['records'].items():
                with st.expander(f"{doc_id[:16]} · {record['status']}", expanded=doc_id == current_id):
                    st.table([{'Box': box, 'Printed label': BOX_LABELS[box], 'Amount (USD)': amount['value'],
                               'Source': amount['source']['method'],
                               'Model confidence (not probability)': amount.get('vision_confidence') or '—'}
                              for box, amount in sorted(record['fields'].items(), key=lambda item: int(item[0]))])
                    st.json({box: amount['source'] for box, amount in record['fields'].items()}, expanded=False)
                    st.caption('Boxes 12–20 are not fully structured. The Rules agent must inspect the source image.')
                    st.download_button('Download extracted record', json.dumps(record, indent=2),
                                       file_name=f'{doc_id}.json', mime='application/json', key=doc_id)
except SafeInputError as exc:
    st.error(str(exc))
except ValidationError:
    st.error('Check the review fields. A reviewer and a review note are required.')
except ModuleNotFoundError:
    st.error('A dependency is missing. Close this app and run START_WINDOWS.cmd again.')
except (ValueError, OSError):
    st.error('The operation could not be completed. Check the case ID, input fields, and local file permissions.')
