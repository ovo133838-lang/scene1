"""Final independent retest of AC001-004, only isolated test schemas."""
import contextlib,datetime,hashlib,hmac,importlib.util,json,pathlib,re,subprocess,time,urllib.request,urllib.error
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=APP/'evidence/independent-testing-final';OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('independent_base',APP/'scripts/independent_testing.py')
i=importlib.util.module_from_spec(spec);spec.loader.exec_module(i)
i.OUT=OUT;i.EXE=APP/'bin/scene1-independent-final.exe';f=i.f

# Existing regression's broad poll returns historic anomalies before this run's
# notification arrives. Wait by exact channel transaction without changing assertions.
original_lists=f.lists
def fresh_lists(path,role,**filters):
    rows=original_lists(path,role,**filters)
    if filters.get('type')=='UNKNOWN_ORDER':
        latest=next((e['result']['data']['txn_id'] for e in reversed(f.EVENTS) if e.get('method')=='POST' and e.get('path')=='/mock/v1/payments' and e.get('result',{}).get('data',{}).get('txn_id')),None)
        if latest:
            found=False
            for row in rows:
                detail=f.request('/api/v1/support/payment-anomalies/'+row['id'],role=role)
                if any(note.get('provider_txn_id')==latest for note in detail['notifications']):found=True;break
            if not found:return []
    return rows
f.lists=fresh_lists

def envelope(path,body,role):
    raw=json.dumps(body,separators=(',',':')).encode()
    req=urllib.request.Request(f.BASE+path,data=raw,headers={'Content-Type':'application/json','Idempotency-Key':f.key(),'Authorization':'Bearer '+f.TOKENS[role],'X-Request-Id':'caller-controlled-id'},method='POST')
    with urllib.request.urlopen(req,timeout=15) as res:status=res.status;pack=json.load(res)
    f.EVENTS.append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'POST','path':path,'status':status,'result':pack})
    return pack

def signature_probe():
    path='/mock/v1/payments/by-request/no-such-request?merchant_ref=scene1'
    stamp=str(int(time.time()));nonce=f.key();key_id='shop-to-mock'
    raw='\n'.join(['GET',path,stamp,nonce,hashlib.sha256(b'').hexdigest()])
    derived=hmac.new(f.CFG['SCENE1_HMAC_SECRET'].encode(),key_id.encode(),hashlib.sha256).digest()
    signature=hmac.new(derived,raw.encode(),hashlib.sha256).hexdigest()
    base_headers={'X-Key-Id':key_id,'X-Timestamp':stamp,'X-Nonce':nonce,'X-Signature':signature}
    for label,headers,expect in [('wrong-direction',dict(base_headers,**{'X-Key-Id':'mock-to-shop'}),401),('original',base_headers,404),('replayed-nonce',base_headers,401)]:
        req=urllib.request.Request(f.MOCK+path,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=15) as res:status=res.status;body=json.load(res)
        except urllib.error.HTTPError as e:status=e.code;body=json.load(e)
        assert status==expect,(label,status,body)
        f.EVENTS.append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'probe':label,'method':'GET','path':path,'status':status,'result':body})

