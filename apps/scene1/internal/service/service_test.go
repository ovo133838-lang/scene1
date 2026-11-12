package service

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/testsupport"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/wire"
)

var ctx = context.Background()

type fixture struct {
	s                                *Service
	m                                *testsupport.Memory
	buyer, other, op, wh, support, p Row
	t                                *testing.T
}

func setup(t *testing.T) *fixture {
	t.Helper()
	m := testsupport.New()
	s := &Service{Store: m, Secret: strings.Repeat("s", 32), Demo: true}
	if e := s.Seed(ctx, "demo-password-2026"); e != nil {
		t.Fatal(e)
	}
	f := &fixture{s: s, m: m, t: t}
	for _, a := range m.Tables["accounts"] {
		switch a.S("login_name") {
		case "buyer1":
			f.buyer = a
		case "buyer2":
			f.other = a
		case "operator":
			f.op = a
		case "warehouse":
			f.wh = a
		case "support":
			f.support = a
		}
	}
	f.p = m.Tables["products"][0]
	f.exec(f.op, "update_product", f.p.S("id"), Row{"version": int64(0), "sale_status": "ON_SHELF", "reason": "上架"})
	return f
}
func (f *fixture) exec(a Row, op, id string, b Row) Row {
	f.t.Helper()
	r, e := f.s.Exec(ctx, a, op, id, repository.ID(), b)
	if e != nil {
		f.t.Fatal(op, e)
	}
	v, _ := r.Data.(Row)
	return v
}
func (f *fixture) bad(a Row, op, id string, b Row) {
	f.t.Helper()
	if _, e := f.s.Exec(ctx, a, op, id, repository.ID(), b); e == nil {
		f.t.Fatal("expected rejection", op)
	}
}
func (f *fixture) create() Row {
	return f.exec(f.buyer, "create_order", "", Row{"product_id": f.p["id"], "quantity": int64(1)})
}
func (f *fixture) detail(o Row) Row {
	v, e := f.s.Read(ctx, f.buyer, "order", o.S("id"), Row{}, 20, "")
	if e != nil {
		f.t.Fatal(e)
	}
	return v.(Row)
}
func (f *fixture) paid(o Row) Row {
	p := f.exec(f.buyer, "pay", o.S("id"), Row{})
	var request string
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) {
		request = t.One("payment_intents", Row{"id": p["id"]}).S("provider_request_id")
		return nil, nil
	})
	ev := Row{"event_id": repository.ID(), "merchant_ref": "scene1", "request_id": request, "order_ref": o["id"], "txn_id": repository.ID(), "amount_cents": o["amount_cents"], "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}
	if _, e := f.s.Ingest(ctx, "PAYMENT", ev, repository.ID(), "", repository.ID()); e != nil {
		f.t.Fatal(e)
	}
	return ev
}
func (f *fixture) refundEvent(r Row, status string) Row {
	var a, receipt Row
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) {
		rr := t.One("refunds", Row{"id": r["id"]})
		a = t.One("refund_attempts", Row{"id": rr["current_attempt_id"]})
		receipt = t.One("receipts", Row{"id": rr["receipt_id"]})
		return nil, nil
	})
	return Row{"merchant_ref": "scene1", "request_id": a["provider_request_id"], "txn_id": receipt["provider_txn_id"], "refund_id": repository.ID(), "amount_cents": r["amount_cents"], "currency": "CNY", "status": status, "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}
}
func (f *fixture) notify(kind string, b Row) Row {
	v, e := f.s.Ingest(ctx, kind, b, repository.ID(), "", repository.ID())
	if e != nil {
		f.t.Fatal(e)
	}
	return v.(Row)
}
func TestIdentityAndStorageFailure(t *testing.T) {
	f := setup(t)
	if e := f.s.Seed(ctx, "demo-password-2026"); e != nil {
		t.Fatal(e)
	}
	if e := f.s.Seed(ctx, "short"); e == nil {
		t.Fatal("password")
	}
	if _, e := f.s.Login(ctx, "buyer1", "bad"); e == nil {
		t.Fatal("bad password")
	}
	v, e := f.s.Login(ctx, "buyer1", "demo-password-2026")
	if e != nil {
		t.Fatal(e)
	}
	token := v.(Row).S("token")
	if a, e := f.s.Auth(ctx, token); e != nil || a.S("id") != f.buyer.S("id") {
		t.Fatal(a, e)
	}
	if e = f.s.Logout(ctx, token); e != nil {
		t.Fatal(e)
	}
	if _, e = f.s.Auth(ctx, token); e == nil {
		t.Fatal("revoked")
	}
	f.s.Logout(ctx, "unknown")
	if _, e = f.s.Auth(ctx, "fake"); e == nil {
		t.Fatal("fake")
	}
	f.m.Run(ctx, true, func(t repository.Unit) (any, error) {
		t.Patch("accounts", t.One("accounts", Row{"id": f.buyer["id"]}), Row{"enabled": false})
		return nil, nil
	})
	if _, e = f.s.Login(ctx, "buyer1", "demo-password-2026"); e == nil {
		t.Fatal("disabled")
	}
	f.m.Failure = errors.New("db down")
	if _, e = f.s.Auth(ctx, token); e == nil {
		t.Fatal("storage")
	}
	if _, e = f.s.Exec(ctx, f.buyer, "pay", "", repository.ID(), Row{}); e == nil {
		t.Fatal("storage")
	}
	if e = f.s.Seed(ctx, "demo-password-2026"); e == nil {
		t.Fatal("init failure")
	}
}
func TestOrderStockIdempotencyExpiryAndShipment(t *testing.T) {
	f := setup(t)
	f.bad(f.buyer, "create_order", "", Row{"product_id": f.p["id"], "quantity": int64(3)})
	f.bad(f.buyer, "create_order", "", Row{"product_id": repository.ID(), "quantity": int64(1)})
	key := repository.ID()
	b := Row{"product_id": f.p["id"], "quantity": int64(2)}
	r, e := f.s.Exec(ctx, f.buyer, "create_order", "", key, b)
	if e != nil {
		t.Fatal(e)
	}
	again, e := f.s.Exec(ctx, f.buyer, "create_order", "", key, b)
	if e != nil || !again.Replayed || again.Data.(Row).S("id") != r.Data.(Row).S("id") {
		t.Fatal(again, e)
	}
	b["quantity"] = int64(1)
	if _, e = f.s.Exec(ctx, f.buyer, "create_order", "", key, b); e == nil {
		t.Fatal("key conflict")
	}
	o := r.Data.(Row)
	f.bad(f.other, "cancel", o.S("id"), Row{"reason": "越权"})
	if _, e = f.s.Read(ctx, f.other, "order", o.S("id"), Row{}, 20, ""); e == nil {
		t.Fatal("ownership")
	}
	f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "取消"})
	f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "重关"})
	f.bad(f.buyer, "pay", o.S("id"), Row{})
	o = f.create()
	f.s.Clock(ctx, 600)
	f.bad(f.buyer, "pay", o.S("id"), Row{})
	if f.detail(o).S("status") != "CLOSED" {
		t.Fatal("expiration rollback")
	}
	o = f.create()
	f.s.Clock(ctx, 600)
	f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "过期"})
	o = f.create()
	f.s.Clock(ctx, 600)
	if e = f.s.Expire(ctx); e != nil {
		t.Fatal(e)
	}
	if e = f.s.Expire(ctx); e != nil {
		t.Fatal(e)
	}
	o = f.create()
	f.paid(o)
	f.bad(f.buyer, "cancel", o.S("id"), Row{"reason": "已付"})
	f.bad(f.buyer, "pay", o.S("id"), Row{})
	f.exec(f.wh, "ship", o.S("id"), Row{"carrier": "快递", "tracking_no": "T1"})
	f.bad(f.wh, "ship", o.S("id"), Row{"carrier": "快递", "tracking_no": "T2"})
	f.bad(f.buyer, "apply", o.S("id"), Row{"reason": "已发"})
	detail := f.detail(o)
	if detail.S("status") != "SHIPPED" || detail["shipment"].(Row).S("tracking_no") != "T1" {
		t.Fatal(detail)
	}
	f.m.Run(ctx, true, func(t repository.Unit) (any, error) {
		p := t.One("products", Row{"id": f.p["id"]})
		p["available_quantity"] = int64(0)
		p["sale_status"] = "ON_SHELF"
		return nil, nil
	})
	f.bad(f.buyer, "create_order", "", Row{"product_id": f.p["id"], "quantity": int64(1)})
	f.m.Run(ctx, true, func(t repository.Unit) (any, error) {
		t.One("products", Row{"id": f.p["id"]})["sale_status"] = "OFF_SHELF"
		return nil, nil
	})
	f.bad(f.buyer, "create_order", "", Row{"product_id": f.p["id"], "quantity": int64(1)})
	f.bad(f.buyer, "unknown", "", Row{})
}
func TestRefundReviewFreezeRetryAndSettlement(t *testing.T) {
	f := setup(t)
	o := f.create()
	ev := f.paid(o)
	a := f.exec(f.buyer, "apply", o.S("id"), Row{"reason": "不需要"})
	f.bad(f.wh, "ship", o.S("id"), Row{"carrier": "x", "tracking_no": "t"})
	f.bad(f.buyer, "apply", o.S("id"), Row{"reason": "重复"})
	f.bad(f.support, "review", a.S("id"), Row{"decision": "BAD", "reason": "x"})
	f.bad(f.support, "review", repository.ID(), Row{"decision": "APPROVE", "reason": "x"})
	f.exec(f.support, "review", a.S("id"), Row{"decision": "REJECT", "reason": "核实后拒绝"})
	f.exec(f.support, "review", a.S("id"), Row{"decision": "REJECT", "reason": "不覆盖原原因"})
	f.bad(f.support, "review", a.S("id"), Row{"decision": "APPROVE", "reason": "反转"})
	a = f.exec(f.buyer, "apply", o.S("id"), Row{"reason": "再申请"})
	r := f.exec(f.support, "review", a.S("id"), Row{"decision": "APPROVE", "reason": "同意"})["refund"].(Row)
	f.bad(f.support, "retry_refund", r.S("id"), Row{"reason": "未失败"})
	f.exec(f.support, "query_refund", r.S("id"), Row{"reason": "核查"})
	failed := f.refundEvent(r, "FAILED")
	f.notify("REFUND", failed)
	if f.detail(o).S("status") != "REFUND_PROCESSING" {
		t.Fatal("failed unfreezes")
	}
	f.notify("REFUND", failed)
	bad := Row{}
	for k, v := range failed {
		bad[k] = v
	}
	bad["status"] = "SUCCEEDED"
	if f.notify("REFUND", bad).S("result") != "RESULT_CONFLICT" {
		t.Fatal("terminal contradiction")
	}
	f.bad(f.support, "retry_refund", r.S("id"), Row{"reason": "冲突必须先核实"})
	failed["_channel_query"] = true
	f.m.Run(ctx, true, func(u repository.Unit) (any, error) { return f.s.applyRefund(u, failed, nil), nil })
	f.exec(f.support, "retry_refund", r.S("id"), Row{"reason": "明确失败重试"})
	good := f.refundEvent(r, "SUCCEEDED")
	f.notify("REFUND", good)
	f.notify("REFUND", good)
	if f.detail(o).S("status") != "REFUNDED" {
		t.Fatal("not refunded")
	}
	f.bad(f.support, "retry_refund", r.S("id"), Row{"reason": "不能重复退"})
	bad["amount_cents"] = "1"
	f.notify("REFUND", bad)
	f.notify("REFUND", Row{"request_id": "unknown"})
	f.notify("PAYMENT", ev)
	v, e := f.s.Read(ctx, f.op, "reconciliation", o.S("id"), Row{}, 20, "")
	if e != nil || v.(Row).S("refunded_cents") != "10000" {
		t.Fatal(v, e)
	}
	if x, e := f.s.Read(ctx, f.op, "summary", "", Row{}, 20, ""); e != nil || x.(Row).S("net_cents") != "0" {
		t.Fatal(x, e)
	}
}
func TestAdjustmentPaginationAndReadModels(t *testing.T) {
	f := setup(t)
	for _, op := range []string{"adjust", "update_product"} {
		f.bad(f.op, op, repository.ID(), Row{"version": int64(0)})
		f.bad(f.op, op, f.p.S("id"), Row{"version": int64(999)})
	}
	var p Row
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) { p = t.One("products", Row{"id": f.p["id"]}); return nil, nil })
	for _, n := range []int64{0, -10, 1000001} {
		f.bad(f.op, "adjust", p.S("id"), Row{"version": p.N("version"), "delta": n, "reason": "调整"})
	}
	entry := f.exec(f.op, "adjust", p.S("id"), Row{"version": p.N("version"), "delta": int64(3), "reason": "补货"})
	if entry.N("available_after") != 8 {
		t.Fatal(entry)
	}
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) { p = t.One("products", Row{"id": f.p["id"]}); return nil, nil })
	f.bad(f.op, "update_product", p.S("id"), Row{"version": p.N("version"), "unit_price_cents": "0", "reason": "非法"})
	f.exec(f.op, "update_product", p.S("id"), Row{"version": p.N("version"), "name": "更新商品", "unit_price_cents": "20000", "reason": "调价"})
	o1 := f.create()
	o2 := f.create()
	f.paid(o1)
	f.exec(f.buyer, "apply", o1.S("id"), Row{"reason": "x"})
	f.exec(f.buyer, "cancel", o2.S("id"), Row{"reason": "x"})
	for _, kind := range []string{"products", "orders", "warehouse", "refund_applications", "refunds", "payment_anomalies", "channel_notifications", "receipts"} {
		for _, actor := range []Row{f.buyer, f.op, f.support} {
			if _, e := f.s.Read(ctx, actor, kind, "", Row{}, 20, ""); e != nil {
				t.Fatal(kind, e)
			}
		}
	}
	v, e := f.s.Read(ctx, f.buyer, "orders", "", Row{}, 1, "")
	if e != nil {
		t.Fatal(e)
	}
	page := v.(Row)
	cursor := page.S("next_cursor")
	if cursor == "" {
		t.Fatal(page)
	}
	second, e := f.s.Read(ctx, f.buyer, "orders", "", Row{}, 1, cursor)
	if e != nil || second.(Row)["items"].([]Row)[0].S("id") == page["items"].([]Row)[0].S("id") {
		t.Fatal(second, e)
	}
	if _, e = f.s.Read(ctx, f.buyer, "orders", "", Row{}, 1, "bad"); e == nil {
		t.Fatal("cursor")
	}
	f.s.Read(ctx, f.op, "summary", "", Row{"product_id": p["id"]}, 20, "")
	if _, e = f.s.Read(ctx, f.op, "anomaly", repository.ID(), Row{}, 20, ""); e == nil {
		t.Fatal("missing")
	}
	if f.s.Fingerprint() == "" {
		t.Fatal("fingerprint")
	}
}
func TestTwentyConcurrentUnitCommandsAndRace(t *testing.T) {
	f := setup(t)
	var wg sync.WaitGroup
	var mu sync.Mutex
	won := []Row{}
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			r, e := f.s.Exec(ctx, f.buyer, "create_order", "", repository.ID(), Row{"product_id": f.p["id"], "quantity": int64(1)})
			if e == nil {
				mu.Lock()
				won = append(won, r.Data.(Row))
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if len(won) != 5 {
		t.Fatal(len(won))
	}
	for _, o := range won {
		f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "释放"})
	}
	o := f.create()
	f.paid(o)
	count := 0
	for _, op := range []string{"apply", "ship"} {
		wg.Add(1)
		go func(op string) {
			defer wg.Done()
			actor, b := f.buyer, Row{"reason": "race"}
			if op == "ship" {
				actor = f.wh
				b = Row{"carrier": "x", "tracking_no": "x"}
			}
			_, e := f.s.Exec(ctx, actor, op, o.S("id"), repository.ID(), b)
			if e == nil {
				mu.Lock()
				count++
				mu.Unlock()
			}
		}(op)
	}
	wg.Wait()
	if count != 1 {
		t.Fatal(count)
	}
}
func TestPaymentsAnomaliesAndWorkerRecovery(t *testing.T) {
	f := setup(t)
	o := f.create()
	p := f.exec(f.buyer, "pay", o.S("id"), Row{})
	same := f.exec(f.buyer, "pay", o.S("id"), Row{})
	if same.S("id") != p.S("id") {
		t.Fatal("two intents")
	}
	f.exec(f.buyer, "query_payment", p.S("id"), Row{})
	f.bad(f.other, "query_payment", p.S("id"), Row{})
	f.bad(f.buyer, "query_payment", repository.ID(), Row{})
	f.bad(f.support, "query_refund", repository.ID(), Row{})
	status := "SUCCEEDED"
	var payment Row
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var b Row
		json.NewDecoder(r.Body).Decode(&b)
		if r.Method == "POST" {
			payment = Row{"merchant_ref": "scene1", "request_id": b["request_id"], "order_ref": o["id"], "txn_id": "txn-unit", "amount_cents": o["amount_cents"], "currency": "CNY", "status": status, "paid_at": time.Now().UTC().Format(time.RFC3339Nano)}
		}
		wire.Write(w, r, 200, Row{"data": payment}, f.s.Secret)
	}))
	defer srv.Close()
	client := channel.New(srv.URL, f.s.Secret)
	if e := f.s.WorkOnce(ctx, client); e != nil {
		t.Fatal(e)
	}
	if f.detail(o).S("status") != "PENDING_SHIPMENT" {
		t.Fatal("worker settlement")
	}
	f.s.WorkOnce(ctx, client)
	f.s.WorkOnce(ctx, client)
	// Invalid/replayed notifications are retained but cannot add funds.
	fake := Row{"event_id": repository.ID(), "merchant_ref": "scene1", "request_id": "req-unit", "order_ref": repository.ID(), "txn_id": "fake-txn", "amount_cents": "10", "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)}
	for _, auth := range []string{"INVALID_SIGNATURE", "INVALID_BODY"} {
		if _, e := f.s.Ingest(ctx, "PAYMENT", fake, repository.ID(), auth, repository.ID()); e != nil {
			t.Fatal(e)
		}
	}
	nonce := repository.ID()
	f.s.Ingest(ctx, "PAYMENT", fake, "x", "", nonce)
	v, e := f.s.Ingest(ctx, "PAYMENT", fake, "x", "", nonce)
	if e != nil || v.(Row).S("result") != "REPLAYED_SIGNATURE" {
		t.Fatal(v, e)
	}
	f.m.Run(ctx, true, func(t repository.Unit) (any, error) {
		for _, j := range t.All("outbox_jobs", nil) {
			t.Patch("outbox_jobs", j, Row{"status": "DONE"})
		}
		return nil, nil
	})
	o2 := f.create()
	f.exec(f.buyer, "pay", o2.S("id"), Row{})
	badClient := channel.New("http://127.0.0.1:1", f.s.Secret)
	if e := f.s.WorkOnce(ctx, badClient); e != nil {
		t.Fatal(e)
	}
	if f.detail(o2)["payment"].(Row).S("status") != "UNKNOWN" {
		t.Fatal("timeout must be unknown")
	}
	f.m.Failure = errors.New("storage")
	if f.s.WorkOnce(ctx, client) == nil {
		t.Fatal("storage")
	}
}
func TestLateAndUnverifiedMoneyRequiresTrustedQuery(t *testing.T) {
	f := setup(t)
	o := f.create()
	f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "取消"})
	b := Row{"merchant_ref": "scene1", "request_id": "external-request", "order_ref": o["id"], "txn_id": "external-txn", "amount_cents": "10000", "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano), "paid_at": time.Now().UTC().Format(time.RFC3339Nano)}
	f.notify("PAYMENT", b)
	var an Row
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) { an = t.One("payment_anomalies", nil); return nil, nil })
	f.bad(f.support, "refund_anomaly", an.S("id"), Row{"reason": "未核实"})
	f.bad(f.support, "resolve_anomaly", an.S("id"), Row{"reason": "不能忽略"})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { wire.Write(w, r, 200, Row{"data": b}, f.s.Secret) }))
	defer srv.Close()
	c := channel.New(srv.URL, f.s.Secret)
	key := repository.ID()
	v, e := f.s.VerifyAnomaly(ctx, c, f.support, an.S("id"), key, "核实")
	if e != nil || v.Data.(Row).S("verification") != "FUNDS_CONFIRMED" {
		t.Fatal(v, e)
	}
	replay, e := f.s.VerifyAnomaly(ctx, c, f.support, an.S("id"), key, "核实")
	if e != nil || !replay.Replayed {
		t.Fatal(replay, e)
	}
	if _, e = f.s.VerifyAnomaly(ctx, c, f.support, an.S("id"), key, "不同原因"); e == nil {
		t.Fatal("conflict")
	}
	r := f.exec(f.support, "refund_anomaly", an.S("id"), Row{"reason": "退回"})
	f.notify("REFUND", f.refundEvent(r, "SUCCEEDED"))
	again := f.exec(f.support, "refund_anomaly", an.S("id"), Row{"reason": "重复"})
	if again.S("id") != r.S("id") || f.detail(o).S("status") != "CLOSED" {
		t.Fatal("exception state")
	}
	noFunds := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { wire.Write(w, r, 404, Row{}, f.s.Secret) }))
	defer noFunds.Close()
	fake := Row{"txn_id": "not-real"}
	f.s.Ingest(ctx, "PAYMENT", fake, "newhash", "INVALID_SIGNATURE", repository.ID())
	f.m.Run(ctx, false, func(t repository.Unit) (any, error) {
		an = t.One("payment_anomalies", Row{"dedupe_key": "INVALID_SIGNATURE:newhash"})
		return nil, nil
	})
	if _, e = f.s.VerifyAnomaly(ctx, channel.New(noFunds.URL, f.s.Secret), f.support, an.S("id"), repository.ID(), "查无资金"); e != nil {
		t.Fatal(e)
	}
	f.exec(f.support, "resolve_anomaly", an.S("id"), Row{"reason": "可信无资金"})
	if _, e = f.s.VerifyAnomaly(ctx, c, f.support, repository.ID(), repository.ID(), "不存在"); e == nil {
		t.Fatal("missing")
	}
	f.s.Read(ctx, f.support, "anomaly", an.S("id"), Row{}, 20, "")
	_ = d.CanShip(nil)
}
