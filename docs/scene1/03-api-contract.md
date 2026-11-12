# 接口契约与字段要求（实施契约0.2）

日期2026-11-12；48个接口已有路由实现，正式验证结果按evidence和独立报告，不以本声明代替验证。数据字典和业务约束是同一版本契约；变更后同步测试和页面。

## 通用协议与校验

- 商城/api/v1；JSON UTF-8，body最大64KiB；拒绝未知字段、重复JSON键、非法UTF-8/控制字符、错误类型、尾随JSON。所有path UUID严格校验，字符串trim后检长度，业务ID外部字段为1..80个安全ASCII字符，仅允许A-Z/a-z/0-9/点/下划线/连字符，禁止单独点或双点；请求键另有最短16位限制。未知订单引用是受限外部ID，不要求本地UUID。
- Money在JSON中为规范十进制整数字符串（例"10000"），无符号/小数/科学记数/前导零，1..int64最大；商品单价额外≤1000000000，订单由快照计算。汇总_cents均字符串，库存/quantity为JSON整数且校验安全范围；DB为bigint，不用float计算金额。amount_cents格式错误400；业务金额不匹配记录异常。
- 人类接口Authorization: Bearer随机会话token。角色由accounts取，对象归属由数据库取；请求中user_id、buyer_id、role、状态、时间不得冒充身份。运营筛选buyer_id只限API28。买家读/写他人单统一404，跨角色403，缺/过期token401；不存在资源404。
- 所有人类业务写动作（不含login/logout和只读GET）要求Idempotency-Key:16–64 ASCII字符。范围为actor+规范化method/route（含对象ID）+key；哈希规范化业务参数，换参409 IDEMPOTENCY_CONFLICT；同键成功重放返回原resource_id及当前可读事实，meta.replayed=true，不重做副作用。查询POST可重放已存在查询任务，不新退款。
- 成功包络：{data:DTO,meta:{request_id:UUID,replayed:boolean,server_time:UTC,business_time:UTC}}。错误包络：{error:{code:string,message:中文安全说明,retryable:boolean},meta:{request_id,server_time,business_time}}，不返回SQL/堆栈/凭证。login token仅首次返回，无日志。List的data为Page。
- Page={items:DTO[],next_cursor:string|null}；limit默认20，1..100；cursor不可伪造（签名或严格不可变编码游标），按created_at,id倒序稳定分页；新增数据不造成重复/遗漏已有区间。只接受每个接口声明的过滤参数。无结果200空items，非法cursor400。
- HTTP400 INVALID_ARGUMENT，401 UNAUTHENTICATED/INVALID_SIGNATURE，403 FORBIDDEN，404 NOT_FOUND，409 OUT_OF_STOCK/NOT_ON_SALE/STATE_CONFLICT/EXPIRED/ACTIVE_REFUND/SHIPMENT_EXISTS/ALREADY_REVIEWED/IDEMPOTENCY_CONFLICT/RESULT_UNKNOWN，429 RATE_LIMITED，503 DEPENDENCY_UNAVAILABLE/RETRYABLE_STORAGE。预期业务冲突不当500；可重试错误给安全提示。返回EXPIRED若需补关闭，关闭事务必须提交，不能随错误一起回滚。
- 查询GET不产生外部资金动作、不修改订单。worker负责到期关闭；写操作锁内发现到期先关闭释放，操作拒绝后事实仍应持久化。GET返回executable_actions依据服务端当前时间，不因status尚待付款而允许付费。

## DTO逐字段白名单

DTO是允许返回字段的完整白名单；不可直接序列化DB实体。下列money均Money字符串、时间UTC或null、ID均UUID。未声明字段不返回。[*]代表数组元素类型，不代表省略字段。

