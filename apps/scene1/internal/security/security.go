package security

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"golang.org/x/crypto/argon2"
)

func Token() string {
	b := make([]byte, 32)
	if _, e := rand.Read(b); e != nil {
		panic(e)
	}
	return hex.EncodeToString(b)
}
func Password(p string) string {
	salt := make([]byte, 16)
	if _, e := rand.Read(salt); e != nil {
		panic(e)
	}
	h := argon2.IDKey([]byte(p), salt, 1, 32*1024, 2, 32)
	return "argon2id$" + base64.RawStdEncoding.EncodeToString(salt) + "$" + base64.RawStdEncoding.EncodeToString(h)
}
func VerifyPassword(p, hash string) bool {
	v := strings.Split(hash, "$")
	if len(v) != 3 || v[0] != "argon2id" {
		return false
	}
	salt, e := base64.RawStdEncoding.DecodeString(v[1])
	if e != nil || len(salt) != 16 {
		return false
	}
	want, e := base64.RawStdEncoding.DecodeString(v[2])
	if e != nil || len(want) != 32 {
		return false
	}
	got := argon2.IDKey([]byte(p), salt, 1, 32*1024, 2, 32)
	return subtle.ConstantTimeCompare(got, want) == 1
}
func Digest(b []byte) string { v := sha256.Sum256(b); return hex.EncodeToString(v[:]) }

const ShopToMock = "shop-to-mock"
const MockToShop = "mock-to-shop"

func KeyID(path string) string {
	if strings.HasPrefix(path, "/mock/") {
		return ShopToMock
	}
	return MockToShop
}

// Canonical uses RFC3986 query encoding, with a single path-and-query line.
func Canonical(r *http.Request, body []byte) string {
	path := r.URL.EscapedPath()
	if query := strings.ReplaceAll(r.URL.Query().Encode(), "+", "%20"); query != "" {
		path += "?" + query
	}
	return strings.Join([]string{strings.ToUpper(r.Method), path, r.Header.Get("X-Timestamp"), r.Header.Get("X-Nonce"), Digest(body)}, "\n")
}
func signature(r *http.Request, body []byte, secret string) string {
	derived := hmac.New(sha256.New, []byte(secret))
	derived.Write([]byte(KeyID(r.URL.Path)))
	h := hmac.New(sha256.New, derived.Sum(nil))
	h.Write([]byte(Canonical(r, body)))
	return hex.EncodeToString(h.Sum(nil))
}
func Sign(r *http.Request, body []byte, secret string) {
	r.Header.Set("X-Key-Id", KeyID(r.URL.Path))
	r.Header.Set("X-Timestamp", strconv.FormatInt(time.Now().Unix(), 10))
	r.Header.Set("X-Nonce", Token())
	r.Header.Set("X-Signature", signature(r, body, secret))
}
func Verify(r *http.Request, body []byte, secret string) error {
	stamp, e := strconv.ParseInt(r.Header.Get("X-Timestamp"), 10, 64)
	if e != nil || stamp < time.Now().Unix()-300 || stamp > time.Now().Unix()+300 {
		return errors.New("INVALID_SIGNATURE")
	}
	nonce := r.Header.Get("X-Nonce")
	if len(nonce) < 16 || len(nonce) > 64 || r.Header.Get("X-Key-Id") != KeyID(r.URL.Path) {
		return errors.New("INVALID_SIGNATURE")
	}
	for _, c := range nonce {
		if c < 33 || c > 126 {
			return errors.New("INVALID_SIGNATURE")
		}
	}
	sig, e := hex.DecodeString(r.Header.Get("X-Signature"))
	if e != nil {
		return errors.New("INVALID_SIGNATURE")
	}
	want, _ := hex.DecodeString(signature(r, body, secret))
	if !hmac.Equal(sig, want) {
		return errors.New("INVALID_SIGNATURE")
	}
	return nil
}
func Cursor(created time.Time, id, secret string) string {
	raw := fmt.Sprintf("%s|%s", created.UTC().Format(time.RFC3339Nano), id)
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(raw))
	return base64.RawURLEncoding.EncodeToString([]byte(raw + "|" + hex.EncodeToString(h.Sum(nil))))
}
func ReadCursor(v, secret string) (time.Time, string, error) {
	b, e := base64.RawURLEncoding.DecodeString(v)
	if e != nil {
		return time.Time{}, "", e
	}
	p := strings.Split(string(b), "|")
	if len(p) != 3 {
		return time.Time{}, "", errors.New("invalid cursor")
	}
	t, e := time.Parse(time.RFC3339Nano, p[0])
	if e != nil {
		return t, "", e
	}
	if Cursor(t, p[1], secret) != v {
		return t, "", errors.New("invalid cursor")
	}
	return t, p[1], nil
}
func ResponseSignature(status int, nonce string, body []byte, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	fmt.Fprintf(h, "%d\n%s\n%s", status, nonce, Digest(body))
	return hex.EncodeToString(h.Sum(nil))
}
func VerifyResponse(status int, nonce string, body []byte, sig, secret string) bool {
	return hmac.Equal([]byte(ResponseSignature(status, nonce, body, secret)), []byte(sig))
}
