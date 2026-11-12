"""Extract every physical column from actual production migration and migration runner.

This produces a NOT_RUN inventory, never a claim that DDL was executed.
"""
import pathlib,re,json,csv,hashlib
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
OUT.mkdir(parents=True,exist_ok=True)
contract=json.loads((APP/'../../docs/scene1/contract-index.json').resolve().read_text(encoding='utf-8'))
dictionary={(t['name'],f[0]):f for t in contract['tables'] for f in t['fields']}
inventory=[]
def item(scope,table,field,definition,path,line,technical=False):
    key='mock.'+table if scope=='mock' and table!='auth_nonces' else table
    cf=dictionary.get((key,field))
    inventory.append(dict(scope=scope,table=table,field=field,definition=definition,kind='technical' if technical else 'generated' if 'GENERATED ALWAYS' in definition else 'business',source=str(path.relative_to(APP)),line=line,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),contract_requirement=cf[5] if cf else 'actual technical/generated field outside original logical dictionary',runtime_status='NOT_RUN'))
for scope in ['shop','mock']:
    path=APP/'internal/repository/migrations'/f'{scope}.sql';table=None
    for line_number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        match=re.match(r'CREATE TABLE IF NOT EXISTS `([^`]+)`',line)
        if match:table=match[1]
        match=re.match(r'`([^`]+)` (.*)',line)
        if match and table:item(scope,table,match[1],match[2].rstrip(','),path,line_number)
        if 'CREATE TABLE IF NOT EXISTS runtime_lock' in line:item(scope,'runtime_lock','id','smallint PRIMARY KEY',path,line_number,True)
    path=APP/'internal/repository/store.go'
    source=path.read_text(encoding='utf-8')
    match=re.search(r'CREATE TABLE IF NOT EXISTS schema_migrations \((.*?)\)',source)
    assert match
    line=source[:match.start()].count('\n')+1
    for field,definition in [('version','varchar(40) PRIMARY KEY'),('checksum','char(64) NOT NULL'),('applied_at','datetime(6) NOT NULL')]:item(scope,'schema_migrations',field,definition,path,line,True)
assert len(inventory)==272,len(inventory)
(OUT/'source-field-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'source-field-inventory.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    wr=csv.DictWriter(fh,fieldnames=list(inventory[0]));wr.writeheader();wr.writerows(inventory)
print('source inventory:',len(inventory),'columns /',len({(r['scope'],r['table']) for r in inventory}),'table instances; runtime NOT_RUN')