| DTO | 完整字段及类型 |
| --- | --- |
| Account | id:UUID, login_name:string, display_name:string, role:枚举；不返回password_hash/token_hash |
| Product | id:UUID, sku:string, name:string, unit_price_cents:Money, sale_status:枚举, available_quantity:number, reserved_quantity:number, shipped_quantity:number, initial_quantity:number, adjustment_net:number, version:number |
| OrderSummary | id:UUID, order_no:string, product_id:UUID, sku_snapshot:string, name_snapshot:string, unit_price_cents:Money, quantity:number, amount_cents:Money, status:订单枚举, created_at:UTC, expires_at:UTC, close_reason:string或null, payment_deadline_passed:boolean |
| OrderDetail | OrderSummary全部字段 + paid_at/closed_at/refunded_at/shipped_at:UTC或null, payment:PaymentIntent或null, applications:RefundApplication[], receipts:Receipt[], refunds:Refund[], shipment:Shipment或null, anomalies:BuyerAnomaly[], executable_actions:Action[]；只含本单本人的数据 |
| Action | code:CANCEL/PAY/QUERY_PAYMENT/APPLY_REFUND/VIEW_SHIPMENT, enabled:boolean, disabled_reason:string或null；按钮仅提示，服务端仍重查 |
| PaymentIntent | id:UUID, order_id:UUID, status:意图枚举, amount_cents:Money, currency:CNY, failure_code:string或null, provider_txn_id:string或null, created_at:UTC, updated_at:UTC；不返回服务端签名 |
| Receipt | id:UUID, order_id:UUID或null, provider:MOCK, provider_txn_id:string, amount_cents:Money, currency:CNY, classification:枚举, verified_at:UTC, provider_paid_at:UTC |
| RefundApplication | id:UUID, order_id:UUID, reason:string, status:申请枚举, review_reason:string或null, reviewer_id:UUID或null, reviewed_at:UTC或null, created_at:UTC |
| Refund | id:UUID, receipt_id:UUID, order_id/application_id/anomaly_id:UUID或null, kind:枚举, amount_cents:Money, status:退款枚举, attempts:RefundAttempt[], success_at:UTC或null, created_at:UTC, updated_at:UTC |
| RefundAttempt | id:UUID, attempt_no:number, status:尝试枚举, provider_refund_id:string或null, failure_code:string或null, sent_at/resolved_at/last_queried_at:UTC或null；不返回原始鉴权资料 |
| Shipment | id:UUID, order_id:UUID, carrier:string, tracking_no:string, operator_id:UUID, shipped_at:UTC |
| WarehouseOrder | id:UUID, order_no:string, name_snapshot:string, quantity:number, paid_at:UTC, can_ship:boolean；题面未要求真实地址，此教学登记不收集真实地址 |
| BuyerAnomaly | id:UUID, type:枚举, status:异常枚举, summary:string（只含本单安全描述）, refund_id:UUID或null |
| Anomaly | id:UUID, type:枚举, order_id/receipt_id/refund_id:UUID或null, status:异常枚举, verification:枚举, summary:string, resolved_reason:string或null, created_at:UTC, updated_at:UTC |
| AnomalyDetail | Anomaly全部字段 + notifications:Notification[], actions:AnomalyAction[], receipt:Receipt或null, refund:Refund或null |
| AnomalyAction | id:UUID, actor_id:UUID或null, action:枚举, reason:string, from_status:string, to_status:string, evidence_redacted:安全JSON对象, created_at:UTC |
| Notification | id:UUID, kind:枚举, provider_event_id:string或null, external_order_ref/provider_txn_id/provider_refund_id:string或null, claimed_amount_cents:Money或null, auth_valid:boolean, process_result:枚举, reason_code:string, received_at:UTC, processed_at:UTC或null；不返回原始签名/请求头/body |
| InventoryEntry | id:UUID, product_id:UUID, order_id/refund_id/actor_id:UUID或null, event_type:枚举, delta_available/delta_reserved/delta_shipped/delta_adjustment:number, available_before/available_after/reserved_before/reserved_after/shipped_before/shipped_after:number, reason:string, created_at:UTC |
| AuditEvent | id:UUID, actor_id:UUID或null, actor_kind:枚举, entity_type:枚举, entity_id:UUID或null, action:string, request_id:UUID, before_redacted/after_redacted:安全JSON对象, reason:string, created_at:UTC |
| Reconciliation | order:OrderDetail, inventory_entries:InventoryEntry[], receipts:Receipt[], refunds:Refund[], shipment:Shipment或null, anomalies:Anomaly[], audit_events:AuditEvent[], received_cents/refunded_cents/net_cents:Money（净额允许0）, unresolved_count:number, consistent:boolean, differences:string[]；同一快照 |
| Summary | as_of:UTC, normal_received_cents/exception_received_cents/total_received_cents/refunded_cents/net_cents:非负整数字符串, unverified_notification_count/unknown_refund_count/failed_refund_count/unresolved_anomaly_count:number, inventory:Product[], reconciliation_link_template:string（仅固定站内相对路径）, receipt_list_path/refund_list_path/anomaly_list_path:string（固定站内相对路径，分别API36/37/38） |
| ChannelPayment | merchant_ref/request_id/order_ref/txn_id:string, amount_cents:Money, currency:CNY, status:PENDING/SUCCEEDED/FAILED, paid_at:UTC或null |
| ChannelRefund | merchant_ref/request_id/txn_id/refund_id:string, amount_cents:Money, currency:CNY, status:PENDING/SUCCEEDED/FAILED, failure_code:string或null, refunded_at:UTC或null |
| SimulationRule | id:UUID, target_order_ref:string, target_request_id:string或null, attempt_no:number或null, operation/mode:枚举, delay_ms/repeat_count/remaining_uses:number；管理面不返回任何密钥 |

