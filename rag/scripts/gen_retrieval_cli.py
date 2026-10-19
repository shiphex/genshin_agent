"""Generate the single retrieval CLI reference; --check never writes files."""
import argparse
import ast
import html
from pathlib import Path
import sys


SOURCE = 'rag/scripts/evaluate_retrieval.py'
DOC = 'rag/README.md'
BEGIN = '<!-- BEGIN GENERATED: retrieval-cli -->'
END = '<!-- END GENERATED: retrieval-cli -->'


def argument_rows(source):
    """Accept only this pilot's direct, literal argparse definitions; fail closed."""
    tree = ast.parse(source, filename=SOURCE)
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    if len(mains) != 1:
        raise ValueError('expected one main function')
    statements = mains[0].body
    expected = ast.parse('parser = argparse.ArgumentParser(description=__doc__)').body[0]
    if ast.dump(statements[0]) != ast.dump(expected):
        raise ValueError('unsupported parser construction; review generator before continuing')
    rows, seen, calls = [], set(), []
    for stmt in statements[1:]:
        if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)
                and ast.unparse(stmt.value.func) == 'parser.parse_args'):
            break
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and ast.unparse(stmt.value.func) == 'parser.add_argument'):
            raise ValueError(f'line {stmt.lineno}: unsupported statement before parse_args')
        call = stmt.value
        calls.append(call)
        flags = [ast.literal_eval(arg) for arg in call.args]
        if not flags or any(not isinstance(f, str) or not f.startswith('-') for f in flags):
            raise ValueError(f'line {stmt.lineno}: expected literal option names')
        if seen.intersection(flags):
            raise ValueError(f'line {stmt.lineno}: duplicate option')
        seen.update(flags)
        keywords = {kw.arg: kw.value for kw in call.keywords}
        if len(keywords) != len(call.keywords) or keywords.keys() - {'type', 'default', 'help'}:
            raise ValueError(f'line {stmt.lineno}: unsupported argparse keyword')
        kind = ast.unparse(keywords['type']) if 'type' in keywords else 'str'
        if kind not in {'Path', 'int', 'float', 'str'}:
            raise ValueError(f'line {stmt.lineno}: unsupported argument type {kind}')
        default = ast.literal_eval(keywords['default']) if 'default' in keywords else None
        help_text = ast.literal_eval(keywords['help']) if 'help' in keywords else '—'
        if not isinstance(help_text, str):
            raise ValueError(f'line {stmt.lineno}: help must be literal text')
        rows.append((flags, kind, default, help_text))
    else:
        raise ValueError('missing direct parse_args call')
    all_calls = [n for n in ast.walk(mains[0]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'add_argument']
    if not rows or set(all_calls) != set(calls):
        raise ValueError('argument definitions outside the supported direct parser block')
    return rows


def cell(text):
    return html.escape(str(text), quote=False).replace('|', '&#124;').replace('`', '&#96;').replace('\n', '<br>')


def generated_table(source):
    lines = ['| 参数 | 解析类型 | 解析默认值 | 源码 help |', '| --- | --- | --- | --- |']
    for flags, kind, default, help_text in argument_rows(source):
        options = ', '.join(f'`{cell(flag)}`' for flag in flags)
        lines.append(f'| {options} | `{kind}` | `{cell(repr(default))}` | {cell(help_text)} |')
    return '\n'.join(lines)


def updated_document(document, source):
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise ValueError(f'{DOC}: expected exactly one BEGIN/END retrieval-cli marker pair')
    start, end = document.index(BEGIN), document.index(END)
    if start >= end:
        raise ValueError(f'{DOC}: reversed generation markers')
    for index, marker in [(start, BEGIN), (end, END)]:
        if (index and document[index - 1] != '\n') or document[index + len(marker):].split('\n', 1)[0].strip():
            raise ValueError(f'{DOC}: generation markers must occupy their own lines')
    # Git may check Markdown out as CRLF on Windows. Match the marker's EOL
    # so a clean checkout is fresh and manual bytes outside the block survive.
    newline = '\r\n' if document[start + len(BEGIN):].startswith('\r\n') else '\n'
    table = generated_table(source).replace('\n', newline)
    return document[:start + len(BEGIN)] + newline * 2 + table + newline * 2 + document[end:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        path = args.root / DOC
        original = path.read_bytes()
        expected = updated_document(original.decode('utf-8'),
                                    (args.root / SOURCE).read_text(encoding='utf-8-sig')).encode('utf-8')
        if original != expected:
            if args.check:
                print(f'{DOC}: stale retrieval-cli block from {SOURCE}; run rag/scripts/gen_retrieval_cli.py', file=sys.stderr)
                return 1
            path.write_bytes(expected)
        print(f'{DOC}: retrieval-cli {"verified" if args.check else "generated"}')
        return 0
    except (OSError, ValueError, SyntaxError, TypeError) as exc:
        print(f'{SOURCE} -> {DOC}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
