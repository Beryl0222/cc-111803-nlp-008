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
