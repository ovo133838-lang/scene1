"""Read-only semantic integrity assertions over the independent real HTTP test database.

These prove actual persistent invariants, not that every adversarial transition ran.
"""
import json,pathlib,datetime,pymysql,os
ROOT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12');OUT=ROOT/'fields'
field_summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
DB=field_summary['schemas'][0];MOCK=field_summary['schemas'][1]
CONFIG=dict(x.split('=',1) for x in (pathlib.Path(__file__).resolve().parents[1]/'.env.test.local').read_text(encoding='utf-8').splitlines() if x and not x.startswith('#'))
conn=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=(os.environ.get('SCENE1_FIELD_ROOT_PASSWORD') or CONFIG['SCENE1_FIELD_ROOT_PASSWORD']),database=DB,charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor)
checks=[
('normal-receipt-owner',['orders.normal_receipt_id','receipts.order_id','receipts.classification'],"SELECT COUNT(*) n FROM orders o JOIN receipts r ON r.id=o.normal_receipt_id WHERE r.order_id<>o.id OR r.classification<>'NORMAL'"),
('active-application-owner',['orders.active_application_id','refund_applications.order_id','refund_applications.buyer_id'],"SELECT COUNT(*) n FROM orders o JOIN refund_applications a ON a.id=o.active_application_id WHERE a.order_id<>o.id OR a.buyer_id<>o.buyer_id"),
('normal-refund-link',['refunds.order_id','refunds.application_id','refunds.receipt_id','refunds.kind','refunds.amount_cents','refund_applications.status'],"SELECT COUNT(*) n FROM refunds f LEFT JOIN refund_applications a ON a.id=f.application_id JOIN receipts r ON r.id=f.receipt_id WHERE f.kind='NORMAL' AND (a.id IS NULL OR a.status<>'APPROVED' OR NOT(a.order_id<=>f.order_id) OR NOT(r.order_id<=>f.order_id) OR r.amount_cents<>f.amount_cents OR r.classification<>'NORMAL')"),
('exception-refund-link',['refunds.anomaly_id','refunds.receipt_id','refunds.amount_cents','payment_anomalies.receipt_id'],"SELECT COUNT(*) n FROM refunds f LEFT JOIN payment_anomalies a ON a.id=f.anomaly_id JOIN receipts r ON r.id=f.receipt_id WHERE f.kind='EXCEPTION' AND (a.id IS NULL OR NOT(a.receipt_id<=>f.receipt_id) OR f.amount_cents<>r.amount_cents)"),
('current-attempt-owner',['refunds.current_attempt_id','refund_attempts.refund_id'],"SELECT COUNT(*) n FROM refunds f JOIN refund_attempts a ON a.id=f.current_attempt_id WHERE a.refund_id<>f.id"),
('normal-intent-owner',['receipts.payment_intent_id','payment_intents.order_id','payment_intents.amount_cents'],"SELECT COUNT(*) n FROM receipts r JOIN payment_intents p ON p.id=r.payment_intent_id WHERE r.classification='NORMAL' AND (NOT(r.order_id<=>p.order_id) OR r.amount_cents<>p.amount_cents)"),
('normal-receipt-snapshot',['orders.amount_cents','orders.paid_at','receipts.amount_cents','receipts.verified_at'],"SELECT COUNT(*) n FROM orders o JOIN receipts r ON r.id=o.normal_receipt_id WHERE o.amount_cents<>r.amount_cents OR NOT(o.paid_at<=>r.verified_at)"),
('shipment-and-order',['shipments.order_id','shipments.shipped_at','orders.shipped_at','orders.status'],"SELECT COUNT(*) n FROM shipments s JOIN orders o ON o.id=s.order_id WHERE o.status<>'SHIPPED' OR NOT(s.shipped_at<=>o.shipped_at)"),
('actor-roles',['orders.buyer_id','refund_applications.buyer_id','refund_applications.reviewer_id','refunds.created_by','shipments.operator_id'],"SELECT (SELECT COUNT(*) FROM orders o JOIN accounts a ON a.id=o.buyer_id WHERE a.role<>'BUYER')+(SELECT COUNT(*) FROM refund_applications r JOIN accounts a ON a.id=r.buyer_id WHERE a.role<>'BUYER')+(SELECT COUNT(*) FROM refund_applications r JOIN accounts a ON a.id=r.reviewer_id WHERE a.role<>'SUPPORT')+(SELECT COUNT(*) FROM refunds r JOIN accounts a ON a.id=r.created_by WHERE a.role<>'SUPPORT')+(SELECT COUNT(*) FROM shipments s JOIN accounts a ON a.id=s.operator_id WHERE a.role<>'WAREHOUSE') n"),
('inventory-live-owners',['products.reserved_quantity','products.shipped_quantity','products.available_quantity','products.adjustment_net','orders.quantity'],"SELECT COUNT(*) n FROM products p WHERE p.initial_quantity+p.adjustment_net<>p.available_quantity+p.reserved_quantity+p.shipped_quantity OR p.reserved_quantity<>(SELECT COALESCE(SUM(quantity),0) FROM orders o WHERE o.product_id=p.id AND o.status IN('PENDING_PAYMENT','PENDING_SHIPMENT','REFUND_REVIEW','REFUND_PROCESSING')) OR p.shipped_quantity<>(SELECT COALESCE(SUM(quantity),0) FROM orders o WHERE o.product_id=p.id AND o.status='SHIPPED')"),
('normal-refund-only-release',['inventory_ledger.refund_id','inventory_ledger.event_type','refunds.kind'],"SELECT COUNT(*) n FROM inventory_ledger l JOIN refunds f ON f.id=l.refund_id WHERE f.kind<>'NORMAL' OR l.event_type<>'REFUND_RELEASE'"),
('one-release-per-refund',['inventory_ledger.refund_id','refunds.status','refunds.settled_at'],"SELECT COUNT(*) n FROM refunds f WHERE f.kind='NORMAL' AND ((f.status='SUCCEEDED' AND (SELECT COUNT(*) FROM inventory_ledger l WHERE l.refund_id=f.id AND l.event_type='REFUND_RELEASE')<>1) OR (f.status<>'SUCCEEDED' AND EXISTS(SELECT 1 FROM inventory_ledger l WHERE l.refund_id=f.id)))"),
('channel-success-ceiling',['mock.channel_refunds.txn_id','mock.channel_refunds.amount_cents','mock.channel_payments.amount_cents'],f"SELECT COUNT(*) n FROM {MOCK}.channel_payments p WHERE (SELECT COALESCE(SUM(amount_cents),0) FROM {MOCK}.channel_refunds r WHERE r.txn_id=p.txn_id AND r.status='SUCCEEDED')>p.amount_cents"),
('attempt-number-sequence',['refund_attempts.attempt_no','refund_attempts.refund_id'],"SELECT COUNT(*) n FROM (SELECT refund_id,COUNT(*) count_rows,MAX(attempt_no) max_no,MIN(attempt_no) min_no FROM refund_attempts GROUP BY refund_id HAVING min_no<>1 OR count_rows<>max_no) q"),
('expiry-exact-ten-minutes',['orders.expires_at','orders.created_at'],"SELECT COUNT(*) n FROM orders WHERE TIMESTAMPDIFF(MICROSECOND,created_at,expires_at)<>600000000"),
('queryable-invalid-notifications',['channel_notifications.auth_valid','channel_notifications.process_result','payment_anomalies.first_notification_id'],"SELECT COUNT(*) n FROM channel_notifications n WHERE n.auth_valid=0 AND n.process_result IN('INVALID_SIGNATURE','INVALID_BODY','REPLAYED_SIGNATURE') AND NOT EXISTS(SELECT 1 FROM payment_anomalies a WHERE a.first_notification_id=n.id OR a.dedupe_key=CONCAT(IF(n.process_result='INVALID_BODY','INVALID_BODY','INVALID_SIGNATURE'),':',n.payload_hash))"),
]
results=[]
try:
    with conn.cursor() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');c.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        for name,fields,sql in checks:
            c.execute(sql);n=c.fetchone()['n'];results.append(dict(case=name,fields=fields,expected_violations=0,actual_violations=n,status='PASS' if n==0 else 'FAIL',sql=sql,scope='persistent relationship invariant from isolated field fixture loaded from real prior HTTP regression; not complete adversarial service proof'))
        c.execute('SELECT COUNT(*) orders_n FROM orders');size=c.fetchone()
        if size['orders_n']==0:
            for r in results:r['status']='NOT_RUN';r['reason']='empty fixture cannot prove relationship constraints'
finally:conn.rollback();conn.close()
(OUT/'cross-table-invariants.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),schema=DB,dataset=size,cases=results),ensure_ascii=False,indent=2),encoding='utf-8')
print('cross-table invariants',len(results),'PASS',sum(x['status']=='PASS' for x in results),'FAIL',sum(x['status']=='FAIL' for x in results))
