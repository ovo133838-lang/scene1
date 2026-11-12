"""Independent real-route HTTP matrix. Only dedicated api_20261112 schemas are used.
No production source edits, no deployment, no shared database reset. Secrets stay in memory.
"""
import concurrent.futures,csv,datetime,hashlib,hmac,importlib.util,json,os,pathlib,re,subprocess,time,traceback,urllib.error,urllib.parse,urllib.request,uuid,shutil,sys
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path(os.environ.get('SCENE1_MATRIX_OUT','D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/apis'))
OUT.mkdir(parents=True,exist_ok=True)
MYSQL=os.environ.get('SCENE1_MYSQL_BIN') or shutil.which('mysql') or 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe'
DBPORT=os.environ.get('SCENE1_MATRIX_MYSQL_PORT','3306')
DBPASS=os.environ.get('SCENE1_MATRIX_MYSQL_PASSWORD','root')
RUN_SUFFIX=uuid.uuid4().hex[:8]
SHOPDB='scene1_api_20261112_'+RUN_SUFFIX;MOCKDB='scene1_api_mock_20261112_'+RUN_SUFFIX
BASE='http://127.0.0.1:18110';MOCK='http://127.0.0.1:18111'
CFG=dict(l.split('=',1) for l in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if l and not l.startswith('#'))
spec=importlib.util.spec_from_file_location('functional',APP/'scripts/functional.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
f.BASE=BASE;f.MOCK=MOCK
EVENTS=[];CASES=[];PROCS=[];FAILURES=[];EXE=APP/'bin'/('scene1-api-matrix.exe' if os.name=='nt' else 'scene1-api-matrix')
routes=[]
src=(APP/'internal/httpapi/api.go').read_text(encoding='utf-8')
for section,mock in [('ShopRoutes',False),('MockRoutes',True)]:
    block=src.split('var '+section+' = []Route{',1)[1].split('\n}',1)[0]
    for m in re.finditer(r'\{"(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", (true|false)\}',block):
        method,path,role,op,req,opt,query,write=m.groups();routes.append(dict(method=method,path=path,role=role,op=op,required=req.split(),optional=opt.split(),query=query.split(),write=write=='true',mock=mock))
routes.append(dict(method='GET',path='/health/live',role='',op='mock_live',required=[],optional=[],query=[],write=False,mock=True))
assert len(routes)==49,len(routes)
def key():return str(uuid.uuid4())
def sql(q,mock=False):
    assert re.fullmatch('scene1_api(_mock)?_20261112_[a-f0-9]{8}',MOCKDB if mock else SHOPDB)
    env=os.environ.copy();env['MYSQL_PWD']=DBPASS
    p=subprocess.run([MYSQL,'--no-defaults','-N','-B','--default-character-set=utf8mb4','-h','127.0.0.1','-P',DBPORT,'-u','root',MOCKDB if mock else SHOPDB,'-e',q],env=env,text=True,encoding='utf-8',capture_output=True)
    assert p.returncode==0,p.stderr
    return p.stdout.strip()
def snapshot():
    return sql("SELECT CONCAT_WS('|',(SELECT COUNT(*) FROM orders),(SELECT COUNT(*) FROM receipts),(SELECT COALESCE(SUM(amount_cents),0) FROM receipts),(SELECT COUNT(*) FROM refunds),(SELECT COALESCE(SUM(amount_cents),0) FROM refunds WHERE status='SUCCEEDED'),(SELECT COUNT(*) FROM shipments),(SELECT GROUP_CONCAT(CONCAT_WS(':',id,available_quantity,reserved_quantity,shipped_quantity,adjustment_net) ORDER BY id) FROM products));")+';'+sql("SELECT CONCAT_WS('|',(SELECT COUNT(*) FROM channel_payments),(SELECT COUNT(*) FROM channel_refunds));",True)
def match(path,method,mock):
    p=path.partition('?')[0]
    for rt in routes:
        if rt['method']==method and rt['mock']==mock and re.fullmatch(re.sub(r'\{[^}]+\}',r'[^/]+',rt['path']),p):return rt
def sign_headers(path,method,data,stamp=None,nonce=None,sign_path=None,sign_body=None):
    stamp=stamp or str(int(time.time()));nonce=nonce or key();pp,_,q=(sign_path or path).partition('?')
    q=urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(q,keep_blank_values=True)),quote_via=urllib.parse.quote,safe='~')
    canonical='\n'.join([method,pp+('?' + q if q else ''),stamp,nonce,hashlib.sha256(data if sign_body is None else sign_body).hexdigest()])
    kid='shop-to-mock' if pp.startswith('/mock/') else 'mock-to-shop'
    dk=hmac.new(CFG['SCENE1_HMAC_SECRET'].encode(),kid.encode(),hashlib.sha256).digest()
    return {'X-Key-Id':kid,'X-Timestamp':stamp,'X-Nonce':nonce,'X-Signature':hmac.new(dk,canonical.encode(),hashlib.sha256).hexdigest()}
