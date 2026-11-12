"""Independent real HTTP transitions with explicit persistent-field assertions.

Only newly named isolated schemas are written. Secrets are asserted in memory,
never serialized. No arbitrary SQL mutation is used to stand in for a service rule.
"""
import pathlib, importlib.util, os, subprocess, json, time, uuid, hashlib, re, datetime, hmac, urllib.request, urllib.error, traceback
import pymysql
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
spec=importlib.util.spec_from_file_location('functional',APP/'scripts/functional.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
suffix=uuid.uuid4().hex[:8];DB='scene1_field_sem_'+suffix;MDB='scene1_field_sem_mock_'+suffix
ROOT_PASSWORD=os.environ.get('SCENE1_FIELD_ROOT_PASSWORD') or f.CFG['SCENE1_FIELD_ROOT_PASSWORD']
CFG=dict(f.CFG);f.BASE='http://127.0.0.1:18130';f.MOCK='http://127.0.0.1:18131'
CFG.update(SCENE1_MYSQL_DSN=f'root:{ROOT_PASSWORD}@tcp(127.0.0.1:3306)/{DB}?parseTime=true&loc=UTC',SCENE1_MOCK_DSN=f'root:{ROOT_PASSWORD}@tcp(127.0.0.1:3306)/{MDB}?parseTime=true&loc=UTC',SCENE1_SHOP_URL=f.BASE,SCENE1_MOCK_URL=f.MOCK);f.CFG=CFG
conn=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=ROOT_PASSWORD,autocommit=True,cursorclass=pymysql.cursors.DictCursor)
procs=[];logs=[];CASES=[];LINKS=[];round_no=0;success=False
def query(q,args=None):
    with conn.cursor() as c:c.execute(q,args);return c.fetchall()
def one(table,id,scope='shop'):
    rows=query(f'SELECT * FROM `{DB if scope=="shop" else MDB}`.`{table}` WHERE id=%s',(id,));assert len(rows)==1;return rows[0]
def record(name,tables,fn,note=''):
    start=len(f.EVENTS)
    try:
        observed=fn();status='PASS';error=None
    except Exception:
        observed=None;status='FAIL';error=traceback.format_exc()
    cid=f'SEM-R{round_no}-{len(CASES)+1:04}-{name}'
    CASES.append(dict(id=cid,round=round_no,status=status,assertion=name,note=note,observed=observed,error=error,http_event_end=len(f.EVENTS)))
    for scope,table,fields in tables:
        for field in fields.split():LINKS.append(dict(scope=scope,table=table,field=field,case_id=cid,status=status,assertion=name,note=note))
    if status!='PASS':raise AssertionError(cid+' '+error)
    return observed
def ok(condition,message):assert condition,message
def uuid_ok(v):return str(uuid.UUID(v))==v
def dt(v):return isinstance(v,datetime.datetime)
def technical(row,fields):
    for k in fields:
        if k=='id':assert uuid_ok(row[k]),('uuid',k)
        elif k.endswith('_at') and row[k] is not None:assert dt(row[k]),('timestamp',k)
def ledger_check():
    rows=query(f'SELECT * FROM {DB}.inventory_ledger ORDER BY created_at,id')
    assert rows
    for r in rows:
        technical(r,['id','created_at']);assert r['reason'].strip() and len(r['reason'])<=500
        assert r['available_after']==r['available_before']+r['delta_available']
        assert r['reserved_after']==r['reserved_before']+r['delta_reserved']
        assert r['shipped_after']==r['shipped_before']+r['delta_shipped']
        if r['event_type']=='ADJUST':
            assert (r['delta_reserved'],r['delta_shipped'],r['delta_adjustment'])==(0,0,r['delta_available']);assert r['order_id'] is None and r['refund_id'] is None;assert one('accounts',r['actor_id'])['role']=='OPERATOR'
        else:
            o=one('orders',r['order_id']);q=o['quantity'];assert r['product_id']==o['product_id'];assert r['event_key']==r['event_type']+':'+o['id']
            vectors={'RESERVE':(-q,q,0,0),'SHIP':(0,-q,q,0),'CLOSE_RELEASE':(q,-q,0,0),'REFUND_RELEASE':(q,-q,0,0)}
            assert tuple(r[k] for k in ['delta_available','delta_reserved','delta_shipped','delta_adjustment'])==vectors[r['event_type']]
            if r['event_type']=='REFUND_RELEASE':assert one('refunds',r['refund_id'])['kind']=='NORMAL'
            else:assert r['refund_id'] is None
            if r['actor_id']:assert one('accounts',r['actor_id'])['role']==('WAREHOUSE' if r['event_type']=='SHIP' else 'BUYER')
    for p in query(f'SELECT * FROM {DB}.products'):
        rr=[r for r in rows if r['product_id']==p['id']]
        for before,after in zip(rr,rr[1:]):
            assert tuple(before[k+'_after'] for k in ['available','reserved','shipped'])==tuple(after[k+'_before'] for k in ['available','reserved','shipped'])
        if rr:assert tuple(rr[-1][k+'_after'] for k in ['available','reserved','shipped'])==tuple(p[k+'_quantity'] for k in ['available','reserved','shipped'])
        assert p['initial_quantity']+p['adjustment_net']==p['available_quantity']+p['reserved_quantity']+p['shipped_quantity']
        assert sum(r['delta_adjustment'] for r in rr)==p['adjustment_net']
    return {'entries':len(rows),'vectors':['ADJUST','RESERVE','SHIP','CLOSE_RELEASE','REFUND_RELEASE'],'sequence':'every consecutive before/after and final product balances'}
