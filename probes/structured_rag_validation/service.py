"""Explicit ownership of a service launched through the project's existing launcher."""
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

from Benchmarks.agent_story.providers import QwenClient
from Benchmarks.support.common import file_hash, read_json, write_json
from rag.scripts.local_model_config import load_settings
from rag.scripts.serve_local_model import server_command


def validate_deployment(actual, expected, model_sha, server_sha, reference):
    if (actual != expected or model_sha != reference['model_sha256']
            or server_sha != reference['server_sha256']):
        raise ValueError('model deployment differs from the frozen launch/model identity')


def start(project, output, config):
    project, output, config = Path(project), Path(output), Path(config)
    output.mkdir()
    expected = server_command(load_settings(config))
    expected[0] = str(Path(shutil.which(expected[0]) or expected[0]).resolve())
    model = Path(expected[expected.index('--model') + 1])
    reference = read_json(project / '.cache/worktrees/a06-diagnosis/Benchmarks/outputs/agent_story/a06_diagnosis/r003/environment/environment.json')['deployment']
    model_sha, server_sha = file_hash(model), file_hash(expected[0])
    validate_deployment(expected, expected, model_sha, server_sha, reference)
    api = load_settings(config)
    client = QwenClient({key: api.get(key) for key in ('base_url', 'model', 'api_key_env')})
    try:
        client.transport('models', None, 2)
    except Exception:
        pass
    else:
        raise ValueError('endpoint already serves a model; refusing to replace or own it')
    private = config.with_name(config.stem + '.local.json')
    identity = {'status': 'starting', 'model_sha256': model_sha, 'server_sha256': server_sha,
        'config_sha256': file_hash(config), 'private_config_sha256': file_hash(private) if private.is_file() else None,
        'launcher_sha256': file_hash(project / 'rag/scripts/serve_local_model.py'),
        'model_stat': [model.stat().st_size, model.stat().st_mtime_ns], 'model_path': str(model),
        'server_log': str((output / 'stderr.log').resolve()), 'expected_command': expected}
    log_path = output / 'stderr.log'
    with (output / 'stdout.log').open('wb') as stdout, log_path.open('wb') as stderr:
        process = subprocess.Popen([sys.executable, '-B', str(project / 'rag/scripts/serve_local_model.py'),
            '--config', str(config)], cwd=project, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    owner = None
    try:
        owner = psutil.Process(process.pid)
        identity.update(owner_pid=owner.pid, owner_create_time=owner.create_time())
        write_json(output / 'service.json', identity, exclusive=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError('model launcher exited before readiness')
            children = owner.children(recursive=True)
            servers = [p for p in children if Path(p.exe()).resolve() == Path(expected[0])]
            if len(servers) == 1:
                server = servers[0]
                actual = server.cmdline()
                actual[0] = str(Path(actual[0]).resolve())
                validate_deployment(actual, expected, model_sha, server_sha, reference)
                try:
                    models = client.transport('models', None, 2)
                    ready = api['model'] in [m['id'] for m in models['data']]
                except Exception:
                    ready = False
                if ready:
                    identity.update(status='ready', server_pid=server.pid, server_create_time=server.create_time())
                    write_json(output / 'service.json', identity)
                    return identity
            time.sleep(0.25)
        raise TimeoutError('model service did not become ready')
    except BaseException:
        if (output / 'service.json').is_file():
            stop(output)
        else:
            children = []
            if owner is not None:
                try:
                    children = owner.children(recursive=True)
                except psutil.NoSuchProcess:
                    pass
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            _, alive = psutil.wait_procs(children, timeout=10)
            for child in alive:
                child.kill()
            _, alive = psutil.wait_procs(alive, timeout=5)
            if alive:
                raise ValueError('startup cleanup incomplete')
        raise


def check(output):
    identity = read_json(Path(output) / 'service.json')
    process = psutil.Process(identity['server_pid'])
    if (identity['status'] != 'ready' or process.create_time() != identity['server_create_time']
            or file_hash(process.exe()) != identity['server_sha256']):
        raise ValueError('owned model service identity changed')
    model = Path(identity['model_path'])
    if [model.stat().st_size, model.stat().st_mtime_ns] != identity['model_stat']:
        raise ValueError('model weight file changed')
    actual = process.cmdline(); actual[0] = str(Path(actual[0]).resolve())
    if actual != identity['expected_command']:
        raise ValueError('service launch arguments changed')
    return identity


def stop(output):
    path = Path(output) / 'service.json'
    identity = read_json(path)
    try:
        owner = psutil.Process(identity['owner_pid'])
        if owner.create_time() != identity['owner_create_time']:
            raise ValueError('owner PID was reused; refusing to stop another process')
        processes = owner.children(recursive=True) + [owner]
        for process in reversed(processes):
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=10)
        for process in alive:
            process.kill()
        _, alive = psutil.wait_procs(alive, timeout=5)
        if alive:
            raise ValueError('owned service cleanup incomplete')
    except psutil.NoSuchProcess:
        if identity.get('server_pid') and psutil.pid_exists(identity['server_pid']):
            raise ValueError('owner missing but server PID remains; manual identity check required')
    write_json(Path(output) / 'stopped.json', {'stopped': True, 'owner_pid': identity['owner_pid']}, exclusive=True)
