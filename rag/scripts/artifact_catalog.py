"""Resolve stable artifact identities and reserve immutable local run directories."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
TERMINAL = {'completed', 'completed_with_errors', 'failed', 'interrupted'}
LEGACY_DATASETS = {'full_corpus': 'rag/data/full/genshin_wiki_data_20260605/corpus.jsonl',
                   'sample_corpus': 'rag/data/mvp/corpus.jsonl'}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_catalog(root=PROJECT):
    doc = json.loads((Path(root) / 'rag/catalog.json').read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1 or any(not isinstance(doc.get(k), dict) for k in ('experiments', 'runs', 'reviews', 'datasets')):
        raise ValueError('Invalid artifact catalog')
    return doc


def local_path(root, relative, parent):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    base = (root / parent).resolve()
    if not base.is_relative_to(root) or not path.is_relative_to(base) or path == base:
        raise ValueError('Artifact outside its approved directory')
    return path


def experiment_input(root, experiment, name):
    doc = load_catalog(root)
    return local_path(root, doc['experiments'][experiment]['inputs'][name], 'rag')


def dataset_path(root, dataset, version=None):
    catalog = Path(root) / 'rag/catalog.json'
    if catalog.exists():
        row = load_catalog(root)['datasets'][dataset]
        relative = row['versions'][version]['path'] if version is not None else row['path']
    else:
        relative = LEGACY_DATASETS[dataset]
    return local_path(root, relative, 'rag')


def resolve_data_path(root, path):
    normalized = str(path).replace('\\', '/')
    if '..' in PurePosixPath(normalized).parts:
        raise ValueError('Parent traversal in historical path')
    boundary = normalized.find('/rag/')
    marker = 0 if normalized.startswith('rag/') else (boundary + 1 if boundary >= 0 else -1)
    if marker < 0:
        raise ValueError('Unrecognized historical project path')
    normalized = normalized[marker:]
    aliases = load_catalog(root).get('legacy_paths', {}) if (Path(root) / 'rag/catalog.json').exists() else {}
    for old, new in sorted(aliases.items(), key=lambda pair: -len(pair[0])):
        if normalized == old or normalized.startswith(old + '/'):
            normalized = new + normalized[len(old):]
            break
    return local_path(root, normalized, 'rag/data')


def read_data_bytes(root, path):
    resolved = resolve_data_path(root, path)
    if resolved.is_file():
        return resolved.read_bytes()
    relative = resolved.relative_to(Path(root).resolve()).as_posix()
    entry = load_catalog(root).get('archived_files', {}).get(relative)
    if entry is None:
        raise FileNotFoundError(relative)
    with zipfile.ZipFile(local_path(root, entry['archive'], 'rag/data')) as archive:
        return archive.read(entry['member'])


def assert_writable_output(root, output, document=None):
    root = Path(root).resolve()
    output = Path(output).resolve()
    doc = document or load_catalog(root)
    protected = [root / 'data/raw']
    for dataset in doc['datasets'].values():
        if dataset.get('kind') == 'corpus':
            protected.append((root / dataset['path']).parent)
            protected.extend((root / row['path']).parent for row in dataset.get('versions', {}).values() if row['status'] == 'completed')
    protected.extend(root / row['artifacts'] for row in doc['runs'].values() if row['execution_status'] in TERMINAL)
    protected.extend((root / row['path']).parent for row in doc.get('prepared', {}).values() if row['status'] == 'completed')
    for section in ('releases', 'archives'):
        protected.extend(root / row['directory'] for row in doc.get(section, {}).values())
    protected.extend((root / row['path']).parent for row in doc.get('baselines', {}).values())
    protected.extend(root / old for old in doc.get('legacy_paths', {}) if old.startswith('rag/data/'))
    if any(output.is_relative_to(p.resolve()) for p in protected):
        raise ValueError('Output is inside a frozen artifact; choose a new version or run')


def output_namespace(root, output, kind):
    root = Path(root).resolve()
    if not any(Path(output).resolve().is_relative_to(root / 'rag/data' / folder) for folder in (kind, 'tmp')):
        raise ValueError('Explicit output must be under rag/data/' + kind + ' or a new tmp task')


def reserve_corpus(root, dataset, output_dir=None):
    root = Path(root).resolve()
    with catalog_lock(root):
        doc = load_catalog(root)
        definition = doc['datasets'][dataset]
        if definition.get('kind') != 'corpus':
            raise ValueError('Not a corpus resource')
        explicit = local_path(root, str(output_dir), 'rag/data') if output_dir is not None else None
        if explicit is not None and explicit.exists():
            raise FileExistsError('Corpus output already exists')
        if explicit is not None:
            assert_writable_output(root, explicit, doc)
            output_namespace(root, explicit, 'corpora')
        versions = definition.setdefault('versions', {definition['version']: {'path': definition['path'], 'status': 'completed'}})
        number = max((int(v[1:]) for v in versions if re.fullmatch(r'v\d+', v)), default=0) + 1
        while True:
            version = f'v{number}'
            output = explicit or local_path(root, f"rag/data/corpora/{definition['resource_id']}/{version}", 'rag/data')
            if output.exists():
                number += 1
                continue
            output.mkdir(parents=True, exist_ok=False)
            break
        versions[version] = {'path': (output / 'corpus.jsonl').relative_to(root).as_posix(),
                             'status': 'building', 'created_at': now()}
        save_catalog(root, doc)
        return version, output


def finish_corpus(root, dataset, version, status, metadata=None):
    if status not in {'completed', 'failed'}:
        raise ValueError('Invalid corpus build status')
    with catalog_lock(root):
        doc = load_catalog(root)
        definition = doc['datasets'][dataset]
        record = definition['versions'][version]
        if record['status'] != 'building':
            raise ValueError('Corpus build already finished')
        record.update(status=status, finished_at=now(), metadata=metadata or {})
        if status == 'completed':
            if not local_path(root, record['path'], 'rag/data').is_file():
                raise ValueError('Missing generated corpus')
            definition.update(version=version, path=record['path'])
            manifest = local_path(root, record['path'], 'rag/data').parent / 'corpus_manifest.json'
            if manifest.is_file():
                record['manifest'] = manifest.relative_to(Path(root).resolve()).as_posix()
                definition['manifest'] = record['manifest']
            if metadata and metadata.get('source_snapshot'):
                definition['snapshot'] = metadata['source_snapshot']
        save_catalog(root, doc)


def reserve_prepared(root, dataset, version, output_file=None):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', str(version)):
        raise ValueError('Invalid input version')
    with catalog_lock(root):
        doc = load_catalog(root)
        if dataset not in doc['datasets'] or not re.fullmatch(r'[a-z][a-z0-9_]*', dataset):
            raise ValueError('Unknown input dataset')
        explicit = local_path(root, str(output_file), 'rag/data') if output_file is not None else None
        if explicit is not None and (explicit.exists() or explicit.parent.exists()):
            raise FileExistsError('Prepared output directory already exists')
        if explicit is not None:
            assert_writable_output(root, explicit, doc)
            output_namespace(root, explicit, 'prepared')
        records = doc.setdefault('prepared', {})
        prefix = dataset + '/v' + str(version)
        numbers = [int(key.rsplit('/r', 1)[1]) for key in records if re.fullmatch(re.escape(prefix) + r'/r\d{3,}', key)]
        number = max(numbers, default=0) + 1
        while True:
            run_id = f'r{number:03d}'
            output = explicit or local_path(root, f'rag/data/prepared/{prefix}/{run_id}/questions.json', 'rag/data')
            if output.parent.exists():
                number += 1
                continue
            output.parent.mkdir(parents=True, exist_ok=False)
            break
        key = prefix + '/' + run_id
        records[key] = {'dataset_id': dataset, 'input_version': str(version), 'generation_id': run_id,
                        'path': output.relative_to(root).as_posix(), 'status': 'building', 'created_at': now()}
        save_catalog(root, doc)
        return key, output


def finish_prepared(root, key, status, metadata=None):
    if status not in {'completed', 'failed'}:
        raise ValueError('Invalid prepared status')
    with catalog_lock(root):
        doc = load_catalog(root)
        record = doc['prepared'][key]
        if record['status'] != 'building':
            raise ValueError('Prepared copy already finished')
        record.update(status=status, finished_at=now(), metadata=metadata or {})
        if status == 'completed' and not local_path(root, record['path'], 'rag/data').is_file():
            raise ValueError('Missing prepared copy')
        if status == 'completed' and doc['datasets'][record['dataset_id']]['version'] == record['input_version']:
            doc['datasets'][record['dataset_id']]['prepared_current'] = key
        save_catalog(root, doc)


def run_record(root, experiment, run_id):
    return load_catalog(root)['runs'][experiment + '/' + run_id]


def resolve_run(root, identity):
    matches = [record for key, record in load_catalog(root)['runs'].items()
               if record.get('legacy_id') == identity or key == identity]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous run identity: ' + identity)
    return matches[0]


def report_directory(root, legacy_id):
    record = resolve_run(root, legacy_id)
    if not record.get('report'):
        raise ValueError('Run has no public report')
    path = local_path(root, record['report'], 'rag/reports')
    return path.relative_to(Path(root).resolve()).as_posix()


@contextmanager
def catalog_lock(root):
    data = Path(root).resolve() / 'rag/data'
    data.mkdir(parents=True, exist_ok=True)
    lock = data / '.catalog.lock'
    deadline = time.monotonic() + 3
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise FileExistsError('Catalog is locked; inspect the active process before retrying')
            time.sleep(0.01)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def save_catalog(root, document):
    root = Path(root).resolve()
    with tempfile.NamedTemporaryFile(dir=root / 'rag/data', suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    try:
        os.replace(temporary, root / 'rag/catalog.json')
    finally:
        temporary.unlink(missing_ok=True)


def manifest_write(root, record, manifest):
    path = local_path(root, record['manifest'], 'rag/data')
    path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def reserve_run(root, experiment, output_dir=None):
    root = Path(root).resolve()
    if not re.fullmatch(r'[a-z][a-z0-9_]*', experiment):
        raise ValueError('Invalid experiment ID')
    with catalog_lock(root):
        doc = load_catalog(root)
        if experiment not in doc['experiments'] or doc['experiments'][experiment].get('state') == 'retired':
            raise ValueError('Unknown or retired experiment')
        explicit = local_path(root, str(output_dir), 'rag/data') if output_dir is not None else None
        if explicit is not None and explicit.exists():
            raise FileExistsError('Run output already exists')
        if explicit is not None:
            assert_writable_output(root, explicit, doc)
            output_namespace(root, explicit, 'runs')
        numbers = [int(key.rsplit('/r', 1)[1]) for key in doc['runs']
                   if re.fullmatch(re.escape(experiment) + r'/r\d{3,}', key)]
        number = max(numbers, default=0) + 1
        while True:
            run_id = f'r{number:03d}'
            output = explicit or local_path(root, f'rag/data/runs/{experiment}/{run_id}', 'rag/data')
            if output.exists():
                number += 1
                continue
            output.mkdir(parents=True, exist_ok=False)
            break
        key = experiment + '/' + run_id
        record = {'experiment_id': experiment, 'run_id': run_id, 'created_at': now(),
                  'execution_status': 'running', 'review_status': 'not_reviewed',
                  'publication_status': 'not_published', 'artifacts': output.relative_to(root).as_posix(),
                  'manifest': (output / 'run_manifest.json').relative_to(root).as_posix(), 'report': None}
        doc['runs'][key] = record
        # The directory itself also reserves the number if the process is interrupted.
        manifest_write(root, record, dict(record, inputs=[], parameters={}))
        save_catalog(root, doc)
        return key, output


def seal_inputs(root, key, paths, parameters):
    with catalog_lock(root):
        doc = load_catalog(root)
        record = doc['runs'][key]
        if record['execution_status'] != 'running':
            raise ValueError('Cannot change a finished run')
        inputs = []
        for value in paths:
            p = Path(value).resolve()
            relative = p.relative_to(Path(root).resolve()).as_posix() if p.is_relative_to(Path(root).resolve()) else str(p)
            data = p.read_bytes()
            entry = {'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if p.suffix == '.py' and p.is_relative_to(Path(root).resolve() / 'rag/scripts'):
                frozen = local_path(root, record['artifacts'], 'rag/data') / 'executed_source' / relative
                frozen.parent.mkdir(parents=True, exist_ok=True)
                with frozen.open('xb') as stream:
                    stream.write(data)
                entry['executed_copy'] = frozen.relative_to(Path(root).resolve()).as_posix()
            inputs.append(entry)
        try:
            commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
            dirty = bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], stderr=subprocess.DEVNULL).strip())
        except (OSError, subprocess.CalledProcessError):
            commit, dirty = None, None
        manifest_write(root, record, dict(record, inputs=inputs, parameters=parameters,
                                        source_commit=commit, source_dirty=dirty))


def finish_run(root, key, status):
    if status not in TERMINAL:
        raise ValueError('Invalid terminal execution status')
    with catalog_lock(root):
        doc = load_catalog(root)
        record = doc['runs'][key]
        if record['execution_status'] != 'running':
            raise ValueError('Run already finished')
        manifest = json.loads(local_path(root, record['manifest'], 'rag/data').read_text(encoding='utf-8'))
        record.update(execution_status=status, finished_at=now())
        manifest.update(record)
        manifest_write(root, record, manifest)
        save_catalog(root, doc)


def check_catalog(root=PROJECT):
    doc = load_catalog(root)
    aliases = set()
    for experiment, definition in doc['experiments'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', experiment) or definition['state'] not in {'active', 'frozen', 'retired'}:
            raise ValueError('Invalid experiment definition')
        for name in definition['inputs']:
            if not experiment_input(root, experiment, name).is_file():
                raise ValueError('Missing experiment input')
    for key, record in doc['runs'].items():
        if key != record['experiment_id'] + '/' + record['run_id'] or record['experiment_id'] not in doc['experiments']:
            raise ValueError('Invalid run identity')
        if not re.fullmatch(r'r\d{3,}', record['run_id']):
            raise ValueError('Invalid run number')
        if record['execution_status'] not in TERMINAL | {'running'}:
            raise ValueError('Invalid execution status')
        if record['review_status'] not in {'not_reviewed', 'in_review', 'accepted', 'needs_revision'}:
            raise ValueError('Invalid review status')
        if record['publication_status'] not in {'not_published', 'pending_upload', 'available'}:
            raise ValueError('Invalid publication status')
        local_path(root, record['artifacts'], 'rag/data')
        if record.get('legacy_id'):
            if record['legacy_id'] in aliases:
                raise ValueError('Duplicate legacy alias')
            aliases.add(record['legacy_id'])
        if record.get('report'):
            report_directory(root, key)
    for dataset in doc['datasets'].values():
        if dataset.get('version') and dataset.get('kind') != 'corpus':
            value = json.loads(local_path(root, dataset['path'], 'rag/eval').read_text(encoding='utf-8'))
            if value.get('version') != dataset['version']:
                raise ValueError('Dataset version differs from catalog')
    for review in doc['reviews'].values():
        for field in ('input', 'summary'):
            if review.get(field) is None and review.get('availability') == 'local_optional':
                continue
            parent = 'rag/data' if review[field].startswith('rag/data/') else 'rag/eval/reviews'
            if not local_path(root, review[field], parent).is_file() and review.get('availability') != 'local_optional':
                raise ValueError('Missing review material')
        if review['review_status'] not in {'not_reviewed', 'in_review', 'accepted', 'needs_revision'}:
            raise ValueError('Invalid review status')
    return {'experiments': len(doc['experiments']), 'runs': len(doc['runs']),
            'reviews': len(doc['reviews']), 'legacy_aliases': len(aliases)}


if __name__ == '__main__':
    print(json.dumps(check_catalog(), ensure_ascii=False))
