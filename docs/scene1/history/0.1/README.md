# 题目01开发、测试与验收约束包

版本0.1，2026-11-12。AI根据用户请求起草，待学生亲自阅读、修改和审核。本次未开发业务、建表、运行测试或提交Git。

| 文件 | 内容 |
| --- | --- |
| [根AGENTS.md](../../AGENTS.md) | 项目总约束与所有共通门槛 |
| [角色入口](../../.agent/README.md) | 开发、独立测试、独立验收的使用和改动范围 |
| [00-review.md](00-review.md) | 已确认U与待审A/技术方案、外部缺口、学生审核 |
| [01-data-dictionary.md](01-data-dictionary.md) | 23种表结构、256个字段的类型、空值、范围、约束/索引及测试要求；auth_nonces商城和mock各实例化一张 |
| [02-business-rules.md](02-business-rules.md) | 状态、库存资金、锁/事务、幂等、外部超时与恢复 |
| [03-api-contract.md](03-api-contract.md) | 48个接口，完整请求字段、DTO白名单、权限、签名、错误码、幂等及副作用 |
| [04-test-matrix.md](04-test-matrix.md) | 全字段/全接口映射、五完整场景、并发/异常/重启、共通门槛 |
| [05-evidence-templates.md](05-evidence-templates.md) | 真实加载/审核、测试结果、缺陷复测、覆盖率及发布关联模板 |
| [原始题面](source/assignment.md) / [提交原文](source/commit-convention.md) | 原始来源；摘要不可替代 |
| [假设确认原件](source/03-假设与确认清单.md) / [原验收条件](source/04-验收条件.md) | 保留旧阶段快照，U01–U06与待审A有区别 |

框架来源：当前既有go-zero导入根模块github.com/zeromicro/go-zero、Go1.25.0，仓库基准a7388f69a555c2ce7bd4939ecb8ae91cbe6380cf。保留LICENSE及框架内容，未核实远程框架release标签，不冒称某个发布版本。业务拟新增apps/scene1独立模块，PostgreSQL16、单体go-zero服务及独立HTTP模拟渠道均是技术建议，不以微服务/组件数作为要求。

原件source/内保留历史相对链接和时间描述，阅读其正文及source-manifest.json理解来源；仓库导航以本入口为准，不篡改历史快照。正式任务规划、学生审核及实际业务/独立测试/验收/Skill/Git发布证据还需后续执行。
