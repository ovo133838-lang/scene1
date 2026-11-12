package wire

import (
	"encoding/json"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestStrictJSON(t *testing.T) {
	for _, s := range []string{`{}`, `{"a":{"nested":[1,true,null]}}`} {
		r := httptest.NewRequest("POST", "/", strings.NewReader(s))
		if _, _, e := Decode(r); e != nil {
			t.Fatal(s, e)
		}
	}
	for _, s := range []string{``, `[]`, `null`, `{"x":1,"x":2}`, `{"a":{"x":1,"x":2}}`, `{"x":1} {}`, `{"x":`, string([]byte{255}), strings.Repeat("x", 65537)} {
		if _, _, e := Decode(httptest.NewRequest("POST", "/", strings.NewReader(s))); e == nil {
			t.Fatal(s[:min(len(s), 30)])
		}
	}
	for _, b := range []repository.Row{{}, {"x": nil}, {"x": "ok", "extra": "x"}, {"x": true}, {"x": " "}} {
		if Validate(b, "x", "") == nil {
			t.Fatal(b)
		}
	}
	for _, b := range []repository.Row{{"quantity": "1"}, {"quantity": json.Number("1.5")}, {"quantity": json.Number("-1")}, {"amount_cents": "01"}, {"product_id": "bad"}} {
		for k := range b {
			if Validate(b, k, "") == nil {
				t.Fatal(b)
			}
		}
	}
	if e := Validate(repository.Row{"quantity": json.Number("1"), "reason": "中文"}, "quantity reason", ""); e != nil {
		t.Fatal(e)
	}
	for _, s := range []string{"0", "101", "x"} {
		if _, e := Limit(httptest.NewRequest("GET", "/?limit="+s, nil)); e == nil {
			t.Fatal(s)
		}
	}
	if n, e := Limit(httptest.NewRequest("GET", "/", nil)); e != nil || n != 20 {
		t.Fatal(n)
	}
	if n, e := Limit(httptest.NewRequest("GET", "/?limit=2", nil)); e != nil || n != 2 {
		t.Fatal(n)
	}
	w := httptest.NewRecorder()
	Write(w, httptest.NewRequest("GET", "/", nil), 201, repository.Row{"ok": true}, "secret")
	if w.Code != 201 || w.Header().Get("X-Response-Signature") == "" {
		t.Fatal(w)
	}
}

func TestExternalIDsArePathSafe(t *testing.T) {
	for _, key := range []string{"event_id", "merchant_ref", "request_id", "order_ref", "txn_id", "refund_id", "target_order_ref", "target_request_id"} {
		for _, value := range []string{"中", "a?b", "a#b", "a/b", "a%b", ".", "..", strings.Repeat("x", 81)} {
			if Validate(repository.Row{key: value}, key, "") == nil {
				t.Fatalf("accepted %s=%s", key, value)
			}
		}
		if err := Validate(repository.Row{key: "external-1.a_b"}, key, ""); err != nil {
			t.Fatal(err)
		}
	}
}
