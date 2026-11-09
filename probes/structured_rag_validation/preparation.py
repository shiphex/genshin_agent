"""Bind the existing scenarios to explicitly migrated, read-only candidate inputs."""
from pathlib import Path

from Benchmarks.agent_story.scenarios import load_scenarios
from Benchmarks.agent_story.providers import freeze_sources, SYSTEM, SEARCH_TOOL
from Benchmarks.support.common import ROOT, read_json, read_rows, write_json, file_hash
from probes.a06_diagnosis.evidence import source_anchors, map_anchors
from probes.core_self.worker import POLICIES
from rag.scripts.local_model_config import load_api_config
from .artifacts import new_store, bind_suite, experimental_config, seal, assert_sealed
from .evidence import require_mapped
from .validation import validate_inputs

SELECTED = ['a06', 'a07', 'a10', 'a11']


def relocate_required(anchors, entries, old_groups):
    groups = []
    for indices in old_groups:
        group = []
        for index in indices:
            matches = [entry for entry in entries if entry.get('input') == 'questions.json'
                and entry['question_id'] == 'gq2-001' and entry['old_pointer'] == f'/对话/{index}/内容'
                and entry['status'] != 'unresolved']
            if len(matches) != 1:
                raise ValueError('required anchor migration must be unique and resolved')
            entry = matches[0]
            found = [a for a in anchors if a['source_file'] == entry['file']
                     and a['source_pointer'] == entry['new_pointer']]
            require_mapped(found)
            group.extend(found)
        groups.append(group)
    return groups


def prepare(project, output, *, config=None, corpus=None, questions=None, raw_root=None,
            api_timeout=180, worker_timeout=240):
    if type(worker_timeout) is not int or worker_timeout < 1:
        raise ValueError('worker_timeout must be a positive integer')
    project = Path(project).resolve()
    config = Path(config or project / 'rag/config/local_api.json').resolve()
    private = config.with_name(config.stem + '.local.json')
    corpus = Path(corpus or project / 'rag/data/outputs/corpus/r002/corpus.jsonl').resolve()
    questions = Path(questions or project / 'rag/data/outputs/prepared/r004/questions.json').resolve()
    raw_root = Path(raw_root or project / 'data/raw/genshin_wiki_data_20260605_261106').resolve()
    migration = questions.with_name('migration_report.json')
    template = ROOT / 'Benchmarks/agent_story/scenarios.json'
    store = new_store(output, 'inputs', paths=[config, corpus, questions, migration, template])
    try:
        bind_suite(template, questions, store.path / 'scenarios.json')
        suite = load_scenarios(ROOT, store.path / 'scenarios.json', questions_path=questions)
        suite['scenarios'] = [s for s in suite['scenarios'] if s['id'] in SELECTED]
        if {s['id'] for s in suite['scenarios']} != set(SELECTED):
            raise ValueError('selected scenarios are missing')
        rows = read_rows(corpus)
        validate_inputs(rows, suite, raw_root)
        bank = read_json(questions)
        original = {q['id']: q for q in read_json(project / 'rag/eval/questions.json')['questions']}
        for q in bank['questions']:
            if q['id'] in {qid for s in suite['scenarios'] for qid in s['question_ids']}:
                if any(q[key] != original[q['id']][key] for key in ('question', 'answer', 'criteria')):
                    raise ValueError('candidate changes selected question semantics')
                if any(s.get('migration_status') == 'unresolved' for s in q['sources']):
                    raise ValueError('selected source is unresolved')
        materials = {s['id']: {'scenario': s, 'frozen_sources': freeze_sources(s, raw_root),
            'mapped_anchors': require_mapped(map_anchors(source_anchors(s, raw_root), rows))}
            for s in suite['scenarios']}
        old_inputs = read_json(ROOT / 'probes/a06_diagnosis/inputs.json')
        necessary = relocate_required(materials['a06']['mapped_anchors'], read_json(migration)['entries'],
                                      old_inputs['necessary_dialogue_indices'])
        write_json(store.path / 'materials.json', materials, exclusive=True)
        write_json(store.path / 'effective-suite.json', suite, exclusive=True)
        catalog = read_json(project / 'rag/catalog.json')
        baseline = {name: file_hash(project / name) for name in catalog['files']}
        if any(sha != catalog['files'][name]['sha256'] for name, sha in baseline.items()):
            raise ValueError('baseline fingerprint mismatch before execution')
        files = [config, corpus, questions, migration, template,
                 *{raw_root / source['source_file'] for m in materials.values() for source in m['frozen_sources']}]
        if private.is_file():
            files.append(private)
        binding = {'project': str(project), 'config_path': str(config), 'corpus': str(corpus),
            'questions': str(questions), 'raw_root': str(raw_root),
            'input_hashes': {str(p): file_hash(p) for p in files}, 'baseline': baseline,
            'private_overlay': {'path': str(private), 'present': private.is_file()},
            'model_config': experimental_config(load_api_config(config), api_timeout=api_timeout),
            'worker_timeout': worker_timeout, 'selected_scenarios': SELECTED,
            'necessary_anchors': necessary, 'oracle_queries': old_inputs['oracle_queries'],
            'system': SYSTEM, 'tools': [SEARCH_TOOL], 'policies': POLICIES,
            'historical_reference_only': 'exp/a06-diagnosis:r003/report-r002',
            'user_acceptance': 'not_evaluated'}
        write_json(store.path / 'binding.json', binding, exclusive=True)
        store.finish('completed')
    except BaseException as exc:
        store.finish('failed', type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path


def execution_sources(run, *, require_current):
    run = Path(run)
    metadata = read_json(run / 'manifest.json')['provenance']
    changed = []
    for name, sha in metadata['files'].items():
        target = Path(name) if Path(name).is_absolute() else ROOT / name
        if target.suffix == '.py' or target.name in ('pyproject.toml', 'uv.lock', '.python-version'):
            archived = run / 'sources' / (sha + '-' + target.name)
            if not archived.is_file() or file_hash(archived) != sha:
                raise ValueError(f'execution source archive changed: {name}')
            if not target.is_file() or file_hash(target) != sha:
                changed.append(name)
        elif require_current and (not target.is_file() or file_hash(target) != sha):
            changed.append(name)
    if require_current and changed:
        raise ValueError(f'execution source changed: {changed}')
    return {'execution_git_commit': metadata['git_commit'], 'changed_sources': changed,
            'policy': 'current_required' if require_current else 'verified_execution_archive'}


def load_run(run, *, require_current_sources=True):
    run = Path(run)
    assert_sealed(run)
    binding = read_json(run / 'binding.json')
    if Path(binding['private_overlay']['path']).is_file() != binding['private_overlay']['present']:
        raise ValueError('private configuration presence changed')
    for name, sha in binding['input_hashes'].items():
        if file_hash(name) != sha:
            raise ValueError(f'input fingerprint changed: {name}')
    suite = load_scenarios(ROOT, run / 'scenarios.json', questions_path=Path(binding['questions']))
    expected = read_json(run / 'effective-suite.json')
    suite['scenarios'] = [s for s in suite['scenarios'] if s['id'] in SELECTED]
    if suite != expected:
        raise ValueError('effective scenario binding changed')
    materials = read_json(run / 'materials.json')
    if any(materials[s['id']]['scenario'] != s for s in suite['scenarios']):
        raise ValueError('materials/effective scenario mismatch')
    execution_sources(run, require_current=require_current_sources)
    return binding, {s['id']: s for s in suite['scenarios']}, materials
