"""Summarize current independent release evidence; does not execute business writes."""
import csv, hashlib, json, pathlib, re, shutil

APP=pathlib.Path(__file__).resolve().parents[1]
OUT=APP/'evidence/independent-testing-release'
raw=json.loads((OUT/'http-regression.json').read_text(encoding='utf-8'))
coverage=json.loads((OUT/'unit-summary.json').read_text(encoding='utf-8'))
start=json.loads((OUT/'version-start.json').read_text(encoding='utf-8'))
end=json.loads((OUT/'version-end.json').read_text(encoding='utf-8'))
rows=[]
matrix=(APP.parents[1]/'docs/scene1/04-test-matrix.md').read_text(encoding='utf-8')
for line in matrix.splitlines():
    if not line.startswith('| HTTP-'):continue
    cols=[v.strip() for v in line.split('|')][1:-1]
    ident,route=cols[:2];method,path=route.split(' ',1)
    pattern='^'+re.sub(r'\{[^}]+\}',r'[^/]+',path)+'$'
    observed=[e for e in raw['events'] if e.get('method')==method and re.match(pattern,e['path'].split('?')[0])]
    codes=sorted({e['status'] for e in observed})
    if ident=='HTTP-API01':codes=[200];observed=[{'note':raw['login']}]
    rows.append({'id':ident,'route':route,'observed_codes':','.join(map(str,codes)),'scenario_calls':'PASS' if observed else 'NOT_RUN','complete_input_auth_state_failure_matrix':'NOT_RUN','note':'Real HTTP/DB calls observed; login credentials/results intentionally excluded.'})
