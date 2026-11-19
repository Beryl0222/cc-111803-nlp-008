# 版本说明中的兼容性影响与知识条目更新

本地文本工作区用于保存发布说明结构与接口实体相关的合成记录，并提供基础规范化和词项查看能力。

## 环境

需要 Python 3.11 或更新版本。运行程序仅使用 Python 标准库。测试依赖固定为 pytest 8.3.4，可执行 `python -m pip install -r requirements-dev.txt` 安装。

## 运行

运行 `PYTHONPATH=src python -m nlp_release_impact_index.desk_cli` 按已整理的发布条件查询受影响的集成和待核配置。接口版本以点分整数组成。集成设置中的 null 表示实现方尚未确认。通知记录关联具体集成。

条件级迁移核查使用 fixtures/migration-case.json（迁移规则与补充公告）和 fixtures/migration-registry.json（接口目录、集成配置、通知与配置快照）：

- 默认输出逐集成评估：每条规则的每个条件单独给出“满足/不适用/待查”，未确认的 null 配置记为“待查”，与已核实的“不适用”分开；同一工作项在不同集成上各自独立判断。
- 接口简称按规则声明的产品经接口目录解析，不同产品的同简称功能不会串台。
- 规则可带补充公告：`补充条件` 形成例外豁免，`撤回` 只撤回该条规则，不影响其他独立规则要求的同一项工作。
- `--amendment A-1` 按通知阶段与迁移状态分派：待发通知交通知经办人撤回，已发通知交客户成功更正，已开始的迁移交迁移负责人复核，文案更正不视为撤回迁移。
- `--explain-notice N-71` 回查某次告知的原文、发出时掌握的配置快照，以及按当前资料和补充公告重判的结果。

旧的扁平规则夹具（fixtures/work.json、fixtures/business.json）仍走原引擎，输出结构保持不变。

从项目根目录执行 `PYTHONPATH=src python -m nlp_release_impact_index.cli ingest fixtures/records.json` 导入样例，随后执行 `PYTHONPATH=src python -m nlp_release_impact_index.cli list` 查看记录。工作数据写入 `var/records.json`。业务查询使用 fixtures/business.json 中的初始资料，约定见 fixtures/business-contract.md。执行 PYTHONPATH=src python -m nlp_release_impact_index.cli business 可查看当前业务目录结果。

样例为本地合成文本。记录包含来源、修订号和原文，当前工作区对空白做统一处理，并提供字符及英文词项切分。

## 测试

执行 `python -m pytest -q` 检查规范化、记录持久化和来源筛选。
