# 开发与独立测试缺陷记录（本地编号，不是飞书Bug号）

|编号|发现方式|问题与修复|证据/复测|
|---|---|---|---|
|DEV-B01|第一轮HTTP回归|教学规则未填attempt_no时空值断言panic；改为先判断非NULL再转整数|evidence/http-regression-first-failure.json、测试日志；随后两轮完整通过；mockpay和HTTP单元反例|
|DEV-B02|按业务Skill自查|矛盾退款号可能被当重复；增加退款号匹配；外部成功证明校验request/order/merchant/amount|settlement.go/worker.go；单元和后续HTTP回归|
|IT-001|独立测试反例|退款先失败后矛盾成功仍可retry；冲突关联refund_id并阻断新尝试，仅可信原键查询可澄清|evidence/independent-testing/IT-001-first-failure.txt；独立用例保留，修复后开发与独立最终复测PASS，见独立report和targeted-current|
|IT-002|独立测试反例|已知receipt被后续404推翻成无资金并结案；保留receipt标冲突，结案再校验无receipt|evidence/independent-testing/IT-002-first-failure.txt；独立用例保留，修复后开发与独立最终复测PASS，见独立report和targeted-current|

不声称这些修复由学生亲自审核或指导；学生已授权开发与独立测试，不伪造逐缺陷人工纠错。正式fix提交仍需真实飞书缺陷核验。

AC005（开发最终复核发现）：非仓库列表省略创建时间后失去正确排序。原反例evidence/pagination-first-failure.txt，修复views.go从原始实体传内部排序时间并在分页后删除；针对性单测、最新质量门禁PASS，待最新独立测试/验收报告。未改外部DTO字段。


|AC-001|独立验收契约检查|外部ID允许Unicode/query分隔符；新增路径安全ID校验，覆盖body与渠道查询path/merchant|wire反例、独立最终测试及验收已复测，见final报告|
|AC-002|独立验收DTO检查|仓库列表多返回created_at；内部_sort_time分页后删除，6字段白名单|HTTP白名单/分页回归，独立最终测试及验收已复测，见final报告|
|AC-003|独立验收协议检查|方向key_id共用、canonical文档不符；分方向派生密钥，RFC3986规范与跨语言固定向量|security固定向量和双向拒绝测试，独立最终测试及验收已复测，见final报告|
|AC-004|独立验收审计检查|响应与审计各生成request_id；服务端请求上下文关联，后台另生成ID|HTTP创建订单响应/审计一致性测试，独立最终测试及验收已复测，见final报告|

|FIELD-001|2026-11-12独立全字段SQL反例|APPROVED/REJECTED申请review_reason=NULL时CHECK结果为UNKNOWN而被MySQL接受；新增003-shop前向迁移，明确review_reason IS NOT NULL，不改001/002校验值|补充验证/2026-11-12/fields首败FIELD-01432/01433；repository迁移单测PASS，独立新库/升级/HTTP复验进行中；非飞书Bug ID，学生指导待真实补充|
