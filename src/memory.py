"""P3 public memory entry points for P1/P2. No model call or tax interpretation."""
from silverfile_extraction.case_memory import CaseMemory, StaleRevisionError
from silverfile_extraction.checkpointer import case_config, sqlite_checkpointer


def load_resume_context(graph, case_id):
    """Read the team's persisted state without invoking/restarting the graph."""
    snapshot = graph.get_state(case_config(case_id))
    state = snapshot.values or {}
    facts = state.get('facts', {})
    topics = []
    if any(k in facts for k in ['age', 'taxpayer_dob', 'spouse_age', 'spouse_dob']):
        topics.append('age information')
    if any(k in facts for k in ['filing_status', 'filing_status_claim']):
        topics.append('filing information')
    if state.get('documents'):
        topics.append('uploaded documents')
    summary = ('Welcome back. We saved information about ' + ', '.join(topics) + '.'
               if topics else 'Welcome back. Your saved place is available.')
    if (state.get('escalation') or {}).get('pending'):
        summary += ' A volunteer needs to review the case before you continue.'
    return {'case_id': case_id, 'summary': summary,
            'pending_question': state.get('pending_question'),
            'status': state.get('status', 'new'),
            'awaiting_human': bool((state.get('escalation') or {}).get('pending'))}