def send(path,method='GET',body=None,role=None,expect=200,signed=False,admin=False,mock=False,idem=None,raw=None,headers=None,auth_token=None,dimension='flow',guard=False):
    data=(json.dumps(body,separators=(',',':'),ensure_ascii=False).encode() if body is not None else None) if raw is None else raw
    hh={'Content-Type':'application/json'}
    if method!='GET':hh['Idempotency-Key']=idem or key()
    if role:hh['Authorization']='Bearer '+f.TOKENS[role]
    if auth_token is not None:hh['Authorization']='Bearer '+auth_token
    if admin:hh['Authorization']='Bearer '+CFG['SCENE1_ADMIN_TOKEN']
    if signed:hh.update(sign_headers(path,method,data or b''))
    if headers:hh.update(headers)
    before=snapshot() if guard else None
    t=time.time();req=urllib.request.Request((MOCK if mock else BASE)+path,data=data,headers=hh,method=method)
    transport_retries=[]
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req,timeout=18) as res:status=res.status;payload=res.read();rh=dict(res.headers)
            break
        except urllib.error.HTTPError as e:status=e.code;payload=e.read();rh=dict(e.headers);break
        except OSError as e:
            # Windows may reset an early-rejected request with an unread oversized tail.
            # Keep each transport failure; demand an actual HTTP result before PASS.
            if dimension!='oversized' or attempt==3:raise
            transport_retries.append({'attempt':attempt+1,'error':type(e).__name__,'errno':e.errno})
            time.sleep(.05)
    try:out=json.loads(payload)
    except ValueError:out={'text':payload.decode(errors='replace')[:300]}
    after=snapshot() if guard else None
    ok=status in ([expect] if isinstance(expect,int) else expect)
    if payload.startswith(b'{'):
        nonce=hh.get('X-Nonce','')
        message=str(status)+'\n'+nonce+'\n'+hashlib.sha256(payload).hexdigest()
        wanted=hmac.new(CFG['SCENE1_HMAC_SECRET'].encode(),message.encode(),hashlib.sha256).hexdigest()
        response_signature=rh.get('X-Response-Signature') or rh.get('X-response-signature')
        assert hmac.compare_digest(wanted,response_signature or ''),'untrusted response signature'
    if guard:ok=ok and before==after
    # Tokens are deliberately absent from persisted login responses.
    stored={'omitted':'credential-bearing login response','dto_valid':set(out.get('data',{}))=={'token','expires_at','account'} and set(out.get('data',{}).get('account',{}))=={'id','login_name','display_name','role'}} if path.partition('?')[0]=='/api/v1/auth/login' else out
    rt=match(path,method,mock);event={'index':len(EVENTS),'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'route':rt['path'] if rt else path,'mock':mock,'method':method,'path':path,'dimension':dimension,'input':{'omitted':'login credentials'} if path.partition('?')[0]=='/api/v1/auth/login' else body,'raw_sha256':hashlib.sha256(data or b'').hexdigest(),'expected_http':expect,'actual_http':status,'response':stored,'elapsed':round(time.time()-t,3),'db_before':before,'db_after':after,'passed':ok}
    # Never persist signatures or Authorization. Response signatures independently verified in dedicated cases.
    event['request_key']=hh.get('Idempotency-Key')
    if transport_retries:event['transport_retries']=transport_retries
    EVENTS.append(event)
    assert ok,(method,path,dimension,status,expect,stored,'db unchanged',before==after)
    return out.get('data',out)
f.request=send
original_lists=f.lists
def fresh_lists(path,role,**filters):
    rows=original_lists(path,role,**filters)
    if filters.get('type')=='UNKNOWN_ORDER':
        latest=next((e['response']['data']['txn_id'] for e in reversed(EVENTS) if e.get('method')=='POST' and e.get('path')=='/mock/v1/payments' and e.get('response',{}).get('data',{}).get('txn_id')),None)
        if latest:
            rows=[row for row in rows if any(n.get('provider_txn_id')==latest for n in send('/api/v1/support/payment-anomalies/'+row['id'],role=role)['notifications'])]
    return rows
f.lists=fresh_lists
def case(label,fn):
    start=len(EVENTS)
    try:fn();CASES.append({'case':label,'status':'PASS','first_event':start,'last_event':len(EVENTS)-1})
    except Exception as e:
        msg=str(e)
        for secret in [CFG['SCENE1_HMAC_SECRET'],CFG['SCENE1_ADMIN_TOKEN'],CFG['SCENE1_PASSWORD']]:msg=msg.replace(secret,'[REDACTED]')
        FAILURES.append({'case':label,'error':msg});CASES.append({'case':label,'status':'FAIL','first_event':start,'last_event':len(EVENTS)-1,'error':msg})
    try:print(CASES[-1]['status'],label,flush=True)
    except OSError:pass # A detached terminal must not abort the actual test run.
def start():
    for mode,port in [('shop',18110),('mock',18111)]:
        env=os.environ.copy();env.update(CFG);env.update({'SCENE1_MYSQL_DSN':f'root:{DBPASS}@tcp(127.0.0.1:{DBPORT})/'+SHOPDB+'?parseTime=true&loc=UTC','SCENE1_MOCK_DSN':f'root:{DBPASS}@tcp(127.0.0.1:{DBPORT})/'+MOCKDB+'?parseTime=true&loc=UTC','SCENE1_SHOP_URL':BASE,'SCENE1_MOCK_URL':MOCK,'SCENE1_PORT':str(port)})
        log=open(OUT/(mode+'.log'),'ab');p=subprocess.Popen([str(EXE),'-mode',mode,'-env','nonexistent-api-matrix.env'],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));PROCS.append(p)
    for _ in range(100):
        try:send('/health/ready');return
        except Exception:time.sleep(.2)
    raise RuntimeError('service startup failed; inspect sanitized logs')
