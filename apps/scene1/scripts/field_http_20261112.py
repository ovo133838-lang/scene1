"""Independent body assignment probes for every real physical field's API boundary.

Only immutability is proved here; cross-row semantic coverage is separately accounted.
"""
import pathlib,importlib.util,os,subprocess,json,time,uuid,hashlib,pymysql,re
APP=pathlib.Path(__file__).resolve().parents[1];OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
spec=importlib.util.spec_from_file_location('functional',APP/'scripts/functional.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
ROOT_PASSWORD=os.environ.get('SCENE1_FIELD_ROOT_PASSWORD') or f.CFG['SCENE1_FIELD_ROOT_PASSWORD']
CFG=dict(f.CFG);DB='scene1_field_http_20261112';MDB='scene1_field_http_mock_20261112';f.BASE='http://127.0.0.1:18130';f.MOCK='http://127.0.0.1:18131'
CFG.update(SCENE1_MYSQL_DSN=f'root:{ROOT_PASSWORD}@tcp(127.0.0.1:3306)/{DB}?parseTime=true&loc=UTC',SCENE1_MOCK_DSN=f'root:{ROOT_PASSWORD}@tcp(127.0.0.1:3306)/{MDB}?parseTime=true&loc=UTC',SCENE1_SHOP_URL=f.BASE,SCENE1_MOCK_URL=f.MOCK);f.CFG=CFG
conn=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=ROOT_PASSWORD,autocommit=True);procs=[];logs=[];cases=[];normal_inputs=[]
def sql(query):
    with conn.cursor() as c:c.execute(query);return c.fetchall()
def snapshot():
    return sql(f'SELECT (SELECT COUNT(*) FROM {DB}.orders),(SELECT COUNT(*) FROM {DB}.receipts),(SELECT COUNT(*) FROM {DB}.refunds),(SELECT COUNT(*) FROM {DB}.shipments),(SELECT SUM(available_quantity) FROM {DB}.products),(SELECT SUM(reserved_quantity) FROM {DB}.products),(SELECT SUM(shipped_quantity) FROM {DB}.products),(SELECT COUNT(*) FROM {MDB}.channel_payments),(SELECT COUNT(*) FROM {MDB}.channel_refunds)')
id=str(uuid.uuid4())
# Actual public field destinations. The complete endpoint's required body is valid;
# unknown persisted fields are injected one at a time and expected to be rejected.
mapping={
'accounts':('/api/v1/auth/login','POST',{'login_name':'buyer1','password':'invalid-safe-password'},None,False,False,False),
'sessions':('/api/v1/auth/logout','POST',{},'buyer1',False,False,False),
'products':('/api/v1/operator/products/'+id,'PATCH',{'version':0,'reason':'field assignment probe'},'operator',False,False,False),
'orders':('/api/v1/buyer/orders','POST',{'product_id':id,'quantity':1},'buyer1',False,False,False),
'inventory_ledger':('/api/v1/operator/products/'+id+'/inventory-adjustments','POST',{'version':0,'delta':1,'reason':'field assignment probe'},'operator',False,False,False),
'payment_intents':('/api/v1/buyer/orders/'+id+'/payments','POST',{},'buyer1',False,False,False),
'receipts':('/api/v1/channel/payment-notifications','POST',{'event_id':id,'merchant_ref':'scene1','order_ref':id,'request_id':id,'txn_id':id,'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':'2026-11-12T00:00:00Z'},None,True,False,False),
'channel_notifications':('/api/v1/channel/payment-notifications','POST',{'event_id':id,'merchant_ref':'scene1','order_ref':id,'request_id':id,'txn_id':id,'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':'2026-11-12T00:00:00Z'},None,True,False,False),
'auth_nonces':('/api/v1/channel/payment-notifications','POST',{'event_id':id,'merchant_ref':'scene1','order_ref':id,'request_id':id,'txn_id':id,'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':'2026-11-12T00:00:00Z'},None,True,False,False),
'refund_applications':('/api/v1/buyer/orders/'+id+'/refund-applications','POST',{'reason':'field assignment probe'},'buyer1',False,False,False),
'refunds':('/api/v1/support/refund-applications/'+id+'/review','POST',{'decision':'APPROVE','reason':'field assignment probe'},'support',False,False,False),
'refund_attempts':('/api/v1/support/refunds/'+id+'/retry','POST',{'reason':'field assignment probe'},'support',False,False,False),
'shipments':('/api/v1/warehouse/orders/'+id+'/shipment','POST',{'carrier':'teaching','tracking_no':'field-probe'},'warehouse',False,False,False),
'payment_anomalies':('/api/v1/support/payment-anomalies/'+id+'/verify','POST',{'reason':'field assignment probe'},'support',False,False,False),
'anomaly_actions':('/api/v1/support/payment-anomalies/'+id+'/verify','POST',{'reason':'field assignment probe'},'support',False,False,False),
'idempotency_records':('/api/v1/buyer/orders','POST',{'product_id':id,'quantity':1},'buyer1',False,False,False),
'outbox_jobs':('/api/v1/buyer/orders/'+id+'/payments','POST',{},'buyer1',False,False,False),
'audit_events':('/api/v1/buyer/orders','POST',{'product_id':id,'quantity':1},'buyer1',False,False,False),
'demo_clock':('/internal/demo/clock/advance','POST',{'seconds':1},None,False,True,False),
'channel_payments':('/mock/v1/payments','POST',{'merchant_ref':'scene1','request_id':id,'order_ref':id,'amount_cents':'1','currency':'CNY'},None,True,False,True),
'channel_refunds':('/mock/v1/refunds','POST',{'merchant_ref':'scene1','request_id':id,'txn_id':id,'amount_cents':'1','currency':'CNY'},None,True,False,True),
'notification_jobs':('/mock/admin/notifications/'+id+'/replay','POST',{'repeat_count':1,'delay_ms':0},None,False,True,True),
'simulation_rules':('/mock/admin/rules','POST',{'target_order_ref':id,'operation':'PAYMENT','mode':'SUCCESS'},None,False,True,True)}
inventory=json.loads((OUT/'source-field-inventory.json').read_text(encoding='utf-8'))
route_allowed=[]
for match in re.finditer(r'\{"(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", (true|false)\}',(APP/'internal/httpapi/api.go').read_text(encoding='utf-8')):
    method,path,role,op,required,optional,query,write=match.groups()
    route_allowed.append((method,re.sub(r'\{[^}]+\}',r'[^/]+',path),set((required+' '+optional).split())))
