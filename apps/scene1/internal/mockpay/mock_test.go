package mockpay

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/testsupport"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/wire"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

var ctx = context.Background()

func fixture(t *testing.T) (*Provider, *testsupport.Memory, *int) {
	m := testsupport.New()
	m.Mock = true
	code := 200
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		data := Row{"business_now": time.Now().UTC().Format(time.RFC3339Nano)}
		if r.Method == "POST" {
			var b Row
			if e := json.NewDecoder(r.Body).Decode(&b); e != nil {
				t.Error(e)
			}
			if b["event_id"] == nil {
				t.Error("missing event")
			}
		}
		wire.Write(w, r, code, Row{"data": data}, strings.Repeat("s", 32))
	}))
	t.Cleanup(srv.Close)
	return &Provider{Store: m, Shop: channel.New(srv.URL, strings.Repeat("s", 32)), Demo: true}, m, &code
}
func payment(order string) Row {
	return Row{"merchant_ref": "scene1", "request_id": repository.ID(), "order_ref": order, "amount_cents": "10000", "currency": "CNY"}
}
func TestProviderIdempotencyAndMoneyGuards(t *testing.T) {
	p, m, _ := fixture(t)
	b := payment(repository.ID())
	v, timeout, e := p.Create(ctx, false, b)
	if e != nil || timeout || v.(Row).S("status") != "SUCCEEDED" {
		t.Fatal(v, timeout, e)
	}
	paid := v.(Row)
	v, _, e = p.Create(ctx, false, b)
	if e != nil || v.(Row).S("txn_id") != paid.S("txn_id") {
		t.Fatal(v, e)
	}
	b["amount_cents"] = "9999"
	if _, _, e = p.Create(ctx, false, b); e == nil {
		t.Fatal("changed")
	}
	b["amount_cents"] = "0"
	if _, _, e = p.Create(ctx, false, b); e == nil {
		t.Fatal("money")
	}
	b["amount_cents"] = "10000"
	b["merchant_ref"] = "other"
	if _, _, e = p.Create(ctx, false, b); e == nil {
		t.Fatal("merchant")
	}
	if _, e = p.Query(ctx, "channel_payments", "txn_id", paid.S("txn_id"), "scene1"); e != nil {
		t.Fatal(e)
	}
	if _, e = p.Query(ctx, "channel_payments", "txn_id", "missing", "scene1"); e == nil {
		t.Fatal("not found")
	}
	r := Row{"merchant_ref": "scene1", "request_id": repository.ID(), "txn_id": paid["txn_id"], "amount_cents": "10000", "currency": "CNY"}
	v, _, e = p.Create(ctx, true, r)
	if e != nil || v.(Row).S("status") != "SUCCEEDED" {
		t.Fatal(v, e)
	}
	v2, _, e := p.Create(ctx, true, r)
	if e != nil || v2.(Row).S("refund_id") != v.(Row).S("refund_id") {
		t.Fatal(v2, e)
	}
	r["request_id"] = repository.ID()
	if _, _, e = p.Create(ctx, true, r); e == nil {
		t.Fatal("overrefund")
	}
	r["txn_id"] = "missing"
	if _, _, e = p.Create(ctx, true, r); e == nil {
		t.Fatal("not paid")
	}
	if e = p.Nonce(ctx, "unique"); e != nil {
		t.Fatal(e)
	}
	if e = p.Nonce(ctx, "unique"); e == nil {
		t.Fatal("replay")
	}
	m.Failure = errors.New("db")
	if e = p.Nonce(ctx, "new"); e == nil {
		t.Fatal("storage")
	}
}
func TestRuleModesRetryUnknownAndNotifications(t *testing.T) {
	for _, mode := range []string{"SUCCESS", "EXPLICIT_FAIL", "TIMEOUT_AFTER_SUCCESS", "PENDING", "DELAY_NOTIFY", "DUPLICATE_NOTIFY"} {
		t.Run(mode, func(t *testing.T) {
			p, m, code := fixture(t)
			b := payment(repository.ID())
			rule := Row{"target_order_ref": b["order_ref"], "operation": "PAYMENT", "mode": mode, "delay_ms": int64(0), "repeat_count": int64(2), "remaining_uses": int64(1)}
			if _, e := p.AddRule(ctx, rule); e != nil {
				t.Fatal(e)
			}
			v, timeout, e := p.Create(ctx, false, b)
			if e != nil || timeout != (mode == "TIMEOUT_AFTER_SUCCESS") {
				t.Fatal(v, timeout, e)
			}
			if mode == "PENDING" {
				if v.(Row).S("status") != "PENDING" || len(m.Tables["notification_jobs"]) != 0 {
					t.Fatal(v)
				}
				return
			}
			if mode == "EXPLICIT_FAIL" && v.(Row).S("status") != "FAILED" {
				t.Fatal(v)
			}
			m.Run(ctx, true, func(u repository.Unit) (any, error) {
				for _, j := range u.All("notification_jobs", nil) {
					u.Patch("notification_jobs", j, Row{"deliver_after": time.Now().Add(-time.Second)})
				}
				return nil, nil
			})
			if e = p.DeliverOnce(ctx); e != nil {
				t.Fatal(e)
			}
			var event string
			m.Run(ctx, false, func(u repository.Unit) (any, error) {
				event = u.One("notification_jobs", nil).S("event_id")
				return nil, nil
			})
			if _, e = p.Replay(ctx, event, 2, 0); e != nil {
				t.Fatal(e)
			}
			*code = 503
			if e = p.DeliverOnce(ctx); e != nil {
				t.Fatal(e)
			}
			*code = 200
			p.DeliverOnce(ctx)
			for _, arg := range [][2]int64{{0, 0}, {21, 0}, {1, -1}, {1, 600001}} {
				if _, e = p.Replay(ctx, event, arg[0], arg[1]); e == nil {
					t.Fatal(arg)
				}
			}
			if _, e = p.Replay(ctx, "missing", 1, 0); e == nil {
				t.Fatal("missing")
			}
		})
	}
	p, _, _ := fixture(t)
	b := payment(repository.ID())
	v, _, _ := p.Create(ctx, false, b)
	paid := v.(Row)
	p.AddRule(ctx, Row{"target_order_ref": b["order_ref"], "operation": "REFUND", "mode": "EXPLICIT_FAIL", "attempt_no": int64(1)})
	r := Row{"merchant_ref": "scene1", "request_id": repository.ID(), "txn_id": paid["txn_id"], "amount_cents": "10000", "currency": "CNY"}
	v, _, e := p.Create(ctx, true, r)
	if e != nil || v.(Row).S("status") != "FAILED" {
		t.Fatal(v, e)
	}
	r["request_id"] = repository.ID()
	v, _, e = p.Create(ctx, true, r)
	if e != nil || v.(Row).S("status") != "SUCCEEDED" {
		t.Fatal(v, e)
	}
	for i := 0; i < 3; i++ {
		if e = p.DeliverOnce(ctx); e != nil {
			t.Fatal(e)
		}
	}
	for _, bad := range []Row{{"repeat_count": int64(0)}, {"remaining_uses": int64(21)}, {"delay_ms": int64(600001)}, {"attempt_no": int64(0)}} {
		if _, e = p.AddRule(ctx, bad); e == nil {
			t.Fatal(bad)
		}
	}
	p.Demo = false
	if now, e := p.clock(ctx); e != nil || now.IsZero() {
		t.Fatal(now, e)
	}
	p.Demo = true
	p.Shop = channel.New("http://127.0.0.1:1", "secret")
	if _, _, e = p.Create(ctx, false, payment("x")); e == nil {
		t.Fatal("clock unavailable")
	}
}
