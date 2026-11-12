package httpapi

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/mockpay"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/service"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/wire"
)

type Row = repository.Row
type Route struct {
	Method, Path, Role, Op, Required, Optional, Query string
	Write                                             bool
}

var ShopRoutes = []Route{
	{"POST", "/api/v1/auth/login", "", "login", "login_name password", "", "", false},
	{"GET", "/api/v1/auth/me", "*", "me", "", "", "", false},
	{"POST", "/api/v1/auth/logout", "*", "logout", "", "", "", false},
	{"GET", "/api/v1/products", "BUYER", "products", "", "", "cursor limit", false},
	{"GET", "/api/v1/buyer/orders", "BUYER", "orders", "", "", "status cursor limit", false},
	{"POST", "/api/v1/buyer/orders", "BUYER", "create_order", "product_id quantity", "", "", true},
	{"GET", "/api/v1/buyer/orders/{order_id}", "BUYER", "order", "", "", "", false},
	{"POST", "/api/v1/buyer/orders/{order_id}/cancel", "BUYER", "cancel", "reason", "", "", true},
	{"POST", "/api/v1/buyer/orders/{order_id}/payments", "BUYER", "pay", "", "", "", true},
	{"POST", "/api/v1/buyer/payments/{payment_id}/query", "BUYER", "query_payment", "", "", "", true},
	{"POST", "/api/v1/buyer/orders/{order_id}/refund-applications", "BUYER", "apply", "reason", "", "", true},
	{"GET", "/api/v1/warehouse/orders", "WAREHOUSE", "warehouse", "", "", "cursor limit", false},
	{"POST", "/api/v1/warehouse/orders/{order_id}/shipment", "WAREHOUSE", "ship", "carrier tracking_no", "", "", true},
	{"GET", "/api/v1/support/refund-applications", "SUPPORT", "refund_applications", "", "", "status cursor limit", false},
	{"POST", "/api/v1/support/refund-applications/{application_id}/review", "SUPPORT", "review", "decision reason", "", "", true},
	{"GET", "/api/v1/support/refunds", "SUPPORT", "refunds", "", "", "status kind cursor limit", false},
	{"POST", "/api/v1/support/refunds/{refund_id}/retry", "SUPPORT", "retry_refund", "reason", "", "", true},
	{"POST", "/api/v1/support/refunds/{refund_id}/query", "SUPPORT", "query_refund", "reason", "", "", true},
	{"GET", "/api/v1/support/payment-anomalies", "SUPPORT", "payment_anomalies", "", "", "status type cursor limit", false},
	{"GET", "/api/v1/support/payment-anomalies/{anomaly_id}", "SUPPORT", "anomaly", "", "", "", false},
	{"POST", "/api/v1/support/payment-anomalies/{anomaly_id}/verify", "SUPPORT", "verify", "reason", "", "", true},
	{"POST", "/api/v1/support/payment-anomalies/{anomaly_id}/refund", "SUPPORT", "refund_anomaly", "reason", "", "", true},
	{"POST", "/api/v1/support/payment-anomalies/{anomaly_id}/resolve", "SUPPORT", "resolve_anomaly", "reason", "", "", true},
	{"GET", "/api/v1/support/notifications", "SUPPORT", "channel_notifications", "", "", "kind process_result cursor limit", false},
	{"GET", "/api/v1/operator/products", "OPERATOR", "products", "", "", "cursor limit", false},
	{"PATCH", "/api/v1/operator/products/{product_id}", "OPERATOR", "update_product", "version reason", "name unit_price_cents sale_status", "", true},
	{"POST", "/api/v1/operator/products/{product_id}/inventory-adjustments", "OPERATOR", "adjust", "delta reason version", "", "", true},
	{"GET", "/api/v1/operator/orders", "OPERATOR", "orders", "", "", "order_no buyer_id status cursor limit", false},
	{"GET", "/api/v1/operator/orders/{order_id}/reconciliation", "OPERATOR", "reconciliation", "", "", "", false},
	{"GET", "/api/v1/operator/summary", "OPERATOR", "summary", "", "", "product_id", false},
	{"POST", "/api/v1/channel/payment-notifications", "HMAC", "notify_payment", "event_id merchant_ref order_ref request_id txn_id amount_cents currency status occurred_at", "", "", false},
	{"POST", "/api/v1/channel/refund-notifications", "HMAC", "notify_refund", "event_id merchant_ref txn_id request_id refund_id amount_cents currency status occurred_at", "failure_code", "", false},
	{"GET", "/health/live", "", "live", "", "", "", false},
	{"GET", "/health/ready", "", "ready", "", "", "", false},
	{"GET", "/api/v1/support/orders/{order_id}", "SUPPORT", "order", "", "", "", false},
	{"GET", "/api/v1/operator/receipts", "OPERATOR", "receipts", "", "", "classification order_id cursor limit", false},
	{"GET", "/api/v1/operator/refunds", "OPERATOR", "refunds", "", "", "status kind order_id cursor limit", false},
	{"GET", "/api/v1/operator/payment-anomalies", "OPERATOR", "payment_anomalies", "", "", "status type cursor limit", false},
	{"GET", "/api/v1/operator/payment-anomalies/{anomaly_id}", "OPERATOR", "anomaly", "", "", "", false},
	{"POST", "/internal/demo/clock/advance", "ADMIN", "advance", "seconds", "", "", false},
	{"GET", "/internal/demo/clock", "CLOCK", "clock", "", "", "", false},
}
var MockRoutes = []Route{
	{"POST", "/mock/v1/payments", "HMAC", "payment", "merchant_ref request_id order_ref amount_cents currency", "", "", false},
	{"GET", "/mock/v1/payments/by-request/{request_id}", "HMAC", "payment_query", "", "", "merchant_ref", false},
	{"GET", "/mock/v1/transactions/{txn_id}", "HMAC", "transaction_query", "", "", "merchant_ref", false},
	{"POST", "/mock/v1/refunds", "HMAC", "refund", "merchant_ref request_id txn_id amount_cents currency", "", "", false},
	{"GET", "/mock/v1/refunds/by-request/{request_id}", "HMAC", "refund_query", "", "", "merchant_ref", false},
	{"POST", "/mock/admin/rules", "ADMIN", "rule", "target_order_ref operation mode", "target_request_id attempt_no delay_ms repeat_count remaining_uses", "", false},
	{"POST", "/mock/admin/notifications/{event_id}/replay", "ADMIN", "replay", "repeat_count delay_ms", "", "", false},
}

