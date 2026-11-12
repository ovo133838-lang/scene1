"""Evidence-linked route dimension matrix; unavailable dimensions remain NOT_RUN."""
import json,pathlib,csv,re,hashlib,datetime
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/apis')
SOURCES=[OUT,OUT/'followup',OUT/'final-probes',OUT/'ready-fault',OUT/'barrier'];events=[]
for src in SOURCES:
    if (src/'events.json').exists():
        for e in json.loads((src/'events.json').read_text(encoding='utf-8')):e['evidence']=str(src/'events.json')+'#'+str(e['index']);events.append(e)
routes=json.loads((OUT/'routes.json').read_text(encoding='utf-8'))
rows=[]
dto_source=(APP/'internal/service/views.go').read_text(encoding='utf-8')
dto_block=dto_source.split('var dtoFields = map[string]string{',1)[1].split('\n}',1)[0]
dto={k:set(v.split()) for k,v in re.findall(r'"(\w+)":\s+"([^"]+)"',dto_block)}
dto['orders'].add('payment_deadline_passed');dto['refunds'].add('attempts')
orderdetail=dto['orders']|set('paid_at closed_at refunded_at shipped_at payment applications receipts refunds shipment anomalies executable_actions'.split())
anomalydetail=dto['payment_anomalies']|set('actions notifications receipt refund'.split())
checks=[]
for e in events:
    if not e['passed'] or e['actual_http']>=300 or 'data' not in e['response']:continue
    data=e['response']['data'];rt=next((r for r in routes if (r['path'],r['method'],r['mock'])==(e['route'],e['method'],e['mock'])),None)
    if not rt:continue
    op=rt['op'];schema=None;objs=[]
    if op in ['products','orders','refund_applications','refunds','payment_anomalies','channel_notifications','receipts']:
        schema=dto[op];objs=data['items']
    elif op in ['order','create_order','cancel']:schema=orderdetail;objs=[data]
    elif op=='warehouse':schema=set('id order_no name_snapshot quantity paid_at can_ship'.split());objs=data['items']
    elif op in ['pay','query_payment']:schema=dto['payment_intents'];objs=[data]
    elif op=='ship':schema=dto['shipments'];objs=[data]
    elif op=='apply':schema=dto['refund_applications'];objs=[data]
    elif op in ['retry_refund','query_refund','refund_anomaly']:schema=dto['refunds'];objs=[data]
    elif op in ['anomaly','verify','resolve_anomaly']:schema=anomalydetail;objs=[data]
    elif op=='update_product':schema=dto['products'];objs=[data]
    elif op=='adjust':schema=dto['inventory_ledger'];objs=[data]
    elif op=='me':schema=set('id login_name display_name role'.split());objs=[data]
    elif op=='logout':schema={'revoked'};objs=[data]
    elif op in ['notify_payment','notify_refund']:schema={'notification_id','result'};objs=[data]
    elif op in ['live','mock_live']:schema={'status'};objs=[data]
    elif op=='ready':schema={'status','version'};objs=[data]
    elif op in ['clock','advance']:schema=set('business_now advanced_seconds offset_seconds version'.split());objs=[data]
    elif op=='review':schema={'application','refund'};objs=[data]
    elif op=='reconciliation':schema=set('order inventory_entries receipts refunds shipment anomalies audit_events received_cents refunded_cents net_cents unresolved_count consistent differences'.split());objs=[data]
    elif op=='summary':schema=set('as_of normal_received_cents exception_received_cents total_received_cents refunded_cents net_cents unverified_notification_count unknown_refund_count failed_refund_count unresolved_anomaly_count inventory reconciliation_link_template receipt_list_path refund_list_path anomaly_list_path'.split());objs=[data]
    elif op in ['payment','payment_query','transaction_query']:schema=set('merchant_ref request_id order_ref txn_id amount_cents currency status paid_at'.split());objs=[data]
    elif op in ['refund','refund_query']:schema=set('merchant_ref request_id txn_id refund_id amount_cents currency status failure_code refunded_at'.split());objs=[data]
    elif op=='replay':schema={'event_id','queued'};objs=[data]
    elif op=='rule':schema=set('id target_order_ref attempt_no operation mode delay_ms repeat_count remaining_uses created_at'.split())|({'target_request_id'} if 'target_request_id' in data else set());objs=[data]
    if schema is not None:
        ok=all(set(o)==schema for o in objs)
        checks.append({'route':e['route'],'mock':e['mock'],'method':e['method'],'source_event':e['evidence'],'objects':len(objs),'actual_keys':[sorted(o) for o in objs[:1]],'expected_keys':sorted(schema),'passed':ok})
