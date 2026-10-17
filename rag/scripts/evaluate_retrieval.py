"""Evaluate JSON development questions offline using source-location proxies."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import statistics
import sys
import time

try:
    from . import artifact_catalog, evaluate_rag_mvp, retrieval_report
except ImportError:
    import artifact_catalog
    import evaluate_rag_mvp
    import retrieval_report

LexicalIndex = evaluate_rag_mvp.LexicalIndex
PROJECT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = 'retrieval-source-location-v0'
SCHEMA_VERSION = 1


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value


def _location(file, pointer):
    _text(file, 'source file')
    parts = PurePosixPath(file).parts
    if (not parts or parts[0] != 'parsed' or len(parts) < 2 or '..' in parts
            or '\\' in file or ':' in file or PurePosixPath(file).as_posix() != file):
        raise ValueError('source file must be a relative POSIX path inside parsed/')
    if not isinstance(pointer, str) or not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        raise ValueError('source pointer must be an RFC 6901 field pointer')
    return file, pointer


def validate_inputs(document, corpus):
    if not isinstance(document, dict):
        raise ValueError('questions must be a JSON object')
    for field in ('version', 'dataset', 'source_snapshot'):
        _text(document.get(field), field)
    questions = document.get('questions')
    if not isinstance(questions, list) or not questions:
        raise ValueError('questions must be a nonempty list')
    ids = set()
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError('question must be an object')
        for field in ('id', 'question', 'type', 'difficulty'):
            _text(question.get(field), field)
        if question['id'] in ids:
            raise ValueError('duplicate question ID')
        ids.add(question['id'])
        if not isinstance(question.get('sources'), list):
            raise ValueError('sources must be a list; use [] for unlabelled questions')
        for source in question['sources']:
            if not isinstance(source, dict):
                raise ValueError('source must be an object')
            _location(source.get('file'), source.get('pointer'))
    if not corpus:
        raise ValueError('corpus must be nonempty')
    ids = set()
    for row in corpus:
        if not isinstance(row, dict):
            raise ValueError('corpus row must be an object')
        for field in ('id', 'title', 'text'):
            _text(row.get(field), field)
        if row['id'] in ids:
            raise ValueError('duplicate corpus ID')
        ids.add(row['id'])
        pointers = row.get('source_pointer')
        if not isinstance(pointers, list) or not pointers:
            raise ValueError('corpus source_pointer must be a nonempty list')
        for pointer in pointers:
            _location(row.get('source_file'), pointer)


def corpus_locations(corpus):
    return {(row['source_file'], pointer) for row in corpus for pointer in row['source_pointer']}


def score_locations(sources, retrieved, available):
    """Exact annotated field locations only; no character-span or semantic verdict."""
    ranks = {}
    for rank, row in enumerate(retrieved, 1):
        for pointer in row['source_pointer']:
            ranks.setdefault((row['source_file'], pointer), []).append({'id': row['id'], 'rank': rank})
    expected = list(dict.fromkeys((source['file'], source['pointer']) for source in sources))
    matched = sum(location in ranks for location in expected)
    return {'annotated_locations': len(expected), 'matched_locations': matched,
            'unmapped_locations': sum(location not in available for location in expected),
            'hit_at_k': int(matched > 0) if expected else None,
            'coverage_at_k': matched / len(expected) if expected else None,
            'sources': [{'file': file, 'pointer': pointer, 'in_corpus': (file, pointer) in available,
                         'matches': ranks.get((file, pointer), [])} for file, pointer in expected]}


def summarize(results, expected_questions, status, index_seconds):
    scored = [r['source_location'] for r in results if r['source_location']['annotated_locations']]
    annotated = sum(r['annotated_locations'] for r in scored)
    matched = sum(r['matched_locations'] for r in scored)
    timings = [r['retrieval_seconds'] for r in results]
    return {'schema_version': SCHEMA_VERSION, 'protocol_id': PROTOCOL_ID,
            'execution_status': status, 'complete': status == 'completed' and len(results) == expected_questions,
            'expected_questions': expected_questions, 'processed_questions': len(results),
            'scored_questions': len(scored), 'unscored_questions': len(results) - len(scored),
            'annotated_locations': annotated, 'matched_locations': matched,
            'source_location_hit_at_k': sum(r['hit_at_k'] for r in scored) / len(scored) if scored else None,
            'source_location_macro_coverage_at_k': sum(r['coverage_at_k'] for r in scored) / len(scored) if scored else None,
            'source_location_micro_coverage_at_k': matched / annotated if annotated else None,
            'unmapped_locations': [{'question_id': r['question_id'], 'file': s['file'], 'pointer': s['pointer']}
                                   for r in results for s in r['source_location']['sources'] if not s['in_corpus']],
            'index_build_seconds': index_seconds,
            'retrieval_seconds': {'total': sum(timings), 'mean': statistics.mean(timings) if timings else None,
                                  'median': statistics.median(timings) if timings else None,
                                  'max': max(timings) if timings else None},
            'model_calls': 0, 'semantic_coverage': 'not_evaluated', 'answer_correctness': 'not_evaluated'}


def _fingerprint(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def _write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def _write_report(output, summary, results):
    retrieval_report.write_report(output, summary, results)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions', type=Path, help='JSON development set; defaults to catalog story_dev')
    parser.add_argument('--corpus', type=Path, help='JSONL corpus; defaults to catalog full_corpus')
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--output-dir', type=Path, help='new retrieval output directory; allocated automatically by default')
    args = parser.parse_args(argv)
    output = None
    results = []
    expected = 0
    index_seconds = None
    parameters = None
    status, exit_code, error_type = 'failed', 1, None
    try:
        if args.top_k < 1:
            raise ValueError('top-k must be positive')
        doc = artifact_catalog.load_catalog(PROJECT)
        questions_path = (args.questions or artifact_catalog.dataset_path(PROJECT, 'story_dev')).resolve()
        corpus_path = (args.corpus or artifact_catalog.dataset_path(PROJECT, 'full_corpus')).resolve()
        verified = {}
        fingerprints = {path: _fingerprint(path) for path in (questions_path, corpus_path)}
        for path in (questions_path, corpus_path):
            relative = path.relative_to(PROJECT).as_posix() if path.is_relative_to(PROJECT) else None
            verified[path] = relative in doc['files']
            if verified[path]:
                artifact_catalog.verify_files(PROJECT, [relative])
        document = json.loads(questions_path.read_text(encoding='utf-8-sig'))
        corpus = evaluate_rag_mvp.load_jsonl(corpus_path)
        if any(_fingerprint(path) != info for path, info in fingerprints.items()):
            raise ValueError('input changed while being loaded')
        validate_inputs(document, corpus)
        expected = len(document['questions'])
        if questions_path == artifact_catalog.dataset_path(PROJECT, 'story_dev'):
            meta = doc['datasets']['story_dev']
            if (document['version'] != meta['version'] or expected != meta['questions']
                    or document['source_snapshot'] != doc['raw_root']):
                raise ValueError('question metadata differs from catalog')
        if corpus_path == artifact_catalog.dataset_path(PROJECT, 'full_corpus') and len(corpus) != doc['datasets']['full_corpus']['rows']:
            raise ValueError('corpus row count differs from catalog')
        sources = [Path(__file__).resolve(), Path(evaluate_rag_mvp.__file__).resolve(), Path(artifact_catalog.__file__).resolve(), Path(retrieval_report.__file__).resolve()]
        identity = {'questions': {**fingerprints[questions_path], 'path': str(questions_path),
                                 'dataset': document['dataset'], 'version': document['version'],
                                 'source_snapshot': document['source_snapshot'], 'rows': expected,
                                 'baseline_verified': verified[questions_path]},
                    'corpus': {**fingerprints[corpus_path], 'path': str(corpus_path), 'rows': len(corpus),
                               'baseline_verified': verified[corpus_path],
                               'source_snapshot': doc['source_snapshot'] if corpus_path == artifact_catalog.dataset_path(PROJECT, 'full_corpus') else None},
                    'retriever': {'class': 'evaluate_rag_mvp.LexicalIndex', **_fingerprint(sources[1])}}
        parameters = {'protocol_id': PROTOCOL_ID, 'schema_version': SCHEMA_VERSION, 'top_k': args.top_k,
                      'query_field': 'question', 'question_order': 'input', 'index_builds': 1,
                      'timing_boundary': 'search call only; one sequential sample per question',
                      'identity': identity, 'runtime': {'python': platform.python_version(),
                          'implementation': platform.python_implementation(), 'platform': platform.platform(),
                          'machine': platform.machine(), 'processor': platform.processor()}}
        output = artifact_catalog.reserve_output(PROJECT, 'retrieval', args.output_dir)
        artifact_catalog.seal_inputs(PROJECT, output,
                                    [questions_path, corpus_path, PROJECT / 'rag/catalog.json', *sources], parameters)
        manifest = json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))
        for entry, path in zip(manifest['inputs'][:2], (questions_path, corpus_path)):
            if entry['sha256'] != fingerprints[path]['sha256']:
                raise ValueError('input changed before sealing')
        available = corpus_locations(corpus)
        index = LexicalIndex(corpus)
        index_seconds = index.build_seconds
        with (output / 'results.jsonl').open('x', encoding='utf-8', newline='\n') as stream:
            for number, question in enumerate(document['questions'], 1):
                started = time.perf_counter()
                retrieved = index.search(question['question'], args.top_k)
                elapsed = time.perf_counter() - started
                result = {'schema_version': SCHEMA_VERSION, 'protocol_id': PROTOCOL_ID,
                          'question_id': question['id'], 'question': question['question'],
                          'type': question['type'], 'difficulty': question['difficulty'],
                          'execution_status': 'completed', 'retrieval_seconds': elapsed,
                          'retrieved': retrieved, 'source_location': score_locations(question['sources'], retrieved, available)}
                stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
                stream.flush()
                results.append(result)
                print(f"[{number}/{expected}] {question['id']}", file=sys.stderr, flush=True)
        status, exit_code = 'completed', 0
    except KeyboardInterrupt:
        status, exit_code, error_type = 'interrupted', 130, 'KeyboardInterrupt'
    except Exception as error:
        error_type = type(error).__name__
        print(f'Retrieval evaluation failed ({error_type}): {error}', file=sys.stderr)
    finally:
        if output is not None:
            try:
                summary = summarize(results, expected, status, index_seconds)
                summary.update(top_k=args.top_k, identity=parameters['identity'])
                _write_json(output / 'summary.json', summary)
                _write_report(output, summary, results)
                metadata = {'processed_questions': len(results), 'expected_questions': expected,
                            'error_type': error_type,
                            'artifacts': {p.name: _fingerprint(p) for p in output.iterdir() if p.is_file()
                                          and p.name != 'run_manifest.json'}}
                artifact_catalog.finish_output(PROJECT, output, status, metadata)
                print(json.dumps({'output_dir': str(output), **summary}, ensure_ascii=False))
            except Exception as error:
                print(f'Could not finalize run ({type(error).__name__}); inspect {output}', file=sys.stderr)
                manifest = json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))
                if manifest['execution_status'] == 'running':
                    artifact_catalog.finish_output(PROJECT, output, 'failed', {'error_type': type(error).__name__})
                exit_code = 1
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
