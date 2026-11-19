import argparse
import json
from pathlib import Path

from . import desk


def _load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_case(case_path, registry_path):
    case = json.loads(case_path.read_text(encoding='utf-8'))
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    return assess_case(case, registry)


def _has_condition_engine(case):
    first = case['rules'][0]
    return 'conditions' in first


def assess_case(case, registry):
    if _has_condition_engine(case):
        return desk.assess_registry(case, registry)
    return desk.assess(case, registry)


def main():
    parser = argparse.ArgumentParser(description='核查集成迁移的客户通知')
    parser.add_argument('--case', type=Path, default=Path('fixtures/work.json'))
    parser.add_argument('--registry', type=Path, default=Path('fixtures/business.json'))
    parser.add_argument('--explain-notice', help='回查指定通知（通知编号）发出时的原文与配置快照')
    parser.add_argument('--amendment', help='落地指定补充公告，按通知阶段与迁移状态分派事项')
    args = parser.parse_args()
    try:
        case = _load(args.case)
        registry = _load(args.registry)
        if args.explain_notice:
            result = desk.explain_notice(args.explain_notice, case, registry)
        elif args.amendment:
            result = desk.route_amendment(args.amendment, case, registry)
        else:
            result = assess_case(case, registry)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
