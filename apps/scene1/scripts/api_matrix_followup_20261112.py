"""Additional independent route storage-failure and DTO evidence against fresh real DBs."""
import importlib.util,pathlib,json,datetime,sys
P=pathlib.Path(__file__).resolve().with_name('api_matrix_20261112.py')
sp=importlib.util.spec_from_file_location('matrix',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
m.OUT=m.OUT/'followup';m.OUT.mkdir(exist_ok=True)
try:
    m.init();m.start();m.f.login();m.case('all-dependent-route-storage-failure',m.dependency_matrix)
    m.case('HMAC-window-safe-margin-retest',m.window_retest)
    for n in [1,2]:
        m.case('extra-flow-retest-'+str(n),m.extra_flow)
        m.case('semantic-boundaries-retest-'+str(n),m.semantic_boundaries)
        m.case('write-route-idempotency-round-'+str(n),m.write_replays)
        m.case('state-and-ownership-round-'+str(n),m.state_ownership)
finally:
    m.stop();m.write_results();(m.OUT/'version-end.json').write_text(json.dumps(m.version(),indent=2),encoding='utf-8')
sys.exit(bool(m.FAILURES))