try:
    sql(f'CREATE DATABASE IF NOT EXISTS {DB}');sql(f'CREATE DATABASE IF NOT EXISTS {MDB}')
    exe=APP/'bin/scene1-field-http.exe';build=subprocess.run(['go','build','-o',str(exe),'./cmd/scene1'],cwd=APP,capture_output=True,text=True);(OUT/'http-build.log').write_text(build.stdout+build.stderr,encoding='utf-8');assert build.returncode==0
    for mode,port in [('shop',18130),('mock',18131)]:
        env=os.environ.copy();env.update(CFG);env['SCENE1_PORT']=str(port);log=open(OUT/('http-'+mode+'.log'),'ab');logs.append(log);procs.append(subprocess.Popen([str(exe),'-mode',mode,'-env','nonexistent.env'],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    for _ in range(80):
        try:f.request('/health/ready');break
        except Exception:time.sleep(.2)
    f.login()
    for round_no in [1,2]:
        login=f.request('/api/v1/auth/login','POST',{'login_name':'buyer1','password':CFG['SCENE1_PASSWORD']})
        assert login['account']['login_name']=='buyer1'
        normal_inputs.append(dict(round=round_no,table='accounts',fields=['login_name'],route='POST /api/v1/auth/login',status='PASS',safe_result={'login_name':login['account']['login_name'],'role':login['account']['role']},input_note='correct local password supplied from ignored env; never serialized'))
        rule_body={'target_order_ref':str(uuid.uuid4()),'target_request_id':str(uuid.uuid4()),'attempt_no':1,'operation':'PAYMENT','mode':'SUCCESS','delay_ms':0,'repeat_count':1,'remaining_uses':1}
        rule=f.request('/mock/admin/rules','POST',rule_body,admin=True,mock=True,expect=201)
        assert all(rule[k]==v for k,v in rule_body.items())
        normal_inputs.append(dict(round=round_no,table='simulation_rules',fields=list(rule_body),route='POST /mock/admin/rules',status='PASS',safe_result=rule,input=rule_body))
        for row in inventory:
            table,field=row['table'],row['field']
            if table not in mapping:
                cases.append(dict(round=round_no,scope=row['scope'],table=table,field=field,status='NOT_APPLICABLE',reason='technical migration/lock table has no public endpoint'));continue
            path,method,body,role,signed,admin,mock=mapping[table]
            allowed=next(fields for route_method,route_pattern,fields in route_allowed if route_method==method and re.fullmatch(route_pattern,path))
            if field in allowed:
                cases.append(dict(round=round_no,scope=row['scope'],table=table,field=field,status='NOT_RUN',reason='declared request field; semantic validation belongs to actual API matrix',route=method+' '+path));continue
            before=snapshot();error=None
            try:f.request(path,method,dict(body,**{field:'client-forged-field'}),role=role,signed=signed,admin=admin,mock=mock,expect=400)
            except Exception as exc:error=type(exc).__name__
            after=snapshot();passed=error is None and before==after
            cases.append(dict(round=round_no,scope=row['scope'],table=table,field=field,status='PASS' if passed else 'FAIL',route=method+' '+path,expected='400 unknown persisted field; no order/inventory/funds side effect',error_type=error,side_effect_snapshot_equal=before==after,notification_trace_allowed=table in ['receipts','channel_notifications','auth_nonces']))
finally:
    for p in procs:p.terminate()
    for p in procs:
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()
    for log in logs:log.close()
    conn.close()
    (OUT/'http-field-results.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'http-field-events.json').write_text(json.dumps(f.EVENTS,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'normal-input-results.json').write_text(json.dumps(normal_inputs,ensure_ascii=False,indent=2),encoding='utf-8')
print('HTTP field assignment',len(cases),'PASS',sum(c['status']=='PASS' for c in cases),'FAIL',sum(c['status']=='FAIL' for c in cases),'NOT_RUN',sum(c['status']=='NOT_RUN' for c in cases))
