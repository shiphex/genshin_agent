"""Integrity and independent semantic judgments remain separate from execution."""
from pathlib import Path
from collections import Counter

from Benchmarks.support.common import read_json, read_rows, write_json, file_hash
from probes.a06_diagnosis.evidence import audit_transfers, audit_injected_history
from .artifacts import new_store, seal, assert_sealed, assessment
from .preparation import load_run, execution_sources
from .validation import validate_request, assert_presentation_pair

D_CRITERIA = [
    {'id': 'd1', 'text': '准确回答当前人物或效忠问题，保留材料中的说话者归属。'},
    {'id': 'd2', 'text': '不混淆女士、温迪、摩拉克斯或不同场景。'},
    {'id': 'd3', 'text': '断言得到实际工具证据支持，不无据扩写，保留来源性质与限定。'}]


def validate_query_audit(expected, rows):
    def key(query):
        return query.get('origin_stage'), query['turn'], query['query']
    if Counter(map(key, expected)) != Counter(key(r) for r in rows if r.get('kind') == 'actual'):
        raise ValueError('final actual query audit is incomplete or bound to another origin')


def presentation_groups(rows, judgments):
    if len(rows) != len(judgments):
        raise ValueError('presentation judgments must cover every sample')
    groups = []
    for turn, arm in sorted({(row['turn'], row['arm']) for row in rows}):
        pairs = [(row, status) for row, status in zip(rows, judgments) if row['turn'] == turn and row['arm'] == arm]
        group = {'turn': turn, 'arm': arm, 'total': len(pairs),
                 **{key: sum(status == key for _, status in pairs)
                    for key in ('pass', 'fail', 'uncertain', 'unreviewed', 'incomplete')}}
        for key in ('prompt_tokens', 'completion_tokens'):
            values = [row.get('result', {}).get('usage') or {} for row, _ in pairs]
            group[key] = [v[key] for v in values] if all(key in v for v in values) else None
        groups.append(group)
    return groups


def semantic_status(row, criteria, review, source_ids=()):
    judgment = review.get('samples', {}).get(row['sample_id'])
    if judgment is None:
        return 'unreviewed'
    items = judgment.get('criteria', [])
    if len(items) != len(criteria) or {c['id'] for c in items} != {c['id'] for c in criteria}:
        raise ValueError('review must contain every frozen criterion exactly once')
    allowed = {'sample:execution'} | {f'turn:{t["turn"]}' for t in row.get('turns', [])}
    if row.get('turn'):
        allowed.add(f'turn:{row["turn"]}')
    allowed |= {f'retrieved:{h["id"]}' for h in row.get('observed_evidence', [])}
    allowed |= {f'source:{identity}' for identity in source_ids}
    for item in items:
        if (item.get('verdict') not in ('pass', 'fail', 'uncertain') or not item.get('rationale')
                or not item.get('evidence_refs') or not set(item['evidence_refs']) <= allowed):
            raise ValueError('review contains invalid judgment or unresolved evidence reference')
    if row['execution_status'] != 'completed':
        return 'incomplete'
    verdicts = {item['verdict'] for item in items}
    return 'fail' if 'fail' in verdicts else 'uncertain' if 'uncertain' in verdicts else 'pass'


