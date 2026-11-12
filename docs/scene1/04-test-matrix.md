> 0.2：以下是逐字段计划，执行证据见apps/scene1/evidence。矩阵未逐项验证的条款仍不得视为通过；已有单元/HTTP回归不等于全部256字段反例。

# 逐字段、逐接口与全流程测试矩阵（计划，尚未执行）

版本0.1，2026-11-12。以下测试ID是本地检查编号，不能当飞书工作项ID。测试角色独立读取原题、目标代码、确认清单；设计建议待审核，不因测试写好就视作已实现或已通过。

## 测试层次与共同断言

| 层次 | 必须验证 | 证据 |
| --- | --- | --- |
| 单元 | 纯规则、状态转换、金额计算、防越权、幂等决策、失败/未知处理、签名canonical | 命令/输出、断言、原始unit覆盖率及整体/核心包报告 |
| DB集成 | 所有字段类型/约束/索引/外键/迁移、事务回滚、唯一冲突、跨表语义、库存/资金守恒 | 隔离MySQL8真实schema及查询结果，不能只mock |
| HTTP接口 | 完整路由/middleware/认证+DB+独立HTTP模拟渠道 | 请求/响应、request_id、状态码、DB事实、渠道事实 |
| 并发 | 真实请求同步竞争，锁/事务/唯一约束共同生效 | 每轮结果、随机种子/同步屏障、守恒、-race单独输出 |
| 重启/故障 | 超时/响应丢失/worker崩溃/DB失败/重启恢复 | 前后持久化结果、恢复任务/租约、无重复资金/库存 |
| 页面与最终验收 | 四工作台、多角色完整五场景、状态及失败可见 | 同版本页面、API及数据证据；正式独立验收另做 |

每个字段测试先确定规则适用性；服务端生成只读字段测不可注入、不可改写；FK/唯一/CHECK用真实DB反例；可空字段测NULL及合法非NULL，不以空字符串替代NULL。校验失败还应断言无非法副作用，并保留应存的通知/异常。

## 全部逐字段检查（256项，所有结果未执行）

每行是要求/测试计划，不是测试代码或通过声明。执行时另填05模板；表结构定义见01字段字典。auth_nonces结构须在商城和mock两侧分别验证。

