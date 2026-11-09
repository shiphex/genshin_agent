"""Explicit stages for the structured RAG experiment; outputs are never reused."""
import argparse
from pathlib import Path

from . import preparation, service, stages, reporting
from Benchmarks.support.common import ROOT, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'stop', 'preflight', 'live', 'retrieval',
                                         'presentation', 'assess', 'verify', 'report'])
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--project', type=Path)
    for name in ('config', 'corpus', 'questions', 'raw-root', 'input', 'stage'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--condition', choices=['O', 'A', 'C2', 'R'])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--scenario', default='a06')
    parser.add_argument('--name')
    args = parser.parse_args()
    base = (ROOT / 'Benchmarks/outputs/agent_story/structured_rag_validation').resolve()
    run = args.run.resolve()
    if not run.is_relative_to(base) or run == base:
        parser.error('run must be a new experiment directory under Benchmarks/outputs/agent_story/structured_rag_validation')
    if args.name is not None and (Path(args.name).name != args.name or args.name in ('.', '..')):
        parser.error('name must be a single directory name')
    if args.action == 'prepare':
        if args.project is None:
            parser.error('prepare requires --project')
        output = preparation.prepare(args.project, run, config=args.config, corpus=args.corpus,
            questions=args.questions, raw_root=args.raw_root)
    elif args.action == 'start':
        binding, _, _ = preparation.load_run(run)
        service.start(binding['project'], run / 'service', binding['config_path'])
        output = run / 'service'
    elif args.action == 'stop':
        service.stop(run / 'service'); output = run / 'service/stopped.json'
    elif args.action == 'live':
        if not args.condition:
            parser.error('live requires --condition')
        output = stages.live(run, args.condition, args.repeat, args.scenario)
    elif args.action == 'retrieval':
        if args.name not in ('B-r001', 'B-final-r001'):
            parser.error('retrieval requires --name B-r001 or B-final-r001')
        output = stages.retrieval(run, args.name)
    elif args.action == 'presentation':
        output = stages.presentation(run)
    elif args.action == 'preflight':
        output = stages.preflight(run)
    elif args.action == 'assess':
        if not args.stage or not args.input:
            parser.error('assess requires --stage and --input')
        stage = args.stage.resolve()
        if stage.parent != run:
            parser.error('assessment stage must be directly inside this run')
        output = reporting.import_assessment(stage, args.input)
    elif args.action == 'verify':
        output, passed = reporting.verify(run, run / (args.name or 'verification-r001'))
        print(output)
        return 0 if passed else 1
    else:
        output = reporting.report(run, run / (args.name or 'report-r001'))
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
