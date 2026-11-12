"""Upgrade real 001/002 schemas through the actual current migrate-only binary."""
import pathlib,subprocess,os,uuid,datetime,hashlib,json,pymysql
APP=pathlib.Path(__file__).resolve().parents[1];OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields');SUFFIX=uuid.uuid4().hex[:8]
CFG=dict(x.split('=',1) for x in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if x and not x.startswith('#'))
ROOT_PASSWORD=os.environ.get('SCENE1_FIELD_ROOT_PASSWORD') or CFG['SCENE1_FIELD_ROOT_PASSWORD']
conn=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=ROOT_PASSWORD,autocommit=True,cursorclass=pymysql.cursors.DictCursor)
def rows(sql,args=None):
    with conn.cursor() as c:c.execute(sql,args);return c.fetchall()
def run(schema):
    env=os.environ.copy();env.update(CFG);env['SCENE1_MYSQL_DSN']=f'root:{ROOT_PASSWORD}@tcp(127.0.0.1:3306)/{schema}?parseTime=true&loc=UTC'
    p=subprocess.run([str(APP/'bin/scene1-field-upgrade.exe'),'-mode','shop','-env','nonexistent.env','-migrate-only'],cwd=APP,env=env,capture_output=True,text=True,encoding='utf-8')
    return dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
def state(schema):
    return dict(migrations=rows(f'SELECT version,checksum,applied_at FROM {schema}.schema_migrations ORDER BY version'),reason=rows(f'SELECT id,status,review_reason,reviewer_id,reviewed_at FROM {schema}.refund_applications'),constraint=rows(f"SHOW CREATE TABLE {schema}.refund_applications")[0]['Create Table'])
results=[]
build=subprocess.run(['go','build','-o','bin/scene1-field-upgrade.exe','./cmd/scene1'],cwd=APP,capture_output=True,text=True);assert build.returncode==0
try:
    for invalid in [False,True]:
        schema=f'scene1_field_upgrade_{"bad_" if invalid else "ok_"}{SUFFIX}';rows(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4');rows(f'USE `{schema}`')
        rows('CREATE TABLE schema_migrations (version varchar(40) PRIMARY KEY,checksum char(64) NOT NULL,applied_at datetime(6) NOT NULL)')
        for version,name in [('001-shop','shop.sql'),('002-shop','shop-constraints.sql')]:
            data=(APP/'internal/repository/migrations'/name).read_bytes()
            for statement in data.decode().split(';'):
                if statement.strip():rows(statement)
            rows('INSERT INTO schema_migrations VALUES(%s,%s,UTC_TIMESTAMP(6))',[version,hashlib.sha256(data).hexdigest()])
        # Populate valid cyclic fixture from previously isolated tests, never mutate the source.
        rows('SET FOREIGN_KEY_CHECKS=0')
        tables=rows('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')
        for t in tables:
            table=t['TABLE_NAME']
            if table=='schema_migrations':continue
            cols=rows('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND GENERATION_EXPRESSION="" ORDER BY ORDINAL_POSITION',[table]);names=','.join('`'+x['COLUMN_NAME']+'`' for x in cols)
            rows(f'INSERT INTO `{table}` ({names}) SELECT {names} FROM scene1_test.`{table}`')
        rows('SET FOREIGN_KEY_CHECKS=1')
        app=rows("SELECT id FROM refund_applications WHERE status IN('APPROVED','REJECTED') LIMIT 1")[0]['id']
        if invalid:rows('UPDATE refund_applications SET review_reason=NULL WHERE id=%s',[app])
        before=state(schema);first=run(schema);after=state(schema)
        if invalid:
            passed=first['exit_code']!=0 and before==after and not any(x['version']=='003-shop' for x in after['migrations'])
            second=None
        else:
            second=run(schema);last=state(schema)
            passed=first['exit_code']==second['exit_code']==0 and before['reason']==after['reason']==last['reason'] and len(after['migrations'])==3 and after==last and before['migrations']==after['migrations'][:2]
        results.append(dict(case='invalid-old-null-atomic-failure' if invalid else 'valid-old-upgrade-idempotent',schema=schema,status='PASS' if passed else 'FAIL',before=before,first_run=first,after=after,second_run=second,expected='003 fails atomically; old CHECK and migration facts retained' if invalid else '003 recorded once; 001/002 checksums and audit reasons retained; rerun no change'))
finally:conn.close()
(OUT/'upgrade-results.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=results),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('upgrade',[(r['case'],r['status']) for r in results])
