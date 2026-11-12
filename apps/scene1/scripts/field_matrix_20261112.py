"""Independent physical-field behavior probes; only newly created field_* schemas mutate.

Requires PyMySQL. Credentials are read from ignored local configuration or environment;
no credentials, session hashes or full fixture data are written to evidence.
"""
import csv, datetime as dt, decimal, hashlib, json, os, pathlib, re, sys, uuid
import pymysql

APP = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = uuid.uuid4().hex[:8]
CONFIG = dict(x.split('=', 1) for x in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if x and not x.startswith('#'))
SOURCES = {}
for scope, key in [('shop', 'SCENE1_MYSQL_DSN'), ('mock', 'SCENE1_MOCK_DSN')]:
    match = re.match(r'([^:]+):(.+)@tcp\(([^:]+):(\d+)\)/([^?]+)', CONFIG[key])
    assert match and match[5] in ['scene1_test', 'scene1_mock_test'], 'source must be prior isolated test schema'
    SOURCES[scope] = match[5]
ROOT = dict(host='127.0.0.1', port=3306, user='root', password=(os.environ.get('SCENE1_FIELD_ROOT_PASSWORD') or CONFIG['SCENE1_FIELD_ROOT_PASSWORD']), charset='utf8mb4', autocommit=True)
ADMIN = pymysql.connect(**ROOT)
RESULTS, META, WITNESSES = [], {}, {}
NOW = dt.datetime(2026, 11, 12, 0, 1, 2, 123456)

def serial(value):
    if isinstance(value, (dt.datetime, dt.date)): return value.isoformat()
    if isinstance(value, decimal.Decimal): return str(value)
    if isinstance(value, bytes): return value.hex()
    raise TypeError(type(value).__name__)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=serial, ensure_ascii=False).encode()).hexdigest()

def rows(conn, sql, args=None):
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()

def execute(conn, sql, args=None):
    with conn.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.rowcount

def snapshot(conn):
    # Server-side checksum of every persisted column: never serialize fixture secrets.
    parts={}
    for table,meta in META[conn.db.decode()].items():
        fields=','.join('COALESCE(CAST(`'+c['COLUMN_NAME']+'` AS CHAR),\'<NULL>\')' for c in meta['columns'])
        parts[table]=rows(conn,f"SELECT COUNT(*) n,COALESCE(BIT_XOR(CRC32(CONCAT_WS(CHAR(31),{fields}))),0) checksum FROM `{table}`")[0]
    return parts

def probe(conn, table, field, category, sql, args, expected='accept', codes=(), verify=None):
    schema = conn.db.decode()
    before = snapshot(conn)
    execute(conn, 'SAVEPOINT field_case')
    error, affected, warnings, value_matches = None, None, [], None
    try:
        affected = execute(conn, sql, args)
        warnings = rows(conn, 'SHOW WARNINGS')
        if verify is not None:
            value_matches=verify()
    except pymysql.MySQLError as exc:
        error = exc.args[0]
    observed = 'reject' if error else 'accept'
    expected_choices = expected.split('|')
    passed = observed in expected_choices and (not error or not codes or error in codes) and value_matches is not False
    execute(conn, 'ROLLBACK TO SAVEPOINT field_case')
    after = snapshot(conn)
    passed = passed and before == after
    record = dict(id=f'FIELD-{len(RESULTS)+1:05d}', schema=schema, table=table, field=field,
                  category=category, expected=expected, observed=observed, error_code=error,
                  expected_error_codes=list(codes), affected=affected, status='PASS' if passed else 'FAIL',
                  rollback_all_tables_equal=before == after, before_sha256=digest(before), after_sha256=digest(after),
                  changed_table_checksums={k:{'before':before[k],'after':after[k]} for k in before if before[k]!=after[k]},
                  statement_template=sql, input_sha256=digest(args), warnings=[w['Code'] for w in warnings],
                  persisted_value_matches=value_matches,
                  assertion_scope='observation-only' if '|' in expected else 'strict-behavior',
                  at=dt.datetime.now(dt.timezone.utc).isoformat())
    RESULTS.append(record)
    return record

