package security

import (
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPasswordAndSignatures(t *testing.T) {
	p := Password("valid-password")
	if !VerifyPassword("valid-password", p) || VerifyPassword("wrong", p) {
		t.Fatal("password")
	}
	for _, v := range []string{"", "x$a$b", "argon2id$!$!", "argon2id$YQ$YQ"} {
		if VerifyPassword("x", v) {
			t.Fatal(v)
		}
	}
	if Token() == Token() {
		t.Fatal("random")
	}
	r := httptest.NewRequest("POST", "http://example/a?b=2&a=1", nil)
	body := []byte(`{"a":1}`)
	Sign(r, body, "secret")
	if e := Verify(r, body, "secret"); e != nil {
		t.Fatal(e)
	}
	if Verify(r, body, "wrong") == nil {
		t.Fatal("wrong key")
	}
	r.Header.Set("X-Signature", "!")
	if Verify(r, body, "secret") == nil {
		t.Fatal("invalid hex")
	}
	Sign(r, body, "secret")
	r.Header.Set("X-Nonce", "x")
	if Verify(r, body, "secret") == nil {
		t.Fatal("nonce")
	}
	Sign(r, body, "secret")
	r.Header.Set("X-Timestamp", "0")
	if Verify(r, body, "secret") == nil {
		t.Fatal("stale")
	}
	sig := ResponseSignature(200, "nonce", body, "secret")
	if !VerifyResponse(200, "nonce", body, sig, "secret") || VerifyResponse(500, "nonce", body, sig, "secret") {
		t.Fatal("response")
	}
	now := time.Now()
	c := Cursor(now, "id", "secret")
	at, id, e := ReadCursor(c, "secret")
	if e != nil || !at.Equal(now) || id != "id" {
		t.Fatal(c, e)
	}
	for _, v := range []string{"!", "eA", c + "x", strings.Replace(c, "a", "b", 1)} {
		_, _, _ = ReadCursor(v, "secret")
	}
	if _, _, e = ReadCursor(c, "wrong"); e == nil {
		t.Fatal("tampered")
	}
}

func TestCanonicalFixedVectorAndDirection(t *testing.T) {
	r := httptest.NewRequest("POST", "/mock/v1/payments?z=%E4%B8%AD&a=one+two", nil)
	r.Header.Set("X-Timestamp", "1700000000")
	r.Header.Set("X-Nonce", "0123456789abcdef")
	want := "POST\n/mock/v1/payments?a=one%20two&z=%E4%B8%AD\n1700000000\n0123456789abcdef\n44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
	if Canonical(r, []byte("{}")) != want || signature(r, []byte("{}"), "vector-secret") != "e72c506718f45af3fe693c68f2f7c9d2068dd8397d95beaedef19fa99ce16bad" {
		t.Fatal("fixed external HMAC vector differs")
	}
	Sign(r, nil, "secret")
	if r.Header.Get("X-Key-Id") != ShopToMock || Verify(r, nil, "secret") != nil {
		t.Fatal("shop direction")
	}
	r.Header.Set("X-Key-Id", MockToShop)
	if Verify(r, nil, "secret") == nil {
		t.Fatal("wrong direction accepted")
	}
	r = httptest.NewRequest("POST", "/api/v1/channel/payment-notifications", nil)
	Sign(r, nil, "secret")
	if r.Header.Get("X-Key-Id") != MockToShop || Verify(r, nil, "secret") != nil {
		t.Fatal("mock direction")
	}
	r.Header.Set("X-Nonce", "0123456789abcde中")
	if Verify(r, nil, "secret") == nil {
		t.Fatal("non-ASCII nonce")
	}
}
