"""Read-only Doc Sync V0: budgets, Markdown links and the retrieval CLI pilot."""
import argparse
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import verify_doc_budgets, verify_md_links
from rag.scripts import gen_retrieval_cli


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT)
    args = parser.parse_args(argv)
    root_args = ['--root', str(args.root)]
    failed = False
    for name, run, extra in [('doc-budgets', verify_doc_budgets.main, []),
                             ('markdown-links', verify_md_links.main, []),
                             ('retrieval-cli', gen_retrieval_cli.main, ['--check'])]:
        code = run(root_args + extra)
        print(f'{"FAIL" if code else "PASS"} {name}', flush=True)
        failed |= bool(code)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
