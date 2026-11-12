"""Final focused real HTTP probes for the remaining mock refund and login DTO edges."""
import importlib.util,pathlib,json,sys
P=pathlib.Path(__file__).resolve().with_name('api_matrix_20261112.py');sp=importlib.util.spec_from_file_location('matrix',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
m.OUT=m.OUT/'final-probes';m.OUT.mkdir(exist_ok=True)
try:
    m.init();m.start();m.f.login()
    for n in [1,2]:m.case('mock-refund-keys-and-signed-responses-'+str(n),m.extra_flow)
finally:
    m.stop();m.write_results();(m.OUT/'version-end.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
sys.exit(bool(m.FAILURES))