字段组合超过题面范围（如真实收货地址）不得擅加；若后续确有需要先修改审核清单。嵌套DTO按用途裁剪，买家不得看到其他人的异常/通知；员工安全白名单不能让订单详情递归无限展开。单笔资金Money要求>0；所有汇总received/refunded/net字段允许"0"，仍是规范十进制非负整数字符串，不使用浮点。

## 渠道签名协议（双向HTTP，同一规范）

请求头X-Key-Id、X-Timestamp（真实Unix秒）、X-Nonce（16..64随机ASCII）、X-Signature（hex HMAC-SHA256）必填。签名原文为method大写+换行+path+规范化排序query+换行+timestamp+换行+nonce+换行+SHA256原始body；path与query连接规则固定为path+(query非空时'?' +按RFC3986键值编码/排序的query)。本协议说明必须转为代码内可复用canonical函数并给固定签名向量，避免双方猜测格式。

签名时效建议±300秒，常量时间比较。入参不允许密钥/回调URL。有效nonce缓存/库唯一记录按key_id+nonce至少保留窗口两倍，重复同nonce拒绝并留接收记录；支付渠道网络重投用新nonce/timestamp、同业务event_id，必须被资金幂等入口安全接受。HMAC key与用户token、管理token分离，方向各用不同key_id：商城到mock为shop-to-mock，mock到商城为mock-to-shop（含只读教学时钟查询）；方向密钥=HMAC-SHA256(配置根密钥,key_id)，再用该二进制密钥签名canonical。根密钥仅环境配置，不能放请求。query编码使用RFC3986，空格为%20；方向ID由目标路径固定决定，接收端拒绝其他方向。正常通知的金额/币种/交易归属也必须校验。HTTP响应/查询结果使用可信固定HTTPS连接（本地教学loopback可HTTP），响应业务字段仍校验；跨网教学应启TLS，不关闭证书校验。

## 每个接口的完整契约

### API01 · POST /api/v1/auth/login

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 匿名 |
| 输入字段 | body: login_name:string(3..64)，password:string(教学Demo模式6..128，非Demo模式8..128)，均必填 |
| 输出 / 状态码 | 200: token:string，expires_at:UTC，account:Account |
| 前置、幂等、事务与异常 | 比对哈希、账号启用；失败统一INVALID_CREDENTIALS，不泄露账号是否存在；限流；密码/token不入日志 |
| 测试Agent必须覆盖 | 正确/错误/停用/超长/重复登录；只返回安全Account |

### API02 · GET /api/v1/auth/me

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 所有已登录角色 |
| 输入字段 | 无body |
| 输出 / 状态码 | 200: Account |
| 前置、幂等、事务与异常 | 从会话取身份与最新enabled/role，不信任query/user_id |
| 测试Agent必须覆盖 | 缺token、过期、撤销、伪造、改角色/用户ID |

### API03 · POST /api/v1/auth/logout

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 所有已登录角色 |
| 输入字段 | 无body |
| 输出 / 状态码 | 200: {revoked:true} |
| 前置、幂等、事务与异常 | 撤销当前会话，已撤销token再次请求401；不影响其他会话 |
| 测试Agent必须覆盖 | 撤销即时生效；不把密码/token回显 |

### API04 · GET /api/v1/products

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER |
| 输入字段 | query: cursor?,limit? |
| 输出 / 状态码 | 200: Page<Product> |
| 前置、幂等、事务与异常 | 只返回在售；可售0仍可显示售罄；不要求加购物车 |
| 测试Agent必须覆盖 | 下架隐藏、售罄可见、稳定分页、非买家403 |

### API05 · GET /api/v1/buyer/orders

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER |
| 输入字段 | query: status?（七主状态），cursor?,limit? |
| 输出 / 状态码 | 200: Page<OrderSummary> |
| 前置、幂等、事务与异常 | 服务端强制buyer_id当前用户；禁止query任意buyer_id |
| 测试Agent必须覆盖 | 本人/他人隔离、非法status/分页、到期状态说明 |

