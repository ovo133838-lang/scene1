// Package mockpay is a controllable HTTP payment provider with its own database credentials.
package mockpay

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
)

type Row = repository.Row
type Provider struct {
	Store         repository.Database
	Shop          *channel.Client
	Secret, Admin string
	Demo          bool
}

func (p *Provider) clock(ctx context.Context) (time.Time, error) {
	if !p.Demo {
		return time.Now().UTC(), nil
	}
	v, e := p.Shop.Do(ctx, "GET", "/internal/demo/clock", nil)
	if e != nil {
		return time.Time{}, e
	}
	return time.Parse(time.RFC3339Nano, v.S("business_now"))
}
func (p *Provider) Nonce(ctx context.Context, nonce string) error {
	_, e := p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		if t.One("auth_nonces", Row{"key_id": "shop-to-mock", "nonce": nonce}) != nil {
			return nil, d.Fail("REPLAYED_SIGNATURE", 401, "签名已使用")
		}
		t.Add("auth_nonces", Row{"key_id": "shop-to-mock", "nonce": nonce, "expires_at": time.Now().UTC().Add(10 * time.Minute)})
		return nil, nil
	})
	return e
}
func safe(r Row) Row {
	out := Row{}
	for _, k := range strings.Fields("merchant_ref request_id order_ref txn_id refund_id amount_cents currency status paid_at refunded_at failure_code") {
		if v, ok := r[k]; ok {
			if k == "amount_cents" {
				v = fmt.Sprint(r.N(k))
			}
			out[k] = v
		}
	}
	if _, ok := out["currency"]; !ok {
		out["currency"] = "CNY"
	}
	return out
}
func (p *Provider) Query(ctx context.Context, table, col, id, merchant string) (any, error) {
	return p.Store.Run(ctx, false, func(t repository.Unit) (any, error) {
		r := t.One(table, Row{col: id, "merchant_ref": merchant})
		if e := d.Require(r); e != nil {
			return nil, e
		}
		return safe(r), nil
	})
}
func (p *Provider) rule(t repository.Unit, operation, order, request string, attempt int64) Row {
	for _, r := range t.All("simulation_rules", Row{"target_order_ref": order}) {
		if r.N("remaining_uses") < 1 || r.S("operation") != operation {
			continue
		}
		if r.S("target_request_id") != "" && r.S("target_request_id") != request {
			continue
		}
		if r["attempt_no"] != nil && r.N("attempt_no") != attempt {
			continue
		}
		t.Patch("simulation_rules", r, Row{"remaining_uses": r.N("remaining_uses") - 1})
		return r
	}
	return Row{"mode": "SUCCESS", "delay_ms": int64(0), "repeat_count": int64(1)}
}
func (p *Provider) createJob(t repository.Unit, kind, resource string, rule Row) {
	delay := rule.N("delay_ms")
	count := int64(1)
	if rule.S("mode") == "DUPLICATE_NOTIFY" {
		count = rule.N("repeat_count")
	}
	if rule.S("mode") == "TIMEOUT_AFTER_SUCCESS" {
		delay = 60000
	}
	t.Add("notification_jobs", Row{"kind": kind, "resource_ref": resource, "event_id": repository.ID(), "deliver_after": time.Now().UTC().Add(time.Duration(delay) * time.Millisecond), "remaining_deliveries": count, "status": "READY"})
}

