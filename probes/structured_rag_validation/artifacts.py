"""Exclusive artifacts, effective bindings, and fingerprints of executed sources."""
from copy import deepcopy
from pathlib import Path

from Benchmarks.support.common import ROOT, RunStore, file_hash, provenance, read_json, write_json

HERE = Path(__file__).resolve().parent


def experimental_config(public, *, api_timeout=180):
    if type(api_timeout) is not int or api_timeout < 1:
        raise ValueError('api_timeout must be a positive integer')
    return {**{key: public.get(key) for key in ('base_url', 'model', 'api_key_env')},
            'timeout': api_timeout, 'max_tokens': 1536, 'temperature': 0, 'seed': 42, 'top_k': 5,
            'tool_choice_mode': 'required_single_tool_prefill'}


def bind_suite(template, questions, output):
    suite = deepcopy(read_json(template))
    suite['question_bank_sha256'] = file_hash(questions)
    suite['questions_path'] = str(Path(questions).resolve())
    suite['template_path'] = str(Path(template).resolve())
    suite['template_sha256'] = file_hash(template)
    write_json(output, suite, exclusive=True)
    return suite


def new_store(output, condition, *, paths=(), parameters=None):
    sources = [*paths, ROOT / 'probes/core_self/worker.py',
               ROOT / 'probes/a06_diagnosis/controls.py', ROOT / 'probes/a06_diagnosis/evidence.py',
               ROOT / 'probes/a06_diagnosis/history_worker.py']
    sources += list((ROOT / 'Benchmarks/agent_story').glob('*.py'))
    sources += [ROOT / 'rag/scripts' / name for name in (
        'evaluate_rag_mvp.py', 'corpus_schema.py', 'local_model_config.py', 'prepare_eval.py', 'artifact_catalog.py')]
    identity = provenance(sources, implementation=HERE)
    store = RunStore(output, {'suite': 'structured_rag_validation', 'condition': condition,
        'parameters': parameters or {}, 'provenance': identity, 'planned_samples': [],
        'user_acceptance': 'not_evaluated'})
    archive = store.path / 'sources'; archive.mkdir()
    for name, sha in identity['files'].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        if path.suffix == '.py' or path.name in ('pyproject.toml', 'uv.lock', '.python-version'):
            (archive / (sha + '-' + path.name)).write_bytes(path.read_bytes())
    return store


def seal(path):
    path = Path(path)
    write_json(path / 'hashes.json', {p.relative_to(path).as_posix(): file_hash(p)
        for p in sorted(path.rglob('*')) if p.is_file() and p.name != 'hashes.json'
        and 'assessments' not in p.relative_to(path).parts}, exclusive=True)


def assert_sealed(path):
    path = Path(path)
    for name, sha in read_json(path / 'hashes.json').items():
        target = path / name
        if not target.is_file() or file_hash(target) != sha:
            raise ValueError(f'sealed artifact changed: {name}')


def assessment(stage, path=None):
    files = sorted((Path(stage) / 'assessments').glob('r*.json'))
    selected = Path(path) if path else (files[-1] if files else None)
    if selected is None:
        raise ValueError('independent assessment required')
    return read_json(selected), {'path': str(selected.resolve()), 'sha256': file_hash(selected)}
