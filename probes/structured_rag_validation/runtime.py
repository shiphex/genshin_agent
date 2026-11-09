"""Real core-self execution with full transport observation and intact history."""
from copy import deepcopy
from pathlib import Path
import sys
import time

from Benchmarks.agent_story.providers import LiveProvider, SEARCH_TOOL, SYSTEM, citation_check
from Benchmarks.agent_story.scenarios import public_turns
from Benchmarks.support.common import ROOT, read_rows, write_json
from Benchmarks.support.protocol import Worker
from probes.a06_diagnosis.controls import ObservedClient, api_statistics
from probes.a06_diagnosis.evidence import audit_transfers, audit_injected_history
from probes.core_self.worker import POLICIES
from .artifacts import seal
from .validation import validate_request


def observed_client(config, store, transport=None):
    def emit(event):
        store.append('api.jsonl', event)
        if event['event'] == 'request' and event['endpoint'] == 'chat/completions':
            validate_request(event['payload'], forced=((store.manifest['condition'] == 'A'
                and event['turn'] == 1 or store.manifest['condition'] == 'preflight' and event['turn'] == 0)
                and event['request'] == 1))
    return ObservedClient(config, emit, transport)


def run_sample(store, scene, corpus, client, *, condition, fixture=None, server_log=None):
    provider = LiveProvider(client, corpus, 5, 8, SYSTEM, policies=POLICIES)
    command = [sys.executable, '-B', str(ROOT / 'probes/core_self/worker.py')]
    if fixture is not None:
        write_json(store.path / 'injected-history.json', fixture, exclusive=True)
        command = [sys.executable, '-B', '-m', 'probes.a06_diagnosis.history_worker',
                   str((store.path / 'injected-history.json').resolve())]
        provider.histories['session'] = deepcopy(fixture['messages'])
        import json
        for message in fixture['messages']:
            if message['role'] == 'tool':
                provider.evidence.update({h['id']: h for h in json.loads(message['content'])['result']['evidence']})
    sample = f'{store.path.name}:{scene["id"]}'
    store.manifest['planned_samples'] = [{'sample_id': sample, 'scenario_id': scene['id']}]
    store.manifest['worker_command'] = command
    row = {'sample_id': sample, 'scenario_id': scene['id'], 'condition': condition,
           'turns': [], 'correct': None, 'execution_status': 'incomplete',
           'synthetic_history': fixture is not None}
    log = Path(server_log) if server_log else None
    offset = log.stat().st_size if log and log.exists() else 0
    if log is not None:
        def choice_guard():
            with log.open('rb') as handle:
                handle.seek(offset)
                lines = handle.read().decode('utf-8', errors='replace').splitlines()
            accepted = not any('tool_choice' in line and ('Wrong type' in line or 'using default' in line) for line in lines)
            store.append('api.jsonl', {'event': 'tool_choice_capability', 'server_rejected_named_choice': not accepted})
            return accepted
        client.choice_guard = choice_guard
    started = time.perf_counter()
    try:
        with Worker(command, store.path / 'worker.stderr.txt', timeout=240,
                    trace=lambda direction, message: store.append('trace.jsonl',
                        {'direction': direction, 'message': message})) as worker:
            worker.request('init', 'control', {'protocol_version': 1, 'suite': 'agent',
                'scenario_id': scene['id'], 'policies': POLICIES, 'system': SYSTEM,
                'tools': [SEARCH_TOOL], 'max_steps': 8, 'context_limit': None,
                'context_counter': 'service_managed'})
            worker.request('reset', 'session', {})
            for number, turn in enumerate(public_turns(scene), 1):
                if fixture is not None and number == 1:
                    continue
                client.begin(number, force_first=condition == 'A' and number == 1)
                provider.begin('session', turn['content'], number)
                before_models, before_tools = provider.total_models, provider.tool_requests
                tick = time.perf_counter()
                result = worker.request('turn', 'session', turn, provider=provider.provide)
                provider.end(result)
                row['turns'].append({'turn': number, 'user': turn['content'], 'result': result,
                    'elapsed_ms': (time.perf_counter() - tick) * 1000,
                    'model_requests': provider.total_models - before_models,
                    'tool_requests': provider.tool_requests - before_tools,
                    'citations': citation_check(result['content'], provider.evidence)})
                if result['status'] != 'completed':
                    break
        expected = len(scene['turns']) - (1 if fixture else 0)
        if len(row['turns']) == expected and all(t['result']['status'] == 'completed' for t in row['turns']) and not provider.violations:
            row['execution_status'] = 'completed'
    except BaseException as exc:
        row.update(execution_status='failed' if isinstance(exc, Exception) else 'interrupted', error=type(exc).__name__)
        if not isinstance(exc, Exception):
            raise
    finally:
        if log and log.exists():
            with log.open('rb') as handle:
                handle.seek(offset)
                (store.path / 'server-segment.log').write_bytes(handle.read())
        records = read_rows(store.path / 'api.jsonl') if (store.path / 'api.jsonl').exists() else []
        row.update(provider.stats(), provider_records=provider.records,
            observed_evidence=list(provider.evidence.values()), force_status=client.force_status,
            transfers=audit_transfers(read_rows(store.path / 'trace.jsonl'), records),
            elapsed_ms=(time.perf_counter() - started) * 1000, **api_statistics(records))
        row['unexecuted_turns'] = [n for n in range(2 if fixture else 1, len(scene['turns']) + 1)
                                  if n not in {t['turn'] for t in row['turns']}]
        row['conformance_status'] = 'failed' if provider.violations else (
            'passed' if row['execution_status'] == 'completed' else 'not_evaluated')
        if fixture is not None:
            row['injected_history_delivery'] = audit_injected_history(fixture, records)
        store.result(row)
        store.finish('completed' if row['execution_status'] == 'completed' else 'failed', row.get('error'))
        seal(store.path)
    return row