| 编号 | 表.字段 | 类型 / 空值默认 | 取值与约束 | 必须验证的结果 |
| --- | --- | --- | --- | --- |
| FIELD-001 | accounts.id | uuid；非空，生成 | 账号ID；主键 | 不能由请求body替代当前身份 |
| FIELD-002 | accounts.login_name | varchar(64)；非空 | 3–64字符，仅教学账号；唯一 | 重复名称拒绝 |
| FIELD-003 | accounts.password_hash | text；非空 | Argon2id含盐哈希，禁止明文；不得返回API | 校验错误密码、不泄露哈希 |
| FIELD-004 | accounts.display_name | varchar(80)；非空 | 1–80字符；无 | 超长/空白拒绝 |
| FIELD-005 | accounts.role | varchar(16)；非空 | BUYER/OPERATOR/WAREHOUSE/SUPPORT；CHECK枚举 | 角色伪造拒绝 |
| FIELD-006 | accounts.enabled | boolean；非空，true | 停用后请求立即拒绝；无 | 已发token不能绕过停用 |
| FIELD-007 | accounts.created_at | timestamptz；非空 | UTC写入；无 | 返回RFC3339 |
| FIELD-008 | accounts.updated_at | timestamptz；非空 | UTC写入；无 | 变更不早于创建 |
| FIELD-009 | sessions.id | uuid；非空，生成 | 会话ID；主键 | 不可预测 |
| FIELD-010 | sessions.account_id | uuid；非空 | 所属账号；FK accounts | 不存在账号拒绝 |
| FIELD-011 | sessions.token_hash | char(64)；非空 | 随机256位令牌SHA256；唯一 | 仅创建时返回明文token，数据库无明文 |
| FIELD-012 | sessions.expires_at | timestamptz；非空 | 建议8小时会话时效；索引 | 到期立即401 |
| FIELD-013 | sessions.revoked_at | timestamptz；可空 | 登出/撤销时间；无 | 撤销后401 |
| FIELD-014 | sessions.created_at | timestamptz；非空 | 真实服务端时间；无 | 不得使用业务教学时钟延长认证 |
| FIELD-015 | products.id | uuid；非空，生成 | 商品ID；主键 | 固定两商品 |
| FIELD-016 | products.sku | varchar(32)；非空 | 教学商品编码；唯一 | 重复拒绝 |
| FIELD-017 | products.name | varchar(120)；非空 | 去首尾空白后1–120字符；无 | 空白/超长拒绝 |
| FIELD-018 | products.unit_price_cents | bigint；非空 | 1..1000000000，人民币分；CHECK | 零、负、小数、溢出拒绝 |
| FIELD-019 | products.sale_status | varchar(16)；非空，OFF_SHELF | ON_SHELF/OFF_SHELF；CHECK | 枚举外拒绝 |
| FIELD-020 | products.initial_quantity | bigint；非空 | 0..1000000，种子后不可改；CHECK | 运营不能修改初始基数 |
| FIELD-021 | products.available_quantity | bigint；非空 | 0..1000000；CHECK非负 | 下单/调整竞争不负数 |
| FIELD-022 | products.reserved_quantity | bigint；非空，0 | 活动订单占用；CHECK非负 | 与订单数量合计相等 |
| FIELD-023 | products.shipped_quantity | bigint；非空，0 | 已出库累计；CHECK非负 | 每单一次出库 |
| FIELD-024 | products.adjustment_net | bigint；非空，0 | 运营调整净额，可负；守恒CHECK | 初始+净额=可售+占用+出库 |
| FIELD-025 | products.version | bigint；非空，0 | 每次商品/库存变化递增；乐观锁 | 旧version修改返回409 |
| FIELD-026 | products.created_at | timestamptz；非空 | 创建UTC；无 | 稳定 |
| FIELD-027 | products.updated_at | timestamptz；非空 | 更新UTC；无 | 同事务更新 |
| FIELD-028 | orders.id | uuid；非空，生成 | 订单ID；主键 | 全链关联 |
| FIELD-029 | orders.order_no | varchar(40)；非空 | 不含个人信息的展示单号；唯一 | 不以可猜单号代替权限 |
| FIELD-030 | orders.buyer_id | uuid；非空 | 下单账号；FK accounts | 必须BUYER且由会话注入 |
| FIELD-031 | orders.product_id | uuid；非空 | 商品ID；FK products | 不可换商品 |
| FIELD-032 | orders.sku_snapshot | varchar(32)；非空 | 创建时SKU；不可变 | 后续商品变化不改 |
| FIELD-033 | orders.name_snapshot | varchar(120)；非空 | 创建时名称；不可变 | 调名不改 |
| FIELD-034 | orders.unit_price_cents | bigint；非空 | 创建时价格分；CHECK >0 | 客户端价格不能覆盖 |
| FIELD-035 | orders.quantity | smallint；非空 | 1或2；CHECK IN(1,2) | 0/3/负/小数拒绝 |
| FIELD-036 | orders.amount_cents | bigint；非空 | 快照单价乘数量；CHECK等式 | 旧价付款；溢出前检查 |
| FIELD-037 | orders.status | varchar(24)；非空，PENDING_PAYMENT | 七主状态见业务约束；CHECK | 禁止任意PATCH状态 |
| FIELD-038 | orders.normal_receipt_id | uuid；可空 | 唯一正常付款；唯一FK receipts | 一个正常付款只履约一次 |
| FIELD-039 | orders.active_application_id | uuid；可空 | 当前未拒绝/未结束退款申请；FK refund_applications | 同一时刻一个活动申请 |
| FIELD-040 | orders.close_reason | varchar(24)；可空 | BUYER_CANCELLED/TIMEOUT；CHECK状态配套 | 关闭必须有原因 |
| FIELD-041 | orders.expires_at | timestamptz；非空 | 创建业务时间+10分钟；索引(status,expires_at) | 恰好截止过期 |
| FIELD-042 | orders.paid_at | timestamptz；可空 | 商城确认正常支付时间；无 | 渠道时间不能代替 |
| FIELD-043 | orders.closed_at | timestamptz；可空 | 首次关闭时间；无 | 重复关闭不覆盖 |
| FIELD-044 | orders.refunded_at | timestamptz；可空 | 普通退款首次结算时间；无 | 异常退款不改订单为已退款 |
| FIELD-045 | orders.shipped_at | timestamptz；可空 | 发货时间；无 | 与shipments一致 |
| FIELD-046 | orders.version | bigint；非空，0 | 状态变更递增；无 | 竞争裁决可追溯 |
| FIELD-047 | orders.created_at | timestamptz；非空 | 创建业务时间；索引(buyer_id,created_at,id) | 排序稳定 |
| FIELD-048 | orders.updated_at | timestamptz；非空 | 更新业务时间；无 | 同事务更新 |
| FIELD-049 | inventory_ledger.id | uuid；非空，生成 | 流水ID；主键 | 唯一 |
| FIELD-050 | inventory_ledger.product_id | uuid；非空 | 关联商品；FK products | 不存在拒绝 |
| FIELD-051 | inventory_ledger.order_id | uuid；可空 | 占用/释放/发货关联订单；FK orders | ADJUST可空，其余必填 |
| FIELD-052 | inventory_ledger.refund_id | uuid；可空 | 普通退款释放关联退款；FK refunds | 退款释放必须可追溯 |
| FIELD-053 | inventory_ledger.actor_id | uuid；可空 | 操作人，系统关闭可空；FK accounts | 非系统调整必填 |
| FIELD-054 | inventory_ledger.event_type | varchar(24)；非空 | RESERVE/CLOSE_RELEASE/REFUND_RELEASE/SHIP/ADJUST；CHECK | 迟到退款无库存事件 |
| FIELD-055 | inventory_ledger.event_key | varchar(120)；非空 | 订单动作唯一键或调整请求键；唯一 | 同动作重放不多生效 |
| FIELD-056 | inventory_ledger.delta_available | bigint；非空 | 可售变化；CHECK事件向量 | 占用-q，释放+q |
| FIELD-057 | inventory_ledger.delta_reserved | bigint；非空 | 占用变化；CHECK事件向量 | 占用+q，释放/出库-q |
| FIELD-058 | inventory_ledger.delta_shipped | bigint；非空 | 出库变化；CHECK事件向量 | 仅SHIP为+q |
| FIELD-059 | inventory_ledger.delta_adjustment | bigint；非空 | 调整净额变化；CHECK事件向量 | 仅ADJUST与可售同值 |
| FIELD-060 | inventory_ledger.available_before | bigint；非空 | 可售前值；CHECK>=0 | 前后值匹配 |
| FIELD-061 | inventory_ledger.available_after | bigint；非空 | 可售后值；CHECK=before+delta | 不负数 |
| FIELD-062 | inventory_ledger.reserved_before | bigint；非空 | 占用前值；CHECK>=0 | 与商品事务一致 |
| FIELD-063 | inventory_ledger.reserved_after | bigint；非空 | 占用后值；CHECK=before+delta | 不负数 |
| FIELD-064 | inventory_ledger.shipped_before | bigint；非空 | 出库前值；CHECK>=0 | 与商品事务一致 |
| FIELD-065 | inventory_ledger.shipped_after | bigint；非空 | 出库后值；CHECK=before+delta | 不负数 |
| FIELD-066 | inventory_ledger.reason | varchar(500)；非空 | 原因1–500字符；无 | 调整必填，系统原因固定码说明 |
| FIELD-067 | inventory_ledger.created_at | timestamptz；非空 | 业务时间；索引(product_id,created_at,id) | 可重算余额 |
| FIELD-068 | payment_intents.id | uuid；非空，生成 | 支付意图ID；主键 | 重试原请求返回同一意图 |
| FIELD-069 | payment_intents.order_id | uuid；非空 | 关联订单；FK orders | 必须本人有效待付款 |
| FIELD-070 | payment_intents.provider_request_id | varchar(80)；非空 | 渠道支付幂等键；唯一 | 未知时沿用此键查询 |
| FIELD-071 | payment_intents.amount_cents | bigint；非空 | 订单应付快照；CHECK >0 | 不接受body金额 |
| FIELD-072 | payment_intents.currency | char(3)；非空，CNY | 币种；CHECK=CNY | 其他币种拒绝 |
| FIELD-073 | payment_intents.status | varchar(24)；非空，READY | READY/PENDING/SUCCEEDED/FAILED/UNKNOWN；CHECK | 成功不等于已获正常履约资格 |
| FIELD-074 | payment_intents.provider_txn_id | varchar(80)；可空 | 渠道交易ID；索引 | 最终以receipts唯一归属 |
| FIELD-075 | payment_intents.failure_code | varchar(64)；可空 | 安全原因码；无 | 无渠道密钥/堆栈 |
| FIELD-076 | payment_intents.last_queried_at | timestamptz；可空 | 最后查询业务时间；无 | 未知可查询 |
| FIELD-077 | payment_intents.created_at | timestamptz；非空 | 业务时间；索引(order_id,created_at) | 保留历史 |
| FIELD-078 | payment_intents.updated_at | timestamptz；非空 | 业务时间；无 | 状态更新可追溯 |
| FIELD-079 | receipts.id | uuid；非空，生成 | 收款ID；主键 | 退款依据 |
| FIELD-080 | receipts.provider | varchar(24)；非空，MOCK | 渠道名；联合唯一键组成 | 渠道身份独立 |
| FIELD-081 | receipts.provider_txn_id | varchar(80)；非空 | 渠道交易ID；唯一(provider,provider_txn_id) | 跨订单重放不改归属 |
| FIELD-082 | receipts.external_order_ref | varchar(80)；非空 | 渠道原始订单引用；不可变 | 未知订单也保留原引用 |
| FIELD-083 | receipts.order_id | uuid；可空 | 商城可核实订单；FK orders | 未知订单不伪造订单 |
| FIELD-084 | receipts.payment_intent_id | uuid；可空 | 关联商城意图；FK payment_intents | 外部注入可空 |
| FIELD-085 | receipts.amount_cents | bigint；非空 | 渠道核实实际金额；CHECK>0 | 金额异常仍按真实金额记录 |
| FIELD-086 | receipts.currency | char(3)；非空 | CNY；CHECK=CNY | 不转换币种 |
| FIELD-087 | receipts.classification | varchar(24)；非空 | NORMAL/LATE/EXTRA/AMOUNT_MISMATCH/UNKNOWN_ORDER；CHECK | 非NORMAL不能放行订单 |
| FIELD-088 | receipts.proof_type | varchar(16)；非空 | SIGNED_NOTIFY/CHANNEL_QUERY；CHECK | 验签失败不建立收款 |
| FIELD-089 | receipts.verified_at | timestamptz；非空 | 商城完成可信核验业务时间；无 | 晚到分类可验证 |
| FIELD-090 | receipts.provider_paid_at | timestamptz；非空 | 渠道付款时间，仅证据；无 | 不延长有效期 |
| FIELD-091 | receipts.created_at | timestamptz；非空 | 首次保存时间；无 | 重复不增加实收 |
| FIELD-092 | channel_notifications.id | uuid；非空，生成 | 接收记录ID；主键 | 重复通知也新增接收轨迹 |
| FIELD-093 | channel_notifications.kind | varchar(16)；非空 | PAYMENT/REFUND；CHECK | 不同协议分开校验 |
| FIELD-094 | channel_notifications.provider | varchar(24)；非空 | 渠道名；无 | 白名单 |
| FIELD-095 | channel_notifications.provider_event_id | varchar(80)；可空 | 渠道事件ID；非唯一索引 | 不能只凭事件ID决定资金幂等 |
| FIELD-096 | channel_notifications.external_order_ref | varchar(80)；可空 | 声称的订单引用；无 | 未核实不得信任 |
| FIELD-097 | channel_notifications.provider_txn_id | varchar(80)；可空 | 声称交易号；索引 | 冲突保留 |
| FIELD-098 | channel_notifications.provider_refund_id | varchar(80)；可空 | 声称退款号；索引 | 匹配attempt |
| FIELD-099 | channel_notifications.claimed_amount_cents | bigint；可空 | 成功解析的声称金额；无 | 非法负/溢出只在安全摘要记录 |
| FIELD-100 | channel_notifications.payload_hash | char(64)；非空 | 原始请求SHA256；无 | 不保留密钥 |
| FIELD-101 | channel_notifications.payload_redacted | jsonb；非空，{} | 有上限的脱敏要点；无 | 脱敏不损失业务关键标识 |
| FIELD-102 | channel_notifications.auth_valid | boolean；非空，false | 是否通过HMAC；无 | 失败不改业务 |
| FIELD-103 | channel_notifications.process_result | varchar(32)；非空 | ACCEPTED/DUPLICATE/INVALID_SIGNATURE/REPLAYED_SIGNATURE/AMOUNT_MISMATCH/UNKNOWN_ORDER/TXN_CONFLICT/INVALID_BODY/RESULT_CONFLICT/RETRYABLE；CHECK | 可查询处理原因 |
| FIELD-104 | channel_notifications.reason_code | varchar(64)；非空 | 安全错误码；无 | 错误结果可查 |
| FIELD-105 | channel_notifications.receipt_id | uuid；可空 | 关联可信收款；FK receipts | 无可信资金时空 |
| FIELD-106 | channel_notifications.refund_attempt_id | uuid；可空 | 关联退款尝试；FK refund_attempts | 与通知类型匹配 |
| FIELD-107 | channel_notifications.received_at | timestamptz；非空 | 首次接收业务时间；索引(kind,received_at,id) | 记录接收与裁决区别 |
| FIELD-108 | channel_notifications.processed_at | timestamptz；可空 | 业务处理完成时间；无 | 失败/待重试可解释 |
| FIELD-109 | auth_nonces.id | uuid；非空，生成 | 接收记录ID；主键 | 稳定 |
| FIELD-110 | auth_nonces.key_id | varchar(40)；非空 | 配置中已知签名方向密钥ID，不是密钥值；唯一键组成 | 未知key_id拒绝 |
| FIELD-111 | auth_nonces.nonce | varchar(64)；非空 | 16..64随机安全ASCII；唯一(key_id,nonce) | 并发重复只一条受理 |
| FIELD-112 | auth_nonces.expires_at | timestamptz；非空 | 真实时间窗口至少600秒后可清理；索引 | 时效窗口内不得提前清理 |
| FIELD-113 | auth_nonces.created_at | timestamptz；非空 | 真实服务端时间；无 | 业务教学时钟不影响 |
| FIELD-114 | refund_applications.id | uuid；非空，生成 | 申请ID；主键 | 拒绝后重提新ID |
| FIELD-115 | refund_applications.order_id | uuid；非空 | 订单；FK orders | 只限已付未发货 |
| FIELD-116 | refund_applications.buyer_id | uuid；非空 | 申请人；FK accounts | 必须订单本人 |
| FIELD-117 | refund_applications.reason | varchar(500)；非空 | 申请原因1–500字符；无 | 空白拒绝 |
| FIELD-118 | refund_applications.status | varchar(16)；非空，PENDING | PENDING/APPROVED/REJECTED；CHECK | 审核结论不可反转 |
| FIELD-119 | refund_applications.reviewer_id | uuid；可空 | 审核客服；FK accounts | 审核后必填SUPPORT |
| FIELD-120 | refund_applications.review_reason | varchar(500)；可空 | 同意/拒绝原因；无 | 审核时必填 |
| FIELD-121 | refund_applications.reviewed_at | timestamptz；可空 | 审核业务时间；无 | 重复不覆盖 |
| FIELD-122 | refund_applications.created_at | timestamptz；非空 | 申请业务时间；索引(order_id,created_at,id) | 历史保留 |
| FIELD-123 | refunds.id | uuid；非空，生成 | 逻辑退款ID；主键 | 重复发起返回本退款 |
| FIELD-124 | refunds.receipt_id | uuid；非空 | 可信实际收款；唯一FK receipts | 防重复整笔退款 |
| FIELD-125 | refunds.order_id | uuid；可空 | 订单；FK orders | 未知订单异常退款可空 |
| FIELD-126 | refunds.application_id | uuid；可空 | 普通售前已批准申请；唯一FK refund_applications | NORMAL必填 |
| FIELD-127 | refunds.anomaly_id | uuid；可空 | 异常款项核实记录；FK payment_anomalies | EXCEPTION必填 |
| FIELD-128 | refunds.kind | varchar(16)；非空 | NORMAL/EXCEPTION；CHECK | 库存动作必须按类型 |
| FIELD-129 | refunds.amount_cents | bigint；非空 | 对应收款全额；CHECK>0 | 等于可信收款金额且成功累计不超收款 |
| FIELD-130 | refunds.status | varchar(16)；非空，READY | READY/PROCESSING/UNKNOWN/FAILED/SUCCEEDED；CHECK | 失败与未知分离 |
| FIELD-131 | refunds.current_attempt_id | uuid；可空 | 当前尝试；FK refund_attempts | 与状态同事务 |
| FIELD-132 | refunds.created_by | uuid；非空 | 审核/发起客服；FK accounts | 不能买家直接生成 |
| FIELD-133 | refunds.success_at | timestamptz；可空 | 首次可信成功结算时间；无 | 成功不倒退 |
| FIELD-134 | refunds.settled_at | timestamptz；可空 | 本地退款/库存结算完成时间；无 | 和成功记账同一事务 |
| FIELD-135 | refunds.created_at | timestamptz；非空 | 业务时间；索引(status,created_at,id) | 可待办恢复 |
| FIELD-136 | refunds.updated_at | timestamptz；非空 | 业务时间；无 | 一致 |
| FIELD-137 | refund_attempts.id | uuid；非空，生成 | 尝试ID；主键 | 与逻辑退款分离 |
| FIELD-138 | refund_attempts.refund_id | uuid；非空 | 逻辑退款；FK refunds | 存在性 |
| FIELD-139 | refund_attempts.attempt_no | integer；非空 | 从1递增；唯一(refund_id,attempt_no) | 并发重试不创建两条 |
| FIELD-140 | refund_attempts.provider_request_id | varchar(80)；非空 | 渠道请求幂等键；唯一 | 网络重发沿用，明确失败才新尝试 |
| FIELD-141 | refund_attempts.provider_refund_id | varchar(80)；可空 | 渠道退款号；唯一（非空） | 回报精确匹配 |
| FIELD-142 | refund_attempts.status | varchar(16)；非空，READY | READY/PROCESSING/UNKNOWN/FAILED/SUCCEEDED；CHECK | 未知不能转READY盲重发 |
| FIELD-143 | refund_attempts.failure_code | varchar(64)；可空 | 渠道明确失败/网络错误原因；无 | HTTP超时不当FAILED |
| FIELD-144 | refund_attempts.proof_redacted | jsonb；非空，{} | 可信查询/通知摘要；无 | 终态冲突留异常 |
| FIELD-145 | refund_attempts.sent_at | timestamptz；可空 | 首次发送时间；无 | 发送前先持久化 |
| FIELD-146 | refund_attempts.resolved_at | timestamptz；可空 | 可信终态时间；无 | 失败终态可验证 |
| FIELD-147 | refund_attempts.last_queried_at | timestamptz；可空 | 最后查询时间；无 | 未知可恢复跟进 |
| FIELD-148 | refund_attempts.created_at | timestamptz；非空 | 业务时间；索引(refund_id,created_at,id) | 历史不覆盖 |
| FIELD-149 | shipments.id | uuid；非空，生成 | 发货ID；主键 | 唯一 |
| FIELD-150 | shipments.order_id | uuid；非空 | 订单；唯一FK orders | 最多一条 |
| FIELD-151 | shipments.carrier | varchar(80)；非空 | 承运方1–80字符；无 | 空白拒绝 |
| FIELD-152 | shipments.tracking_no | varchar(80)；非空 | 运单1–80字符，禁止控制字符；无 | 不全局唯一，不能误拦合法承运方单号 |
| FIELD-153 | shipments.operator_id | uuid；非空 | 仓库操作人；FK accounts | WAREHOUSE |
| FIELD-154 | shipments.shipped_at | timestamptz；非空 | 登记业务时间；无 | 与订单同事务 |
| FIELD-155 | payment_anomalies.id | uuid；非空，生成 | 异常ID；主键 | 不删除 |
| FIELD-156 | payment_anomalies.type | varchar(32)；非空 | LATE_PAYMENT/INVALID_SIGNATURE/AMOUNT_MISMATCH/UNKNOWN_ORDER/TXN_CONFLICT/EXTRA_PAYMENT/REFUND_RESULT_CONFLICT/INVALID_BODY；CHECK | 分类可筛选 |
| FIELD-157 | payment_anomalies.dedupe_key | varchar(160)；非空 | 按异常类型及业务事实去重；唯一 | 重复通知不造多个处理退款 |
| FIELD-158 | payment_anomalies.order_id | uuid；可空 | 可核实订单；FK orders | 未知可空 |
| FIELD-159 | payment_anomalies.receipt_id | uuid；可空 | 可信收款；FK receipts | 未核实可空 |
| FIELD-160 | payment_anomalies.refund_id | uuid；可空 | 关联退款；FK refunds | 冲突可定位 |
| FIELD-161 | payment_anomalies.first_notification_id | uuid；可空 | 首次证据；FK channel_notifications | 可回查 |
| FIELD-162 | payment_anomalies.status | varchar(24)；非空，OPEN | OPEN/VERIFIED/REFUNDING/RESOLVED；CHECK | 只能合法动作推进 |
| FIELD-163 | payment_anomalies.verification | varchar(24)；非空，UNVERIFIED | UNVERIFIED/FUNDS_CONFIRMED/NO_FUNDS/CONFLICT；CHECK | 不能手填金额伪造实收 |
| FIELD-164 | payment_anomalies.summary | varchar(500)；非空 | 安全摘要；无 | 敏感内容不入摘要 |
| FIELD-165 | payment_anomalies.resolved_reason | varchar(500)；可空 | 结案原因/证据说明；无 | 有实际款项未退不能结案 |
| FIELD-166 | payment_anomalies.resolved_by | uuid；可空 | 结案客服；FK accounts | 系统成功可沿用原发起人并标系统事件 |
| FIELD-167 | payment_anomalies.resolved_at | timestamptz；可空 | 结案业务时间；无 | 已处理仍可查询 |
| FIELD-168 | payment_anomalies.created_at | timestamptz；非空 | 业务时间；索引(status,type,created_at,id) | 活动列表 |
| FIELD-169 | payment_anomalies.updated_at | timestamptz；非空 | 业务时间；无 | 保留处理轨迹 |
| FIELD-170 | anomaly_actions.id | uuid；非空，生成 | 记录ID；主键 | 追加式 |
| FIELD-171 | anomaly_actions.anomaly_id | uuid；非空 | 异常；FK payment_anomalies | 关联必须存在 |
| FIELD-172 | anomaly_actions.actor_id | uuid；可空 | 客服账号/系统；FK accounts | 系统动作明确标识 |
| FIELD-173 | anomaly_actions.action | varchar(24)；非空 | QUERY/VERIFY/REQUEST_REFUND/RETRY/RESOLVE/CONFLICT；CHECK | 禁止通用任意改状态 |
| FIELD-174 | anomaly_actions.reason | varchar(500)；非空 | 1–500字符；无 | 客服动作原因必填 |
| FIELD-175 | anomaly_actions.evidence_redacted | jsonb；非空，{} | 核查请求/响应摘要和request_id；无 | 不含密钥 |
| FIELD-176 | anomaly_actions.from_status | varchar(24)；非空 | 动作前状态；无 | 与事实对应 |
| FIELD-177 | anomaly_actions.to_status | varchar(24)；非空 | 动作后状态；无 | 合法转换 |
| FIELD-178 | anomaly_actions.created_at | timestamptz；非空 | 业务时间；索引(anomaly_id,created_at,id) | 可顺序追溯 |
| FIELD-179 | idempotency_records.id | uuid；非空，生成 | 记录ID；主键 | 唯一 |
| FIELD-180 | idempotency_records.actor_id | uuid；非空 | 可信账号；FK accounts | 系统/渠道不用人类请求键 |
| FIELD-181 | idempotency_records.operation | varchar(80)；非空 | HTTP method+规范化路由/对象；唯一键组成 | 跨接口不混用 |
| FIELD-182 | idempotency_records.request_key | varchar(64)；非空 | Idempotency-Key，16–64 ASCII字符；唯一(actor_id,operation,request_key) | 同键换参409 |
| FIELD-183 | idempotency_records.request_hash | char(64)；非空 | 规范化body和对象ID哈希；无 | 身份来自服务端 |
| FIELD-184 | idempotency_records.resource_type | varchar(32)；非空 | 订单/退款等结果类型；无 | 可重读当前资源 |
| FIELD-185 | idempotency_records.resource_id | uuid；非空 | 业务资源ID；由服务校验关联 | 提交成功后能回读 |
| FIELD-186 | idempotency_records.http_status | smallint；非空 | 首次成功2xx响应码；CHECK 200..299 | 重试返回原资源及replayed=true |
| FIELD-187 | idempotency_records.created_at | timestamptz；非空 | 真实服务端时间；无 | 业务生命周期内不清理 |
| FIELD-188 | outbox_jobs.id | uuid；非空，生成 | 任务ID；主键 | 唯一 |
| FIELD-189 | outbox_jobs.job_key | varchar(160)；非空 | 稳定业务动作键；唯一 | 防重复任务 |
| FIELD-190 | outbox_jobs.kind | varchar(24)；非空 | PAYMENT_SEND/REFUND_SEND/PAYMENT_QUERY/REFUND_QUERY；CHECK | 只白名单处理器 |
| FIELD-191 | outbox_jobs.aggregate_id | uuid；非空 | 意图/尝试ID；按kind服务校验 | 不存任意执行指令 |
| FIELD-192 | outbox_jobs.status | varchar(16)；非空，READY | READY/RUNNING/DONE/RETRY；CHECK | 可恢复 |
| FIELD-193 | outbox_jobs.attempt_count | integer；非空，0 | 投递次数非负；CHECK>=0 | 有上限告警，不静默丢弃 |
| FIELD-194 | outbox_jobs.next_run_at | timestamptz；非空 | 真实调度时间；索引(status,next_run_at) | 不受业务时钟回拨 |
| FIELD-195 | outbox_jobs.lease_until | timestamptz；可空 | 真实租约到期；无 | 崩溃过期可认领 |
| FIELD-196 | outbox_jobs.last_error_code | varchar(64)；可空 | 安全失败原因；无 | 不含连接串 |
| FIELD-197 | outbox_jobs.created_at | timestamptz；非空 | 真实时间；无 | 同业务事务入库 |
| FIELD-198 | outbox_jobs.updated_at | timestamptz；非空 | 真实时间；无 | 恢复可追溯 |
| FIELD-199 | audit_events.id | uuid；非空，生成 | 审计ID；主键 | 追加式 |
| FIELD-200 | audit_events.actor_id | uuid；可空 | 账号；系统/渠道可空；FK accounts | 身份可信 |
| FIELD-201 | audit_events.actor_kind | varchar(16)；非空 | USER/SYSTEM/CHANNEL；CHECK | 不得客户端任填 |
| FIELD-202 | audit_events.entity_type | varchar(32)；非空 | PRODUCT/ORDER/PAYMENT/REFUND/SHIPMENT/ANOMALY；CHECK | 可联查 |
| FIELD-203 | audit_events.entity_id | uuid；可空 | 可定位对象；按类型服务校验 | 未知对象可空 |
| FIELD-204 | audit_events.action | varchar(64)；非空 | 固定业务动作码；无 | 不接受任意SQL或状态改写 |
| FIELD-205 | audit_events.request_id | uuid；非空 | 服务端关联ID；索引 | 与HTTP响应关联 |
| FIELD-206 | audit_events.before_redacted | jsonb；非空，{} | 变更前关键值；无 | 脱敏 |
| FIELD-207 | audit_events.after_redacted | jsonb；非空，{} | 变更后关键值；无 | 可解释状态/金额/库存 |
| FIELD-208 | audit_events.reason | varchar(500)；非空 | 操作理由或系统原因；无 | 商品维护、审核、异常需原因 |
| FIELD-209 | audit_events.created_at | timestamptz；非空 | 业务时间；索引(entity_type,entity_id,created_at,id) | 留历史 |
| FIELD-210 | demo_clock.id | smallint；非空，1 | 唯一单行，固定1；主键及CHECK=1 | 禁止插第二行/删除后默默归零 |
| FIELD-211 | demo_clock.offset_seconds | bigint；非空，0 | 相对真实UTC的非负偏移；CHECK>=0 | 只前进，重启不归零 |
| FIELD-212 | demo_clock.version | bigint；非空，0 | 每次推进递增；并发条件更新 | 并发推进不丢更新 |
| FIELD-213 | demo_clock.updated_by | varchar(80)；非空 | 独立admin凭证的安全标识，非令牌值；无 | 不可由body伪造 |
| FIELD-214 | demo_clock.updated_at | timestamptz；非空 | 真实UTC；无 | 不使用已偏移业务时间 |
| FIELD-215 | mock.channel_payments.id | uuid；非空，生成 | 渠道内部ID；主键 | 独立数据库/独立schema账户 |
| FIELD-216 | mock.channel_payments.merchant_ref | varchar(40)；非空 | 配置的教学商城标识；唯一键组成 | 跨商户请求拒绝 |
| FIELD-217 | mock.channel_payments.request_id | varchar(80)；非空 | 商城支付幂等键；唯一(merchant_ref,request_id) | 同键换参409 |
| FIELD-218 | mock.channel_payments.order_ref | varchar(80)；非空 | 商城订单引用；不可变 | 查询返回原值 |
| FIELD-219 | mock.channel_payments.txn_id | varchar(80)；非空 | 渠道交易号；唯一 | 不同请求也不重复 |
| FIELD-220 | mock.channel_payments.amount_cents | bigint；非空 | 正整数人民币分；CHECK>0 | 超范围拒绝 |
| FIELD-221 | mock.channel_payments.currency | char(3)；非空，CNY | 币种；CHECK=CNY | 不支持币种拒绝 |
| FIELD-222 | mock.channel_payments.status | varchar(16)；非空 | PENDING/SUCCEEDED/FAILED；CHECK | 终态不可反转 |
| FIELD-223 | mock.channel_payments.paid_at | timestamptz；可空 | 成功业务时间；无 | 成功必填 |
| FIELD-224 | mock.channel_payments.created_at | timestamptz；非空 | 业务时间；无 | 持久化 |
| FIELD-225 | mock.channel_payments.updated_at | timestamptz；非空 | 业务时间；无 | 重启可查 |
| FIELD-226 | mock.channel_refunds.id | uuid；非空，生成 | 内部ID；主键 | 稳定 |
| FIELD-227 | mock.channel_refunds.merchant_ref | varchar(40)；非空 | 商城标识；联合唯一组成 | 身份绑定 |
| FIELD-228 | mock.channel_refunds.request_id | varchar(80)；非空 | 商城退款尝试幂等键；唯一(merchant_ref,request_id) | 重发不重复实退 |
| FIELD-229 | mock.channel_refunds.txn_id | varchar(80)；非空 | 原成功交易；FK channel_payments.txn_id | 只退本商户收款 |
| FIELD-230 | mock.channel_refunds.refund_id | varchar(80)；非空 | 渠道退款号；唯一 | 通知与查询同号 |
| FIELD-231 | mock.channel_refunds.amount_cents | bigint；非空 | 整笔真实金额；CHECK>0 | 成功实退累计不得超过原收款 |
| FIELD-232 | mock.channel_refunds.status | varchar(16)；非空 | PENDING/SUCCEEDED/FAILED；CHECK | 明确失败不能事后变成功 |
| FIELD-233 | mock.channel_refunds.failure_code | varchar(64)；可空 | 明确失败码；无 | 可触发首败再成功 |
| FIELD-234 | mock.channel_refunds.refunded_at | timestamptz；可空 | 成功业务时间；无 | 成功必填 |
| FIELD-235 | mock.channel_refunds.created_at | timestamptz；非空 | 业务时间；无 | 重启可查 |
| FIELD-236 | mock.channel_refunds.updated_at | timestamptz；非空 | 业务时间；无 | 同键结果稳定 |
| FIELD-237 | mock.notification_jobs.id | uuid；非空，生成 | 任务ID；主键 | 稳定 |
| FIELD-238 | mock.notification_jobs.kind | varchar(16)；非空 | PAYMENT/REFUND；CHECK | 签名协议一致 |
| FIELD-239 | mock.notification_jobs.resource_ref | varchar(80)；非空 | txn_id或refund_id；服务校验 | 查询得到原事实 |
| FIELD-240 | mock.notification_jobs.event_id | varchar(80)；非空 | 稳定事件号；唯一 | 重复投递用同event_id |
| FIELD-241 | mock.notification_jobs.deliver_after | timestamptz；非空 | 真实调度时间；索引 | 显式教学延迟 |
| FIELD-242 | mock.notification_jobs.remaining_deliveries | integer；非空 | 0..20；CHECK | 支持重复次数，上限防误发洪泛 |
| FIELD-243 | mock.notification_jobs.status | varchar(16)；非空 | READY/RUNNING/DONE/RETRY；CHECK | 可恢复 |
| FIELD-244 | mock.notification_jobs.lease_until | timestamptz；可空 | 真实租约；无 | 重启恢复 |
| FIELD-245 | mock.notification_jobs.last_http_status | smallint；可空 | 最近商城响应；无 | 5xx可重试 |
| FIELD-246 | mock.notification_jobs.created_at | timestamptz；非空 | 真实时间；无 | 投递轨迹 |
| FIELD-247 | mock.simulation_rules.id | uuid；非空，生成 | 规则ID；主键 | 稳定 |
| FIELD-248 | mock.simulation_rules.target_order_ref | varchar(80)；非空 | 已知商城订单引用，发送前可配置；索引 | 只匹配明确订单，不全局污染并发 |
| FIELD-249 | mock.simulation_rules.target_request_id | varchar(80)；可空 | 进一步限定已知意图/尝试请求键；索引 | 非空时必须同时匹配 |
| FIELD-250 | mock.simulation_rules.attempt_no | integer；可空 | 进一步限定退款第几次尝试，>=1；CHECK | 可预设首次失败第二次成功 |
| FIELD-251 | mock.simulation_rules.operation | varchar(16)；非空 | PAYMENT/REFUND/NOTIFY；CHECK | 白名单 |
| FIELD-252 | mock.simulation_rules.mode | varchar(32)；非空 | SUCCESS/EXPLICIT_FAIL/TIMEOUT_AFTER_SUCCESS/PENDING/DELAY_NOTIFY/DUPLICATE_NOTIFY；CHECK | 拒绝任意程序/URL |
| FIELD-253 | mock.simulation_rules.delay_ms | integer；非空，0 | 0..600000；CHECK | 教学可控上限 |
| FIELD-254 | mock.simulation_rules.repeat_count | integer；非空，1 | 1..20；CHECK | 不影响真实业务幂等 |
| FIELD-255 | mock.simulation_rules.remaining_uses | integer；非空，1 | 1..20；CHECK | 原子消费 |
| FIELD-256 | mock.simulation_rules.created_at | timestamptz；非空 | 真实时间；无 | 保留配置证据 |

