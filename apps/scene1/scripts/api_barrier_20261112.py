"""Explicit barrier concurrency through real HTTP/isolated MySQL; no production edits."""
import importlib.util,pathlib,json,threading,concurrent.futures,datetime,time,sys,hashlib
P=pathlib.Path(__file__).with_name('api_matrix_20261112.py');sp=importlib.util.spec_from_file_location('matrix',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
m.OUT=m.OUT/'barrier';m.OUT.mkdir(exist_ok=True);ROUNDS=[]
def race(label,actions):
    barrier=threading.Barrier(len(actions));results=[]
    def run(i,action):
        path,method,body,role,expected,idem,extra=action
        barrier.wait(timeout=10);started=datetime.datetime.now(datetime.timezone.utc).isoformat();index=len(m.EVENTS)
        response=m.send(path,method,body,role=role,expect=expected,idem=idem,dimension='barrier:'+label,**extra)
        ended=datetime.datetime.now(datetime.timezone.utc).isoformat()
        event=next(e for e in reversed(m.EVENTS) if e.get('request_key')==idem and e['path']==path)
        return {'index':i,'request_key':idem,'start':started,'end':ended,'path':path,'method':method,'actual_http':event['actual_http'],'server_request_id':event['response'].get('meta',{}).get('request_id'),'response':response}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(actions)) as pool:results=list(pool.map(lambda x:run(*x),enumerate(actions)))
    return {'label':label,'barrier_parties':len(actions),'requests':results,'db_summary_after_requests':conservation()}
def act(path,body,role,expected=(200,201,202,409),method='POST',idem=None,**extra):return (path,method,body,role,expected,idem or m.key(),extra)
def conservation():
    s=m.send('/api/v1/operator/summary',role='operator')
    assert int(s['total_received_cents'])-int(s['refunded_cents'])==int(s['net_cents'])
    for p in s['inventory']:assert p['initial_quantity']+p['adjustment_net']==p['available_quantity']+p['reserved_quantity']+p['shipped_quantity']
    return s
