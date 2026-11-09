"""Retrieval audits, observed agent samples, and fixed-evidence continuations."""
from copy import deepcopy
import json
from pathlib import Path

from Benchmarks.agent_story.providers import SYSTEM, SEARCH_TOOL, citation_check
from Benchmarks.agent_story.scenarios import public_turns
from Benchmarks.support.common import read_json, read_rows, write_json, encoded, file_hash
from probes.a06_diagnosis.evidence import coverage
from rag.scripts.corpus_schema import to_model_evidence
from rag.scripts.evaluate_rag_mvp import LexicalIndex
from .artifacts import new_store, seal, assert_sealed, assessment
from .preparation import load_run
from .runtime import observed_client, run_sample
from .evidence import correct_history, as_text
from .validation import assert_presentation_pair
from . import service


def actual_queries(run):
    queries = []
    for path in sorted(Path(run).glob('*/api.jsonl')):
        if path.parent.name.startswith('D-') or path.parent.name == 'preflight':
            continue
        for record in read_rows(path):
            if record.get('event') != 'response' or record.get('endpoint') != 'chat/completions':
                continue
            for choice in record['raw_response'].get('choices', []):
                for call in choice['message'].get('tool_calls') or []:
                    try:
                        query = json.loads(call['function']['arguments'])['query']
                    except (ValueError, KeyError, TypeError):
                        continue
                    queries.append({'query': query, 'turn': record['turn'], 'kind': 'actual',
                                    'origin_stage': path.parent.name})
    return queries


def retrieval(run, name):
    binding, scenes, materials = load_run(run)
    corpus = read_rows(binding['corpus']); index = LexicalIndex(corpus)
    store = new_store(Path(run) / name, 'B', parameters={'model_calls': 0, 'top_k': 5})
    try:
        queries = []
        for number, turn in enumerate(public_turns(scenes['a06']), 1):
            queries += [{'sample_id': f't{number}-user', 'turn': number, 'kind': 'user', 'query': turn['content']},
                        {'sample_id': f't{number}-oracle', 'turn': number, 'kind': 'oracle',
                         'oracle_assisted_diagnostic': True, 'query': binding['oracle_queries'][number - 1]}]
        for number, query in enumerate(actual_queries(run), 1):
            queries.append({'sample_id': f'actual-{number}', **query})
        store.manifest['planned_samples'] = [{'sample_id': q['sample_id']} for q in queries]
        store.manifest['planned_samples'] += [{'sample_id': f't{number}-direct'} for number in (1, 3)]
        for query in queries:
            hits = index.search(query['query'], 5)
            stage = query.get('origin_stage', '')
            scenario = next((s for s in scenes if s in stage), 'a06')
            anchors = materials[scenario]['mapped_anchors']
            necessary = binding['necessary_anchors'][query['turn'] - 1] if scenario == 'a06' else anchors
            store.result({**query, 'execution_status': 'completed', 'hits': hits,
                'necessary': coverage(necessary, hits), 'all_annotated': coverage(anchors, hits)})
        for number in (1, 3):
            required = {identity for anchor in binding['necessary_anchors'][number - 1] for identity in anchor['ids']}
            hits = [r for r in corpus if r['id'] in required]
            store.result({'sample_id': f't{number}-direct', 'turn': number, 'kind': 'direct_corpus_selection',
                'retrieval_result': False, 'execution_status': 'completed', 'hits': hits,
                'necessary': coverage(binding['necessary_anchors'][number - 1], hits)})
        store.finish('completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path


def select_evidence(rows, review, turn):
    for name in (f't{turn}-oracle', f't{turn}-direct'):
        verdict = review.get('queries', {}).get(name, {})
        if verdict.get('semantic_sufficiency') != 'sufficient' or not verdict.get('reason'):
            continue
        row = next((r for r in rows if r['sample_id'] == name), None)
        if row is None:
            continue
        ids = {h['id'] for h in row['hits']}
        supporting = verdict.get('supporting_ids', [])
        if not supporting or not set(supporting) <= ids:
            raise ValueError('reviewed supporting IDs must occur in the frozen hits')
        return deepcopy(row['hits']), supporting[0], name
    raise ValueError('reviewed sufficient evidence required before seeding history')


def live(run, condition, repeat, scenario='a06'):
    if repeat not in (1, 2, 3) or condition not in ('O', 'A', 'C2', 'R'):
        raise ValueError('condition/repeat outside the fixed plan')
    if condition == 'O' and repeat != 1:
        raise ValueError('O is planned once')
    if condition != 'R' and scenario != 'a06' or condition == 'R' and scenario not in ('a07', 'a10', 'a11'):
        raise ValueError('scenario outside the fixed plan')
    binding, scenes, _ = load_run(run)
    if read_json(Path(run) / 'preflight/manifest.json')['status'] != 'completed':
        raise ValueError('native tool preflight must pass before scenario execution')
    deployment = service.check(Path(run) / 'service')
    fixture, review_binding = None, {}
    if condition == 'C2':
        parent = Path(run) / f'A-r{repeat:03}'
        assert_sealed(parent)
        a_review, a_ref = assessment(parent)
        first = a_review.get('first_turn', {})
        if first.get('supported_correct') is True or 'supported_correct' not in first or not first.get('reason'):
            raise ValueError('C2 requires a reviewed failed or uncertain first answer')
        if read_rows(parent / 'results.jsonl')[0].get('force_status') != 'succeeded':
            raise ValueError('technical forced-call failure cannot enable C2')
        b_stage = Path(run) / 'B-r001'; assert_sealed(b_stage)
        b_review, b_ref = assessment(b_stage)
        hits, supporting, origin = select_evidence(read_rows(b_stage / 'results.jsonl'), b_review, 1)
        fixture = correct_history(public_turns(scenes['a06'])[0]['content'],
            [to_model_evidence(h) for h in hits], supporting, SYSTEM)
        fixture['selection'] = origin
        review_binding = {'a_assessment': a_ref, 'b_assessment': b_ref}
    name = f'R-{scenario}-r{repeat:03}' if condition == 'R' else f'{condition}-r{repeat:03}'
    store = new_store(Path(run) / name, condition, paths=[Path(run) / 'binding.json',
        Path(run) / 'effective-suite.json', Path(run) / 'materials.json'], parameters={
        'model': binding['model_config'], 'system': SYSTEM, 'tools': [SEARCH_TOOL],
        'max_steps': 8, 'top_k': 5, 'timeout': binding.get('worker_timeout', 240), 'assessment_binding': review_binding,
        'service_identity_sha256': file_hash(Path(run) / 'service/service.json'),
        'end_to_end_score': 'not_applicable' if condition == 'C2' else 'pending_review'})
    row = run_sample(store, scenes[scenario], read_rows(binding['corpus']),
                     observed_client(binding['model_config'], store), condition=condition,
                     fixture=fixture, server_log=deployment['server_log'],
                     worker_timeout=binding.get('worker_timeout', 240))
    if condition == 'A' and row['force_status'] != 'succeeded':
        raise ValueError('forced tool call failed; do not broaden budget or retry strategy')
    return store.path


def preflight(run):
    binding, _, _ = load_run(run)
    service.check(Path(run) / 'service')
    store = new_store(Path(run) / 'preflight', 'preflight', parameters={'model': binding['model_config']})
    store.manifest['planned_samples'] = [{'sample_id': 'preflight'}]
    try:
        result = observed_client(binding['model_config'], store).preflight()
        store.result({'sample_id': 'preflight', 'execution_status': 'completed', 'result': result, 'correct': None})
        store.finish('completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path


def presentation_messages(turns, first_hits, supporting, third_hits, turn):
    history = correct_history(turns[0], first_hits, supporting, SYSTEM)['messages']
    if turn == 1:
        return history[:4], [3]
    history += [{'role': 'user', 'content': turns[2]},
        {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'controlled-third', 'type': 'function',
         'function': {'name': 'search_story', 'arguments': encoded({'query': '女士 执行官 冰之女皇 效忠 温迪'})}}]},
        {'role': 'tool', 'tool_call_id': 'controlled-third',
         'content': encoded({'ok': True, 'result': {'evidence': third_hits}})}]
    return history, [3, 7]


