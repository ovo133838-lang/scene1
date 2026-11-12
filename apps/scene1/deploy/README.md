# 题1自动发布准备与实际状态

2026-11-12新增本题独立流水线`.github/workflows/scene1.yml`，没有改变框架既有workflow。当前仅本机生成和检查，未上传GitHub、未触发Actions、未连接服务器或声称部署成功。

流水线对dev/01、PR和main执行fmt/vet、两轮单元、整体及8核心包覆盖率≥85%、两轮race及构建；只允许main push的发布job，将同一github.sha写入二进制，产物校验后部署并进行健康/业务冒烟。仓库main保护还需实际启用必需检查`quality`与`integration`，禁止直推/删除/强推。正式发布前仍需独立测试/验收通过及真实工作项核验、合规提交和PR。

当前模板适配Linux amd64、systemd，目标是否符合须由服务器资料核实。预置专用`scene1`系统用户、`/opt/scene1/releases`目录、Python3、curl和MySQL8专用schema/受限用户；复制两份service到`/etc/systemd/system/`并daemon-reload，Secret只放`/etc/scene1/shop.env`和`mock.env`（root读取权限600）。服务进程凭systemd读取环境，不需直接读取文件。环境字段见`.env.example`，两边HMAC/admin应一致，渠道和商城URL可在本机回环互通；SHOP HOST按反向代理需求设定。不要把Windows本机MySQL地址直接复制到服务器。

Actions的`scene1-teaching`环境配置四项Secret：SCENE1_DEPLOY_HOST、SCENE1_DEPLOY_USER、SCENE1_DEPLOY_KEY、SCENE1_KNOWN_HOSTS（管理员核验的host key，不临时信任扫描结果）。部署身份需允许执行指定发布脚本的sudo；服务器服务账户不赋予root。环境审批/仓库规则由实际权限确认，不伪造截图。

冒烟使用真实接口`/health/ready`验证发布SHA、`/health/live`验证存活，可信登录后创建一笔1件待付款订单，查询、取消并确认库存和资金恢复，留下真实审计/关闭记录；不产生收款。活动商品须已上架且有可售库存，否则冒烟失败、发布回退，不擅自修改商品配置。生产教学环境确保这段验证期间不并发改对应商品；并发业务验证由独立隔离矩阵完成。

脚本用release目录和current符号链接切换：失败恢复上一版二进制并重启；首次失败停两服务，保留发布目录/日志。数据库迁移保持前向，不自动执行down或删除数据；遇到不兼容迁移先人工评审和备份，不能仅二进制回退。`deployment.json`和`smoke-result.json`对应具体SHA，Actions保存运行日志与质量profile。当前没有这些线上原件，不能勾选实际部署完成。

还需：真实版本、r17te9需求/Bug ID及meegle权限，GitHub MCP/Actions/保护权限，101.96.204.17的系统架构/SSH端口用户/域名端口/目录、上述Secret和服务器MySQL配置。本机可执行验证不能替代主分支发布。


## 已检查的服务器与开发预览准备（2026-11-12）

面板已登录，实际只读核实Ubuntu24.04/x86_64，Docker/systemd/Python/mysql/curl/git/go可用；已有MySQL8.4.13容器1Panel-mysql-3fae，未更改echo_admin等现有库。根盘剩余3.8GB；本题18080/18081与/opt/scene1、/etc/scene1未占用。不安装重复MySQL或清理已有数据。已构建并上传/tmp/scene1-v1.0.0-preview.tar.gz，服务器SHA256与本地一致。

可审阅预览准备脚本scripts/prepare-preview-linux.py：只新增scene1_preview/scene1_mock_preview两个schema及各自受限DB用户（限制Docker网关172.18.0.1，各只获所属schema权限），新建无交互登录的scene1-preview系统用户、独立/opt/scene1-preview与/etc/scene1-preview；随机密码/签名密钥仅在服务器root-only文件生成并保存，不显示、不沿用面板密码。只新增scene1-preview-shop/mock服务，商城18080监听对外、mock18081仅回环；不改防火墙、现有服务、正式current或用户原库。先验证哈希再运行迁移/种子，教学初次上架后真实健康/业务冒烟；失败仅停止新增服务，保留专库与诊断。访问受云端安全组现状影响，尚未开端口。

执行该脚本将创建新的受限凭证及网络服务；按computer-use的敏感访问创建确认规则，须获得本次具体批准后才执行。当前仅脚本准备/静态检查与包上传，未建库/账号、未启动服务、未上线。该脚本不是main正式发布流水线，不计自动部署完成；正式v1.0.0仍需真实工作项核验及PR/main门禁。


## 2026-11-12 15:35 当前预览部署结果

用户已完成面板许可确认并登录，随后明确批准隔离预览方案；现已实际执行成功。

