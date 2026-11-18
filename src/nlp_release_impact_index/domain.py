import json
from pathlib import Path

def load_facts(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize(facts):
    integrations = {entry['id'] for entry in facts['integrations'] if entry['product'] == facts['product']}
    return [notice['ref'] for notice in facts['notices']
            if notice['integration'] in integrations and notice['phase'] == '待发']
