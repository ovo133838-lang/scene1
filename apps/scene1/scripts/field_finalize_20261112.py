"""Produce evidence indexes; never infer execution from file presence."""
import pathlib,json,csv,collections,hashlib,datetime
APP=pathlib.Path(__file__).resolve().parents[1];OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
result=json.loads((OUT/'semantics-results.json').read_text(encoding='utf-8'));assert result['passed'] and result['source_unchanged']
assert all(hashlib.sha256((APP/k).read_bytes()).hexdigest()==v for k,v in result['code_files_sha256'].items()),'production changed'
inventory=json.loads((OUT/'source-field-inventory.json').read_text(encoding='utf-8'))
dimensions=json.loads((OUT/'field-dimensions.json').read_text(encoding='utf-8'))
links=[]
for field in inventory:
    if field['table'] in ['schema_migrations','runtime_lock']:continue
    selected=[x for x in result['links'] if all(x[k]==field[k] for k in ['scope','table','field'])]
    assert selected and all(x['status']=='PASS' for x in selected)
    ids=list(dict.fromkeys(x['case_id'] for x in selected));rounds={c['round'] for c in result['cases'] if c['id'] in ids};assert rounds=={1,2}
    dim=next(x for x in dimensions if x['dimension']=='service-immutability-cross-table' and all(x[k]==field[k] for k in ['scope','table','field']))
    links.append(dict(scope=field['scope'],table=field['table'],field=field['field'],status='PASS',rounds='1 2',requirement=field['contract_requirement'],actual_predicates=dim['reason'],case_ids=' '.join(ids),source=field['source'],line=field['line'],evidence='semantics-results.json / field_semantics_20261112.py; http-field-results.json; api-input-links.json'))
(OUT/'service-field-links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'service-field-links.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    w=csv.DictWriter(fh,fieldnames=list(links[0]));w.writeheader();w.writerows(links)
summary=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),physical_columns=len(inventory),service_columns_with_two_round_evidence=len(links),semantic_checkpoints=len(result['cases']),semantic_pass=sum(x['status']=='PASS' for x in result['cases']),schemas=result['schemas'],dimension_counts=dict(collections.Counter(x['status'] for x in dimensions)),source_unchanged=True,code_files_sha256=result['code_files_sha256'],upgrade_cases=json.loads((OUT/'upgrade-results.json').read_text(encoding='utf-8'))['cases'])
# Upgrade detail stays in its original; summary needs only case status and schema.
summary['upgrade_cases']=[{k:r[k] for k in ['case','status','schema']} for r in summary['upgrade_cases']]
(OUT/'completion-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='code_files_sha256'},ensure_ascii=False))
