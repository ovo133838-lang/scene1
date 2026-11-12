"""Independent HTTP/DB test runner. Only scene1_test + scene1_mock_test.

Reuses the developer scenario driver after independent inspection, adds separate
auth/route/DB probes, records its own outputs without overwriting developer evidence.
"""
import csv, datetime, hashlib, importlib.util, json, os, pathlib, re, subprocess, sys, time, urllib.request, urllib.error

APP = pathlib.Path(__file__).resolve().parents[1]
OUT = APP / 'evidence/independent-testing'
OUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('scene1_driver', APP / 'scripts/functional.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
EXE = APP / 'bin/scene1-independent.exe'

def start():
    for mode, port in [('shop',18090),('mock',18091)]:
        env=os.environ.copy();env['SCENE1_PORT']=str(port)
        log=open(APP/'bin'/f'independent-{mode}.log','ab')
        f.PROCS.append(subprocess.Popen([str(EXE),'-mode',mode,'-env','.env.test.local'],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    for _ in range(80):
        try:f.request('/health/ready');return
        except (OSError,AssertionError):time.sleep(.2)
    raise AssertionError('independent services failed to start; inspect ignored logs')
f.start=start

def db_sql(key,sql):
    m=re.fullmatch(r'([^:]+):([^@]+)@tcp\(([^:]+):(\d+)\)/([^?]+)(?:\?.*)?',f.CFG[key])
    assert m and m[5] in ['scene1_test','scene1_mock_test'],'test-only schema guard'
    env=os.environ.copy();env['MYSQL_PWD']=m[2]
    return subprocess.run(['C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe','--no-defaults','-N','-B','--default-character-set=utf8mb4','-h',m[3],'-P',m[4],'-u',m[1],m[5]],input=sql,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)

def db_probes():
    keys=['SCENE1_MYSQL_DSN','SCENE1_MOCK_DSN']
    # Every documented field is listed separately; structure is distinguished
    # from behavior so no successful DESCRIBE can imply all boundary cases passed.
    schema={}
    for k in keys:
        p=db_sql(k,"SELECT table_name,column_name,column_type,is_nullable,COALESCE(column_default,'<NULL>') FROM information_schema.columns WHERE table_schema=DATABASE() ORDER BY table_name,ordinal_position;")
        assert p.returncode==0,p.stderr
        (OUT/('shop-schema.tsv' if k==keys[0] else 'mock-schema.tsv')).write_text(p.stdout,encoding='utf-8')
        schema[k]={tuple(x.split('\t')[:2]):x.split('\t')[2:] for x in p.stdout.splitlines()}
        constraints=db_sql(k,"SELECT table_name,constraint_name,constraint_type FROM information_schema.table_constraints WHERE table_schema=DATABASE() ORDER BY table_name,constraint_name;")
        assert constraints.returncode==0,constraints.stderr
        (OUT/('shop-constraints.tsv' if k==keys[0] else 'mock-constraints.tsv')).write_text(constraints.stdout,encoding='utf-8')
    rows=[]
    matrix=(APP.parents[1]/'docs/scene1/04-test-matrix.md').read_text(encoding='utf-8')
    for line in matrix.splitlines():
        if not line.startswith('| FIELD-'):continue
        parts=[v.strip() for v in line.split('|')][1:-1]
        ident,field=parts[:2];kind=keys[1] if field.startswith('mock.') else keys[0]
        tab,col=field.removeprefix('mock.').split('.')
        obs=schema[kind].get((tab,col));assert obs,(ident,field,'column missing')
        rows.append({'id':ident,'field':field,'structure':'PASS','physical_type':obs[0],'nullable':obs[1],'default':obs[2],'full_behavior_matrix':'NOT_RUN','note':'Structure inspected; scenario tests do not prove every field boundary/immutability combination.'})
    assert len(rows)==256,len(rows)
    # auth_nonces is instantiated on both sides, not omitted from metadata.
    assert all(('auth_nonces','nonce') in schema[k] for k in keys)
    with (OUT/'field-results.csv').open('w',newline='',encoding='utf-8-sig') as dest:
        w=csv.DictWriter(dest,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    cases=[
      ('DB01','accounts','role',"'ROOT'",3819),
      ('DB02','products','unit_price_cents','0',3819),
      ('DB03','products','available_quantity','-1',3819),
      ('DB04','products','version','-1',3819),
      ('DB05','orders','quantity','3',3819),
      ('DB06','orders','amount_cents','amount_cents+1',3819),
      ('DB07','orders','buyer_id',"'00000000-0000-0000-0000-000000000001'",1452),
      ('DB08','inventory_ledger','available_after','available_after+1',3819),
      ('DB09','refund_attempts','attempt_no','0',3819),
      ('DB10','sessions','account_id','NULL',1048),
      ('DB11','products','sku',"(SELECT sku FROM (SELECT sku FROM products ORDER BY id DESC LIMIT 1) q)",1062),
    ]
    results=[]
    for ident,table,col,value,code in cases:
        before=db_sql(keys[0],f'SELECT COUNT(*) FROM `{table}`;');assert int(before.stdout.strip())>0,(ident,'no fixture')
        p=db_sql(keys[0],f'START TRANSACTION; UPDATE `{table}` SET `{col}`={value} ORDER BY id LIMIT 1; ROLLBACK;')
        # A mysql error closes the connection and rolls back the transaction.
        expected_codes=[1452,1216] if code==1452 else [code]
        assert p.returncode!=0 and any(f'ERROR {n} ' in p.stderr for n in expected_codes),(ident,p.stdout,p.stderr)
        results.append({'id':ident,'status':'PASS','table':table,'field':col,'expected_mysql_error':code,'actual':p.stderr.strip()})
    for ident,col,value in [('DB12','repeat_count','0'),('DB13','delay_ms','600001'),('DB14','remaining_uses','21')]:
        p=db_sql(keys[1],f'START TRANSACTION; UPDATE simulation_rules SET `{col}`={value} LIMIT 1; ROLLBACK;')
        assert p.returncode!=0 and 'ERROR 3819 ' in p.stderr,(ident,p.stdout,p.stderr)
        results.append({'id':ident,'status':'PASS','field':col,'actual':p.stderr.strip()})
    # SQL-only independent checks against active orders and shipping facts.
    p=db_sql(keys[0],"SELECT p.id,p.reserved_quantity,COALESCE(SUM(CASE WHEN o.status IN('PENDING_PAYMENT','PENDING_SHIPMENT','REFUND_REVIEW','REFUND_PROCESSING') THEN o.quantity ELSE 0 END),0) AS expected FROM products p LEFT JOIN orders o ON o.product_id=p.id GROUP BY p.id HAVING p.reserved_quantity<>expected; SELECT p.id,p.shipped_quantity,COALESCE(SUM(CASE WHEN o.status='SHIPPED' THEN o.quantity ELSE 0 END),0) AS expected FROM products p LEFT JOIN orders o ON o.product_id=p.id GROUP BY p.id HAVING p.shipped_quantity<>expected;")
    assert p.returncode==0 and not p.stdout.strip(),('actual order-vs-stock mismatch',p.stdout,p.stderr)
    results.append({'id':'DB15','status':'PASS','assertion':'reserved and shipped balances equal underlying order quantities'})
    (OUT/'db-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS 256 field metadata rows + 15 real database probes',flush=True)

def snapshot(name):
    paths=[p for base in ['cmd','internal','web','migrations','scripts'] for p in (APP/base).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    docroot=APP.parents[1]/'docs/scene1'
    paths+=list(docroot.rglob('*.md'))
    data={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'git_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=APP,text=True).strip(),'go':subprocess.check_output(['go','version'],cwd=APP,text=True).strip(),'files':{str(p.relative_to(APP.parents[1])).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    snapshot('version-start.json');passed=False
    try:
        f.start()
        for n in [1,2]:f.run_round(n)
        before=f.request('/api/v1/operator/summary',role='operator');f.stop();f.start();f.login();after=f.request('/api/v1/operator/summary',role='operator')
        assert before['total_received_cents']==after['total_received_cents'] and before['refunded_cents']==after['refunded_cents']
        print('PASS independent restart persistence',flush=True)
        db_probes();passed=True
    finally:
        f.stop();snapshot('version-end.json')
        (OUT/'http-regression.json').write_text(json.dumps({'passed':passed,'rounds_requested':2,'driver':'scripts/functional.py independently inspected and reused','events':f.EVENTS},ensure_ascii=False,indent=2),encoding='utf-8')
