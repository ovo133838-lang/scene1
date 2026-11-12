"""Real HTTP/MySQL regression. Uses dedicated scene1_test schemas; never truncates business data."""
import concurrent.futures,datetime,hashlib,hmac,json,os,pathlib,subprocess,sys,time,urllib.request,urllib.error,uuid,argparse
APP=pathlib.Path(__file__).resolve().parents[1]
CFG=dict(line.split('=',1) for line in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'))
BASE='http://127.0.0.1:18090'; MOCK='http://127.0.0.1:18091'; EVENTS=[]; TOKENS={}; PROCS=[]
def key():return str(uuid.uuid4())
def request(path,method='GET',body=None,role=None,expect=200,signed=False,admin=False,mock=False,idem=None,raw=None):
    data=(json.dumps(body,separators=(',',':'),ensure_ascii=False).encode() if body is not None else None) if raw is None else raw
    headers={'Content-Type':'application/json'}
    if method!='GET':headers['Idempotency-Key']=idem or key()
    if role:headers['Authorization']='Bearer '+TOKENS[role]
    if admin:headers['Authorization']='Bearer '+CFG['SCENE1_ADMIN_TOKEN']
    if signed:
        stamp=str(int(time.time()));nonce=key();pp,_,query=path.partition('?')
        from urllib.parse import parse_qsl,quote,urlencode
        query=urlencode(sorted(parse_qsl(query,keep_blank_values=True)),quote_via=quote,safe='~')
        canonical='\n'.join([method,pp+('?' + query if query else ''),stamp,nonce,hashlib.sha256(data or b'').hexdigest()])
        key_id='shop-to-mock' if pp.startswith('/mock/') else 'mock-to-shop'
        direction_key=hmac.new(CFG['SCENE1_HMAC_SECRET'].encode(),key_id.encode(),hashlib.sha256).digest()
        sig=hmac.new(direction_key,canonical.encode(),hashlib.sha256).hexdigest()
        headers.update({'X-Key-Id':key_id,'X-Timestamp':stamp,'X-Nonce':nonce,'X-Signature':sig})
    req=urllib.request.Request((MOCK if mock else BASE)+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as res:status=res.status;out=json.load(res)
    except urllib.error.HTTPError as e:status=e.code;out=json.load(e)
    assert status in ([expect] if isinstance(expect,int) else expect),(method,path,status,out)
    if path!='/api/v1/auth/login':EVENTS.append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':method,'path':path,'status':status,'result':out})
    return out.get('data',out)
def poll(fn,check,seconds=14):
    end=time.monotonic()+seconds;v=None
    while time.monotonic()<end:
        v=fn()
        if check(v):return v
        time.sleep(.15)
    raise AssertionError(('poll timeout',v))
def start():
    logs=APP/'bin';logs.mkdir(exist_ok=True)
    for mode,port in [('shop',18090),('mock',18091)]:
        env=os.environ.copy();env['SCENE1_PORT']=str(port)
        f=open(logs/f'test-{mode}.log','ab');p=subprocess.Popen([str(APP/'bin/scene1.exe'),'-mode',mode,'-env','.env.test.local'],cwd=APP,env=env,stdout=f,stderr=f,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));PROCS.append(p)
    for i in range(50):
        try:request('/health/ready');return
        except (OSError,AssertionError):time.sleep(.2)
    raise AssertionError('test services did not start; inspect ignored bin/test-*.log')
def stop():
    for p in PROCS:p.terminate()
    for p in PROCS:
        try:p.wait(10)
        except subprocess.TimeoutExpired:p.kill()
    PROCS.clear()
def login():
    for role in ['buyer1','buyer2','buyer3','operator','warehouse','support']:
        TOKENS[role]=request('/api/v1/auth/login','POST',{'login_name':role,'password':CFG['SCENE1_PASSWORD']})['token']
def lists(path,role,**filters):
    from urllib.parse import urlencode
    return request(path+'?'+urlencode(dict(limit=100,**filters)),role=role)['items']
def product():return sorted(lists('/api/v1/operator/products','operator'),key=lambda p:p['sku'])[0]
def stock(n):
    p=product();request('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'sale_status':'ON_SHELF','reason':'自动化隔离库测试上架'},role='operator');p=product()
    if n!=p['available_quantity']:request('/api/v1/operator/products/'+p['id']+'/inventory-adjustments','POST',{'version':p['version'],'delta':n-p['available_quantity'],'reason':'隔离库设置场景可售数量'},role='operator',expect=201)
    return product()
def create(p=None,role='buyer1',q=1,idem=None):return request('/api/v1/buyer/orders','POST',{'product_id':(p or product())['id'],'quantity':q},role=role,expect=201,idem=idem)
def order(o,role='buyer1'):return request('/api/v1/buyer/orders/'+o['id'],role=role)
def pay(o):
    payment=request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202)
    return poll(lambda:order(o),lambda v:v['status']=='PENDING_SHIPMENT')
def cancel(o,role='buyer1'):return request('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'场景测试取消'},role=role)
def apply(o):return request('/api/v1/buyer/orders/'+o['id']+'/refund-applications','POST',{'reason':'场景测试售前整单退款'},role='buyer1',expect=201)
def rule(o,mode,operation='REFUND',**kw):return request('/mock/admin/rules','POST',{'target_order_ref':o['id'],'operation':operation,'mode':mode,**kw},admin=True,mock=True,expect=201)
def approve(a,decision='APPROVE'):return request('/api/v1/support/refund-applications/'+a['id']+'/review','POST',{'decision':decision,'reason':'已核实教学订单申请'},role='support')
def ship(o,expect=201):return request('/api/v1/warehouse/orders/'+o['id']+'/shipment','POST',{'carrier':'教学承运方','tracking_no':'TEST-'+key()},role='warehouse',expect=expect)
def receipt_event(o):
    data=order(o);p=data['payment'];r=data['receipts'][0]
    proof=request('/mock/v1/transactions/'+r['provider_txn_id']+'?merchant_ref=scene1',signed=True,mock=True)
    return {'event_id':key(),'merchant_ref':'scene1','order_ref':o['id'],'request_id':proof['request_id'],'txn_id':r['provider_txn_id'],'amount_cents':r['amount_cents'],'currency':'CNY','status':'SUCCEEDED','occurred_at':proof['paid_at']}
def check(label,fn):
    start=time.monotonic();fn();print('PASS '+label,flush=True);EVENTS.append({'case':label,'passed':True,'elapsed_seconds':round(time.monotonic()-start,3)})
def run_round(number):
    login();prefix=f'round {number} / '
    def normal():
        stock(30);o=create();paid=pay(o);assert paid['amount_cents']=='10000';ship(o);done=order(o);assert done['shipment']['carrier']=='教学承运方';assert done['status']=='SHIPPED';rec=request('/api/v1/operator/orders/'+o['id']+'/reconciliation',role='operator');assert rec['consistent'] and rec['received_cents']=='10000' and rec['refunded_cents']=='0';ship(o,409);request('/api/v1/buyer/orders/'+o['id']+'/refund-applications','POST',{'reason':'不能售后退款'},role='buyer1',expect=409)
    check(prefix+'normal paid shipment reconciliation',normal)
    def concurrent_stock():
        p=stock(5)
        def buy(i):return request('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':1},role=['buyer1','buyer2','buyer3'][i%3],expect=[201,409])
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:results=list(pool.map(buy,range(20)))
        won=[(i,o) for i,o in enumerate(results) if 'id' in o];assert len(won)==5 and product()['available_quantity']==0
        for i,o in won:cancel(o,['buyer1','buyer2','buyer3'][i%3]);cancel(o,['buyer1','buyer2','buyer3'][i%3])
        assert product()['available_quantity']==5;other=create(role='buyer3');cancel(other,'buyer3');assert product()['available_quantity']==5
    check(prefix+'20 concurrent buys, abandon, release once, buy again',concurrent_stock)
    def refund_fail():
        stock(10);o=create();pay(o);a=apply(o);ship(o,409);rule(o,'EXPLICIT_FAIL',attempt_no=1);r=approve(a)['refund'];poll(lambda:request('/api/v1/support/refunds?status=FAILED&limit=100',role='support'),lambda x:any(v['id']==r['id'] for v in x['items']));assert order(o)['status']=='REFUND_PROCESSING';ship(o,409)
        request('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'渠道明确失败后重试'},role='support',expect=202);done=poll(lambda:order(o),lambda v:v['status']=='REFUNDED');assert len(done['refunds'])==1 and len(done['refunds'][0]['attempts'])==2;assert product()['available_quantity']==10
        request('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'禁止重复退'},role='support',expect=409);request('/api/v1/support/refunds/'+r['id']+'/query','POST',{'reason':'核查成功结果'},role='support',expect=202)
    check(prefix+'refund freeze, first failure then retry success',refund_fail)
    def late():
        stock(10);o=create();rule(o,'TIMEOUT_AFTER_SUCCESS','PAYMENT');request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202);cancel(o)
        an=poll(lambda:lists('/api/v1/support/payment-anomalies','support',type='LATE_PAYMENT'),lambda xs:any(v['order_id']==o['id'] for v in xs));a=next(v for v in an if v['order_id']==o['id']);assert order(o)['status']=='CLOSED';request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'未核实不能退'},role='support',expect=409)
        verified=request('/api/v1/support/payment-anomalies/'+a['id']+'/verify','POST',{'reason':'独立核实迟到款'},role='support');assert verified['verification']=='FUNDS_CONFIRMED';r=request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'迟到实收整笔退回'},role='support',expect=202);poll(lambda:request('/api/v1/support/payment-anomalies/'+a['id'],role='support'),lambda x:x['status']=='RESOLVED');assert product()['available_quantity']==10 and order(o)['status']=='CLOSED'
        again=request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'重复操作'},role='support',expect=202);assert again['id']==r['id'];request('/api/v1/operator/payment-anomalies/'+a['id'],role='operator')
    check(prefix+'late payment verification refund, no second stock release',late)
    def race():
        stock(20)
        for i in range(5):
            o=create();pay(o)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(request,'/api/v1/buyer/orders/'+o['id']+'/refund-applications','POST',{'reason':'并发退款申请'},'buyer1',[201,409]);b=pool.submit(ship,o,[201,409]);aa=a.result();bb=b.result()
            assert ('id' in aa)+('id' in bb)==1
            final=order(o);assert final['status'] in ['REFUND_REVIEW','SHIPPED']
            if final['status']=='REFUND_REVIEW':approve(aa);poll(lambda:order(o),lambda v:v['status']=='REFUNDED')
    check(prefix+'5 refund-application vs shipment races',race)
    def duplicates_permissions():
        stock(10);idem=key();o=create(idem=idem);same=create(idem=idem);assert same['id']==o['id'];request('/api/v1/buyer/orders','POST',{'product_id':product()['id'],'quantity':2},role='buyer1',idem=idem,expect=409);pay(o);ev=receipt_event(o)
        for i in range(3):assert request('/api/v1/channel/payment-notifications','POST',ev,signed=True)['result']=='DUPLICATE'
        wrong=dict(ev,order_ref=str(uuid.uuid4()));assert request('/api/v1/channel/payment-notifications','POST',wrong,signed=True)['result']=='TXN_CONFLICT'
        request('/api/v1/channel/payment-notifications','POST',ev,expect=401)
        request('/api/v1/buyer/orders/'+o['id'],role='buyer2',expect=404);request('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'越权'},role='buyer2',expect=404);request('/api/v1/operator/summary',role='buyer1',expect=403);request('/api/v1/support/orders/'+o['id'],role='support');request('/api/v1/buyer/orders?buyer_id='+str(uuid.uuid4()),role='buyer1',expect=400)
        for body in [{'product_id':product()['id'],'quantity':0},{'product_id':product()['id'],'quantity':1.5},{'product_id':product()['id'],'quantity':1,'buyer_id':str(uuid.uuid4())}]:request('/api/v1/buyer/orders','POST',body,role='buyer1',expect=400 if body.get('quantity')!=0 else 400)
        request('/api/v1/buyer/orders','POST',role='buyer1',raw=b'{"quantity":1,"quantity":2}',expect=400)
        request('/api/v1/buyer/orders?limit=0',role='buyer1',expect=400);request('/api/v1/buyer/orders?cursor=fake',role='buyer1',expect=400)
        a=apply(o);approve(a,'REJECT');o2=order(o);assert o2['status']=='PENDING_SHIPMENT';a2=apply(o);assert a2['id']!=a['id'];approve(a2);done=poll(lambda:order(o),lambda v:v['status']=='REFUNDED');rr=done['refunds'][0];attempt=rr['attempts'][-1]
        proof=request('/mock/v1/refunds/by-request/'+get_refund_request(o,attempt)+'?merchant_ref=scene1',signed=True,mock=True)
        event={'event_id':key(),'merchant_ref':'scene1','txn_id':ev['txn_id'],'request_id':proof['request_id'],'refund_id':proof['refund_id'],'amount_cents':rr['amount_cents'],'currency':'CNY','status':'SUCCEEDED','occurred_at':proof['refunded_at']}
        for i in range(3):assert request('/api/v1/channel/refund-notifications','POST',event,signed=True)['result']=='DUPLICATE'
        event['amount_cents']='1';assert request('/api/v1/channel/refund-notifications','POST',event,signed=True)['result']=='RESULT_CONFLICT'
    check(prefix+'idempotency, callbacks, review rejection, permissions, validation',duplicates_permissions)
    def timeout_snapshot_boundary():
        stock(10);o=create(q=2);p=product();request('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'name':'活动标准商品改名','unit_price_cents':'12000','sale_status':'OFF_SHELF','reason':'验证订单快照'},role='operator');paid=pay(o);assert paid['amount_cents']=='20000' and paid['unit_price_cents']=='10000';a=apply(o);rule(o,'TIMEOUT_AFTER_SUCCESS');r=approve(a)['refund'];unknown=poll(lambda:order(o),lambda x:x['refunds'][0]['status']=='UNKNOWN',seconds=8);assert unknown['status']=='REFUND_PROCESSING';ship(o,409);request('/api/v1/support/refunds/'+r['id']+'/retry','POST',{'reason':'未知不能重试'},role='support',expect=409);request('/api/v1/support/refunds/'+r['id']+'/query','POST',{'reason':'查询原退款'},role='support',expect=202);poll(lambda:order(o),lambda x:x['status']=='REFUNDED');assert product()['sale_status']=='OFF_SHELF'
        p=product();request('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'unit_price_cents':'10000','reason':'恢复场景价'},role='operator');stock(5);o=create();request('/internal/demo/clock',admin=True);request('/internal/demo/clock/advance','POST',{'seconds':600},admin=True);request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=409);done=poll(lambda:order(o),lambda x:x['status']=='CLOSED');assert done['close_reason']=='TIMEOUT' and product()['available_quantity']==5
    check(prefix+'snapshot, timeout refund UNKNOWN, no retry, full 10 minute boundary',timeout_snapshot_boundary)
    def exception_queries():
        stock(20);o=create();req=key();p=request('/mock/v1/payments','POST',{'merchant_ref':'scene1','request_id':req,'order_ref':o['id'],'amount_cents':'9999','currency':'CNY'},signed=True,mock=True);request('/mock/v1/payments/by-request/'+req+'?merchant_ref=scene1',signed=True,mock=True)
        a=poll(lambda:lists('/api/v1/support/payment-anomalies','support',type='AMOUNT_MISMATCH'),lambda xs:any(v['order_id']==o['id'] for v in xs));a=next(v for v in a if v['order_id']==o['id']);request('/api/v1/support/payment-anomalies/'+a['id']+'/verify','POST',{'reason':'核实真实差额资金'},role='support');request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'整笔异常退回'},role='support',expect=202);poll(lambda:request('/api/v1/support/payment-anomalies/'+a['id'],role='support'),lambda x:x['status']=='RESOLVED');cancel(o)
        p=request('/mock/v1/payments','POST',{'merchant_ref':'scene1','request_id':key(),'order_ref':str(uuid.uuid4()),'amount_cents':'8000','currency':'CNY'},signed=True,mock=True)
        a=poll(lambda:lists('/api/v1/support/payment-anomalies','support',type='UNKNOWN_ORDER'),lambda xs:any(v['id'] for v in xs));a=next(v for v in a if request('/api/v1/support/payment-anomalies/'+v['id'],role='support')['notifications'][0]['provider_txn_id']==p['txn_id']);request('/api/v1/support/payment-anomalies/'+a['id']+'/verify','POST',{'reason':'核实无订单收款'},role='support');request('/api/v1/support/payment-anomalies/'+a['id']+'/refund','POST',{'reason':'无订单实收退回'},role='support',expect=202);poll(lambda:request('/api/v1/support/payment-anomalies/'+a['id'],role='support'),lambda x:x['status']=='RESOLVED')
        fake={'event_id':key(),'merchant_ref':'scene1','order_ref':str(uuid.uuid4()),'request_id':key(),'txn_id':key(),'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':datetime.datetime.now(datetime.timezone.utc).isoformat()};request('/api/v1/channel/payment-notifications','POST',fake,expect=401);xs=lists('/api/v1/support/payment-anomalies','support',type='INVALID_SIGNATURE');a=next(x for x in xs if request('/api/v1/support/payment-anomalies/'+x['id'],role='support')['notifications'][0]['provider_txn_id']==fake['txn_id']);v=request('/api/v1/support/payment-anomalies/'+a['id']+'/verify','POST',{'reason':'排查伪造通知'},role='support');assert v['verification']=='NO_FUNDS';request('/api/v1/support/payment-anomalies/'+a['id']+'/resolve','POST',{'reason':'渠道证实没有真实交易'},role='support')
        ns=lists('/api/v1/support/notifications','support');event=next(n['provider_event_id'] for n in ns if n['auth_valid'] and n['provider_event_id']);request('/mock/admin/notifications/'+event+'/replay','POST',{'repeat_count':2,'delay_ms':0},admin=True,mock=True,expect=202)
    check(prefix+'mismatch, unknown order, fake signature, verify/refund/resolve, replay',exception_queries)
    def all_lists_auth():
        for path,role in [('/api/v1/products','buyer1'),('/api/v1/buyer/orders','buyer1'),('/api/v1/warehouse/orders','warehouse'),('/api/v1/support/refund-applications','support'),('/api/v1/support/refunds','support'),('/api/v1/support/notifications','support'),('/api/v1/operator/orders','operator'),('/api/v1/operator/receipts','operator'),('/api/v1/operator/refunds','operator'),('/api/v1/operator/payment-anomalies','operator')]:request(path,role=role)
        summary=request('/api/v1/operator/summary',role='operator');assert int(summary['total_received_cents'])-int(summary['refunded_cents'])==int(summary['net_cents'])
        for p in summary['inventory']:assert p['initial_quantity']+p['adjustment_net']==p['available_quantity']+p['reserved_quantity']+p['shipped_quantity']
        request('/api/v1/auth/me',role='buyer3');request('/api/v1/auth/logout','POST',{},role='buyer3');request('/api/v1/auth/me',role='buyer3',expect=401)
    check(prefix+'all role lists, funds and stock conservation, logout',all_lists_auth)
def get_refund_request(o,attempt):
    # Request IDs are intentionally not public DTOs. Read the provider event through the redacted channel notification trace.
    ns=poll(lambda:lists('/api/v1/support/notifications','support',kind='REFUND'),lambda xs:any(x['provider_refund_id']==attempt['provider_refund_id'] for x in xs))
    # The provider request is not in Notification DTO either; obtain it from the test-only signed provider lookup using known receipt/refund fixtures.
    # Query original request mapping from the local DB via the restricted test fixture utility below, never expose credentials or arbitrary production queries.
    import re
    dsn=CFG['SCENE1_MYSQL_DSN'];m=re.match(r'([^:]+):([^@]+)@tcp\(([^:]+):(\d+)\)/([^?]+)',dsn);assert m and m[5]=='scene1_test'
    env=os.environ.copy();env['MYSQL_PWD']=m[2]
    sql="SELECT provider_request_id FROM refund_attempts WHERE id='"+str(uuid.UUID(attempt['id']))+"';"
    out=subprocess.check_output(['C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe','--no-defaults','-N','-B','-h',m[3],'-P',m[4],'-u',m[1],m[5],'-e',sql],env=env,text=True)
    return out.strip()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rounds',type=int,default=2);args=parser.parse_args();outdir=APP/'evidence';outdir.mkdir(exist_ok=True);success=False
    try:
        start()
        for n in range(1,args.rounds+1):run_round(n)
        before=request('/api/v1/operator/summary',role='operator');stop();start();login();after=request('/api/v1/operator/summary',role='operator');assert before['total_received_cents']==after['total_received_cents'] and before['refunded_cents']==after['refunded_cents'];print('PASS restart persisted facts',flush=True);success=True
    finally:
        stop();(outdir/'http-regression.json').write_text(json.dumps({'passed':success,'rounds_requested':args.rounds,'events':EVENTS},ensure_ascii=False,indent=2),encoding='utf-8')
