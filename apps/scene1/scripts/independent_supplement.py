import importlib.util,json,pathlib
APP=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('independent',APP/'scripts/independent_testing.py');i=importlib.util.module_from_spec(spec);spec.loader.exec_module(i);f=i.f
passed=False
try:
    f.start()
    for n in [1,2]:
        f.login();f.request('/health/live');f.stock(10);o=f.create();f.pay(o)
        data=f.order(o);p=data['payment']
        f.request('/api/v1/buyer/payments/'+p['id']+'/query','POST',{},role='buyer1',expect=202)
        a=f.apply(o);f.approve(a);done=f.poll(lambda:f.order(o),lambda x:x['status']=='REFUNDED');r=done['refunds'][0];attempt=r['attempts'][-1]
        request_id=f.get_refund_request(o,attempt)
        proof=f.request('/mock/v1/refunds/by-request/'+request_id+'?merchant_ref=scene1',signed=True,mock=True)
        repeated=f.request('/mock/v1/refunds','POST',{'merchant_ref':'scene1','request_id':request_id,'txn_id':done['receipts'][0]['provider_txn_id'],'amount_cents':r['amount_cents'],'currency':'CNY'},signed=True,mock=True)
        assert repeated['refund_id']==proof['refund_id']
        assert f.product()['available_quantity']==10
        print('PASS supplement round',n,': payment query, liveness, provider refund idempotency',flush=True)
    passed=True
finally:
    f.stop();(i.OUT/'http-supplement.json').write_text(json.dumps({'passed':passed,'rounds':2,'login':'PASS, 6 accounts each round; credentials/results excluded','events':f.EVENTS},ensure_ascii=False,indent=2),encoding='utf-8')