def ac_probes(n):
    f.stock(20)
    order=envelope('/api/v1/buyer/orders',{'product_id':f.product()['id'],'quantity':1},'buyer1')
    o=order['data'];request_id=order['meta']['request_id']
    assert request_id!='caller-controlled-id' and re.fullmatch('[a-f0-9-]{36}',request_id)
    rec=f.request('/api/v1/operator/orders/'+o['id']+'/reconciliation',role='operator')
    events=[a for a in rec['audit_events'] if a['entity_id']==o['id'] and a['action']=='CREATE']
    assert len(events)==1 and events[0]['request_id']==request_id,events
    f.pay(o)
    page=f.request('/api/v1/warehouse/orders?limit=1',role='warehouse')
    assert page['items']
    expected={'id','order_no','name_snapshot','quantity','paid_at','can_ship'}
    for item in page['items']:assert set(item)==expected,item
    if page['next_cursor']:
        from urllib.parse import quote
        second=f.request('/api/v1/warehouse/orders?limit=1&cursor='+quote(page['next_cursor']),role='warehouse')
        assert all(set(row)==expected and row['id']!=page['items'][0]['id'] for row in second['items'])
    f.apply(o)
    # Verify strict external IDs at signed HTTP boundary; invalid notifications persist safely.
    sample={'event_id':f.key(),'merchant_ref':'scene1','order_ref':f.key(),'request_id':f.key(),'txn_id':f.key(),'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    for key in ['event_id','merchant_ref','order_ref','request_id','txn_id']:
        for value in ['中文','a?b','a#b','a/b','a%b','.', '..','x'*81]:
            body=dict(sample);body[key]=value
            f.request('/api/v1/channel/payment-notifications','POST',body,signed=True,expect=400)
    safe=dict(sample);safe['order_ref']='unknown-order.1_a'
    f.request('/api/v1/channel/payment-notifications','POST',safe,signed=True)
    # Independently built fixed canonical; no Go Sign helper and no live secrets in output.
    canonical='POST\n/mock/v1/payments?a=one%20two&z=%E4%B8%AD\n1700000000\n0123456789abcdef\n'+hashlib.sha256(b'{}').hexdigest()
    derived=hmac.new(b'vector-secret',b'shop-to-mock',hashlib.sha256).digest()
    assert hmac.new(derived,canonical.encode(),hashlib.sha256).hexdigest()=='e72c506718f45af3fe693c68f2f7c9d2068dd8397d95beaedef19fa99ce16bad'
    signature_probe()
    print('PASS AC001-004 round',n,': safe IDs, six-field warehouse/pagination, direction canonical vector, audit correlation',flush=True)

def supplement(n):
    f.login();f.request('/health/live');f.stock(20);o=f.create();f.pay(o)
    payment=f.order(o)['payment'];f.request('/api/v1/buyer/payments/'+payment['id']+'/query','POST',{},role='buyer1',expect=202)
    a=f.apply(o);f.approve(a);done=f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED');r=done['refunds'][0];attempt=r['attempts'][-1]
    request_id=f.get_refund_request(o,attempt)
    proof=f.request('/mock/v1/refunds/by-request/'+request_id+'?merchant_ref=scene1',signed=True,mock=True)
    repeated=f.request('/mock/v1/refunds','POST',{'merchant_ref':'scene1','request_id':request_id,'txn_id':done['receipts'][0]['provider_txn_id'],'amount_cents':r['amount_cents'],'currency':'CNY'},signed=True,mock=True)
    assert repeated['refund_id']==proof['refund_id']
    print('PASS supplement round',n,': remaining routes/provider refund idempotency',flush=True)

if __name__=='__main__':
    success=False;i.snapshot('version-start.json')
    subprocess.run(['go','build','-o',str(i.EXE),'./cmd/scene1'],cwd=APP,check=True)
    (OUT/'binary-sha256.txt').write_text(hashlib.sha256(i.EXE.read_bytes()).hexdigest()+'\n')
    try:
        f.start()
        for n in [1,2]:
            f.run_round(n);supplement(n);ac_probes(n)
        before=f.request('/api/v1/operator/summary',role='operator');f.stop();f.start();f.login();after=f.request('/api/v1/operator/summary',role='operator')
        assert before['total_received_cents']==after['total_received_cents'] and before['refunded_cents']==after['refunded_cents']
        print('PASS final restart persistence',flush=True)
        i.db_probes();success=True
    finally:
        f.stop();i.snapshot('version-end.json')
        (OUT/'http-regression.json').write_text(json.dumps({'passed':success,'rounds':2,'login':'6 accounts executed each round; credentials/results excluded','events':f.EVENTS},ensure_ascii=False,indent=2),encoding='utf-8')
