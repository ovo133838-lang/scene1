# 题目01：全部实际使用 Skill 汇总

更新：2026-11-12（北京时间）。以下只列有读取/执行依据的Skill；角色文件和未调用候选不计已使用。作者归属与调用完成分别核对，不把AI协助稿称学生已自编/审核。当前文件是汇总，不是完整会话导出。源文件SHA256见本轮skill-source-manifest.json。

## scene1-business-check

- 名称、来源、版本：题1项目Skill，AI协助编写0.1，2026-11-12补成0.2；文件[SKILL.md](../../.agents/skills/scene1-business-check/SKILL.md)。学生作者/审阅证据待补。
- 使用位置：开发DEV-B02自检、独立测试IT-001/002与最终交付版；本轮独立上下文finish_field_verification、finish_api_verification及主开发QA06，针对真实字段/API/故障补测。
- 使用原因：只看支付成功不足以证明库存、退款、发货一致，需要验证迟到不再占库、UNKNOWN不另退、同键重试不重复收退款。
- 输入和过程：原题共通+题1、U01–U06、真实DDL/schema/routes和当前文件哈希；独立字段SQL合法/反例及全表回滚校验，HTTP参数/权限/幂等/依赖矩阵，两轮事务和进程恢复测试。
- 实际帮助：历史IT-001/002定位冲突退款重试、可信收款被404推翻；本轮字段反例发现FIELD-001：审核原因NULL穿过旧CHECK，开发新增003-shop原子前向迁移。崩溃前/后恢复验证单笔渠道款与单笔receipt、库存仅占用一次。具体数字只按结果原件统计。
- 证据与局限：历史evidence/independent-testing*/skill-usage.md和report；本轮桌面题目01-补充验证/2026-11-12/fields、apis、faults，最终以各报告/首败/复测为准。字段metadata不是服务约束通过，观察型SQL类型转换不算严格反例。学生没有逐缺陷指导记录，不把AI自修写成学生指导。

## scene1-acceptance

- 名称、来源、版本：题1项目Skill，AI协助稿0.1→0.2；[SKILL.md](../../.agents/skills/scene1-acceptance/SKILL.md)，学生来源待补。
- 使用位置：历史独立验收final/release上下文真实读取并执行；本轮0.2独立浏览器验收完成情况以browser/skill-usage.md实际记录为准，文件未产生前不能视为本轮调用完成。
- 使用原因：独立于开发/测试，按原题五场景和共通要求检查最终候选，避免以单元覆盖率或开发声明代替页面业务闭环。
- 输入和过程：原题、当前源码/版本、独立测试及缺口、隔离运行地址、部署/过程索引；历史已两轮多角色API/DB/重启/质量复验，本轮要求真实浏览器四工作台及截图、同版本核对。
- 实际帮助：历史AC001–005发现外部ID、仓库DTO、签名方向、request_id、分页问题，修复与复测均有原件；未覆盖的全量矩阵和独立浏览器路径明确NOT_RUN，推动本轮补测。没有把本地候选通过判为整题完成。
- 证据与局限：evidence/independent-acceptance-final和release/report、skill-usage；本轮browser报告若完成后追加。Git/部署/学生材料缺失仍阻断整题，历史主开发截图不能替代独立浏览器验收。

## skill-creator（既有）

- 名称、来源、版本：系统Skill，C:/Users/30343/.codex/skills/.system/skill-creator/SKILL.md，无语义版本，以hash绑定。
- 使用位置：开发准备DEV01与本轮DOC02，主开发上下文读取使用。
- 使用原因：两个旧项目Skill过于精简，需要成为可发现、能重复执行的题1工作流，明确失败处理和完成标准。
- 输入和过程：题1业务/验收要求、旧Skill、AGENTS和真实测试缺口；补全七要素、配置入口、隔离环境/真字段规则；两个quick_validate实际返回Skill is valid。
- 实际帮助：将全字段/路由清点、UNKNOWN冻结、故障恢复和独立浏览器证据写为可执行步骤，并要求失败留原件/交开发，不把角色设定当Skill。
- 证据与局限：两个SKILL.md、docs/skill-configuration.md与本轮配置/校核原件；quick_validate只验证格式，不证明业务完成或学生作者来源。

## computer-use（既有）

- 名称、来源、版本：插件computer-use，实际文件C:/Users/30343/.codex/plugins/cache/openai-bundled/computer-use/26.1103.60933/skills/computer-use/SKILL.md；历史原型加载的具体版本以当期usage为准。
- 使用位置：原型阶段走查，历史开发UI回查四工作台；本轮独立浏览器调用由独立验收实际记录补入，不凭本汇总推定。
- 使用原因：验证可操作页面、展示错误与状态，不能只靠HTML源码/截图静态存在。
- 输入和过程：真实浏览器URL、可操作原型及本地HTTP服务；通过工具读取DOM、点击/填写、观察页面与截图。
- 实际帮助：形成原型18截图和走查；业务UI回查确认运营汇总/订单与运单可见。历史主开发UI操作范围有限，未替代独立全场景。
- 证据与局限：桌面题目01-原型设计/skill-usage.md、evidence/ui及本轮browser实际记录。无部署验证；浏览器动作与程序并发分别标注。

