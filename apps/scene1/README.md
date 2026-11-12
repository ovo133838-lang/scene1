# 题目01 · 小型商城交易协作台

Go 核心业务、go-zero HTTP、MySQL8 持久化、独立可控 HTTP 模拟支付，以及买家/仓库/客服/运营四工作台。当前为本地教学预览，尚无合规提交、PR或正式发布。

## 本机运行

先管理员运行桌面 `start_all.bat`，确认MySQL3306可用。服务不需要Redis。已在本机建立本题专用库 `scene1_shop_20261112` / `scene1_mock_20261112`，以及隔离回归库 `scene1_test` / `scene1_mock_test`；运行服务使用两个独立受限账号，不使用root。已有业务表不被重置。

真实配置在本目录 `.env.local`（已Git忽略）；示例见`.env.example`，不要把真实文件提交或截图。买家账号buyer1/buyer2/buyer3；员工operator/warehouse/support。共用的教学登录密码取本机`.env.local`中的`SCENE1_PASSWORD`；不是数据库密码。教学控制使用`SCENE1_ADMIN_TOKEN`，仅输入本地页面控制区。

```powershell
Set-Location D:/Desktop/go-zero-master/apps/scene1
go build -o bin/scene1.exe ./cmd/scene1
./scripts/start-local.ps1
# 商城 http://127.0.0.1:18080 ，HTTP模拟渠道 http://127.0.0.1:18081
# 停止仅本题已登记的进程：
./scripts/stop-local.ps1
```

可在两个终端前台分别运行`./bin/scene1.exe -mode shop`和`./bin/scene1.exe -mode mock`。启动按校验和应用迁移并幂等补种；`-migrate-only`仅迁移。配置支持`SCENE1_PORT/HOST/SHOP_URL/MOCK_URL`，默认仅回环访问。教学预览有两笔页面走查订单（一次发货、一次退款），所以活动A当前可售4、出库1，初始数量仍5；测试数据库与它隔离。

## 演示

1. operator上架→buyer1买1–2件→模拟付款→刷新看到待发货→warehouse登记承运方和运单→买家查运单→operator按单核对与汇总。
2. `python scripts/independent_release.py`在隔离库执行固定两轮、真实启动18090/18091，20个HTTP并发争5件、关闭释放再买；不清空业务库。
3. 退款前用独立教学管理令牌为订单设置REFUND/EXPLICIT_FAIL/attempt_no=1；买家申请立即冻结，仓库不能发；客服批准→明确失败→重试成功→数量恢复。
4. 支付设置TIMEOUT_AFTER_SUCCESS，点击支付后立即取消；渠道原键查询成功成为迟到款，客服异常列表核实→整笔退回，订单保持关闭且不再释放数量。
5. PENDING保持未知、仅查原键；TIMEOUT_AFTER_SUCCESS模拟渠道成功响应丢失、通知暂延迟；DELAY_NOTIFY/DUPLICATE_NOTIFY控制通知。业务时间可推进10分钟，认证/HMAC/租约仍走真实时钟。

模拟服务不是真实支付接入；页面仅教学数据，不收集真实地址或支付资料。商品B=20000分/8件。旧订单快照价格、满10分钟过期、拒绝后可重提、退款未知保持冻结等遵守U01–U06。

## 契约与质量

- 需求/原题/字段/接口：仓库`docs/scene1/`；0.1历史和0.2 MySQL物理映射均保存。`api/openapi.json`是48路由索引，字段详情以共享契约和HTTP实现校核，不宣称自动生成完整SDK。
- 24业务表实例、256种字段（nonce在两侧各实例），MySQL生成列保证活动申请/尝试/支付意图条件唯一。002迁移补充CHECK/默认/索引；迁移按校验和拒绝漂移。down仅供明确隔离测试回滚，不自动运行。
- 小规模教学系统写事务先锁单例时钟/渠道技术锁行，跨进程串行裁决；读使用一致快照。HTTP渠道调用不持写锁，outbox/固定请求键/数据库租约支持恢复。吞吐优化不在本题范围。
- 金额以整数分存储，JSON字符串；严格JSON、DTO白名单、可信会话、HMAC请求和响应、nonce持久化防重放；异常审计不可删除/通用改状态。
- `python scripts/quality.py`执行fmt/vet/单元覆盖率门禁/race/build，Windows race需要可用gcc：环境变量`SCENE1_CC`指向编译器。所有自编生产代码均计整体覆盖，测试替身也保守计入；8核心包分别≥85%，启动入口覆盖单列。
- `python scripts/db_audit.py`只读schema+隔离库回滚反例；`functional.py`保留真实HTTP结果；失败和独立报告在`evidence/`。不能把单元Memory替身当真实数据库验证。
- 回归会追加隔离测试数据，不提供清空异常/任意改订单状态接口。需要全新验收基线时创建新隔离schema并改本地配置，不能删共享记录。

## 来源与当前边界

既有仓库根是go-zero框架源码，基准`a7388f69a555c2ce7bd4939ecb8ae91cbe6380cf`，保留其LICENSE与源码；新增本目录模块、SQL、页面、测试和脚本为本题AI协助编写，未使用现成完整业务项目。模块本地replace框架根；使用实际`rest.NewServer/AddRoute`和conf API，未运行goctl脚手架。Go1.27.1开发；当前x/crypto依赖令模块最低Go版本为1.26。

学生自编/审核约束与Skill的来源门槛、全过程会话完整导出、真实飞书编号/meegle、GitHub主分支保护/PR、指定服务器CI/CD、视频和班级群提交仍需真实材料，不代签、不伪造。用户已说明提交/部署资料稍后提供。独立测试和验收按各自最终报告，业务自测通过不表示整题已合格。

最终候选返修AC001–005已通过独立测试与独立验收复测，详见`evidence/independent-testing-release/report.md`和`evidence/independent-acceptance-release/report.md`；整题仍缺Git发布/部署与学生材料。旧functional基础驱动在累计异常数据下的等待时序失败保留，推荐运行带本轮交易精确等待的independent_release.py，不能只用列表非空判断新通知已到达。


2026-11-12最新：用户亲自完成六个教学账号统一六位密码的最终修改，旧密码失效。当前预览v1.0.0-preview.3d3d8c181404；两轮服务器登录/旧密码拒绝/重启与业务冒烟通过，最终公网六角色页面登录全部通过。初始化SCENE1_PASSWORD仅作bootstrap，重置后不代表当前登录密码；不要改成六位导致启动失败。[修改、验证与证据](deploy/README.md)。独立五场景浏览器及正式发布门槛未因此通过。
