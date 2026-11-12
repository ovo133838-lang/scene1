package service

import (
	"context"
	"time"

	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
)

func (s *Service) anomaly(t repository.Unit, typ, key string, o, receipt, n Row) Row {
	old := t.One("payment_anomalies", Row{"dedupe_key": typ + ":" + key})
	if old != nil {
		return old
	}
	var oid, rid, nid any
	if o != nil {
		oid = o["id"]
	}
	if receipt != nil {
		rid = receipt["id"]
	}
	if n != nil {
		nid = n["id"]
	}
	return t.Add("payment_anomalies", Row{"type": typ, "dedupe_key": typ + ":" + key, "order_id": oid, "receipt_id": rid, "first_notification_id": nid, "status": "OPEN", "verification": "UNVERIFIED", "summary": typ + "：请核实渠道收退款记录", "created_at": s.Now(t), "updated_at": s.Now(t)})
}
func (s *Service) anomalyAction(t repository.Unit, a, actor Row, action, reason, from string, evidence Row) {
	var aid any
	if actor != nil {
		aid = actor["id"]
	}
	t.Add("anomaly_actions", Row{"anomaly_id": a["id"], "actor_id": aid, "action": action, "reason": reason, "from_status": from, "to_status": a["status"], "evidence_redacted": evidence, "created_at": s.Now(t)})
}
func (s *Service) Ingest(ctx context.Context, kind string, b Row, hash, authError, nonce string) (any, error) {
	return s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		now := s.Now(t)
		amount, _ := d.Money(b.S("amount_cents"))
		var claimed any
		if amount > 0 {
			claimed = amount
		}
		n := t.Add("channel_notifications", Row{"kind": kind, "provider": "MOCK", "provider_event_id": nullable(b.S("event_id")), "external_order_ref": nullable(b.S("order_ref")), "provider_txn_id": nullable(b.S("txn_id")), "provider_refund_id": nullable(b.S("refund_id")), "claimed_amount_cents": claimed, "payload_hash": hash, "payload_redacted": pick(b, "event_id merchant_ref order_ref request_id txn_id refund_id status"), "auth_valid": authError == "", "process_result": "ACCEPTED", "reason_code": "OK", "received_at": now, "processed_at": now})
		if authError == "" {
			if t.One("auth_nonces", Row{"key_id": "mock-to-shop", "nonce": nonce}) != nil {
				authError = "REPLAYED_SIGNATURE"
			} else {
				t.Add("auth_nonces", Row{"key_id": "mock-to-shop", "nonce": nonce, "expires_at": time.Now().UTC().Add(10 * time.Minute)})
			}
		}
		result := "ACCEPTED"
		if authError != "" {
			result = authError
			typ := "INVALID_SIGNATURE"
			if authError == "INVALID_BODY" {
				typ = "INVALID_BODY"
			}
			s.anomaly(t, typ, hash, nil, nil, n)
			t.Patch("channel_notifications", n, Row{"auth_valid": false})
		} else if kind == "PAYMENT" {
			result = s.applyPayment(t, b, n, false)
		} else {
			result = s.applyRefund(t, b, n)
		}
		t.Patch("channel_notifications", n, Row{"process_result": result, "reason_code": result})
		return Row{"notification_id": n["id"], "result": result}, nil
	})
}
func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}
func (s *Service) applyPayment(t repository.Unit, b, n Row, query bool) string {
	o := t.One("orders", Row{"id": b["order_ref"]})
	p := t.One("payment_intents", Row{"provider_request_id": b["request_id"]})
	amount, e := d.Money(b.S("amount_cents"))
	key := b.S("txn_id")
	now := s.Now(t)
	if e != nil || b.S("merchant_ref") != "scene1" || b.S("currency") != "CNY" {
		s.anomaly(t, "AMOUNT_MISMATCH", key, o, nil, n)
		return "AMOUNT_MISMATCH"
	}
	if b.S("status") == "PENDING" {
		return "ACCEPTED"
	}
	if b.S("status") == "FAILED" {
		if p != nil && o != nil && p.S("order_id") == o.S("id") && p.N("amount_cents") == amount && p.S("status") != "SUCCEEDED" {
			t.Patch("payment_intents", p, Row{"status": "FAILED", "failure_code": "CHANNEL_FAILED", "updated_at": now})
		}
		return "ACCEPTED"
	}
	if b.S("status") != "SUCCEEDED" {
		return "INVALID_BODY"
	}
	receipt := t.One("receipts", Row{"provider": "MOCK", "provider_txn_id": key})
	if receipt != nil {
		if receipt.S("external_order_ref") != b.S("order_ref") || receipt.N("amount_cents") != amount {
			s.anomaly(t, "TXN_CONFLICT", key+":"+b.S("order_ref"), o, nil, n)
			return "TXN_CONFLICT"
		}
		if n != nil {
			t.Patch("channel_notifications", n, Row{"receipt_id": receipt["id"]})
		}
		return "DUPLICATE"
	}
	classification := "NORMAL"
	typ := ""
	result := "ACCEPTED"
	if o == nil {
		classification = "UNKNOWN_ORDER"
		typ = "UNKNOWN_ORDER"
		result = typ
	} else if p == nil || p.S("order_id") != o.S("id") || amount != o.N("amount_cents") {
		classification = "AMOUNT_MISMATCH"
		typ = "AMOUNT_MISMATCH"
		result = typ
	} else {
		if o.S("status") == "PENDING_PAYMENT" && d.Expired(o, now) {
			s.close(t, o, nil, "TIMEOUT")
		}
		if o.S("status") == "CLOSED" {
			classification = "LATE"
			typ = "LATE_PAYMENT"
		} else if o.S("status") != "PENDING_PAYMENT" {
			classification = "EXTRA"
			typ = "EXTRA_PAYMENT"
		}
	}
	// Non-normal extra/mismatched/unknown funds require an independent channel query.
	if typ != "" && classification != "LATE" && !query {
		s.anomaly(t, typ, key, o, nil, n)
		return result
	}
	paidAt, e := time.Parse(time.RFC3339Nano, b.S("paid_at"))
	if e != nil {
		paidAt, e = time.Parse(time.RFC3339Nano, b.S("occurred_at"))
	}
	if e != nil {
		return "INVALID_BODY"
	}
	proof := "SIGNED_NOTIFY"
	if query {
		proof = "CHANNEL_QUERY"
	}
	var oid, pid any
	if o != nil {
		oid = o["id"]
	}
	if p != nil && p.S("order_id") == b.S("order_ref") {
		pid = p["id"]
	}
	receipt = t.Add("receipts", Row{"provider": "MOCK", "provider_txn_id": key, "external_order_ref": b["order_ref"], "order_id": oid, "payment_intent_id": pid, "amount_cents": amount, "currency": "CNY", "classification": classification, "proof_type": proof, "verified_at": now, "provider_paid_at": paidAt.UTC(), "created_at": now})
	if n != nil {
		t.Patch("channel_notifications", n, Row{"receipt_id": receipt["id"]})
	}
	if classification == "NORMAL" {
		t.Patch("orders", o, Row{"status": "PENDING_SHIPMENT", "normal_receipt_id": receipt["id"], "paid_at": now, "version": o.N("version") + 1, "updated_at": now})
		s.audit(t, nil, "ORDER", o.S("id"), "PAYMENT_CONFIRMED", "可信支付", Row{}, Row{"receipt_id": receipt["id"]})
	} else {
		s.anomaly(t, typ, key, o, receipt, n)
	}
	if p != nil && p.S("order_id") == b.S("order_ref") && p.N("amount_cents") == amount {
		t.Patch("payment_intents", p, Row{"status": "SUCCEEDED", "provider_txn_id": key, "updated_at": now})
	}
	return result
}
func (s *Service) applyRefund(t repository.Unit, b, n Row) string {
	a := t.One("refund_attempts", Row{"provider_request_id": b["request_id"]})
	if a == nil {
		s.anomaly(t, "REFUND_RESULT_CONFLICT", b.S("request_id"), nil, nil, n)
		return "RESULT_CONFLICT"
	}
	r := t.One("refunds", Row{"id": a["refund_id"]})
	receipt := t.One("receipts", Row{"id": r["receipt_id"]})
	o := t.One("orders", Row{"id": r["order_id"]})
	amount, e := d.Money(b.S("amount_cents"))
	now := s.Now(t)
	conflict := func() string {
		an := s.anomaly(t, "REFUND_RESULT_CONFLICT", a.S("id"), o, receipt, n)
		t.Patch("payment_anomalies", an, Row{"refund_id": r["id"], "verification": "CONFLICT", "updated_at": now})
		return "RESULT_CONFLICT"
	}
	if e != nil || b.S("merchant_ref") != "scene1" || b.S("currency") != "CNY" || amount != r.N("amount_cents") || b.S("txn_id") != receipt.S("provider_txn_id") || b.S("refund_id") == "" {
		return conflict()
	}
	if n != nil {
		t.Patch("channel_notifications", n, Row{"refund_attempt_id": a["id"]})
	}
	status := b.S("status")
	if status == "PENDING" {
		return "ACCEPTED"
	}
	if status != "SUCCEEDED" && status != "FAILED" {
		return "INVALID_BODY"
	}
	activeConflict := t.One("payment_anomalies", Row{"dedupe_key": "REFUND_RESULT_CONFLICT:" + a.S("id")})
	if activeConflict != nil && activeConflict.S("status") != "RESOLVED" {
		if !b.B("_channel_query") {
			return conflict()
		}
		// Only a signed query for this original attempt can restore confidence.
		if status == "FAILED" && a.S("status") == "FAILED" {
			from := activeConflict.S("status")
			t.Patch("payment_anomalies", activeConflict, Row{"status": "RESOLVED", "verification": "NO_FUNDS", "resolved_reason": "可信查询确认此尝试明确失败，未发生退款", "resolved_at": now, "updated_at": now})
			s.anomalyAction(t, activeConflict, nil, "RESOLVE", "可信渠道查询确认失败", from, Row{"attempt_id": a["id"]})
			return "DUPLICATE"
		}
		if status == "SUCCEEDED" && a.S("status") == "FAILED" && r.S("current_attempt_id") == a.S("id") {
			t.Patch("refund_attempts", a, Row{"status": "UNKNOWN"})
		}
	}
	if a.S("status") == "SUCCEEDED" || a.S("status") == "FAILED" {
		if a.S("provider_refund_id") != "" && a.S("provider_refund_id") != b.S("refund_id") {
			return conflict()
		}
		if a.S("status") != status {
			return conflict()
		}
		return "DUPLICATE"
	}
	if r.S("current_attempt_id") != a.S("id") {
		return conflict()
	}
	if r.S("status") == "SUCCEEDED" {
		return "DUPLICATE"
	}
	t.Patch("refund_attempts", a, Row{"status": status, "provider_refund_id": b["refund_id"], "failure_code": nullable(b.S("failure_code")), "proof_redacted": pick(b, "status request_id refund_id amount_cents"), "resolved_at": now})
	if status == "FAILED" {
		t.Patch("refunds", r, Row{"status": "FAILED", "updated_at": now})
		return "ACCEPTED"
	}
	if r.S("kind") == "NORMAL" {
		if o == nil || o.S("status") != "REFUND_PROCESSING" {
			return conflict()
		}
		p := t.One("products", Row{"id": o["product_id"]})
		s.inventory(t, p, o, nil, "REFUND_RELEASE", o.N("quantity"), r["id"], "渠道确认售前退款成功")
		t.Patch("orders", o, Row{"status": "REFUNDED", "active_application_id": nil, "refunded_at": now, "version": o.N("version") + 1, "updated_at": now})
	}
	t.Patch("refunds", r, Row{"status": "SUCCEEDED", "success_at": now, "settled_at": now, "updated_at": now})
	if activeConflict != nil && b.B("_channel_query") {
		from := activeConflict.S("status")
		t.Patch("payment_anomalies", activeConflict, Row{"status": "RESOLVED", "verification": "FUNDS_CONFIRMED", "resolved_reason": "可信查询确认原尝试成功并结算", "resolved_at": now, "updated_at": now})
		s.anomalyAction(t, activeConflict, nil, "RESOLVE", "原尝试可信成功", from, Row{"attempt_id": a["id"]})
	}
	if r["anomaly_id"] != nil {
		an := t.One("payment_anomalies", Row{"id": r["anomaly_id"]})
		from := an.S("status")
		t.Patch("payment_anomalies", an, Row{"status": "RESOLVED", "resolved_reason": "渠道确认异常款已整笔退回", "resolved_at": now, "updated_at": now})
		s.anomalyAction(t, an, nil, "RESOLVE", "渠道确认成功", from, Row{"refund_id": r["id"]})
	}
	s.audit(t, nil, "REFUND", r.S("id"), "SETTLED", "渠道确认成功", Row{}, Row{"status": "SUCCEEDED"})
	return "ACCEPTED"
}
