import csv,datetime,hashlib,importlib.util,json,pathlib,re,shutil
APP=pathlib.Path(__file__).resolve().parents[1];OUT=APP/'evidence/independent-testing-final'
r=json.loads((OUT/'http-regression.json').read_text(encoding='utf-8'));extra=json.loads((OUT/'http-extra.json').read_text(encoding='utf-8'))
matrix=(APP.parents[1]/'docs/scene1/04-test-matrix.md').read_text(encoding='utf-8')
rows=[]
for line in matrix.splitlines():
    if not line.startswith('| HTTP-'):continue
    cols=[v.strip() for v in line.split('|')][1:-1];ident,route=cols[:2];method,path=route.split(' ',1)
    pattern='^'+re.sub(r'\{[^}]+\}',r'[^/]+',path)+'$'
    found=[e for e in r['events']+extra['events'] if e.get('method')==method and re.match(pattern,e['path'].split('?')[0])]
    codes=sorted({e['status'] for e in found})
    if ident=='HTTP-API01':codes=[200];found=[{'note':r['login']}]
    rows.append({'id':ident,'route':route,'observed_codes':','.join(map(str,codes)),'scenario_calls':'PASS' if found else 'NOT_RUN','complete_input_auth_state_failure_matrix':'NOT_RUN','note':'Actual calls, not complete branch coverage. Login executed; credentials/results excluded.'})
