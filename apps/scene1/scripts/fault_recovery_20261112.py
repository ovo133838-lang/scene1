"""Real process/HTTP/MySQL fault probes, dedicated disposable schemas only.

No production fault hooks: triggers abort transactions and HTTP gates cut responses.
Credentials remain in child environments and never enter the evidence.
"""
import sys, pathlib, os, subprocess, json, threading, time, http.server, http.client, uuid, hashlib, importlib.util, datetime
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/faults')
OUT.mkdir(parents=True,exist_ok=True)
MYSQL='C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe'
RUN_SUFFIX=uuid.uuid4().hex[:8]
SHOP='scene1_fault_20261112_'+RUN_SUFFIX; MOCK='scene1_fault_mock_20261112_'+RUN_SUFFIX
DBPORT=int(os.environ.get('SCENE1_TEST_DB_PORT','3306'))
CFG=dict(x.split('=',1) for x in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if x and not x.startswith('#'))
CFG.update(SCENE1_MYSQL_DSN=f'root:root@tcp(127.0.0.1:{DBPORT})/{SHOP}?parseTime=true&loc=UTC',SCENE1_MOCK_DSN=f'root:root@tcp(127.0.0.1:{DBPORT})/{MOCK}?parseTime=true&loc=UTC',SCENE1_SHOP_URL='http://127.0.0.1:18124',SCENE1_MOCK_URL='http://127.0.0.1:18122')
spec=importlib.util.spec_from_file_location('functional',APP/'scripts/functional.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
f.CFG=CFG; f.BASE='http://127.0.0.1:18120';f.MOCK='http://127.0.0.1:18121'
RESULTS=[];PROCS={};FILES=[]
def sql(query,mock=False):
    env=os.environ.copy();env['MYSQL_PWD']='root'
    r=subprocess.run([MYSQL,'--no-defaults','-u','root','-h','127.0.0.1','-P',str(DBPORT),'--batch','--skip-column-names',MOCK if mock else SHOP,'-e',query],env=env,capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise AssertionError(r.stderr)
    return r.stdout.strip()
def root_sql(query):
    env=os.environ.copy();env['MYSQL_PWD']='root'
    subprocess.run([MYSQL,'--no-defaults','-u','root','-h','127.0.0.1','-P',str(DBPORT),'-e',query],env=env,check=True,capture_output=True)
def start(mode):
    log=open(OUT/(mode+'-process.log'),'ab');FILES.append(log)
    env=os.environ.copy();env.update(CFG);env['SCENE1_PORT']='18120' if mode=='shop' else '18121'
    p=subprocess.Popen([str(APP/'bin/scene1-fault.exe'),'-mode',mode,'-env',str(APP/'.env.test.local')],cwd=APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));PROCS[mode]=p
    f.poll(lambda:health(mode),lambda x:x,20)
def health(mode):
    try:return f.request('/health/live',mock=mode=='mock')['status']=='UP'
    except Exception:return False
def kill(mode):
    p=PROCS.pop(mode,None)
    if p:p.kill();p.wait(10)
class Gate:
    def __init__(self,port,target):
        self.target=target;self.mode='OPEN';self.hit=threading.Event();self.release=threading.Event();self.release.set();self.captured={}
        gate=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_GET(self):self.forward()
            def do_POST(self):self.forward()
            def forward(self):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')));mode=gate.mode
                if mode=='BLOCK_CALLBACK' and '/notifications' in self.path:
                    self.send_response(503);self.end_headers();self.wfile.write(b'{}');return
                if self.command=='POST' and self.path=='/mock/v1/payments' and mode in ('BEFORE','AFTER'):
                    gate.captured=json.loads(body)
                    if mode=='BEFORE':gate.hit.set();gate.release.wait(25);return
                conn=http.client.HTTPConnection('127.0.0.1',gate.target,timeout=15)
                try:
                    conn.request(self.command,self.path,body,dict(self.headers));res=conn.getresponse();data=res.read()
                    if self.command=='POST' and self.path=='/mock/v1/payments' and mode=='AFTER':gate.hit.set();gate.release.wait(25);return
                    if mode=='DROP_ORDER' and self.path=='/api/v1/buyer/orders' and self.command=='POST':
                        gate.captured=json.loads(data);gate.hit.set();return
                    self.send_response(res.status)
                    for k,v in res.getheaders():
                        if k.lower() not in ('connection','transfer-encoding','content-length'):self.send_header(k,v)
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                except (OSError,TimeoutError):pass
                finally:conn.close()
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def arm(self,mode):self.mode=mode;self.hit.clear();self.captured={};self.release.clear()
    def open(self):self.mode='OPEN';self.release.set()
def record(name,fn):
    before=time.monotonic();r={'case':name,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:r['evidence']=fn();r['status']='PASS'
    except Exception as e:r['status']='FAIL';r['error']=str(e)
    r['elapsed_seconds']=round(time.monotonic()-before,3);RESULTS.append(r);save();print(r['status'],name,flush=True)
def save():
    (OUT/'results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'http-events.json').write_text(json.dumps(f.EVENTS,ensure_ascii=False,indent=2),encoding='utf-8')
def paid_once(o):
    done=f.poll(lambda:f.order(o),lambda x:x['status']=='PENDING_SHIPMENT',40)
    n=sql(f"SELECT COUNT(*) FROM receipts WHERE order_id='{o['id']}'")
    count=sql(f"SELECT COUNT(*) FROM channel_payments WHERE order_ref='{o['id']}'",True)
    assert n=='1' and count=='1',(n,count)
    return {'order_id':o['id'],'state':done['status'],'shop_receipts':n,'channel_payments':count}
def rollback():
    p=f.stock(40);before=sql('SELECT (SELECT COUNT(*) FROM orders),(SELECT COUNT(*) FROM inventory_ledger),(SELECT COUNT(*) FROM idempotency_records)')
    root_sql(f"CREATE TRIGGER {SHOP}.fault_ledger BEFORE INSERT ON {SHOP}.inventory_ledger FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='INJECTED_LEDGER_FAILURE'")
    try:f.request('/api/v1/buyer/orders','POST',{'product_id':p['id'],'quantity':1},role='buyer1',expect=503)
    finally:root_sql(f'DROP TRIGGER {SHOP}.fault_ledger')
    after=sql('SELECT (SELECT COUNT(*) FROM orders),(SELECT COUNT(*) FROM inventory_ledger),(SELECT COUNT(*) FROM idempotency_records)')
    assert before==after and f.product()['available_quantity']==40,(before,after)
    return {'before':before,'after':after,'available':40,'abort':'inventory_ledger BEFORE INSERT SQLSTATE 45000'}
def response_loss():
    f.stock(40);k=f.key();proxy.arm('DROP_ORDER');old=f.BASE;f.BASE='http://127.0.0.1:18123'
    try:
        try:f.create(idem=k);raise AssertionError('response should be cut')
        except (http.client.RemoteDisconnected,OSError):pass
    finally:f.BASE=old;proxy.open()
    assert proxy.hit.is_set();committed=proxy.captured['data'];again=f.create(idem=k)
    assert committed['id']==again['id'] and f.product()['available_quantity']==39
    return {'request_key':k,'committed_order_id':committed['id'],'retry_order_id':again['id'],'available':39}
def crash(phase):
    f.stock(40);o=f.create();callbacks.arm('BLOCK_CALLBACK');channel.arm(phase)
    f.request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202)
    assert channel.hit.wait(10),'worker did not reach gate'
    job=sql(f"SELECT status,attempt_count,lease_until FROM outbox_jobs WHERE aggregate_id=(SELECT id FROM payment_intents WHERE order_id='{o['id']}')")
    assert job.startswith('RUNNING\t'),job
    count=sql(f"SELECT COUNT(*) FROM channel_payments WHERE order_ref='{o['id']}'",True)
    assert count==('0' if phase=='BEFORE' else '1'),count
    kill('shop');channel.open();start('shop');r=paid_once(o);callbacks.open()
    r.update(crash_phase=phase,job_before_kill=job,channel_count_before_kill=count,available=f.product()['available_quantity'])
    assert r['available']==39
    return r
def settlement_db_failure():
    f.stock(40);o=f.create();callbacks.arm('BLOCK_CALLBACK')
    root_sql(f"CREATE TRIGGER {SHOP}.fault_receipt BEFORE INSERT ON {SHOP}.receipts FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='INJECTED_RECEIPT_FAILURE'")
    try:
        f.request('/api/v1/buyer/orders/'+o['id']+'/payments','POST',{},role='buyer1',expect=202)
        f.poll(lambda:sql(f"SELECT COUNT(*) FROM channel_payments WHERE order_ref='{o['id']}'",True),lambda x:x=='1')
        time.sleep(.5)
        assert sql(f"SELECT COUNT(*) FROM receipts WHERE order_id='{o['id']}'")=='0'
        assert f.order(o)['status']=='PENDING_PAYMENT'
    finally:root_sql(f'DROP TRIGGER {SHOP}.fault_receipt')
    r=paid_once(o);callbacks.open();return dict(r,failed_local_receipts=0,external_committed=1)
def main():
    root_sql(f'CREATE DATABASE IF NOT EXISTS {SHOP}; CREATE DATABASE IF NOT EXISTS {MOCK};')
    build=subprocess.run(['go','build','-o','bin/scene1-fault.exe','./cmd/scene1'],cwd=APP,capture_output=True,text=True)
    (OUT/'build.log').write_text(build.stdout+build.stderr,encoding='utf-8');assert build.returncode==0
    global channel,callbacks,proxy
    channel=Gate(18122,18121);callbacks=Gate(18124,18120);proxy=Gate(18123,18120)
    try:
        start('mock');start('shop');f.login()
        for n in (1,2):
            record(f'round{n}:transaction rollback',rollback)
            record(f'round{n}:committed HTTP response lost same-key retry',response_loss)
            record(f'round{n}:worker crash before external call',lambda:crash('BEFORE'))
            record(f'round{n}:worker crash after external commit',lambda:crash('AFTER'))
            record(f'round{n}:external commit local settlement DB failure',settlement_db_failure)
        summary=f.request('/api/v1/operator/summary',role='operator')
        for p in summary['inventory']:assert p['initial_quantity']+p['adjustment_net']==p['available_quantity']+p['reserved_quantity']+p['shipped_quantity']
        assert int(summary['total_received_cents'])-int(summary['refunded_cents'])==int(summary['net_cents'])
        (OUT/'final-conservation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        channel.open();callbacks.open();proxy.open()
        for mode in list(PROCS):kill(mode)
        for gate in (channel,callbacks,proxy):gate.server.shutdown()
        for file in FILES:file.close()
        save()
    return 0 if all(x['status']=='PASS' for x in RESULTS) else 1
if __name__=='__main__':sys.exit(main())