def invariant_tables():
    # Read a single transaction snapshot so worker commits cannot split a relation.
    conn.begin()
    try:
        tables={t:query(f'SELECT * FROM {DB}.{t}') for t in ['accounts','sessions','products','orders','payment_intents','receipts','refund_applications','refunds','refund_attempts','shipments','payment_anomalies','anomaly_actions','channel_notifications','idempotency_records','outbox_jobs','audit_events','auth_nonces','demo_clock']}
        by={t:{r['id']:r for r in rows} for t,rows in tables.items()}
        for p in tables['products']:
            technical(p,['id','created_at','updated_at']);assert p['sku'] and p['name'].strip() and 1<=p['unit_price_cents']<=1000000000 and p['sale_status'] in ['ON_SHELF','OFF_SHELF'];assert p['version']>=0 and p['updated_at']>=p['created_at']
        for o in tables['orders']:
            technical(o,['id','created_at','updated_at','expires_at','paid_at','closed_at','refunded_at','shipped_at'])
            assert by['accounts'][o['buyer_id']]['role']=='BUYER';assert o['product_id'] in by['products'];assert o['order_no'].startswith('SO')
            assert o['amount_cents']==o['unit_price_cents']*o['quantity'];assert o['expires_at']-o['created_at']==datetime.timedelta(minutes=10);assert o['version']>=0
            if o['normal_receipt_id']:
                r=by['receipts'][o['normal_receipt_id']];assert r['order_id']==o['id'] and r['classification']=='NORMAL' and r['amount_cents']==o['amount_cents'];assert o['paid_at'] is not None and o['paid_at']<o['expires_at']
            if o['active_application_id']:
                a=by['refund_applications'][o['active_application_id']];assert a['order_id']==o['id'] and a['buyer_id']==o['buyer_id'];assert a['status'] in ['PENDING','APPROVED']
            if o['status']=='CLOSED':assert o['closed_at'] and o['close_reason'] in ['TIMEOUT','BUYER_CANCELLED']
            if o['status']=='REFUNDED':assert o['refunded_at'] is not None and not any(s['order_id']==o['id'] for s in tables['shipments'])
        for p in tables['payment_intents']:
            o=by['orders'][p['order_id']];assert p['amount_cents']==o['amount_cents'] and p['currency']=='CNY';assert uuid_ok(p['provider_request_id']);assert p['active_order']==(p['order_id'] if p['status']!='FAILED' else None)
            if p['provider_txn_id']:
                cp=query(f'SELECT * FROM {MDB}.channel_payments WHERE txn_id=%s',(p['provider_txn_id'],));assert len(cp)==1 and cp[0]['request_id']==p['provider_request_id'] and cp[0]['order_ref']==o['id']
            technical(p,['id','created_at','updated_at','last_queried_at'])
            if p['status']=='FAILED':assert p['failure_code'] in ['CHANNEL_FAILED','CLOSED_WITH_NO_CHANNEL_RECORD']
        for r in tables['receipts']:
            assert r['provider']=='MOCK' and r['currency']=='CNY';technical(r,['id','created_at','verified_at','provider_paid_at'])
            cp=query(f'SELECT * FROM {MDB}.channel_payments WHERE txn_id=%s',(r['provider_txn_id'],));assert len(cp)==1;cp=cp[0]
            assert cp['merchant_ref']=='scene1' and cp['status']=='SUCCEEDED' and cp['amount_cents']==r['amount_cents'] and cp['order_ref']==r['external_order_ref'];assert r['proof_type'] in ['SIGNED_NOTIFY','CHANNEL_QUERY']
            if r['order_id']:assert by['orders'][r['order_id']]['id']==r['external_order_ref']
            if r['payment_intent_id']:assert by['payment_intents'][r['payment_intent_id']]['order_id']==r['order_id']
            assert r['normal_order']==(r['order_id'] if r['classification']=='NORMAL' else None)
        for a in tables['refund_applications']:
            o=by['orders'][a['order_id']];assert a['buyer_id']==o['buyer_id'];assert a['reason'].strip();assert a['pending_order']==(a['order_id'] if a['status']=='PENDING' else None)
            if a['status']=='PENDING':assert a['reviewer_id'] is None and a['review_reason'] is None and a['reviewed_at'] is None
            else:assert by['accounts'][a['reviewer_id']]['role']=='SUPPORT' and a['review_reason'].strip() and dt(a['reviewed_at'])
            technical(a,['id','created_at'])
        for r in tables['refunds']:
            receipt=by['receipts'][r['receipt_id']];assert r['order_id']==receipt['order_id'] and r['amount_cents']==receipt['amount_cents'];assert by['accounts'][r['created_by']]['role']=='SUPPORT'
            attempt=by['refund_attempts'][r['current_attempt_id']];assert attempt['refund_id']==r['id'];assert attempt['attempt_no']==max(x['attempt_no'] for x in tables['refund_attempts'] if x['refund_id']==r['id'])
            if r['kind']=='NORMAL':
                a=by['refund_applications'][r['application_id']];assert a['order_id']==r['order_id'] and a['status']=='APPROVED' and receipt['classification']=='NORMAL' and r['anomaly_id'] is None
            else:
                a=by['payment_anomalies'][r['anomaly_id']];assert a['verification']=='FUNDS_CONFIRMED' and a['receipt_id']==receipt['id'] and receipt['classification']!='NORMAL' and r['application_id'] is None
                assert not query(f'SELECT id FROM {DB}.inventory_ledger WHERE refund_id=%s',(r['id'],))
            assert (r['status']=='SUCCEEDED')==(r['settled_at'] is not None)
            if r['status']=='SUCCEEDED':assert r['success_at'] is not None and attempt['status']=='SUCCEEDED'
            technical(r,['id','success_at','settled_at','created_at','updated_at'])
        for a in tables['refund_attempts']:
            r=by['refunds'][a['refund_id']];assert uuid_ok(a['provider_request_id']);assert a['active_refund']==(a['refund_id'] if a['status'] in ['READY','PROCESSING','UNKNOWN'] else None)
            if a['provider_refund_id']:
                cr=query(f'SELECT * FROM {MDB}.channel_refunds WHERE refund_id=%s',(a['provider_refund_id'],));assert len(cr)==1;cr=cr[0];assert cr['request_id']==a['provider_request_id'] and cr['txn_id']==by['receipts'][r['receipt_id']]['provider_txn_id'] and cr['amount_cents']==r['amount_cents']
            if a['status']=='FAILED':assert a['failure_code'] and a['resolved_at'] is not None
            if a['status']=='SUCCEEDED':assert a['resolved_at'] and json.loads(a['proof_redacted'])['status']=='SUCCEEDED'
            technical(a,['id','created_at','sent_at','resolved_at','last_queried_at'])
        for sh in tables['shipments']:
            o=by['orders'][sh['order_id']];assert o['status']=='SHIPPED' and o['normal_receipt_id'] and o['shipped_at']==sh['shipped_at'];assert sh['shipped_at']>=o['paid_at'];assert by['accounts'][sh['operator_id']]['role']=='WAREHOUSE';assert sh['carrier']=='教学承运方' and sh['tracking_no'].startswith('TEST-');technical(sh,['id','shipped_at'])
        for a in tables['payment_anomalies']:
            assert a['dedupe_key'] and a['summary'];technical(a,['id','created_at','updated_at','resolved_at'])
            if a['receipt_id']:assert by['receipts'][a['receipt_id']]['order_id']==a['order_id']
            if a['refund_id']:assert by['refunds'][a['refund_id']]['anomaly_id']==a['id'] or a['type']=='REFUND_RESULT_CONFLICT'
            if a['first_notification_id']:assert a['first_notification_id'] in by['channel_notifications']
            if a['status']=='RESOLVED':assert a['resolved_at'] and a['resolved_reason'];assert a['resolved_by'] is None or by['accounts'][a['resolved_by']]['role']=='SUPPORT'
        for a in tables['anomaly_actions']:
            assert a['anomaly_id'] in by['payment_anomalies'];assert a['reason'].strip();assert isinstance(json.loads(a['evidence_redacted']),dict);assert a['from_status'] in ['OPEN','VERIFIED','REFUNDING','RESOLVED'] and a['to_status'] in ['OPEN','VERIFIED','REFUNDING','RESOLVED'];technical(a,['id','created_at'])
            if a['actor_id']:assert by['accounts'][a['actor_id']]['role']=='SUPPORT'
        for n in tables['channel_notifications']:
            assert n['provider']=='MOCK';assert re.fullmatch('[a-f0-9]{64}',n['payload_hash']);payload=json.loads(n['payload_redacted']);assert isinstance(payload,dict)
            for column,key in [('provider_event_id','event_id'),('external_order_ref','order_ref'),('provider_txn_id','txn_id'),('provider_refund_id','refund_id')]:assert n[column]==payload.get(key)
            assert n['claimed_amount_cents'] is None or n['claimed_amount_cents']>0
            if n['receipt_id']:assert by['receipts'][n['receipt_id']]['provider_txn_id']==n['provider_txn_id']
            if n['refund_attempt_id']:assert by['refund_attempts'][n['refund_attempt_id']]['provider_refund_id']==n['provider_refund_id']
            if n['process_result'] in ['ACCEPTED','DUPLICATE']:assert n['auth_valid']
            technical(n,['id','received_at','processed_at']);assert n['reason_code']==n['process_result'] and n['processed_at']>=n['received_at']
        for j in tables['outbox_jobs']:
            table='payment_intents' if j['kind'].startswith('PAYMENT') else 'refund_attempts';assert j['aggregate_id'] in by[table];parts=j['job_key'].split(':');assert parts[0] in (["PAYMENT_SEND","PAYMENT_QUERY"] if table=='payment_intents' else ["REFUND_SEND","REFUND_QUERY"]) and parts[1]==j['aggregate_id'] and uuid_ok(parts[2]);assert j['attempt_count']>=0
            technical(j,['id','created_at','updated_at','next_run_at','lease_until'])
            if j['status']=='RUNNING':assert j['lease_until'] is not None
        for a in tables['audit_events']:
            assert uuid_ok(a['request_id']) and a['reason'];assert isinstance(json.loads(a['before_redacted']),dict) and isinstance(json.loads(a['after_redacted']),dict)
            if a['actor_kind']=='USER':assert a['actor_id'] in by['accounts']
            else:assert a['actor_id'] is None
            entity={'PRODUCT':'products','ORDER':'orders','PAYMENT':'payment_intents','REFUND':'refunds','SHIPMENT':'shipments','ANOMALY':'payment_anomalies'}[a['entity_type']];assert a['entity_id'] in by[entity] and a['action']
            technical(a,['id','created_at'])
        for a in tables['auth_nonces']:
            assert a['key_id']=='mock-to-shop' and re.fullmatch('[A-Za-z0-9_-]{16,64}',a['nonce']) and a['expires_at']>a['created_at'];technical(a,['id','created_at','expires_at'])
        return {t:len(v) for t,v in tables.items()}
    finally:conn.rollback()
