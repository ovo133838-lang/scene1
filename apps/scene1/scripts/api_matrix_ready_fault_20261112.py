"""Isolated shop DB TCP gate proves readiness DOWN without stopping user's MySQL."""
import importlib.util,pathlib,json,sys,socket,threading,select,os,subprocess,time
P=pathlib.Path(__file__).resolve().with_name('api_matrix_20261112.py');sp=importlib.util.spec_from_file_location('matrix',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
m.OUT=m.OUT/'ready-fault';m.OUT.mkdir(exist_ok=True);m.BASE='http://127.0.0.1:18112'
blocked=False;sockets=[];lock=threading.Lock();server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',18113));server.listen()
def relay(client):
    if blocked:client.close();return
    target=socket.create_connection(('127.0.0.1',int(m.DBPORT)))
    with lock:sockets.extend([client,target])
    try:
        while not blocked:
            ready,_,_=select.select([client,target],[],[],.2)
            for source in ready:
                data=source.recv(65536)
                if not data:return
                (target if source is client else client).sendall(data)
    except OSError:pass
    finally:client.close();target.close()
def accept():
    while True:
        try:c,_=server.accept()
        except OSError:return
        threading.Thread(target=relay,args=(c,),daemon=True).start()
threading.Thread(target=accept,daemon=True).start()
proc=None
try:
    m.init();env=os.environ.copy();env.update(m.CFG);env.update(SCENE1_MYSQL_DSN=f'root:{m.DBPASS}@tcp(127.0.0.1:18113)/'+m.SHOPDB+'?parseTime=true&loc=UTC',SCENE1_PORT='18112',SCENE1_SHOP_URL=m.BASE,SCENE1_MOCK_URL=m.MOCK)
    log=open(m.OUT/'shop.log','ab');proc=subprocess.Popen([str(m.EXE),'-mode','shop','-env','nonexistent-ready.env'],cwd=m.APP,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(100):
        try:m.send('/health/ready');break
        except OSError:time.sleep(.1)
    blocked=True
    with lock:
        for conn in sockets:
            try:conn.shutdown(socket.SHUT_RDWR);conn.close()
            except OSError:pass
    m.case('readiness-DB-unavailable-503',lambda:m.send('/health/ready',expect=503,dimension='storage-unavailable'))
    m.case('liveness-remains-UP-with-DB-unavailable',lambda:m.send('/health/live'))
finally:
    if proc:proc.terminate();proc.wait(10)
    server.close();m.write_results();(m.OUT/'version-end.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
sys.exit(bool(m.FAILURES))
