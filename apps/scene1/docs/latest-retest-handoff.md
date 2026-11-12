# 最新候选复测交接（分页返修）

2026-11-12。在AC001–004完成后，主Agent源码检查发现非仓库列表DTO也省略created_at（如商品/收款），旧page从DTO取时间导致按随机UUID排序。新增service/pagination_regression_test.go首先真实失败，原件evidence/pagination-first-failure.txt；修复views.go的普通列表分支，在DTO中暂存来自原实体的_sort_time，page构造游标后删除。外部字段白名单不变。

新增测试故意让较小UUID更新、较大UUID更旧，验证第一页、第二页与内部字段不外泄。当前fmt/vet/单测覆盖/race/build已通过，整体86.41%、核心均≥85%。这是AC005（本地编号）分页契约修正；新业务源码应重新绑定哈希，旧final报告只适用其旧哈希。

后续独立测试：读取原题/规范，复核这处变更，实际两轮HTTP分页探测（可新增受控产品/收款时间夹具但不可修改共享预览）；再跑既有独立final全场景两轮/DB/质量，保留原输出到evidence/independent-testing-release。测试完成后新独立验收才能开始evidence/independent-acceptance-release。不提交不发布不代签；整题外部门槛不变。生产代码暂停修改，文档与交付可能更新。