### API06 · POST /api/v1/buyer/orders

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER |
| 输入字段 | body: product_id:UUID，quantity:number(整数1或2)，均必填；Idempotency-Key必填 |
| 输出 / 状态码 | 201: OrderDetail；同键成功重放原http状态并meta.replayed=true |
| 前置、幂等、事务与异常 | 锁商品合法快照；本事务订单+占用+流水+幂等；客户端金额/状态/买家ID未知字段400 |
| 测试Agent必须覆盖 | 缺货/下架/所有非法quantity；20并发；同键并发/换参；落库失败回滚 |

### API07 · GET /api/v1/buyer/orders/{order_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER本人 |
| 输入字段 | path UUID |
| 输出 / 状态码 | 200: OrderDetail |
| 前置、幂等、事务与异常 | 他人订单与不存在统一404；过期未扫时executable_actions不放付款，显示期限已到，worker负责关闭；只读GET不修改状态 |
| 测试Agent必须覆盖 | 越权详情/运单/收退款隔离；重启回读；过期旧状态不可付 |

### API08 · POST /api/v1/buyer/orders/{order_id}/cancel

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER本人 |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 200: OrderDetail |
| 前置、幂等、事务与异常 | 仅待付款关闭；同一关闭重复回当前事实、不多释放；已付款409；已超时保持TIMEOUT原因 |
| 测试Agent必须覆盖 | 重复关闭、跨人、付款竞争、超时竞争；库存一次 |

### API09 · POST /api/v1/buyer/orders/{order_id}/payments

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER本人 |
| 输入字段 | 空JSON {}；Idempotency-Key |
| 输出 / 状态码 | 202: PaymentIntent |
| 前置、幂等、事务与异常 | 创建或复用非失败意图+outbox，金额由快照；过期先在锁内关闭后持久化拒绝事实；明确失败后可新意图，UNKNOWN先查原意图 |
| 测试Agent必须覆盖 | 过期/关闭/已付拒绝；同键/不同键并发不重复扣款；响应丢失恢复 |

### API10 · POST /api/v1/buyer/payments/{payment_id}/query

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER本人 |
| 输入字段 | 空JSON {}；Idempotency-Key |
| 输出 / 状态码 | 202: PaymentIntent（查询任务已排队） |
| 前置、幂等、事务与异常 | 仅查询该意图原渠道请求；可信结果走共享结算入口；非本人404 |
| 测试Agent必须覆盖 | 未知仍未知/成功/明确失败；不会延长到期或新扣款 |

### API11 · POST /api/v1/buyer/orders/{order_id}/refund-applications

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | BUYER本人 |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 201: RefundApplication |
| 前置、幂等、事务与异常 | 仅PENDING_SHIPMENT；锁内申请+冻结；活动申请同键重放原资源，新键返回409 ACTIVE_REFUND；已驳回可新申请 |
| 测试Agent必须覆盖 | 重复、重提、已发货/待付款拒绝；申请与发货并发唯一结果 |

### API12 · GET /api/v1/warehouse/orders

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | WAREHOUSE |
| 输入字段 | query: cursor?,limit? |
| 输出 / 状态码 | 200: Page<WarehouseOrder> |
| 前置、幂等、事务与异常 | 仅PENDING_SHIPMENT且无活动退款；必要单据/商品/数量，不暴露会话或渠道敏感字段 |
| 测试Agent必须覆盖 | 被冻结/已发货不列；跨角色403；旧页面操作仍重查 |

### API13 · POST /api/v1/warehouse/orders/{order_id}/shipment

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | WAREHOUSE |
| 输入字段 | body: carrier:string(1..80)，tracking_no:string(1..80)；Idempotency-Key |
| 输出 / 状态码 | 201: Shipment |
| 前置、幂等、事务与异常 | 锁内待发货且无活动退款；登记一次+SHIP；同键同参重放；新键重复409 SHIPMENT_EXISTS，运单不覆盖 |
| 测试Agent必须覆盖 | 必填/控制字符/超长、重复、新参数覆盖拒绝、申请竞争 |

### API14 · GET /api/v1/support/refund-applications

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | query: status?（申请枚举），cursor?,limit? |
| 输出 / 状态码 | 200: Page<RefundApplication> |
| 前置、幂等、事务与异常 | 默认PENDING；可查历次审核，拒绝不删 |
| 测试Agent必须覆盖 | 筛选历史、分页、越权、用户自报role无效 |

