package service

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/wire"
)

// Independent counterexample: a contradictory terminal result makes the actual
// funds uncertain. A previous FAILED result must no longer authorize a new debit.
func TestIndependentContradictoryRefundBlocksNewAttempt(t *testing.T) {
	f := setup(t)
	o := f.create()
	f.paid(o)
	a := f.exec(f.buyer, "apply", o.S("id"), Row{"reason": "独立测试整单退款"})
	r := f.exec(f.support, "review", a.S("id"), Row{"decision": "APPROVE", "reason": "独立测试批准"})["refund"].(Row)
	failed := f.refundEvent(r, "FAILED")
	if got := f.notify("REFUND", failed).S("result"); got != "ACCEPTED" {
		t.Fatalf("initial explicit failure = %s", got)
	}
	contradiction := Row{}
	for k, v := range failed {
		contradiction[k] = v
	}
	contradiction["status"] = "SUCCEEDED"
	if got := f.notify("REFUND", contradiction).S("result"); got != "RESULT_CONFLICT" {
		t.Fatalf("contradictory success = %s", got)
	}
	if _, err := f.s.Exec(ctx, f.support, "retry_refund", r.S("id"), repository.ID(), Row{"reason": "冲突尚未可信核实"}); err == nil {
		t.Fatal("unsafe new refund attempt accepted after contradictory terminal success; expected rejection pending trusted reconciliation")
	}
	if got := f.detail(o).S("status"); got != "REFUND_PROCESSING" {
		t.Fatalf("order must remain frozen, got %s", got)
	}
}

// A subsequent authenticated NOT_FOUND does not erase a previously verified
// receipt. Contradictory provider evidence requires investigation, not closure.
func TestIndependentKnownFundsCannotBecomeNoFunds(t *testing.T) {
	f := setup(t)
	o := f.create()
	p := f.exec(f.buyer, "pay", o.S("id"), Row{})
	var request string
	f.m.Run(ctx, false, func(tx repository.Unit) (any, error) {
		request = tx.One("payment_intents", Row{"id": p["id"]}).S("provider_request_id")
		return nil, nil
	})
	f.exec(f.buyer, "cancel", o.S("id"), Row{"reason": "关闭后迟到款"})
	f.notify("PAYMENT", Row{"merchant_ref": "scene1", "request_id": request, "order_ref": o["id"], "txn_id": repository.ID(), "amount_cents": o["amount_cents"], "currency": "CNY", "status": "SUCCEEDED", "occurred_at": time.Now().UTC().Format(time.RFC3339Nano)})
	var anomaly Row
	f.m.Run(ctx, false, func(tx repository.Unit) (any, error) {
		anomaly = tx.One("payment_anomalies", Row{"order_id": o["id"]})
		return nil, nil
	})
	if anomaly == nil || anomaly["receipt_id"] == nil {
		t.Fatal("fixture must contain established late receipt")
	}
	provider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		wire.Write(w, req, http.StatusNotFound, Row{}, f.s.Secret)
	}))
	defer provider.Close()
	if _, err := f.s.VerifyAnomaly(ctx, channel.New(provider.URL, f.s.Secret), f.support, anomaly.S("id"), repository.ID(), "复查已知迟到实收"); err != nil {
		t.Fatal(err)
	}
	if _, err := f.s.Exec(ctx, f.support, "resolve_anomaly", anomaly.S("id"), repository.ID(), Row{"reason": "不得用404抹掉已知实收"}); err == nil {
		t.Fatal("known unrefunded receipt was marked NO_FUNDS and resolved following contradictory authenticated 404")
	}
}
