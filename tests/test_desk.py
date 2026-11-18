from pathlib import Path

from nlp_release_impact_index.desk_cli import load_case


def test_unverified_config_is_separate_from_irrelevant_other_product():
    fixture = Path(__file__).parents[1] / 'fixtures'
    output = load_case(fixture / 'work.json', fixture / 'business.json')
    assert output[0]['required'] == []
    assert output[0]['action'] == '核对是否需要更正'
    assert output[1]['unknown'] == ['批量导出切换']
    assert output[2]['action'] == '无需发送'