## 全部逐接口检查（48项，所有结果未执行）

每个接口均验证03契约声明的完整请求/响应字段、成功状态、400/401/403/404/409/503适用分支、权限/对象归属、幂等/非法状态/DB副作用和响应脱敏。没有该分支时写明确依据，不强行造无意义用例，也不能把必做缺失写“不适用”。

| 编号 | 接口 | 调用方 | 额外必须覆盖 |
| --- | --- | --- | --- |
| HTTP-API01 | POST /api/v1/auth/login | 匿名 | 正确/错误/停用/超长/重复登录；只返回安全Account |
| HTTP-API02 | GET /api/v1/auth/me | 所有已登录角色 | 缺token、过期、撤销、伪造、改角色/用户ID |
| HTTP-API03 | POST /api/v1/auth/logout | 所有已登录角色 | 撤销即时生效；不把密码/token回显 |
| HTTP-API04 | GET /api/v1/products | BUYER | 下架隐藏、售罄可见、稳定分页、非买家403 |
| HTTP-API05 | GET /api/v1/buyer/orders | BUYER | 本人/他人隔离、非法status/分页、到期状态说明 |
| HTTP-API06 | POST /api/v1/buyer/orders | BUYER | 缺货/下架/所有非法quantity；20并发；同键并发/换参；落库失败回滚 |
| HTTP-API07 | GET /api/v1/buyer/orders/{order_id} | BUYER本人 | 越权详情/运单/收退款隔离；重启回读；过期旧状态不可付 |
| HTTP-API08 | POST /api/v1/buyer/orders/{order_id}/cancel | BUYER本人 | 重复关闭、跨人、付款竞争、超时竞争；库存一次 |
| HTTP-API09 | POST /api/v1/buyer/orders/{order_id}/payments | BUYER本人 | 过期/关闭/已付拒绝；同键/不同键并发不重复扣款；响应丢失恢复 |
| HTTP-API10 | POST /api/v1/buyer/payments/{payment_id}/query | BUYER本人 | 未知仍未知/成功/明确失败；不会延长到期或新扣款 |
| HTTP-API11 | POST /api/v1/buyer/orders/{order_id}/refund-applications | BUYER本人 | 重复、重提、已发货/待付款拒绝；申请与发货并发唯一结果 |
| HTTP-API12 | GET /api/v1/warehouse/orders | WAREHOUSE | 被冻结/已发货不列；跨角色403；旧页面操作仍重查 |
| HTTP-API13 | POST /api/v1/warehouse/orders/{order_id}/shipment | WAREHOUSE | 必填/控制字符/超长、重复、新参数覆盖拒绝、申请竞争 |
| HTTP-API14 | GET /api/v1/support/refund-applications | SUPPORT | 筛选历史、分页、越权、用户自报role无效 |
| HTTP-API15 | POST /api/v1/support/refund-applications/{application_id}/review | SUPPORT | 双客服/同意拒绝竞争；原因空/非法decision；旧申请不能影响新申请 |
| HTTP-API16 | GET /api/v1/support/refunds | SUPPORT | 失败与未知区分；整笔计数不按attempt累加 |
| HTTP-API17 | POST /api/v1/support/refunds/{refund_id}/retry | SUPPORT | 失败重试成功、未知拒绝、重复重试、旧回报竞争不多退 |
| HTTP-API18 | POST /api/v1/support/refunds/{refund_id}/query | SUPPORT | 未知维持冻结；确认成功只结算一次；确认失败才允许retry |
| HTTP-API19 | GET /api/v1/support/payment-anomalies | SUPPORT | 迟到/验签失败/金额不符/未知/冲突均可查；不直接改状态消失 |
| HTTP-API20 | GET /api/v1/support/payment-anomalies/{anomaly_id} | SUPPORT | 原始关键标识可查但无密钥、token和未脱敏body |
| HTTP-API21 | POST /api/v1/support/payment-anomalies/{anomaly_id}/verify | SUPPORT | 恶意未签通知不能任填退款；正常迟到可信核实；查询未知/错商户 |
| HTTP-API22 | POST /api/v1/support/payment-anomalies/{anomaly_id}/refund | SUPPORT | 未核实拒绝；重复返回同退款；迟到/未知订单可信资金处理；库存不再释放 |
| HTTP-API23 | POST /api/v1/support/payment-anomalies/{anomaly_id}/resolve | SUPPORT | 写忽略不能抹异常；资金未退拒绝；历史保留 |
| HTTP-API24 | GET /api/v1/support/notifications | SUPPORT | 重放有接收轨迹，无资金重复；无效body记录；分页及权限 |
| HTTP-API25 | GET /api/v1/operator/products | OPERATOR | 与流水、订单占用一致；其他角色403 |
| HTTP-API26 | PATCH /api/v1/operator/products/{product_id} | OPERATOR | 缺字段/非法价格/旧version/调价下架与下单竞争；快照不变 |
| HTTP-API27 | POST /api/v1/operator/products/{product_id}/inventory-adjustments | OPERATOR | 负库存拒绝、同键重复、原因空、与下单并发守恒 |
| HTTP-API28 | GET /api/v1/operator/orders | OPERATOR | 联查筛选、无敏感数据、分页 |
| HTTP-API29 | GET /api/v1/operator/orders/{order_id}/reconciliation | OPERATOR | 正常、退款、迟到、重复、未知、失败明细汇总一致 |
| HTTP-API30 | GET /api/v1/operator/summary | OPERATOR | 不按通知条数累加；未知不当已退；下钻金额一致 |
| HTTP-API31 | POST /api/v1/channel/payment-notifications | 模拟渠道HMAC | 重复、错签/重放时间、错金额、未知订单、交易跨单、不同交易同单、迟到、取消竞争 |
| HTTP-API32 | POST /api/v1/channel/refund-notifications | 模拟渠道HMAC | 重复成功/失败、旧尝试、错金额/身份/收款、回报与query并发 |
| HTTP-API33 | GET /health/live | 无认证（仅必要信息） | 响应快且不泄露配置 |
| HTTP-API34 | GET /health/ready | 部署健康探测 | DB断开503、版本标识、不能代替业务冒烟 |
| HTTP-API35 | GET /api/v1/support/orders/{order_id} | SUPPORT | 客服能核实金额/状态；买家调用员工路由403；无敏感凭证 |
| HTTP-API36 | GET /api/v1/operator/receipts | OPERATOR | 总额与分页明细一致，异常和正常分类，未知订单也不丢记录 |
| HTTP-API37 | GET /api/v1/operator/refunds | OPERATOR | 成功金额一致，失败未知不能算实退，角色只读 |
| HTTP-API38 | GET /api/v1/operator/payment-anomalies | OPERATOR | 异常汇总数量与列表一致，不修改状态、不泄密 |
| HTTP-API39 | GET /api/v1/operator/payment-anomalies/{anomaly_id} | OPERATOR | 明细/汇总可追溯；运营不能借查询权限审核/退款/结案 |
| HTTP-MOCK01 | POST /mock/v1/payments | 商城服务HMAC | 渠道实际扣一次、重启可查、商城不能直接写渠道DB |
| HTTP-MOCK02 | GET /mock/v1/payments/by-request/{request_id} | 商城服务HMAC | 未知/成功/失败/错商户/查询超时 |
| HTTP-MOCK03 | GET /mock/v1/transactions/{txn_id} | 商城服务HMAC | 伪造通知/不存在/错商户不变实收 |
| HTTP-MOCK04 | POST /mock/v1/refunds | 商城服务HMAC | 首次失败后成功、超时但实退成功、重发不多退/超原额拒绝 |
| HTTP-MOCK05 | GET /mock/v1/refunds/by-request/{request_id} | 商城服务HMAC | 成功/失败/PENDING/未找到/网络超时 |
| HTTP-MOCK06 | POST /mock/admin/rules | 教学开关+独立admin令牌 | 开关关闭404、普通token403、非法模式/值拒绝，不暴露签名密钥 |
| HTTP-MOCK07 | POST /mock/admin/notifications/{event_id}/replay | 教学开关+独立admin令牌 | 重复/迟到可演示；任意callback_url拒绝、超范围拒绝 |
| HTTP-DEMO01 | POST /internal/demo/clock/advance | 仅教学开关+独立admin令牌 | 10分钟前/正好/后边界，重启/多实例统一，并发推进不丢更新；默认真实10分钟 |
| HTTP-DEMO02 | GET /internal/demo/clock | 仅教学开关+模拟渠道服务HMAC或独立admin令牌 | 多进程偏移一致，重启保留，鉴权/教学开关；时钟不可由客户端回拨 |

