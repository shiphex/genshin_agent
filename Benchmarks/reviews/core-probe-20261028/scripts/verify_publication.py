"""Read-only checks of the approved snapshot; no model calls or score changes."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = BUNDLE.parents[2]
EVIDENCE = BUNDLE / 'evidence'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    provenance = read(BUNDLE / 'provenance.json')
    expected = provenance['published_files']
    for relative, fingerprint in expected.items():
        check(sha(ROOT / relative) == fingerprint, 'published hash differs: ' + relative)
    changed = subprocess.check_output(['git', 'diff', '--name-only', provenance['base_commit']], cwd=ROOT, text=True).splitlines()
    new = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    actual = set(changed + new)
    manifest_path = (BUNDLE / 'provenance.json').relative_to(ROOT).as_posix()
    check(actual == set(expected) | {manifest_path}, 'publication file whitelist differs')
    for record in provenance['records']:
        check(sha(ROOT / record['path']) == record['published_sha256'], 'source-copy hash differs: ' + record['path'])
        if record['copy'] == 'byte_exact':
            check(record['source_sha256'] == record['published_sha256'], 'copy was changed')
        if '--source-root' in sys.argv:
            source_root = Path(sys.argv[sys.argv.index('--source-root') + 1])
            check(sha(source_root / record['source']) == record['source_sha256'], 'local original changed: ' + record['source'])
    secret_patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                       rb'\b(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}',
                       rb'(?i)"(?:api_key|access_token|password)"\s*:\s*"[^"\s]+"',
                       rb'(?i)Authorization:\s*Bearer\s+[A-Za-z0-9_.\-]{12,}']
    for relative in expected:
        if relative.endswith('verify_publication.py'):
            continue  # the literal scan patterns are not credentials
        data = (ROOT / relative).read_bytes()
        check(not any(re.search(pattern, data) for pattern in secret_patterns), 'possible credential in: ' + relative)
    core_counts = {}
    for run, candidate, count in [('core-self-smoke-r001', 'core_self', 9),
                                   ('core-sdk-smoke-r002', 'core_sdk', 9),
                                   ('core-probe-full-r001', 'core_self', 15),
                                   ('core-sdk-full-r002', 'core_sdk', 15)]:
        selected = [r for r in rows(EVIDENCE / 'agent_core/core' / run / 'results.jsonl') if r['adapter_id'] == candidate]
        check(len(selected) == count and all(r['execution_status'] == 'completed' and r['correct'] is True
              and r['conformance_status'] == 'passed' for r in selected), 'final Core denominator/verdict differs')
        core_counts[run] = count
    perf = {}
    for phase in ('timing', 'memory'):
        samples = rows(EVIDENCE / f'agent_core/perf/core-probe-{phase}-r001/results.jsonl')
        check(len(samples) == 21 and all(r['execution_status'] == 'completed' and r['correct'] is True
              and r['conformance_status'] == 'passed' and len(r['iterations_ms']) == 100 for r in samples), 'perf denominator/verdict differs')
        check(Counter(r['adapter_id'] for r in samples) == {'core_self': 7, 'core_sdk': 7, 'transport_replay': 7}, 'perf groups differ')
        manifest = read(EVIDENCE / f'agent_core/perf/core-probe-{phase}-r001/manifest.json')
        check([r['sample_id'] for r in samples] == [r['sample_id'] for r in manifest['planned_samples']], 'perf order differs')
        metric = (lambda r: r['per_iteration_ms']) if phase == 'timing' else (lambda r: r['resources']['sampled_peak_rss_bytes'] / 1048576)
        perf[phase] = {a: statistics.median(metric(r) for r in samples if r['adapter_id'] == a)
                       for a in ('core_self', 'core_sdk', 'transport_replay')}
    check(round(perf['timing']['core_self'], 3) == 19.050 and round(perf['timing']['core_sdk'], 3) == 21.579, 'timing report differs')
    check(round(perf['memory']['core_self'], 3) == 16.824 and round(perf['memory']['core_sdk'], 3) == 79.227, 'memory report differs')
    run = EVIDENCE / 'agent_story/agent/core-probe-live-r001'
    review = EVIDENCE / 'agent_story/review/core-probe-live-r001'
    originals, materials = rows(run / 'results.jsonl'), read(run / 'materials.json')
    package, binding, scoring = (read(review / name) for name in ('package.json', 'binding.json', 'scored.json'))
    check(len(originals) == len(package['samples']) == len(scoring['samples']) == 18, 'Story sample count differs')
    check(package['materials_sha256'] == sha(run / 'materials.json'), 'frozen materials changed')
    check(binding['package_sha256'] == scoring['package_sha256'] == sha(review / 'package.json'), 'package hash differs')
    check(package['run_identity'] == binding['run_identity'] == scoring['run_identity'], 'run binding differs')
    identity_parts = {name: sha(run / name) for name in ('manifest.json', 'results.jsonl', 'materials.json')}
    identity_parts['trace.jsonl'] = provenance['original_story_trace_sha256']
    encoded = json.dumps(identity_parts, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    check(hashlib.sha256(encoded).hexdigest() == binding['run_identity'], 'original run identity hash claims differ')
    score_by_id = {s['id']: s for s in scoring['samples']}
    criterion_counts, passed = Counter(), Counter()
    for number, (original, sample) in enumerate(zip(originals, package['samples']), 1):
        sid = f'sample-{number:04}'
        check(sample['id'] == sid and binding['mapping'][sid] == original['sample_id'], 'sample mapping differs')
        check(original['execution_status'] == 'completed' and original['conformance_status'] == 'passed', 'Story execution failed')
        material = materials[original['scenario_id']]
        scene = material['scenario']
        evidence = {'source:' + s['id']: s for s in material['frozen_sources']}
        evidence.update({'retrieved:' + s['id']: s for s in original.get('observed_evidence', [])})
        for field, expected_value in {'scenario_id': original['scenario_id'], 'repeat': original['repeat'],
                'execution_status': original['execution_status'], 'turns': original['turns'],
                'provider_records': original['provider_records'], 'reference_material': scene['reference_material'],
                'criteria': scene['criteria'], 'forbidden': scene['forbidden'], 'evidence': evidence}.items():
            check(sample[field] == expected_value, 'anonymous package differs: ' + field)
        criteria = score_by_id[sid]['criteria']
        check(len(criteria) == len(sample['criteria']) and {c['id'] for c in criteria} == {c['id'] for c in sample['criteria']}, 'rubric incomplete')
        refs = {'sample:execution'} | set(evidence) | {f'turn:{i+1}' for i in range(len(sample['turns']))} | {f'trace:{i+1}' for i in range(len(sample['trace']))}
        for criterion in criteria:
            check(criterion['verdict'] in {'pass', 'fail', 'uncertain'} and bool(criterion['rationale'].strip()), 'invalid judgment')
            check(bool(criterion['evidence_refs']) and set(criterion['evidence_refs']) <= refs, 'invalid evidence reference')
            criterion_counts[criterion['verdict']] += 1
        if all(c['verdict'] == 'pass' for c in criteria):
            passed[original['adapter_id']] += 1
    check(criterion_counts == {'pass': 60, 'fail': 36} and passed == {'core_self': 6, 'core_sdk': 6}, 'AI score totals differ')
    check(sum(r['model_api_completed'] for r in originals) == 54, 'API count differs')
    print(json.dumps({'published_files': len(expected) + 1, 'core_final_counts': core_counts,
        'perf_medians': perf, 'story_samples': 18, 'scenario_model_calls': 54,
        'ai_criteria': dict(criterion_counts), 'ai_passed': dict(passed),
        'limits': 'Hash consistency only; omitted trace is not independently verified; no semantic/user acceptance.'}, indent=2))

if __name__ == '__main__':
    main()
