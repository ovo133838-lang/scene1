"""Exercise runner failure handling in subprocesses without MySQL/HTTP mutation."""
import pathlib,subprocess,json,tempfile,os,sys
APP=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-补充验证/2026-11-12/apis/fail-closed-selfcheck');OUT.mkdir(exist_ok=True)
results=[]
for name in ['api_matrix_20261112.py','api_matrix_followup_20261112.py','api_matrix_final_probes_20261112.py','api_barrier_20261112.py']:
    if name=='api_matrix_20261112.py':
        script="""import runpy,sys,os,pathlib
def deny(event,args):
 if event=='socket.connect' or (event=='subprocess.Popen' and 'mysql' in str(args[0]).lower()):raise RuntimeError('SELFTEST_DENIED_DEPENDENCY')
sys.addaudithook(deny)
runpy.run_path(sys.argv[1],run_name='__main__')
"""
    else:
        script="""import importlib.util,sys,pathlib
p=pathlib.Path(sys.argv[1]);src=p.read_text(encoding='utf-8')
# Exercise the actual final exit expression, with the recorded test-failure collection.
tail=src[src.rfind('sys.exit('):];m=type('FailureFixture',(),{'FAILURES':[{'case':'synthetic known failure'}]})()
exec(compile(tail,str(p),'exec'))
"""
    env=os.environ.copy();env['SCENE1_MATRIX_OUT']=str(OUT/name.replace('.py',''))
    p=subprocess.run([sys.executable,'-X','utf8','-c',script,str(APP/'scripts'/name)],env=env,capture_output=True,text=True,encoding='utf-8')
    results.append({'script':name,'exit_code':p.returncode,'expected':'nonzero','passed':p.returncode!=0,'stdout':p.stdout,'stderr':p.stderr})
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results,ensure_ascii=False));sys.exit(0 if all(x['passed'] for x in results) else 1)