assert len(rows)==48 and all(r['scenario_calls']=='PASS' for r in rows)
with (OUT/'api-results.csv').open('w',newline='',encoding='utf-8-sig') as dest:
    writer=csv.DictWriter(dest,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
prefixes=tuple('apps/scene1/'+s+'/' for s in ['cmd','internal','web','migrations'])
production={k:v for k,v in start['files'].items() if k.startswith(prefixes) and not k.endswith('_test.go')}
changes={k:{'start':start['files'].get(k),'end':end['files'].get(k)} for k in sorted(set(start['files'])|set(end['files'])) if start['files'].get(k)!=end['files'].get(k)}
assert all(end['files'].get(k)==v for k,v in production.items())
assert not any(k.startswith(prefixes) and not k.endswith('_test.go') for k in changes)
comparison={'start_utc':start['at'],'end_utc':end['at'],'git_base':start['git_base'],'production_files':production,'production_hashes_stable':True,'all_snapshotted_changes':changes,'note':'Production means non-test cmd/internal/web/migrations files; scripts/docs are separately recorded.'}
(OUT/'version-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'candidate':'AC005 stored entity timestamp pagination repair','independent_role':'test','rounds':2,'http_driver_passed':raw['passed'],'business_scenario_groups':18,'additional_ac005_groups':2,'all_asserted_event_groups':sum(e.get('passed',False) for e in raw['events']),'api_route_observed':48,'api_full_matrices':'NOT_RUN','field_metadata':256,'full_field_behavior':'NOT_RUN','real_db_probes':15,'restart':'PASS','gofmt':'PASS','vet':'PASS','unit_count':2,'race_count':2,'targeted_count':2,'coverage':coverage,'production_hashes_stable':True,'first_execution_issue':'PowerShell output redirection target directory did not exist. No tests started; created evidence directory and reran, exit 0.','result':'PASS within executed scope; not overall assignment acceptance or proof of no bugs.'}
(OUT/'results-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
skill='''# 业务 Skill 实际使用记录

角色：独立测试子 Agent；日期：2026-11-12；目标：AC005候选，版本哈希见version-start/end及version-comparison.json。

已读取并采用仓库根 `.agents/skills/scene1-business-check/SKILL.md` 0.1，输入为原始题面、U01–U06、06实施决定、字段/接口/事务/矩阵、当前生产代码与隔离MySQL。

沿创建→关闭或付款→退款申请或发货→退款确认检查库存及资金守恒、渠道交易唯一、异常保留。实际运行两轮20并发抢购、重复通知、迟到支付、退款首次失败重试、结果未知禁止另起退款、退款发货竞争、越权与重启恢复；15项DB探针及AC001–005补充探针均PASS。命令及原始输出见console.txt、http-regression.json、db-results.json和unit/race原件。

Skill为AI协助起草，未证明学生自编/审核来源；Skill使用不等于正式独立验收。完整字段/API分支及崩溃注入等NOT_RUN项见report.md；本次未改生产、未提交、未部署。
'''
(OUT/'skill-usage.md').write_text(skill,encoding='utf-8')
report=f'''# 题目01 AC005候选独立测试报告

2026-11-12，独立测试子 Agent。结论：本报告所列实际执行范围通过，可交当前版本独立验收；不代表整题通过或不存在BUG。仅新增测试脚本/证据，未修改生产或契约、未提交Git、未部署。

## 版本与环境

dev/01基准 `{start['git_base']}`，当前新增尚未提交。本次专门覆盖AC005：商品、收款等DTO省略created_at时，分页必须使用原实体时间排序和生成游标；内部_sort_time在响应前删除。生产非测试cmd/internal/web/migrations共{len(production)}文件，运行前后SHA256一致，详见version-comparison.json、version-start/end.json。二进制见binary-sha256.txt。旧independent-testing-final仅绑定旧版，不能替代本报告。

Go1.27.1 Windows amd64、本机MySQL8；仅scene1_test/scene1_mock_test及18090/18091独立进程。未重置测试历史、未操作18080/18081共享预览，凭证和登录响应不导出。反例DB事务回滚；分页探针修改的测试夹具时间均finally恢复并SQL逐字回读校验。

已读取原始共通与题1、提交规范、根AGENTS/testing、U01–U06与当前共享契约，并采用scene1-business-check 0.1；实际用法见skill-usage.md。测试驱动复用经独立审查的既有完整流程，新增真实DB/HTTP分页反例。

## 实际结果

| 项目 | 结果与验证范围 | 原件 |
| --- | --- | --- |
| 五个必须演示场景及主要异常 | 两轮18组PASS：正常成交核查；每轮20并发争抢5件恰5单成功、弃单释放再买；退款冻结/首次失败再成功；迟到支付不恢复订单不双释放；退款申请发货竞争、重复与越权 | console.txt、http-regression.json |
| 退款未知及时间边界 | 两轮PASS：未知保持冻结且不另发退款；满10分钟失效；旧订单快照；签名/金额不符/未知订单异常及处理 | 同上 |
| AC001–004补充 | 两轮PASS：外部ID安全字符边界、仓库严格6字段及游标、方向key与独立canonical固定向量/防重放、响应request_id与审计关联 | 同上 |
| AC005分页反例 | 两轮，每轮products和receipts各一组：从测试库取两个ID升序夹具，小UUID设2099-01-02，大UUID设2099-01-01，故意逆转ID降序；真实HTTP limit=1首项必须小UUID、下一游标必须大UUID；两页均无created_at/_sort_time；最后恢复并核实原微秒时间 | 同上，事件AC005 stored-time pagination round 1/2 |
| 48接口路由 | 两轮流程及补充调用，48/48至少真实调用；支付查询与渠道退款幂等均补测 | api-results.csv；仅路由调用覆盖 |
| DB/字段 | 256字段元数据存在性、物理类型/NULL/default及两侧nonce结构；15项真实CHECK/FK/唯一/NULL反例与底层订单对库存余额核查PASS | field-results.csv、shop/mock TSV、db-results.json |
| 重启 | 收款及退款累计事实重启前后不变PASS | console.txt、http-regression.json |
| 格式/静态/单元/并发 | gofmt、vet PASS；全包单元count=2、race count=2 PASS；IT001/IT002与当前分页单元count=2 PASS | gofmt/vet/unit/race/targeted-current.txt |

退款申请与发货每轮5次，共10次竞争；未达矩阵所有建议并发20轮。真实MySQL/HTTP与单元sqlmock/Memory分开计证据。DB07接受MySQL外键拒绝1216或1452，本次真实1216；其余错误码及断言详见原件。

## 覆盖率与命令

`python -X utf8 scripts/independent_release.py` 最终退出0。单元命令：`go test -count=2 -covermode=atomic -coverpkg=./... -coverprofile=evidence/independent-testing-release/unit-coverage.out ./...`。相同block合并跨测试进程命中后，整体{coverage['overall']:.4f}%（{coverage['statements']}条语句），未排除自编生产包。核心包如下：

| 包 | 语句覆盖率 |
| --- | --- |
'''
for name,pct in coverage['packages'].items():
    if '/internal/' in name and not name.endswith('/testsupport'):
        report+=f'| {name.rsplit("/",1)[-1]} | {pct:.2f}% |\n'
report+='''
cmd入口23.71%和testsupport90.91%均计入整体。跨包覆盖反映各包测试对生产语句的联合执行，不能把unit.txt每行的“of statements in ./...”当该包覆盖率。原始profile、func、HTML及计算摘要齐全。开发普通包内覆盖率应读取其自身当前证据，不以本数值替代；框架根全量测试未执行。

## 执行问题与保留证据

第一次PowerShell重定向时目标证据目录尚不存在，因此脚本未启动；创建目录后执行完整两轮并退出0。此执行问题未触发生产修改。旧测试中FK错误码判断、历史UNKNOWN_ORDER等待条件等原失败保留在旧目录；当前wrapper按本轮交易精确等待。开发原AC005失败 `evidence/pagination-first-failure.txt` 保留，当前针对性两次PASS。未弱化分页排序、DTO白名单或库存/资金断言。

## 未执行与交接边界

256字段全部合法/NULL/default/边界/不可变/跨表组合、48接口全部输入/鉴权/非法状态/故障分支未穷尽，CSV完整行为列保持NOT_RUN。worker发送前后崩溃、提交后响应丢失、迁移中断恢复及全部建议并发轮数未注入。此次没有浏览器全链验证。

需要随后由新独立验收上下文读取原题、当前哈希与本报告实际复跑；本测试Agent没有启动或代签验收。学生真实审核、完整会话导出、真实飞书编号与版本及meegle核验、GitHub保护/合规提交PR、主分支CI部署、视频群提交等外部门槛未由本次完成。当前不得宣称整题完成。
'''
(OUT/'report.md').write_text(report,encoding='utf-8')
desktop=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-独立测试交付版')
desktop.mkdir(parents=True,exist_ok=True)
for path in OUT.iterdir():
    if path.is_file():shutil.copy2(path,desktop/path.name)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in desktop.iterdir() if p.is_file() and p.name!='manifest-sha256.json'}
(desktop/'manifest-sha256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'report':str(OUT/'report.md'),'desktop':str(desktop),'api_calls':len(rows),'overall':coverage['overall'],'production_files_stable':len(production),'snapshot_changes':changes},ensure_ascii=False,indent=2))