## 五组完整工作场景

| 编号 | 多角色实际步骤 | 最终断言 |
| --- | --- | --- |
| SC01 | 运营上架A→本人买2→模拟付款→有效通知→仓库填承运/运单→本人查询→运营下钻 | 金额20000分；可售3、占用0、出库2；实收20000、退款0；运单只一次 |
| SC02 | 隔离seed A=5→20不同请求/键各1件同步下单→部分主动取消/超时→其他买家新键购买释放商品 | 无释放穿插时恰好5成功15缺货；释放一次，新单可用，最终守恒，无负库存 |
| SC03 | 本人付款→整单申请→旧仓库页尝试发货失败→客服批准→渠道明确首次失败→客服重试成功→买家/运营核对 | 失败与未知都不发货/不放库存；成功实退一次、正常库存恢复一次，原因/历次尝试保留 |
| SC04 | 订单先超时或取消关闭→释放商品可被别人购买→迟到可信成功通知→客服异常列表核实→退款→运营核对 | 旧单保持CLOSED；一收一退；迟到收款及退款无库存动作；无重复释放/退款 |
| SC05 | 退款申请与发货并发；重复支付/退款通知；买家B读/取消/退A单，买家调用员工API | 单订单竞争只一合法结果；重复不多记款/退款/库存/发货；越权无数据泄露或副作用 |

