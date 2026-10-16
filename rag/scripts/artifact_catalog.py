"""Locate the immutable current baseline and allocate separate local outputs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

PROJECT = Path(__file__).resolve().parents[2]
PURPOSES = {'corpus', 'prepared', 'retrieval', 'model', 'review', 'hf'}
TERMINAL = {'completed', 'completed_with_errors', 'failed', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_catalog(root=PROJECT):
    doc = json.loads((Path(root) / 'rag/catalog.json').read_text(encoding='utf-8'))
    if (doc.get('schema_version') != 2 or not doc.get('baseline_id')
            or not isinstance(doc.get('datasets'), dict) or not isinstance(doc.get('files'), dict)):
        raise ValueError('Invalid current baseline catalog')
    return doc


def local_path(root, relative, parent='rag'):
    relative = str(relative)
    if '..' in PurePosixPath(relative).parts or '\\' in relative or ':' in relative:
        raise ValueError('Invalid relative artifact path')
    root = Path(root).resolve()
    path = (root / relative).resolve()
    base = (root / parent).resolve()
    if not base.is_relative_to(root) or not path.is_relative_to(base) or path == base:
        raise ValueError('Artifact outside its approved directory')
    return path


def dataset_path(root, dataset):
    return local_path(root, load_catalog(root)['datasets'][dataset]['path'])


def assert_writable_output(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    base = root / 'rag/data/outputs'
    if not output.is_relative_to(base) or len(output.relative_to(base).parts) != 2:
        raise ValueError('Output must be a new, non-nested directory under rag/data/outputs/<purpose>')
    if output.relative_to(base).parts[0] not in PURPOSES:
        raise ValueError('Unknown output purpose')
    # A custom raw snapshot must never become an output, even under outputs/.
    if any((p / 'parsed').is_dir() and (p / 'pages').is_dir() for p in (output, *output.parents)):
        raise ValueError('Output must be outside raw snapshots')
    for relative in load_catalog(root)['files']:
        protected = local_path(root, relative)
        if output == protected or output.is_relative_to(protected.parent):
            raise ValueError('Output overlaps a baseline resource')
    # Reject nested writes into completed, failed or active output directories.
    if any((p / 'run_manifest.json').is_file() for p in output.parents if p.is_relative_to(base)):
        raise ValueError('Output is nested inside an existing run')


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def reserve_output(root, purpose, output=None):
    root = Path(root).resolve()
    if purpose not in PURPOSES:
        raise ValueError('Unknown output purpose')
    base = root / 'rag/data/outputs' / purpose
    if output is not None:
        output = Path(output).resolve()
        assert_writable_output(root, output)
        if not output.is_relative_to(base):
            raise ValueError('Output purpose differs from requested operation')
        output.mkdir(parents=True, exist_ok=False)
    else:
        number = 1
        while True:
            output = base / f'r{number:03d}'
            assert_writable_output(root, output)
            try:
                output.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                number += 1
    _write(output / 'run_manifest.json', {
        'purpose': purpose, 'baseline_id': load_catalog(root)['baseline_id'],
        'created_at': now(), 'execution_status': 'running', 'review_status': 'not_reviewed',
        'publication_status': 'not_published', 'inputs': [], 'parameters': {},
    })
    return output


def seal_inputs(root, output, paths, parameters):
    root, output = Path(root).resolve(), Path(output).resolve()
    assert_writable_output(root, output)
    manifest = json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))
    if manifest['execution_status'] != 'running' or manifest['inputs']:
        raise ValueError('Inputs are already sealed or output is finished')
    entries = []
    for value in paths:
        path = Path(value).resolve()
        data = path.read_bytes()
        row = {'path': path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
               'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if path.suffix == '.py' and path.is_relative_to(root / 'rag/scripts'):
            copied = output / 'executed_source' / path.name
            copied.parent.mkdir(exist_ok=True)
            with copied.open('xb') as stream:
                stream.write(data)
            row['executed_copy'] = copied.relative_to(root).as_posix()
        entries.append(row)
    try:
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    manifest.update(inputs=entries, parameters=parameters, source_commit=commit, source_dirty=dirty)
    _write(output / 'run_manifest.json', manifest)


def finish_output(root, output, status, metadata=None):
    output = Path(output).resolve()
    assert_writable_output(root, output)
    manifest = json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))
    if status not in TERMINAL or manifest['execution_status'] != 'running':
        raise ValueError('Invalid status or output already finished')
    manifest.update(execution_status=status, finished_at=now())
    if metadata is not None:
        manifest['metadata'] = metadata
    _write(output / 'run_manifest.json', manifest)


def verify_files(root, relatives):
    """Check selected baseline bytes before using them as default execution inputs."""
    doc = load_catalog(root)
    for relative in relatives:
        if relative not in doc['files']:
            raise ValueError('Baseline input is not fingerprinted: ' + relative)
        info = doc['files'][relative]
        path = local_path(root, relative)
        data = path.read_bytes()
        if len(data) != info['bytes'] or hashlib.sha256(data).hexdigest() != info['sha256']:
            raise ValueError('Baseline fingerprint/hash mismatch: ' + relative)


def check_catalog(root=PROJECT):
    doc = load_catalog(root)
    verify_files(root, doc['files'])
    for dataset in doc['datasets'].values():
        path = local_path(root, dataset['path'])
        if dataset['path'] not in doc['files']:
            raise ValueError('Dataset is not fingerprinted')
        if 'version' in dataset:
            value = json.loads(path.read_text(encoding='utf-8'))
            if value['version'] != dataset['version'] or len(value['questions']) != dataset['questions']:
                raise ValueError('Question metadata differs from baseline')
    return {'baseline_id': doc['baseline_id'], 'verified_files': len(doc['files'])}


if __name__ == '__main__':
    print(json.dumps(check_catalog(), ensure_ascii=False))
