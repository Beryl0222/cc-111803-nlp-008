from pathlib import Path

from nlp_release_impact_index.desk import (
    AMEND_CONDITION,
    AMEND_WITHDRAW,
    MIGRATION_STARTED,
    NOT_APPLICABLE,
    NOTICE_PENDING,
    NOTICE_SENT,
    RULE_APPLIES,
    RULE_EXEMPT,
    RULE_NOT_APPLICABLE,
    RULE_UNVERIFIED,
    RULE_WITHDRAWN,
    SATISFIED,
    UNVERIFIED,
    assess_registry,
    evaluate_condition,
    explain_notice,
    route_amendment,
)
from nlp_release_impact_index.desk_cli import load_case

FIXTURE = Path(__file__).parents[1] / 'fixtures'


def _case():
    import json
    return json.loads((FIXTURE / 'migration-case.json').read_text(encoding='utf-8'))


def _registry():
    import json
    return json.loads((FIXTURE / 'migration-registry.json').read_text(encoding='utf-8'))


def _row(rows, integration):
    return next(row for row in rows if row['integration'] == integration)


def _rule(row, rule_id):
    return next(item for item in row['rules'] if item['rule_id'] == rule_id)


def test_unverified_null_is_separate_from_confirmed_not_applicable():
    rows = assess_registry(_case(), _registry())
    inst2 = _rule(_row(rows, 'INST-2'), 'R-100')
    assert inst2['applicability'] == RULE_UNVERIFIED
    exemption = inst2['exemptions'][0]
    assert exemption['key'] == 'hosted'
    assert exemption['outcome'] == UNVERIFIED
    assert exemption['actual'] is None

    inst3 = _rule(_row(rows, 'INST-3'), 'R-100')
    assert inst3['applicability'] == RULE_NOT_APPLICABLE
    version_condition = next(item for item in inst3['conditions'] if item['kind'] == 'version_lt')
    assert version_condition['outcome'] == NOT_APPLICABLE
    assert version_condition['actual'] == '4.3'

    assert _row(rows, 'INST-2')['unknown'] == ['批量导出切换']
    assert _row(rows, 'INST-3')['required'] == []
    assert _row(rows, 'INST-3')['action'] == '无需发送'


def test_condition_level_outcomes_and_source_traceability():
    condition = {
        'kind': 'eq', 'key': 'gateway', 'label': '网关',
        'expected': '旧网关', 'source_ref': 'release-4.5', 'quote': '4.2 以下的旧网关。',
    }
    confirmed = evaluate_condition(condition, {'gateway': '新网关'}, [])
    missing = evaluate_condition(condition, {'gateway': None}, [])
    assert confirmed['outcome'] == NOT_APPLICABLE
    assert missing['outcome'] == UNVERIFIED
    assert confirmed['quote'] == '4.2 以下的旧网关。'

    rows = assess_registry(_case(), _registry())
    r100 = _rule(_row(rows, 'INST-1'), 'R-100')
    assert all(item['outcome'] == SATISFIED for item in r100['conditions'])
    assert r100['source_ref'] == 'release-4.5'
    assert r100['exemptions'][0]['source_ref'] == 'bulletin-hosted'


def test_interface_alias_resolves_per_product_and_does_not_cross_products():
    rows = assess_registry(_case(), _registry())
    inst1 = _row(rows, 'INST-1')
    inst5 = _row(rows, 'INST-5')

    r300_on_inst1 = _rule(inst1, 'R-300')
    feature_condition = next(item for item in r300_on_inst1['conditions'] if item['kind'] == 'feature')
    assert feature_condition['expected'] == 'bulk-export-atlas'
    assert feature_condition['actual'] == ['bulk-export-mc']
    assert feature_condition['outcome'] == NOT_APPLICABLE

    r100_on_inst5 = _rule(inst5, 'R-100')
    feature_condition = next(item for item in r100_on_inst5['conditions'] if item['kind'] == 'feature')
    assert feature_condition['expected'] == 'bulk-export-mc'
    assert feature_condition['actual'] == ['bulk-export-atlas']
    assert feature_condition['outcome'] == NOT_APPLICABLE

    assert _rule(inst5, 'R-300')['applicability'] == RULE_WITHDRAWN
    assert _rule(inst5, 'R-100')['applicability'] == RULE_NOT_APPLICABLE


def test_withdrawn_rule_does_not_retire_work_required_by_another_rule():
    rows = assess_registry(_case(), _registry())
    inst5 = _row(rows, 'INST-5')
    assert _rule(inst5, 'R-300')['status'] == '已撤回'
    assert inst5['required'] == []
    assert inst5['action'] == '无需发送'

    inst1 = _row(rows, 'INST-1')
    assert _rule(inst1, 'R-300')['applicability'] == RULE_WITHDRAWN
    assert _rule(inst1, 'R-100')['applicability'] == RULE_APPLIES
    assert inst1['required'] == ['批量导出切换']
    assert inst1['action'] == '核对当前迁移须知'


