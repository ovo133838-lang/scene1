package httpapi

import (
	"context"
	"net/http"
	"testing"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

func TestSixCharacterTeachingPassword(t *testing.T) {
	f := fixture(t)
	_, err := f.m.Run(context.Background(), true, func(tx repository.Unit) (any, error) {
		for _, account := range tx.All("accounts", nil) {
			tx.Patch("accounts", account, Row{"password_hash": security.Password("123456")})
		}
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"buyer1", "buyer2", "buyer3", "operator", "warehouse", "support"} {
		t.Run(name, func(t *testing.T) {
			data := f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": name, "password": "123456"}, "", http.StatusOK)
			account := Row(data["account"].(map[string]any))
			if account.S("login_name") != name || account["password_hash"] != nil || data.S("token") == "" {
				t.Fatal("login identity or response whitelist incorrect")
			}
		})
	}
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "12345"}, "", http.StatusBadRequest)
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "654321"}, "", http.StatusUnauthorized)
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "demo-password-2026"}, "", http.StatusUnauthorized)
	f.a.Demo = false
	f.do(http.MethodPost, "/api/v1/auth/login", Row{"login_name": "buyer1", "password": "123456"}, "", http.StatusBadRequest)
}