### API15 · POST /api/v1/support/refund-applications/{application_id}/review

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: decision:APPROVE或REJECT，reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 200: {application:RefundApplication,refund:Refund|null} |
| 前置、幂等、事务与异常 | 一次结论；同键同参回原；已审核同结论新键回原事实且不覆盖原因，冲突结论409；批准创建唯一退款/首尝试/outbox，拒绝解除冻结 |
| 测试Agent必须覆盖 | 双客服/同意拒绝竞争；原因空/非法decision；旧申请不能影响新申请 |

### API16 · GET /api/v1/support/refunds

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | query: status?（退款枚举），kind?:NORMAL或EXCEPTION，cursor?,limit? |
| 输出 / 状态码 | 200: Page<Refund> |
| 前置、幂等、事务与异常 | 展示FAILED/UNKNOWN/READY及原收款和尝试；默认未SUCCEEDED |
| 测试Agent必须覆盖 | 失败与未知区分；整笔计数不按attempt累加 |

### API17 · POST /api/v1/support/refunds/{refund_id}/retry

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 202: Refund |
| 前置、幂等、事务与异常 | 仅可信FAILED可新尝试，UNKNOWN/PROCESSING拒绝RESULT_UNKNOWN或STATE_CONFLICT；唯一活动尝试；同键返回原尝试 |
| 测试Agent必须覆盖 | 失败重试成功、未知拒绝、重复重试、旧回报竞争不多退 |

### API18 · POST /api/v1/support/refunds/{refund_id}/query

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 202: Refund |
| 前置、幂等、事务与异常 | 排队查询原尝试；不新建资金请求；可信成功/失败驱动同一结算入口 |
| 测试Agent必须覆盖 | 未知维持冻结；确认成功只结算一次；确认失败才允许retry |

### API19 · GET /api/v1/support/payment-anomalies

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | query: status?（异常枚举），type?（异常类型），cursor?,limit? |
| 输出 / 状态码 | 200: Page<Anomaly> |
| 前置、幂等、事务与异常 | 已解决可按筛选查询，默认未RESOLVED；保留无效通知处理结论 |
| 测试Agent必须覆盖 | 迟到/验签失败/金额不符/未知/冲突均可查；不直接改状态消失 |

### API20 · GET /api/v1/support/payment-anomalies/{anomaly_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | path UUID |
| 输出 / 状态码 | 200: AnomalyDetail |
| 前置、幂等、事务与异常 | 含脱敏通知和核查、退款历史；无任意改状态按钮 |
| 测试Agent必须覆盖 | 原始关键标识可查但无密钥、token和未脱敏body |

### API21 · POST /api/v1/support/payment-anomalies/{anomaly_id}/verify

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 200: AnomalyDetail；外部未确认可202同DTO |
| 前置、幂等、事务与异常 | 固定渠道可信查询；商户/交易/金额归属全校验；body不允许直接写verified=true/金额。查询失败保持待核实，记录动作 |
| 测试Agent必须覆盖 | 恶意未签通知不能任填退款；正常迟到可信核实；查询未知/错商户 |

### API22 · POST /api/v1/support/payment-anomalies/{anomaly_id}/refund

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 202: Refund |
| 前置、幂等、事务与异常 | 仅FUNDS_CONFIRMED且receipt存在、未成功退款；按实际全额EXCEPTION；创建一次逻辑退款/尝试/outbox；无库存动作 |
| 测试Agent必须覆盖 | 未核实拒绝；重复返回同退款；迟到/未知订单可信资金处理；库存不再释放 |

### API23 · POST /api/v1/support/payment-anomalies/{anomaly_id}/resolve

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | body: reason:string(1..500)；Idempotency-Key |
| 输出 / 状态码 | 200: AnomalyDetail |
| 前置、幂等、事务与异常 | 仅可信NO_FUNDS等无需资金动作可人工结案；有资金必须SUCCEEDED实退才系统收尾，CONFLICT/UNKNOWN不得结案 |
| 测试Agent必须覆盖 | 写忽略不能抹异常；资金未退拒绝；历史保留 |

### API24 · GET /api/v1/support/notifications

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | query: kind?,process_result?,cursor?,limit? |
| 输出 / 状态码 | 200: Page<Notification> |
| 前置、幂等、事务与异常 | 可查询鉴权失败、重复、金额不符、未知订单及处理结论；字段脱敏 |
| 测试Agent必须覆盖 | 重放有接收轨迹，无资金重复；无效body记录；分页及权限 |

