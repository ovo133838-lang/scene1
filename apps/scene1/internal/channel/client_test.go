package channel

import (
	"context"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClientTrustAndErrors(t *testing.T) {
	status := 200
	raw := []byte(`{"data":{"status":"SUCCEEDED"}}`)
	valid := true
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if valid {
			w.Header().Set("X-Response-Signature", security.ResponseSignature(status, r.Header.Get("X-Nonce"), raw, "secret"))
		}
		w.WriteHeader(status)
		w.Write(raw)
	}))
	defer srv.Close()
	c := New(srv.URL, "secret")
	if r, e := c.Do(context.Background(), "POST", "/", map[string]string{"x": "1"}); e != nil || r.S("status") != "SUCCEEDED" {
		t.Fatal(r, e)
	}
	status = 404
	if _, e := c.Do(context.Background(), "GET", "/", nil); e == nil {
		t.Fatal("404")
	}
	status = 200
	valid = false
	if _, e := c.Do(context.Background(), "GET", "/", nil); e == nil {
		t.Fatal("unsigned")
	}
	valid = true
	raw = []byte(`broken`)
	if _, e := c.Do(context.Background(), "GET", "/", nil); e == nil {
		t.Fatal("bad JSON")
	}
	if _, e := c.Do(context.Background(), "GET", "/", make(chan int)); e == nil {
		t.Fatal("marshal")
	}
	bad := New("://bad", "secret")
	if _, e := bad.Do(context.Background(), "GET", "/", nil); e == nil {
		t.Fatal("url")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e := c.Do(ctx, "GET", "/", nil); e == nil {
		t.Fatal("cancel")
	}
	if (&HTTPError{500}).Error() == "" {
		t.Fatal("error")
	}
}
