# 数据表与逐字段约束（实施契约0.2）

日期：2026-11-12。数据库采用MySQL8/InnoDB；旧0.1已保存在history/0.1。256字段保留名称和语义；真实SQL见apps/scene1/migrations，采用用户本轮授权补齐的实施决定。原题未指定表名、类型、上限和索引，以下均为本次技术设计建议，受原题与U01–U06约束。审核清单见[00-review.md](00-review.md)。

## 全表统一规则

- 本文完整列出拟用的23张表，字段不允许以“等”省略。无特别说明均无隐式默认；所有外键ON DELETE RESTRICT，禁止级联删除业务历史。字段名snake_case，Go JSON一致，禁止存浮点金额。
- UUID由服务端生成，客户端不得指定主键、角色、状态、时间、付款金额、库存余额。枚举在SQL CHECK和服务层双重校验。空字符串不得代替NULL；文本先规范化再按字符数限制；UUID非法返回400。
- datetime(6)存UTC，API使用RFC3339 UTC。业务时钟用于订单有效期和业务事件；真实时钟用于认证、HMAC、租约调度。精度微秒，截止边界t>=expires_at即过期。
- SQL参数化；迁移显式建约束和索引；循环FK后置ALTER。跨表语义通过数据库事务+行锁/条件更新；不能声称单表CHECK可验证跨表值。
- 数据迁移、种子、回滚脚本与可重复初始化在apps/scene1/migrations/；模拟渠道独立数据库/独立schema和最小权限账号。没有真实数据库集成结果不能宣称约束有效。
- 下文最后一列是测试Agent必须验证的字段行为；进一步状态/竞争/故障见[业务约束](02-business-rules.md)与[测试矩阵](04-test-matrix.md)。

## 01. accounts

预置可信身份；不提供注册、角色自助提升。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 账号ID | 主键 | 不能由请求body替代当前身份 |
| login_name | varchar(64) | 非空 | 3–64字符，仅教学账号 | 唯一 | 重复名称拒绝 |
| password_hash | text | 非空 | Argon2id含盐哈希，禁止明文 | 不得返回API | 校验错误密码、不泄露哈希 |
| display_name | varchar(80) | 非空 | 1–80字符 | 无 | 超长/空白拒绝 |
| role | varchar(16) | 非空 | BUYER/OPERATOR/WAREHOUSE/SUPPORT | CHECK枚举 | 角色伪造拒绝 |
| enabled | boolean | 非空，true | 停用后请求立即拒绝 | 无 | 已发token不能绕过停用 |
| created_at | datetime(6) UTC | 非空 | UTC写入 | 无 | 返回RFC3339 |
| updated_at | datetime(6) UTC | 非空 | UTC写入 | 无 | 变更不早于创建 |

种子恰好3买家及运营/仓库/客服各1；商品B和员工数为设计建议A03。种子密码来自教学环境配置，不提交真实凭证。

## 02. sessions

不依赖客户端自报身份的随机令牌会话。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 会话ID | 主键 | 不可预测 |
| account_id | char(36) ASCII | 非空 | 所属账号 | FK accounts | 不存在账号拒绝 |
| token_hash | char(64) | 非空 | 随机256位令牌SHA256 | 唯一 | 仅创建时返回明文token，数据库无明文 |
| expires_at | datetime(6) UTC | 非空 | 建议8小时会话时效 | 索引 | 到期立即401 |
| revoked_at | datetime(6) UTC | 可空 | 登出/撤销时间 | 无 | 撤销后401 |
| created_at | datetime(6) UTC | 非空 | 真实服务端时间 | 无 | 不得使用业务教学时钟延长认证 |

业务教学时钟与认证时间分离；Authorization: Bearer，前端仅内存持有。刷新重新登录。

## 03. products

商品当前信息与可分配数量；余额同事务维护。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 商品ID | 主键 | 固定两商品 |
| sku | varchar(32) | 非空 | 教学商品编码 | 唯一 | 重复拒绝 |
| name | varchar(120) | 非空 | 去首尾空白后1–120字符 | 无 | 空白/超长拒绝 |
| unit_price_cents | bigint | 非空 | 1..1000000000，人民币分 | CHECK | 零、负、小数、溢出拒绝 |
| sale_status | varchar(16) | 非空，OFF_SHELF | ON_SHELF/OFF_SHELF | CHECK | 枚举外拒绝 |
| initial_quantity | bigint | 非空 | 0..1000000，种子后不可改 | CHECK | 运营不能修改初始基数 |
| available_quantity | bigint | 非空 | 0..1000000 | CHECK非负 | 下单/调整竞争不负数 |
| reserved_quantity | bigint | 非空，0 | 活动订单占用 | CHECK非负 | 与订单数量合计相等 |
| shipped_quantity | bigint | 非空，0 | 已出库累计 | CHECK非负 | 每单一次出库 |
| adjustment_net | bigint | 非空，0 | 运营调整净额，可负 | 守恒CHECK | 初始+净额=可售+占用+出库 |
| version | bigint | 非空，0 | 每次商品/库存变化递增 | 乐观锁 | 旧version修改返回409 |
| created_at | datetime(6) UTC | 非空 | 创建UTC | 无 | 稳定 |
| updated_at | datetime(6) UTC | 非空 | 更新UTC | 无 | 同事务更新 |