(OUT/'dto-whitelist-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
def add(rt,dimension,es,reason='',required=True):
    # Preserve old false-negative evidence while evaluating a later explicit re-test.
    old=[e for e in es if not e['passed']]
    if old and dimension=='HMAC tampering window direction':
        retested=[e for e in es if '/followup/' in e['evidence'].replace('\\','/') and e['dimension']=='timestamp-future' and e['passed']]
        if retested:
            es=[e for e in es if e['passed']];reason+='; old +301s fixture could enter legal +300s window during DB snapshot, explicit +360s retest passed; old failure retained'
    rows.append({'method':rt['method'],'route':rt['path'],'scope':'mock' if rt['mock'] else 'shop','dimension':dimension,'status':'PASS' if es and all(e['passed'] for e in es) else 'FAIL' if es else 'NOT_RUN' if required else 'NOT_APPLICABLE','reason':reason,'executed':len(es),'evidence':';'.join(e['evidence'] for e in (es[:6]+old[:2]))})
for rt in routes:
    es=[e for e in events if (e['route'],e['method'],e['mock'])==(rt['path'],rt['method'],rt['mock'])]
    add(rt,'normal status and returned facts',[e for e in es if e['passed'] and e['actual_http']<300])
    cs=[c for c in checks if (c['route'],c['mock'],c['method'])==(rt['path'],rt['mock'],rt['method'])]
    if rt['op']=='login':cs=[dict(passed=e['response']['dto_valid']) for e in es if e['actual_http']==200 and 'dto_valid' in e['response']]
    rows.append({'method':rt['method'],'route':rt['path'],'scope':'mock' if rt['mock'] else 'shop','dimension':'exact runtime DTO whitelist','status':'PASS' if cs and all(c['passed'] for c in cs) else 'FAIL' if cs else 'NOT_RUN','reason':'' if cs else 'special envelope/DTO needs dedicated assertion','executed':len(cs),'evidence':str(OUT/'dto-whitelist-checks.json')})
    for label,dims,applies,reason in [
        ('strict request fields',['unknown-body','array','trailing-json','duplicate-key','invalid-utf8','oversized'],rt['method']!='GET','GET has no JSON request DTO'),
        ('authentication',['no-auth','forged-auth','no-admin','no-hmac'],bool(rt['role']),'public login and health intentionally anonymous'),
        ('expired revoked disabled',['expired','revoked','disabled'],rt['role'] in ['BUYER','OPERATOR','WAREHOUSE','SUPPORT','*'],'human session lifecycle only; service HMAC/admin use separate credentials'),
        ('wrong role',['wrong-role','user-token-is-not-admin'],rt['role'] in ['BUYER','OPERATOR','WAREHOUSE','SUPPORT','ADMIN','CLOCK'],'anonymous/all-session/HMAC routes have no human role restriction'),
        ('same-key replay',['same-key-replay','new-nonce-same-request'],rt['write'] or rt['op'] in ['payment','refund'],'read-only/query/admin controls do not promise business-key idempotency'),
        ('same-key different parameters',['same-key-different-valid-body','same-key-different-body'],(rt['write'] and rt['required']) or rt['op'] in ['payment','refund'],'empty-JSON payment/query have no alternative valid body; reads/admin are not business-key commands'),
        ('storage dependency failure',['storage-unavailable'],rt['op'] not in ['live','mock_live'],'liveness intentionally does not depend on database'),
        ('other buyer ownership',['other-owner'],rt['role']=='BUYER' and '{' in rt['path'],'only buyer object routes bind caller ownership; staff scopes are role-wide'),
        ('illegal business state',['illegal-state','closed-order-illegal-state'],rt['op'] in ['create_order','cancel','pay','apply','ship','review','retry_refund','refund_anomaly','resolve_anomaly','update_product','adjust'],'route permits querying/re-verifying facts regardless of aggregate state, or has no business transition'),
    ]:
        add(rt,label,[e for e in es if e['dimension'] in dims],reason if not applies else '',applies)
    add(rt,'required and optional field values',[e for e in es if any(e['dimension'].startswith(p) for p in ['missing:','null:','wrong-type:','empty:','whitespace:','control:','overlong:','fraction:','numeric-string:','int-overflow:','money:'])],'' if rt['method']!='GET' and rt['required']+rt['optional'] else 'no body fields declared',bool(rt['required']+rt['optional']))
    add(rt,'pagination and filter bounds',[e for e in es if e['dimension'].startswith(('limit:','forged-cursor','invalid-filter:'))],'' if 'limit' in rt['query'] else 'route has no page cursor/limit contract','limit' in rt['query'])
    add(rt,'HMAC tampering window direction',[e for e in es if e['dimension'] in ['timestamp-old','timestamp-future','wrong-body','wrong-path','wrong-direction','short-nonce']],'' if rt['role']=='HMAC' else 'human/admin authentication uses bearer credentials',rt['role']=='HMAC')
with (OUT/'route-dimension-matrix.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    w=csv.DictWriter(fh,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(OUT/'route-dimension-matrix.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'rows':len(rows),'status':{s:sum(x['status']==s for x in rows) for s in ['PASS','FAIL','NOT_RUN','NOT_APPLICABLE']},'events':len(events)},ensure_ascii=False))