## 关键边界、竞争和故障清单

| 编号 | 输入/时序 | 预期 |
| --- | --- | --- |
| EDGE01 | expires_at前1微秒、正好、后1微秒；过期扫描故意未跑 | 仅截止前且仍待付款可正常履约，其余关闭+异常可信款，不受客户端/渠道时间控制 |
| EDGE02 | 下单后调价/下架，再付款或普通退款 | 快照价履约；普通退款只恢复数量，不自动上架 |
| EDGE03 | 同渠道交易通知另一订单/不同金额，或同单另一成功交易 | 归属不覆盖；可信额外/差额款列异常，不二次发货，不直接按声称金额退款 |
| EDGE04 | 退款驳回→重提；旧审核重放；并发同意/拒绝 | 新历史冻结；旧结论不改；一申请一结论一逻辑退款 |
| EDGE05 | 普通退款失败→UNKNOWN→查询SUCCESS；期间反复点击retry | UNKNOWN不新尝试、不发货、不释放；可信成功仅一次结算 |
| EDGE06 | 旧失败回报晚于成功，旧失败attempt出现矛盾成功 | 不倒退、不多退；冲突保留并暂停后续退款，可信查询核对真实总额 |
| EDGE07 | 发货缺字段/重复/更换运单；已发货申请售前退 | 拒绝非法及二次登记，原运单不覆盖，无退款/库存副作用 |
| EDGE08 | 运营可售负调整超过余额；与下单/改价并发 | 不改占用、不负库存；合法快照和流水守恒 |
| CON01 | 付款确认vs取消/超时关闭，20轮同步竞争 | 待发货占货或关闭+异常收款，不能释放后发货 |
| CON02 | 退款申请vs发货，20轮同步竞争 | 仅申请成功且发货拒绝，或发货成功且申请拒绝 |
| CON03 | 同幂等键并发/换参；重复审核/退款重试/回调与查询 | 同事实仅一次副作用，换参409；活动尝试最多一笔 |
| FAULT01 | 渠道支付/退款已成功但响应超时 | 本地显示待确认，原请求查回可信终态，不重新实际扣/退款 |
| FAULT02 | 业务事务在流水/状态/幂等/审计任一步注入DB失败 | 整体回滚，余额和事实一致；必要接收/异常记录独立保留，返回可重试错误 |
| FAULT03 | DB已提交但HTTP响应丢失 | 同键重试回原资源，不重复占货/退款/发货 |
| FAULT04 | worker发送前/发送后崩溃，服务重启/租约到期 | outbox恢复同请求键；成功事实不丢，无多退多释放 |
| SEC01 | 伪token/改buyer_id/角色字段/跨人对象；枚举错、SQL/XSS、超大body | 鉴权/归属拒绝或校验拒绝，无泄密、副作用；页面转义 |
| SEC02 | HMAC错body/path/query/币种/商户/时间/nonce，签名正确但业务归属错 | 鉴权与业务校验都生效；处理结果可查，错误不计资金 |
| SEC03 | 普通业务token调用教学规则/时钟/重放；关闭教学开关 | 403或404，不能强行成功/重置/任意回调 |
| REC01 | 订单/退款失败/未知/发货/异常记录持久化后重启 | 所有事实可查；到期可恢复，未知仍未知且可查；守恒一致 |
| REC02 | 实收/实退汇总含重复通知、未知/失败退款、迟到实收、未签通知 | 一致快照，正常/异常可信实收分列；只成功逻辑退款计实退；未知/未核实单列 |

## 原始验收条件与共通门槛

AC01–AC32、QA01–QA09完整快照见[source/04-验收条件.md](source/04-验收条件.md)，原题见[source/assignment.md](source/assignment.md)。逐条建立结果，不只挑成功路径。教学数据和时钟建议审定后与测试/演示保持一致。

共通10节必须另核对：Go/页面/DB/模拟与环境，阶段顺序与独立上下文，学生项目约束历史/实际加载，两个自编Skill及全部使用总结，可见会话/结构化事件/AI说明，测试覆盖率质量，真实主分支门禁部署/恢复，MCP/dev分支/main保护/PR过程，方括号提交/真实工作项核验，学生视频及当天群提交。缺一关键门槛不能整题通过；本次尚无这些执行结果。
