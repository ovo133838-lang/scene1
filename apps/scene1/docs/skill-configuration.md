# 题1 Skill配置和真实调用入口

2026-11-12。仓库中的两个项目Skill：

- `.agents/skills/scene1-business-check/SKILL.md`（0.2）：跨订单/库存/资金/退款/发货验证。
- `.agents/skills/scene1-acceptance/SKILL.md`（0.2）：独立上下文验收五场景及全部共通门禁。

使用Codex打开仓库根`D:/Desktop/go-zero-master`，项目技能目录为`.agents/skills/<name>/SKILL.md`。文件有name/description YAML frontmatter；在工具技能列表中可发现时以`$scene1-business-check`或`$scene1-acceptance`选择。当前聊天运行目录在另一个记录工作区，所以本轮由独立Agent显式读取上述绝对文件并依步骤执行，保留read调用、测试命令和实际结果；不声称本会话已经自动加载项目技能目录。无需修改全局配置或安装第三方依赖。

业务调用输入范例：本题原题、U01–U06、dev/01基准SHA+当前文件哈希、隔离库、实际API注册与DDL、已有失败原件；要求输出逐规则/字段/接口结论与HTTP/DB证据，不从声明推定通过。

验收调用输入范例：原题和最终代码/哈希、独立测试原件及缺口、浏览器商城和渠道地址；在新独立上下文执行五场景，输出逐项结论、截图/数据库结果、部署及人工门禁缺失。不能在开发会话中改称验收Agent。

本轮结构验证命令：`python -X utf8 C:/Users/30343/.codex/skills/.system/skill-creator/scripts/quick_validate.py <Skill目录>`，两个文件均返回`Skill is valid!`。这只证明格式，不证明业务通过。实际执行记录见桌面补充验证目录下fields/apis/browser的`skill-usage.md`及项目总`skill-usage.md`。

作者归属：文件由AI协助编写，用户要求按题面补齐；没有证据证明学生自行编写全部内容或逐条审核。不代填学生签名、日期与纠错指令。若学生审核，应保留其真实意见、修订diff和随后复测；补写文档不能冒充开发前历史。