type API struct {
	Shop                   *service.Service
	Mock                   *mockpay.Provider
	Channel                *channel.Client
	Secret, Admin, Version string
	Demo                   bool
	mu                     sync.Mutex
	logins                 map[string]loginWindow
}
type loginWindow struct {
	start time.Time
	count int
}

func (a *API) limited(ip string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.logins == nil {
		a.logins = map[string]loginWindow{}
	}
	now := time.Now()
	if len(a.logins) > 1000 {
		for k, v := range a.logins {
			if now.Sub(v.start) > time.Minute {
				delete(a.logins, k)
			}
		}
	}
	v := a.logins[ip]
	if now.Sub(v.start) > time.Minute {
		v = loginWindow{start: now}
	}
	v.count++
	a.logins[ip] = v
	return v.count > 30
}
func (a *API) Handler(static http.Handler) http.Handler {
	mux := http.NewServeMux()
	routes := ShopRoutes
	if a.Mock != nil {
		routes = MockRoutes
	}
	for _, route := range routes {
		r := route
		mux.HandleFunc(r.Method+" "+r.Path, func(w http.ResponseWriter, req *http.Request) { a.serve(w, req, r) })
	}
	if a.Mock != nil {
		mux.HandleFunc("GET /health/live", func(w http.ResponseWriter, r *http.Request) { a.respond(w, r, 200, Row{"status": "UP"}, false) })
	} else if static != nil {
		mux.Handle("/", static)
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r = r.WithContext(repository.WithRequestID(r.Context(), repository.ID()))
		if a.Mock != nil && a.Demo {
			origin := r.Header.Get("Origin")
			if origin == "http://127.0.0.1:18080" || origin == "http://localhost:18080" || origin == "http://127.0.0.1:18090" {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Vary", "Origin")
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
				if r.Method == "OPTIONS" {
					w.WriteHeader(204)
					return
				}
			}
		}
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		mux.ServeHTTP(w, r)
	})
}
func (a *API) respond(w http.ResponseWriter, r *http.Request, status int, data any, replayed bool) {
	now := time.Now().UTC()
	business := now
	if a.Shop != nil {
		if clock, e := a.Shop.Clock(r.Context(), 0); e == nil {
			business = clock.(Row)["business_now"].(time.Time)
		}
	}
	wire.Write(w, r, status, Row{"data": data, "meta": Row{"request_id": repository.RequestID(r.Context()), "replayed": replayed, "server_time": now, "business_time": business}}, a.Secret)
}
func (a *API) fail(w http.ResponseWriter, r *http.Request, e error) {
	status, code, message := 503, "RETRYABLE_STORAGE", "服务暂时不可用，请稍后重试"
	var f *d.Fault
	if errors.As(e, &f) {
		status, code, message = f.Status, f.Code, f.Message
	}
	wire.Write(w, r, status, Row{"error": Row{"code": code, "message": message, "retryable": status >= 500}, "meta": Row{"request_id": repository.RequestID(r.Context()), "server_time": time.Now().UTC(), "business_time": time.Now().UTC()}}, a.Secret)
}
func (a *API) nonce(ctx context.Context, nonce string) error {
	if a.Mock != nil {
		return a.Mock.Nonce(ctx, nonce)
	}
	_, e := a.Shop.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		if t.One("auth_nonces", Row{"key_id": "mock-to-shop", "nonce": nonce}) != nil {
			return nil, d.Fail("REPLAYED_SIGNATURE", 401, "签名已使用")
		}
		t.Add("auth_nonces", Row{"key_id": "mock-to-shop", "nonce": nonce, "expires_at": time.Now().UTC().Add(10 * time.Minute)})
		return nil, nil
	})
	return e
}
func checkEnums(b Row) error {
	for k, allowed := range map[string]string{"sale_status": "ON_SHELF OFF_SHELF", "decision": "APPROVE REJECT", "mode": "SUCCESS EXPLICIT_FAIL TIMEOUT_AFTER_SUCCESS PENDING DELAY_NOTIFY DUPLICATE_NOTIFY", "operation": "PAYMENT REFUND NOTIFY"} {
		if b[k] != nil && !strings.Contains(" "+allowed+" ", " "+b.S(k)+" ") {
			return d.Invalid("枚举错误：" + k)
		}
	}
	return nil
}
func (a *API) serve(w http.ResponseWriter, r *http.Request, rt Route) {
	b := Row{}
	raw := []byte{}
	var decodeErr error
	if r.Method != "GET" {
		b, raw, decodeErr = wire.Decode(r)
	}
	isNotify := strings.HasPrefix(rt.Op, "notify_")
	if isNotify {
		kind := "PAYMENT"
		if rt.Op == "notify_refund" {
			kind = "REFUND"
		}
		auth := ""
		if e := security.Verify(r, raw, a.Secret); e != nil {
			auth = "INVALID_SIGNATURE"
		}
		if decodeErr != nil || wire.Validate(b, rt.Required, rt.Optional) != nil {
			auth = "INVALID_BODY"
			b = Row{}
		} else if b.S("status") != "SUCCEEDED" && b.S("status") != "FAILED" {
			auth = "INVALID_BODY"
			b = Row{}
		} else if _, e := time.Parse(time.RFC3339Nano, b.S("occurred_at")); e != nil {
			auth = "INVALID_BODY"
			b = Row{}
		}
		data, e := a.Shop.Ingest(r.Context(), kind, b, repository.Hash(raw), auth, r.Header.Get("X-Nonce"))
		if e != nil {
			a.fail(w, r, e)
			return
		}
		result := data.(Row).S("result")
		if result == "INVALID_SIGNATURE" || result == "REPLAYED_SIGNATURE" {
			a.fail(w, r, d.Fail(result, 401, "通知鉴权失败，已保存处理记录"))
			return
		}
		if result == "INVALID_BODY" {
			a.fail(w, r, d.Invalid("通知格式错误，已保存处理记录"))
			return
		}
		a.respond(w, r, 200, data, false)
		return
	}
	if decodeErr != nil {
		a.fail(w, r, decodeErr)
		return
	}
	if e := wire.Validate(b, rt.Required, rt.Optional); e != nil {
		a.fail(w, r, e)
		return
	}
	if e := checkEnums(b); e != nil {
		a.fail(w, r, e)
		return
	}
	for k, values := range r.URL.Query() {
		if len(values) != 1 || !strings.Contains(" "+rt.Query+" ", " "+k+" ") {
			a.fail(w, r, d.Invalid("不支持或重复的查询参数："+k))
			return
		}
	}
	var actor Row
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	adminOK := a.Demo && len(a.Admin) >= 32 && security.Digest([]byte(token)) == security.Digest([]byte(a.Admin))
	if rt.Role == "ADMIN" {
		if !a.Demo {
			http.NotFound(w, r)
			return
		}
		if !adminOK {
			a.fail(w, r, d.Fail("FORBIDDEN", 403, "需要独立教学管理凭证"))
			return
		}
	}
	if rt.Role == "CLOCK" {
		if !a.Demo {
			http.NotFound(w, r)
			return
		}
		if !adminOK {
			if e := security.Verify(r, raw, a.Secret); e != nil {
				a.fail(w, r, d.Fail("UNAUTHENTICATED", 401, "教学时钟鉴权失败"))
				return
			}
			if e := a.nonce(r.Context(), r.Header.Get("X-Nonce")); e != nil {
				a.fail(w, r, e)
				return
			}
		}
	}
	if rt.Role == "HMAC" {
		if e := security.Verify(r, raw, a.Secret); e != nil {
			a.fail(w, r, d.Fail("INVALID_SIGNATURE", 401, "渠道鉴权失败"))
			return
		}
		if e := a.nonce(r.Context(), r.Header.Get("X-Nonce")); e != nil {
			a.fail(w, r, e)
			return
		}
	}
	if rt.Role != "" && rt.Role != "ADMIN" && rt.Role != "CLOCK" && rt.Role != "HMAC" {
		var e error
		actor, e = a.Shop.Auth(r.Context(), token)
		if e != nil {
			a.fail(w, r, e)
			return
		}
		if rt.Role != "*" && rt.Role != actor.S("role") {
			a.fail(w, r, d.Fail("FORBIDDEN", 403, "当前角色无权操作"))
			return
		}
	}
	id := ""
	for _, key := range []string{"order_id", "payment_id", "application_id", "refund_id", "anomaly_id", "product_id"} {
		if v := r.PathValue(key); v != "" {
			id = v
			if !d.UUID(v) {
				a.fail(w, r, d.Invalid("资源ID格式错误"))
				return
			}
		}
	}
	if a.Mock != nil {
		a.mockServe(w, r, rt, b)
		return
	}
	if rt.Write {
		key := r.Header.Get("Idempotency-Key")
		if !d.ASCII(key, 16, 64) {
			a.fail(w, r, d.Invalid("Idempotency-Key须为16到64个ASCII字符"))
			return
		}
		if rt.Op == "update_product" && len(b) < 3 {
			a.fail(w, r, d.Invalid("至少提供一项商品变更"))
			return
		}
		var result service.Result
		var e error
		if rt.Op == "verify" {
			result, e = a.Shop.VerifyAnomaly(r.Context(), a.Channel, actor, id, key, b.S("reason"))
		} else {
			result, e = a.Shop.Exec(r.Context(), actor, rt.Op, id, key, b)
		}
		if e != nil {
			a.fail(w, r, e)
			return
		}
		a.respond(w, r, result.Status, result.Data, result.Replayed)
		return
	}
	switch rt.Op {
	case "login":
		if a.limited(strings.Split(r.RemoteAddr, ":")[0]) {
			a.fail(w, r, d.Fail("RATE_LIMITED", 429, "登录请求过多，请稍后重试"))
			return
		}
		minPasswordLength := 8
		if a.Demo {
			minPasswordLength = 6
		}
		if !d.ASCII(b.S("login_name"), 3, 64) || len(b.S("password")) < minPasswordLength {
			a.fail(w, r, d.Invalid("账号或密码长度错误"))
			return
		}
		v, e := a.Shop.Login(r.Context(), b.S("login_name"), b.S("password"))
		if e != nil {
			a.fail(w, r, e)
			return
		}
		a.respond(w, r, 200, v, false)
	case "me":
		a.respond(w, r, 200, actor, false)
	case "logout":
		if e := a.Shop.Logout(r.Context(), token); e != nil {
			a.fail(w, r, e)
			return
		}
		a.respond(w, r, 200, Row{"revoked": true}, false)
	case "live":
		a.respond(w, r, 200, Row{"status": "UP"}, false)
	case "ready":
		ctx, cancel := context.WithTimeout(r.Context(), time.Second)
		defer cancel()
		status, state := 200, "UP"
		if e := a.Shop.Store.Ping(ctx); e != nil {
			status, state = 503, "DOWN"
		}
		a.respond(w, r, status, Row{"status": state, "version": a.Version}, false)
	case "clock", "advance":
		sec := int64(0)
		if rt.Op == "advance" {
			sec = b.N("seconds")
			if sec < 1 || sec > 3600 {
				a.fail(w, r, d.Invalid("seconds须为1到3600"))
				return
			}
		}
		v, e := a.Shop.Clock(r.Context(), sec)
		if e != nil {
			a.fail(w, r, e)
			return
		}
		a.respond(w, r, 200, v, false)
	default:
		limit, e := wire.Limit(r)
		if e != nil {
			a.fail(w, r, e)
			return
		}
		f := Row{}
		for k, values := range r.URL.Query() {
			if k != "cursor" && k != "limit" {
				v := values[0]
				if !d.Text(v, 160) {
					a.fail(w, r, d.Invalid("筛选值格式错误"))
					return
				}
				if strings.HasSuffix(k, "_id") && !d.UUID(v) {
					a.fail(w, r, d.Invalid("筛选ID格式错误"))
					return
				}
				f[k] = v
			}
		}
		if e := validateFilters(rt.Op, f); e != nil {
			a.fail(w, r, e)
			return
		}
		v, e := a.Shop.Read(r.Context(), actor, rt.Op, id, f, limit, r.URL.Query().Get("cursor"))
		if e != nil {
			a.fail(w, r, e)
			return
		}
		a.respond(w, r, 200, v, false)
	}
}
func validateFilters(op string, f Row) error {
	enums := map[string]string{"kind": "NORMAL EXCEPTION", "classification": "NORMAL LATE EXTRA AMOUNT_MISMATCH UNKNOWN_ORDER", "type": "LATE_PAYMENT INVALID_SIGNATURE AMOUNT_MISMATCH UNKNOWN_ORDER TXN_CONFLICT EXTRA_PAYMENT REFUND_RESULT_CONFLICT INVALID_BODY", "process_result": "ACCEPTED DUPLICATE INVALID_SIGNATURE REPLAYED_SIGNATURE AMOUNT_MISMATCH UNKNOWN_ORDER TXN_CONFLICT INVALID_BODY RESULT_CONFLICT RETRYABLE"}
	switch op {
	case "orders":
		enums["status"] = "PENDING_PAYMENT CLOSED PENDING_SHIPMENT REFUND_REVIEW REFUND_PROCESSING REFUNDED SHIPPED"
	case "refunds":
		enums["status"] = "READY PROCESSING UNKNOWN FAILED SUCCEEDED"
	case "refund_applications":
		enums["status"] = "PENDING APPROVED REJECTED"
	case "payment_anomalies":
		enums["status"] = "OPEN VERIFIED REFUNDING RESOLVED"
	case "channel_notifications":
		enums["kind"] = "PAYMENT REFUND"
	}
	for k, v := range f {
		if allowed := enums[k]; allowed != "" && !strings.Contains(" "+allowed+" ", " "+v.(string)+" ") {
			return d.Invalid("非法筛选枚举：" + k)
		}
	}
	return nil
}
func (a *API) mockServe(w http.ResponseWriter, r *http.Request, rt Route, b Row) {
	var v any
	var e error
	status := 200
	timeout := false
	switch rt.Op {
	case "payment", "refund":
		if !d.ExternalID(b.S("request_id"), 16, 80) {
			e = d.Invalid("渠道请求ID格式错误")
			break
		}
		v, timeout, e = a.Mock.Create(r.Context(), rt.Op == "refund", b)
	case "payment_query", "transaction_query", "refund_query":
		table, col, id := "channel_payments", "request_id", r.PathValue("request_id")
		if rt.Op == "transaction_query" {
			col = "txn_id"
			id = r.PathValue("txn_id")
		}
		if rt.Op == "refund_query" {
			table = "channel_refunds"
		}
		if !d.ExternalID(id, 1, 80) || !d.ExternalID(r.URL.Query().Get("merchant_ref"), 1, 80) {
			e = d.Invalid("查询参数缺失或错误")
			break
		}
		v, e = a.Mock.Query(r.Context(), table, col, id, r.URL.Query().Get("merchant_ref"))
	case "rule":
		v, e = a.Mock.AddRule(r.Context(), b)
		status = 201
	case "replay":
		v, e = a.Mock.Replay(r.Context(), r.PathValue("event_id"), b.N("repeat_count"), b.N("delay_ms"))
		status = 202
	}
	if e != nil {
		a.fail(w, r, e)
		return
	}
	if timeout {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(2 * time.Second):
		}
	}
	a.respond(w, r, status, v, false)
}
