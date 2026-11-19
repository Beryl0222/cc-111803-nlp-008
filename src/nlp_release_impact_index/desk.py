def version(value):
    return tuple(int(part) for part in value.split('.'))


class ScopeCheck:
    @staticmethod
    def applies(condition, account):
        if condition['product'] != account['product'] or condition['gateway'] != account['gateway']:
            return False
        if version(account['api']) >= version(condition['before']):
            return False
        if account['bulk'] is None:
            return None
        return account['bulk'] == condition['bulk']


class MigrationWork:
    def __init__(self, rules):
        self.rules = rules

    def needs(self, account):
        confirmed = set()
        unknown = set()
        for rule in self.rules:
            applies = ScopeCheck.applies(rule, account)
            if applies is True:
                confirmed.add(rule['work'])
            elif applies is None:
                unknown.add(rule['work'])
        return confirmed, unknown - confirmed


class CustomerNotices:
    def __init__(self, notices):
        self.notices = {notice['integration']: notice for notice in notices}

    def outcome(self, integration, required, unknown):
        notice = self.notices.get(integration)
        if required:
            todo = '核对当前迁移须知'
        elif unknown:
            todo = '待核实际配置'
        elif notice and notice['phase'] == '已发':
            todo = '核对是否需要更正'
        else:
            todo = '无需发送'
        return {'integration': integration, 'required': sorted(required), 'unknown': sorted(unknown),
                'action': todo, 'notice': notice}


def assess(case, registry):
    work = MigrationWork(case['rules'])
    notices = CustomerNotices(registry['notices'])
    return [notices.outcome(account['id'], *work.needs(account)) for account in registry['integrations']]


# 条件级迁移核查引擎：每条迁移规则由若干可单独回查的条件合取而成，
# 补充公告以修订（补充豁免条件或撤回）形式挂在规则上。

SATISFIED = '满足'
NOT_APPLICABLE = '不适用'
UNVERIFIED = '待查'

RULE_APPLIES = '适用'
RULE_UNVERIFIED = '待查'
RULE_NOT_APPLICABLE = '不适用'
RULE_EXEMPT = '例外豁免'
RULE_WITHDRAWN = '已撤回'

AMEND_CONDITION = '补充条件'
AMEND_WITHDRAW = '撤回'

NOTICE_PENDING = '待发'
NOTICE_SENT = '已发'
MIGRATION_STARTED = '已开始'


def _resolve_catalog_entry(catalog, product, alias):
    for entry in catalog:
        if entry['product'] == product and entry['alias'] == alias:
            return entry
    return None


def evaluate_condition(condition, account, catalog, rule_product=None):
    """判定单个条件，返回条件级结论。未确认的配置记为待查，与核实不适用分开。"""
    kind = condition['kind']
    key = condition['key']
    result = {'key': key, 'label': condition['label'], 'kind': kind,
              'source_ref': condition['source_ref'], 'quote': condition.get('quote')}
    if kind == 'version_lt':
        actual = account.get('api')
        result['expected'] = '<' + condition['expected']
        result['actual'] = actual
        if actual is None:
            result['outcome'] = UNVERIFIED
        else:
            result['outcome'] = SATISFIED if version(actual) < version(condition['expected']) else NOT_APPLICABLE
        return result
    if kind == 'feature':
        # 接口简称按规则声明的产品解析，避免不同产品同简称的功能串台
        entry = _resolve_catalog_entry(catalog, rule_product or account.get('product'), condition['alias'])
        used_features = account.get('features')
        result['alias'] = condition['alias']
        result['expected'] = entry['feature'] if entry else None
        result['actual'] = used_features
        if entry is None or used_features is None:
            result['outcome'] = UNVERIFIED if used_features is None else NOT_APPLICABLE
        else:
            result['outcome'] = SATISFIED if entry['feature'] in used_features else NOT_APPLICABLE
        return result
    actual = account.get(key)
    result['expected'] = condition['expected']
    result['actual'] = actual
    if actual is None:
        result['outcome'] = UNVERIFIED
    else:
        result['outcome'] = SATISFIED if actual == condition['expected'] else NOT_APPLICABLE
    return result


def _amendments_for_rule(rule_id, amendments):
    return [amendment for amendment in amendments if amendment['rule_id'] == rule_id]


def evaluate_rule(rule, account, catalog, amendments):
    """评估一条迁移规则对某个集成的适用性，含补充公告带来的豁免与撤回。"""
    linked = _amendments_for_rule(rule['id'], amendments)
    rule_product = rule.get('product')
    base_results = [evaluate_condition(condition, account, catalog, rule_product)
                    for condition in rule['conditions']]
    exemption_results = []
    for amendment in linked:
        if amendment['type'] == AMEND_CONDITION:
            exemption = evaluate_condition(amendment['condition'], account, catalog, rule_product)
            exemption['amendment'] = amendment['id']
            exemption['source_ref'] = amendment['source_ref']
            exemption['quote'] = amendment.get('quote')
            exemption_results.append(exemption)
    if any(amendment['type'] == AMEND_WITHDRAW for amendment in linked):
        applicability = RULE_WITHDRAWN
    elif any(item['outcome'] == NOT_APPLICABLE for item in base_results):
        applicability = RULE_NOT_APPLICABLE
    elif any(item['outcome'] == UNVERIFIED for item in base_results):
        applicability = RULE_UNVERIFIED
    elif any(item['outcome'] == SATISFIED for item in exemption_results):
        applicability = RULE_EXEMPT
    elif any(item['outcome'] == UNVERIFIED for item in exemption_results):
        applicability = RULE_UNVERIFIED
    else:
        applicability = RULE_APPLIES
    return {
        'rule_id': rule['id'],
        'work': rule['work'],
        'feature': rule.get('feature'),
        'status': RULE_WITHDRAWN if applicability == RULE_WITHDRAWN else '现行',
        'applicability': applicability,
        'conditions': base_results,
        'exemptions': exemption_results,
        'amendments': [amendment['id'] for amendment in linked],
        'source_ref': rule['source_ref'],
        'quote': rule.get('quote'),
    }