def presentation(run):
    binding, scenes, _ = load_run(run)
    service.check(Path(run) / 'service')
    b_stage = Path(run) / 'B-r001'; assert_sealed(b_stage)
    review, review_ref = assessment(b_stage)
    rows = read_rows(b_stage / 'results.jsonl')
    first, supporting, first_origin = select_evidence(rows, review, 1)
    third, _, third_origin = select_evidence(rows, review, 3)
    first, third = [to_model_evidence(h) for h in first], [to_model_evidence(h) for h in third]
    store = new_store(Path(run) / 'D-r001', 'D', parameters={
        'model': binding['model_config'], 'b_assessment': review_ref, 'tool_choice': 'none',
        'selection': {'first': first_origin, 'third': third_origin},
        'end_to_end_score': 'not_applicable', 'system': SYSTEM, 'tools': [SEARCH_TOOL]})
    planned = [{'sample_id': f'D:t{turn}:{arm}:{repeat}', 'turn': turn, 'arm': arm, 'repeat': repeat}
               for turn in (1, 3) for repeat in (1, 2, 3) for arm in ('structured', 'text')]
    store.manifest['planned_samples'] = planned
    try:
        turns = [t['content'] for t in public_turns(scenes['a06'])]
        for turn in (1, 3):
            canonical, indices = presentation_messages(turns, first, supporting, third, turn)
            for repeat in (1, 2, 3):
                payloads = {}
                for arm in (('structured', 'text') if repeat % 2 else ('text', 'structured')):
                    service.check(Path(run) / 'service')
                    sample = f'D:t{turn}:{arm}:{repeat}'
                    messages = deepcopy(canonical)
                    if arm == 'text':
                        for index in indices:
                            wrapper = json.loads(messages[index]['content'])
                            wrapper['result']['evidence'] = [as_text(h) for h in wrapper['result']['evidence']]
                            messages[index]['content'] = encoded(wrapper)
                    def emit(event):
                        store.append('api.jsonl', {**event, 'sample_id': sample})
                    from probes.a06_diagnosis.controls import ObservedClient
                    client = ObservedClient(binding['model_config'], emit)
                    client.begin(turn)
                    row = next(deepcopy(p) for p in planned if p['sample_id'] == sample)
                    seen = first if turn == 1 else first + third
                    row['observed_evidence'] = deepcopy(seen)
                    try:
                        result = client.chat(messages, [SEARCH_TOOL], binding['model_config']['timeout'], tool_choice='none')
                        row.update(result=result, execution_status='completed' if result['finish_reason'] == 'stop'
                            and not result['message'].get('tool_calls') else 'incomplete', correct=None,
                            citations=citation_check(result['message'].get('content') or '', {h['id']: h for h in seen}))
                        payloads[arm] = result['request']['payload']
                    except Exception as exc:
                        row.update(execution_status='failed', error=type(exc).__name__, correct=None)
                    store.result(row)
                if len(payloads) == 2:
                    assert_presentation_pair(payloads['structured'], payloads['text'], indices)
                    store.append('pairs.jsonl', {'turn': turn, 'repeat': repeat, 'only_planned_content_changed': True})
        store.finish('completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path
