package service

import (
	"context"
	"fmt"
	"math/big"
	"sort"
	"strings"
	"time"

	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

func pick(r Row, fields string) Row {
	if r == nil {
		return nil
	}
	out := Row{}
	for _, k := range strings.Fields(fields) {
		v := r[k]
		if strings.HasSuffix(k, "_cents") && v != nil {
			if _, ok := v.(string); ok {
				out[k] = v
				continue
			}
			v = cents(r.N(k))
		}
		out[k] = v
	}
	return out
}

var dtoFields = map[string]string{
	"products":              "id sku name unit_price_cents sale_status available_quantity reserved_quantity shipped_quantity initial_quantity adjustment_net version",
	"orders":                "id order_no product_id sku_snapshot name_snapshot unit_price_cents quantity amount_cents status created_at expires_at close_reason",
	"payment_intents":       "id order_id status amount_cents currency failure_code provider_txn_id created_at updated_at",
	"receipts":              "id order_id provider provider_txn_id amount_cents currency classification verified_at provider_paid_at",
	"refund_applications":   "id order_id reason status review_reason reviewer_id reviewed_at created_at",
	"refunds":               "id receipt_id order_id application_id anomaly_id kind amount_cents status success_at created_at updated_at",
	"refund_attempts":       "id attempt_no status provider_refund_id failure_code sent_at resolved_at last_queried_at",
	"shipments":             "id order_id carrier tracking_no operator_id shipped_at",
	"payment_anomalies":     "id type order_id receipt_id refund_id status verification summary resolved_reason created_at updated_at",
	"channel_notifications": "id kind provider_event_id external_order_ref provider_txn_id provider_refund_id claimed_amount_cents auth_valid process_result reason_code received_at processed_at",
	"anomaly_actions":       "id actor_id action reason from_status to_status evidence_redacted created_at",
	"inventory_ledger":      "id product_id order_id refund_id actor_id event_type delta_available delta_reserved delta_shipped delta_adjustment available_before available_after reserved_before reserved_after shipped_before shipped_after reason created_at",
	"audit_events":          "id actor_id actor_kind entity_type entity_id action request_id before_redacted after_redacted reason created_at",
}

func (s *Service) dto(t repository.Unit, table string, r Row) Row {
	v := pick(r, dtoFields[table])
	if r == nil {
		return nil
	}
	if table == "orders" {
		v["payment_deadline_passed"] = d.Expired(r, s.Now(t))
	}
	if table == "refunds" {
		a := []Row{}
		for _, r := range t.All("refund_attempts", Row{"refund_id": r["id"]}) {
			a = append(a, s.dto(t, "refund_attempts", r))
		}
		sort.Slice(a, func(i, j int) bool { return a[i].N("attempt_no") < a[j].N("attempt_no") })
		v["attempts"] = a
	}
	return v
}
func (s *Service) dtos(t repository.Unit, table string, where Row) []Row {
	out := []Row{}
	for _, r := range t.All(table, where) {
		out = append(out, s.dto(t, table, r))
	}
	return out
}
func (s *Service) orderDetail(t repository.Unit, o Row) Row {
	if o == nil {
		return nil
	}
	v := s.dto(t, "orders", o)
	for _, k := range []string{"paid_at", "closed_at", "refunded_at", "shipped_at"} {
		v[k] = o[k]
	}
	v["payment"] = nil
	intents := t.All("payment_intents", Row{"order_id": o["id"]})
	sort.Slice(intents, func(i, j int) bool { return intents[i].T("created_at").After(intents[j].T("created_at")) })
	if len(intents) > 0 {
		v["payment"] = s.dto(t, "payment_intents", intents[0])
	}
	v["applications"] = s.dtos(t, "refund_applications", Row{"order_id": o["id"]})
	v["receipts"] = s.dtos(t, "receipts", Row{"order_id": o["id"]})
	v["refunds"] = s.dtos(t, "refunds", Row{"order_id": o["id"]})
	v["shipment"] = s.dto(t, "shipments", t.One("shipments", Row{"order_id": o["id"]}))
	anomalies := []Row{}
	for _, a := range t.All("payment_anomalies", Row{"order_id": o["id"]}) {
		anomalies = append(anomalies, pick(a, "id type status summary refund_id"))
	}
	v["anomalies"] = anomalies
	active := o.S("status") == "PENDING_PAYMENT" && !d.Expired(o, s.Now(t))
	actions := []Row{}
	for _, a := range []struct {
		code    string
		enabled bool
	}{{"CANCEL", active}, {"PAY", active}, {"QUERY_PAYMENT", len(intents) > 0}, {"APPLY_REFUND", d.CanApply(o)}, {"VIEW_SHIPMENT", o.S("status") == "SHIPPED"}} {
		var reason any
		if !a.enabled {
			reason = "当前状态或有效期不允许此操作"
		}
		actions = append(actions, Row{"code": a.code, "enabled": a.enabled, "disabled_reason": reason})
	}
	v["executable_actions"] = actions
	return v
}
func (s *Service) anomalyDetail(t repository.Unit, a Row) Row {
	v := s.dto(t, "payment_anomalies", a)
	if a == nil {
		return nil
	}
	v["actions"] = s.dtos(t, "anomaly_actions", Row{"anomaly_id": a["id"]})
	v["notifications"] = []Row{}
	for _, n := range t.All("channel_notifications", nil) {
		if (a["first_notification_id"] != nil && n["id"] == a["first_notification_id"]) || (a["receipt_id"] != nil && n["receipt_id"] == a["receipt_id"]) {
			v["notifications"] = append(v["notifications"].([]Row), s.dto(t, "channel_notifications", n))
		}
	}
	v["receipt"] = s.dto(t, "receipts", t.One("receipts", Row{"id": a["receipt_id"]}))
	v["refund"] = s.dto(t, "refunds", t.One("refunds", Row{"id": a["refund_id"]}))
	return v
}
func (s *Service) response(t repository.Unit, op string, ref Ref) any {
	r := t.One(ref.Table, Row{"id": ref.ID})
	switch ref.Table {
	case "orders":
		return s.orderDetail(t, r)
	case "payment_anomalies":
		return s.anomalyDetail(t, r)
	case "refund_applications":
		if op == "review" {
			return Row{"application": s.dto(t, ref.Table, r), "refund": s.dto(t, "refunds", t.One("refunds", Row{"application_id": r["id"]}))}
		}
	}
	return s.dto(t, ref.Table, r)
}
func rowTime(r Row) time.Time {
	for _, k := range []string{"_sort_time", "created_at", "received_at", "shipped_at"} {
		if v := r.T(k); !v.IsZero() {
			return v
		}
	}
	return time.Time{}
}
func (s *Service) page(rows []Row, limit int, cursor string) (any, error) {
	var ct time.Time
	var cid string
	var e error
	if cursor != "" {
		ct, cid, e = security.ReadCursor(cursor, s.Secret)
		if e != nil {
			return nil, d.Invalid("分页游标无效")
		}
	}
	sort.Slice(rows, func(i, j int) bool {
		a, b := rowTime(rows[i]), rowTime(rows[j])
		if a.Equal(b) {
			return rows[i].S("id") > rows[j].S("id")
		}
		return a.After(b)
	})
	out := []Row{}
	more := false
	for _, r := range rows {
		rt := rowTime(r)
		if cursor != "" && (rt.After(ct) || (rt.Equal(ct) && r.S("id") >= cid)) {
			continue
		}
		if len(out) == limit {
			more = true
			break
		}
		out = append(out, r)
	}
	var next any
	if more && len(out) > 0 {
		r := out[len(out)-1]
		next = security.Cursor(rowTime(r), r.S("id"), s.Secret)
	}
	for _, r := range out {
		delete(r, "_sort_time")
	}
	return Row{"items": out, "next_cursor": next}, nil
}
func (s *Service) Read(ctx context.Context, actor Row, kind, id string, f Row, limit int, cursor string) (any, error) {
	return s.Store.Run(ctx, false, func(t repository.Unit) (any, error) {
		switch kind {
		case "order", "reconciliation":
			o, e := s.owned(t, id, actor)
			if e != nil {
				return nil, e
			}
			if kind == "order" {
				return s.orderDetail(t, o), nil
			}
			return s.reconciliation(t, o), nil
		case "anomaly":
			a := t.One("payment_anomalies", Row{"id": id})
			if e := d.Require(a); e != nil {
				return nil, e
			}
			return s.anomalyDetail(t, a), nil
		case "summary":
			return s.summary(t, f.S("product_id")), nil
		}
		table := kind
		where := Row{}
		for k, v := range f {
			where[k] = v
		}
		if kind == "orders" && actor.S("role") == "BUYER" {
			where["buyer_id"] = actor["id"]
		}
		if kind == "products" && actor.S("role") == "BUYER" {
			where["sale_status"] = "ON_SHELF"
		}
		if kind == "warehouse" {
			table = "orders"
			where["status"] = "PENDING_SHIPMENT"
		}
		rows := []Row{}
		for _, r := range t.All(table, where) {
			if kind == "warehouse" {
				if d.CanShip(r) {
					v := pick(r, "id order_no name_snapshot quantity paid_at")
					v["_sort_time"] = r["created_at"]
					v["can_ship"] = true
					rows = append(rows, v)
				}
				continue
			}
			if table == "refund_applications" && f["status"] == nil && r.S("status") != "PENDING" {
				continue
			}
			if actor.S("role") == "SUPPORT" && table == "refunds" && f["status"] == nil && r.S("status") == "SUCCEEDED" {
				continue
			}
			if actor.S("role") == "SUPPORT" && table == "payment_anomalies" && f["status"] == nil && r.S("status") == "RESOLVED" {
				continue
			}
			v := s.dto(t, table, r)
			v["_sort_time"] = rowTime(r)
			rows = append(rows, v)
		}
		return s.page(rows, limit, cursor)
	})
}
func addMoney(sum *big.Int, r Row, k string) { sum.Add(sum, big.NewInt(r.N(k))) }
func (s *Service) reconciliation(t repository.Unit, o Row) Row {
	received, refunded := new(big.Int), new(big.Int)
	receipts := t.All("receipts", Row{"order_id": o["id"]})
	for _, r := range receipts {
		addMoney(received, r, "amount_cents")
	}
	refunds := t.All("refunds", Row{"order_id": o["id"]})
	unknown := false
	for _, r := range refunds {
		if r.S("status") == "SUCCEEDED" {
			addMoney(refunded, r, "amount_cents")
		} else {
			unknown = true
		}
	}
	anomalies := t.All("payment_anomalies", Row{"order_id": o["id"]})
	unresolved := 0
	for _, a := range anomalies {
		if a.S("status") != "RESOLVED" {
			unresolved++
		}
	}
	diff := []string{}
	p := t.One("products", Row{"id": o["product_id"]})
	if !d.Conserved(p) {
		diff = append(diff, "商品库存不守恒")
	}
	if unknown {
		diff = append(diff, "退款尚未成功结算")
	}
	if unresolved > 0 {
		diff = append(diff, "存在未解决支付异常")
	}
	if refunded.Cmp(received) > 0 {
		diff = append(diff, "退款超过实收")
	}
	audit := []Row{}
	for _, r := range t.All("audit_events", nil) {
		if r["entity_id"] == o["id"] {
			audit = append(audit, s.dto(t, "audit_events", r))
		}
	}
	return Row{"order": s.orderDetail(t, o), "inventory_entries": s.dtos(t, "inventory_ledger", Row{"order_id": o["id"]}), "receipts": s.dtos(t, "receipts", Row{"order_id": o["id"]}), "refunds": s.dtos(t, "refunds", Row{"order_id": o["id"]}), "shipment": s.dto(t, "shipments", t.One("shipments", Row{"order_id": o["id"]})), "anomalies": s.dtos(t, "payment_anomalies", Row{"order_id": o["id"]}), "audit_events": audit, "received_cents": received.String(), "refunded_cents": refunded.String(), "net_cents": new(big.Int).Sub(received, refunded).String(), "unresolved_count": unresolved, "consistent": len(diff) == 0, "differences": diff}
}
func (s *Service) summary(t repository.Unit, product string) Row {
	normal, exception, refund := new(big.Int), new(big.Int), new(big.Int)
	include := func(r Row) bool {
		if product == "" {
			return true
		}
		o := t.One("orders", Row{"id": r["order_id"]})
		return o != nil && o.S("product_id") == product
	}
	for _, r := range t.All("receipts", nil) {
		if include(r) {
			if r.S("classification") == "NORMAL" {
				addMoney(normal, r, "amount_cents")
			} else {
				addMoney(exception, r, "amount_cents")
			}
		}
	}
	unknown, failed := 0, 0
	for _, r := range t.All("refunds", nil) {
		if !include(r) {
			continue
		}
		switch r.S("status") {
		case "SUCCEEDED":
			addMoney(refund, r, "amount_cents")
		case "UNKNOWN":
			unknown++
		case "FAILED":
			failed++
		}
	}
	unverified, unresolved := 0, 0
	for _, n := range t.All("channel_notifications", nil) {
		if !n.B("auth_valid") {
			unverified++
		}
	}
	for _, a := range t.All("payment_anomalies", nil) {
		if include(a) && a.S("status") != "RESOLVED" {
			unresolved++
		}
	}
	where := Row{}
	if product != "" {
		where["id"] = product
	}
	total := new(big.Int).Add(normal, exception)
	return Row{"as_of": s.Now(t), "normal_received_cents": normal.String(), "exception_received_cents": exception.String(), "total_received_cents": total.String(), "refunded_cents": refund.String(), "net_cents": new(big.Int).Sub(total, refund).String(), "unverified_notification_count": unverified, "unknown_refund_count": unknown, "failed_refund_count": failed, "unresolved_anomaly_count": unresolved, "inventory": s.dtos(t, "products", where), "reconciliation_link_template": "/api/v1/operator/orders/{order_id}/reconciliation", "receipt_list_path": "/api/v1/operator/receipts", "refund_list_path": "/api/v1/operator/refunds", "anomaly_list_path": "/api/v1/operator/payment-anomalies"}
}
func (s *Service) Fingerprint() string { return fmt.Sprintf("scene1/MySQL/demo=%t", s.Demo) }
