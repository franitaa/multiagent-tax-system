"""Measure real API input tokens across ten images in a persistent graph thread."""
import argparse
import getpass
import json
import os
import sys
import uuid
from contextlib import closing
from pathlib import Path
from typing import Annotated, TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from silverfile_extraction.checkpointer import case_config, sqlite_checkpointer
from silverfile_extraction.extractor import extract_w2
from silverfile_extraction.image_input import save_source
from silverfile_extraction.memory import merge_documents, merge_versioned
from silverfile_extraction.privacy import SafeInputError
from silverfile_extraction.vision import DEFAULT_MODELS, VisionReader


class BatchState(TypedDict, total=False):
    image_path: str
    records: Annotated[dict, merge_versioned]
    documents: Annotated[dict, merge_documents]
    current_id: str


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--compare', action='store_true')
    group.add_argument('--no-context-strategy', action='store_true')
    parser.add_argument('--provider', choices=['openai', 'anthropic'], default='openai')
    parser.add_argument('--model')
    args = parser.parse_args()
    from langgraph.graph import StateGraph, START, END
    destination = ROOT / 'runtime/benchmark'
    destination.mkdir(parents=True, exist_ok=True)
    images = sorted((ROOT / 'data/fixtures').glob('w2_*.jpg'))
    if len(images) != 10:
        raise SafeInputError('Expected exactly ten synthetic W-2 fixtures.')
    modes = [False, True] if args.compare else [not args.no_context_strategy]
    print(f'This measurement sends fictional fixtures in {len(modes) * 10} paid API calls.')
    key_env = 'OPENAI_API_KEY' if args.provider == 'openai' else 'ANTHROPIC_API_KEY'
    key = os.getenv(key_env) or getpass.getpass(args.provider + ' API key (hidden): ')
    args.model = args.model or DEFAULT_MODELS[args.provider]
    run_id = uuid.uuid4().hex
    results = {}
    with closing(VisionReader(key, args.model, provider=args.provider)) as reader:
        for enabled in modes:
            label = 'enabled' if enabled else 'disabled'

            def extract(state):
                document, record, png = extract_w2(
                    Path(state['image_path']).read_bytes(), reader,
                    synthetic_confirmed=True, records=state.get('records', {}),
                    context_strategy=enabled)
                save_source(document, png, destination / 'documents')
                return {'documents': {document.document_id: document.model_dump(mode='json')},
                        'records': {document.document_id: record.model_dump(mode='json')},
                        'current_id': document.document_id}

            builder = StateGraph(BatchState)
            builder.add_node('extract', extract)
            builder.add_edge(START, 'extract')
            builder.add_edge('extract', END)
            counts = []
            with sqlite_checkpointer(destination / 'measurements.sqlite') as saver:
                graph = builder.compile(checkpointer=saver)
                config = case_config(f'{run_id}-{label}')
                for index, path in enumerate(images, 1):
                    state = graph.invoke({'image_path': str(path)}, config)
                    record = state['records'][state['current_id']]
                    usage = record['usage']
                    if usage['api_input_tokens'] is None:
                        raise SafeInputError('The API did not return input-token usage.')
                    counts.append({'image': path.name, **usage})
                    print(f'{label}: image {index}/10, input tokens={usage["api_input_tokens"]}')
                    results[label] = counts
                    (destination / f'{run_id}.json').write_text(
                        json.dumps(results, indent=2), encoding='utf-8')
    lines = ['# Actual API context measurements', '', f'Run: `{run_id}`. Provider: `{args.provider}`. Requested model: `{args.model}`.',
             '', 'Counts are provider-reported input tokens (including cache reads/writes for Claude), including images and schema. Each mode uses one',
             'persistent LangGraph thread; all records remain unapproved. No counts are mocked.', '',
             '| Image | Strategy disabled | Strategy enabled |', '| --- | ---: | ---: |']
    for index, path in enumerate(images):
        cells = [str(results[mode][index]['api_input_tokens']) if mode in results else '—'
                 for mode in ['disabled', 'enabled']]
        lines.append(f'| {path.name} | {cells[0]} | {cells[1]} |')
    lines += ['', 'The disabled baseline replays prior transcriptions. Enabled selective recall sends',
              'only the current image and a short session summary. Full records remain in SQLite.',
              'Image tokens may dominate; inspect the measured trend before claiming a flatter curve.']
    (ROOT / 'docs/metrics.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Saved actual measurements to docs/metrics.md and runtime/benchmark/.')


if __name__ == '__main__':
    try:
        main()
    except SafeInputError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('Stopped. Completed measurements remain in runtime/benchmark/.')
        raise SystemExit(1)
