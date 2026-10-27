"""Local P3 demo using the team's actual graph, tools and human gate."""
from pathlib import Path
from silverfile_extraction.checkpointer import case_config, sqlite_checkpointer
from silverfile_extraction.models import HumanDecision
from silverfile_extraction.privacy import SafeInputError
from src.p3.bridge import P3Tools


class ExtractionService:
    def __init__(self, runtime='runtime', reader=None):
        self.runtime = Path(runtime)
        self.tools = P3Tools(self.runtime, reader)

    @property
    def reader(self):
        return self.tools.reader

    @reader.setter
    def reader(self, value):
        self.tools.reader = value

    def __enter__(self):
        from src.graph import build_graph
        self.runtime.mkdir(parents=True, exist_ok=True)
        self._manager = sqlite_checkpointer(self.runtime / 'team_checkpoints.sqlite')
        saver = self._manager.__enter__()
        self.graph = build_graph(checkpointer=saver, trace_dir=self.runtime / 'traces',
                                 tool_registry=self.tools.registry())
        return self

    def __exit__(self, *args):
        return self._manager.__exit__(*args)

    def snapshot(self, case_id):
        state = self.graph.get_state(case_config(case_id))
        values = state.values or {}
        extracted = values.get('extracted', {})
        records = {key: entry['record'] for key, entry in extracted.items() if 'record' in entry}
        documents = {key: entry['document'] for key, entry in extracted.items() if 'document' in entry}
        escalation = values.get('escalation') or {}
        current = escalation.get('document_id') or next(iter(records), None)
        return {'session_id': case_id, 'pending': bool(escalation.get('pending')),
                'current_document_id': current, 'records': records, 'documents': documents,
                'team_status': values.get('status', 'new'), 'escalation': escalation,
                'summary': {'documents': len(records), **{status: sum(r['status'] == status for r in records.values())
                            for status in ['ready_for_rules', 'needs_review', 'rejected']}}}

    def submit(self, case_id, data, *, synthetic_confirmed, context_strategy=True):
        config = case_config(case_id)
        existing = self.snapshot(case_id)
        if existing['records']:
            raise SafeInputError('This demo uses one document per case. Choose a new case ID for another W-2.')
        if existing['pending']:
            raise SafeInputError('Resolve the pending human request first.')
        ref = self.tools.upload(data, synthetic_confirmed)
        state = self.graph.get_state(config)
        if state.next:
            prior = (state.values or {}).get('documents', [])
            if not prior or prior[0]['id'] != ref['id']:
                raise SafeInputError('Retry this case with its original image or choose a new case ID.')
            self.graph.invoke(None, config)
        else:
            # P3 demo inputs only. Never claim the supplied Intake stub collected these.
            self.graph.invoke({'case_id': case_id, 'documents': [ref], 'intake_complete': True,
                               'facts': {'age': {'value': 70, 'source': 'P3 synthetic demo'},
                                         'filing_status_claim': {'value': 'single', 'source': 'P3 synthetic demo'}}}, config)
        return self.snapshot(case_id)

    def resolve(self, case_id, decision: HumanDecision):
        from langgraph.types import Command
        snapshot = self.snapshot(case_id)
        if snapshot['escalation'].get('condition') != 'EXTRACTION_REVIEW':
            raise SafeInputError('This page can only resolve extraction review. Use the team human dashboard for other conditions.')
        current = snapshot['current_document_id']
        # Validate before resume so the UI can show a concise error without caching bad input.
        if decision.action == 'accept':
            self.tools.registry()['p3_verify_w2'](
                self.graph.get_state(case_config(case_id)).values['extracted'][current],
                decision.model_dump(mode='json'))
        answer = {'decision': 'continue' if decision.action == 'accept' else 'stop',
                  'note': decision.reason}
        if decision.action == 'accept':
            answer['resolution'] = {'document_id': current, 'review': decision.model_dump(mode='json')}
        self.graph.invoke(Command(resume=answer), case_config(case_id))
        return self.snapshot(case_id)