def all_fields(table,scope='shop'):
    return ' '.join(x['field'] for x in INVENTORY if x['scope']==scope and x['table']==table)
INVENTORY=json.loads((OUT/'source-field-inventory.json').read_text(encoding='utf-8'))
VERSION_START={k:hashlib.sha256((APP/k).read_bytes()).hexdigest() for k in json.loads((OUT/'version-end.json').read_text(encoding='utf-8'))['code_files_sha256']}
assert VERSION_START==json.loads((OUT/'version-end.json').read_text(encoding='utf-8'))['code_files_sha256'],'source differs from field DB/API linked version'
def check_relations(label):
    tested=['products','orders','payment_intents','receipts','refund_applications','refunds','refund_attempts','shipments','payment_anomalies','anomaly_actions','channel_notifications','outbox_jobs','audit_events','auth_nonces']
    record(label,[('shop',t,all_fields(t)) for t in tested],invariant_tables,'Explicit non-vacuous positive checkpoints plus same-order/actor/proof/amount/state/time/key joins; detailed predicates in field_semantics_20261112.py. Nullable branch coverage separately retained in cases.')
def replay_signature(event):
    path='/api/v1/channel/payment-notifications';raw=json.dumps(event,separators=(',',':')).encode();stamp=str(int(time.time()));nonce=str(uuid.uuid4());kid='mock-to-shop';dk=hmac.new(CFG['SCENE1_HMAC_SECRET'].encode(),kid.encode(),hashlib.sha256).digest();canonical='\n'.join(['POST',path,stamp,nonce,hashlib.sha256(raw).hexdigest()]);sig=hmac.new(dk,canonical.encode(),hashlib.sha256).hexdigest()
    headers={'Content-Type':'application/json','X-Key-Id':kid,'X-Timestamp':stamp,'X-Nonce':nonce,'X-Signature':sig}
    outcomes=[]
    for expected in [200,401]:
        req=urllib.request.Request(f.BASE+path,data=raw,method='POST',headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=15) as resp:status=resp.status;out=json.load(resp)
        except urllib.error.HTTPError as e:status=e.code;out=json.load(e)
        assert status==expected,(status,out);outcomes.append({'status':status,'result':out});f.EVENTS.append({'method':'POST','path':path,'status':status,'result':out,'probe':'same nonce replay; signed headers not serialized'})
    assert len(query(f'SELECT id FROM {DB}.auth_nonces WHERE key_id=%s AND nonce=%s',(kid,nonce)))==1
    return {'statuses':[x['status'] for x in outcomes],'single_nonce':True}
