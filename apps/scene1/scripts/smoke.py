"""Health and reversible business smoke on the actual released HTTP service."""
import os,json,urllib.request,uuid,sys,pathlib
base=os.environ.get('SCENE1_SMOKE_URL','http://127.0.0.1:18080').rstrip('/')
def call(path,method='GET',body=None,token=None):
    data=json.dumps(body).encode() if body is not None else None
    headers={'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())}
    if token:headers['Authorization']='Bearer '+token
    with urllib.request.urlopen(urllib.request.Request(base+path,data,headers,method=method),timeout=15) as res:
        return json.load(res)['data']
ready=call('/health/ready');live=call('/health/live')
expected=os.environ.get('SCENE1_EXPECT_VERSION')
if expected:assert ready.get('version')==expected,('unexpected release',ready)
password=os.environ['SCENE1_PASSWORD']
buyer=call('/api/v1/auth/login','POST',{'login_name':'buyer1','password':password})['token']
operator=call('/api/v1/auth/login','POST',{'login_name':'operator','password':password})['token']
try:
    before=call('/api/v1/operator/summary',token=operator)
    all_products=call('/api/v1/products',token=buyer)['items']
    available=[p for p in all_products if p['sale_status']=='ON_SHELF' and p['available_quantity']>0]
    assert available,'business smoke needs one on-shelf product with available quantity; seed products start off-shelf'
    p=available[0]
    o=call('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':1},buyer)
    try:
        own=call('/api/v1/buyer/orders/'+o['id'],token=buyer)
        assert own['status']=='PENDING_PAYMENT' and own['amount_cents']==p['unit_price_cents']
    finally:call('/api/v1/buyer/orders/'+o['id']+'/cancel','POST',{'reason':'release business smoke cleanup'},buyer)
    closed=call('/api/v1/buyer/orders/'+o['id'],token=buyer);assert closed['status']=='CLOSED'
    after=call('/api/v1/operator/summary',token=operator)
    for key in ('total_received_cents','refunded_cents','net_cents'):assert before[key]==after[key]
    bp=next(x for x in before['inventory'] if x['id']==p['id']);ap=next(x for x in after['inventory'] if x['id']==p['id'])
    for field in ('available_quantity','reserved_quantity','shipped_quantity','adjustment_net'):
        assert bp[field]==ap[field],('inventory changed',field,bp[field],ap[field])
    print(json.dumps({'status':'PASS','version':ready.get('version'),'order_id':o['id'],'final_order_status':closed['status'],'funds_unchanged':True,'inventory_unchanged':True}))
finally:
    for token in (buyer,operator):call('/api/v1/auth/logout','POST',{},token)
