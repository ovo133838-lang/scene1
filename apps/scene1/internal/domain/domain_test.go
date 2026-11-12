package domain

import (
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"testing"
	"time"
)

func TestDomainBoundaries(t *testing.T) {
	for _, s := range []string{"", "中", "a/b", "a?b", "a#b", ".", "..", "123456789"} {
		if ExternalID(s, 1, 8) {
			t.Fatal("unsafe external ID", s)
		}
	}
	if !ExternalID("a-Z_9.x", 1, 8) {
		t.Fatal("safe external ID")
	}
	for _, s := range []string{"", "0", "01", "-1", "1.2", "1e2", "9223372036854775808"} {
		if _, e := Money(s); e == nil {
			t.Fatal(s)
		}
	}
	if n, e := Money("9223372036854775807"); e != nil || n != 9223372036854775807 {
		t.Fatal(n, e)
	}
	if !UUID(repository.ID()) || UUID("not-an-id") {
		t.Fatal("uuid")
	}
	for _, s := range []string{"", " x", "x ", "x\ny", string([]byte{255})} {
		if Text(s, 10) {
			t.Fatal(s)
		}
	}
	if !Text("中文", 2) || Text("abc", 2) || !ASCII("valid-key", 2, 20) || ASCII("中文", 1, 20) || ASCII(" ", 1, 20) || ASCII("a", 2, 4) {
		t.Fatal("text")
	}
	now := time.Now()
	r := Row{"expires_at": now, "status": "PENDING_SHIPMENT"}
	if !Expired(r, now) || Expired(r, now.Add(-1)) || !CanShip(r) || !CanApply(r) {
		t.Fatal("boundary")
	}
	r["active_application_id"] = "x"
	if CanShip(r) {
		t.Fatal("freeze")
	}
	p := Row{"initial_quantity": int64(5), "available_quantity": int64(3), "reserved_quantity": int64(1), "shipped_quantity": int64(1)}
	if !Conserved(p) {
		t.Fatal(p)
	}
	for _, kind := range []string{"RESERVE", "CLOSE_RELEASE", "REFUND_RELEASE", "SHIP", "ADJUST"} {
		a, b, c, adj, e := StockVector(kind, 2)
		if e != nil || a+b+c != adj {
			t.Fatal(kind)
		}
	}
	if _, _, _, _, e := StockVector("BAD", 1); e == nil {
		t.Fatal("bad")
	}
	if Require(nil) == nil || Require(p) != nil || Invalid("x").Error() != "INVALID_ARGUMENT" || Conflict("x").Error() != "STATE_CONFLICT" {
		t.Fatal("errors")
	}
}
