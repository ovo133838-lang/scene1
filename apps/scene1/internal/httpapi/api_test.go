package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/mockpay"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/service"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/testsupport"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/wire"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type fx struct {
	t      *testing.T
	a      *API
	m      *testsupport.Memory
	h      http.Handler
	tokens map[string]string
	p      Row
}

func fixture(t *testing.T) *fx {
	m := testsupport.New()
	s := &service.Service{Store: m, Secret: strings.Repeat("s", 32), Demo: true}
	if e := s.Seed(context.Background(), "demo-password-2026"); e != nil {
		t.Fatal(e)
	}
	a := &API{Shop: s, Demo: true, Secret: s.Secret, Admin: strings.Repeat("a", 32), Version: "unit-version"}
	f := &fx{t: t, a: a, m: m, tokens: map[string]string{}}
	f.h = a.Handler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	for _, role := range []string{"buyer1", "buyer2", "operator", "warehouse", "support"} {
		v, e := s.Login(context.Background(), role, "demo-password-2026")
		if e != nil {
			t.Fatal(e)
		}
		f.tokens[role] = v.(Row).S("token")
	}
	f.p = m.Tables["products"][0]
	f.do("PATCH", "/api/v1/operator/products/"+f.p.S("id"), Row{"version": 0, "reason": "上架", "sale_status": "ON_SHELF"}, "operator", 200)
	return f
}
func (f *fx) req(method, path string, b any, role string) *http.Request {
	raw, _ := json.Marshal(b)
	if b == nil {
		raw = nil
	}
	r := httptest.NewRequest(method, path, bytes.NewReader(raw))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("Idempotency-Key", repository.ID())
	if role == "admin" {
		r.Header.Set("Authorization", "Bearer "+f.a.Admin)
	} else if role == "signed" {
		security.Sign(r, raw, f.a.Secret)
	} else if role != "" {
		r.Header.Set("Authorization", "Bearer "+f.tokens[role])
	}
	return r
}
func (f *fx) call(r *http.Request, want int) Row {
	f.t.Helper()
	w := httptest.NewRecorder()
	f.h.ServeHTTP(w, r)
	if w.Code != want {
		f.t.Fatalf("%s %s: %d want %d: %s", r.Method, r.URL.Path, w.Code, want, w.Body)
	}
	var v Row
	if e := json.Unmarshal(w.Body.Bytes(), &v); e != nil {
		if want == 404 || want == 204 {
			return nil
		}
		f.t.Fatal(e, w.Body.String())
	}
	return v
}
func (f *fx) do(method, path string, b any, role string, want int) Row {
	f.t.Helper()
	v := f.call(f.req(method, path, b, role), want)
	out, _ := v["data"].(map[string]any)
	return Row(out)
}
func (f *fx) create() Row {
	return f.do("POST", "/api/v1/buyer/orders", Row{"product_id": f.p["id"], "quantity": 1}, "buyer1", 201)
}
func (f *fx) pay(o Row) {
	f.do("POST", "/api/v1/buyer/orders/"+o.S("id")+"/payments", Row{}, "buyer1", 202)
	var p Row
	f.m.Run(context.Background(), false, func(t repository.Unit) (any, error) {
		p = t.One("payment_intents", Row{"order_id": o["id"]})
		return nil, nil
	})
	ev := Row{"event_id": repository.ID(), "merchant_ref": "scene1", "order_ref": o["id"], "request_id": p["provider_request_id"], "txn_id": repository.ID(), "amount_cents": o["amount_cents"], "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}
	f.do("POST", "/api/v1/channel/payment-notifications", ev, "signed", 200)
}

func TestAuditCorrelationAndWarehouseWhitelist(t *testing.T) {
	f := fixture(t)
	r := f.req("POST", "/api/v1/buyer/orders", Row{"product_id": f.p["id"], "quantity": 1}, "buyer1")
	r.Header.Set("X-Request-Id", "caller-cannot-choose")
	pack := f.call(r, 201)
	id := Row(pack["meta"].(map[string]any)).S("request_id")
	o := Row(pack["data"].(map[string]any))
	found := false
	for _, a := range f.m.Tables["audit_events"] {
		if a.S("entity_id") == o.S("id") && a.S("action") == "CREATE" {
			found = a.S("request_id") == id
		}
	}
	if !found || id == "caller-cannot-choose" || id == "" {
		t.Fatal("audit must use server response request ID")
	}
	f.pay(o)
	page := f.do("GET", "/api/v1/warehouse/orders?limit=1", nil, "warehouse", 200)
	rows := page["items"].([]any)
	if len(rows) != 1 {
		t.Fatal(rows)
	}
	row := rows[0].(map[string]any)
	if len(row) != 6 || row["can_ship"] != true || row["created_at"] != nil || row["_sort_time"] != nil {
		t.Fatal(row)
	}
}
func TestRoleRoutesActionsAndViews(t *testing.T) {
	f := fixture(t)
	o := f.create()
	f.do("GET", "/api/v1/auth/me", nil, "buyer1", 200)
	f.do("GET", "/api/v1/products", nil, "buyer1", 200)
	f.do("GET", "/api/v1/buyer/orders/"+o.S("id"), nil, "buyer1", 200)
	f.pay(o)
	f.do("GET", "/api/v1/warehouse/orders", nil, "warehouse", 200)
	a := f.do("POST", "/api/v1/buyer/orders/"+o.S("id")+"/refund-applications", Row{"reason": "申请整单退"}, "buyer1", 201)
	f.do("GET", "/api/v1/support/refund-applications?status=PENDING", nil, "support", 200)
	f.do("GET", "/api/v1/support/orders/"+o.S("id"), nil, "support", 200)
	review := f.do("POST", "/api/v1/support/refund-applications/"+a.S("id")+"/review", Row{"decision": "APPROVE", "reason": "同意"}, "support", 200)
	r := Row(review["refund"].(map[string]any))
	f.do("POST", "/api/v1/support/refunds/"+r.S("id")+"/query", Row{"reason": "核查"}, "support", 202)
	f.do("POST", "/api/v1/support/refunds/"+r.S("id")+"/retry", Row{"reason": "不能重试"}, "support", 409)
	f.do("POST", "/api/v1/buyer/payments/"+f.do("GET", "/api/v1/buyer/orders/"+o.S("id"), nil, "buyer1", 200)["payment"].(map[string]any)["id"].(string)+"/query", Row{}, "buyer1", 202)
	for path, role := range map[string]string{"/api/v1/support/refunds": "support", "/api/v1/support/payment-anomalies": "support", "/api/v1/support/notifications": "support", "/api/v1/operator/products": "operator", "/api/v1/operator/orders": "operator", "/api/v1/operator/receipts": "operator", "/api/v1/operator/refunds": "operator", "/api/v1/operator/payment-anomalies": "operator", "/api/v1/operator/summary": "operator", "/api/v1/operator/orders/" + o.S("id") + "/reconciliation": "operator"} {
		f.do("GET", path, nil, role, 200)
	}
	o2 := f.create()
	f.do("POST", "/api/v1/buyer/orders/"+o2.S("id")+"/cancel", Row{"reason": "取消"}, "buyer1", 200)
	o3 := f.create()
	f.pay(o3)
	f.do("POST", "/api/v1/warehouse/orders/"+o3.S("id")+"/shipment", Row{"carrier": "快递", "tracking_no": "unit-track"}, "warehouse", 201)
	var p Row
	f.m.Run(context.Background(), false, func(t repository.Unit) (any, error) { p = t.One("products", Row{"id": f.p["id"]}); return nil, nil })
	f.do("POST", "/api/v1/operator/products/"+p.S("id")+"/inventory-adjustments", Row{"delta": 1, "version": p.N("version"), "reason": "补货"}, "operator", 201)
	f.do("GET", "/health/live", nil, "", 200)
	ready := f.do("GET", "/health/ready", nil, "", 200)
	if ready.S("version") != "unit-version" {
		t.Fatal(ready)
	}
	f.do("GET", "/internal/demo/clock", nil, "admin", 200)
	f.do("GET", "/internal/demo/clock", nil, "signed", 200)
	f.do("POST", "/internal/demo/clock/advance", Row{"seconds": 600}, "admin", 200)
	f.do("POST", "/internal/demo/clock/advance", Row{"seconds": 0}, "admin", 400)
	f.do("POST", "/api/v1/auth/logout", Row{}, "buyer1", 200)
	f.do("GET", "/api/v1/auth/me", nil, "buyer1", 401)
}
func TestAuthenticationValidationAndFailureResponses(t *testing.T) {
	f := fixture(t)
	f.do("POST", "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "demo-password-2026"}, "", 200)
	f.do("POST", "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "incorrect"}, "", 401)
	f.do("POST", "/api/v1/auth/login", Row{"login_name": "a", "password": "short"}, "", 400)
	f.do("GET", "/api/v1/auth/me", nil, "", 401)
	f.do("GET", "/api/v1/operator/summary", nil, "buyer1", 403)
	f.do("GET", "/api/v1/buyer/orders/bad", nil, "buyer1", 400)
	for path := range map[string]bool{"/api/v1/buyer/orders?limit=0": true, "/api/v1/buyer/orders?status=BAD": true, "/api/v1/buyer/orders?buyer_id=x": true, "/api/v1/buyer/orders?limit=1&limit=2": true, "/api/v1/buyer/orders?status=%20": true, "/api/v1/operator/orders?buyer_id=bad": true} {
		role := "buyer1"
		if strings.Contains(path, "operator") {
			role = "operator"
		}
		f.do("GET", path, nil, role, 400)
	}
	for _, b := range []Row{{"product_id": f.p["id"], "quantity": 1, "role": "OPERATOR"}, {"product_id": f.p["id"], "quantity": "1"}, {"product_id": f.p["id"]}} {
		f.do("POST", "/api/v1/buyer/orders", b, "buyer1", 400)
	}
	r := f.req("POST", "/api/v1/buyer/orders", Row{"product_id": f.p["id"], "quantity": 1}, "buyer1")
	r.Header.Del("Idempotency-Key")
	f.call(r, 400)
	r = f.req("POST", "/api/v1/buyer/orders", nil, "buyer1")
	f.call(r, 400)
	f.do("PATCH", "/api/v1/operator/products/"+f.p.S("id"), Row{"version": 1, "reason": "no changes"}, "operator", 400)
	f.do("PATCH", "/api/v1/operator/products/"+f.p.S("id"), Row{"version": 1, "reason": "bad enum", "sale_status": "BAD"}, "operator", 400)
	f.do("GET", "/internal/demo/clock", nil, "buyer1", 401)
	f.do("POST", "/internal/demo/clock/advance", Row{"seconds": 1}, "buyer1", 403)
	f.a.Demo = false
	f.do("GET", "/internal/demo/clock", nil, "admin", 404)
	f.do("POST", "/internal/demo/clock/advance", Row{"seconds": 1}, "admin", 404)
	f.a.Demo = true
	for i := 0; i < 31; i++ {
		f.a.limited("limit-ip")
	}
	if !f.a.limited("limit-ip") {
		t.Fatal("limit")
	}
	f.a.logins["old"] = loginWindow{start: time.Now().Add(-time.Hour)}
	for i := 0; i < 1002; i++ {
		f.a.logins[repository.ID()] = loginWindow{start: time.Now().Add(-time.Hour)}
	}
	f.a.limited("new-ip")
	f.a.logins["192.0.2.1"] = loginWindow{start: time.Now(), count: 31}
	f.do("POST", "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "password"}, "", 429)
	f.m.Failure = errors.New("secret-db-error")
	f.do("GET", "/health/ready", nil, "", 503)
	f.do("GET", "/api/v1/auth/me", nil, "buyer1", 503)
	f.do("POST", "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "password"}, "", 429)
}
func TestNotificationExceptionsAndAnomalyActions(t *testing.T) {
	f := fixture(t)
	o := f.create()
	ev := Row{"event_id": repository.ID(), "merchant_ref": "scene1", "order_ref": o["id"], "request_id": repository.ID(), "txn_id": repository.ID(), "amount_cents": "10000", "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}
	f.do("POST", "/api/v1/channel/payment-notifications", ev, "", 401)
	f.do("POST", "/api/v1/channel/payment-notifications", Row{}, "signed", 400)
	bad := Row{}
	for k, v := range ev {
		bad[k] = v
	}
	bad["status"] = "BAD"
	f.do("POST", "/api/v1/channel/payment-notifications", bad, "signed", 400)
	bad["status"] = "SUCCEEDED"
	bad["occurred_at"] = "bad"
	f.do("POST", "/api/v1/channel/payment-notifications", bad, "signed", 400)
	r1 := f.req("POST", "/api/v1/channel/payment-notifications", ev, "signed")
	r2 := f.req("POST", "/api/v1/channel/payment-notifications", ev, "signed")
	r2.Header = r1.Header.Clone()
	f.call(r1, 200)
	f.call(r2, 401)
	f.do("POST", "/api/v1/channel/refund-notifications", Row{"event_id": repository.ID(), "merchant_ref": "scene1", "request_id": repository.ID(), "txn_id": "unknown", "refund_id": "unknown", "amount_cents": "1", "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}, "signed", 200)
	var an Row
	f.m.Run(context.Background(), false, func(t repository.Unit) (any, error) {
		an = t.One("payment_anomalies", Row{"type": "INVALID_SIGNATURE"})
		return nil, nil
	})
	f.do("GET", "/api/v1/support/payment-anomalies/"+an.S("id"), nil, "support", 200)
	f.do("GET", "/api/v1/operator/payment-anomalies/"+an.S("id"), nil, "operator", 200)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { wire.Write(w, r, 404, Row{}, f.a.Secret) }))
	defer srv.Close()
	f.a.Channel = channel.New(srv.URL, f.a.Secret)
	f.do("POST", "/api/v1/support/payment-anomalies/"+an.S("id")+"/verify", Row{"reason": "核实"}, "support", 200)
	f.do("POST", "/api/v1/support/payment-anomalies/"+an.S("id")+"/resolve", Row{"reason": "无实际收款"}, "support", 200)
	f.do("POST", "/api/v1/support/payment-anomalies/"+an.S("id")+"/refund", Row{"reason": "不可退款"}, "support", 409)
	f.m.Failure = errors.New("down")
	f.do("POST", "/api/v1/channel/payment-notifications", ev, "signed", 503)
}
func TestMockRoutesAndControls(t *testing.T) {
	m := testsupport.New()
	m.Mock = true
	p := &mockpay.Provider{Store: m, Demo: false}
	a := &API{Mock: p, Secret: strings.Repeat("s", 32), Admin: strings.Repeat("a", 32), Demo: true}
	f := &fx{t: t, a: a, m: m, h: a.Handler(nil), tokens: map[string]string{}}
	b := Row{"merchant_ref": "scene1", "request_id": repository.ID(), "order_ref": repository.ID(), "amount_cents": "10000", "currency": "CNY"}
	v := f.do("POST", "/mock/v1/payments", b, "signed", 200)
	f.do("GET", "/mock/v1/payments/by-request/"+b.S("request_id")+"?merchant_ref=scene1", nil, "signed", 200)
	f.do("GET", "/mock/v1/transactions/"+v.S("txn_id")+"?merchant_ref=scene1", nil, "signed", 200)
	refund := Row{"merchant_ref": "scene1", "request_id": repository.ID(), "txn_id": v["txn_id"], "amount_cents": "10000", "currency": "CNY"}
	f.do("POST", "/mock/v1/refunds", refund, "signed", 200)
	f.do("GET", "/mock/v1/refunds/by-request/"+refund.S("request_id")+"?merchant_ref=scene1", nil, "signed", 200)
	f.do("GET", "/mock/v1/payments/by-request/a", nil, "signed", 400)
	f.do("GET", "/mock/v1/transactions/a?merchant_ref=scene1", nil, "signed", 404)
	f.do("POST", "/mock/admin/rules", Row{"target_order_ref": "order", "operation": "PAYMENT", "mode": "SUCCESS"}, "admin", 201)
	f.do("POST", "/mock/admin/rules", Row{"target_order_ref": "order", "operation": "PAYMENT", "mode": "BAD"}, "admin", 400)
	f.do("POST", "/mock/admin/rules", Row{"target_order_ref": "order", "operation": "PAYMENT", "mode": "SUCCESS"}, "", 403)
	var event string
	m.Run(context.Background(), false, func(t repository.Unit) (any, error) {
		event = t.One("notification_jobs", nil).S("event_id")
		return nil, nil
	})
	f.do("POST", "/mock/admin/notifications/"+event+"/replay", Row{"repeat_count": 2, "delay_ms": 0}, "admin", 202)
	f.do("GET", "/health/live", nil, "", 200)
	f.do("POST", "/mock/v1/payments", b, "", 401)
	bad := Row{}
	for k, v := range b {
		bad[k] = v
	}
	bad["request_id"] = "x"
	f.do("POST", "/mock/v1/payments", bad, "signed", 400)
	r := f.req("GET", "/mock/v1/transactions/"+v.S("txn_id")+"?merchant_ref=scene1", nil, "signed")
	r2 := f.req("GET", r.URL.String(), nil, "signed")
	r2.Header = r.Header.Clone()
	f.call(r, 200)
	f.call(r2, 401)
	r = httptest.NewRequest("OPTIONS", "/mock/admin/rules", nil)
	r.Header.Set("Origin", "http://127.0.0.1:18080")
	f.call(r, 204)
	a.Demo = false
	f.do("POST", "/mock/admin/rules", Row{"target_order_ref": "order", "operation": "PAYMENT", "mode": "SUCCESS"}, "admin", 404)
}
