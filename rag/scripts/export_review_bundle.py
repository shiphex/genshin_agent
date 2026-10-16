"""Export approved review views and verified offline ZIPs. Standard library only.

No model calls, corpus rebuilding, upload, or writes to historical inputs.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

try:
    from rag.scripts import artifact_catalog
except ModuleNotFoundError:
    import artifact_catalog

ROOT = Path(__file__).resolve().parents[2]
FULL_RECORD = artifact_catalog.run_record(ROOT, 'model_comparison', 'r001')
DIAG_RECORD = artifact_catalog.run_record(ROOT, 'generation_diagnosis', 'r001')
FULL_RUN = FULL_RECORD['artifacts']
DIAG_RUN = DIAG_RECORD['artifacts']
LEGACY_FULL_ID = FULL_RECORD['legacy_id']
LEGACY_DIAG_ID = DIAG_RECORD['legacy_id']
CORPUS = FULL_RECORD.get('corpus_path', artifact_catalog.dataset_path(ROOT, 'full_corpus').relative_to(ROOT).as_posix())
RAW = 'data/raw/genshin_wiki_data_20260605'
REPORTS = 'rag/reports'
VERSION = 'review-20261010-v3'
EXCERPTS = 'rag/reports/inputs/excerpts_v3.json'
CATALOG = artifact_catalog.load_catalog(ROOT)
DATA_ROOTS = (FULL_RUN, DIAG_RUN,
              str(Path(CATALOG['datasets']['sample_corpus']['path']).parent).replace('\\', '/'),
              str(Path(CORPUS).parent).replace('\\', '/'),
              str(Path(CATALOG['baselines']['wiki_snapshot/v1']['path']).parent).replace('\\', '/'),
              *(CATALOG['runs'][key]['artifacts'] for key in ('full_retrieval/r001', 'sample_retrieval/r001',
                 'sample_model_comparison/r001', 'sample_model_comparison/r002')))


def data_location(root, relative):
    if not relative.startswith('rag/data/'):
        return root / relative
    if (root / 'rag/catalog.json').exists():
        return artifact_catalog.resolve_data_path(root, relative)
    candidate = root / relative
    if candidate.exists():
        return candidate
    # Older frozen packages contain the legacy coordinates, not the new catalog.
    for old, new in sorted(CATALOG.get('legacy_paths', {}).items(), key=lambda pair: -len(pair[1])):
        if relative == new or relative.startswith(new + '/'):
            historical = root / (old + relative[len(new):])
            if historical.exists():
                return historical
    return candidate


def executed_input_bytes(root, relative, digest):
    safe_name(relative)
    catalog = artifact_catalog.load_catalog(root) if (root / 'rag/catalog.json').exists() else {}
    try:
        if relative.startswith('rag/data/') and catalog:
            data = artifact_catalog.read_data_bytes(root, relative)
        else:
            actual = catalog.get('legacy_input_paths', {}).get(relative, relative)
            data = (root / actual).read_bytes()
        if sha(data) == digest:
            return data
    except FileNotFoundError:
        pass
    # Live Git inputs can change later; existing sealed ZIPs retain exact executed bytes.
    for release in catalog.get('releases', {}).values():
        for entry in release['files']:
            if not entry['path'].endswith('.zip'):
                continue
            path = root / entry['path']
            if sha(path.read_bytes()) != entry['sha256']:
                raise ValueError('Changed frozen release ZIP')
            with zipfile.ZipFile(path) as archive:
                member = 'publication/historical_inputs/' + relative
                if member in archive.namelist():
                    data = archive.read(member)
                    if sha(data) == digest:
                        return data
    raise ValueError('Executed input unavailable or changed: ' + relative)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_utf8(path, json_text(value) + '\n')


def write_utf8(path, text):
    # Deterministic bytes match Git's LF blobs on Windows and Linux alike.
    path.write_bytes(text.encode('utf-8'))


def block(text, kind):
    # A longer fence preserves embedded Markdown and trailing newlines exactly.
    longest = max((len(s) for s in re.findall(r'`+', text)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}{kind}\n{text}\n{fence}\n'


def extract_blocks(markdown, kind):
    return [m[1] for m in re.findall(r'(?m)^(`{3,})' + re.escape(kind) + r'\n([\s\S]*?)\n\1\n', markdown)]


def answer_block(answer):
    metadata = {k: v for k, v in answer.items() if k != 'text'}
    return block(json_text(metadata), 'json') + '\n' + block(answer.get('text', ''), 'answer')


def evidence_block(rows):
    out = []
    for row in rows:
        meta = {k: row[k] for k in ('id', 'title', 'source_kind', 'source_file',
                                    'source_pointer', 'source_spans', 'score') if k in row}
        safe_name(meta['source_file'])
        out += [f"### {row['id']}\n", block(json_text(meta), 'json'), block(row['text'], 'evidence')]
    return '\n'.join(out)


def safe_name(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError(f'Unsafe relative path: {name}')
    devices = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    for part in p.parts:
        if part.endswith((' ', '.')) or part.split('.')[0].upper() in devices or re.search(r'[<>"|?*\x00-\x1f]', part):
            raise ValueError('Unsafe Windows path component: ' + name)
    return p


def data_files(root, full=False):
    roots = (RAW,) + DATA_ROOTS if full else (FULL_RUN, DIAG_RUN)
    files = []
    for rel in roots:
        for path in sorted(data_location(root, rel).rglob('*')):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in {'.json', '.jsonl', '.md', '.py', '.html', '.txt'}:
                if '__pycache__' not in path.parts and not any(s.startswith('.') for s in path.relative_to(root).parts):
                    files.append(path)
    if full and (root / 'rag/catalog.json').exists():
        for record in (FULL_RECORD, DIAG_RECORD):
            if record.get('process_archive'):
                files.append(root / record['process_archive'])
    return files


def inventory(root, paths):
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
             'sha256': sha(p.read_bytes())} for p in sorted(paths)]


def sources(root):
    a = {batch: read_jsonl(data_location(root, FULL_RUN) / batch / 'results.jsonl') for batch in ('regression', 'independent')}
    b = read_jsonl(data_location(root, DIAG_RUN) / 'model/results.jsonl')
    trials = read_json(data_location(root, DIAG_RUN) / 'model/trials.json')
    return a, b, trials


def checked_excerpt(text, selection):
    start, end = selection['start'], selection['end']
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ValueError('Invalid excerpt coordinates')
    quote = text[start:end]
    if sha(quote.encode('utf-8')) != selection['sha256']:
        raise ValueError('Excerpt no longer matches original text')
    return quote


def validate_compact_matrix(calls, diagnosis=False):
    expected = {(c, s) for c in ('R0', 'C0', 'R1', 'C1')
                for s in ((42,) if c.endswith('0') else (42, 43, 44))} if diagnosis else {('baseline', 42), ('rag', 42)}
    keys = [(c['condition'], c['seed']) for c in calls]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError('Missing, duplicate or unexpected condition/seed')


def validate_reference(ref, row):
    if any(ref[k] != row[r] for k, r in (('source_id', 'id'), ('source_file', 'source_file'), ('source_kind', 'source_kind'))):
        raise ValueError('Review reference provenance mismatch')
    if not any(p == ref['pointer'] and s['start'] < ref['end'] and ref['start'] < s['end']
               for p, s in zip(row['source_pointer'], row['source_spans'])):
        raise ValueError('Review reference pointer/span mismatch')


def validate_speaker(ref, parent):
    actual = '未标注；按来源字段核查'
    if isinstance(parent, dict):
        for key in ('说话者', '角色', '说话人', '人物', 'speaker'):
            if key in parent and isinstance(parent[key], str):
                actual = parent[key] or actual
                break
    if ref['speaker'] != actual:
        raise ValueError('Review speaker label disagrees with original parent record')


def render_compact_case(qid, question, calls, references, coverage=None, access_link='../../data_access.md'):
    lines = [f'# {qid}：{question}', '', f'[实验概要与参数](../summary.md) · [完整记录获取]({access_link})', '',
             '这是关键摘录与原文初审，不是完整回答／实际输入上下文。所有结果待用户逐题验收；ok只表示调用完成。', '']
    if coverage is not None:
        total = coverage.get('total_groups', 0)
        lines += [f"检索：Top5覆盖标注证据组 {coverage.get('covered_groups', 0)}/{total}。参考不穷尽；空组不计成功。", '']
    lines += ['| 条件／seed | 调用状态／结束原因 | 引用格式与ID审计 | 主结论初审 |', '|---|---|---|---|']
    for call in calls:
        answer = call['answer']
        audit = answer.get('citation_audit', {})
        ids = ', '.join(audit.get('unknown_ids', [])) or '无'
        citation = f"合规格式：{'有' if audit.get('has_citations') else '无'}；未知ID：{ids}"
        verdict = call['review'].get('core_verdict', '见下文；未统一评分')
        lines.append(f"| {call['condition']}／{call['seed']} | {answer.get('status')}／{answer.get('finish_reason')} | {citation} | {verdict} |")
    lines += ['', '引用ID有效不保证内容支持结论；语义与说话者归因见下方初审。', '', '## 关键原句与诊断', '']
    for call in calls:
        lines += [f"### {call['condition']} · seed {call['seed']}", '', call['review']['notes'], '']
        if call['review'].get('unsupported_extras') is not None:
            lines += [f"初审记录有无依据补充：{'有' if call['review']['unsupported_extras'] else '未发现'}。", '']
        excerpts = call['excerpt'] if isinstance(call['excerpt'], list) else [call['excerpt']]
        if not 1 <= len(excerpts) <= 2:
            raise ValueError('Select one or two excerpts per answer')
        for selection in excerpts:
            lines.append(block(checked_excerpt(call['answer']['text'], selection), 'excerpt').rstrip('\n'))
            lines.append('')
    lines += ['## 复核原文摘录', '', '仅展示核查所需的局部原字段；不表示这些片段均完整进入了模型上下文。上下文与检索列表见资料包。', '']
    if not references:
        lines += ['当前未选择可定位的直接原文；不据此推断游戏没有答案。', '']
    for i, ref in enumerate(references, 1):
        lines += [f"**E{i} · {ref['source_id']} · {ref['source_kind']}**", '',
                  f"来源：{ref['source_file']}；Pointer：{ref['pointer']}；字符范围：[{ref['start']},{ref['end']})；说话者／来源行：{ref.get('speaker', '未标注')}。", '',
                  block(ref['quote'], 'source-excerpt').rstrip('\n'), '']
    lines += ['## 待核验', '', '初审未穷尽所有延伸结论，也不是用户验收。资料不足、原文歧义及替代来源需要另查；人物判断、传说和Wiki编纂不能自动当作确定事实。诊断题的人工原文仍可能含解锁元数据与旁白。']
    return '\n'.join(lines) + '\n'


def report_case_path(root, legacy_id, qid):
    safe_name(qid + '.md')
    if (root / 'rag/catalog.json').exists():
        return root / artifact_catalog.report_directory(root, legacy_id) / 'cases' / (qid + '.md')
    # Frozen packages precede the catalog and retain their original layout.
    if legacy_id not in {LEGACY_FULL_ID, LEGACY_DIAG_ID}:
        raise ValueError('Unknown historical report')
    return root / REPORTS / legacy_id / 'cases' / (qid + '.md')


def excerpt_path(root):
    if (root / 'rag/catalog.json').exists():
        return root / EXCERPTS
    return root / 'rag/experiments/publication_review_v3/excerpts.json'


def render_case_at(root, path, case):
    access_link = os.path.relpath(root / REPORTS / 'data_access.md', path.parent).replace(os.sep, '/')
    return render_compact_case(case['question_id'], case['question'], case['calls'], case['references'], case['coverage'], access_link)


def compact_cases(root):
    a, b, trials = sources(root)
    initial = read_json(data_location(root, FULL_RUN) / 'preliminary_review.json')
    review = read_json(data_location(root, DIAG_RUN) / 'source_review.json')['reviews']
    inputs = read_json(excerpt_path(root))
    available = {}
    evidence = {}
    for batch, results in a.items():
        for row in results:
            key = (LEGACY_FULL_ID, row['question_id'])
            calls = []
            for condition, answer in row['answers'].items():
                calls.append({'condition': condition, 'seed': 42, 'answer': answer,
                              'review': {'notes': initial[batch][row['question_id']][condition]}})
            available[key] = {'question': row['question'], 'calls': calls, 'coverage': row['evidence_coverage'],
                              'evidence_ids': [e['id'] for e in row['retrieved']]}
            evidence.update({e['id']: e for e in row['retrieved']})
    trial_map = {(t['question_id'], t['condition'], t['seed']): t for t in trials}
    requests = read_jsonl(data_location(root, DIAG_RUN) / 'model/requests.jsonl')
    request_map = {(r['question_id'], r['condition'], r['seed']): r['payload'] for r in requests}
    if len(b) != 48 or len(trial_map) != 48 or len(request_map) != 48:
        raise ValueError('Diagnosis request/trial matrix incomplete')
    for row in b:
        key = (LEGACY_DIAG_ID, row['question_id'])
        trial_key = (row['question_id'], row['condition'], row['seed'])
        trial, request = trial_map[trial_key], request_map[trial_key]
        if trial['messages'] != request['messages'] or trial['evidence_ids'] != row['evidence_ids']:
            raise ValueError('Actual request/context mismatch')
        if any(request.get(k) != v or trial['generation'].get(k) != v for k, v in row['generation'].items()):
            raise ValueError('Actual generation parameter mismatch')
        case = available.setdefault(key, {'question': row['question'], 'calls': [], 'evidence_ids': [], 'coverage': None})
        case['calls'].append({'condition': row['condition'], 'seed': row['seed'], 'answer': row['answer'],
                             'review': review[':'.join(map(str, trial_key))]})
        case['evidence_ids'].extend(e['id'] for e in trial['evidence'])
        evidence.update({e['id']: e for e in trial['evidence']})
    keys = [(c['experiment_id'], c['question_id']) for c in inputs['cases']]
    if len(keys) != 30 or len(set(keys)) != 30 or set(keys) != set(available):
        raise ValueError('Compact question inventory mismatch')
    slice_path = root / 'publication/selected_source_fields.jsonl'
    field_slices = {(r['source_file'], r['pointer']): r for r in read_jsonl(slice_path)} if slice_path.exists() else {}
    documents = {}
    if (data_location(root, CORPUS)).exists():
        reference_rows = {r['id']: r for r in read_jsonl(data_location(root, CORPUS))}
    elif (root / 'publication/selected_evidence_records.jsonl').exists():
        reference_rows = {r['id']: r for r in read_jsonl(root / 'publication/selected_evidence_records.jsonl')}
    else:
        raise ValueError('Missing frozen review provenance records')
    cases = []
    for selected in inputs['cases']:
        key = (selected['experiment_id'], selected['question_id'])
        case = available[key]
        validate_compact_matrix(selected['calls'], diagnosis=key[0].startswith('generation_'))
        validate_compact_matrix(case['calls'], diagnosis=key[0].startswith('generation_'))
        selections = {(c['condition'], c['seed']): c for c in selected['calls']}
        for call in case['calls']:
            selection = selections[(call['condition'], call['seed'])]
            if sha(call['answer']['text'].encode('utf-8')) != selection['answer_sha256']:
                raise ValueError('Original answer fingerprint changed')
            call['excerpt'] = selection['excerpts']
            for excerpt in call['excerpt']:
                checked_excerpt(call['answer']['text'], excerpt)
        references = []
        for ref in selected['references']:
            safe_name(ref['source_file'])
            if ref['source_id'] not in reference_rows:
                raise ValueError('Review evidence ID missing from frozen corpus records')
            validate_reference(ref, reference_rows[ref['source_id']])
            source_path = root / RAW / ref['source_file']
            if source_path.exists():
                if ref['source_file'] not in documents:
                    documents[ref['source_file']] = read_json(source_path)
                if sha(source_path.read_bytes()) != ref['source_sha256']:
                    raise ValueError('Original source fingerprint changed')
                field = pointer_get(documents[ref['source_file']], ref['pointer'])
                parent = pointer_get(documents[ref['source_file']], ref['pointer'].rsplit('/', 1)[0]) if '/' in ref['pointer'][1:] else None
            else:
                preserved = field_slices.get((ref['source_file'], ref['pointer']))
                if preserved is None or preserved['source_sha256'] != ref['source_sha256']:
                    raise ValueError('Focused package missing selected raw source')
                field = preserved['raw_field']
                parent = preserved.get('parent_context')
            validate_speaker(ref, parent)
            verified = dict(ref, quote=checked_excerpt(field, ref))
            references.append(verified)
        cases.append(dict(case, experiment_id=key[0], question_id=key[1], references=references))
    return cases, evidence


def export_views(root):
    cases, evidence = compact_cases(root)
    entries = []
    for case in cases:
        path = report_case_path(root, case['experiment_id'], case['question_id'])
        path.parent.mkdir(parents=True, exist_ok=True)
        write_utf8(path, render_case_at(root, path, case))
        identity = artifact_catalog.resolve_run(root, case['experiment_id'])
        entries.append({'path': path.relative_to(root).as_posix(), 'question_id': case['question_id'],
            'experiment_id': identity['experiment_id'], 'run_id': identity['run_id'], 'legacy_id': case['experiment_id'],
            'answers': len(case['calls']), 'evidence_ids': sorted(set(case['evidence_ids'])),
            'calls': [{'condition': c['condition'], 'seed': c['seed'],
                       'answer_sha256': sha(c['answer']['text'].encode('utf-8')),
                       'status': c['answer'].get('status'), 'finish_reason': c['answer'].get('finish_reason')}
                      for c in case['calls']]})
    source_paths = [data_location(root, FULL_RUN) / p for p in ('run_manifest.json', 'experiment_summary.json', 'preliminary_review.json',
        'user_feedback.json', 'sealed_inputs.json', 'regression/results.jsonl', 'independent/results.jsonl')]
    source_paths += [data_location(root, DIAG_RUN) / p for p in ('diagnosis_summary.json', 'source_review.json', 'model/results.jsonl',
        'model/requests.jsonl', 'model/trials.json', 'model/sealed_inputs.json', 'runner_executed.py', 'post_run_fix_manifest.json')]
    source_paths.append(root / EXCERPTS)
    old = read_json(root / REPORTS / 'manifest.json')
    experiments = []
    for experiment in old['experiments']:
        legacy = experiment.get('legacy_id', experiment['id'])
        record = artifact_catalog.resolve_run(root, legacy)
        experiments.append(dict(experiment, id=record['experiment_id'], run_id=record['run_id'], legacy_id=legacy))
    manifest = {'schema_version': 3, 'view': 'curated_excerpts', 'bundle_id': VERSION, 'package_version': 3,
        'source_commit': None, 'source_commit_note': 'ZIP内清单固定重写后的源码版本；后续索引独立登记。',
        'availability': 'pending_upload', 'github_url': None, 'drive_urls': {'focused': None, 'full': None},
        'corpus': old['corpus'], 'experiments': experiments,
        'sources': inventory(root, source_paths), 'cases': entries,
        'published_files': inventory(root, list((root / REPORTS).rglob('*.md'))),
        'acceptance': 'preliminary_pending_user_acceptance'}
    write_utf8(root / REPORTS / 'manifest.json', json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    return evidence, [ref for case in cases for ref in case['references']]


def pointer_get(doc, pointer):
    value = doc
    for token in pointer.lstrip('/').split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def historical_relative(path):
    known = ('rag/experiments/generation_diagnosis/cases.jsonl',
             'rag/experiments/generation_diagnosis/generation_profiles.json',
             CORPUS, DIAG_RUN + '/local_api.json',
             'rag/data/full/genshin_wiki_data_20260605/corpus.jsonl',
             DIAG_RECORD.get('legacy_artifacts', DIAG_RUN) + '/local_api.json')
    normalized = str(path).replace('\\', '/')
    matches = [rel for rel in set(known) if normalized == rel or normalized.endswith('/' + rel)]
    if len(matches) != 1:
        raise ValueError('Unknown historical input mapping: ' + str(path))
    return matches[0]


def focused_slices(root, evidence, anchors):
    cache, fields = {}, {}
    for row in evidence.values():
        for pointer, span in zip(row['source_pointer'], row['source_spans']):
            fields[(row['source_file'], pointer, span['start'], span['end'])] = row['id']
    for a in anchors:
        fields[(a['source_file'], a['source_pointer'], a['start'], a['end'])] = 'reference_anchor'
    records = []
    for (file, pointer, start, end), eid in sorted(fields.items()):
        safe_name(file)
        path = root / RAW / file
        if file not in cache:
            cache[file] = read_json(path)
        value = pointer_get(cache[file], pointer)
        if not isinstance(value, str) or not 0 <= start <= end <= len(value):
            raise ValueError('Invalid field span: ' + file + pointer)
        parent = pointer_get(cache[file], pointer.rsplit('/', 1)[0]) if '/' in pointer[1:] else None
        records.append({'evidence_id': eid, 'source_file': file, 'source_sha256': sha(path.read_bytes()),
            'pointer': pointer, 'start': start, 'end': end, 'raw_slice': value[start:end],
            'raw_field': value, 'parent_context': parent if isinstance(parent, dict) else None})
    return records


def verify_views(root):
    manifest = read_json(root / REPORTS / 'manifest.json')
    cases, evidence = compact_cases(root)
    expected_paths = set()
    answers = 0
    total_bytes = 0
    for case in cases:
        rel = report_case_path(root, case['experiment_id'], case['question_id']).relative_to(root).as_posix()
        expected_paths.add(rel)
        expected = render_case_at(root, root / rel, case)
        if (root / rel).read_bytes() != expected.encode('utf-8'):
            raise ValueError('Changed compact view, excerpt or answer metadata: ' + rel)
        entry = next((c for c in manifest['cases'] if c['path'] == rel), None)
        if entry is None or entry['answers'] != len(case['calls']):
            raise ValueError('Missing compact manifest entry')
        if (root / 'rag/catalog.json').exists():
            identity = artifact_catalog.resolve_run(root, case['experiment_id'])
            if (entry.get('experiment_id'), entry.get('run_id'), entry.get('legacy_id')) != (identity['experiment_id'], identity['run_id'], case['experiment_id']):
                raise ValueError('Manifest run identity mismatch')
        call_records = [{'condition': c['condition'], 'seed': c['seed'],
                         'answer_sha256': sha(c['answer']['text'].encode('utf-8')),
                         'status': c['answer'].get('status'), 'finish_reason': c['answer'].get('finish_reason')}
                        for c in case['calls']]
        if entry['calls'] != call_records or entry['evidence_ids'] != sorted(set(case['evidence_ids'])):
            raise ValueError('Manifest call/context fingerprint mismatch')
        answers += len(case['calls'])
        total_bytes += (root / rel).stat().st_size
    if {c['path'] for c in manifest['cases']} != expected_paths or len(manifest['cases']) != 30:
        raise ValueError('Manifest case inventory mismatch')
    actual_paths = {p.relative_to(root).as_posix() for p in (root / REPORTS).rglob('cases/*.md')}
    if actual_paths != expected_paths or answers != 96 or total_bytes > 300_000:
        raise ValueError('Unexpected cases, calls or compact page size')
    for entry in manifest['sources'] + manifest['published_files']:
        if sha((root / entry['path']).read_bytes()) != entry['sha256']:
            raise ValueError('Changed publication input/file: ' + entry['path'])
    return {'cases': len(cases), 'answers_accounted_for': answers, 'exact_excerpts_verified': answers,
            'case_bytes': total_bytes, 'view': 'curated_excerpts'}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def verify_archive(path, extract_to=None):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        for info in infos:
            safe_name(info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP symlink forbidden')
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError('Duplicate ZIP entries')
        if 'bundle_manifest.json' not in names:
            raise ValueError('Missing bundle manifest')
        manifest = json.loads(z.read('bundle_manifest.json'))
        expected = [e['path'] for e in manifest['files']]
        if len(set(expected)) != len(expected) or set(names) != set(expected) | {'bundle_manifest.json'}:
            raise ValueError('ZIP inventory mismatch')
        for entry in manifest['files']:
            data = z.read(entry['path'])
            if sha(data) != entry['sha256'] or len(data) != entry['bytes']:
                raise ValueError('ZIP hash/size mismatch: ' + entry['path'])
        if extract_to is not None:
            extract_to = Path(extract_to).resolve()
            if extract_to.exists():
                raise ValueError('Extraction requires a new directory')
            for name in names:
                target = (extract_to / name).resolve()
                if not target.is_relative_to(extract_to):
                    raise ValueError('Extraction outside destination')
            extract_to.mkdir(parents=True)
            z.extractall(extract_to)
            if manifest.get('kind') == 'full':
                corpus = read_jsonl(data_location(extract_to, CORPUS))
                if len(corpus) != manifest['corpus']['rows']:
                    raise ValueError('Restored corpus row count')
                # Restore source pointers using the new root, without replaying old absolute paths.
                for row in corpus[::997]:
                    doc = read_json(extract_to / RAW / row['source_file'])
                    for pointer, span in zip(row['source_pointer'], row['source_spans']):
                        value = pointer_get(doc, pointer)
                        if not isinstance(value, str) or not 0 <= span['start'] <= span['end'] <= len(value):
                            raise ValueError('Restored source coordinate invalid')
            slices_path = extract_to / 'publication/selected_source_fields.jsonl'
            if slices_path.exists():
                for row in read_jsonl(slices_path):
                    if row['raw_field'][row['start']:row['end']] != row['raw_slice']:
                        raise ValueError('Focused source slice corrupt')
            if (extract_to / REPORTS / 'manifest.json').exists():
                verify_views(extract_to)
        return {'kind': manifest.get('kind'), 'files': len(expected), 'sha256': sha(path.read_bytes()),
                'bundle_id': manifest.get('bundle_id'), 'source_commit': manifest.get('source_commit')}


def validate_bundle_output(root, output):
    resolved = output.resolve()
    if output.exists():
        raise ValueError('Bundle output must be new; keep previous publications')
    publication_root = (root / 'rag/data/releases').resolve()
    if resolved == publication_root or not resolved.is_relative_to(publication_root):
        raise ValueError('Local bundles must be under ignored rag/data/releases')
    if (root / 'rag/catalog.json').exists():
        artifact_catalog.assert_writable_output(root, output)
    for rel in DATA_ROOTS:
        protected = (root / rel).resolve()
        if resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
            raise ValueError('Bundle output overlaps historical data')


def build_bundles(root, output):
    validate_bundle_output(root, output)
    status = git(root, 'status', '--porcelain').decode('utf-8')
    if status.strip():
        raise ValueError('Pin verified source commit first; working tree must be clean')
    verify_views(root)
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    paths = git(root, 'ls-tree', '-r', '--name-only', 'HEAD').decode('utf-8').splitlines()
    code = {}
    for rel in paths:
        safe_name(rel)
        if not (rel in {'.gitignore', '.gitattributes', 'AGENTS.md', 'README.md', 'context.md', '.agents/skills/genshin-dev-questions/SKILL.md'} or rel.startswith(('rag/scripts/', 'rag/tests/', 'rag/experiments/', 'rag/reports/', 'rag/config/', 'rag/docs/', 'rag/eval/')) or rel in {'rag/README.md', 'rag/context.md', 'rag/catalog.json'}):
            raise ValueError('Unapproved source file: ' + rel)
        code[rel] = git(root, 'show', 'HEAD:' + rel)
    # Views are already verified; gather original rows without regenerating committed files.
    a, b, trials = sources(root)
    corpus = {r['id']: r for r in read_jsonl(data_location(root, CORPUS))}
    manifest = read_json(root / REPORTS / 'manifest.json')
    evidence = {eid: corpus[eid] for c in manifest['cases'] for eid in c['evidence_ids']}
    initial = read_json(data_location(root, FULL_RUN) / 'preliminary_review.json')
    for batch, rs in a.items():
        for r in rs:
            for eid in initial[batch][r['question_id']].get('source_ids', []):
                if eid in corpus:
                    evidence[eid] = corpus[eid]
            for group in r.get('expected_evidence', []):
                for eid in group:
                    if eid in corpus:
                        evidence[eid] = corpus[eid]
    anchors = [v for rs in a.values() for r in rs for group in r.get('expected_source_evidence', []) for v in group]
    inputs = read_json(root / EXCERPTS)
    anchors += [dict(ref, source_pointer=ref['pointer']) for case in inputs['cases'] for ref in case['references']]
    evidence.update({ref['source_id']: corpus[ref['source_id']] for case in inputs['cases'] for ref in case['references']})
    slices = focused_slices(root, evidence, anchors)
    sealed = read_json(data_location(root, DIAG_RUN) / 'model/sealed_inputs.json')
    output.mkdir(parents=True)
    results = []
    for kind in ('focused', 'full'):
        members = dict(code)
        for p in data_files(root, full=kind == 'full'):
            members[p.relative_to(root).as_posix()] = p.read_bytes()
        members['publication/selected_source_fields.jsonl'] = ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in slices).encode('utf-8')
        members['publication/selected_evidence_records.jsonl'] = ''.join(json.dumps(x, ensure_ascii=False) + '\n' for _, x in sorted(evidence.items())).encode('utf-8')
        historical_inputs = []
        # Git normalizes text EOLs. Archive byte-exact small executed inputs separately,
        # so sealed input hashes remain checkable without confusing them with the Git tree.
        input_specs = [(historical_relative(path), digest)
                       for path, digest in sealed['input_manifest']['files'].items()
                       if not historical_relative(path).endswith('/corpus.jsonl')]
        old_manifest = read_json(data_location(root, FULL_RUN) / 'run_manifest.json')
        input_specs.append((old_manifest['actual_regression_input']['path'], old_manifest['actual_regression_input']['sha256']))
        for rel, digest in sorted(set(input_specs)):
            safe_name(rel)
            data = executed_input_bytes(root, rel, digest)
            if sha(data) != digest:
                raise ValueError('Executed input changed: ' + rel)
            archive_path = 'publication/historical_inputs/' + rel
            members[archive_path] = data
            historical_inputs.append({'original_relative_path': rel, 'archive_path': archive_path, 'sha256': digest})
        members['publication/README.md'] = (
            '# 离线分析资料包\n\n'
            f'版本：{VERSION}；源码 commit：{commit}；包类型：{kind}。\n\n'
            '下载后先使用 export_review_bundle.py verify 校验，再解压至新目录。ZIP 内路径相对项目根。\n'
            '历史封存记录含旧机器绝对路径，原件保持原样；按相同相对后缀在新目录定位，不执行旧绝对命令。\n'
            'focused 不包含完整快照或全量语料，用 selected_source_fields.jsonl 检查原字段及说话者。\n'
            'full 包可直接读取冻结语料，无需重建；运行说明见 rag/README.md。\n'
            'Python 3.11 与 uv 需另备；模型权重、模型服务、uv 缓存不包含，离线 uv 运行需本机已有解释器。\n'
            '历史执行 runner 位于 rag/data/generation_diagnosis/20261010_145424/runner_executed.py；\n'
            '当前 runner 含实验后的正文校验修正，不能据此改写旧请求。原文初审不等于用户验收。\n'
            'Git文本换行可与调用时字节不同；publication/historical_inputs保留小型执行输入原始字节，映射见清单。\n'
        ).encode('utf-8')
        records = [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(members.items())]
        bundle_manifest = {'schema_version': 1, 'bundle_id': VERSION, 'kind': kind, 'source_commit': commit,
            'corpus': manifest['corpus'], 'availability': 'pending_upload',
            'model': sealed['input_manifest']['config']['model'], 'runtime_build': sealed['input_manifest']['runtime']['build_info'],
            'profiles': sealed['input_manifest']['profiles'], 'files': records,
            'historical_inputs': historical_inputs,
            'history': {'executed_runner': DIAG_RUN + '/runner_executed.py', 'current_runner': 'rag/scripts/diagnose_rag_generation.py'},
            'absolute_paths': 'Only original historical records retain old absolute paths; inventory uses project-relative paths.'}
        zip_path = output / f'{VERSION}-{kind}.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, data in sorted(members.items()):
                safe_name(name)
                z.writestr(name, data)
            z.writestr('bundle_manifest.json', json_text(bundle_manifest) + '\n')
        write_json(output / f'{kind}_manifest.json', bundle_manifest)
        result = verify_archive(zip_path, output / f'verified_restore_{kind}')
        result.update(path=zip_path.relative_to(root).as_posix(), bytes=zip_path.stat().st_size)
        results.append(result)
    index = {'bundle_id': VERSION, 'source_commit': commit, 'availability': 'pending_upload', 'packages': results}
    write_json(output / 'bundle_index.json', index)
    (output / 'SHA256SUMS.txt').write_text(''.join(x['sha256'] + '  ' + Path(x['path']).name + '\n' for x in results), encoding='ascii')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('views')
    sub.add_parser('check-views')
    p = sub.add_parser('bundles')
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('archive', type=Path)
    p.add_argument('--extract-to', type=Path)
    args = parser.parse_args()
    if args.command == 'views':
        export_views(ROOT)
        result = verify_views(ROOT)
    elif args.command == 'check-views':
        result = verify_views(ROOT)
    elif args.command == 'bundles':
        result = build_bundles(ROOT, args.output.resolve())
    else:
        result = verify_archive(args.archive, args.extract_to)
    print(json_text(result))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
