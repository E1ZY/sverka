import json
from pathlib import Path

import pytest

from scripts.edge_case_support import run_fixture

ROOT=Path(__file__).resolve().parent.parent
CATALOG=json.loads((ROOT/'cases/catalog.json').read_text(encoding='utf-8'))
PARAMS=[pytest.param(item,id=item['id'],marks=pytest.mark.xfail(strict=True,reason=item['known_limitation']) if item['known_limitation'] else [])
        for item in CATALOG['cases']]


@pytest.mark.generated
@pytest.mark.parametrize('item',PARAMS)
def test_generated_documents_through_upload_and_worker(client,item):
    result=run_fixture(client,ROOT/'cases'/item['manifest'])
    assert not result['failures'], '\n'.join(result['failures'])
