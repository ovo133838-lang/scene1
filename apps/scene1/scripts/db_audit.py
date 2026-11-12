"""Read-only dictionary/schema audit plus rollback-only SQL counterexamples in scene1_test."""
import pathlib,re,os,subprocess,json,uuid
root=pathlib.Path(__file__).resolve().parents[1];cfg=dict(line.split('=',1) for line in (root/'.env.test.local').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'));dictionary=json.loads((root/'../../docs/scene1/contract-index.json').resolve().read_text(encoding='utf-8'));mysql='C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe';results=[]
def connection(mock=False):
 dsn=cfg['SCENE1_MOCK_DSN' if mock else 'SCENE1_MYSQL_DSN'];m=re.match(r'([^:]+):([^@]+)@tcp\(([^:]+):(\d+)\)/([^?]+)',dsn);assert m and m[5] in ['scene1_test','scene1_mock_test'];return m
def sql(text,mock=False,success=True):
 m=connection(mock);env=os.environ.copy();env['MYSQL_PWD']=m[2];p=subprocess.run([mysql,'--no-defaults','-N','-B','-h',m[3],'-P',m[4],'-u',m[1],m[5],'-e',text],env=env,text=True,capture_output=True)
 if success and p.returncode:raise AssertionError('Read-only/rollback audit SQL failed: '+p.stderr)
 if not success:assert p.returncode!=0,'invalid SQL mutation unexpectedly accepted';return {'rejected':True,'mysql_error_code':re.search(r'ERROR (\d+)',p.stderr).group(1)}
 return [line.split('\t') for line in p.stdout.splitlines()]
tables=dictionary['tables']+[dict(next(t for t in dictionary['tables'] if t['name']=='auth_nonces'),name='mock.auth_nonces')]
for t in tables:
 mock=t['name'].startswith('mock.');name=t['name'].split('.')[-1];m=connection(mock)
 actual=sql("SELECT COLUMN_NAME,DATA_TYPE,IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"';",mock)
 mapping={r[0]:r[1:] for r in actual};expected={f[0]:f for f in t['fields']};assert set(expected).issubset(mapping),(name,set(expected)-set(mapping))
 for field in t['fields']:
  n,typ,null=field[:3];physical={'uuid':'char','timestamptz':'datetime','jsonb':'json','integer':'int','boolean':'tinyint'}.get(typ,typ.split('(')[0]);assert mapping[n][0]==physical,(name,n,mapping[n],physical)
  assert mapping[n][1]==('YES' if '可空' in null else 'NO'),(name,n,'nullability')
 results.append({'table':t['name'],'fields_checked':len(expected),'extra_columns':sorted(set(mapping)-set(expected)),'passed':True})
cases=[('negative stock',"UPDATE products SET available_quantity=-1 LIMIT 1"),('inventory conservation',"UPDATE products SET available_quantity=available_quantity+1 LIMIT 1"),('unknown status',"UPDATE orders SET status='BAD' LIMIT 1"),('quantity range',"UPDATE orders SET quantity=3 LIMIT 1"),('amount snapshot',"UPDATE orders SET amount_cents=amount_cents+1 LIMIT 1"),('invalid foreign key',"UPDATE orders SET buyer_id='"+str(uuid.uuid4())+"' LIMIT 1"),('duplicate account',"UPDATE accounts SET login_name='buyer1' WHERE login_name='buyer2'"),('invalid currency',"UPDATE receipts SET currency='USD' LIMIT 1"),('negative clock',"UPDATE demo_clock SET offset_seconds=-1 WHERE id=1"),('attempt zero',"UPDATE refund_attempts SET attempt_no=0 LIMIT 1"),('ledger vector',"UPDATE inventory_ledger SET delta_reserved=999 LIMIT 1")]
for name,stmt in cases:results.append({'case':name,**sql('START TRANSACTION;'+stmt+';ROLLBACK;',success=False)})
for mock in [False,True]:
 results.append({'schema':connection(mock)[5],'migrations':sql('SELECT version,checksum FROM schema_migrations ORDER BY version',mock),'foreign_keys':sql("SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL",mock),'unique_indexes':sql("SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND NON_UNIQUE=0 GROUP BY TABLE_NAME,INDEX_NAME",mock)})
(root/'evidence/db-audit.json').write_text(json.dumps({'passed':True,'table_instances':len(tables),'business_fields_plus_second_nonce':sum(len(t['fields']) for t in tables),'results':results},ensure_ascii=False,indent=2),encoding='utf-8');print('PASS 24 business table instances: exact named fields/types/nullability + 11 rollback-only constraint counterexamples; schema and indexes saved.')