- 商城公网地址：http://101.96.204.17:18080/ ，主Agent受支持浏览器实际打开登录页并保存截图。
- 版本：v1.0.0-preview.e5370c51a417；开发分支未提交候选，formal_release=false。制品SHA256为ee6757a310013be4e73fc7aa390ff8d3c2027d1edfbb35b4c67c8fac6df5aa2a。
- Ubuntu24.04/x86_64，复用MySQL8.4.13；只新增scene1_preview（20表）与scene1_mock_preview（7表）。各DB账号限制172.18.0.1和所属schema，无全局业务权限、无GRANT OPTION。
- scene1-preview-shop/mock均active；商城18080对外、模拟渠道18081仅127.0.0.1；系统用户scene1-preview不可登录。未修改防火墙、原数据库、原服务。
- 两轮真实健康/下单/查询/取消冒烟PASS，金额与库存前后一致；两预览服务重启后首轮订单仍为CLOSED，数据持久化检查通过。
- 账号：buyer1/buyer2/buyer3、operator、warehouse、support。页面密码在服务器`/etc/scene1-preview/shop.env`的`SCENE1_PASSWORD`，用户可通过已登录面板安全查看；不是面板密码或数据库密码。配置目录700、env文件600、root所有，不随源码交付。
- 管理：`systemctl restart scene1-preview-shop scene1-preview-mock`；撤销预览运行：`systemctl stop scene1-preview-shop scene1-preview-mock`。保留专库、配置、发布目录及诊断，不自动删除数据。当前仅start，未enable开机自启。

证据：桌面补充验证`pipeline/preview-result.json`（服务器实际原件）、`preview-first-run-dom.txt`、`preview-second-smoke-dom.txt`、`preview-restart-order-dom.txt`、`preview-isolation-dom.txt`、`preview-public.jpg`。只读权限核对首条SQL失败及修正记录另保留，未影响已通过的部署。

正式发布仍未完成：缺真实r17te9需求/Bug编号及meegle核验、main保护/合规提交/PR，以及main实际版本Actions运行和部署身份/Secret配置。用户明确目前没有真实需求ID，故未commit/push/PR，不以预览冒充主分支自动部署。独立子Agent无浏览器能力，五场景独立UI验收仍NOT_RUN；主Agent公网登录页截图不替代。学生真实审核、Skill指导链/作者来源、完整过程、视频/群记录继续待补。此前状态按当时记录保留，以本节为当前结论。


## 2026-11-12 账号密码维护完成（当前状态）

用户要求六个现有教学账号统一使用其指定的六位密码。用户亲自通过面板普通命令输入框执行最终修改；隐藏输入两次不一致的尝试未提交。已成功更新buyer1、buyer2、buyer3、operator、warehouse、support的Argon2id独立含盐哈希并撤销旧会话。未改面板/数据库密码，未清空订单、库存或收退款数据。

初始化时的SCENE1_PASSWORD仍保留原有至少12位bootstrap配置，以满足启动检查；已有账号不会被Seed覆盖。**该配置值在本次数据库密码重置后不再代表当前账号登录密码**，不能直接将systemd启动配置改成六位。后续冒烟需临时提供当前教学登录密码，不写入源码或报告；密码哈希备份仅在服务器/etc/scene1-preview内，权限600。

本次代码修改：HTTP登录仅在Demo模式最低6位，非Demo保持8位；公网HTTP无法使用crypto.randomUUID，页面改用crypto.getRandomValues生成128位请求键。字段/表/API路径保持一致；当前版本v1.0.0-preview.3d3d8c181404。相对原全矩阵候选，仅internal/httpapi/api.go与web/public/app.js两生产文件变化。

验证：两轮全Go单元及race、fmt/vet/build通过，当前包内整体语句覆盖86.4496%，各核心≥85%；独立测试三包及登录/权限/Seed边界两轮通过；HTTP请求键首败复现与修复后两轮JS检查通过。服务器密码更新后两轮六账号登录/旧密码拒绝/业务冒烟及重启通过；最终页面版本又完成真实上线冒烟，主Agent逐一在公网浏览器登录六账号并核对角色，均PASS。**这不替代独立五场景浏览器验收。**

证据：桌面补充验证/pipeline/password-change/{version-and-quality.json,password-reset-observed.json,six-browser-logins.json,buyer1-login.jpg,http-request-key.json}，以及pipeline/password-change-independent.md及原始输出。password-reset-observed.json是终端输出的结构化观察记录，服务器原件路径写在其中；未冒称字节级导出。源代码旧包已保留before-password-change-source.zip，旧全字段/API报告仍绑定e5370c51a417候选；新版本只按本次受影响检查给结论。

当前公网地址仍为http://101.96.204.17:18080/ 。正式main/PR/Actions、真实工作项及学生过程门槛继续未完成，无commit/push/PR。旧预览版本和旧验证原件保留，不冒充新版本完整独立终验。
