package httpapi

import (
	"context"
	"net/http"
	"testing"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

func TestIndependentTeachingPasswordIdentityAndSeed(t *testing.T) {
	f := fixture(t)
	_, err := f.m.Run(context.Background(), true, func(tx repository.Unit) (any, error) {
		account := tx.One("accounts", Row{"login_name": "buyer1"})
		tx.Patch("accounts", account, Row{"password_hash": security.Password("123456")})
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	// Startup's existing-account seed must not replace an already reset hash.
	if err := f.a.Shop.Seed(context.Background(), "independent-bootstrap-password"); err != nil {
		t.Fatal(err)
	}
	sessionsBefore := len(f.m.Tables["sessions"])
	for _, body := range []Row{
		{"login_name": "buyer1", "password": "wrong12"},
		{"login_name": "nobody", "password": "123456"},
	} {
		f.do(http.MethodPost, "/api/v1/auth/login", body, "", http.StatusUnauthorized)
	}
	if len(f.m.Tables["sessions"]) != sessionsBefore {
		t.Fatal("failed authentication created a session")
	}
	data := f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "123456"}, "", http.StatusOK)
	account := Row(data["account"].(map[string]any))
	if account.S("role") != "BUYER" {
		t.Fatal("password reset changed server-side role")
	}
	f.tokens["buyer1"] = data.S("token")
	me := f.do(http.MethodGet, "/api/v1/auth/me", nil, "buyer1", http.StatusOK)
	if me.S("role") != "BUYER" || me.S("login_name") != "buyer1" {
		t.Fatal("session identity mismatch")
	}
	f.do(http.MethodGet, "/api/v1/operator/summary", nil, "buyer1", http.StatusForbidden)
	f.do(http.MethodPost, "/api/v1/auth/logout", Row{}, "buyer1", http.StatusOK)
	f.do(http.MethodGet, "/api/v1/auth/me", nil, "buyer1", http.StatusUnauthorized)
	_, err = f.m.Run(context.Background(), true, func(tx repository.Unit) (any, error) {
		a := tx.One("accounts", Row{"login_name": "buyer1"})
		tx.Patch("accounts", a, Row{"enabled": false})
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "123456"}, "", http.StatusUnauthorized)
}

func TestIndependentNonDemoEightCharacterPassword(t *testing.T) {
	f := fixture(t)
	_, err := f.m.Run(context.Background(), true, func(tx repository.Unit) (any, error) {
		a := tx.One("accounts", Row{"login_name": "buyer1"})
		tx.Patch("accounts", a, Row{"password_hash": security.Password("testpass8")})
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	f.a.Demo = false
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "1234567"}, "", http.StatusBadRequest)
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "testpass8"}, "", http.StatusOK)
}