def test_same_work_on_two_integrations_is_assessed_independently():
    rows = assess_registry(_case(), _registry())
    inst1 = _row(rows, 'INST-1')
    inst2 = _row(rows, 'INST-2')
    assert inst1['required'] == ['批量导出切换']
    assert inst2['required'] == []
    assert inst2['unknown'] == ['批量导出切换']
    assert inst1['migration']['status'] == MIGRATION_STARTED
    assert inst2['migration'] is None


def test_hosted_exemption_only_changes_its_own_condition():
    rows = assess_registry(_case(), _registry())
    inst4 = _rule(_row(rows, 'INST-4'), 'R-100')
    assert inst4['applicability'] == RULE_EXEMPT
    assert inst4['exemptions'][0]['outcome'] == SATISFIED
    assert all(item['outcome'] == SATISFIED for item in inst4['conditions'])
    assert _row(rows, 'INST-4')['action'] == '无需发送'


def test_amendment_routes_pending_sent_and_started_to_different_owners():
    items = route_amendment('A-1', _case(), _registry())
    by_notice = {}
    for item in items:
        by_notice.setdefault(item['notice_ref'], []).append(item)

    n73 = by_notice['N-73']
    assert len(n73) == 1
    assert n73[0]['phase'] == NOTICE_PENDING
    assert n73[0]['owner'] == '通知经办人'
    assert n73[0]['current_applicability'] == RULE_NOT_APPLICABLE

    n74 = by_notice['N-74'][0]
    assert n74['owner'] == '通知经办人'
    assert n74['current_applicability'] == RULE_EXEMPT

    n72 = by_notice['N-72']
    assert len(n72) == 1
    assert n72[0]['phase'] == NOTICE_SENT
    assert n72[0]['owner'] == '客户成功'

    n71_owners = {item['owner'] for item in by_notice['N-71']}
    assert n71_owners == {'客户成功', '迁移负责人'}
    migration_item = next(item for item in by_notice['N-71'] if item['owner'] == '迁移负责人')
    assert migration_item['migration']['status'] == MIGRATION_STARTED
    assert '不因' in migration_item['handling'] and '撤回' in migration_item['handling']

    for item in items:
        assert item['amendment_source_ref'] == 'bulletin-hosted'
        assert item['rule_source_ref'] == 'release-4.5'


def test_withdrawal_amendment_retracts_notices_but_leaves_other_rules_intact():
    items = route_amendment('A-2', _case(), _registry())
    assert {item['notice_ref'] for item in items} == {'N-75', 'N-76'}
    assert all(item['owner'] == '通知经办人' for item in items)
    assert all(item['handling'].startswith('撤回') for item in items)
    assert all('其他独立规则' in item['handling'] for item in items)

    rows = assess_registry(_case(), _registry())
    inst1 = _row(rows, 'INST-1')
    assert _rule(inst1, 'R-300')['applicability'] == RULE_WITHDRAWN
    assert inst1['required'] == ['批量导出切换']


def test_explain_notice_reconstructs_original_text_and_config_snapshot():
    explanation = explain_notice('N-71', _case(), _registry())
    assert explanation['notice_quote'] == '请 INST-1 在升级前完成旧网关批量导出迁移。'
    assert explanation['at_send_time']['applicability'] == RULE_APPLIES
    assert explanation['at_send_time']['config_snapshot']['hosted'] is None
    assert explanation['current']['applicability'] == RULE_APPLIES
    assert explanation['current']['exemptions'][0]['actual'] is False
    assert explanation['source_refs'] == ['letter-n71', 'release-4.5', 'bulletin-hosted']

    withdrawn = explain_notice('N-75', _case(), _registry())
    assert withdrawn['at_send_time']['applicability'] == RULE_APPLIES
    assert withdrawn['current']['applicability'] == RULE_WITHDRAWN
    assert withdrawn['source_refs'] == ['letter-n75', 'release-atlas-2.0', 'bulletin-withdraw']


def test_cli_auto_selects_condition_engine_for_new_case():
    rows = load_case(FIXTURE / 'migration-case.json', FIXTURE / 'migration-registry.json')
    assert [row['integration'] for row in rows] == ['INST-1', 'INST-2', 'INST-3', 'INST-4', 'INST-5']
    assert _row(rows, 'INST-1')['required'] == ['批量导出切换']


def test_legacy_flat_case_still_uses_original_engine():
    output = load_case(FIXTURE / 'work.json', FIXTURE / 'business.json')
    assert output[0]['required'] == []
    assert output[0]['action'] == '核对是否需要更正'
    assert output[1]['unknown'] == ['批量导出切换']
    assert output[2]['action'] == '无需发送'
    assert AMEND_CONDITION == '补充条件' and AMEND_WITHDRAW == '撤回'