// Create returns the committed provider result and whether the HTTP response should be lost.
func (p *Provider) Create(ctx context.Context, refund bool, b Row) (any, bool, error) {
	now, e := p.clock(ctx)
	if e != nil {
		return nil, false, e
	}
	timeout := false
	v, e := p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		table, operation := "channel_payments", "PAYMENT"
		if refund {
			table = "channel_refunds"
			operation = "REFUND"
		}
		old := t.One(table, Row{"merchant_ref": b["merchant_ref"], "request_id": b["request_id"]})
		amount, e := d.Money(b.S("amount_cents"))
		if e != nil {
			return nil, e
		}
		if b.S("merchant_ref") != "scene1" || b.S("currency") != "CNY" {
			return nil, d.Invalid("商户或币种不符")
		}
		if old != nil {
			if old.N("amount_cents") != amount || (!refund && old.S("order_ref") != b.S("order_ref")) || (refund && old.S("txn_id") != b.S("txn_id")) {
				return nil, d.Fail("IDEMPOTENCY_CONFLICT", 409, "渠道请求键已用于不同参数")
			}
			return safe(old), nil
		}
		order := b.S("order_ref")
		attempt := int64(1)
		var payment Row
		if refund {
			payment = t.One("channel_payments", Row{"txn_id": b["txn_id"], "merchant_ref": b["merchant_ref"]})
			if payment == nil || payment.S("status") != "SUCCEEDED" || payment.N("amount_cents") != amount {
				return nil, d.Conflict("未找到等额本商户成功收款")
			}
			order = payment.S("order_ref")
			for _, r := range t.All("channel_refunds", Row{"txn_id": b["txn_id"]}) {
				if r.S("status") != "FAILED" {
					return nil, d.Conflict("该收款已退款或结果未确认")
				}
				attempt++
			}
		}
		rule := p.rule(t, operation, order, b.S("request_id"), attempt)
		status := "SUCCEEDED"
		if rule.S("mode") == "EXPLICIT_FAIL" {
			status = "FAILED"
		}
		if rule.S("mode") == "PENDING" {
			status = "PENDING"
		}
		timeout = rule.S("mode") == "TIMEOUT_AFTER_SUCCESS"
		values := Row{"merchant_ref": b["merchant_ref"], "request_id": b["request_id"], "amount_cents": amount, "status": status, "created_at": now, "updated_at": now}
		var resource string
		if refund {
			resource = repository.ID()
			values["txn_id"] = b["txn_id"]
			values["refund_id"] = resource
			if status == "SUCCEEDED" {
				values["refunded_at"] = now
			}
			if status == "FAILED" {
				values["failure_code"] = "SIMULATED_FAILURE"
			}
		} else {
			resource = repository.ID()
			values["order_ref"] = order
			values["txn_id"] = resource
			values["currency"] = "CNY"
			if status == "SUCCEEDED" {
				values["paid_at"] = now
			}
		}
		r := t.Add(table, values)
		if status != "PENDING" {
			notifyRule := p.rule(t, "NOTIFY", order, b.S("request_id"), attempt)
			if notifyRule.S("mode") == "DELAY_NOTIFY" || notifyRule.S("mode") == "DUPLICATE_NOTIFY" {
				rule = notifyRule
			}
			p.createJob(t, operation, resource, rule)
		}
		return safe(r), nil
	})
	return v, timeout, e
}
func (p *Provider) AddRule(ctx context.Context, b Row) (any, error) {
	return p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		values := Row{"delay_ms": int64(0), "repeat_count": int64(1), "remaining_uses": int64(1), "attempt_no": nil}
		for k, v := range b {
			values[k] = v
		}
		for _, k := range []string{"delay_ms", "repeat_count", "remaining_uses", "attempt_no"} {
			if values[k] != nil {
				values[k] = Row{"x": values[k]}.N("x")
			}
		}
		if values["delay_ms"].(int64) > 600000 || values["repeat_count"].(int64) < 1 || values["repeat_count"].(int64) > 20 || values["remaining_uses"].(int64) < 1 || values["remaining_uses"].(int64) > 20 {
			return nil, d.Invalid("教学规则范围错误")
		}
		if v, ok := values["attempt_no"]; ok && v != nil && v.(int64) < 1 {
			return nil, d.Invalid("attempt_no至少1")
		}
		r := t.Add("simulation_rules", values)
		return r, nil
	})
}
func (p *Provider) Replay(ctx context.Context, event string, count, delay int64) (any, error) {
	return p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		if count < 1 || count > 20 || delay < 0 || delay > 600000 {
			return nil, d.Invalid("重投参数范围错误")
		}
		j := t.One("notification_jobs", Row{"event_id": event})
		if e := d.Require(j); e != nil {
			return nil, e
		}
		t.Patch("notification_jobs", j, Row{"remaining_deliveries": count, "status": "READY", "lease_until": nil, "deliver_after": time.Now().UTC().Add(time.Duration(delay) * time.Millisecond)})
		return Row{"event_id": event, "queued": count}, nil
	})
}
func (p *Provider) DeliverOnce(ctx context.Context) error {
	v, e := p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		now := time.Now().UTC()
		for _, j := range t.All("notification_jobs", nil) {
			if j.N("remaining_deliveries") < 1 || j.T("deliver_after").After(now) || (j.S("status") == "RUNNING" && j.T("lease_until").After(now)) {
				continue
			}
			t.Patch("notification_jobs", j, Row{"status": "RUNNING", "lease_until": now.Add(15 * time.Second)})
			table, col := "channel_payments", "txn_id"
			if j.S("kind") == "REFUND" {
				table = "channel_refunds"
				col = "refund_id"
			}
			r := safe(t.One(table, Row{col: j["resource_ref"]}))
			r["event_id"] = j["event_id"]
			if j.S("kind") == "PAYMENT" {
				r["occurred_at"] = r["paid_at"]
			} else {
				r["occurred_at"] = r["refunded_at"]
			}
			if r["occurred_at"] == nil {
				r["occurred_at"] = now
			}
			return Row{"job": j, "body": r}, nil
		}
		return nil, nil
	})
	if e != nil || v == nil {
		return e
	}
	pack := v.(Row)
	j := pack["job"].(Row)
	body := pack["body"].(Row)
	if body["failure_code"] == nil {
		delete(body, "failure_code")
	}
	delete(body, "paid_at")
	delete(body, "refunded_at")
	if j.S("kind") == "REFUND" {
		delete(body, "order_ref")
	}
	path := "/api/v1/channel/payment-notifications"
	if j.S("kind") == "REFUND" {
		path = "/api/v1/channel/refund-notifications"
	}
	_, externalErr := p.Shop.Do(ctx, http.MethodPost, path, body)
	_, e = p.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		current := t.One("notification_jobs", Row{"id": j["id"]})
		count := current.N("remaining_deliveries")
		code := 200
		status := "READY"
		if externalErr == nil {
			count--
			if count == 0 {
				status = "DONE"
			}
		} else {
			status = "RETRY"
			code = 503
		}
		t.Patch("notification_jobs", current, Row{"remaining_deliveries": count, "status": status, "lease_until": nil, "last_http_status": code, "deliver_after": time.Now().UTC().Add(time.Second)})
		return nil, nil
	})
	return e
}
