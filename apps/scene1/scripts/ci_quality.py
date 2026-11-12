"""Portable, fail-closed quality gate for every scene1 production Go package."""
import pathlib,subprocess,json,os,sys
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path(os.environ.get('SCENE1_QUALITY_OUT',str(APP/'evidence/ci-quality'))).resolve();OUT.mkdir(parents=True,exist_ok=True)
def run(args,name,env=None):
    p=subprocess.run(args,cwd=APP,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/name).write_text(p.stdout+p.stderr,encoding='utf-8')
    print(name,p.returncode,flush=True)
    if p.returncode:raise SystemExit(p.returncode)
    return p.stdout
files=[str(x.relative_to(APP)) for x in APP.rglob('*.go') if 'bin' not in x.parts]
assert not run(['gofmt','-l',*files],'gofmt.log').strip(),'gofmt required'
run(['go','vet','./...'],'vet.log')
profile=OUT/'unit-coverage.out'
run(['go','test','-count=2','-covermode=atomic','-coverpkg=./...','-coverprofile='+str(profile),'./...'],'unit.log')
run(['go','tool','cover','-func='+str(profile)],'unit-functions.log')
run(['go','tool','cover','-html='+str(profile),'-o',str(OUT/'unit-coverage.html')],'unit-html.log')
blocks={}
for line in profile.read_text(encoding='utf-8').splitlines()[1:]:
    loc,n,hits=line.split();n=int(n);old=blocks.get(loc,(n,0));assert old[0]==n
    blocks[loc]=(n,old[1]+int(hits))
counts={}
for loc,(n,hits) in blocks.items():
    pkg=loc.rsplit('/',1)[0];a,t=counts.get(pkg,(0,0));counts[pkg]=(a+(n if hits else 0),t+n)
# go list's line format avoids parsing a concatenated stream of JSON objects.
production=run(['go','list','-f','{{if .GoFiles}}{{.ImportPath}}{{end}}','./...'],'production-packages.log').split()
missing=[p for p in production if p not in counts and not p.endswith('/web')]
# web/embed.go contains only an embed declaration, no executable statements.
assert not missing,('production packages missing from coverage',missing)
overall=sum(a for a,t in counts.values())/sum(t for a,t in counts.values())*100
percent={p:a/t*100 for p,(a,t) in counts.items()}
core={p:v for p,v in percent.items() if '/internal/' in p and not p.endswith('/testsupport')}
result={'overall':overall,'packages':percent,'core_packages':core,'production_exclusions':[],'declaration_only':['web/embed.go'],'passed':overall>=85 and all(v>=85 for v in core.values())}
(OUT/'unit-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8');assert result['passed'],result
env=os.environ.copy()
if env.get('SCENE1_CC'):
    env.update(CC=env['SCENE1_CC'],CGO_ENABLED='1');env['PATH']=str(pathlib.Path(env['CC']).parent)+os.pathsep+env['PATH']
run(['go','test','-race','-count=2','./...'],'race.log',env)
binary=APP/'bin'/('scene1-ci.exe' if os.name=='nt' else 'scene1-ci');binary.parent.mkdir(exist_ok=True)
run(['go','build','-trimpath','-o',str(binary),'./cmd/scene1'],'build.log')
print('PASS quality',overall)