商品A=10000分/5件；B建议20000分/8件。以上数值上限为技术防溢出建议，不是原题既定限制；审核后写入配置/API。库存上限也限制运营正调整。

## 04. orders

单品订单快照；主状态为唯一业务裁决。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 订单ID | 主键 | 全链关联 |
| order_no | varchar(40) | 非空 | 不含个人信息的展示单号 | 唯一 | 不以可猜单号代替权限 |
| buyer_id | char(36) ASCII | 非空 | 下单账号 | FK accounts | 必须BUYER且由会话注入 |
| product_id | char(36) ASCII | 非空 | 商品ID | FK products | 不可换商品 |
| sku_snapshot | varchar(32) | 非空 | 创建时SKU | 不可变 | 后续商品变化不改 |
| name_snapshot | varchar(120) | 非空 | 创建时名称 | 不可变 | 调名不改 |
| unit_price_cents | bigint | 非空 | 创建时价格分 | CHECK >0 | 客户端价格不能覆盖 |
| quantity | smallint | 非空 | 1或2 | CHECK IN(1,2) | 0/3/负/小数拒绝 |
| amount_cents | bigint | 非空 | 快照单价乘数量 | CHECK等式 | 旧价付款；溢出前检查 |
| status | varchar(24) | 非空，PENDING_PAYMENT | 七主状态见业务约束 | CHECK | 禁止任意PATCH状态 |
| normal_receipt_id | char(36) ASCII | 可空 | 唯一正常付款 | 唯一FK receipts | 一个正常付款只履约一次 |
| active_application_id | char(36) ASCII | 可空 | 当前未拒绝/未结束退款申请 | FK refund_applications | 同一时刻一个活动申请 |
| close_reason | varchar(24) | 可空 | BUYER_CANCELLED/TIMEOUT | CHECK状态配套 | 关闭必须有原因 |
| expires_at | datetime(6) UTC | 非空 | 创建业务时间+10分钟 | 索引(status,expires_at) | 恰好截止过期 |
| paid_at | datetime(6) UTC | 可空 | 商城确认正常支付时间 | 无 | 渠道时间不能代替 |
| closed_at | datetime(6) UTC | 可空 | 首次关闭时间 | 无 | 重复关闭不覆盖 |
| refunded_at | datetime(6) UTC | 可空 | 普通退款首次结算时间 | 无 | 异常退款不改订单为已退款 |
| shipped_at | datetime(6) UTC | 可空 | 发货时间 | 无 | 与shipments一致 |
| version | bigint | 非空，0 | 状态变更递增 | 无 | 竞争裁决可追溯 |
| created_at | datetime(6) UTC | 非空 | 创建业务时间 | 索引(buyer_id,created_at,id) | 排序稳定 |
| updated_at | datetime(6) UTC | 非空 | 更新业务时间 | 无 | 同事务更新 |

主状态PENDING_PAYMENT/CLOSED/PENDING_SHIPMENT/REFUND_REVIEW/REFUND_PROCESSING/REFUNDED/SHIPPED。循环FK用后置ALTER迁移；active_application_id与status在同一事务维护，不使用没有恢复机制的延后补写。

## 05. inventory_ledger

追加式库存事实，不修改或删除历史。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 流水ID | 主键 | 唯一 |
| product_id | char(36) ASCII | 非空 | 关联商品 | FK products | 不存在拒绝 |
| order_id | char(36) ASCII | 可空 | 占用/释放/发货关联订单 | FK orders | ADJUST可空，其余必填 |
| refund_id | char(36) ASCII | 可空 | 普通退款释放关联退款 | FK refunds | 退款释放必须可追溯 |
| actor_id | char(36) ASCII | 可空 | 操作人，系统关闭可空 | FK accounts | 非系统调整必填 |
| event_type | varchar(24) | 非空 | RESERVE/CLOSE_RELEASE/REFUND_RELEASE/SHIP/ADJUST | CHECK | 迟到退款无库存事件 |
| event_key | varchar(120) | 非空 | 订单动作唯一键或调整请求键 | 唯一 | 同动作重放不多生效 |
| delta_available | bigint | 非空 | 可售变化 | CHECK事件向量 | 占用-q，释放+q |
| delta_reserved | bigint | 非空 | 占用变化 | CHECK事件向量 | 占用+q，释放/出库-q |
| delta_shipped | bigint | 非空 | 出库变化 | CHECK事件向量 | 仅SHIP为+q |
| delta_adjustment | bigint | 非空 | 调整净额变化 | CHECK事件向量 | 仅ADJUST与可售同值 |
| available_before | bigint | 非空 | 可售前值 | CHECK>=0 | 前后值匹配 |
| available_after | bigint | 非空 | 可售后值 | CHECK=before+delta | 不负数 |
| reserved_before | bigint | 非空 | 占用前值 | CHECK>=0 | 与商品事务一致 |
| reserved_after | bigint | 非空 | 占用后值 | CHECK=before+delta | 不负数 |
| shipped_before | bigint | 非空 | 出库前值 | CHECK>=0 | 与商品事务一致 |
| shipped_after | bigint | 非空 | 出库后值 | CHECK=before+delta | 不负数 |
| reason | varchar(500) | 非空 | 原因1–500字符 | 无 | 调整必填，系统原因固定码说明 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(product_id,created_at,id) | 可重算余额 |

