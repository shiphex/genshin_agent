"""Evaluate JSON development questions offline using source-location proxies."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import platform
import re
import statistics
import sys
import time

try:
    from . import artifact_catalog, evaluate_rag_mvp
except ImportError:
    import artifact_catalog
    import evaluate_rag_mvp

LexicalIndex = evaluate_rag_mvp.LexicalIndex
PROJECT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = 'retrieval-source-location-v0'
SCHEMA_VERSION = 1
METRICS = [('来源位置 Hit', 'source_location_hit_at_k'),
           ('宏平均 Coverage', 'source_location_macro_coverage_at_k'),
           ('微平均 Coverage', 'source_location_micro_coverage_at_k')]
BINS = ['未命中 · 0%', '部分命中 · (0, 50%)', '部分命中 · [50%, 100%)',
        '全部标注位置 · 100%', '无标注 · 未计分']
LABELS = {'fact': '事实', 'causal': '因果', 'worldbuilding': '世界观', 'relationship': '关系',
          'easy': '简单', 'medium': '中等', 'hard': '困难'}


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


def percentage(value):
    return '未计分' if value is None else f'{value:.2%}'


def coverage_distribution(results):
    counts = [0] * len(BINS)
    for row in results:
        location = row['source_location']
        n, d = location['matched_locations'], location['annotated_locations']
        index = 4 if not d else 0 if not n else 3 if n == d else 1 if n * 2 < d else 2
        counts[index] += 1
    return counts


def group_metrics(results, field):
    groups = {}
    for result in results:
        groups.setdefault(result[field], []).append(result['source_location'])
    rows = []
    order = ('easy', 'medium', 'hard') if field == 'difficulty' else ('fact', 'causal', 'worldbuilding', 'relationship')
    for label, locations in sorted(groups.items(), key=lambda item: (order.index(item[0]) if item[0] in order else len(order), item[0])):
        scored = [r for r in locations if r['annotated_locations']]
        annotated = sum(r['annotated_locations'] for r in scored)
        rows.append({'label': label, 'questions': len(locations), 'scored': len(scored),
                     'hits': sum(r['matched_locations'] > 0 for r in scored),
                     'macro': sum(r['matched_locations'] / r['annotated_locations'] for r in scored) / len(scored) if scored else None,
                     'micro': sum(r['matched_locations'] for r in scored) / annotated if annotated else None})
    return rows


def _cell(value):
    return escape(str(value)).replace('|', '\\|').replace('\n', ' ')


def _seconds(value, milliseconds=False):
    if value is None:
        return '未测量'
    return f'{value * 1000:.2f} ms' if milliseconds else f'{value:.3f} s'


def _write_report(output, summary, results):
    """Write retrieval tables without requiring optional visualizations."""
    state = '执行完成' if summary['complete'] else '未完成，以下仅统计已处理题目'
    lines = ['# 检索评测 V0', '',
             f"运行：`{_cell(output.name)}` · **{state}** · {summary['processed_questions']}/{summary['expected_questions']} 题 · Top-K={summary['top_k']}。", '',
             '> 指标只表示已标注来源的位置命中，是证据获取的代理指标。字段中某个片段命中不证明论据完整召回；'
             '语义覆盖和最终答案正确性均未评测。来源标注也不穷尽等价出处。', '',
             '## 指标总览', '', '| 指标 | 结果 | 统计口径 |', '| --- | ---: | --- |']
    definitions = ['命中至少一个标注位置的题数／计分题数', '每道计分题 Coverage 的等权平均',
                   f"命中 {summary['matched_locations']}/{summary['annotated_locations']} 个逐题唯一标注位置"]
    lines.extend(f"| {label}@{summary['top_k']} | {percentage(summary[key])} | {definition} |"
                 for (label, key), definition in zip(METRICS, definitions))
    lines.extend(['', f"计分 {summary['scored_questions']} 题；无标注 {summary['unscored_questions']} 题。"
                  '未进入语料的位置保留在分母中；失败或中断结果不构成完整评测。', '',
                  '| 逐题覆盖分组 | 题数 |', '| --- | ---: |'])
    lines.extend(f'| {label} | {count} |' for label, count in zip(BINS, coverage_distribution(results)))
    for field, heading in (('type', '按题型'), ('difficulty', '按难度')):
        lines.extend(['', f'## {heading}', '', '| 分组 | 已处理／计分 | 命中题数 | Hit@K | 宏 Coverage@K | 微 Coverage@K |',
                      '| --- | ---: | ---: | ---: | ---: | ---: |'])
        for group in group_metrics(results, field):
            label = _cell(LABELS.get(group['label'], group['label']))
            hit = group['hits'] / group['scored'] if group['scored'] else None
            lines.append(f"| {label} | {group['questions']}/{group['scored']} | {group['hits']} | "
                         f"{percentage(hit)} | {percentage(group['macro'])} | {percentage(group['micro'])} |")
    timings = summary['retrieval_seconds']
    lines.extend(['', '## 耗时', '', '| 阶段／统计 | 耗时 |', '| --- | ---: |',
                  f"| 索引构建 | {_seconds(summary['index_build_seconds'])} |",
                  f"| 检索总计 | {_seconds(timings['total'])} |"])
    lines.extend(f"| 每题{label} | {_seconds(timings[key], True)} |" for label, key in (('平均', 'mean'), ('中位数', 'median'), ('最大', 'max')))
    lines.extend(['', '每题只计一次 search 调用，不含加载、匹配、写盘；不是端到端耗时或性能回退判定。', '',
                  '## 未进入语料的标注位置', '', '| 题号 | 文件 | Pointer |', '| --- | --- | --- |'])
    lines.extend(f"| {_cell(s['question_id'])} | {_cell(s['file'])} | {_cell(s['pointer'])} |" for s in summary['unmapped_locations'])
    if not summary['unmapped_locations']:
        lines.append('| 无（仅指已处理题目） | — | — |')
    identity = summary['identity']
    lines.extend(['', '## 复现与比较', '',
                  f"协议：`{summary['protocol_id']}`；题库版本：`{_cell(identity['questions']['version'])}`。", '',
                  f"题库 SHA-256：`{identity['questions']['sha256']}`。", '',
                  f"语料 SHA-256：`{identity['corpus']['sha256']}`。", '',
                  '[逐题结果](results.jsonl) · [机器可读汇总](summary.json) · [运行记录](run_manifest.json)。', '',
                  '复现按运行记录的 parameters、inputs 和 executed_source 核对。A/B 固定协议、题库与语料哈希及 Top-K，'
                  '按 question_id 对齐；有意改变的因素单列。运行编号和时间戳不参与指标比较，耗时需同等环境重复采样。'])
    with (output / 'report.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')

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
        sources = [Path(__file__).resolve(), Path(evaluate_rag_mvp.__file__).resolve(), Path(artifact_catalog.__file__).resolve()]
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
