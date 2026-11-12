"""Turn actual field probes into dimension-level, evidence-linked accounting.

An observation with expected=accept|reject is not a rule assertion.
"""
import pathlib,json,csv,collections
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/fields')
matrix=json.loads((OUT/'field-matrix.json').read_text(encoding='utf-8'))
cases=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
extra=json.loads((OUT/'strict-extra.json').read_text(encoding='utf-8'))['cases'] if (OUT/'strict-extra.json').exists() else []
http=json.loads((OUT/'http-field-results.json').read_text(encoding='utf-8')) if (OUT/'http-field-results.json').exists() else []
api_links=json.loads((OUT/'api-input-links.json').read_text(encoding='utf-8')) if (OUT/'api-input-links.json').exists() else []
semantics=json.loads((OUT/'semantics-results.json').read_text(encoding='utf-8')) if (OUT/'semantics-results.json').exists() else {}
semantic_links=semantics.get('links',[]) if semantics.get('passed') and semantics.get('source_unchanged') else []
semantic_notes={
'accounts':'Actual six-role login; id/time/display/role/enabled; password differs from plaintext and successful authentication; hash/token values never serialized.',
'sessions':'Actual token SHA256 -> session -> authenticated account; expiry after creation; actual logout sets revoked_at and same token becomes401.',
'products':'Actual operator versioned update and order snapshot comparison; quantities tied to every inventory vector, ordered before/after and final conserved totals.',
'orders':'Actual buyer ownership404/role403, snapshot immutability, exact10min, same-order normal receipt/active buyer application; paid,closed,shipped,review,processing,refunded checkpoints.',
'inventory_ledger':'Actual ADJUST/RESERVE/CLOSE_RELEASE/REFUND_RELEASE/SHIP vector, per-order event key/actor/refund references; every consecutive balance and final product equality.',
'payment_intents':'Actual same-order amount/currency/provider request; channel transaction binding, active generated slot, explicit failure, trusted query time and success.',
'receipts':'Actual merchant-owned successful channel txn/order/amount proof; same-order intent, NORMAL/LATE classification and generated normal_order; duplicate callbacks do not add funds.',
'channel_notifications':'Actual raw-body SHA256, claimed amount, redacted event/order/txn/refund reference equality; receipt/attempt linkage, result/auth/reason/time; duplicates, replay and conflict.',
'auth_nonces':'Actual directional key and bounded random nonce; expiry after creation; identical signed shop nonce second request401 with one persisted nonce; mock nonce directional binding.',
'refund_applications':'Actual same-buyer/order; pending nullable review fields; approved/rejected support/reason/time; reject clears active pointer and reapply retains old row.',
'refunds':'Actual same receipt/order/full amount; NORMAL approved same-order app; EXCEPTION verified merchant funds; current attempt ownership/max sequence; success times; late refund releases no stock.',
'refund_attempts':'Actual FAILED attempt preserved, retry creates next number/new provider request; UNKNOWN409 leaves original key, query same attempt; proof/status/provider refund/channel amount; generated active slot.',
'shipments':'Actual same-order paid SHIPPED/time/operator role/carrier/tracking; repeat409 and refund freeze409; order shipment timestamp equals row.',
'payment_anomalies':'Actual late/transaction/result/signature issues retained; verify FUNDS_CONFIRMED -> same receipt/refund -> RESOLVED with reason/time, no order reopen.',
'anomaly_actions':'Actual retained verification/refund/resolution actions, same anomaly/support-or-system, reason/evidence JSON and from/to states.',
'idempotency_records':'Actual same actor/operation/key replay same order, changed parameters409; recompute exact request hash; resource type/id/status and one inventory reservation.',
'outbox_jobs':'Actual aggregate ownership and stable original job key; UNKNOWN transitions SEND->QUERY while fixed key preserved, RETRY/error/next_run/attempt_count; lease on RUNNING.',
'audit_events':'Actual response meta.request_id joins USER CREATE/REVIEW/SHIP events; actor/entity/JSON/reason/time; rejected application history retained.',
'demo_clock':'Actual admin clock+1 changes offset/version/updater/time and singleton id1.',
'channel_payments':'Actual merchant/request/order/txn amount/currency/time/status across normal, late, failed; shop intent and receipt joins.',
'channel_refunds':'Actual merchant/request/txn/full amount match original successful payment; FAILED and SUCCEEDED results with failure code or refund timestamp.',
'notification_jobs':'Actual kind/resource->channel transaction/refund, bounded remaining delivery/event id/due/lease and statuses; callback delivery observed in HTTP events.',
'simulation_rules':'Actual operation/mode targeted order, rule consumption remaining_uses0; nullable request/attempt targeting plus normal-input-results all optional fields roundtrip.',
}
meta=json.loads((OUT/'schema-metadata.json').read_text(encoding='utf-8'))
dimensions=[]
def record(row,dimension,selected,applicable=True,reason=''):
    strict=[c for c in selected if c.get('assertion_scope')!='observation-only']
    dimensions.append(dict(scope=row['scope'],table=row['table'],field=row['field'],dimension=dimension,status=('NOT_APPLICABLE' if not applicable else 'FAIL' if any(c['status']=='FAIL' for c in strict) else 'PASS' if strict and all(c['status']=='PASS' for c in strict) else 'NOT_RUN'),reason=reason,strict_cases=' '.join(c['id'] for c in strict),observational_cases=' '.join(c['id'] for c in selected if c.get('assertion_scope')=='observation-only'),evidence='results.json; schema-metadata.json'))