def import_assessment(stage, source):
    stage = Path(stage); assert_sealed(stage)
    review = read_json(source)
    if not review.get('reviewer'):
        raise ValueError('independent reviewer identity required')
    stage_hash = file_hash(stage / 'hashes.json')
    if review.get('stage_hashes_sha256') != stage_hash:
        raise ValueError('assessment source binding does not match this sealed stage')
    if 'first_turn' in review:
        first = review['first_turn']
        if (not isinstance(first, dict) or 'supported_correct' not in first
                or first['supported_correct'] is not None and type(first['supported_correct']) is not bool
                or not first.get('reason')):
            raise ValueError('invalid first-turn assessment')
    manifest = read_json(stage / 'manifest.json')
    rows = read_rows(stage / 'results.jsonl')
    by_id = {row['sample_id']: row for row in rows}
    if not set(review.get('samples', {})) <= by_id.keys():
        raise ValueError('assessment contains an unknown sample')
    if review.get('samples'):
        materials = read_json(stage.parent / 'materials.json')
        for sample in review['samples']:
            row = by_id[sample]
            scene = materials[row.get('scenario_id', 'a06')]
            criteria = D_CRITERIA if manifest['condition'] == 'D' else scene['scenario']['criteria']
            semantic_status(row, criteria, review, [s['id'] for s in scene['frozen_sources']])
    for query_id, judgment in review.get('queries', {}).items():
        row = by_id.get(query_id)
        if (row is None or judgment.get('semantic_sufficiency') not in ('sufficient', 'insufficient', 'uncertain')
                or not judgment.get('reason') or not set(judgment.get('supporting_ids', [])) <= {h['id'] for h in row['hits']}
                or judgment.get('semantic_sufficiency') == 'sufficient' and not judgment.get('supporting_ids')):
            raise ValueError('invalid query sufficiency assessment')
    directory = stage / 'assessments'; directory.mkdir(exist_ok=True)
    count = len(list(directory.glob('r*.json'))) + 1
    review.update(imported_from_sha256=file_hash(source), user_acceptance='not_evaluated', kind='ai')
    output = directory / f'r{count:03}.json'
    write_json(output, review, exclusive=True)
    return output


