from copy import deepcopy

from app import cost_tree

CONTEXT = {'contract': 'test', 'stage': 3, 'period_start': '2026-01-01',
           'period_end': '2026-05-31', 'complete_package': True}


def simple_result():
    return {'documents': [{'id': 'report', 'name': 'report.pdf', 'role': 'report', 'extraction': {
        'cost_rows': [{'stage': 3, 'year': 2025, 'values': {'16': '10.00'}},
                      {'stage': 3, 'year': 2026, 'values': {'16': '20.00'}}]}}],
        'metrics': [{'code': '0900', 'actual': '20.00', 'expected': '20.00', 'terms': []}], 'findings': []}


def flatten(node):
    return [node, *(item for child in node['children'] for item in flatten(child))]


def test_hidden_years_do_not_change_totals_or_turn_a_confirmed_period_yellow(monkeypatch):
    monkeypatch.setattr(cost_tree, 'CATEGORIES', [('0900', 'Общехозяйственные', [(16, 'Расходы')])])
    source = simple_result()
    snapshot = deepcopy(source)
    tree = cost_tree.build_cost_tree(CONTEXT, source)
    assert tree['periods'] == [2026] and tree['outside_periods'] == [2025]
    assert tree['include_out_of_scope'] is False
    assert tree['root']['actual'] == tree['root']['expected'] == '20.00'
    assert tree['root']['status'] == 'MATCH' and tree['root']['delta'] == '0.00'
    assert not any(node.get('outside_scope') for node in flatten(tree['root']))
    assert source == snapshot


def test_showing_other_years_marks_them_gray_without_inventing_confirmation(monkeypatch):
    monkeypatch.setattr(cost_tree, 'CATEGORIES', [('0900', 'Общехозяйственные', [(16, 'Расходы')])])
    source = simple_result()
    tree = cost_tree.build_cost_tree(CONTEXT, source, include_out_of_scope=True)
    assert tree['periods'] == [2025, 2026] and tree['include_out_of_scope'] is True
    assert tree['root']['actual'] == '30.00'
    assert tree['root']['expected'] is None and tree['root']['delta'] is None
    assert tree['root']['confirmed_subtotal'] == '20.00'
    assert tree['root']['status'] == 'INSUFFICIENT_DATA'
    assert 'вне проверки' in tree['root']['reason']
    nodes = {node['id']: node for node in flatten(tree['root'])}
    outside = nodes['0900.16.2025']
    assert outside['status'] == 'OUT_OF_SCOPE' and outside['outside_scope']
    assert outside['expected'] is None and outside['delta'] is None and outside['sources'] == []
    assert nodes['0900.16.2026']['status'] == 'MATCH'
    source['metrics'][0]['expected'] = '19.00'
    assert cost_tree.build_cost_tree(CONTEXT, source, include_out_of_scope=True)['root']['status'] == 'MISMATCH'


def test_missing_current_year_does_not_fall_back_to_a_different_year(monkeypatch):
    monkeypatch.setattr(cost_tree, 'CATEGORIES', [('0900', 'Общехозяйственные', [(16, 'Расходы')])])
    result = simple_result()
    result['documents'][0]['extraction']['cost_rows'] = result['documents'][0]['extraction']['cost_rows'][:1]
    result['metrics'][0]['actual'] = None
    tree = cost_tree.build_cost_tree(CONTEXT, result)
    assert tree['periods'] == [2026]
    assert tree['root']['actual'] is None and tree['root']['status'] == 'INSUFFICIENT_DATA'


def test_scope_switch_only_reads_saved_results_and_does_not_restart_ocr(client, baseline):
    case_id = baseline['id']
    before = client.get('/api/cases/' + case_id).json()
    normal = client.get(f'/api/cases/{case_id}/cost-tree').json()
    assert normal['tree'] == before['cost_tree']
    assert normal['tree']['periods'] == [2026]
    full = client.get(f'/api/cases/{case_id}/cost-tree?include_out_of_scope=true').json()
    assert full['run_id'] == before['active_run_id']
    assert full['tree']['periods'] == [2025, 2026]
    assert any(node['status'] == 'OUT_OF_SCOPE' for node in flatten(full['tree']['root']))
    after = client.get('/api/cases/' + case_id).json()
    assert after['result'] == before['result'] and after['runs'] == before['runs']
    assert after['cost_tree']['periods'] == [2026]
    assert client.get('/api/cases/missing/cost-tree').status_code == 404
    assert client.get(f'/api/cases/{case_id}/cost-tree?include_out_of_scope=invalid').status_code == 422
