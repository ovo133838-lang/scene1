"""Run real checks; fail closed. Unit coverage includes all application production packages."""
import subprocess,pathlib,sys,json,os
root=pathlib.Path(__file__).resolve().parents[1];out=root/'evidence';out.mkdir(exist_ok=True)
def run(args,name,env=None):
    p=subprocess.run(args,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace');(out/name).write_text(p.stdout,encoding='utf-8');print(p.stdout,end='');return p.returncode
fmt=subprocess.check_output(['gofmt','-l','cmd','internal','web/embed.go'],cwd=root,text=True)
(out/'gofmt.txt').write_text(fmt,encoding='utf-8')
if fmt:raise SystemExit('gofmt failed')
if run(['go','vet','./...'],'vet.txt'):raise SystemExit(1)
if run(['go','test','./...','-count=1','-coverprofile=evidence/unit-coverage.out'],'unit.txt'):raise SystemExit(1)
if run(['go','tool','cover','-func=evidence/unit-coverage.out'],'unit-functions.txt'):raise SystemExit(1)
counts={}
for line in (out/'unit-coverage.out').read_text(encoding='utf-8').splitlines()[1:]:
    loc,statements,hits=line.split();pkg=loc.rsplit('/',1)[0];covered,total=counts.get(pkg,(0,0));n=int(statements);counts[pkg]=(covered+(n if int(hits)>0 else 0),total+n)
total=sum(v[1] for v in counts.values());covered=sum(v[0] for v in counts.values());result={'overall_including_test_double':covered/total*100,'packages':{k:(a/b*100 if b else 100) for k,(a,b) in counts.items()},'core_minimum':85,'source':'unit-coverage.out','excluded_production_files':[]}
core=[k for k in counts if '/internal/' in k and not k.endswith('/testsupport')]
result['passed']=result['overall_including_test_double']>=85 and all(result['packages'][k]>=85 for k in core)
(out/'unit-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('UNIT COVERAGE GATE:',result['passed'],round(result['overall_including_test_double'],2))
if not result['passed']:raise SystemExit(1)
env=os.environ.copy();compiler=env.get('SCENE1_CC')
if compiler:env['CC']=compiler;env['CGO_ENABLED']='1';env['PATH']=str(pathlib.Path(compiler).parent)+os.pathsep+env.get('PATH','')
if run(['go','test','-race','./...','-count=1'],'race.txt',env):raise SystemExit(1)
if run(['go','build','-o','bin/scene1.exe','./cmd/scene1'],'build.txt'):raise SystemExit(1)
print('Quality gates passed; deployment still requires independent acceptance and compliant main release.')