def round_probes(n):
    f=m.f;f.stock(5);p=f.product()
    record=race('20buyers-round'+str(n),[act('/api/v1/buyer/orders',{'product_id':p['id'],'quantity':1},['buyer1','buyer2','buyer3'][i%3],(201,409)) for i in range(20)])
    winners=[r for r in record['requests'] if 'id' in r['response']];losers=[r for r in record['requests'] if 'error' in r['response']]
    assert len(winners)==5 and len(losers)==15 and all(r['response']['error']['code']=='OUT_OF_STOCK' for r in losers)
    assert f.product()['available_quantity']==0
    for r in winners:f.cancel(r['response'],['buyer1','buyer2','buyer3'][r['index']%3])
    assert f.product()['available_quantity']==5;o=f.create(role='buyer3');f.cancel(o,'buyer3');record['after']=conservation();ROUNDS.append(record)
    f.stock(40);o=f.create();f.pay(o)
    rec=race('apply-vs-ship-'+str(n),[act('/api/v1/buyer/orders/'+o['id']+'/refund-applications',{'reason':'并发申请'},'buyer1',(201,409)),act('/api/v1/warehouse/orders/'+o['id']+'/shipment',{'carrier':'并发教学','tracking_no':m.key()},'warehouse',(201,409))])
    assert sum('id' in r['response'] for r in rec['requests'])==1;state=f.order(o);assert state['status'] in ['SHIPPED','REFUND_REVIEW'];rec['order']=state;ROUNDS.append(rec)
    if state['status']=='REFUND_REVIEW':f.approve(next(r['response'] for r in rec['requests'] if r['index']==0));f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED')
    o=f.create();rec=race('payment-vs-cancel-'+str(n),[act('/api/v1/buyer/orders/'+o['id']+'/payments',{},'buyer1',(202,409)),act('/api/v1/buyer/orders/'+o['id']+'/cancel',{'reason':'并发取消'},'buyer1',(200,409))])
    time.sleep(1);state=f.order(o);assert state['status'] in ['CLOSED','PENDING_SHIPMENT'];assert not(state['status']=='CLOSED' and state['shipment']);rec['order']=state;ROUNDS.append(rec)
    o=f.create();m.send('/internal/demo/clock/advance','POST',{'seconds':600},admin=True)
    rec=race('payment-vs-expire-'+str(n),[act('/api/v1/buyer/orders/'+o['id']+'/payments',{},'buyer1',409),act('/api/v1/buyer/orders/'+o['id']+'/cancel',{'reason':'超时取消'},'buyer1',200)])
    state=f.order(o);assert state['status']=='CLOSED' and state['close_reason']=='TIMEOUT';rec['order']=state;ROUNDS.append(rec)
    o=f.create();f.pay(o);a=f.apply(o)
    rec=race('review-approve-vs-reject-'+str(n),[act('/api/v1/support/refund-applications/'+a['id']+'/review',{'decision':d,'reason':'并发'+d},'support',(200,409)) for d in ['APPROVE','REJECT']])
    assert sum('application' in r['response'] for r in rec['requests'])==1
    state=f.order(o);assert state['status'] in ['PENDING_SHIPMENT','REFUND_PROCESSING','REFUNDED'];rec['order']=state;ROUNDS.append(rec)
    if state['status']=='REFUND_PROCESSING':f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED')
    if state['status']=='PENDING_SHIPMENT':f.ship(o)
    o=f.create();f.pay(o);a=f.apply(o);f.rule(o,'TIMEOUT_AFTER_SUCCESS');refund=f.approve(a)['refund']
    state=f.poll(lambda:f.order(o),lambda x:x['refunds'][0]['status']=='UNKNOWN',8);attempt=state['refunds'][0]['attempts'][0];request=m.request_id(o,attempt)
    proof=m.send('/mock/v1/refunds/by-request/'+request+'?merchant_ref=scene1',signed=True,mock=True)
    receipt=state['receipts'][0];event={'event_id':m.key(),'merchant_ref':'scene1','txn_id':receipt['provider_txn_id'],'request_id':request,'refund_id':proof['refund_id'],'amount_cents':refund['amount_cents'],'currency':'CNY','status':'SUCCEEDED','occurred_at':proof['refunded_at']}
    rec=race('refund-report-vs-query-'+str(n),[act('/api/v1/channel/refund-notifications',event,None,200,signed=True),act('/api/v1/support/refunds/'+refund['id']+'/query',{'reason':'并发查询原尝试'},'support',202)])
    state=f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED');assert len(state['refunds'])==1 and len(state['refunds'][0]['attempts'])==1;assert m.sql("SELECT COUNT(*) FROM inventory_ledger WHERE event_type='REFUND_RELEASE' AND order_id='"+o['id']+"'")=='1';rec['order']=state;ROUNDS.append(rec)
    p=f.stock(30);k=m.key();rec=race('same-key-create-'+str(n),[act('/api/v1/buyer/orders',{'product_id':p['id'],'quantity':1},'buyer1',201,idem=k) for _ in range(2)])
    assert rec['requests'][0]['response']['id']==rec['requests'][1]['response']['id'] and f.product()['available_quantity']==29;f.cancel(rec['requests'][0]['response']);ROUNDS.append(rec)
    p=f.product();rec=race('price-vs-create-'+str(n),[act('/api/v1/operator/products/'+p['id'],{'version':p['version'],'reason':'并发调价','unit_price_cents':'12000'},'operator',(200,409),method='PATCH'),act('/api/v1/buyer/orders',{'product_id':p['id'],'quantity':1},'buyer1',201)])
    o=rec['requests'][1]['response'];assert o['unit_price_cents'] in ['10000','12000'] and o['amount_cents']==o['unit_price_cents'];f.cancel(o);ROUNDS.append(rec)
    p=f.product();m.send('/api/v1/operator/products/'+p['id'],'PATCH',{'version':p['version'],'reason':'恢复价格','unit_price_cents':'10000'},role='operator')
    rec['final_conservation']=conservation()
try:
    (m.OUT/'version-start.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
    m.init();m.start();m.f.login()
    for n in [1,2]:m.case('barrier-full-round-'+str(n),lambda n=n:round_probes(n))
finally:
    m.stop();m.write_results();(m.OUT/'barrier-rounds.json').write_text(json.dumps(ROUNDS,ensure_ascii=False,indent=2),encoding='utf-8');(m.OUT/'version-end.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
sys.exit(bool(m.FAILURES))