def _action_for(required, unknown, notice):
    if required:
        return '核对当前迁移须知'
    if unknown:
        return '待核实际配置'
    if notice and notice['phase'] == NOTICE_SENT:
        return '核对是否需要更正'
    return '无需发送'


def assess_registry(case, registry):
    """逐集成评估全部规则；同一工作项在不同集成上各自独立判断。"""
    catalog = registry.get('catalog', [])
    amendments = case.get('amendments', [])
    notices = {notice['integration']: notice for notice in registry['notices']}
    rows = []
    for account in registry['integrations']:
        rule_results = [evaluate_rule(rule, account, catalog, amendments) for rule in case['rules']]
        required = {row['work'] for row in rule_results if row['applicability'] == RULE_APPLIES}
        unknown = {row['work'] for row in rule_results if row['applicability'] == RULE_UNVERIFIED} - required
        notice = notices.get(account['id'])
        rows.append({
            'integration': account['id'],
            'product': account['product'],
            'required': sorted(required),
            'unknown': sorted(unknown),
            'action': _action_for(required, unknown, notice),
            'notice': notice,
            'migration': account.get('migration'),
            'rules': rule_results,
        })
    return rows


def _find(rows, key, value, label):
    for row in rows:
        if row[key] == value:
            return row
    raise ValueError(f'{label} {value} 不存在')


def route_amendment(amendment_id, case, registry):
    """补充公告落地时，按通知阶段与迁移状态把事项分派给对应负责人。"""
    amendment = _find(case.get('amendments', []), 'id', amendment_id, '补充公告')
    rule = _find(case['rules'], 'id', amendment['rule_id'], '迁移规则')
    catalog = registry.get('catalog', [])
    items = []
    for notice in registry['notices']:
        if notice['rule_id'] != rule['id']:
            continue
        account = _find(registry['integrations'], 'id', notice['integration'], '集成')
        current = evaluate_rule(rule, account, catalog, case.get('amendments', []))
        evidence = {
            'amendment': amendment['id'],
            'amendment_source_ref': amendment['source_ref'],
            'rule_id': rule['id'],
            'rule_source_ref': rule['source_ref'],
            'notice_ref': notice['ref'],
            'notice_source_ref': notice['source_ref'],
            'integration': account['id'],
            'current_applicability': current['applicability'],
        }
        if amendment['type'] == AMEND_WITHDRAW:
            items.append({**evidence, 'phase': notice['phase'], 'owner': '通知经办人',
                          'handling': '撤回该条说明对应的通知，撤回不影响其他独立规则要求的工作'})
            continue
        if notice['phase'] == NOTICE_PENDING:
            items.append({**evidence, 'phase': NOTICE_PENDING, 'owner': '通知经办人',
                          'handling': '撤回待发通知，并按更正后的条件重新判定是否需要告知'})
            continue
        items.append({**evidence, 'phase': NOTICE_SENT, 'owner': '客户成功',
                      'handling': '发送补充公告的更正告知，更正通知文案'})
        migration = account.get('migration')
        if migration and migration.get('status') == MIGRATION_STARTED:
            items.append({**evidence, 'phase': NOTICE_SENT, 'owner': '迁移负责人',
                          'handling': '已开始的迁移不因通知文案更正而撤回，按更正后的条件复核是否继续',
                          'migration': migration})
    return items


def explain_notice(notice_ref, case, registry):
    """回查某次告知：发出时依据的原文与配置快照，以及按当前资料的重判结果。"""
    notice = _find(registry['notices'], 'ref', notice_ref, '通知')
    rule = _find(case['rules'], 'id', notice['rule_id'], '迁移规则')
    account = _find(registry['integrations'], 'id', notice['integration'], '集成')
    catalog = registry.get('catalog', [])
    at_send_time = evaluate_rule(rule, notice['snapshot'], catalog, amendments=[])
    current = evaluate_rule(rule, account, catalog, case.get('amendments', []))
    source_refs = [notice['source_ref'], rule['source_ref']]
    source_refs.extend(amendment['source_ref'] for amendment in _amendments_for_rule(rule['id'], case.get('amendments', [])))
    return {
        'notice_ref': notice['ref'],
        'integration': account['id'],
        'phase': notice['phase'],
        'rule_id': rule['id'],
        'work': rule['work'],
        'notice_source_ref': notice['source_ref'],
        'notice_quote': notice.get('quote'),
        'at_send_time': {
            'applicability': at_send_time['applicability'],
            'conditions': at_send_time['conditions'],
            'config_snapshot': notice['snapshot'],
        },
        'current': {
            'applicability': current['applicability'],
            'conditions': current['conditions'],
            'exemptions': current['exemptions'],
            'amendments': current['amendments'],
        },
        'source_refs': source_refs,
    }