## student-project-audit（既有）

- 名称、来源、版本：个人既有C:/Users/30343/.codex/skills/student-project-audit/SKILL.md，以源hash绑定。
- 使用位置：396要求完成表拆解，用户指定的题1交付版评分检查；本轮补实现不是重新评分。
- 使用原因：共通条款及题1复合要求易遗漏，需逐条原文映射、证据门禁和固定评分。
- 输入和过程：原题和提交规范、全部交付物及可见过程、实际质量/版本证据；拆396行、106计分原子，官方脚本计分，缺证据不勾选。
- 实际帮助：指出完整字段/API/故障及独立浏览器不足、发布和学生材料未齐；历史评分原始8.10/门禁7.90，保留原报告，本轮整改不追改过去结论。
- 证据与局限：桌面题目01-完成情况/skill-usage.md、题目01-项目检查/2026-11-12-交付版检查；审查者曾参与开发，不冒称教师独立终验；当前补测不自动提高评分。

## 配置、纠错链与尚缺人工材料

配置见[skill-configuration.md](docs/skill-configuration.md)。两个项目Skill0.2已包含用途、触发、输入、步骤、输出格式、失败处理和完成标准。实际独立读取/执行以对应会话和原件为准；未用Skill不列入。

本轮真实链：用户指出字段/API必须基于代码并要求补齐 → 独立字段Skill检查发现审核原因NULL问题 → AI开发修正003迁移 → 独立复验。用户的范围要求有记录，但尚无学生针对这个缺陷的具体判断/指导，不能完整冒称“学生指导纠错”已满足。请学生审阅真实首败和修复后给出实际意见，再保存修订及复测。没有编造无问题或零缺陷。

学生亲自讲解Skill帮助/局限的视频及当天群提交尚未提供，时间目录准备见docs/student-review-and-video.md；全部人工门槛仍待真实完成。


## 本轮独立浏览器调用的实际收尾

2026-11-12，独立上下文/root/independent_browser_acceptance实际读取两个项目Skill0.2、computer-use及原题/当前源码，按scene1-acceptance启动验收并执行失败处理。原生Windows控制因URL置信度无法满足而停止；新turn的CUA返回无可用浏览器/iab不可用，工具库存browsers为空。已依要求completion_summary结束。五场景NOT_RUN，无业务操作或截图，不用API替代。证据：桌面补充验证/browser/{report.md,actions.jsonl,case-matrix.csv,skill-usage.md,version-start.json,version-end.json}。24个既定生产文件前后相同。实际帮助是明确环境阻塞和真实未验证范围，不是发现产品缺陷；恢复受控浏览器后仍需完整重跑。


## 最终补测交接范围

字段独立上下文按scene1-business-check完成27表272列、2992维1818PASS/1174NA；265业务列的两轮真实HTTP/SQL谓词及36检查点、旧库升级有效与脏历史原子失败均保存fields/。API独立上下文完成49入口686维、3764HTTP及两轮16组显式栅栏，apis/报告及Skill使用记录可复查。主开发最后脱敏扫描另发现带query登录负面case泄露教学密码，已清除三份事件副本的6处凭证并修记录器exact-path判断，sentinel自检通过；证据apis/log-redaction-correction.json。该修正属AI发现与执行，不编造学生指导。生产24文件hash未改变，浏览器五场景仍NOT_RUN；这些追加不提高历史评分或替代主分支部署。


## computer-use本次服务器预览实际调用（2026-11-12）

在已批准的部署阶段，主Agent读取既有computer-use Skill并使用受支持CUA/IAB：检查面板终端、通过文件上传候选包与已审阅脚本，核对SHA256后执行隔离部署；观察两轮HTTP冒烟、重启订单查询、账号权限/端口隔离及公网登录页。用户亲自确认许可协议，并针对新增专库、受限账号、服务和端口当次批准；面板凭证未落盘。输出为pipeline/preview-result.json、终端DOM原件及preview-public.jpg，帮助确认真实服务器运行和公网地址，避免将面板登录或本机结果作为上线依据。限制：仅开发预览，未执行正式main流水线；主Agent页面检查不是独立浏览器五场景验收，后者仍NOT_RUN。只读SQL核对命令首败后修正成功，不编造成产品缺陷或学生指导。


2026-11-12密码维护：主Agent按computer-use的密码修改必须交由用户执行规则，先完成脚本/只读检查；用户亲自通过普通文本输入框提交密码修改，随后主Agent验证六个公网角色登录。独立测试Agent实际读取业务Skill及原题/当前代码，补充登录边界、角色/会话/Seed与HTTP请求键测试；见桌面pipeline/password-change-independent.md。没有把用户不一致的输入尝试当成功，也未把主Agent六次登录当独立五场景验收。