CHECK向量：RESERVE=(-q,+q,0,0)，CLOSE/REFUND_RELEASE=(+q,-q,0,0)，SHIP=(0,-q,+q,0)，ADJUST=(d,0,0,d)。q取关联订单数量，由服务端验证；唯一键阻止重复生效。

## 06. payment_intents

商城侧支付发起及结果待确认，不代表实收。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 支付意图ID | 主键 | 重试原请求返回同一意图 |
| order_id | char(36) ASCII | 非空 | 关联订单 | FK orders | 必须本人有效待付款 |
| provider_request_id | varchar(80) | 非空 | 渠道支付幂等键 | 唯一 | 未知时沿用此键查询 |
| amount_cents | bigint | 非空 | 订单应付快照 | CHECK >0 | 不接受body金额 |
| currency | char(3) | 非空，CNY | 币种 | CHECK=CNY | 其他币种拒绝 |
| status | varchar(24) | 非空，READY | READY/PENDING/SUCCEEDED/FAILED/UNKNOWN | CHECK | 成功不等于已获正常履约资格 |
| provider_txn_id | varchar(80) | 可空 | 渠道交易ID | 索引 | 最终以receipts唯一归属 |
| failure_code | varchar(64) | 可空 | 安全原因码 | 无 | 无渠道密钥/堆栈 |
| last_queried_at | datetime(6) UTC | 可空 | 最后查询业务时间 | 无 | 未知可查询 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(order_id,created_at) | 保留历史 |
| updated_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 状态更新可追溯 |

每单最多一个非FAILED支付意图，可空生成列唯一索引WHERE status IN(READY,PENDING,SUCCEEDED,UNKNOWN)。明确失败可新建，UNKNOWN禁止第二次实际扣款（A12建议待审）。

## 07. receipts

经可信渠道确认的实际收款；通知失败不能写本表。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 收款ID | 主键 | 退款依据 |
| provider | varchar(24) | 非空，MOCK | 渠道名 | 联合唯一键组成 | 渠道身份独立 |
| provider_txn_id | varchar(80) | 非空 | 渠道交易ID | 唯一(provider,provider_txn_id) | 跨订单重放不改归属 |
| external_order_ref | varchar(80) | 非空 | 渠道原始订单引用 | 不可变 | 未知订单也保留原引用 |
| order_id | char(36) ASCII | 可空 | 商城可核实订单 | FK orders | 未知订单不伪造订单 |
| payment_intent_id | char(36) ASCII | 可空 | 关联商城意图 | FK payment_intents | 外部注入可空 |
| amount_cents | bigint | 非空 | 渠道核实实际金额 | CHECK>0 | 金额异常仍按真实金额记录 |
| currency | char(3) | 非空 | CNY | CHECK=CNY | 不转换币种 |
| classification | varchar(24) | 非空 | NORMAL/LATE/EXTRA/AMOUNT_MISMATCH/UNKNOWN_ORDER | CHECK | 非NORMAL不能放行订单 |
| proof_type | varchar(16) | 非空 | SIGNED_NOTIFY/CHANNEL_QUERY | CHECK | 验签失败不建立收款 |
| verified_at | datetime(6) UTC | 非空 | 商城完成可信核验业务时间 | 无 | 晚到分类可验证 |
| provider_paid_at | datetime(6) UTC | 非空 | 渠道付款时间，仅证据 | 无 | 不延长有效期 |
| created_at | datetime(6) UTC | 非空 | 首次保存时间 | 无 | 重复不增加实收 |

一个订单NORMAL收款最多一笔：可空生成列唯一索引order_id WHERE classification=NORMAL。冲突通知不覆盖原收款；额外收款经独立可信查询才入账并建异常。正常和异常实收均计实收，异常单列。

## 08. channel_notifications