for row in matrix:
    relevant=[c for c in cases if c['schema']==row['schema'] and c['table']==row['table'] and row['field'] in c['field'].split(',')]
    table=meta[row['schema']][row['table']];generated=bool(row['generated_expression'])
    for dim,prefix in [('legal','legal-roundtrip'),('null','null'),('default','default'),('type','TYPE')]:
        selected=[c for c in relevant if c['category']==prefix] if prefix!='TYPE' else [c for c in relevant if any(x in c['category'] for x in ['overflow','wrong-type','datetime-invalid','json-invalid'])]
        if dim=='default':selected += [dict(c,id='EXTRA-'+str(i),assertion_scope='strict-behavior') for i,c in enumerate(extra) if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field'] and c['category']=='default']
        record(row,dim,selected,not generated,'generated column accepts only DEFAULT and is tested through expression/readonly probes' if generated else '')
    precision=[dict(c,id='EXTRA-'+str(i),assertion_scope='strict-behavior') for i,c in enumerate(extra) if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field'] and c['category']=='utc-microsecond-precision']
    record(row,'utc-microsecond-precision',precision,'datetime' in row['physical_type'],'non-datetime column')
    enums=[c for c in relevant if c['category'].startswith('enum-')];ranges=[c for c in relevant if c['category'].startswith(('range-','quantity-member-'))]
    record(row,'enum-or-range',enums+ranges,bool(enums or ranges),'no SQL range/enum for this column; stronger service rule separately checked' if not enums and not ranges else '')
    foreign=[c for c in relevant if c['category'].startswith('foreign-key-')]
    record(row,'foreign-key',foreign,any(c['CONSTRAINT_TYPE']=='FOREIGN KEY' and c['COLUMN_NAME']==row['field'] for c in table['constraints']),'no SQL FK on this field')
    unique=[c for c in relevant if c['category'].startswith(('unique-','conditional-unique'))]
    record(row,'unique',unique,any(c['CONSTRAINT_TYPE'] in ['UNIQUE','PRIMARY KEY'] and c['COLUMN_NAME']==row['field'] for c in table['constraints']),'no SQL unique/PK on this field')
    record(row,'generated-expression-readonly',[c for c in relevant if c['category'].startswith('generated-')],generated,'ordinary stored column' if not generated else '')
    assignment=[dict(c,id='HTTPFIELD-'+str(i),assertion_scope='strict-behavior') for i,c in enumerate(http) if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field'] and c['status'] in ['PASS','FAIL']]
    http_notrun=[c for c in http if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field'] and c['status']=='NOT_RUN']
    assignment += [dict(c,id='APILINK-'+str(i),assertion_scope='strict-behavior') for i,c in enumerate(api_links) if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field'] and c['status']=='PASS']
    record(row,'http-client-assignment',assignment,row['table'] not in ['runtime_lock','schema_migrations'],'declared API input; separate semantic matrix evidence needed' if http_notrun else 'technical table no public endpoint' if row['table'] in ['runtime_lock','schema_migrations'] else 'real HTTP unknown persisted field returns400; inventory/funds/order snapshot unchanged')
    sem=[dict(c,id=c['case_id'],assertion_scope='strict-behavior') for c in semantic_links if c['scope']==row['scope'] and c['table']==row['table'] and c['field']==row['field']]
    record(row,'service-immutability-cross-table',sem,not(row['table'] in ['runtime_lock','schema_migrations']), 'technical migration/lock has no business service mutation route; migration behavior separately in upgrade-results.json' if row['table'] in ['runtime_lock','schema_migrations'] else row['contract_requirement']+'; '+semantic_notes.get(row['table'],'')+' Declared field/scenario predicates only; not every theoretical branch/failure or arbitrary corrupt DB combination.')
    if sem:dimensions[-1]['evidence']='semantics-results.json cases+events+source_unchanged; field_semantics_20261112.py; http-field-results.json; api-input-links.json; normal-input-results.json'
with (OUT/'field-dimensions.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    wr=csv.DictWriter(fh,fieldnames=list(dimensions[0]));wr.writeheader();wr.writerows(dimensions)
(OUT/'field-dimensions.json').write_text(json.dumps(dimensions,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(collections.Counter(r['status'] for r in dimensions))))
