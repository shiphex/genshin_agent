"""按显式 manifest 检查中文与英文混排文档的字数预算；只读，不修正文档。"""
import argparse
import json
from pathlib import Path
import re
import sys


# 常用、兼容及补充平面的汉字；ASCII 连续词独立计数。
UNITS = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]|[A-Za-z0-9_]+')


def count_units(text):
    """汉字逐字、ASCII 字母数字下划线连续词计一单位；包含原始 Markdown。"""
    return len(UNITS.findall(text))


def unique_entries(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('预算重复条目：' + key)
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='仓库根目录；默认由脚本位置定位')
    parser.add_argument('--list', action='store_true', help='展示用量，超限不影响退出码；配置错误仍失败')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        budgets = json.loads((root / 'scripts/doc-budgets.manifest.json').read_text(encoding='utf-8-sig'),
                             object_pairs_hook=unique_entries)
        if not isinstance(budgets, dict) or not budgets:
            raise ValueError('预算 manifest 必须是非空的路径到正整数映射')
        rows = []
        for name, ceiling in budgets.items():
            if type(ceiling) is not int or ceiling <= 0:
                raise ValueError(f'预算必须为正整数：{name} = {ceiling!r}')
            path = (root / name).resolve()
            if Path(name).is_absolute() or not path.is_relative_to(root) or path == root:
                raise ValueError('预算路径必须位于仓库内：' + name)
            if not path.is_file():
                raise ValueError('预算文件缺失：' + name)
            count = count_units(path.read_text(encoding='utf-8-sig'))
            rows.append((name, count, ceiling))
    except (OSError, ValueError) as exc:
        print('文档预算检查失败：' + str(exc), file=sys.stderr)
        return 1
    overflow = False
    for name, count, ceiling in rows:
        exceeded = count > ceiling
        overflow |= exceeded
        print(f'{"超限" if exceeded else "通过"}  {count} / {ceiling}  余量 {ceiling - count}  {name}')
    if overflow:
        print('超限处理：先归位、再精简；必要时说明理由调整 manifest。')
    return int(overflow and not args.list)


if __name__ == '__main__':
    raise SystemExit(main())