def stop():
    for p in PROCS:p.terminate()
    for p in PROCS:
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()
    PROCS.clear()
f.start=start;f.stop=stop
def request_id(o,attempt):return sql("SELECT provider_request_id FROM refund_attempts WHERE id='"+str(uuid.UUID(attempt['id']))+"';")
f.get_refund_request=request_id
def version():
    files={str(p.relative_to(APP)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(APP.rglob('*.go')) if 'bin' not in p.parts}
    files.update({str(p.relative_to(APP)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (APP/'internal/repository/migrations').glob('*.sql')})
    return {'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'branch':subprocess.check_output(['git','branch','--show-current'],cwd=APP,text=True).strip(),'base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=APP,text=True).strip(),'files':files,'schemas':[SHOPDB,MOCKDB],'mysql_port':DBPORT}
def init():
    env=os.environ.copy();env['MYSQL_PWD']=DBPASS
    q=''.join('CREATE DATABASE IF NOT EXISTS `'+db+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;' for db in [SHOPDB,MOCKDB])
    p=subprocess.run([MYSQL,'--no-defaults','-h','127.0.0.1','-P',DBPORT,'-u','root','-e',q],env=env,capture_output=True,text=True);assert p.returncode==0,p.stderr
    p=subprocess.run(['go','build','-o',str(EXE),'./cmd/scene1'],cwd=APP,capture_output=True,text=True,encoding='utf-8');(OUT/'build.log').write_text(p.stdout+p.stderr,encoding='utf-8');assert p.returncode==0
def prototype(rt):
    ident='11111111-1111-4111-8111-111111111111'
    values=dict(login_name='buyer1',password=CFG['SCENE1_PASSWORD'],product_id=ident,quantity=1,reason='独立接口矩阵',carrier='TEST',tracking_no='MATRIX-001',decision='APPROVE',version=0,name='标准商品',unit_price_cents='10000',sale_status='ON_SHELF',delta=1,event_id=key(),merchant_ref='scene1',order_ref=ident,request_id=key(),txn_id=key(),amount_cents='10000',currency='CNY',status='SUCCEEDED',occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),refund_id=key(),failure_code='FAILED',target_order_ref=ident,operation='PAYMENT',mode='SUCCESS',target_request_id=key(),attempt_no=1,delay_ms=0,repeat_count=1,remaining_uses=1,seconds=1)
    body={k:values[k] for k in rt['required']}
    if rt['op']=='update_product':body['name']='标准商品'
    path=re.sub(r'\{[^}]+\}',ident,rt['path'])
    if rt['op'] in ['payment_query','transaction_query','refund_query']:path+='?merchant_ref=scene1'
    role={'BUYER':'buyer1','OPERATOR':'operator','WAREHOUSE':'warehouse','SUPPORT':'support','*':'buyer1'}.get(rt['role'])
    return path,body if rt['method']!='GET' else None,dict(role=role,signed=rt['role']=='HMAC',admin=rt['role'] in ['ADMIN','CLOCK'],mock=rt['mock'])
INTEGER={'quantity','version','delta','seconds','attempt_no','delay_ms','repeat_count','remaining_uses'}
def negative_matrix(round_no):
    for rt in routes:
        path,body,kw=prototype(rt);tag=('mock ' if rt['mock'] else 'shop ')+rt['method']+' '+rt['path']
        def invoke(dim,b=None,p=None,ex=400,**options):
            args=dict(kw);args.update(options)
            return send(p or path,rt['method'],body if b is None else b,expect=ex,dimension=dim,guard=True,**args)
        case(f'R{round_no} {tag} unknown-query',lambda:invoke('unknown-query',p=path+('&' if '?' in path else '?')+'unexpected=1')) if rt['role']!='HMAC' and rt['op']!='mock_live' else None
        # Notification auth branch records rejected events before generic query validation; tested separately.
        if rt['role'] in ['BUYER','OPERATOR','WAREHOUSE','SUPPORT','*']:
            case(f'R{round_no} {tag} no-auth',lambda:invoke('no-auth',ex=401,role=None))
            case(f'R{round_no} {tag} forged-auth',lambda:invoke('forged-auth',ex=401,role=None,auth_token='forged-token'))
            if rt['role']!='*':
                wrong='operator' if rt['role']=='BUYER' else 'buyer1'
                case(f'R{round_no} {tag} wrong-role',lambda:invoke('wrong-role',ex=403,role=wrong))
            for mode in ['expired','revoked','disabled']:
                role=kw['role'];th=hashlib.sha256(f.TOKENS[role].encode()).hexdigest()
                if mode=='expired':q="UPDATE sessions SET expires_at='2000-01-01' WHERE token_hash='"+th+"';";restore="UPDATE sessions SET expires_at=UTC_TIMESTAMP()+INTERVAL 8 HOUR WHERE token_hash='"+th+"';"
                elif mode=='revoked':q="UPDATE sessions SET revoked_at=UTC_TIMESTAMP() WHERE token_hash='"+th+"';";restore="UPDATE sessions SET revoked_at=NULL WHERE token_hash='"+th+"';"
                else:q="UPDATE accounts SET enabled=0 WHERE login_name='"+role+"';";restore="UPDATE accounts SET enabled=1 WHERE login_name='"+role+"';"
                sql(q)
                try:case(f'R{round_no} {tag} {mode}',lambda mode=mode:invoke(mode,ex=401))
                finally:sql(restore)
        elif rt['role'] in ['ADMIN','CLOCK']:
            ex=403 if rt['role']=='ADMIN' else 401
            case(f'R{round_no} {tag} no-admin',lambda:invoke('no-admin',ex=ex,admin=False))
            case(f'R{round_no} {tag} user-token-is-not-admin',lambda:invoke('user-token-is-not-admin',ex=ex,admin=False,role='buyer1'))
        elif rt['role']=='HMAC':
            case(f'R{round_no} {tag} no-hmac',lambda:invoke('no-hmac',ex=401,signed=False))
            for kind in ['timestamp-old','timestamp-future','wrong-body','wrong-path','wrong-direction','short-nonce']:
                data=json.dumps(body,separators=(',',':'),ensure_ascii=False).encode() if body is not None else b''
                args={}
                if kind=='timestamp-old':args['stamp']=str(int(time.time())-360)
                if kind=='timestamp-future':args['stamp']=str(int(time.time())+360)
                if kind=='wrong-body':args['sign_body']=b'changed'
                if kind=='wrong-path':args['sign_path']=path+'/changed'
                if kind=='short-nonce':args['nonce']='short'
                headers=sign_headers(path,rt['method'],data,**args)
                if kind=='wrong-direction':headers['X-Key-Id']='mock-to-shop' if rt['mock'] else 'shop-to-mock'
                case(f'R{round_no} {tag} {kind}',lambda headers=headers,kind=kind:invoke(kind,ex=401,signed=False,headers=headers))
        if rt['method']!='GET':
            case(f'R{round_no} {tag} unknown-body',lambda:invoke('unknown-body',b=dict(body,unexpected='x')))
            for raw,label in [(b'[]','array'),(b'{}{}','trailing-json'),(b'{"x":1,"x":2}','duplicate-key'),(b'\xff','invalid-utf8'),(b'{'+b' '*65536+b'}','oversized')]:
                case(f'R{round_no} {tag} {label}',lambda raw=raw,label=label:invoke(label,raw=raw))
            for field in rt['required']+rt['optional']:
                base=dict(body)
                if field not in base:base[field]=prototype(rt)[1].get(field,1 if field in INTEGER else 'x')
                if field in rt['required']:
                    b=dict(base);b.pop(field);case(f'R{round_no} {tag} missing:{field}',lambda b=b,field=field:invoke('missing:'+field,b=b))
                for val,label in [(None,'null'),([], 'wrong-type')]:
                    b=dict(base);b[field]=val;case(f'R{round_no} {tag} {label}:{field}',lambda b=b,label=label,field=field:invoke(label+':'+field,b=b))
                vals=[(1.5,'fraction'),('1','numeric-string'),(9223372036854775808,'int-overflow')]
                if field not in INTEGER:vals=[('','empty'),(' ','whitespace'),('x\n','control'),('x'*501,'overlong')]
                if field.endswith('_cents'):vals += [(v,'money:'+str(v)) for v in ['0','-1','1.5','1e3','01','9223372036854775808']]
                for val,label in vals:
                    b=dict(base);b[field]=val;case(f'R{round_no} {tag} {label}:{field}',lambda b=b,label=label,field=field:invoke(label+':'+field,b=b))
        if rt['write']:
            for idem in ['', 'short','x'*65]:case(f'R{round_no} {tag} invalid-idem:{len(idem)}',lambda idem=idem:invoke('invalid-idem',idem=idem or ' '))
        if '{' in rt['path'] and not rt['mock']:
            bad=re.sub(r'\{[^}]+\}','not-a-uuid',rt['path']);case(f'R{round_no} {tag} invalid-path-id',lambda:invoke('invalid-path-id',p=bad))
        if 'limit' in rt['query']:
            for value in ['0','101','1.5','x','-1']:case(f'R{round_no} {tag} limit:{value}',lambda value=value:invoke('limit:'+value,p=path+'?limit='+value))
            case(f'R{round_no} {tag} forged-cursor',lambda:invoke('forged-cursor',p=path+'?cursor=fake'))
        for field in rt['query']:
            if field in ['status','kind','type','classification','process_result']:
                case(f'R{round_no} {tag} invalid-filter:{field}',lambda field=field:invoke('invalid-filter:'+field,p=path+'?'+field+'=INVALID'))
def extra_flow():
    f.stock(20)
    o=f.create();p=send('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202)
    send('/api/v1/buyer/payments/'+p['id']+'/query','POST',{},role='buyer1',expect=202)
    f.poll(lambda:f.order(o),lambda x:x['status']=='PENDING_SHIPMENT')
    send('/api/v1/buyer/payments/'+p['id']+'/query','POST',{},role='buyer2',expect=404,guard=True,dimension='other-owner')
    f.ship(o)
    send('/health/live',mock=True);send('/health/live')
    # Legitimate same nonce replay is rejected; new nonce same business key is safe.
    b={'merchant_ref':'scene1','request_id':key(),'order_ref':key(),'amount_cents':'20','currency':'CNY'}
    data=json.dumps(b,separators=(',',':')).encode();headers=sign_headers('/mock/v1/payments','POST',data)
    p=send('/mock/v1/payments','POST',b,mock=True,headers=headers)
    send('/mock/v1/payments','POST',b,mock=True,headers=headers,expect=401,guard=True,dimension='nonce-replay')
    same=send('/mock/v1/payments','POST',b,mock=True,signed=True,dimension='new-nonce-same-request');assert same['txn_id']==p['txn_id']
    send('/mock/v1/payments','POST',dict(b,amount_cents='21'),mock=True,signed=True,expect=409,guard=True,dimension='same-key-different-body')
    rb={'merchant_ref':'scene1','request_id':key(),'txn_id':p['txn_id'],'amount_cents':'20','currency':'CNY'}
    rr=send('/mock/v1/refunds','POST',rb,mock=True,signed=True,dimension='same-key-first')
    same=send('/mock/v1/refunds','POST',rb,mock=True,signed=True,dimension='same-key-replay');assert same['refund_id']==rr['refund_id']
    send('/mock/v1/refunds','POST',dict(rb,amount_cents='21'),mock=True,signed=True,expect=409,dimension='same-key-different-body')
def semantic_boundaries():
    p=f.stock(30)
    for q in [0,-1,3,9223372036854775807]:send('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':q},role='buyer1',expect=400,guard=True,dimension='quantity-range:'+str(q))
    for q in [1,2]:
        o=f.create(q=q);assert o['quantity']==q and o['amount_cents']==str(q*10000);f.cancel(o)
    for price in ['1000000001','9223372036854775807']:
        p=f.product();send('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'reason':'非法上限','unit_price_cents':price},role='operator',expect=400,guard=True,dimension='unit-price-upper-limit')
    for delta in [0,-1000001,1000001,-31]:
        p=f.product();send('/api/v1/operator/products/'+p['id']+'/inventory-adjustments','POST',{'version':p['version'],'reason':'非法库存边界','delta':delta},role='operator',expect=400,guard=True,dimension='delta-range:'+str(delta))
    p=f.product();send('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version']+1,'reason':'旧版本','name':'错误名称'},role='operator',expect=409,guard=True,dimension='stale-version')
    o=f.create();f.cancel(o)
    for suffix,body in [('payments',{}),('refund-applications',{'reason':'关闭不可退'})]:send('/api/v1/buyer/orders/'+o['id']+'/'+suffix,'POST',body,role='buyer1',expect=409,guard=True,dimension='closed-order-illegal-state')
    send('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'他人不可取消'},role='buyer2',expect=404,guard=True,dimension='other-owner')
    for sec in [0,3601]:send('/internal/demo/clock/advance','POST',{'seconds':sec},admin=True,expect=400,guard=True,dimension='clock-range')
    for field,values in [('delay_ms',[-1,600001]),('repeat_count',[0,21]),('remaining_uses',[0,21]),('attempt_no',[0])]:
        for val in values:send('/mock/admin/rules','POST',{'target_order_ref':o['id'],'operation':'PAYMENT','mode':'SUCCESS',field:val},admin=True,mock=True,expect=400,guard=True,dimension='rule-range:'+field)
    for field,values in [('delay_ms',[-1,600001]),('repeat_count',[0,21])]:
        for val in values:send('/mock/admin/notifications/'+key()+'/replay','POST',dict({'repeat_count':1,'delay_ms':0},**{field:val}),admin=True,mock=True,expect=400,guard=True,dimension='replay-range:'+field)
    for rt in routes:
        if rt['mock'] and rt['op'] in ['payment_query','refund_query','transaction_query']:
            for suffix in ['', '?merchant_ref=other']:
                path=re.sub(r'\{[^}]+\}',key(),rt['path'])+suffix
                send(path,signed=True,mock=True,expect=400 if not suffix else 404,guard=True,dimension='merchant-scope')
def dependency_matrix():
    f.login()
    for rt in routes:
        if rt['op'] in ['live','mock_live','ready']:continue
        path,body,kw=prototype(rt)
        table=('channel_refunds' if rt['op']=='refund_query' else 'channel_payments' if rt['op'] in ['payment_query','transaction_query'] else 'runtime_lock') if rt['mock'] else ('demo_clock' if rt['op'] in ['notify_payment','notify_refund','advance','clock'] else 'accounts')
        before=snapshot()
        sql('RENAME TABLE `'+table+'` TO `fault_hidden_'+table+'`;',rt['mock'])
        try:
            send(path,rt['method'],body,expect=503,dimension='storage-unavailable',**kw)
        finally:sql('RENAME TABLE `fault_hidden_'+table+'` TO `'+table+'`;',rt['mock'])
        after=snapshot();assert before==after,(rt,before,after)
        EVENTS[-1].update(db_before=before,db_after=after,storage_fault=table+' temporarily unavailable')
def write_replays():
    f.login();f.stock(60)
    def replay(path,body,role,status,changed=None):
        k=key();a=send(path,'PATCH' if path.startswith('/api/v1/operator/products/') and not path.endswith('inventory-adjustments') else 'POST',body,role=role,expect=status,idem=k,dimension='same-key-first')
        method='PATCH' if path.startswith('/api/v1/operator/products/') and not path.endswith('inventory-adjustments') else 'POST'
        b=send(path,method,body,role=role,expect=status,idem=k,dimension='same-key-replay')
        def ident(v):return v.get('id') or v.get('application',{}).get('id')
        assert ident(a)==ident(b),(path,a,b)
        if changed is not None:send(path,method,changed,role=role,expect=409,idem=k,dimension='same-key-different-valid-body')
        return a
    p=f.product();replay('/api/v1/operator/products/'+p['id'],{'version':p['version'],'reason':'幂等商品','name':'活动标准商品'},'operator',200,{'version':p['version'],'reason':'换参','name':'另一商品名'})
    p=f.product();replay('/api/v1/operator/products/'+p['id']+'/inventory-adjustments',{'version':p['version'],'reason':'幂等库存','delta':1},'operator',201,{'version':p['version'],'reason':'幂等库存','delta':2})
    o=replay('/api/v1/buyer/orders',{'product_id':p['id'],'quantity':1},'buyer1',201,{'product_id':p['id'],'quantity':2})
    replay('/api/v1/buyer/orders/'+o['id']+'/cancel',{'reason':'关闭'},'buyer1',200,{'reason':'换关闭原因'})
    o=f.create();payment=replay('/api/v1/buyer/orders/'+o['id']+'/payments',{},'buyer1',202)
    replay('/api/v1/buyer/payments/'+payment['id']+'/query',{},'buyer1',202)
    f.poll(lambda:f.order(o),lambda x:x['status']=='PENDING_SHIPMENT')
    a=replay('/api/v1/buyer/orders/'+o['id']+'/refund-applications',{'reason':'退款申请'},'buyer1',201,{'reason':'换申请原因'})
    r=replay('/api/v1/support/refund-applications/'+a['id']+'/review',{'decision':'REJECT','reason':'拒绝原因'},'support',200,{'decision':'APPROVE','reason':'冲突结论'})
    replay('/api/v1/warehouse/orders/'+o['id']+'/shipment',{'carrier':'测试渠道','tracking_no':'IDEM-SHIP'},'warehouse',201,{'carrier':'测试渠道','tracking_no':'CHANGED'})
    o=f.create();f.pay(o);a=f.apply(o);f.rule(o,'EXPLICIT_FAIL',attempt_no=1);r=f.approve(a)['refund']
    f.poll(lambda:f.lists('/api/v1/support/refunds','support',status='FAILED'),lambda xs:any(x['id']==r['id'] for x in xs))
    replay('/api/v1/support/refunds/'+r['id']+'/retry',{'reason':'明确失败重试'},'support',202,{'reason':'换重试原因'})
    replay('/api/v1/support/refunds/'+r['id']+'/query',{'reason':'查询原尝试'},'support',202,{'reason':'换查询原因'})
    f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED')
    o=f.create();f.rule(o,'TIMEOUT_AFTER_SUCCESS','PAYMENT');send('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202);f.cancel(o)
    xs=f.poll(lambda:f.lists('/api/v1/support/payment-anomalies','support',type='LATE_PAYMENT'),lambda xs:any(x['order_id']==o['id'] for x in xs));an=next(x for x in xs if x['order_id']==o['id'])
    replay('/api/v1/support/payment-anomalies/'+an['id']+'/verify',{'reason':'核实原款'},'support',200,{'reason':'换核实原因'})
    replay('/api/v1/support/payment-anomalies/'+an['id']+'/refund',{'reason':'迟到退款'},'support',202,{'reason':'换退款原因'})
    fake={'event_id':key(),'merchant_ref':'scene1','order_ref':key(),'request_id':key(),'txn_id':key(),'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    send('/api/v1/channel/payment-notifications','POST',fake,expect=401)
    xs=f.lists('/api/v1/support/payment-anomalies','support',type='INVALID_SIGNATURE');an=next(x for x in xs if any(n['provider_txn_id']==fake['txn_id'] for n in send('/api/v1/support/payment-anomalies/'+x['id'],role='support')['notifications']))
    send('/api/v1/support/payment-anomalies/'+an['id']+'/verify','POST',{'reason':'核实伪造'},role='support')
    replay('/api/v1/support/payment-anomalies/'+an['id']+'/resolve',{'reason':'渠道无收款'},'support',200,{'reason':'换结案原因'})
def state_ownership():
    f.stock(30);o=f.create()
    for suffix,body in [('',None),('/cancel',{'reason':'越权'}),('/payments',{}),('/refund-applications',{'reason':'越权'})]:
        send('/api/v1/buyer/orders/'+o['id']+suffix,'GET' if body is None else 'POST',body,role='buyer2',expect=404,guard=True,dimension='other-owner')
    send('/api/v1/warehouse/orders/'+o['id']+'/shipment','POST',{'carrier':'教学','tracking_no':'NOT-PAID'},role='warehouse',expect=409,guard=True,dimension='illegal-state')
    f.pay(o)
    send('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'已付不可取消'},role='buyer1',expect=409,guard=True,dimension='illegal-state')
    a=f.apply(o);f.approve(a,'REJECT')
    send('/api/v1/support/refund-applications/'+a['id']+'/review','POST',{'decision':'APPROVE','reason':'冲突结论'},role='support',expect=409,guard=True,dimension='illegal-state')
    a=f.apply(o);r=f.approve(a)['refund'];f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED')
    send('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'成功不可重试'},role='support',expect=409,guard=True,dimension='illegal-state')
    p=f.product();send('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version']+1,'name':'旧版本','reason':'过期版本'},role='operator',expect=409,guard=True,dimension='illegal-state')
    send('/api/v1/operator/products/'+p['id']+'/inventory-adjustments','POST',{'version':p['version']+1,'delta':1,'reason':'过期版本'},role='operator',expect=409,guard=True,dimension='illegal-state')
    p=f.product();send('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'sale_status':'OFF_SHELF','reason':'下架测试'},role='operator')
    send('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':1},role='buyer1',expect=409,guard=True,dimension='illegal-state')
    f.stock(30);o=f.create();f.cancel(o)
    for suffix,body in [('payments',{}),('refund-applications',{'reason':'关闭不可退'})]:send('/api/v1/buyer/orders/'+o['id']+'/'+suffix,'POST',body,role='buyer1',expect=409,guard=True,dimension='illegal-state')
    fake={'event_id':key(),'merchant_ref':'scene1','order_ref':key(),'request_id':key(),'txn_id':key(),'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    send('/api/v1/channel/payment-notifications','POST',fake,expect=401)
    xs=f.lists('/api/v1/support/payment-anomalies','support',type='INVALID_SIGNATURE');an=next(x for x in xs if any(n['provider_txn_id']==fake['txn_id'] for n in send('/api/v1/support/payment-anomalies/'+x['id'],role='support')['notifications']))
    for action in ['refund','resolve']:send('/api/v1/support/payment-anomalies/'+an['id']+'/'+action,'POST',{'reason':'未核实不可操作'},role='support',expect=409,guard=True,dimension='illegal-state')
def window_retest():
    for rt in routes:
        if rt['role']!='HMAC':continue
        path,body,kw=prototype(rt);data=json.dumps(body,separators=(',',':'),ensure_ascii=False).encode() if body is not None else b''
        for delta,label in [(-360,'timestamp-old'),(360,'timestamp-future')]:
            headers=sign_headers(path,rt['method'],data,stamp=str(int(time.time())+delta));opts=dict(kw,signed=False,headers=headers)
            send(path,rt['method'],body,expect=401,dimension=label,guard=True,**opts)
def write_results():
    (OUT/'events.json').write_text(json.dumps(EVENTS,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'cases.json').write_text(json.dumps(CASES,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'failures.json').write_text(json.dumps(FAILURES,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'api-execution.csv').open('w',encoding='utf-8-sig',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=['index','at','method','route','mock','dimension','expected_http','actual_http','passed','db_before','db_after']);wr.writeheader();wr.writerows({k:e.get(k) for k in wr.fieldnames} for e in EVENTS)
    summary=[]
    for rt in routes:
        es=[e for e in EVENTS if e['route']==rt['path'] and e['method']==rt['method'] and e['mock']==rt['mock']]
        summary.append(dict(rt,executed=len(es),passed=sum(e['passed'] for e in es),failed=sum(not e['passed'] for e in es),normal_success=sum(e['actual_http']<300 and e['passed'] for e in es),dimensions=sorted(set(e['dimension'] for e in es))))
    (OUT/'routes.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    (OUT/'version-start.json').write_text(json.dumps(version(),indent=2),encoding='utf-8')
    try:
        init();start();f.login()
        for n in [1,2]:negative_matrix(n)
        for n in [1,2]:case('complete-functional-round-'+str(n),lambda n=n:f.run_round(n));case('extra-flow-'+str(n),extra_flow);case('semantic-boundaries-'+str(n),semantic_boundaries)
        case('every-dependent-route-storage-failure',dependency_matrix)
    except Exception as e:
        FAILURES.append({'case':'harness','error':str(e)});print('FAIL harness',type(e).__name__,flush=True)
    finally:
        stop();write_results();(OUT/'version-end.json').write_text(json.dumps(version(),indent=2),encoding='utf-8')
        print(json.dumps({'cases':len(CASES),'failed':len(FAILURES),'events':len(EVENTS)}),flush=True)
    sys.exit(1 if FAILURES else 0)
