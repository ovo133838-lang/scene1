import json, pathlib, subprocess, os
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=APP/'evidence/independent-testing'
def run(args,name,env=None):
    p=subprocess.run(args,cwd=APP,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,encoding='utf-8',errors='replace')
    (OUT/name).write_text(p.stdout,encoding='utf-8');print(name,p.returncode,flush=True)
    assert p.returncode==0,(name,p.stdout)
    return p.stdout
start=json.loads((OUT/'version-start.json').read_text(encoding='utf-8'));end=json.loads((OUT/'version-end.json').read_text(encoding='utf-8'))
changed=[k for k,v in start['files'].items() if end['files'].get(k)!=v]
print('changed during HTTP:',changed)
run(['go','vet','./...'],'vet.txt')
assert not run(['gofmt','-l','cmd','internal','web/embed.go'],'gofmt.txt').strip()
run(['go','test','-count=1','-covermode=atomic','-coverpkg=./...','-coverprofile=evidence/independent-testing/unit-coverage.out','./...'],'unit.txt')
run(['go','tool','cover','-func=evidence/independent-testing/unit-coverage.out'],'unit-functions.txt')
run(['go','tool','cover','-html=evidence/independent-testing/unit-coverage.out','-o','evidence/independent-testing/unit-coverage.html'],'cover-html.txt')
counts={};blocks={}
for line in (OUT/'unit-coverage.out').read_text().splitlines()[1:]:
    loc,n,h=line.split();old=blocks.get(loc,(int(n),0));assert old[0]==int(n);blocks[loc]=(int(n),old[1]+int(h))
for loc,(n,h) in blocks.items():
    pkg=loc.rsplit('/',1)[0];a,t=counts.get(pkg,(0,0));counts[pkg]=(a+(n if h>0 else 0),t+n)
overall=sum(a for a,t in counts.values())/sum(t for a,t in counts.values())*100
packages={k:a/t*100 for k,(a,t) in counts.items()}
assert overall>=85 and all(v>=85 for k,v in packages.items() if '/internal/' in k and not k.endswith('/testsupport'))
(OUT/'unit-summary.json').write_text(json.dumps({'overall':overall,'packages':packages,'passed':True,'production_exclusions':[]},indent=2),encoding='utf-8')
env=os.environ.copy();env['CC']='C:/Users/30343/Documents/Codex/2026-11-11/di-yi/work/compiler/w64devkit/bin/gcc.exe';env['CGO_ENABLED']='1';env['PATH']=str(pathlib.Path(env['CC']).parent)+os.pathsep+env['PATH']
run(['go','test','-race','-count=1','./...'],'race.txt',env)
print('PASS independent quality',overall,flush=True)