### API25 · GET /api/v1/operator/products

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: cursor?,limit? |
| 输出 / 状态码 | 200: Page<Product> |
| 前置、幂等、事务与异常 | 含上下架两类、库存四分量及版本；只读 |
| 测试Agent必须覆盖 | 与流水、订单占用一致；其他角色403 |

### API26 · PATCH /api/v1/operator/products/{product_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | body: version:integer>=0，reason:string(1..500)，name?:string(1..120)，unit_price_cents?:Money，sale_status?:枚举；至少一项变更；Idempotency-Key |
| 输出 / 状态码 | 200: Product |
| 前置、幂等、事务与异常 | 不允许body直接改库存/旧单；锁内比version，保留审计变更前后 |
| 测试Agent必须覆盖 | 缺字段/非法价格/旧version/调价下架与下单竞争；快照不变 |

### API27 · POST /api/v1/operator/products/{product_id}/inventory-adjustments

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | body: delta:integer(-1000000..1000000且非0)，reason:string(1..500)，version:integer>=0；Idempotency-Key |
| 输出 / 状态码 | 201: InventoryEntry |
| 前置、幂等、事务与异常 | 只调available及adjustment_net，不改reserved；available+delta范围合法，保存前后值和人 |
| 测试Agent必须覆盖 | 负库存拒绝、同键重复、原因空、与下单并发守恒 |

### API28 · GET /api/v1/operator/orders

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: order_no?,buyer_id?:UUID,status?,cursor?,limit? |
| 输出 / 状态码 | 200: Page<OrderSummary> |
| 前置、幂等、事务与异常 | 运营可跨订单核对，仅只读；不提供修改订单状态接口 |
| 测试Agent必须覆盖 | 联查筛选、无敏感数据、分页 |

### API29 · GET /api/v1/operator/orders/{order_id}/reconciliation

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | path UUID |
| 输出 / 状态码 | 200: Reconciliation |
| 前置、幂等、事务与异常 | 同一一致快照关联订单、库存流水、收款、退款、发货、异常/审核历史及差异；未知状态不能标全部结清 |
| 测试Agent必须覆盖 | 正常、退款、迟到、重复、未知、失败明细汇总一致 |

### API30 · GET /api/v1/operator/summary

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: product_id?:UUID；无额外日期过滤本题保持全活动累计 |
| 输出 / 状态码 | 200: Summary |
| 前置、幂等、事务与异常 | 可信正常/异常实收、成功实退/净留存、未核实/未知/失败/待办数量单列，库存守恒 |
| 测试Agent必须覆盖 | 不按通知条数累加；未知不当已退；下钻金额一致 |

### API31 · POST /api/v1/channel/payment-notifications

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 模拟渠道HMAC |
| 输入字段 | body: event_id,merchant_ref,order_ref,request_id,txn_id,amount_cents:Money,currency:CNY,status:SUCCEEDED或FAILED,occurred_at:UTC；全部必填 |
| 输出 / 状态码 | 200: {notification_id:UUID,result:处理枚举}；无效鉴权401 |
| 前置、幂等、事务与异常 | 先限body/解析安全摘要，再鉴权、匹配、唯一归属、时限；有效失败只更新意图不记实收；业务异常持久化后200 ACK，基础设施失败503，签名错401仍留记录 |
| 测试Agent必须覆盖 | 重复、错签/重放时间、错金额、未知订单、交易跨单、不同交易同单、迟到、取消竞争 |

### API32 · POST /api/v1/channel/refund-notifications

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 模拟渠道HMAC |
| 输入字段 | body: event_id,merchant_ref,txn_id,request_id,refund_id,amount_cents:Money,currency:CNY,status:SUCCEEDED或FAILED,occurred_at:UTC，failure_code?:string；全部必填项按上文 |
| 输出 / 状态码 | 200: {notification_id:UUID,result:处理枚举}；签名错401 |
| 前置、幂等、事务与异常 | 精确匹配尝试/收款/金额；成功仅首次结算；旧/矛盾回报留冲突，不能倒退/多退；失败须来自渠道明确终态 |
| 测试Agent必须覆盖 | 重复成功/失败、旧尝试、错金额/身份/收款、回报与query并发 |