支付/退款通知每次接收与查询结果，含无效及重复。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 接收记录ID | 主键 | 重复通知也新增接收轨迹 |
| kind | varchar(16) | 非空 | PAYMENT/REFUND | CHECK | 不同协议分开校验 |
| provider | varchar(24) | 非空 | 渠道名 | 无 | 白名单 |
| provider_event_id | varchar(80) | 可空 | 渠道事件ID | 非唯一索引 | 不能只凭事件ID决定资金幂等 |
| external_order_ref | varchar(80) | 可空 | 声称的订单引用 | 无 | 未核实不得信任 |
| provider_txn_id | varchar(80) | 可空 | 声称交易号 | 索引 | 冲突保留 |
| provider_refund_id | varchar(80) | 可空 | 声称退款号 | 索引 | 匹配attempt |
| claimed_amount_cents | bigint | 可空 | 成功解析的声称金额 | 无 | 非法负/溢出只在安全摘要记录 |
| payload_hash | char(64) | 非空 | 原始请求SHA256 | 无 | 不保留密钥 |
| payload_redacted | json | 非空，{} | 有上限的脱敏要点 | 无 | 脱敏不损失业务关键标识 |
| auth_valid | boolean | 非空，false | 是否通过HMAC | 无 | 失败不改业务 |
| process_result | varchar(32) | 非空 | ACCEPTED/DUPLICATE/INVALID_SIGNATURE/REPLAYED_SIGNATURE/AMOUNT_MISMATCH/UNKNOWN_ORDER/TXN_CONFLICT/INVALID_BODY/RESULT_CONFLICT/RETRYABLE | CHECK | 可查询处理原因 |
| reason_code | varchar(64) | 非空 | 安全错误码 | 无 | 错误结果可查 |
| receipt_id | char(36) ASCII | 可空 | 关联可信收款 | FK receipts | 无可信资金时空 |
| refund_attempt_id | char(36) ASCII | 可空 | 关联退款尝试 | FK refund_attempts | 与通知类型匹配 |
| received_at | datetime(6) UTC | 非空 | 首次接收业务时间 | 索引(kind,received_at,id) | 记录接收与裁决区别 |
| processed_at | datetime(6) UTC | 可空 | 业务处理完成时间 | 无 | 失败/待重试可解释 |

无效通知也持久化（请求体最大64KiB，只留安全摘要）；基础设施写库失败返回5xx要求重试，不回复已处理。该表不能由业务角色删除。

## 09. auth_nonces

HMAC防重放窗口记录；商城与mock各自存一份同结构。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 接收记录ID | 主键 | 稳定 |
| key_id | varchar(40) | 非空 | 配置中已知签名方向密钥ID，不是密钥值 | 唯一键组成 | 未知key_id拒绝 |
| nonce | varchar(64) | 非空 | 16..64随机安全ASCII | 唯一(key_id,nonce) | 并发重复只一条受理 |
| expires_at | datetime(6) UTC | 非空 | 真实时间窗口至少600秒后可清理 | 索引 | 时效窗口内不得提前清理 |
| created_at | datetime(6) UTC | 非空 | 真实服务端时间 | 无 | 业务教学时钟不影响 |

只有HMAC验证正确后才能占nonce，避免伪造请求污染；重复nonce返回401 REPLAYED_SIGNATURE，仍保留商城通知接收记录。渠道重投用新nonce同event_id；资金幂等另按交易/退款号。商城与mock分别用自己的auth_nonces表，隔离账户不能互写。

## 10. refund_applications

历次买家整单退款申请及一次性审核。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 申请ID | 主键 | 拒绝后重提新ID |
| order_id | char(36) ASCII | 非空 | 订单 | FK orders | 只限已付未发货 |
| buyer_id | char(36) ASCII | 非空 | 申请人 | FK accounts | 必须订单本人 |
| reason | varchar(500) | 非空 | 申请原因1–500字符 | 无 | 空白拒绝 |
| status | varchar(16) | 非空，PENDING | PENDING/APPROVED/REJECTED | CHECK | 审核结论不可反转 |
| reviewer_id | char(36) ASCII | 可空 | 审核客服 | FK accounts | 审核后必填SUPPORT |
| review_reason | varchar(500) | 可空 | 同意/拒绝原因 | 无 | 审核时必填 |
| reviewed_at | datetime(6) UTC | 可空 | 审核业务时间 | 无 | 重复不覆盖 |
| created_at | datetime(6) UTC | 非空 | 申请业务时间 | 索引(order_id,created_at,id) | 历史保留 |

可空生成列唯一索引order_id WHERE status=PENDING；批准后订单状态和active_application_id继续防止再申请；拒绝后解除活动指针，申请记录保留。不提供买家撤回（A06待审）。

## 11. refunds

