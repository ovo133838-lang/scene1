package service

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
)

func (s *Service) VerifyAnomaly(ctx context.Context, c *channel.Client, actor Row, id, key, reason string) (Result, error) {
	var txn string
	_, e := s.Store.Run(ctx, false, func(t repository.Unit) (any, error) {
		a := t.One("payment_anomalies", Row{"id": id})
		if e := d.Require(a); e != nil {
			return nil, e
		}
		if a["receipt_id"] != nil {
			txn = t.One("receipts", Row{"id": a["receipt_id"]}).S("provider_txn_id")
		} else {
			txn = t.One("channel_notifications", Row{"id": a["first_notification_id"]}).S("provider_txn_id")
		}
		return nil, nil
	})
	if e != nil {
		return Result{}, e
	}
	var proof Row
	var queryErr error
	if txn != "" {
		proof, queryErr = c.Do(ctx, http.MethodGet, "/mock/v1/transactions/"+txn+"?merchant_ref=scene1", nil)
	}
	v, e := s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		a := t.One("payment_anomalies", Row{"id": id})
		raw := repository.Hash([]byte(reason))
		old := t.One("idempotency_records", Row{"actor_id": actor["id"], "operation": "verify:" + id, "request_key": key})
		if old != nil {
			if old.S("request_hash") != raw {
				return nil, d.Fail("IDEMPOTENCY_CONFLICT", 409, "幂等参数不同")
			}
			return Result{Data: s.anomalyDetail(t, a), Status: 200, Replayed: true}, nil
		}
		from := a.S("status")
		status := 202
		evidence := Row{"query": "UNCONFIRMED"}
		if queryErr == nil && proof != nil && proof.S("merchant_ref") == "scene1" && proof.S("txn_id") == txn && proof.S("status") == "SUCCEEDED" {
			s.applyPayment(t, proof, nil, true)
			r := t.One("receipts", Row{"provider": "MOCK", "provider_txn_id": txn})
			if r == nil {
				s.anomalyAction(t, a, actor, "CONFLICT", reason, from, Row{"query": "INVALID_CHANNEL_PROOF"})
				return Result{Data: s.anomalyDetail(t, a), Status: 202}, nil
			}
			verification := "CONFLICT"
			if r != nil && r.S("classification") != "NORMAL" {
				verification = "FUNDS_CONFIRMED"
			}
			if a.S("status") != "RESOLVED" {
				t.Patch("payment_anomalies", a, Row{"receipt_id": r["id"], "order_id": r["order_id"], "verification": verification, "status": "VERIFIED", "updated_at": s.Now(t)})
			}
			status = 200
			evidence = pick(proof, "txn_id status amount_cents")
		} else if he := new(channel.HTTPError); errors.As(queryErr, &he) && he.Status == 404 {
			verification := "NO_FUNDS"
			if a["receipt_id"] != nil {
				verification = "CONFLICT"
			}
			if a.S("status") != "RESOLVED" {
				t.Patch("payment_anomalies", a, Row{"verification": verification, "status": "VERIFIED", "updated_at": s.Now(t)})
			}
			status = 200
			evidence = Row{"query": "AUTHENTIC_NOT_FOUND", "known_receipt_preserved": a["receipt_id"] != nil}
		}
		s.anomalyAction(t, a, actor, "VERIFY", reason, from, evidence)
		t.Add("idempotency_records", Row{"actor_id": actor["id"], "operation": "verify:" + id, "request_key": key, "request_hash": raw, "resource_type": "payment_anomalies", "resource_id": id, "http_status": status})
		return Result{Data: s.anomalyDetail(t, a), Status: status}, nil
	})
	if e != nil {
		return Result{}, e
	}
	return v.(Result), nil
}
func (s *Service) WorkOnce(ctx context.Context, c *channel.Client) error {
	v, e := s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		now := time.Now().UTC()
		for _, j := range t.All("outbox_jobs", nil) {
			if j.S("status") == "DONE" || j.T("next_run_at").After(now) || (j.S("status") == "RUNNING" && j.T("lease_until").After(now)) {
				continue
			}
			t.Patch("outbox_jobs", j, Row{"status": "RUNNING", "lease_until": now.Add(15 * time.Second), "attempt_count": j.N("attempt_count") + 1, "updated_at": now})
			return j, nil
		}
		return nil, nil
	})
	if e != nil || v == nil {
		return e
	}
	job := v.(Row)
	kind := job.S("kind")
	var aggregate, receipt, order Row
	_, e = s.Store.Run(ctx, false, func(t repository.Unit) (any, error) {
		if kind == "PAYMENT_SEND" || kind == "PAYMENT_QUERY" {
			aggregate = t.One("payment_intents", Row{"id": job["aggregate_id"]})
			order = t.One("orders", Row{"id": aggregate["order_id"]})
		} else {
			aggregate = t.One("refund_attempts", Row{"id": job["aggregate_id"]})
			refund := t.One("refunds", Row{"id": aggregate["refund_id"]})
			receipt = t.One("receipts", Row{"id": refund["receipt_id"]})
		}
		return nil, d.Require(aggregate)
	})
	if e != nil {
		return e
	}
	method, path := http.MethodGet, ""
	var body any
	switch kind {
	case "PAYMENT_SEND":
		method = http.MethodPost
		path = "/mock/v1/payments"
		body = Row{"merchant_ref": "scene1", "request_id": aggregate["provider_request_id"], "order_ref": order["id"], "amount_cents": cents(aggregate.N("amount_cents")), "currency": "CNY"}
	case "PAYMENT_QUERY":
		path = "/mock/v1/payments/by-request/" + aggregate.S("provider_request_id") + "?merchant_ref=scene1"
	case "REFUND_SEND":
		method = http.MethodPost
		path = "/mock/v1/refunds"
		body = Row{"merchant_ref": "scene1", "request_id": aggregate["provider_request_id"], "txn_id": receipt["provider_txn_id"], "amount_cents": cents(receipt.N("amount_cents")), "currency": "CNY"}
	case "REFUND_QUERY":
		path = "/mock/v1/refunds/by-request/" + aggregate.S("provider_request_id") + "?merchant_ref=scene1"
	}
	proof, externalErr := c.Do(ctx, method, path, body)
	if externalErr == nil {
		amount, amountErr := d.Money(proof.S("amount_cents"))
		valid := proof.S("merchant_ref") == "scene1" && proof.S("request_id") == aggregate.S("provider_request_id") && proof.S("currency") == "CNY" && amountErr == nil
		if isPaymentKind := kind == "PAYMENT_SEND" || kind == "PAYMENT_QUERY"; isPaymentKind {
			valid = valid && proof.S("order_ref") == order.S("id") && amount == aggregate.N("amount_cents")
		} else {
			valid = valid && proof.S("txn_id") == receipt.S("provider_txn_id") && amount == receipt.N("amount_cents")
		}
		if !valid {
			externalErr = errors.New("INVALID_CHANNEL_PROOF")
		}
	}
	_, e = s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		j := t.One("outbox_jobs", Row{"id": job["id"]})
		now := s.Now(t)
		pending := externalErr != nil || proof.S("status") == "PENDING"
		isPayment := kind == "PAYMENT_SEND" || kind == "PAYMENT_QUERY"
		if pending {
			if isPayment {
				a := t.One("payment_intents", Row{"id": aggregate["id"]})
				if a.S("status") != "SUCCEEDED" && a.S("status") != "FAILED" {
					t.Patch("payment_intents", a, Row{"status": "UNKNOWN", "updated_at": now})
				}
			} else {
				a := t.One("refund_attempts", Row{"id": aggregate["id"]})
				r := t.One("refunds", Row{"id": a["refund_id"]})
				if r.S("status") != "SUCCEEDED" && a.S("status") != "FAILED" {
					t.Patch("refund_attempts", a, Row{"status": "UNKNOWN"})
					t.Patch("refunds", r, Row{"status": "UNKNOWN", "updated_at": now})
				}
			}
			// Retry the same provider key after lost responses; a query never creates a new financial request.
			t.Patch("outbox_jobs", j, Row{"status": "RETRY", "lease_until": nil, "last_error_code": "CHANNEL_UNCONFIRMED", "next_run_at": time.Now().UTC().Add(3 * time.Second), "updated_at": time.Now().UTC()})
			if kind == "PAYMENT_SEND" || kind == "REFUND_SEND" {
				t.Patch("outbox_jobs", j, Row{"kind": map[bool]string{true: "PAYMENT_QUERY", false: "REFUND_QUERY"}[isPayment]})
			}
			var he *channel.HTTPError
			if errors.As(externalErr, &he) && he.Status == 404 {
				if isPayment && order.S("status") != "PENDING_PAYMENT" {
					t.Patch("outbox_jobs", j, Row{"status": "DONE"})
					p := t.One("payment_intents", Row{"id": aggregate["id"]})
					if p.S("status") != "SUCCEEDED" {
						t.Patch("payment_intents", p, Row{"status": "FAILED", "failure_code": "CLOSED_WITH_NO_CHANNEL_RECORD"})
					}
				} else {
					t.Patch("outbox_jobs", j, Row{"kind": map[bool]string{true: "PAYMENT_SEND", false: "REFUND_SEND"}[isPayment]})
				}
			}
			return nil, nil
		}
		if isPayment {
			s.applyPayment(t, proof, nil, true)
			p := t.One("payment_intents", Row{"id": aggregate["id"]})
			t.Patch("payment_intents", p, Row{"last_queried_at": now})
		} else {
			proof["_channel_query"] = true
			s.applyRefund(t, proof, nil)
			a := t.One("refund_attempts", Row{"id": aggregate["id"]})
			t.Patch("refund_attempts", a, Row{"last_queried_at": now, "sent_at": now})
		}
		t.Patch("outbox_jobs", j, Row{"status": "DONE", "lease_until": nil, "updated_at": time.Now().UTC()})
		return nil, nil
	})
	return e
}
