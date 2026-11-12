"""Prepare a fresh browser-acceptance environment; no shared DB deletes."""
import pathlib,subprocess,os,json,uuid,time,urllib.request,socket
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/browser')
OUT.mkdir(parents=True,exist_ok=True)
MYSQL='C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe'
for port in (18090,18091):
    with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0,('acceptance port occupied',port)
suffix=uuid.uuid4().hex[:8];shop='scene1_browser_20261112_'+suffix;mock='scene1_browser_mock_20261112_'+suffix
env=os.environ.copy();env['MYSQL_PWD']='root'
p=subprocess.run([MYSQL,'--no-defaults','-h','127.0.0.1','-P','3306','-u','root','-e',f'CREATE DATABASE {shop}; CREATE DATABASE {mock};'],env=env,capture_output=True);assert p.returncode==0,'isolated browser schema creation failed'
cfg=dict(x.split('=',1) for x in (APP/'.env.test.local').read_text(encoding='utf-8').splitlines() if x and not x.startswith('#'))
cfg.update(SCENE1_MYSQL_DSN=f'root:root@tcp(127.0.0.1:3306)/{shop}?parseTime=true&loc=UTC',SCENE1_MOCK_DSN=f'root:root@tcp(127.0.0.1:3306)/{mock}?parseTime=true&loc=UTC',SCENE1_SHOP_URL='http://127.0.0.1:18090',SCENE1_MOCK_URL='http://127.0.0.1:18091')
cfgpath=APP/'.env.browser.local';cfgpath.write_text(''.join(k+'='+v+'\n' for k,v in cfg.items()),encoding='utf-8')
binary=APP/'bin/scene1-browser.exe'
p=subprocess.run(['go','build','-o',str(binary),'./cmd/scene1'],cwd=APP,capture_output=True);assert p.returncode==0,'browser candidate build failed'
procs=[]
for mode,port in [('mock',18091),('shop',18090)]:
    child=os.environ.copy();child['SCENE1_PORT']=str(port);log=open(OUT/(mode+'-process.log'),'ab')
    p=subprocess.Popen([str(binary),'-mode',mode,'-env',str(cfgpath)],cwd=APP,env=child,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));procs.append({'mode':mode,'pid':p.pid,'port':port})
for _ in range(100):
    try:
        with urllib.request.urlopen('http://127.0.0.1:18090/health/ready') as res:assert res.status==200
        break
    except OSError:time.sleep(.1)
else:raise SystemExit('browser environment not ready')
(OUT/'environment.json').write_text(json.dumps({'shop':'http://127.0.0.1:18090','mock':'http://127.0.0.1:18091','shop_schema':shop,'mock_schema':mock,'db_port':3306,'processes':procs,'credential_file':'apps/scene1/.env.browser.local (ignored; not delivered)'},indent=2),encoding='utf-8')
print('Independent acceptance environment ready, fresh schemas, shop18090/mock18091. Credentials not printed.')