每笔收款最多一笔整额逻辑退款，不等于每次渠道请求。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 逻辑退款ID | 主键 | 重复发起返回本退款 |
| receipt_id | char(36) ASCII | 非空 | 可信实际收款 | 唯一FK receipts | 防重复整笔退款 |
| order_id | char(36) ASCII | 可空 | 订单 | FK orders | 未知订单异常退款可空 |
| application_id | char(36) ASCII | 可空 | 普通售前已批准申请 | 唯一FK refund_applications | NORMAL必填 |
| anomaly_id | char(36) ASCII | 可空 | 异常款项核实记录 | FK payment_anomalies | EXCEPTION必填 |
| kind | varchar(16) | 非空 | NORMAL/EXCEPTION | CHECK | 库存动作必须按类型 |
| amount_cents | bigint | 非空 | 对应收款全额 | CHECK>0 | 等于可信收款金额且成功累计不超收款 |
| status | varchar(16) | 非空，READY | READY/PROCESSING/UNKNOWN/FAILED/SUCCEEDED | CHECK | 失败与未知分离 |
| current_attempt_id | char(36) ASCII | 可空 | 当前尝试 | FK refund_attempts | 与状态同事务 |
| created_by | char(36) ASCII | 非空 | 审核/发起客服 | FK accounts | 不能买家直接生成 |
| success_at | datetime(6) UTC | 可空 | 首次可信成功结算时间 | 无 | 成功不倒退 |
| settled_at | datetime(6) UTC | 可空 | 本地退款/库存结算完成时间 | 无 | 和成功记账同一事务 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(status,created_at,id) | 可待办恢复 |
| updated_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 一致 |

EXCEPTION永不操作库存，保持原关闭订单状态。SUCCEEDED必须settled_at非空；同事务完成款项结果、库存、订单、异常收尾。不同尝试不能让整笔退款多计。

## 12. refund_attempts

渠道尝试编号与终态证据；未知沿用原键查询。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 尝试ID | 主键 | 与逻辑退款分离 |
| refund_id | char(36) ASCII | 非空 | 逻辑退款 | FK refunds | 存在性 |
| attempt_no | integer | 非空 | 从1递增 | 唯一(refund_id,attempt_no) | 并发重试不创建两条 |
| provider_request_id | varchar(80) | 非空 | 渠道请求幂等键 | 唯一 | 网络重发沿用，明确失败才新尝试 |
| provider_refund_id | varchar(80) | 可空 | 渠道退款号 | 唯一（非空） | 回报精确匹配 |
| status | varchar(16) | 非空，READY | READY/PROCESSING/UNKNOWN/FAILED/SUCCEEDED | CHECK | 未知不能转READY盲重发 |
| failure_code | varchar(64) | 可空 | 渠道明确失败/网络错误原因 | 无 | HTTP超时不当FAILED |
| proof_redacted | json | 非空，{} | 可信查询/通知摘要 | 无 | 终态冲突留异常 |
| sent_at | datetime(6) UTC | 可空 | 首次发送时间 | 无 | 发送前先持久化 |
| resolved_at | datetime(6) UTC | 可空 | 可信终态时间 | 无 | 失败终态可验证 |
| last_queried_at | datetime(6) UTC | 可空 | 最后查询时间 | 无 | 未知可恢复跟进 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(refund_id,created_at,id) | 历史不覆盖 |

可空生成列唯一索引refund_id WHERE status IN(READY,PROCESSING,UNKNOWN)。模拟渠道对同请求键终态不可反转；旧失败尝试的矛盾成功不直接驱动新付款/库存，先冻结并可信核实。

## 13. shipments

人工一次发货登记；不实现物流跟踪/签收。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 发货ID | 主键 | 唯一 |
| order_id | char(36) ASCII | 非空 | 订单 | 唯一FK orders | 最多一条 |
| carrier | varchar(80) | 非空 | 承运方1–80字符 | 无 | 空白拒绝 |
| tracking_no | varchar(80) | 非空 | 运单1–80字符，禁止控制字符 | 无 | 不全局唯一，不能误拦合法承运方单号 |
| operator_id | char(36) ASCII | 非空 | 仓库操作人 | FK accounts | WAREHOUSE |
| shipped_at | datetime(6) UTC | 非空 | 登记业务时间 | 无 | 与订单同事务 |

校验待发货且无活动退款；锁内提交shipments、订单状态与库存SHIP流水；并发退款/发货仅一方成功。

## 14. payment_anomalies

异常持久待办；不能靠修改订单消除。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 异常ID | 主键 | 不删除 |
| type | varchar(32) | 非空 | LATE_PAYMENT/INVALID_SIGNATURE/AMOUNT_MISMATCH/UNKNOWN_ORDER/TXN_CONFLICT/EXTRA_PAYMENT/REFUND_RESULT_CONFLICT/INVALID_BODY | CHECK | 分类可筛选 |
| dedupe_key | varchar(160) | 非空 | 按异常类型及业务事实去重 | 唯一 | 重复通知不造多个处理退款 |
| order_id | char(36) ASCII | 可空 | 可核实订单 | FK orders | 未知可空 |
| receipt_id | char(36) ASCII | 可空 | 可信收款 | FK receipts | 未核实可空 |
| refund_id | char(36) ASCII | 可空 | 关联退款 | FK refunds | 冲突可定位 |
| first_notification_id | char(36) ASCII | 可空 | 首次证据 | FK channel_notifications | 可回查 |
| status | varchar(24) | 非空，OPEN | OPEN/VERIFIED/REFUNDING/RESOLVED | CHECK | 只能合法动作推进 |
| verification | varchar(24) | 非空，UNVERIFIED | UNVERIFIED/FUNDS_CONFIRMED/NO_FUNDS/CONFLICT | CHECK | 不能手填金额伪造实收 |
| summary | varchar(500) | 非空 | 安全摘要 | 无 | 敏感内容不入摘要 |
| resolved_reason | varchar(500) | 可空 | 结案原因/证据说明 | 无 | 有实际款项未退不能结案 |
| resolved_by | char(36) ASCII | 可空 | 结案客服 | FK accounts | 系统成功可沿用原发起人并标系统事件 |
| resolved_at | datetime(6) UTC | 可空 | 结案业务时间 | 无 | 已处理仍可查询 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(status,type,created_at,id) | 活动列表 |
| updated_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 保留处理轨迹 |