def update_probe(conn, table, field, category, expression, value=None, expected='accept', codes=(), companions=None):
    witness = WITNESSES[(conn.db.decode(), table)]
    pk = META[conn.db.decode()][table]['pk']
    sets = [(field, expression, value)] + [(k, '%s', v) for k,v in (companions or {}).items() if k != field]
    sql = f'UPDATE `{table}` SET ' + ','.join(f'`{k}`={e}' for k,e,v in sets) + ' WHERE ' + ' AND '.join(f'`{k}`=%s' for k in pk)
    args = [v for k,e,v in sets if '%s' in e] + [witness[k] for k in pk]
    def verify():
        where=' AND '.join(f'`{k}`=%s' for k in pk)
        pk_values=[value if k==field and expression=='%s' else witness[k] for k in pk]
        found=rows(conn,f'SELECT `{field}` v FROM `{table}` WHERE '+where,pk_values)
        if len(found)!=1:return False
        actual=found[0]['v']
        if expression=='NULL':return actual is None
        if expression!='%s':return True
        if isinstance(value,decimal.Decimal):return decimal.Decimal(actual)==value
        if isinstance(value,str) and META[conn.db.decode()][table]['columns'][0]:
            typ=next(c['DATA_TYPE'] for c in META[conn.db.decode()][table]['columns'] if c['COLUMN_NAME']==field)
            if typ=='json':return json.loads(actual)==json.loads(value)
        return actual==value
    return probe(conn, table, field, category, sql, args, expected, codes, verify if expected=='accept' else None)