def verify(run, output):
    binding, scenes, materials = load_run(run, require_current_sources=False)
    store = new_store(output, 'verification')
    findings = []
    required = ['preflight', 'O-r001', 'B-r001', 'B-final-r001', 'D-r001']
    required += [f'A-r{i:03}' for i in (1, 2, 3)]
    required += [f'R-{s}-r{i:03}' for s in ('a07', 'a10', 'a11') for i in (1, 2, 3)]
    try:
        store.manifest['execution_sources'] = execution_sources(run, require_current=False)
        for name, sha in binding['baseline'].items():
            if file_hash(Path(binding['project']) / name) != sha:
                findings.append(f'baseline changed: {name}')
        for name in required:
            if not (Path(run) / name / 'hashes.json').is_file():
                findings.append(f'planned stage missing: {name}')
        if (Path(run) / 'B-final-r001/results.jsonl').exists():
            from .stages import actual_queries
            validate_query_audit(actual_queries(run), read_rows(Path(run) / 'B-final-r001/results.jsonl'))
        for stage in sorted(Path(run).iterdir()):
            if stage == store.path or not (stage / 'hashes.json').is_file():
                continue
            manifest = read_json(stage / 'manifest.json')
            condition = manifest['condition']
            if condition in ('verification', 'report'):
                continue
            assert_sealed(stage)
            rows = read_rows(stage / 'results.jsonl')
            if {r['sample_id'] for r in rows} != {r['sample_id'] for r in manifest['planned_samples']}:
                findings.append(f'{stage.name}: planned/result identities differ')
            records = read_rows(stage / 'api.jsonl') if (stage / 'api.jsonl').exists() else []
            requests = [r for r in records if r.get('event') == 'request' and r['endpoint'] == 'chat/completions']
            for record in requests:
                forced = (condition == 'A' and record['turn'] == 1 or condition == 'preflight' and record['turn'] == 0) and record['request'] == 1
                validate_request(record['payload'], forced=forced)
                if condition != 'preflight' and record['payload']['messages'][0] != {'role': 'system', 'content': binding['system']}:
                    findings.append(f'{stage.name}: changed system')
                for key in ('max_tokens', 'temperature', 'seed'):
                    if record['payload'].get(key) != binding['model_config'][key]:
                        findings.append(f'{stage.name}: changed generation {key}')
            if condition == 'A':
                if not any(r['turn'] == 1 and r['request'] == 1 for r in requests):
                    findings.append(f'{stage.name}: planned forced request absent')
                try:
                    first_review, _ = assessment(stage)
                    if first_review['first_turn']['supported_correct'] is not True:
                        if not (Path(run) / stage.name.replace('A-', 'C2-') / 'hashes.json').exists():
                            findings.append(f'{stage.name}: gated C2 missing')
                except (ValueError, KeyError):
                    findings.append(f'{stage.name}: first-turn assessment missing')
            parameters = manifest.get('parameters', {})
            references = list(parameters.get('assessment_binding', {}).values())
            if parameters.get('b_assessment'):
                references.append(parameters['b_assessment'])
            for reference in references:
                if file_hash(reference['path']) != reference['sha256']:
                    findings.append(f'{stage.name}: bound assessment changed')
            if condition in ('O', 'A', 'C2', 'R'):
                transfers = audit_transfers(read_rows(stage / 'trace.jsonl'), records)
                if any(not t['exact_match'] for t in transfers):
                    findings.append(f'{stage.name}: tool result not delivered intact')
            if condition == 'C2':
                if not audit_injected_history(read_json(stage / 'injected-history.json'), records)['exact_match']:
                    findings.append(f'{stage.name}: injected history changed')
            if condition == 'D':
                for turn in (1, 3):
                    for repeat in (1, 2, 3):
                        pair = {arm: next((r['payload'] for r in requests
                            if r['sample_id'] == f'D:t{turn}:{arm}:{repeat}'), None)
                            for arm in ('structured', 'text')}
                        if any(value is None for value in pair.values()):
                            findings.append(f'D: missing pair t{turn}/{repeat}')
                        else:
                            assert_presentation_pair(pair['structured'], pair['text'], [3] if turn == 1 else [3, 7])
            for review_path in (stage / 'assessments').glob('r*.json'):
                if read_json(review_path)['stage_hashes_sha256'] != file_hash(stage / 'hashes.json'):
                    findings.append(f'{stage.name}: assessment bound to wrong stage')
            if condition in ('O', 'A', 'C2', 'R', 'D', 'B'):
                try:
                    review, _ = assessment(stage)
                    if condition == 'B':
                        if set(review.get('queries', {})) != {r['sample_id'] for r in rows}:
                            findings.append(f'{stage.name}: incomplete query review')
                    else:
                        for row in rows:
                            material = materials[row.get('scenario_id', 'a06')]
                            criteria = D_CRITERIA if condition == 'D' else material['scenario']['criteria']
                            if semantic_status(row, criteria, review, [s['id'] for s in material['frozen_sources']]) == 'unreviewed':
                                findings.append(f'{stage.name}: missing semantic review {row["sample_id"]}')
                except ValueError as exc:
                    findings.append(f'{stage.name}: invalid or missing review: {exc}')
        write_json(store.path / 'verification.json', {'findings': findings,
            'baseline_files': len(binding['baseline']), 'semantic_verification': 'independent_review',
            'user_acceptance': 'not_evaluated'}, exclusive=True)
        store.finish('failed' if findings else 'completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path, not findings


def report(run, output):
    binding, scenes, materials = load_run(run, require_current_sources=False)
    store = new_store(output, 'report')
    assessments, summary = {}, []
    try:
        store.manifest['execution_sources'] = execution_sources(run, require_current=False)
        lines = ['# 结构化 RAG 探针验证', '',
            '执行、API、证据覆盖、引用及语义分开；独立AI审阅不代表用户验收。', '',
            '| 阶段 | 计划样本 | 完成 | API响应/正常结束 | 工具请求 | AI语义pass/fail/uncertain/未评 |',
            '| --- | ---: | ---: | --- | ---: | --- |']
        for stage in sorted(Path(run).iterdir()):
            if stage == store.path or not (stage / 'manifest.json').is_file():
                continue
            manifest = read_json(stage / 'manifest.json'); condition = manifest['condition']
            if condition not in ('O', 'A', 'C2', 'D', 'R', 'B', 'preflight'):
                continue
            assert_sealed(stage)
            rows = read_rows(stage / 'results.jsonl')
            try:
                review, reference = assessment(stage)
                assessments[stage.name] = reference
            except ValueError:
                review = {}
            judgments = []
            if condition not in ('B', 'preflight'):
                for row in rows:
                    criteria = D_CRITERIA if condition == 'D' else scenes[row['scenario_id']]['criteria']
                    ids = [s['id'] for s in materials[row.get('scenario_id', 'a06')]['frozen_sources']]
                    judgments.append(semantic_status(row, criteria, review, ids))
            records = read_rows(stage / 'api.jsonl') if (stage / 'api.jsonl').exists() else []
            responses = [r for r in records if r.get('event') == 'response' and r['endpoint'] == 'chat/completions']
            normal = sum(r['raw_response']['choices'][0].get('finish_reason') in ('stop', 'tool_calls') for r in responses)
            counts = {key: judgments.count(key) for key in ('pass', 'fail', 'uncertain', 'unreviewed', 'incomplete')}
            result = {'stage': stage.name, 'condition': condition, 'planned': len(manifest['planned_samples']),
                'completed': sum(r['execution_status'] == 'completed' for r in rows),
                'api_responses': len(responses), 'api_normal_finish': normal,
                'tool_requests': sum(r.get('tool_calls', 0) for r in rows), 'ai_semantic': counts,
                'end_to_end_score': 'not_applicable' if condition in ('C2', 'D', 'B', 'preflight') else 'separate_from_diagnostics'}
            if condition == 'D':
                result['presentation_groups'] = presentation_groups(rows, judgments)
            if condition == 'B':
                result['query_audit'] = [{'sample_id': r['sample_id'], 'turn': r['turn'], 'kind': r['kind'],
                    'origin_stage': r.get('origin_stage'), 'necessary_location_proxy': r.get('necessary'),
                    'semantic_review': review.get('queries', {}).get(r['sample_id'], {'semantic_sufficiency': 'unreviewed'})}
                    for r in rows]
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                usages = [r['raw_response'].get('usage') or {} for r in responses]
                result.setdefault('usage_totals', {})[key] = sum(u[key] for u in usages) if usages and all(key in u for u in usages) else None
            summary.append(result)
            values = '/'.join(str(counts[k]) for k in ('pass', 'fail', 'uncertain', 'unreviewed'))
            lines.append(f'| {stage.name} | {result["planned"]} | {result["completed"]} | {len(responses)}/{normal} | {result["tool_requests"]} | {values} |')
        lines += ['', '## 固定证据呈现', '',
            '| 问题／表示 | 样本 | AI语义pass/fail/uncertain | 各次prompt token | 各次completion token |',
            '| --- | ---: | --- | --- | --- |']
        for stage_result in summary:
            for group in stage_result.get('presentation_groups', []):
                status = '/'.join(str(group[key]) for key in ('pass', 'fail', 'uncertain'))
                lines.append(f'| t{group["turn"]}/{group["arm"]} | {group["total"]} | {status} | {group["prompt_tokens"]} | {group["completion_tokens"]} |')
        lines += ['', '## 查询审阅', '', '| 阶段 | 充分 | 不足 | 存疑 | 未评 |', '| --- | ---: | ---: | ---: | ---: |']
        for stage_result in summary:
            if 'query_audit' in stage_result:
                statuses = [q['semantic_review']['semantic_sufficiency'] for q in stage_result['query_audit']]
                values = ' | '.join(str(statuses.count(key)) for key in ('sufficient', 'insufficient', 'uncertain', 'unreviewed'))
                lines.append(f'| {stage_result["stage"]} | {values} |')
        lines += ['', '## 判定与限制', '',
            'A的C1资格由各次完整首答评估决定，不能将错误首答延续计入C1。C2与D为受控诊断，不计端到端。',
            'A与C2的查询及Top5不同，差异不能单独归因正确历史。C2未真实执行首轮，涉及完整三轮或首轮的标准保留存疑。',
            '旧r003/report-r002只作历史参照；语料、提示词与工具说明均有变化，不宣称同条件提升。',
            '固定seed与有限重复不支持统计显著性；未送达证据不能被判定为模型忽略，引用ID合法不等于支持断言。']
        conclusion = Path(run) / 'conclusions.json'
        if conclusion.exists():
            data = read_json(conclusion)
            lines += ['', '## 独立审阅后的诊断', ''] + [f'- {k}: {v}' for k, v in data.items()]
            store.manifest['conclusions_sha256'] = file_hash(conclusion)
        write_json(store.path / 'assessments.json', assessments, exclusive=True)
        write_json(store.path / 'comparison.json', {'stages': summary, 'user_acceptance': 'not_evaluated'}, exclusive=True)
        (store.path / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        store.finish('completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path