无可信订单/金额来源的伪造通知只能记录调查与查询结果，不给任意外部交易退款。异常退款仅允许模拟渠道确认本商城merchant_ref且对应真实交易，金额取渠道事实。

## 15. anomaly_actions

客服每次核查及系统退款收尾历史。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 记录ID | 主键 | 追加式 |
| anomaly_id | char(36) ASCII | 非空 | 异常 | FK payment_anomalies | 关联必须存在 |
| actor_id | char(36) ASCII | 可空 | 客服账号/系统 | FK accounts | 系统动作明确标识 |
| action | varchar(24) | 非空 | QUERY/VERIFY/REQUEST_REFUND/RETRY/RESOLVE/CONFLICT | CHECK | 禁止通用任意改状态 |
| reason | varchar(500) | 非空 | 1–500字符 | 无 | 客服动作原因必填 |
| evidence_redacted | json | 非空，{} | 核查请求/响应摘要和request_id | 无 | 不含密钥 |
| from_status | varchar(24) | 非空 | 动作前状态 | 无 | 与事实对应 |
| to_status | varchar(24) | 非空 | 动作后状态 | 无 | 合法转换 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(anomaly_id,created_at,id) | 可顺序追溯 |

资金未核实/退款未知时不得RESOLVED；退款成功由受控结算动作收尾，原异常和历史不消失。

## 16. idempotency_records

所有业务写请求去重，不能只靠页面防重。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 记录ID | 主键 | 唯一 |
| actor_id | char(36) ASCII | 非空 | 可信账号 | FK accounts | 系统/渠道不用人类请求键 |
| operation | varchar(80) | 非空 | HTTP method+规范化路由/对象 | 唯一键组成 | 跨接口不混用 |
| request_key | varchar(64) | 非空 | Idempotency-Key，16–64 ASCII字符 | 唯一(actor_id,operation,request_key) | 同键换参409 |
| request_hash | char(64) | 非空 | 规范化body和对象ID哈希 | 无 | 身份来自服务端 |
| resource_type | varchar(32) | 非空 | 订单/退款等结果类型 | 无 | 可重读当前资源 |
| resource_id | char(36) ASCII | 非空 | 业务资源ID | 由服务校验关联 | 提交成功后能回读 |
| http_status | smallint | 非空 | 首次成功2xx响应码 | CHECK 200..299 | 重试返回原资源及replayed=true |
| created_at | datetime(6) UTC | 非空 | 真实服务端时间 | 无 | 业务生命周期内不清理 |

同一数据库事务写入资源和幂等记录；并发同键通过唯一约束+整事务回滚重读，不能先扣库存再忽略冲突。业务拒绝不缓存为成功；事务提交成功响应丢失可恢复。登录/登出/渠道通知不使用该人类幂等表。

## 17. outbox_jobs

数据库可靠任务，覆盖批准后未发送及崩溃恢复。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 任务ID | 主键 | 唯一 |
| job_key | varchar(160) | 非空 | 稳定业务动作键 | 唯一 | 防重复任务 |
| kind | varchar(24) | 非空 | PAYMENT_SEND/REFUND_SEND/PAYMENT_QUERY/REFUND_QUERY | CHECK | 只白名单处理器 |
| aggregate_id | char(36) ASCII | 非空 | 意图/尝试ID | 按kind服务校验 | 不存任意执行指令 |
| status | varchar(16) | 非空，READY | READY/RUNNING/DONE/RETRY | CHECK | 可恢复 |
| attempt_count | integer | 非空，0 | 投递次数非负 | CHECK>=0 | 有上限告警，不静默丢弃 |
| next_run_at | datetime(6) UTC | 非空 | 真实调度时间 | 索引(status,next_run_at) | 不受业务时钟回拨 |
| lease_until | datetime(6) UTC | 可空 | 真实租约到期 | 无 | 崩溃过期可认领 |
| last_error_code | varchar(64) | 可空 | 安全失败原因 | 无 | 不含连接串 |
| created_at | datetime(6) UTC | 非空 | 真实时间 | 无 | 同业务事务入库 |
| updated_at | datetime(6) UTC | 非空 | 真实时间 | 无 | 恢复可追溯 |

任务租约领取事务与HTTP调用分离；调用外部时不得持有订单/商品行锁。超时重投同provider_request_id，只能查询或幂等重放同一请求，不建立新逻辑退款。