def init_scope(scope):
    schema = f'scene1_field_{"mock_" if scope=="mock" else ""}20261112_{SUFFIX}'
    assert re.fullmatch(r'scene1_field_(mock_)?20261112_[a-f0-9]{8}', schema)
    execute(ADMIN, f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
    conn = pymysql.connect(**dict(ROOT, database=schema))
    execute(conn, 'SET SESSION time_zone="+00:00"')
    execute(conn, "SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
    execute(conn, 'CREATE TABLE schema_migrations (version varchar(40) PRIMARY KEY, checksum char(64) NOT NULL, applied_at datetime(6) NOT NULL)')
    revisions=[('001-'+scope,scope+'.sql'),('002-'+scope,scope+'-constraints.sql')]
    if scope=='shop':revisions.append(('003-shop','shop-review-reason.sql'))
    for version, filename in revisions:
        data = (APP/'internal/repository/migrations'/filename).read_bytes()
        for statement in data.decode().split(';'):
            if statement.strip(): execute(conn, statement)
        execute(conn, 'INSERT INTO schema_migrations VALUES(%s,%s,%s)', (version,hashlib.sha256(data).hexdigest(),NOW))
    tables = [r['TABLE_NAME'] for r in rows(conn, 'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME')]
    META[schema] = {}
    for table in tables:
        columns = rows(conn, 'SELECT COLUMN_NAME,DATA_TYPE,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,CHARACTER_MAXIMUM_LENGTH,DATETIME_PRECISION,EXTRA,GENERATION_EXPRESSION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION', [table])
        constraints = rows(conn, 'SELECT tc.CONSTRAINT_NAME,tc.CONSTRAINT_TYPE,k.COLUMN_NAME,k.ORDINAL_POSITION,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME FROM information_schema.TABLE_CONSTRAINTS tc LEFT JOIN information_schema.KEY_COLUMN_USAGE k USING (CONSTRAINT_SCHEMA,TABLE_NAME,CONSTRAINT_NAME) WHERE tc.CONSTRAINT_SCHEMA=DATABASE() AND tc.TABLE_NAME=%s ORDER BY tc.CONSTRAINT_NAME,k.ORDINAL_POSITION', [table])
        checks = rows(conn, 'SELECT tc.CONSTRAINT_NAME,cc.CHECK_CLAUSE FROM information_schema.TABLE_CONSTRAINTS tc JOIN information_schema.CHECK_CONSTRAINTS cc USING(CONSTRAINT_SCHEMA,CONSTRAINT_NAME) WHERE tc.CONSTRAINT_SCHEMA=DATABASE() AND tc.TABLE_NAME=%s', [table])
        META[schema][table] = dict(scope=scope, columns=columns, constraints=constraints, checks=checks, pk=[c['COLUMN_NAME'] for c in constraints if c['CONSTRAINT_TYPE']=='PRIMARY KEY'], ddl=rows(conn,f'SHOW CREATE TABLE `{table}`')[0]['Create Table'])
    # Read only from earlier dedicated test fixture. Raw fixture stays only in process memory.
    execute(conn, 'SET FOREIGN_KEY_CHECKS=0')
    for table in tables:
        if table in ['schema_migrations','runtime_lock']: continue
        cols = [c['COLUMN_NAME'] for c in META[schema][table]['columns'] if not c['GENERATION_EXPRESSION']]
        # small bounded witness set, filtered for valid enum statuses after import if needed
        fixture = rows(ADMIN, f'SELECT '+','.join(f'`{c}`' for c in cols)+f' FROM `{SOURCES[scope]}`.`{table}`')
        if fixture:
            with conn.cursor() as cur:
                cur.executemany(f'INSERT INTO `{table}` ('+','.join(f'`{c}`' for c in cols)+') VALUES('+','.join(['%s']*len(cols))+')', [[r[c] for c in cols] for r in fixture])
    execute(conn, 'SET FOREIGN_KEY_CHECKS=1')
    # FK semantics validated after cyclic fixture import, no orphan allowed.
    for table, meta in META[schema].items():
        for fk in [c for c in meta['constraints'] if c['CONSTRAINT_TYPE']=='FOREIGN KEY']:
            c,rt,rc=fk['COLUMN_NAME'],fk['REFERENCED_TABLE_NAME'],fk['REFERENCED_COLUMN_NAME']
            bad=rows(conn,f'SELECT COUNT(*) n FROM `{table}` a LEFT JOIN `{rt}` b ON a.`{c}`=b.`{rc}` WHERE a.`{c}` IS NOT NULL AND b.`{rc}` IS NULL')[0]['n']
            assert bad==0,(table,c,'fixture orphan')
        candidates=rows(conn,f'SELECT * FROM `{table}` LIMIT 1')
        if not candidates:
            print('EMPTY_TABLE',scope,table,flush=True)
        else: WITNESSES[(schema,table)] = candidates[0]
    execute(conn,'SET autocommit=0')
    return conn

def companions(table, field, value, witness, account):
    if table=='orders' and field=='status':
        return dict(closed_at=NOW if value=='CLOSED' else None,close_reason='TIMEOUT' if value=='CLOSED' else None)
    if table=='refunds' and field=='status': return {'settled_at':NOW if value=='SUCCEEDED' else None}
    if table=='refund_applications' and field=='status':
        return dict(reviewer_id=None if value=='PENDING' else account,review_reason=None if value=='PENDING' else 'independent field review',reviewed_at=None if value=='PENDING' else NOW)
    if table=='inventory_ledger' and field=='event_type':
        da,dr,ds,dadj={'RESERVE':(-1,1,0,0),'CLOSE_RELEASE':(1,-1,0,0),'REFUND_RELEASE':(1,-1,0,0),'SHIP':(0,-1,1,0),'ADJUST':(1,0,0,1)}[value]
        return dict(delta_available=da,delta_reserved=dr,delta_shipped=ds,delta_adjustment=dadj,available_before=10,available_after=10+da,reserved_before=10,reserved_after=10+dr,shipped_before=10,shipped_after=10+ds)
    return {}

def run_scope(conn):
    schema=conn.db.decode()
    account = rows(conn,'SELECT id FROM accounts LIMIT 1')[0]['id'] if META[schema].get('accounts') else None
    for table, meta in META[schema].items():
        if (schema,table) not in WITNESSES: continue
        if table=='refund_attempts':
            WITNESSES[(schema,table)]=rows(conn,'SELECT * FROM refund_attempts ORDER BY attempt_no,id LIMIT 1')[0]
        witness = WITNESSES[(schema,table)]
        for col in meta['columns']:
            name,typ=col['COLUMN_NAME'],col['DATA_TYPE']
            if col['GENERATION_EXPRESSION']:
                update_probe(conn,table,name,'generated-readonly','%s',str(uuid.uuid4()),'reject',(3105,))
                # INFORMATION_SCHEMA serializes SQL string quotes with backslashes.
                # It is metadata, not an executable expression until those are restored.
                expression = col['GENERATION_EXPRESSION'].replace("\\'", "'")
                actual=rows(conn,f'SELECT `{name}` <=> ({expression}) equivalent FROM `{table}`')
                assert all(r['equivalent']==1 for r in actual)
                RESULTS.append(dict(id=f'FIELD-{len(RESULTS)+1:05d}',schema=schema,table=table,field=name,category='generated-all-rows-expression',expected='all generated values equal actual DDL expression',observed=f'{len(actual)} rows matched',status='PASS',rollback_all_tables_equal=True))
                continue
            update_probe(conn,table,name,'legal-roundtrip','%s',witness[name])
            # NULL/default may be forbidden by related same-row CHECK, explicitly distinguish.
            null_expected='accept' if col['IS_NULLABLE']=='YES' else 'reject'
            if ((table=='orders' and name in ['closed_at','close_reason'] and witness['status']=='CLOSED') or
                (table=='refunds' and name=='settled_at' and witness['status']=='SUCCEEDED') or
                (table=='refund_applications' and name in ['reviewer_id','review_reason','reviewed_at'] and witness['status']!='PENDING')):
                null_expected='reject'
            update_probe(conn,table,name,'null','NULL',expected=null_expected,codes=(3819,) if col['IS_NULLABLE']=='YES' else (1048,))
            default=col['COLUMN_DEFAULT']
            default_expected='reject' if default is None and col['IS_NULLABLE']=='NO' else ('reject' if default is None and null_expected=='reject' else 'accept|reject')
            default_codes=(1364,) if default is None and col['IS_NULLABLE']=='NO' else (3819,1062,1451,1452,1216)
            update_probe(conn,table,name,'default','DEFAULT',expected=default_expected,codes=default_codes)
            if typ in ['char','varchar','text','mediumtext','longtext']:
                maximum=col['CHARACTER_MAXIMUM_LENGTH']
                if maximum and maximum <= 65535:
                    update_probe(conn,table,name,'string-overflow','%s','x'*(maximum+1),'reject',(1406,))
                # Store raw SQL engine behavior; application validators carry stronger whitespace rules.
                for category,value in [('empty-string',''),('whitespace','   '),('control-character','x\x01y')]:
                    update_probe(conn,table,name,category,'%s',value,'accept|reject',codes=(3819,1451,1452,1216,1062,1366,1406))
            elif typ in ['tinyint','smallint','int','bigint']:
                maximum={'tinyint':127,'smallint':32767,'int':2147483647,'bigint':9223372036854775807}[typ]
                update_probe(conn,table,name,'integer-overflow','%s',str(maximum+1),'reject',(1264,))
                update_probe(conn,table,name,'integer-wrong-type','%s','not-integer','reject',(1366,))
                for label,value in [('zero',0),('negative',-1),('fraction',decimal.Decimal('1.5')),('scientific','1e2')]:
                    update_probe(conn,table,name,'numeric-observed-'+label,'%s',value,'accept|reject',codes=(3819,1062,1451,1452,1216,1366,1264))
                ranges={('products','unit_price_cents'):(1,1000000000),('products','initial_quantity'):(0,1000000),('products','available_quantity'):(0,1000000),('products','reserved_quantity'):(0,None),('products','shipped_quantity'):(0,None),('products','version'):(0,None),('orders','version'):(0,None),('outbox_jobs','attempt_count'):(0,None),('refund_attempts','attempt_no'):(1,None),('idempotency_records','http_status'):(200,299),('demo_clock','offset_seconds'):(0,None),('demo_clock','version'):(0,None),('simulation_rules','delay_ms'):(0,600000),('simulation_rules','repeat_count'):(1,20),('simulation_rules','remaining_uses'):(0,20),('simulation_rules','attempt_no'):(1,None),('notification_jobs','remaining_deliveries'):(0,20)}
                if name=='amount_cents':ranges[(table,name)]=(1,None)
                if (table,name) in ranges:
                    minimum,maximum=ranges[(table,name)]
                    for label,value,expected in [('minimum',minimum,'accept'),('below-minimum',minimum-1,'reject')]+([] if maximum is None else [('maximum',maximum,'accept'),('above-maximum',maximum+1,'reject')]):
                        co={}
                        if table=='products' and name in ['initial_quantity','available_quantity','reserved_quantity','shipped_quantity']:
                            vals={k:witness[k] for k in ['initial_quantity','available_quantity','reserved_quantity','shipped_quantity']};vals[name]=value
                            co['adjustment_net']=vals['available_quantity']+vals['reserved_quantity']+vals['shipped_quantity']-vals['initial_quantity']
                        if table=='orders' and name=='amount_cents':
                            co=dict(quantity=1,unit_price_cents=max(1,value))
                        update_probe(conn,table,name,'range-'+label,'%s',value,expected,(3819,1062),companions=co)
                if table=='orders' and name=='quantity':
                    for value in [-1,0,1,2,3]:
                        update_probe(conn,table,name,'quantity-member-'+str(value),'%s',value,'accept' if value in [1,2] else 'reject',(3819,),companions={'amount_cents':max(1,value*witness['unit_price_cents'])})
            elif typ=='datetime':
                update_probe(conn,table,name,'datetime-invalid','%s','2026-99-99 99:99:99','reject',(1292,))
                update_probe(conn,table,name,'datetime-microseconds','%s',NOW,'accept|reject',codes=(3819,))
            elif typ=='json':
                update_probe(conn,table,name,'json-invalid','%s','{bad','reject',(3140,))
                update_probe(conn,table,name,'json-object','%s','{"independent_field":true}')
            # Every enum is derived from this actual table's CHECK, not from hand-maintained count.
            for check in meta['checks']:
                pattern = re.compile(r'`'+re.escape(name)+r'`\s+in\s*\(([^)]+)\)',re.I)
                for match in pattern.finditer(check['CHECK_CLAUSE'].replace("\\'", "'")):
                    values=re.findall(r"(?:_utf8mb4|_utf8mb3|_latin1|_ascii)?'([^']*)'",match[1])
                    if not values: continue
                    update_probe(conn,table,name,'enum-invalid','%s','INVALID_ENUM','reject',(3819,1406))
                    for value in values:
                        co=companions(table,name,value,witness,account)
                        update_probe(conn,table,name,'enum-member-'+value,'%s',value,'accept',companions=co)
            for fk in [c for c in meta['constraints'] if c['CONSTRAINT_TYPE']=='FOREIGN KEY' and c['COLUMN_NAME']==name]:
                update_probe(conn,table,name,'foreign-key-missing','%s',str(uuid.uuid4()),'reject',(1452,1216))
                rt,rc=fk['REFERENCED_TABLE_NAME'],fk['REFERENCED_COLUMN_NAME']
                valid=rows(conn,f'SELECT `{rc}` v FROM `{rt}` LIMIT 1')[0]['v']
                update_probe(conn,table,name,'foreign-key-existing','%s',valid,'accept|reject',codes=(1062,3819))
        # Every UNIQUE/PK index: actual duplicate write, including nullable/generated keys.
        names=sorted({c['CONSTRAINT_NAME'] for c in meta['constraints'] if c['CONSTRAINT_TYPE'] in ['PRIMARY KEY','UNIQUE']})
        for index in names:
            fields=[c['COLUMN_NAME'] for c in meta['constraints'] if c['CONSTRAINT_NAME']==index]
            if any(next(x for x in meta['columns'] if x['COLUMN_NAME']==f)['GENERATION_EXPRESSION'] for f in fields):
                # Conditional uniqueness exercised by forcing another active aggregate below.
                continue
            candidates=rows(conn,f'SELECT * FROM `{table}` WHERE '+' AND '.join(f'`{f}` IS NOT NULL' for f in fields)+' LIMIT 2')
            if len(candidates)==2:
                a,b=candidates
                sql=f'UPDATE `{table}` SET '+','.join(f'`{f}`=%s' for f in fields)+' WHERE '+' AND '.join(f'`{p}`=%s' for p in meta['pk'])
                probe(conn,table,','.join(fields),'unique-'+index,sql,[a[f] for f in fields]+[b[p] for p in meta['pk']],'reject',(1062,1451,1217,3819))
            else:
                # Duplicate entire row: primary-key duplicate proves PK only; other index requires new PK.
                cols=[c['COLUMN_NAME'] for c in meta['columns'] if not c['GENERATION_EXPRESSION']]
                unique_witness=candidates[0] if candidates else witness
                vals=[unique_witness[f] for f in cols]
                if index!='PRIMARY':
                    for p in meta['pk']:
                        if p=='id' and isinstance(unique_witness[p],str): vals[cols.index(p)]=str(uuid.uuid4())
                sql=f'INSERT INTO `{table}` ('+','.join(f'`{f}`' for f in cols)+') VALUES ('+','.join(['%s']*len(cols))+')'
                probe(conn,table,','.join(fields),'unique-'+index,sql,vals,'reject',(1062,))
        print('FIELD_TABLE_DONE',schema,table,len(meta['columns']),flush=True)
    conditional_unique(conn)
    conn.rollback()

def conditional_unique(conn):
    scope=META[conn.db.decode()]
    definitions=[('payment_intents','active_order','status','READY'),('receipts','normal_order','classification','NORMAL'),('refund_applications','pending_order','status','PENDING'),('refund_attempts','active_refund','status','READY')]
    for table,field,status,value in definitions:
        if table not in scope or (conn.db.decode(),table) not in WITNESSES:continue
        owner='refund_id' if table=='refund_attempts' else 'order_id'
        candidates=rows(conn,f'SELECT * FROM `{table}` WHERE `{field}` IS NOT NULL LIMIT 1')
        if not candidates:candidates=rows(conn,f'SELECT * FROM `{table}` WHERE `{owner}` IS NOT NULL LIMIT 1')
        if not candidates:
            RESULTS.append(dict(id=f'FIELD-{len(RESULTS)+1:05d}',schema=conn.db.decode(),table=table,field=field,category='conditional-unique-active-duplicate',status='NOT_RUN',expected='one active row per owner',observed='fixture has no owner-linked row',assertion_scope='strict-behavior'))
            continue
        witness=candidates[0]
        execute(conn,'SAVEPOINT conditional_setup')
        changes={status:value}
        if table=='refund_applications':changes.update(reviewer_id=None,review_reason=None,reviewed_at=None)
        execute(conn,f'UPDATE `{table}` SET '+','.join(f'`{k}`=%s' for k in changes)+' WHERE id=%s',list(changes.values())+[witness['id']])
        original=rows(conn,f'SELECT * FROM `{table}` WHERE id=%s',[witness['id']])[0]
        values=dict(original);values['id']=str(uuid.uuid4())
        if table=='payment_intents':values['provider_request_id']=str(uuid.uuid4())
        if table=='receipts':values['provider_txn_id']=str(uuid.uuid4())
        if table=='refund_attempts':
            values['provider_request_id']=str(uuid.uuid4());values['provider_refund_id']=None
            values['attempt_no']=rows(conn,'SELECT MAX(attempt_no)+1 n FROM refund_attempts WHERE refund_id=%s',[values['refund_id']])[0]['n']
        cols=[c['COLUMN_NAME'] for c in scope[table]['columns'] if not c['GENERATION_EXPRESSION']]
        query=f'INSERT INTO `{table}` ('+','.join(f'`{c}`' for c in cols)+') VALUES ('+','.join(['%s']*len(cols))+')'
        probe(conn,table,field,'conditional-unique-active-duplicate',query,[values[c] for c in cols],'reject',(1062,))
        execute(conn,'ROLLBACK TO SAVEPOINT conditional_setup')

def write_report(conns):
    contract=json.loads((APP/'../../docs/scene1/contract-index.json').resolve().read_text(encoding='utf-8'))
    dictionary={(t['name'],f[0]):f for t in contract['tables'] for f in t['fields']}
    matrix=[]
    for schema,tables in META.items():
        for table,meta in tables.items():
            for col in meta['columns']:
                name=col['COLUMN_NAME']; relevant=[r for r in RESULTS if r['schema']==schema and r['table']==table and name in r['field'].split(',')]
                contract_table=('mock.'+table) if meta['scope']=='mock' and table!='auth_nonces' else table
                cf=dictionary.get((contract_table,name))
                strict=[r for r in relevant if r.get('assertion_scope')!='observation-only']
                matrix.append(dict(schema=schema,scope=meta['scope'],table=table,field=name,physical_type=col['COLUMN_TYPE'],nullable=col['IS_NULLABLE'],default=col['COLUMN_DEFAULT'],generated_expression=col['GENERATION_EXPRESSION'],contract_requirement=cf[5] if cf else '真实物理/技术字段，原256字段清单之外',db_case_count=len(relevant),strict_case_count=len(strict),observation_only_count=len(relevant)-len(strict),db_status='FAIL' if any(r['status']=='FAIL' for r in strict) else 'PASS' if strict else 'NOT_RUN',case_ids=' '.join(r['id'] for r in relevant),service_status='NOT_RUN',service_requirement='API不可变/跨表业务规则必须关联本轮接口与场景测试，不用SQL引擎行为替代',ddl_source='internal/repository/migrations/'+meta['scope']+'.sql; '+meta['scope']+'-constraints.sql; store.go:Migrate'))
    files={str(p.relative_to(APP)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(APP.rglob('*.go')) if not p.name.endswith('_test.go')}
    files.update({str(p.relative_to(APP)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((APP/'internal/repository/migrations').glob('*.sql'))})
    summary=dict(at=dt.datetime.now(dt.timezone.utc).isoformat(),source='real running MySQL INFORMATION_SCHEMA, actual embedded migration SQL, existing isolated fixture snapshot',schemas=list(META),table_instances=sum(len(t) for t in META.values()),physical_fields=len(matrix),cases=len(RESULTS),case_pass=sum(r['status']=='PASS' for r in RESULTS),case_fail=sum(r['status']=='FAIL' for r in RESULTS),field_db_pass=sum(r['db_status']=='PASS' for r in matrix),field_db_fail=sum(r['db_status']=='FAIL' for r in matrix),field_service_not_run=len(matrix),code_files_sha256=files,code_manifest_sha256=digest(files),environment=rows(ADMIN,'SELECT VERSION() mysql_version,@@sql_mode server_sql_mode'),limitations=['DB probes distinguish SQL storage constraints from stricter API validation; decimal and scientific literals can legally be coerced by MySQL.','Service immutability/authorization/cross-table business rows need separately linked HTTP evidence.','No business or deployment claims are inferred from physical-field PASS.','Fixture import disables FK only during cyclic loading; all FK orphan checks run after loading, probes enable FK.','All mutations are rollback-only in brand-new schemas; prior test schemas are read-only; no raw fixture/token/hash values are written.'])
    (OUT/'results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
    (OUT/'schema-metadata.json').write_text(json.dumps(META,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
    with (OUT/'field-matrix.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(matrix[0]));writer.writeheader();writer.writerows(matrix)
    (OUT/'field-matrix.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['code_files_sha256','limitations','environment']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    connections=[]
    try:
        for scope in ['shop','mock']:
            conn=init_scope(scope);connections.append(conn);run_scope(conn)
    finally:
        if META: write_report(connections)
        for conn in connections: conn.rollback();conn.close()
        ADMIN.close()