### API33 · GET /health/live

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 无认证（仅必要信息） |
| 输入字段 | 无 |
| 输出 / 状态码 | 200: {status:UP} |
| 前置、幂等、事务与异常 | 只证明进程存活，无DB/密钥/业务细节 |
| 测试Agent必须覆盖 | 响应快且不泄露配置 |

### API34 · GET /health/ready

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 部署健康探测 |
| 输入字段 | 无 |
| 输出 / 状态码 | 200或503: {status:UP或DOWN,version:string} |
| 前置、幂等、事务与异常 | 检查DB/迁移就绪，外部依赖故障有明确ready策略；版本为构建注入SHA |
| 测试Agent必须覆盖 | DB断开503、版本标识、不能代替业务冒烟 |

### API35 · GET /api/v1/support/orders/{order_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | SUPPORT |
| 输入字段 | path UUID |
| 输出 / 状态码 | 200: OrderDetail |
| 前置、幂等、事务与异常 | 用于审核时查看订单快照、支付/退款与发货事实；仅安全字段，不允许借此改订单；买家仍只本人 |
| 测试Agent必须覆盖 | 客服能核实金额/状态；买家调用员工路由403；无敏感凭证 |

### API36 · GET /api/v1/operator/receipts

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: classification?,order_id?:UUID,cursor?,limit? |
| 输出 / 状态码 | 200: Page<Receipt> |
| 前置、幂等、事务与异常 | 汇总实收下钻，含可信未知订单收款，未核实通知不混入实收 |
| 测试Agent必须覆盖 | 总额与分页明细一致，异常和正常分类，未知订单也不丢记录 |

### API37 · GET /api/v1/operator/refunds

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: status?,kind?,order_id?:UUID,cursor?,limit? |
| 输出 / 状态码 | 200: Page<Refund> |
| 前置、幂等、事务与异常 | 汇总实退/失败/未知下钻，按逻辑退款计额不按attempt计额 |
| 测试Agent必须覆盖 | 成功金额一致，失败未知不能算实退，角色只读 |

### API38 · GET /api/v1/operator/payment-anomalies

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | query: status?,type?,cursor?,limit? |
| 输出 / 状态码 | 200: Page<Anomaly> |
| 前置、幂等、事务与异常 | 运营可只读核查包括未知订单的全部活动/历史异常，不限有订单才可查 |
| 测试Agent必须覆盖 | 异常汇总数量与列表一致，不修改状态、不泄密 |

### API39 · GET /api/v1/operator/payment-anomalies/{anomaly_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | OPERATOR |
| 输入字段 | path UUID |
| 输出 / 状态码 | 200: AnomalyDetail |
| 前置、幂等、事务与异常 | 只读核查通知处理结论、客服核实与退款记录；客服操作仍仅SUPPORT可用 |
| 测试Agent必须覆盖 | 明细/汇总可追溯；运营不能借查询权限审核/退款/结案 |

### MOCK01 · POST /mock/v1/payments

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 商城服务HMAC |
| 输入字段 | body: merchant_ref,request_id,order_ref,amount_cents:Money,currency:CNY |
| 输出 / 状态码 | 200: ChannelPayment；受控超时可无响应 |
| 前置、幂等、事务与异常 | 幂等键固定、相同参数回原交易，换参409；模拟成功/失败/未知/响应丢失 |
| 测试Agent必须覆盖 | 渠道实际扣一次、重启可查、商城不能直接写渠道DB |

### MOCK02 · GET /mock/v1/payments/by-request/{request_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 商城服务HMAC |
| 输入字段 | path ASCII16..80，query: merchant_ref必填 |
| 输出 / 状态码 | 200: ChannelPayment；不存在404（仅表示尚无记录，商城先保持待确认） |
| 前置、幂等、事务与异常 | 同商户可查，不以未找到直接允许另建交易 |
| 测试Agent必须覆盖 | 未知/成功/失败/错商户/查询超时 |

### MOCK03 · GET /mock/v1/transactions/{txn_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 商城服务HMAC |
| 输入字段 | path ASCII1..80，query: merchant_ref必填 |
| 输出 / 状态码 | 200: ChannelPayment；不存在404 |
| 前置、幂等、事务与异常 | 用于异常款项独立核实，固定渠道URL及商户身份 |
| 测试Agent必须覆盖 | 伪造通知/不存在/错商户不变实收 |

