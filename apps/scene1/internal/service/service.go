// Package service contains transactional use cases. No external HTTP runs while a write transaction is held.
package service

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

type Row = repository.Row
type Service struct {
	Store  repository.Database
	Secret string
	Demo   bool
}
type Result struct {
	Data     any
	Status   int
	Replayed bool
	Err      error
}
type Ref struct {
	Table, ID string
	Status    int
}

func (s *Service) Now(t repository.Unit) time.Time {
	clock := t.One("demo_clock", Row{"id": 1})
	return time.Now().UTC().Add(time.Duration(clock.N("offset_seconds")) * time.Second)
}
func (s *Service) Seed(ctx context.Context, password string) error {
	if len(password) < 12 {
		return fmt.Errorf("SCENE1_PASSWORD must contain at least 12 characters")
	}
	err := s.Store.InitClock(ctx)
	if err != nil {
		return err
	}
	_, err = s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		if len(t.All("accounts", nil)) == 0 {
			hash := security.Password(password)
			for _, a := range []struct{ name, role string }{{"buyer1", "BUYER"}, {"buyer2", "BUYER"}, {"buyer3", "BUYER"}, {"operator", "OPERATOR"}, {"warehouse", "WAREHOUSE"}, {"support", "SUPPORT"}} {
				t.Add("accounts", Row{"login_name": a.name, "display_name": a.name, "password_hash": hash, "role": a.role, "enabled": true})
			}
		}
		if len(t.All("products", nil)) == 0 {
			for i, q := range []int64{5, 8} {
				t.Add("products", Row{"sku": fmt.Sprintf("SHOP-%d", i+1), "name": []string{"活动标准商品", "日常标准商品"}[i], "unit_price_cents": int64((i + 1) * 10000), "sale_status": "OFF_SHELF", "initial_quantity": q, "available_quantity": q})
			}
		}
		return nil, nil
	})
	return err
}
func (s *Service) Login(ctx context.Context, name, password string) (any, error) {
	return s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		a := t.One("accounts", Row{"login_name": name})
		if a == nil || !a.B("enabled") || !security.VerifyPassword(password, a.S("password_hash")) {
			return nil, d.Fail("INVALID_CREDENTIALS", 401, "账号或密码错误")
		}
		token := security.Token()
		expires := time.Now().UTC().Add(8 * time.Hour)
		t.Add("sessions", Row{"account_id": a["id"], "token_hash": security.Digest([]byte(token)), "expires_at": expires})
		return Row{"token": token, "expires_at": expires, "account": pick(a, "id login_name display_name role")}, nil
	})
}
func (s *Service) Auth(ctx context.Context, token string) (Row, error) {
	v, e := s.Store.Run(ctx, false, func(t repository.Unit) (any, error) {
		session := t.One("sessions", Row{"token_hash": security.Digest([]byte(token))})
		if session == nil || session["revoked_at"] != nil || !time.Now().UTC().Before(session.T("expires_at")) {
			return nil, d.Fail("UNAUTHENTICATED", 401, "请重新登录")
		}
		a := t.One("accounts", Row{"id": session["account_id"]})
		if a == nil || !a.B("enabled") {
			return nil, d.Fail("UNAUTHENTICATED", 401, "账号不可用")
		}
		return pick(a, "id login_name display_name role"), nil
	})
	if e != nil {
		return nil, e
	}
	return v.(Row), nil
}
func (s *Service) Logout(ctx context.Context, token string) error {
	_, e := s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		r := t.One("sessions", Row{"token_hash": security.Digest([]byte(token))})
		if r != nil {
			t.Patch("sessions", r, Row{"revoked_at": time.Now().UTC()})
		}
		return nil, nil
	})
	return e
}
func (s *Service) Exec(ctx context.Context, actor Row, op, id, key string, b Row) (Result, error) {
	v, e := s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		raw, _ := json.Marshal(b)
		hash := repository.Hash(append([]byte(id+":"), raw...))
		scope := op + ":" + id
		old := t.One("idempotency_records", Row{"actor_id": actor["id"], "operation": scope, "request_key": key})
		if old != nil {
			if old.S("request_hash") != hash {
				return nil, d.Fail("IDEMPOTENCY_CONFLICT", 409, "同一幂等键的参数不同")
			}
			return Result{Data: s.response(t, op, Ref{old.S("resource_type"), old.S("resource_id"), int(old.N("http_status"))}), Status: int(old.N("http_status")), Replayed: true}, nil
		}
		ref, err := s.command(t, actor, op, id, b)
		if err != nil {
			if f, ok := err.(*d.Fault); ok && f.Code == "EXPIRED" {
				return Result{Err: err}, nil
			}
			return nil, err
		}
		t.Add("idempotency_records", Row{"actor_id": actor["id"], "operation": scope, "request_key": key, "request_hash": hash, "resource_type": ref.Table, "resource_id": ref.ID, "http_status": ref.Status})
		return Result{Data: s.response(t, op, ref), Status: ref.Status}, nil
	})
	if e != nil {
		return Result{}, e
	}
	r := v.(Result)
	return r, r.Err
}
func (s *Service) owned(t repository.Unit, id string, actor Row) (Row, error) {
	o := t.One("orders", Row{"id": id})
	if o == nil || (actor.S("role") == "BUYER" && o.S("buyer_id") != actor.S("id")) {
		return nil, d.Require(nil)
	}
	return o, nil
}
func (s *Service) audit(t repository.Unit, actor Row, kind, id, action, reason string, before, after Row) {
	var aid any
	ak := "SYSTEM"
	if actor != nil {
		aid = actor["id"]
		ak = "USER"
	}
	t.Add("audit_events", Row{"actor_id": aid, "actor_kind": ak, "entity_type": kind, "entity_id": id, "action": action, "request_id": repository.AuditRequestID(t), "before_redacted": before, "after_redacted": after, "reason": reason, "created_at": s.Now(t)})
}
func (s *Service) inventory(t repository.Unit, p, o, actor Row, kind string, q int64, refundID any, reason string) Row {
	da, dr, ds, adj, _ := d.StockVector(kind, q)
	entry := Row{"product_id": p["id"], "order_id": nil, "refund_id": refundID, "actor_id": nil, "event_type": kind, "event_key": kind + ":" + repository.ID(), "delta_available": da, "delta_reserved": dr, "delta_shipped": ds, "delta_adjustment": adj, "available_before": p.N("available_quantity"), "available_after": p.N("available_quantity") + da, "reserved_before": p.N("reserved_quantity"), "reserved_after": p.N("reserved_quantity") + dr, "shipped_before": p.N("shipped_quantity"), "shipped_after": p.N("shipped_quantity") + ds, "reason": reason, "created_at": s.Now(t)}
	if o != nil {
		entry["order_id"] = o["id"]
		entry["event_key"] = kind + ":" + o.S("id")
	}
	if actor != nil {
		entry["actor_id"] = actor["id"]
	}
	t.Patch("products", p, Row{"available_quantity": entry["available_after"], "reserved_quantity": entry["reserved_after"], "shipped_quantity": entry["shipped_after"], "adjustment_net": p.N("adjustment_net") + adj, "version": p.N("version") + 1, "updated_at": s.Now(t)})
	return t.Add("inventory_ledger", entry)
}
func (s *Service) close(t repository.Unit, o, actor Row, reason string) {
	if o.S("status") != "PENDING_PAYMENT" {
		return
	}
	p := t.One("products", Row{"id": o["product_id"]})
	s.inventory(t, p, o, actor, "CLOSE_RELEASE", o.N("quantity"), nil, reason)
	t.Patch("orders", o, Row{"status": "CLOSED", "close_reason": reason, "closed_at": s.Now(t), "version": o.N("version") + 1, "updated_at": s.Now(t)})
	s.audit(t, actor, "ORDER", o.S("id"), "CLOSE", reason, Row{}, Row{"status": "CLOSED"})
}
func (s *Service) newJob(t repository.Unit, kind, id string) {
	now := time.Now().UTC()
	t.Add("outbox_jobs", Row{"job_key": kind + ":" + id + ":" + repository.ID(), "kind": kind, "aggregate_id": id, "status": "READY", "attempt_count": 0, "next_run_at": now})
}
func (s *Service) newAttempt(t repository.Unit, r Row) Row {
	n := int64(len(t.All("refund_attempts", Row{"refund_id": r["id"]})) + 1)
	a := t.Add("refund_attempts", Row{"refund_id": r["id"], "attempt_no": n, "provider_request_id": repository.ID(), "status": "READY", "created_at": s.Now(t)})
	t.Patch("refunds", r, Row{"status": "READY", "current_attempt_id": a["id"], "updated_at": s.Now(t)})
	s.newJob(t, "REFUND_SEND", a.S("id"))
	return a
}
func (s *Service) newRefund(t repository.Unit, receipt, application, anomaly, actor Row) Row {
	old := t.One("refunds", Row{"receipt_id": receipt["id"]})
	if old != nil {
		return old
	}
	kind := "NORMAL"
	var app, anom any
	if application != nil {
		app = application["id"]
	}
	if anomaly != nil {
		kind = "EXCEPTION"
		anom = anomaly["id"]
	}
	r := t.Add("refunds", Row{"receipt_id": receipt["id"], "order_id": receipt["order_id"], "application_id": app, "anomaly_id": anom, "kind": kind, "amount_cents": receipt["amount_cents"], "status": "READY", "created_by": actor["id"], "created_at": s.Now(t), "updated_at": s.Now(t)})
	s.newAttempt(t, r)
	return r
}
func (s *Service) command(t repository.Unit, actor Row, op, id string, b Row) (Ref, error) {
	now := s.Now(t)
	ref := func(table string, r Row, status int) (Ref, error) { return Ref{table, r.S("id"), status}, nil }
	bad := func(e error) (Ref, error) { return Ref{}, e }
	switch op {
	case "create_order":
		p := t.One("products", Row{"id": b["product_id"]})
		if e := d.Require(p); e != nil {
			return bad(e)
		}
		q := b.N("quantity")
		if q != 1 && q != 2 {
			return bad(d.Invalid("数量只能是1或2"))
		}
		if p.S("sale_status") != "ON_SHELF" {
			return bad(d.Fail("NOT_ON_SALE", 409, "商品未上架"))
		}
		if p.N("available_quantity") < q {
			return bad(d.Fail("OUT_OF_STOCK", 409, "可售数量不足"))
		}
		o := t.Add("orders", Row{"order_no": "SO" + security.Token()[:24], "buyer_id": actor["id"], "product_id": p["id"], "sku_snapshot": p["sku"], "name_snapshot": p["name"], "unit_price_cents": p["unit_price_cents"], "quantity": q, "amount_cents": p.N("unit_price_cents") * q, "status": "PENDING_PAYMENT", "expires_at": now.Add(10 * time.Minute), "created_at": now, "updated_at": now})
		s.inventory(t, p, o, actor, "RESERVE", q, nil, "创建订单占用")
		s.audit(t, actor, "ORDER", o.S("id"), "CREATE", "下单", Row{}, Row{"status": "PENDING_PAYMENT"})
		return ref("orders", o, 201)
	case "cancel", "pay", "apply", "ship":
		o, e := s.owned(t, id, actor)
		if e != nil {
			return bad(e)
		}
		if o.S("status") == "PENDING_PAYMENT" && d.Expired(o, now) {
			s.close(t, o, nil, "TIMEOUT")
			if op != "cancel" {
				return bad(d.Fail("EXPIRED", 409, "订单已满10分钟并关闭，库存已释放"))
			}
		}
		switch op {
		case "cancel":
			if o.S("status") == "CLOSED" {
				return ref("orders", o, 200)
			}
			if o.S("status") != "PENDING_PAYMENT" {
				return bad(d.Conflict("已付款或已结束的订单不能取消"))
			}
			s.close(t, o, actor, "BUYER_CANCELLED")
			return ref("orders", o, 200)
		case "pay":
			if o.S("status") != "PENDING_PAYMENT" {
				return bad(d.Conflict("当前订单不能付款"))
			}
			for _, p := range t.All("payment_intents", Row{"order_id": id}) {
				if p.S("status") != "FAILED" {
					return ref("payment_intents", p, 202)
				}
			}
			p := t.Add("payment_intents", Row{"order_id": id, "provider_request_id": repository.ID(), "amount_cents": o["amount_cents"], "currency": "CNY", "status": "READY", "created_at": now, "updated_at": now})
			s.newJob(t, "PAYMENT_SEND", p.S("id"))
			return ref("payment_intents", p, 202)
		case "apply":
			if !d.CanApply(o) {
				return bad(d.Fail("ACTIVE_REFUND", 409, "只有已付款待发货且无活动退款的订单可以申请"))
			}
			a := t.Add("refund_applications", Row{"order_id": id, "buyer_id": actor["id"], "reason": b["reason"], "status": "PENDING", "created_at": now})
			t.Patch("orders", o, Row{"status": "REFUND_REVIEW", "active_application_id": a["id"], "version": o.N("version") + 1, "updated_at": now})
			s.audit(t, actor, "ORDER", id, "APPLY_REFUND", b.S("reason"), Row{}, Row{"status": "REFUND_REVIEW"})
			return ref("refund_applications", a, 201)
		case "ship":
			if t.One("shipments", Row{"order_id": id}) != nil {
				return bad(d.Fail("SHIPMENT_EXISTS", 409, "此单已经登记发货"))
			}
			if !d.CanShip(o) {
				return bad(d.Conflict("非待发货状态或退款处理中，禁止发货"))
			}
			p := t.One("products", Row{"id": o["product_id"]})
			sh := t.Add("shipments", Row{"order_id": id, "carrier": b["carrier"], "tracking_no": b["tracking_no"], "operator_id": actor["id"], "shipped_at": now})
			s.inventory(t, p, o, actor, "SHIP", o.N("quantity"), nil, "人工发货登记")
			t.Patch("orders", o, Row{"status": "SHIPPED", "shipped_at": now, "version": o.N("version") + 1, "updated_at": now})
			s.audit(t, actor, "ORDER", id, "SHIP", "登记运单", Row{}, Row{"shipment_id": sh["id"]})
			return ref("shipments", sh, 201)
		}
	case "query_payment":
		p := t.One("payment_intents", Row{"id": id})
		if e := d.Require(p); e != nil {
			return bad(e)
		}
		if _, e := s.owned(t, p.S("order_id"), actor); e != nil {
			return bad(e)
		}
		s.newJob(t, "PAYMENT_QUERY", id)
		return ref("payment_intents", p, 202)
	case "review":
		a := t.One("refund_applications", Row{"id": id})
		if e := d.Require(a); e != nil {
			return bad(e)
		}
		decision := map[string]string{"APPROVE": "APPROVED", "REJECT": "REJECTED"}[b.S("decision")]
		if decision == "" {
			return bad(d.Invalid("审核决定错误"))
		}
		if a.S("status") != "PENDING" {
			if a.S("status") == decision {
				return ref("refund_applications", a, 200)
			}
			return bad(d.Fail("ALREADY_REVIEWED", 409, "审核结论不能反转"))
		}
		o := t.One("orders", Row{"id": a["order_id"]})
		if o.S("status") != "REFUND_REVIEW" || o.S("active_application_id") != id {
			return bad(d.Conflict("当前活动申请不匹配"))
		}
		t.Patch("refund_applications", a, Row{"status": decision, "review_reason": b["reason"], "reviewer_id": actor["id"], "reviewed_at": now})
		if decision == "REJECTED" {
			t.Patch("orders", o, Row{"status": "PENDING_SHIPMENT", "active_application_id": nil, "version": o.N("version") + 1, "updated_at": now})
		} else {
			receipt := t.One("receipts", Row{"id": o["normal_receipt_id"]})
			s.newRefund(t, receipt, a, nil, actor)
			t.Patch("orders", o, Row{"status": "REFUND_PROCESSING", "version": o.N("version") + 1, "updated_at": now})
		}
		s.audit(t, actor, "ORDER", o.S("id"), "REVIEW", b.S("reason"), Row{}, Row{"decision": decision})
		return ref("refund_applications", a, 200)
	case "retry_refund", "query_refund":
		r := t.One("refunds", Row{"id": id})
		if e := d.Require(r); e != nil {
			return bad(e)
		}
		if op == "retry_refund" {
			for _, an := range t.All("payment_anomalies", Row{"refund_id": r["id"]}) {
				if an.S("type") == "REFUND_RESULT_CONFLICT" && an.S("status") != "RESOLVED" {
					return bad(d.Fail("RESULT_UNKNOWN", 409, "退款存在未核实的冲突回报，请先查询原尝试"))
				}
			}
			if r.S("status") != "FAILED" {
				return bad(d.Fail("RESULT_UNKNOWN", 409, "只有渠道明确失败才可新建尝试，未知请查询原尝试"))
			}
			s.newAttempt(t, r)
		} else {
			for _, attempt := range t.All("refund_attempts", Row{"refund_id": r["id"]}) {
				s.newJob(t, "REFUND_QUERY", attempt.S("id"))
			}
		}
		s.audit(t, actor, "REFUND", id, op, b.S("reason"), Row{}, Row{})
		return ref("refunds", r, 202)
	case "update_product", "adjust":
		p := t.One("products", Row{"id": id})
		if e := d.Require(p); e != nil {
			return bad(e)
		}
		if p.N("version") != b.N("version") {
			return bad(d.Conflict("商品版本已变化，请刷新后操作"))
		}
		before := pick(p, "name unit_price_cents sale_status available_quantity reserved_quantity version")
		if op == "update_product" {
			changes := Row{"version": p.N("version") + 1, "updated_at": now}
			for _, k := range []string{"name", "sale_status"} {
				if v, ok := b[k]; ok {
					changes[k] = v
				}
			}
			if v, ok := b["unit_price_cents"]; ok {
				n, e := d.Money(v.(string))
				if e != nil || n > 1000000000 {
					return bad(d.Invalid("商品价格超出范围"))
				}
				changes["unit_price_cents"] = n
			}
			t.Patch("products", p, changes)
			s.audit(t, actor, "PRODUCT", id, "UPDATE", b.S("reason"), before, pick(p, "name unit_price_cents sale_status version"))
			return ref("products", p, 200)
		}
		delta := b.N("delta")
		if delta == 0 || delta < -1000000 || delta > 1000000 || p.N("available_quantity")+delta < 0 || p.N("available_quantity")+delta > 1000000 {
			return bad(d.Invalid("调整后可售数量须在0到1000000内"))
		}
		entry := s.inventory(t, p, nil, actor, "ADJUST", delta, nil, b.S("reason"))
		s.audit(t, actor, "PRODUCT", id, "ADJUST", b.S("reason"), before, pick(p, "available_quantity reserved_quantity version"))
		return ref("inventory_ledger", entry, 201)
	case "refund_anomaly", "resolve_anomaly":
		a := t.One("payment_anomalies", Row{"id": id})
		if e := d.Require(a); e != nil {
			return bad(e)
		}
		if op == "refund_anomaly" {
			if a.S("verification") != "FUNDS_CONFIRMED" || a["receipt_id"] == nil {
				return bad(d.Conflict("请先从渠道核实真实收款"))
			}
			receipt := t.One("receipts", Row{"id": a["receipt_id"]})
			if receipt.S("classification") == "NORMAL" {
				return bad(d.Conflict("正常订单收款必须走售前申请审核"))
			}
			r := s.newRefund(t, receipt, nil, a, actor)
			if r.S("status") != "SUCCEEDED" {
				from := a.S("status")
				t.Patch("payment_anomalies", a, Row{"refund_id": r["id"], "status": "REFUNDING", "updated_at": now})
				s.anomalyAction(t, a, actor, "REQUEST_REFUND", b.S("reason"), from, Row{})
			}
			return ref("refunds", r, 202)
		}
		if a.S("verification") != "NO_FUNDS" || a["receipt_id"] != nil {
			return bad(d.Conflict("存在资金或未核实的异常不能手工结案"))
		}
		from := a.S("status")
		t.Patch("payment_anomalies", a, Row{"status": "RESOLVED", "resolved_reason": b["reason"], "resolved_by": actor["id"], "resolved_at": now, "updated_at": now})
		s.anomalyAction(t, a, actor, "RESOLVE", b.S("reason"), from, Row{})
		return ref("payment_anomalies", a, 200)
	}
	return bad(d.Invalid("未知业务操作"))
}
func (s *Service) Expire(ctx context.Context) error {
	_, e := s.Store.Run(ctx, true, func(t repository.Unit) (any, error) {
		now := s.Now(t)
		for _, o := range t.All("orders", Row{"status": "PENDING_PAYMENT"}) {
			if d.Expired(o, now) {
				s.close(t, o, nil, "TIMEOUT")
			}
		}
		return nil, nil
	})
	return e
}
func (s *Service) Clock(ctx context.Context, seconds int64) (any, error) {
	return s.Store.Run(ctx, seconds > 0, func(t repository.Unit) (any, error) {
		c := t.One("demo_clock", Row{"id": 1})
		if seconds > 0 {
			t.Patch("demo_clock", c, Row{"offset_seconds": c.N("offset_seconds") + seconds, "version": c.N("version") + 1, "updated_by": "demo-admin", "updated_at": time.Now().UTC()})
		}
		return Row{"business_now": s.Now(t), "advanced_seconds": seconds, "offset_seconds": c.N("offset_seconds"), "version": c.N("version")}, nil
	})
}
func cents(n int64) string { return strconv.FormatInt(n, 10) }
