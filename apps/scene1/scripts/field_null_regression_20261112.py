"""Repeat the exact database NULL-review counterexample on migrated isolated schema."""
import importlib.util,pathlib,json,datetime
path=pathlib.Path(__file__).with_name('field_matrix_20261112.py')
spec=importlib.util.spec_from_file_location('field_matrix',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
schema=json.loads((m.OUT/'summary.json').read_text(encoding='utf-8'))['schemas'][0]
assert schema.startswith('scene1_field_20261112_')
conn=m.pymysql.connect(**dict(m.ROOT,database=schema))
record=[]
try:
    m.execute(conn,'SET autocommit=0')
    for status in ['PENDING','APPROVED','REJECTED']:
        row=m.rows(conn,'SELECT * FROM refund_applications WHERE status=%s LIMIT 1',[status])
        if not row:
            record.append(dict(status=status,result='NOT_RUN',reason='no matching fixture'));continue
        row=row[0]
        for field in ['reviewer_id','review_reason','reviewed_at']:
            m.execute(conn,'SAVEPOINT regression')
            error=None
            try:m.execute(conn,f'UPDATE refund_applications SET `{field}`=NULL WHERE id=%s',[row['id']])
            except m.pymysql.MySQLError as exc:error=exc.args[0]
            m.execute(conn,'ROLLBACK TO SAVEPOINT regression')
            passed=(error is None) if status=='PENDING' else error==3819
            record.append(dict(order_status=status,field=field,expected='accept' if status=='PENDING' else 'reject3819',actual_error=error,status='PASS' if passed else 'FAIL'))
    (m.OUT/'review-null-repeated.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),schema=schema,cases=record),ensure_ascii=False,indent=2),encoding='utf-8')
    print('NULL review regression',len(record),'cases',all(x.get('status')=='PASS' for x in record))
finally:conn.rollback();conn.close();m.ADMIN.close()