### MOCK04 · POST /mock/v1/refunds

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 商城服务HMAC |
| 输入字段 | body: merchant_ref,request_id,txn_id,amount_cents:Money,currency:CNY |
| 输出 / 状态码 | 200: ChannelRefund；受控超时可无响应 |
| 前置、幂等、事务与异常 | 锁原渠道收款，校验商户及全额累计；同键返回同退款，明确失败才能新键 |
| 测试Agent必须覆盖 | 首次失败后成功、超时但实退成功、重发不多退/超原额拒绝 |

### MOCK05 · GET /mock/v1/refunds/by-request/{request_id}

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 商城服务HMAC |
| 输入字段 | path ASCII16..80，query: merchant_ref必填 |
| 输出 / 状态码 | 200: ChannelRefund；不存在404（未确认，不当明确失败） |
| 前置、幂等、事务与异常 | 可信终态稳定，未知不新退款 |
| 测试Agent必须覆盖 | 成功/失败/PENDING/未找到/网络超时 |

### MOCK06 · POST /mock/admin/rules

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 教学开关+独立admin令牌 |
| 输入字段 | body: target_order_ref:string(1..80)，operation,mode（规则表枚举），target_request_id?:string(16..80)，attempt_no?:integer>=1，delay_ms?:0..600000，repeat_count?:1..20，remaining_uses?:1..20 |
| 输出 / 状态码 | 201: SimulationRule |
| 前置、幂等、事务与异常 | 只控制指定订单及尝试；预先为已有订单设置首败/二次成功或延迟；业务角色无权 |
| 测试Agent必须覆盖 | 开关关闭404、普通token403、非法模式/值拒绝，不暴露签名密钥 |

### MOCK07 · POST /mock/admin/notifications/{event_id}/replay

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 教学开关+独立admin令牌 |
| 输入字段 | path event_id，body: repeat_count:1..20，delay_ms:0..600000 |
| 输出 / 状态码 | 202: {event_id:string,queued:number} |
| 前置、幂等、事务与异常 | 只重发已有真实事件，目标回调固定白名单；重复event使用新签名nonce但同业务ID |
| 测试Agent必须覆盖 | 重复/迟到可演示；任意callback_url拒绝、超范围拒绝 |

### DEMO01 · POST /internal/demo/clock/advance

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 仅教学开关+独立admin令牌 |
| 输入字段 | body: seconds:integer(1..3600) |
| 输出 / 状态码 | 200: {business_now:UTC,advanced_seconds:number,offset_seconds:number,version:number} |
| 前置、幂等、事务与异常 | 数据库原子推进demo_clock，记录安全管理标识；只前进，商城/模拟渠道同源；不改认证/HMAC/租约；不允许公网无鉴权 |
| 测试Agent必须覆盖 | 10分钟前/正好/后边界，重启/多实例统一，并发推进不丢更新；默认真实10分钟 |

### DEMO02 · GET /internal/demo/clock

| 项目 | 要求 |
| --- | --- |
| 调用者 / 权限 | 仅教学开关+模拟渠道服务HMAC或独立admin令牌 |
| 输入字段 | 无body |
| 输出 / 状态码 | 200: {business_now:UTC,offset_seconds:number,version:number} |
| 前置、幂等、事务与异常 | 统一读取持久偏移供mock ClockProvider使用，真实模式教学端点404；不泄露DB配置/签名密钥；普通业务身份禁止 |
| 测试Agent必须覆盖 | 多进程偏移一致，重启保留，鉴权/教学开关；时钟不可由客户端回拨 |


不存在通用修改订单状态、任意退款金额、删除异常、任意回调URL或线上重置业务数据的接口。所有教学接口是显式受控功能；普通业务角色不能通过改路径/token或JSON字段获得控制权限。

## 0.2验收返修协议固定向量

AC-003：跨语言独立向量（测试密钥不是运行密钥）：根密钥`vector-secret`、key_id `shop-to-mock`、body `{}`、时间1700000000、nonce `0123456789abcdef`；POST `/mock/v1/payments?z=%E4%B8%AD&a=one+two`的canonical为：

```text
POST
/mock/v1/payments?a=one%20two&z=%E4%B8%AD
1700000000
0123456789abcdef
44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
```

使用二进制方向密钥后的签名为`e72c506718f45af3fe693c68f2f7c9d2068dd8397d95beaedef19fa99ce16bad`，见security固定向量测试。AC-002仓库created_at仅供内部排序，出站DTO不返回。AC-004每个HTTP请求服务端生成关联ID，同请求的审计request_id与响应meta.request_id一致；不信任调用方X-Request-ID。后台操作生成自身关联ID，幂等重放不制造新的历史审计。