## 18. audit_events

商品维护及跨对象业务操作历史。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 审计ID | 主键 | 追加式 |
| actor_id | char(36) ASCII | 可空 | 账号；系统/渠道可空 | FK accounts | 身份可信 |
| actor_kind | varchar(16) | 非空 | USER/SYSTEM/CHANNEL | CHECK | 不得客户端任填 |
| entity_type | varchar(32) | 非空 | PRODUCT/ORDER/PAYMENT/REFUND/SHIPMENT/ANOMALY | CHECK | 可联查 |
| entity_id | char(36) ASCII | 可空 | 可定位对象 | 按类型服务校验 | 未知对象可空 |
| action | varchar(64) | 非空 | 固定业务动作码 | 无 | 不接受任意SQL或状态改写 |
| request_id | char(36) ASCII | 非空 | 服务端关联ID | 索引 | 与HTTP响应关联 |
| before_redacted | json | 非空，{} | 变更前关键值 | 无 | 脱敏 |
| after_redacted | json | 非空，{} | 变更后关键值 | 无 | 可解释状态/金额/库存 |
| reason | varchar(500) | 非空 | 操作理由或系统原因 | 无 | 商品维护、审核、异常需原因 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 索引(entity_type,entity_id,created_at,id) | 留历史 |

成功变更审计与业务同事务；拒绝/异常通知另存接收或安全事件，事务回滚不能顺带抹掉应保存的异常。

## 19. demo_clock

仅教学模式的统一持久化时钟；真实模式不依赖该表。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | smallint | 非空，1 | 唯一单行，固定1 | 主键及CHECK=1 | 禁止插第二行/删除后默默归零 |
| offset_seconds | bigint | 非空，0 | 相对真实UTC的非负偏移 | CHECK>=0 | 只前进，重启不归零 |
| version | bigint | 非空，0 | 每次推进递增 | 并发条件更新 | 并发推进不丢更新 |
| updated_by | varchar(80) | 非空 | 独立admin凭证的安全标识，非令牌值 | 无 | 不可由body伪造 |
| updated_at | datetime(6) UTC | 非空 | 真实UTC | 无 | 不使用已偏移业务时间 |

教学模式business_now=real_now+持久化offset；商城与mock均从相同ClockProvider取得偏移。mock通过固定HMAC GET /internal/demo/clock读取偏移后按同一算法取时；操作前刷新，不信客户端时间。不持锁发HTTP。测试注入同一Clock接口而不改业务判定。真实模式无需推进，默认10分钟。

## 20. mock.channel_payments

模拟渠道独立存储，不能直接写商城表。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 渠道内部ID | 主键 | 独立数据库/独立schema账户 |
| merchant_ref | varchar(40) | 非空 | 配置的教学商城标识 | 唯一键组成 | 跨商户请求拒绝 |
| request_id | varchar(80) | 非空 | 商城支付幂等键 | 唯一(merchant_ref,request_id) | 同键换参409 |
| order_ref | varchar(80) | 非空 | 商城订单引用 | 不可变 | 查询返回原值 |
| txn_id | varchar(80) | 非空 | 渠道交易号 | 唯一 | 不同请求也不重复 |
| amount_cents | bigint | 非空 | 正整数人民币分 | CHECK>0 | 超范围拒绝 |
| currency | char(3) | 非空，CNY | 币种 | CHECK=CNY | 不支持币种拒绝 |
| status | varchar(16) | 非空 | PENDING/SUCCEEDED/FAILED | CHECK | 终态不可反转 |
| paid_at | datetime(6) UTC | 可空 | 成功业务时间 | 无 | 成功必填 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 持久化 |
| updated_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 重启可查 |

渠道HTTP超时可以在已成功扣款后隐藏响应；可信查询仍返回真实终态。教学业务时间与商城统一，不采用渠道时间决定订单有效性。

## 21. mock.channel_refunds

每次商城退款尝试的稳定渠道结果。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 内部ID | 主键 | 稳定 |
| merchant_ref | varchar(40) | 非空 | 商城标识 | 联合唯一组成 | 身份绑定 |
| request_id | varchar(80) | 非空 | 商城退款尝试幂等键 | 唯一(merchant_ref,request_id) | 重发不重复实退 |
| txn_id | varchar(80) | 非空 | 原成功交易 | FK channel_payments.txn_id | 只退本商户收款 |
| refund_id | varchar(80) | 非空 | 渠道退款号 | 唯一 | 通知与查询同号 |
| amount_cents | bigint | 非空 | 整笔真实金额 | CHECK>0 | 成功实退累计不得超过原收款 |
| status | varchar(16) | 非空 | PENDING/SUCCEEDED/FAILED | CHECK | 明确失败不能事后变成功 |
| failure_code | varchar(64) | 可空 | 明确失败码 | 无 | 可触发首败再成功 |
| refunded_at | datetime(6) UTC | 可空 | 成功业务时间 | 无 | 成功必填 |
| created_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 重启可查 |
| updated_at | datetime(6) UTC | 非空 | 业务时间 | 无 | 同键结果稳定 |

