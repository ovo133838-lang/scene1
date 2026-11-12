package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

func TestBoundRequestCorrelation(t *testing.T) {
	ctx := WithRequestID(context.Background(), "server-generated-id")
	if RequestID(ctx) != "server-generated-id" || RequestID(context.Background()) != "" {
		t.Fatal("context correlation")
	}
	if AuditRequestID(BindRequest(nil, ctx)) != "server-generated-id" || AuditRequestID(nil) == "" {
		t.Fatal("unit correlation")
	}
	if AuditRequestID(BindRequest(nil, context.Background())) == "" {
		t.Fatal("background correlation")
	}
}

func dbmock(t *testing.T) (*Store, sqlmock.Sqlmock) {
	t.Helper()
	db, m, e := sqlmock.New()
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() {
		if e := m.ExpectationsWereMet(); e != nil {
			t.Error(e)
		}
		db.Close()
	})
	return &Store{DB: db}, m
}
func begin(m sqlmock.Sqlmock, write, mock bool) {
	m.ExpectBegin()
	if write {
		q := "SELECT id FROM demo_clock"
		if mock {
			q = "SELECT id FROM runtime_lock"
		}
		m.ExpectQuery(q).WillReturnRows(sqlmock.NewRows([]string{"id"}).AddRow(1))
	}
}
func TestRowTypesAndStoreBoundaries(t *testing.T) {
	r := Row{"s": "x", "i": 1, "i64": int64(2), "f": float64(3), "j": json.Number("4"), "b": true, "t": time.Now()}
	if r.S("s") != "x" || r.S("missing") != "" || r.N("i") != 1 || r.N("i64") != 2 || r.N("f") != 3 || r.N("j") != 4 || r.N("missing") != 0 || !r.B("b") || r.T("t").IsZero() {
		t.Fatal(r)
	}
	var nilrow Row
	if nilrow.S("x") != "" || nilrow.N("x") != 0 {
		t.Fatal("nil")
	}
	if ID() == ID() || len(Hash(nil)) != 64 {
		t.Fatal("ids")
	}
	if _, e := Open("bad dsn", false); e == nil {
		t.Fatal("dsn")
	}
	if s, e := Open("u:p@tcp(127.0.0.1:1)/x", false); e == nil {
		if s != nil {
			s.DB.Close()
		}
		t.Fatal("unavailable")
	}
	s, m := dbmock(t)
	m.ExpectExec("INSERT IGNORE").WillReturnResult(sqlmock.NewResult(1, 1))
	if e := s.InitClock(context.Background()); e != nil {
		t.Fatal(e)
	}
	if e := s.Ping(context.Background()); e != nil {
		t.Fatal(e)
	}
}
func TestTransactionsAtomicity(t *testing.T) {
	for _, mock := range []bool{false, true} {
		s, m := dbmock(t)
		s.Mock = mock
		begin(m, true, mock)
		m.ExpectCommit()
		v, e := s.Run(context.Background(), true, func(u Unit) (any, error) { return "ok", nil })
		if e != nil || v != "ok" {
			t.Fatal(v, e)
		}
	}
	s, m := dbmock(t)
	begin(m, false, false)
	m.ExpectRollback()
	if _, e := s.Run(context.Background(), false, func(u Unit) (any, error) { return nil, errors.New("business error") }); e == nil {
		t.Fatal("rollback")
	}
	m.ExpectBegin().WillReturnError(errors.New("begin"))
	if _, e := s.Run(context.Background(), true, func(Unit) (any, error) { return nil, nil }); e == nil {
		t.Fatal("begin")
	}
	m.ExpectBegin()
	m.ExpectQuery("SELECT id").WillReturnError(errors.New("lock"))
	m.ExpectRollback()
	if _, e := s.Run(context.Background(), true, func(Unit) (any, error) { return nil, nil }); e == nil {
		t.Fatal("lock")
	}
	begin(m, false, false)
	m.ExpectCommit().WillReturnError(errors.New("commit"))
	if _, e := s.Run(context.Background(), false, func(Unit) (any, error) { return nil, nil }); e == nil {
		t.Fatal("commit")
	}
}
func TestCRUDParameterizationAndNormalization(t *testing.T) {
	s, m := dbmock(t)
	begin(m, true, false)
	m.ExpectExec("INSERT INTO `accounts`").WillReturnResult(sqlmock.NewResult(1, 1))
	m.ExpectExec("UPDATE `accounts`").WillReturnResult(sqlmock.NewResult(1, 1))
	cols := []string{"account_id", "created_at", "expires_at", "id", "revoked_at", "token_hash"}
	now := time.Now().UTC()
	m.ExpectQuery("SELECT .* FROM `sessions` WHERE `account_id`=\\? AND `revoked_at` IS NULL").WithArgs("account").WillReturnRows(sqlmock.NewRows(cols).AddRow([]byte("account"), now, now, []byte("session"), nil, []byte("hash")))
	m.ExpectQuery("SELECT .* FROM `sessions`").WillReturnRows(sqlmock.NewRows(cols))
	m.ExpectCommit()
	_, e := s.Run(context.Background(), true, func(u Unit) (any, error) {
		a := u.Add("accounts", Row{"login_name": "safe'; DROP TABLE accounts;--", "display_name": "x", "password_hash": "hash", "role": "BUYER", "enabled": true})
		if a.S("id") == "" {
			t.Fatal(a)
		}
		u.Patch("accounts", a, Row{"display_name": "updated"})
		u.Patch("accounts", a, Row{})
		if u.Patch("accounts", nil, Row{}) != nil {
			t.Fatal("nil")
		}
		r := u.One("sessions", Row{"account_id": "account", "revoked_at": nil})
		if r.S("id") != "session" || !r.T("created_at").Equal(now) {
			t.Fatal(r)
		}
		if u.One("sessions", nil) != nil {
			t.Fatal("empty")
		}
		if u.Err() != nil {
			t.Fatal(u.Err())
		}
		return nil, nil
	})
	if e != nil {
		t.Fatal(e)
	}
	if bind(Row{"x": 1}) != "{\"x\":1}" || bind("x") != "x" {
		t.Fatal("bind")
	}
}
func TestReadNumericBoolJSONAndFaults(t *testing.T) {
	s, m := dbmock(t)
	begin(m, false, false)
	cols := []string{}
	for k := range Schema["channel_notifications"] {
		cols = append(cols, k)
	}
	sort.Strings(cols)
	values := []any{}
	for _, k := range cols {
		switch Schema["channel_notifications"][k] {
		case "bigint":
			values = append(values, []byte("123"))
		case "boolean":
			values = append(values, int64(1))
		case "jsonb":
			values = append(values, []byte(`{"status":"OK"}`))
		case "timestamptz":
			values = append(values, time.Now().UTC())
		default:
			values = append(values, []byte("x"))
		}
	}
	row := sqlmock.NewRows(cols)
	driverValues := make([]interface{}, len(values))
	copy(driverValues, values)
	_ = driverValues
	// database/sql's driver.Value alias is required by the row builder.
	row.AddRow(toValues(values)...)
	m.ExpectQuery("SELECT").WillReturnRows(row)
	m.ExpectCommit()
	v, e := s.Run(context.Background(), false, func(u Unit) (any, error) { return u.One("channel_notifications", nil), nil })
	if e != nil || !v.(Row).B("auth_valid") || v.(Row).N("claimed_amount_cents") != 123 {
		t.Fatal(v, e)
	}
	for _, action := range []string{"table", "where", "insert", "patch", "query", "json", "int", "rowerror"} {
		s, m := dbmock(t)
		begin(m, false, false)
		if action == "query" {
			m.ExpectQuery("SELECT").WillReturnError(errors.New("query"))
		}
		if action == "json" || action == "int" {
			table, col := "channel_notifications", "payload_redacted"
			if action == "int" {
				table, col = "products", "available_quantity"
			}
			_ = table
			m.ExpectQuery("SELECT").WillReturnRows(sqlmock.NewRows([]string{col}).AddRow([]byte("invalid")))
		}
		if action == "rowerror" {
			m.ExpectQuery("SELECT").WillReturnRows(sqlmock.NewRows([]string{"id"}).AddRow("x").RowError(0, errors.New("row")))
		}
		m.ExpectRollback()
		_, e := s.Run(context.Background(), false, func(u Unit) (any, error) {
			switch action {
			case "table":
				u.All("not_a_table", nil)
			case "where":
				u.All("orders", Row{"evil": "x"})
			case "insert":
				u.Add("orders", Row{"evil": "x"})
			case "patch":
				u.Patch("orders", Row{"id": "x"}, Row{"evil": true})
			case "json":
				u.All("channel_notifications", nil)
			case "int":
				u.All("products", nil)
			default:
				u.All("orders", nil)
			}
			u.All("orders", nil)
			u.Add("orders", Row{})
			u.Patch("orders", Row{"id": "x"}, Row{})
			return nil, nil
		})
		if e == nil {
			t.Fatal(action)
		}
	}
}
func TestMigrationChecksumAndFailure(t *testing.T) {
	for _, mock := range []bool{false, true} {
		s, m := dbmock(t)
		s.Mock = mock
		scope := "shop"
		if mock {
			scope = "mock"
		}
		b, _ := assets.ReadFile("migrations/" + scope + ".sql")
		m.ExpectExec("CREATE TABLE IF NOT EXISTS schema_migrations").WillReturnResult(sqlmock.NewResult(0, 0))
		m.ExpectQuery("SELECT checksum").WillReturnError(sql.ErrNoRows)
		for _, stmt := range strings.Split(string(b), ";") {
			if strings.TrimSpace(stmt) != "" {
				m.ExpectExec(".*").WillReturnResult(sqlmock.NewResult(0, 0))
			}
		}
		m.ExpectExec("INSERT INTO schema_migrations").WillReturnResult(sqlmock.NewResult(1, 1))
		b2, _ := assets.ReadFile("migrations/" + scope + "-constraints.sql")
		m.ExpectQuery("SELECT checksum").WillReturnError(sql.ErrNoRows)
		for _, stmt := range strings.Split(string(b2), ";") {
			if strings.TrimSpace(stmt) != "" {
				m.ExpectExec(".*").WillReturnResult(sqlmock.NewResult(0, 0))
			}
		}
		m.ExpectExec("INSERT INTO schema_migrations").WillReturnResult(sqlmock.NewResult(1, 1))
		var b3 []byte
		if !mock {
			b3, _ = assets.ReadFile("migrations/shop-review-reason.sql")
			m.ExpectQuery("SELECT checksum").WillReturnError(sql.ErrNoRows)
			for _, stmt := range strings.Split(string(b3), ";") {
				if strings.TrimSpace(stmt) != "" {
					m.ExpectExec(".*").WillReturnResult(sqlmock.NewResult(0, 0))
				}
			}
			m.ExpectExec("INSERT INTO schema_migrations").WillReturnResult(sqlmock.NewResult(1, 1))
		}
		if e := s.Migrate(context.Background()); e != nil {
			t.Fatal(e)
		}
		m.ExpectExec("CREATE TABLE").WillReturnResult(sqlmock.NewResult(0, 0))
		m.ExpectQuery("SELECT checksum").WillReturnRows(sqlmock.NewRows([]string{"checksum"}).AddRow(Hash(b)))
		m.ExpectQuery("SELECT checksum").WillReturnRows(sqlmock.NewRows([]string{"checksum"}).AddRow(Hash(b2)))
		if !mock {
			m.ExpectQuery("SELECT checksum").WillReturnRows(sqlmock.NewRows([]string{"checksum"}).AddRow(Hash(b3)))
		}
		if e := s.Migrate(context.Background()); e != nil {
			t.Fatal(e)
		}
	}
	for _, which := range []string{"create", "query", "mismatch", "statement"} {
		s, m := dbmock(t)
		if which == "create" {
			m.ExpectExec("CREATE TABLE").WillReturnError(errors.New("create"))
		} else {
			m.ExpectExec("CREATE TABLE").WillReturnResult(sqlmock.NewResult(0, 0))
			switch which {
			case "query":
				m.ExpectQuery("SELECT checksum").WillReturnError(errors.New("query"))
			case "mismatch":
				m.ExpectQuery("SELECT checksum").WillReturnRows(sqlmock.NewRows([]string{"checksum"}).AddRow("wrong"))
			case "statement":
				m.ExpectQuery("SELECT checksum").WillReturnError(sql.ErrNoRows)
				m.ExpectExec("CREATE TABLE").WillReturnError(errors.New("ddl"))
			}
		}
		if e := s.Migrate(context.Background()); e == nil {
			t.Fatal(which)
		}
	}
}
