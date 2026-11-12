"""Two repeated strict DEFAULT/precision checks on prior dedicated field schemas."""
import pathlib,importlib.util,json,datetime,decimal
spec=importlib.util.spec_from_file_location('field_matrix',pathlib.Path(__file__).with_name('field_matrix_20261112.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
meta=json.loads((m.OUT/'schema-metadata.json').read_text(encoding='utf-8'))
summary=json.loads((m.OUT/'summary.json').read_text(encoding='utf-8'));records=[]
def convert(v,typ):
    if v is None:return None
    if typ in ['tinyint','smallint','int','bigint']:return int(v)
    return v
for schema,tables in meta.items():
    assert schema.startswith('scene1_field_')
    conn=m.pymysql.connect(**dict(m.ROOT,database=schema));m.META[schema]=tables
    try:
        m.execute(conn,'SET autocommit=0')
        account=m.rows(conn,'SELECT id FROM accounts LIMIT 1')[0]['id'] if 'accounts' in tables else None
        for round_no in [1,2]:
            for table,tm in tables.items():
                available=m.rows(conn,f'SELECT * FROM `{table}` LIMIT 1')
                if not available:continue
                witness=available[0]
                for col in tm['columns']:
                    name=col['COLUMN_NAME'];default=convert(col['COLUMN_DEFAULT'],col['DATA_TYPE'])
                    if col['GENERATION_EXPRESSION']:continue
                    for category,value in [('default',default)]+([('utc-microsecond-precision',datetime.datetime(2026,11,12,0,1,2,123456))] if col['DATA_TYPE']=='datetime' else []):
                        if category=='default' and default is None and col['IS_NULLABLE']=='NO':continue
                        before=m.snapshot(conn);m.execute(conn,'SAVEPOINT extra')
                        changes={name:value};expected='accept';error=None;matches=None
                        if category=='default':
                            changes.update(m.companions(table,name,value,witness,account) if name in ['status','event_type'] and value is not None else {})
                            if table=='products' and name in ['reserved_quantity','shipped_quantity','adjustment_net']:
                                values={k:witness[k] for k in ['initial_quantity','available_quantity','reserved_quantity','shipped_quantity','adjustment_net']};values[name]=value
                                if name=='adjustment_net':changes.update(initial_quantity=10,available_quantity=10,reserved_quantity=0,shipped_quantity=0)
                                else:changes['adjustment_net']=values['available_quantity']+values['reserved_quantity']+values['shipped_quantity']-values['initial_quantity']
                            if value is None and ((table=='orders' and name in ['closed_at','close_reason'] and witness['status']=='CLOSED') or(table=='refunds' and name=='settled_at' and witness['status']=='SUCCEEDED') or(table=='refund_applications' and name in ['reviewer_id','review_reason','reviewed_at'] and witness['status']!='PENDING')):expected='reject'
                        query=f'UPDATE `{table}` SET '+','.join(f'`{k}`='+('DEFAULT' if k==name and category=='default' else '%s') for k in changes)+' WHERE '+' AND '.join(f'`{k}`=%s' for k in tm['pk'])
                        args=[v for k,v in changes.items() if not(k==name and category=='default')]+[witness[k] for k in tm['pk']]
                        try:
                            m.execute(conn,query,args)
                            found=m.rows(conn,f'SELECT `{name}` value FROM `{table}` WHERE '+' AND '.join(f'`{k}`=%s' for k in tm['pk']),[witness[k] for k in tm['pk']])
                            matches=len(found)==1 and found[0]['value']==value
                        except m.pymysql.MySQLError as exc:error=exc.args[0]
                        # Optional timestamp with same-row required/review CHECK must reject NULL;
                        # non-NULL precision values require compatible review/status companions.
                        if category=='utc-microsecond-precision' and error==3819 and ((table=='orders' and name=='closed_at' and witness['status']!='CLOSED') or(table=='refunds' and name=='settled_at' and witness['status']!='SUCCEEDED') or(table=='refund_applications' and name=='reviewed_at' and witness['status']=='PENDING')):expected='reject'
                        m.execute(conn,'ROLLBACK TO SAVEPOINT extra');after=m.snapshot(conn)
                        passed=before==after and ((error==3819) if expected=='reject' else error is None and matches)
                        records.append(dict(round=round_no,scope=tm['scope'],table=table,field=name,category=category,expected=expected,actual_error=error,persisted_value_matches=matches,rollback_equal=before==after,status='PASS' if passed else 'FAIL'))
        conn.rollback()
    finally:conn.close()
m.ADMIN.close()
(m.OUT/'strict-extra.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=records),ensure_ascii=False,indent=2),encoding='utf-8')
print('strict extra',len(records),'PASS',sum(r['status']=='PASS' for r in records),'FAIL',sum(r['status']=='FAIL' for r in records))
for row in records:
    if row['status']=='FAIL':print(row)