新尝试只能在原尝试明确失败后出现；渠道也锁住原收款并校验成功累计金额，作为第二道防重退。不能把超时作为FAILED。

## 22. mock.notification_jobs

可延迟/重复投递，渠道通知可靠记录。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 任务ID | 主键 | 稳定 |
| kind | varchar(16) | 非空 | PAYMENT/REFUND | CHECK | 签名协议一致 |
| resource_ref | varchar(80) | 非空 | txn_id或refund_id | 服务校验 | 查询得到原事实 |
| event_id | varchar(80) | 非空 | 稳定事件号 | 唯一 | 重复投递用同event_id |
| deliver_after | datetime(6) UTC | 非空 | 真实调度时间 | 索引 | 显式教学延迟 |
| remaining_deliveries | integer | 非空 | 0..20 | CHECK | 支持重复次数，上限防误发洪泛 |
| status | varchar(16) | 非空 | READY/RUNNING/DONE/RETRY | CHECK | 可恢复 |
| lease_until | datetime(6) UTC | 可空 | 真实租约 | 无 | 重启恢复 |
| last_http_status | smallint | 可空 | 最近商城响应 | 无 | 5xx可重试 |
| created_at | datetime(6) UTC | 非空 | 真实时间 | 无 | 投递轨迹 |

通知目标固定商城配置的白名单回调URL，不接受浏览器传callback_url，防SSRF；每次投递重新签名timestamp/nonce，业务event_id不变。

## 23. mock.simulation_rules

仅教学控制面可写的有限故障脚本。

| 字段 | MySQL物理类型 | 空值 / 默认 | 字段含义与取值 | 约束 / 索引 | 测试要求 |
| --- | --- | --- | --- | --- | --- |
| id | char(36) ASCII | 非空，生成 | 规则ID | 主键 | 稳定 |
| target_order_ref | varchar(80) | 非空 | 已知商城订单引用，发送前可配置 | 索引 | 只匹配明确订单，不全局污染并发 |
| target_request_id | varchar(80) | 可空 | 进一步限定已知意图/尝试请求键 | 索引 | 非空时必须同时匹配 |
| attempt_no | integer | 可空 | 进一步限定退款第几次尝试，>=1 | CHECK | 可预设首次失败第二次成功 |
| operation | varchar(16) | 非空 | PAYMENT/REFUND/NOTIFY | CHECK | 白名单 |
| mode | varchar(32) | 非空 | SUCCESS/EXPLICIT_FAIL/TIMEOUT_AFTER_SUCCESS/PENDING/DELAY_NOTIFY/DUPLICATE_NOTIFY | CHECK | 拒绝任意程序/URL |
| delay_ms | integer | 非空，0 | 0..600000 | CHECK | 教学可控上限 |
| repeat_count | integer | 非空，1 | 1..20 | CHECK | 不影响真实业务幂等 |
| remaining_uses | integer | 非空，1 | 1..20 | CHECK | 原子消费 |
| created_at | datetime(6) UTC | 非空 | 真实时间 | 无 | 保留配置证据 |

教学控制端点须服务端教学开关+独立admin令牌；正常买家、运营、客服及仓库无权限修改模拟行为。生产模式关闭；测试采用隔离实例，不远程重置共享库。


## 必须核对的跨表关系

orders.normal_receipt_id必须指向同订单的NORMAL收款；refunds.NORMAL必须同订单、已批准application、相同receipt并全额；refunds.EXCEPTION必须指向已确认本商户真实资金的anomaly/receipt。refunds.current_attempt_id只能指向本refund；orders.active_application_id只能指向本单活动申请。外键无法表达的语义由锁内服务层验证，编写反例测试。

订单正常付款不减库存；EXCEPTION退款不写inventory_ledger。外部结果先持久化再结算时必须设计可恢复事务流程；推荐每次可信确认在单个结算事务完成。禁止靠定时修账掩盖已暴露的非法中间状态。

## 0.2物理映射及运行边界

MySQL8：uuid映射char(36) ascii_bin，timestamptz映射datetime(6)并强制UTC，jsonb映射JSON；业务字段不重命名。24业务表实例（nonce双侧），schema_migrations及mock.runtime_lock为已说明技术表，4个可空生成列只用于条件唯一。002增量补充CHECK/default/复合索引。教学写事务先锁时钟/渠道锁行，跨进程串行化以简化小规模教学竞争；外部HTTP在事务外，详见06。旧PostgreSQL表格说明已以本节及实际迁移替代。


2026-11-12账号维护补充：Seed的初始化配置要求至少12位；已有账号不覆盖。按用户要求，当前Demo预览账号经独立维护重置为六位登录密码，仅更新password_hash/updated_at并撤销会话，存储仍为Argon2id独立含盐哈希。登录接口Demo最低6位、非Demo最低8位。初始化配置不再是重置后的登录密码。
