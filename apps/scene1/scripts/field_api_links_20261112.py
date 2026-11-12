"""Link declaration-field validation to actual independent HTTP raw events, fail closed."""
import pathlib,json,re,csv,hashlib
ROOT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12');OUT=ROOT/'fields';APP=pathlib.Path('D:/Desktop/go-zero-master/apps/scene1')
items=json.loads((OUT/'http-field-results.json').read_text(encoding='utf-8'))
events=json.loads((ROOT/'apis/events.json').read_text(encoding='utf-8'))
tested=json.loads((ROOT/'apis/version-end.json').read_text(encoding='utf-8'))
ours=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
normals=json.loads((OUT/'normal-input-results.json').read_text(encoding='utf-8')) if (OUT/'normal-input-results.json').exists() else []
assert all(tested['files'].get(k.replace('\\','/'))==v for k,v in ours['code_files_sha256'].items()),'API evidence does not match field-tested production version'
routes=[]
source=(APP/'internal/httpapi/api.go').read_text(encoding='utf-8')
for m in re.finditer(r'\{"(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", "(.*?)", (true|false)\}',source):
    method,path,role,op,required,optional,query,write=m.groups();routes.append((method,path,re.sub(r'\{[^}]+\}',r'[^/]+',path)))
links=[]
for row in items:
    if row['round']!=1 or row['status']!='NOT_RUN':continue
    method,actual=row['route'].split(' ',1);route=next(path for verb,path,pattern in routes if verb==method and re.fullmatch(pattern,actual));field=row['field']
    selected=[e for e in events if e['method']==method and e['route']==route and e['mock']==(row['scope']=='mock') and e['passed']]
    negative=[e for e in selected if e['dimension'].endswith(':'+field) and 400<=e['actual_http']<500]
    legal=[e for e in selected if e['actual_http']<300 and isinstance(e.get('input'),dict) and field in e['input']]
    supplemental=[n for n in normals if n['table']==row['table'] and field in n['fields'] and n['status']=='PASS']
    linked=dict(scope=row['scope'],table=row['table'],field=field,route=method+' '+route,status='PASS' if (legal or supplemental) and negative else 'NOT_RUN',scope_of_pass='actual input validation + observed normal DTO/status; complete business semantics remains separate',negative_dimensions=' '.join(sorted({e['dimension'] for e in negative})),negative_event_ids=' '.join(str(e['index']) for e in negative),legal_event_ids=' '.join(str(e['index']) for e in legal),supplemental_legal_rounds=' '.join(str(n['round']) for n in supplemental),evidence='../apis/events.json; normal-input-results.json',evidence_sha256=hashlib.sha256((ROOT/'apis/events.json').read_bytes()).hexdigest())
    links.append(linked)
(OUT/'api-input-links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'api-input-links.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    wr=csv.DictWriter(fh,fieldnames=list(links[0]));wr.writeheader();wr.writerows(links)
print('declared field links',len(links),'PASS',sum(r['status']=='PASS' for r in links),'NOT_RUN',sum(r['status']=='NOT_RUN' for r in links))
