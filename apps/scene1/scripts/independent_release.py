"""Independent release-candidate tests after AC005; test-only schemas, no production edits."""
import csv,datetime,hashlib,importlib.util,json,os,pathlib,re,subprocess,urllib.parse
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=APP/'evidence/independent-testing-release';OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('final_driver',APP/'scripts/independent_final.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
i=d.i;f=d.f;d.OUT=OUT;i.OUT=OUT;i.EXE=APP/'bin/scene1-independent-release.exe'

def sql(query):
    result=i.db_sql('SCENE1_MYSQL_DSN',query)
    assert result.returncode==0,result.stderr
    return result.stdout

def pagination_probe(round_no):
    probes=[]
    for table,route in [('products','/api/v1/operator/products'),('receipts','/api/v1/operator/receipts')]:
        raw=sql(f"SELECT id,DATE_FORMAT(created_at,'%Y-%m-%d %H:%i:%s.%f') FROM {table} ORDER BY id LIMIT 2;")
        fixtures=[line.split('\t') for line in raw.splitlines()]
        assert len(fixtures)==2 and fixtures[0][0]<fixtures[1][0],('need two isolated fixtures',table)
        smaller,larger=fixtures[0][0],fixtures[1][0]
        for ident,stamp in fixtures:
            assert re.fullmatch(r'[a-f0-9-]{36}',ident) and re.fullmatch(r'[\d :.-]+',stamp)
        try:
            # Deliberately contradict UUID descending; only test-schema fixture timestamps change.
            sql(f"UPDATE {table} SET created_at=CASE id WHEN '{smaller}' THEN '2099-01-02 00:00:00.000000' ELSE '2099-01-01 00:00:00.000000' END WHERE id IN ('{smaller}','{larger}');")
            first=f.request(route+'?limit=1',role='operator')
            assert len(first['items'])==1 and first['items'][0]['id']==smaller,(table,'first page',first)
            assert first['next_cursor']
            second=f.request(route+'?limit=1&cursor='+urllib.parse.quote(first['next_cursor']),role='operator')
            assert len(second['items'])==1 and second['items'][0]['id']==larger,(table,'second page',second)
            assert all('created_at' not in item and '_sort_time' not in item for page in [first,second] for item in page['items'])
            # Stable traversal of the two fixtures, no duplicates, no secret/internal fields.
            probes.append({'table':table,'first':smaller,'second':larger,'sort':'stored created_at descending overrides ID descending','internal_fields_leaked':False,'passed':True})
        finally:
            for ident,stamp in fixtures:sql(f"UPDATE {table} SET created_at='{stamp}' WHERE id='{ident}';")
        restored=sql(f"SELECT id,DATE_FORMAT(created_at,'%Y-%m-%d %H:%i:%s.%f') FROM {table} WHERE id IN ('{smaller}','{larger}') ORDER BY id;")
        assert restored==raw,('fixture timestamps were not restored',table)
    f.EVENTS.append({'case':'AC005 stored-time pagination round '+str(round_no),'passed':True,'probes':probes})
    print('PASS AC005 round',round_no,': product and receipt real DB/HTTP ordering, next cursor, whitelist and fixture restore',flush=True)

def run(args,name,env=None):
    p=subprocess.run(args,cwd=APP,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
    (OUT/name).write_text(p.stdout,encoding='utf-8');assert p.returncode==0,(name,p.stdout)
    print('PASS '+name,flush=True);return p.stdout

def quality():
    assert not run(['gofmt','-l','cmd','internal','web/embed.go'],'gofmt.txt').strip()
    run(['go','vet','./...'],'vet.txt')
    run(['go','test','-count=2','-covermode=atomic','-coverpkg=./...','-coverprofile=evidence/independent-testing-release/unit-coverage.out','./...'],'unit.txt')
    run(['go','tool','cover','-func=evidence/independent-testing-release/unit-coverage.out'],'unit-functions.txt')
    run(['go','tool','cover','-html=evidence/independent-testing-release/unit-coverage.out','-o','evidence/independent-testing-release/unit-coverage.html'],'cover-html.txt')
    blocks={}
    for line in (OUT/'unit-coverage.out').read_text().splitlines()[1:]:
        loc,n,h=line.split();old=blocks.get(loc,(int(n),0));assert old[0]==int(n);blocks[loc]=(int(n),old[1]+int(h))
    counts={}
    for loc,(n,h) in blocks.items():
        pkg=loc.rsplit('/',1)[0];a,t=counts.get(pkg,(0,0));counts[pkg]=(a+(n if h else 0),t+n)
    overall=sum(a for a,t in counts.values())/sum(t for a,t in counts.values())*100
    packages={k:a/t*100 for k,(a,t) in counts.items()}
    assert overall>=85 and all(v>=85 for k,v in packages.items() if '/internal/' in k and not k.endswith('/testsupport'))
    result={'overall':overall,'packages':packages,'passed':True,'production_exclusions':[],'statements':sum(t for a,t in counts.values()),'count':2,'coverpkg':'./...'}
    (OUT/'unit-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    env=os.environ.copy();env['CC']='C:/Users/30343/Documents/Codex/2026-11-11/di-yi/work/compiler/w64devkit/bin/gcc.exe';env['CGO_ENABLED']='1';env['PATH']=str(pathlib.Path(env['CC']).parent)+os.pathsep+env['PATH']
    run(['go','test','-race','-count=2','./...'],'race.txt',env)
    run(['go','test','./internal/service','-run','TestIndependent|TestListSortDoesNotDependOnDTOTimeWhitelist','-count=2','-v'],'targeted-current.txt')

if __name__=='__main__':
    i.snapshot('version-start.json');passed=False
    run(['go','build','-o',str(i.EXE),'./cmd/scene1'],'build.txt')
    (OUT/'binary-sha256.txt').write_text(hashlib.sha256(i.EXE.read_bytes()).hexdigest()+'\n')
    try:
        f.start()
        for n in [1,2]:
            f.run_round(n);d.supplement(n);d.ac_probes(n);pagination_probe(n)
        before=f.request('/api/v1/operator/summary',role='operator');f.stop();f.start();f.login();after=f.request('/api/v1/operator/summary',role='operator')
        assert before['total_received_cents']==after['total_received_cents'] and before['refunded_cents']==after['refunded_cents']
        print('PASS release restart persistence',flush=True)
        i.db_probes();passed=True
    finally:
        f.stop();i.snapshot('version-end.json')
        (OUT/'http-regression.json').write_text(json.dumps({'passed':passed,'rounds':2,'events':f.EVENTS,'login':'six real accounts called each round; credentials/results excluded'},ensure_ascii=False,indent=2),encoding='utf-8')
    quality()
