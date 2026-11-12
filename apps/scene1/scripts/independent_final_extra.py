import importlib.util,json,pathlib,urllib.parse
APP=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('final_test',APP/'scripts/independent_final.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);f=m.f
passed=False
try:
    f.start();f.login()
    for n in [1,2]:
        for key in ['refund_id','target_order_ref','target_request_id']:
            for bad in ['中','a?b','a#b','a/b','a%b','.', '..','x'*81]:
                if key=='refund_id':
                    body={'event_id':f.key(),'merchant_ref':'scene1','request_id':f.key(),'txn_id':f.key(),'refund_id':bad,'amount_cents':'1','currency':'CNY','status':'SUCCEEDED','occurred_at':'2026-11-12T00:00:00Z'}
                    f.request('/api/v1/channel/refund-notifications','POST',body,signed=True,expect=400)
                else:
                    body={'target_order_ref':f.key(),'operation':'PAYMENT','mode':'SUCCESS',key:bad}
                    f.request('/mock/admin/rules','POST',body,admin=True,mock=True,expect=400)
        f.request('/mock/v1/transactions/a%3Fb?merchant_ref=scene1',signed=True,mock=True,expect=400)
        f.request('/mock/v1/transactions/valid-id?merchant_ref=a%23b',signed=True,mock=True,expect=400)
        f.stock(20);orders=[f.create(),f.create()]
        for o in orders:f.pay(o)
        first=f.request('/api/v1/warehouse/orders?limit=1',role='warehouse');assert first['next_cursor']
        second=f.request('/api/v1/warehouse/orders?limit=1&cursor='+urllib.parse.quote(first['next_cursor']),role='warehouse')
        assert first['items'][0]['id']!=second['items'][0]['id']
        expected={'id','order_no','name_snapshot','quantity','paid_at','can_ship'}
        assert all(set(row)==expected for page in [first,second] for row in page['items'])
        for o in orders:f.apply(o)
        print('PASS additional external IDs and deterministic warehouse pagination round',n,flush=True)
    passed=True
finally:
    f.stop();(m.OUT/'http-extra.json').write_text(json.dumps({'passed':passed,'rounds':2,'events':f.EVENTS},ensure_ascii=False,indent=2),encoding='utf-8')
