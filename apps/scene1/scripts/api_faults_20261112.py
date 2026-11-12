"""Independent storage-fault/DTO supplement using real running binary, dedicated schemas only."""
import importlib.util,json,pathlib,time,hashlib
APP=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('matrix',APP/'scripts/api_matrix_20261112.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=m.OUT/'faults';OUT.mkdir(exist_ok=True);m.OUT=OUT
def faults():
    for rt in m.routes:
        p,b,kw=m.prototype(rt)
        if rt['op'] in ['live','mock_live','ready']:continue
        if rt['mock']:
            table='runtime_lock' if rt['method']!='GET' else ('channel_refunds' if rt['op']=='refund_query' else 'channel_payments')
        elif rt['op'] in ['me','logout']:table='sessions'
        elif rt['write'] or rt['op'] in ['login','advance','clock'] or rt['role']=='HMAC':table='demo_clock'
        elif rt['op'] in ['order','reconciliation','orders','warehouse']:table='orders'
        elif rt['op'] in ['anomaly','payment_anomalies']:table='payment_anomalies'
        else:table={'summary':'products','products':'products','receipts':'receipts','refunds':'refunds','refund_applications':'refund_applications','channel_notifications':'channel_notifications'}[rt['op']]
        ident='matrix_offline_'+table
        before=m.snapshot()
        m.sql('RENAME TABLE `'+table+'` TO `'+ident+'`;',rt['mock'])
        try:m.case(('mock ' if rt['mock'] else 'shop ')+rt['method']+' '+rt['path']+' storage-unavailable',lambda:m.send(p,rt['method'],b,expect=503,dimension='real-db-table-unavailable:'+table,**kw))
        finally:m.sql('RENAME TABLE `'+ident+'` TO `'+table+'`;',rt['mock'])
        after=m.snapshot();assert before==after,('storage fault changed business state',rt)
        m.EVENTS[-1]['db_before']=before;m.EVENTS[-1]['db_after']=after
        # Calls with a health endpoint are deliberately independent of business transaction tables.
    m.case('live is process health',lambda:m.send('/health/live',dimension='health'))
    m.case('mock live is process health',lambda:m.send('/health/live',mock=True,dimension='health'))
    m.case('ready healthy after restoration',lambda:m.send('/health/ready',dimension='health'))
if __name__=='__main__':
    (OUT/'version-start.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
    try:
        m.start();m.f.login()
        for n in [1,2]:m.case('fault round '+str(n),faults)
    finally:
        m.stop();m.write_results();(OUT/'version-end.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8');print(json.dumps({'events':len(m.EVENTS),'failures':m.FAILURES}),flush=True)