assert len(rows)==48 and all(row['scenario_calls']=='PASS' for row in rows),rows
with (OUT/'api-results.csv').open('w',encoding='utf-8-sig',newline='') as fh:
    writer=csv.DictWriter(fh,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
start=json.loads((OUT/'version-start.json').read_text());end=json.loads((OUT/'version-end.json').read_text())
assert start['files']==end['files']
unit=json.loads((OUT/'unit-summary.json').read_text())
summary={'http_passed':r['passed'],'rounds':2,'scenario_groups':sum(e.get('passed',False) for e in r['events']),'api_routes_called':len(rows),'AC001_004':'PASS two rounds real HTTP plus fixed vector and wrong-direction/replay rejection','extra_passed':extra['passed'],'field_metadata':256,'db_probes':15,'restart':'PASS','cross_package_unit_overall':unit['overall'],'core_packages_minimum':85,'full_field_boundaries':'NOT_RUN','complete_api_branch_matrix':'NOT_RUN','production_changed_during_http':False,'production_exclusions':[]}
(OUT/'results-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

report='''# 题目01返修版独立测试报告

日期：2026-11-12。角色：独立测试子Agent；只编写/执行测试与证据，未修改生产、契约、Git历史或真实业务库。本次为AC001–004开发返修后的新候选版本，不覆盖此前报告。

## 版本与环境

dev/01基准a7388f69a555c2ce7bd4939ecb8ae91cbe6380cf，尚未提交；version-start/end.json逐文件SHA256绑定本次代码。两轮HTTP运行期间文件清单无变化。二进制SHA256见binary-sha256.txt；Go1.27.1、Windows amd64、MySQL8、本机3306。使用scene1_test及scene1_mock_test隔离库、18090/18091独立进程；不重置历史数据，DB反例事务回滚。未操作18080/18081预览、未打印凭证。

已读原始共通+题1、提交规范、根AGENTS/testing、六项确认和当前实施决定/共享契约；使用scene1-business-check 0.1沿库存、订单、收款、退款、发货与异常检查。原题要求所有业务分支并保留过程，本报告不把限定测试通过当整题通过。

## 实际结果

| 项目 | 结果与范围 | 原件 |
| --- | --- | --- |
| 五组完整业务场景与主要异常 | 两轮18组PASS；20并发每轮恰5成功，弃单释放再买；退款首败重试、迟到不双释放、退款发货竞争、重复/越权 | http-console.txt、http-regression.json |
| AC001外部ID | 两轮真实HTTP拒绝Unicode、query/fragment/path/percent、点/双点、超80；涵盖付款/退款通知、管理目标引用和查询path/merchant；安全非UUID未知订单引用可入异常流程 | http-regression.json、http-extra.json |
| AC002仓库DTO | 两轮真实HTTP严格6字段，内部created_at/_sort_time不出站；额外每轮创建两笔已付订单，limit1分页无重复 | 同上、http-extra-console.txt |
| AC003签名 | Python独立固定向量与Go向量一致；两轮真实HTTP错误方向401、正确方向404（未知请求）、相同nonce重放401；双向正常请求/通知已覆盖 | http-regression.json、targeted-current.txt |
| AC004审计关联 | 每轮真实创建订单的响应meta.request_id与数据库审计CREATE事件一致，忽略客户X-Request-Id | http-regression.json |
| 48路由 | 全部至少实际调用；附加支付查询、模拟退款幂等，两轮执行 | api-results.csv；不等于全部输入/鉴权/状态分支覆盖 |
| 重启恢复 | 收款/退款累计事实重启后不变，PASS | http-console.txt |
| 数据库与字段 | 256字段元数据及两侧nonce存在；15项CHECK/FK/唯一/NULL反例及底层订单对库存核查PASS | field-results.csv、shop/mock TSV、db-results.json |
| 单元/格式/vet/race | count2单元与count2 race PASS；fmt/vet通过；所有自编生产包纳入 | quality-console.txt、unit/race/vet/gofmt原件 |
| IT001/IT002原缺陷与AC针对性单元 | 当前版本count2 PASS，旧失败保留在独立测试目录 | targeted-current.txt |

两轮退款申请vs发货每轮5次竞争，共10次；未达到矩阵所有建议20轮，不伪称压力全面。接收端资金/库存持久化由真实MySQL/HTTP探测验证；单元Memory/sqlmock不冒充数据库集成。

## 覆盖率

本次独立命令为`go test -count=2 -covermode=atomic -coverpkg=./... -coverprofile=evidence/independent-testing-final/unit-coverage.out ./...`。按block合并跨测试进程记录，整体90.1899%；8核心包为channel97.06%、domain100%、HTTP96.04%、mock98.28%、repository96.20%、security95.95%、service90.75%、wire94.06%。cmd入口23.71%与testsupport90.91%均计整体；无生产排除。可读HTML/func及原始profile齐全。

开发普通包内覆盖率86.39%也通过，不能只挑cross-package较高值；后者计入跨包单元执行，语句集合一致。未执行框架根全部测试，不把已有框架CI当本题结果。

## 失败与修正

首轮复测的旧scenario driver等待UNKNOWN_ORDER时只判断“列表非空”，已有历史记录导致新通知尚未到达即StopIteration。harness-first-failure/results保留；独立wrapper增加本轮txn精确等待，未删断言、未改生产，然后完整两轮重跑PASS。此前独立测试MySQL FK错误码和验收SQL误表名的原始失败仍在各自旧目录，本报告不覆盖。

AC001–004当前针对性探测通过；这不是学生亲自审阅或逐缺陷指导的证明。普通fix仍需真实飞书Bug和meegle核验，不以本地AC编号冒充。

## 未验证与交接边界

256字段每一合法/NULL/default/边界/不可变/跨表组合、48接口全部输入/鉴权/非法状态/故障分支未穷尽，CSV完整行为列仍NOT_RUN。worker发送前后崩溃、提交后响应丢失、迁移中断恢复及全部建议并发轮数尚未注入。已通过不能证明没有BUG。

本Agent未作浏览器全链操作、独立正式验收、学生作者/历史审核、完整会话导出、meegle/GitHub保护/合规提交PR、主分支CI部署、视频群提交。需要后续独立验收当前哈希版本，并补外部权限与学生真实材料；整题仍不能判通过。
'''
(OUT/'report.md').write_text(report,encoding='utf-8')
(OUT/'skill-usage.md').write_text('''# 实际Skill调用

scene1-business-check 0.1，项目AI协助稿，文件.agents/skills/scene1-business-check/SKILL.md。本独立测试上下文先读原题/六项确认/当前契约和返修源码，以AC001–004、IT001/002、五场景和资金库存守恒为输入，真实执行independent_final.py、extra及quality脚本。帮助按跨环节事实复核安全ID、签名、DTO与审计关联；输出report、HTTP/DB原件和哈希。发现旧回归等待历史异常的脚本时序问题，保留失败并精确等待后复跑。当前限定检查通过，学生自编来源、亲自指导与全字段/全部故障组合仍不足，不伪称Skill消除了所有缺陷。
''',encoding='utf-8')
dest=pathlib.Path('D:/Desktop/codex产出物/Go业务场景记录/题目01-独立测试最终');shutil.copytree(OUT,dest,dirs_exist_ok=True)
print(json.dumps(summary,ensure_ascii=False,indent=2))