try:
    query(f'CREATE DATABASE `{DB}`');query(f'CREATE DATABASE `{MDB}`')
    exe=APP/'bin/scene1-field-semantics.exe';build=subprocess.run(['go','build','-o',str(exe),'./cmd/scene1'],cwd=APP,capture_output=True,text=True);(OUT/'semantics-build.log').write_text(build.stdout+build.stderr,encoding='utf-8');assert build.returncode==0
    for mode,port in [('shop',18130),('mock',18131)]:
        env=os.environ.copy();env.update(CFG);env['SCENE1_PORT']=str(port);log=open(OUT/('semantics-'+mode+'.log'),'ab');logs.append(log);procs.append(subprocess.Popen([str(exe),'-mode',mode,'-env','nonexistent.env'],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    for _ in range(100):
        try:f.request('/health/ready');break
        except Exception:time.sleep(.2)
    for round_no in [1,2]:
        f.login();p=f.stock(40)
        def auth():
            expected={'buyer1':'BUYER','buyer2':'BUYER','buyer3':'BUYER','operator':'OPERATOR','warehouse':'WAREHOUSE','support':'SUPPORT'}
            for name,role in expected.items():
                rows=query(f'SELECT * FROM {DB}.accounts WHERE login_name=%s',(name,));assert len(rows)==1;a=rows[0];technical(a,['id','created_at','updated_at']);assert a['role']==role and a['enabled']==1 and a['display_name'];assert a['password_hash']!=CFG['SCENE1_PASSWORD'] and len(a['password_hash'])>40
                digest=hashlib.sha256(f.TOKENS[name].encode()).hexdigest();ss=query(f'SELECT * FROM {DB}.sessions WHERE token_hash=%s',(digest,));assert len(ss)==1;s=ss[0];assert s['account_id']==a['id'] and s['revoked_at'] is None and s['expires_at']>s['created_at'];technical(s,['id','created_at','expires_at'])
            return {'authenticated_seed_accounts':6,'token_storage':'SHA256 digest matches actual login token; values not serialized'}
        record('login-account-session-binding',[('shop','accounts',all_fields('accounts')),('shop','sessions',all_fields('sessions'))],auth)
        idem=f.key();o=f.create(p,idem=idem);created=one('orders',o['id']);same=f.create(p,idem=idem);assert same['id']==o['id']
        def idem_check():
            ir=query(f'SELECT * FROM {DB}.idempotency_records WHERE request_key=%s',(idem,));assert len(ir)==1;r=ir[0];assert r['operation']=='create_order:' and r['resource_type']=='orders' and r['resource_id']==o['id'] and r['http_status']==201;assert r['actor_id']==created['buyer_id'];body={'product_id':p['id'],'quantity':1};canonical=json.dumps(body,separators=(',',':'),sort_keys=True).encode();assert r['request_hash']==hashlib.sha256(b':'+canonical).hexdigest();technical(r,['id','created_at']);assert len(query(f'SELECT id FROM {DB}.inventory_ledger WHERE order_id=%s',(o['id'],)))==1
            return {'resource_id':o['id'],'duplicate_reservations':0,'body_hash_matches':True}
        record('idempotency-real-request-key-hash-resource',[('shop','idempotency_records',all_fields('idempotency_records'))],idem_check)
        f.request('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':2},role='buyer1',idem=idem,expect=409)
        f.request('/api/v1/buyer/orders/'+o['id'],role='buyer2',expect=404);f.request('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'越权'},role='buyer2',expect=404);f.request('/api/v1/operator/summary',role='buyer1',expect=403)
        p=f.product();f.request('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'name':'字段语义快照-'+str(round_no),'unit_price_cents':'12000','sale_status':'OFF_SHELF','reason':'真实字段快照不可变'},role='operator')
        def snapshot_check():
            now=one('orders',o['id']);assert all(now[k]==created[k] for k in ['buyer_id','product_id','sku_snapshot','name_snapshot','unit_price_cents','quantity','amount_cents','created_at','expires_at','order_no']);changed=one('products',p['id']);assert changed['unit_price_cents']==12000 and changed['name']=='字段语义快照-'+str(round_no) and changed['sale_status']=='OFF_SHELF' and changed['version']==p['version']+1;assert changed['reserved_quantity']==p['reserved_quantity'] and changed['available_quantity']==p['available_quantity'];return {'snapshot_price':now['unit_price_cents'],'current_price':changed['unit_price_cents'],'ownership_404_and_role_403_no_mutation':True}
        record('snapshot-and-ownership-immutability',[('shop','orders','buyer_id product_id sku_snapshot name_snapshot unit_price_cents quantity amount_cents created_at expires_at order_no'),('shop','products',all_fields('products'))],snapshot_check)
        f.pay(o);ev=f.receipt_event(o)
        record('signed-nonce-replay-only-once',[('shop','auth_nonces',all_fields('auth_nonces'))],lambda:replay_signature(ev))
        def callback_digest():
            raw=json.dumps(ev,separators=(',',':')).encode();digest=hashlib.sha256(raw).hexdigest();rows=query(f'SELECT * FROM {DB}.channel_notifications WHERE payload_hash=%s',(digest,));assert len(rows)==2 and sorted(x['process_result'] for x in rows)==['DUPLICATE','REPLAYED_SIGNATURE'];assert all(x['claimed_amount_cents']==int(ev['amount_cents']) and x['provider_event_id']==ev['event_id'] and x['external_order_ref']==o['id'] for x in rows);return {'raw_body_digest_rows':2,'auth_flags':sorted(bool(x['auth_valid']) for x in rows)}
        record('callback-original-hash-claim-redaction',[('shop','channel_notifications','payload_hash claimed_amount_cents provider_event_id external_order_ref auth_valid process_result reason_code')],callback_digest)
        for _ in range(2):assert f.request('/api/v1/channel/payment-notifications','POST',ev,signed=True)['result']=='DUPLICATE'
        assert f.request('/api/v1/channel/payment-notifications','POST',dict(ev,order_ref=str(uuid.uuid4())),signed=True)['result']=='TXN_CONFLICT'
        sh=f.ship(o);f.ship(o,409);check_relations('normal-paid-shipped-duplicates-conflict-relations')
        p=f.product();f.request('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'unit_price_cents':'10000','sale_status':'ON_SHELF','reason':'恢复场景定价'},role='operator')
        payment_fail_order=f.create();f.rule(payment_fail_order,'EXPLICIT_FAIL','PAYMENT');f.request('/api/v1/buyer/orders/'+payment_fail_order['id']+'/payments','POST',{},role='buyer1',expect=202);f.poll(lambda:query(f'SELECT * FROM {DB}.payment_intents WHERE order_id=%s',(payment_fail_order['id'],)),lambda x:len(x)==1 and x[0]['status']=='FAILED');failed_intent=query(f'SELECT * FROM {DB}.payment_intents WHERE order_id=%s',(payment_fail_order['id'],))[0]
        def pay_failure():
            assert failed_intent['failure_code']=='CHANNEL_FAILED' and failed_intent['active_order'] is None and one('orders',payment_fail_order['id'])['normal_receipt_id'] is None;return {'status':'FAILED','failure_code':failed_intent['failure_code'],'no_receipt':True}
        record('payment-failure-no-receipt-active-slot-freed',[('shop','payment_intents','failure_code status active_order provider_request_id provider_txn_id')],pay_failure)
        f.cancel(payment_fail_order)
        o=f.create();f.pay(o);a=f.apply(o);f.ship(o,409);f.approve(a,'REJECT');assert one('orders',o['id'])['active_application_id'] is None
        first=one('refund_applications',a['id']);a2=f.apply(o);assert a2['id']!=a['id'];assert one('refund_applications',a['id'])==first
        f.rule(o,'EXPLICIT_FAIL',attempt_no=1);r=f.approve(a2)['refund'];f.poll(lambda:one('refunds',r['id']),lambda x:x['status']=='FAILED');failed=query(f'SELECT * FROM {DB}.refund_attempts WHERE refund_id=%s',(r['id'],))[0];check_relations('rejection-history-and-explicit-refund-failure')
        f.request('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'明确失败后新尝试'},role='support',expect=202);done=f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED');attempts=query(f'SELECT * FROM {DB}.refund_attempts WHERE refund_id=%s ORDER BY attempt_no',(r['id'],));assert [x['attempt_no'] for x in attempts]==[1,2] and attempts[0]==failed and attempts[0]['provider_request_id']!=attempts[1]['provider_request_id']
        proof=f.request('/mock/v1/refunds/by-request/'+attempts[-1]['provider_request_id']+'?merchant_ref=scene1',signed=True,mock=True);event={'event_id':f.key(),'merchant_ref':'scene1','txn_id':f.receipt_event(o)['txn_id'],'request_id':proof['request_id'],'refund_id':proof['refund_id'],'amount_cents':r['amount_cents'],'currency':'CNY','status':'SUCCEEDED','occurred_at':proof['refunded_at']}
        for _ in range(2):assert f.request('/api/v1/channel/refund-notifications','POST',event,signed=True)['result']=='DUPLICATE'
        assert f.request('/api/v1/channel/refund-notifications','POST',dict(event,amount_cents='1'),signed=True)['result']=='RESULT_CONFLICT';check_relations('normal-refund-two-attempts-repeated-result-conflict')
        o=f.create();f.pay(o);a=f.apply(o);f.rule(o,'TIMEOUT_AFTER_SUCCESS');r=f.approve(a)['refund'];f.poll(lambda:one('refunds',r['id']),lambda x:x['status']=='UNKNOWN',seconds=8);before=query(f'SELECT * FROM {DB}.refund_attempts WHERE refund_id=%s',(r['id'],));f.ship(o,409);f.request('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'未知不得新退款'},role='support',expect=409);after=query(f'SELECT * FROM {DB}.refund_attempts WHERE refund_id=%s',(r['id'],));assert len(before)==len(after)==1 and before[0]['provider_request_id']==after[0]['provider_request_id'];check_relations('unknown-refund-no-new-attempt-no-shipment')
        def outbox_retry():
            jobs=query(f'SELECT * FROM {DB}.outbox_jobs WHERE aggregate_id=%s',(before[0]['id'],));assert len(jobs)==1;j=jobs[0];assert j['status']=='RETRY' and j['last_error_code']=='CHANNEL_UNCONFIRMED' and j['kind']=='REFUND_QUERY' and j['lease_until'] is None and j['attempt_count']>=1 and j['next_run_at']>j['created_at'];assert j['job_key'].startswith('REFUND_SEND:'+before[0]['id']+':');return {'converted_kind':j['kind'],'fixed_job_key_origin':'REFUND_SEND','attempt_count':j['attempt_count'],'status':j['status']}
        record('outbox-lost-response-query-same-aggregate',[('shop','outbox_jobs',all_fields('outbox_jobs'))],outbox_retry)
        f.request('/api/v1/support/refunds/'+r['id']+'/query','POST',{'reason':'查询同一未知尝试'},role='support',expect=202);f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED');check_relations('unknown-query-same-request-settled')
        o=f.create();f.rule(o,'TIMEOUT_AFTER_SUCCESS','PAYMENT');f.request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202);f.cancel(o);f.cancel(o)
        found=f.poll(lambda:f.lists('/api/v1/support/payment-anomalies','support',type='LATE_PAYMENT'),lambda xs:any(x['order_id']==o['id'] for x in xs));a=next(x for x in found if x['order_id']==o['id']);f.request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'未核实不退款'},role='support',expect=409);f.request('/api/v1/support/payment-anomalies/'+a['id']+'/verify','POST',{'reason':'渠道核实本商户实收'},role='support');r=f.request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'迟到款原路整单退款'},role='support',expect=202);f.poll(lambda:f.request('/api/v1/support/payment-anomalies/'+a['id'],role='support'),lambda x:x['status']=='RESOLVED');r2=f.request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'重复不新增退款'},role='support',expect=202);assert r['id']==r2['id'];assert one('orders',o['id'])['status']=='CLOSED';check_relations('late-payment-verified-exception-no-second-release')
        record('inventory-vectors-history-continuity',[('shop','inventory_ledger',all_fields('inventory_ledger')),('shop','products','initial_quantity available_quantity reserved_quantity shipped_quantity adjustment_net')],ledger_check)
        def audit_trace():
            ids={e['result'].get('meta',{}).get('request_id') for e in f.EVENTS if isinstance(e.get('result'),dict)};rows=query(f'SELECT * FROM {DB}.audit_events WHERE actor_kind="USER"');matched=[r for r in rows if r['request_id'] in ids];assert matched and any(r['action']=='CREATE' for r in matched) and any(r['action']=='REVIEW' for r in matched) and any(r['action']=='SHIP' for r in matched);return {'http_request_ids_matched_to_audit':len(matched),'retained_rejected_application':first['id']}
        record('audit-origin-request-id-and-history',[('shop','audit_events',all_fields('audit_events'))],audit_trace)
        def mock_check():
            for t in ['channel_payments','channel_refunds','notification_jobs','simulation_rules','auth_nonces']:
                rows=query(f'SELECT * FROM {MDB}.{t}');assert rows,(t,'empty fixture')
                for x in rows:
                    technical(x,[k for k in x if k=='id' or k.endswith('_at')])
                    if t=='channel_payments':assert x['merchant_ref']=='scene1' and x['currency']=='CNY' and uuid_ok(x['order_ref']) and uuid_ok(x['request_id']) and x['txn_id'];assert x['status']!='SUCCEEDED' or x['paid_at']
                    if t=='channel_refunds':
                        cp=query(f'SELECT * FROM {MDB}.channel_payments WHERE txn_id=%s',(x['txn_id'],));assert len(cp)==1 and cp[0]['merchant_ref']==x['merchant_ref'] and cp[0]['amount_cents']==x['amount_cents'];assert x['status']!='SUCCEEDED' or x['refunded_at'];assert x['status']!='FAILED' or x['failure_code']
                    if t=='notification_jobs':
                        resource='channel_payments' if x['kind']=='PAYMENT' else 'channel_refunds';key='txn_id' if x['kind']=='PAYMENT' else 'refund_id';assert query(f'SELECT id FROM {MDB}.{resource} WHERE {key}=%s',(x['resource_ref'],));assert x['remaining_deliveries']>=0 and uuid_ok(x['event_id']) and dt(x['deliver_after']);assert x['status']!='RUNNING' or x['lease_until']
                    if t=='simulation_rules':assert uuid_ok(x['target_order_ref']) and x['operation'] in ['PAYMENT','REFUND'] and x['mode'] in ['EXPLICIT_FAIL','TIMEOUT_AFTER_SUCCESS'] and x['remaining_uses']==0 and x['delay_ms']>=0 and x['repeat_count']>=1
                    if t=='auth_nonces':assert x['key_id']=='shop-to-mock' and re.fullmatch('[A-Za-z0-9_-]{16,64}',x['nonce']) and x['expires_at']>x['created_at']
            return {t:query(f'SELECT COUNT(*) n FROM {MDB}.{t}')[0]['n'] for t in ['channel_payments','channel_refunds','notification_jobs','simulation_rules','auth_nonces']}
        record('mock-money-notification-rule-nonce-bindings',[('mock',t,all_fields(t,'mock')) for t in ['channel_payments','channel_refunds','notification_jobs','simulation_rules','auth_nonces']],mock_check)
        f.request('/api/v1/auth/logout','POST',{},role='buyer3');f.request('/api/v1/auth/me',role='buyer3',expect=401)
        def revoked():
            s=query(f'SELECT * FROM {DB}.sessions WHERE token_hash=%s',(hashlib.sha256(f.TOKENS['buyer3'].encode()).hexdigest(),))[0];assert s['revoked_at']>=s['created_at'];return {'revoked_and_rejected':True}
        record('logout-revocation-rejects-token',[('shop','sessions','revoked_at token_hash account_id')],revoked)
        clock0=query(f'SELECT * FROM {DB}.demo_clock')[0];f.request('/internal/demo/clock/advance','POST',{'seconds':1},admin=True);clock1=query(f'SELECT * FROM {DB}.demo_clock')[0]
        record('demo-clock-admin-version-offset',[('shop','demo_clock',all_fields('demo_clock'))],lambda:(ok(clock1['id']==1 and clock1['offset_seconds']==clock0['offset_seconds']+1 and clock1['version']==clock0['version']+1 and clock1['updated_by']=='demo-admin' and clock1['updated_at']>=clock0['updated_at'],'clock fields'),'only ignored-config demo admin accepted')[1])
        print('PASS semantic round',round_no,'cases',len(CASES),flush=True)
    success=True
finally:
    for p in procs:p.terminate()
    for p in procs:
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()
    for log in logs:log.close()
    conn.close()
    version_end={k:hashlib.sha256((APP/k).read_bytes()).hexdigest() for k in VERSION_START};unchanged=version_end==VERSION_START
    (OUT/'semantics-results.json').write_text(json.dumps({'passed':success and unchanged,'schemas':[DB,MDB],'cases':CASES,'links':LINKS,'events':f.EVENTS,'code_files_sha256':VERSION_START,'source_unchanged':unchanged},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('semantics',success,'cases',len(CASES),'links',len(LINKS))
