// Package repository owns parameterized persistence; business code never builds identifiers from requests.
package repository

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/go-sql-driver/mysql"
	"github.com/google/uuid"
)

//go:embed schema.json migrations/*.sql
var assets embed.FS
var Schema map[string]map[string]string

func init() {
	b, _ := assets.ReadFile("schema.json")
	if err := json.Unmarshal(b, &Schema); err != nil {
		panic(err)
	}
}

type Row map[string]any

func (r Row) S(k string) string {
	if r == nil || r[k] == nil {
		return ""
	}
	s, _ := r[k].(string)
	return s
}
func (r Row) N(k string) int64 {
	if r == nil {
		return 0
	}
	switch v := r[k].(type) {
	case int64:
		return v
	case int:
		return int64(v)
	case float64:
		return int64(v)
	case json.Number:
		n, _ := v.Int64()
		return n
	}
	return 0
}
func (r Row) B(k string) bool      { v, _ := r[k].(bool); return v }
func (r Row) T(k string) time.Time { v, _ := r[k].(time.Time); return v }
func ID() string                   { return uuid.NewString() }
func Hash(b []byte) string         { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }

type Store struct {
	DB   *sql.DB
	Mock bool
}

// Unit defines the transaction boundary consumed by use cases and isolated unit doubles.
type Unit interface {
	All(string, Row) []Row
	One(string, Row) Row
	Add(string, Row) Row
	Patch(string, Row, Row) Row
	Err() error
}
type Database interface {
	Run(context.Context, bool, func(Unit) (any, error)) (any, error)
	InitClock(context.Context) error
	Ping(context.Context) error
}

func (s *Store) Ping(ctx context.Context) error { return s.DB.PingContext(ctx) }
func (s *Store) InitClock(ctx context.Context) error {
	_, e := s.DB.ExecContext(ctx, "INSERT IGNORE INTO demo_clock VALUES(1,0,0,'bootstrap',?)", time.Now().UTC())
	return e
}

func Open(dsn string, mock bool) (*Store, error) {
	cfg, err := mysql.ParseDSN(dsn)
	if err != nil {
		return nil, errors.New("invalid database configuration")
	}
	cfg.ParseTime = true
	cfg.Loc = time.UTC
	cfg.Timeout = 5 * time.Second
	cfg.ReadTimeout = 10 * time.Second
	cfg.WriteTimeout = 10 * time.Second
	db, err := sql.Open("mysql", cfg.FormatDSN())
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(25)
	db.SetConnMaxLifetime(5 * time.Minute)
	return &Store{db, mock}, db.Ping()
}
func (s *Store) Migrate(ctx context.Context) error {
	_, err := s.DB.ExecContext(ctx, "CREATE TABLE IF NOT EXISTS schema_migrations (version varchar(40) PRIMARY KEY, checksum char(64) NOT NULL, applied_at datetime(6) NOT NULL)")
	if err != nil {
		return err
	}
	scope := "shop"
	if s.Mock {
		scope = "mock"
	}
	revisions := []struct{ version, path string }{{"001-" + scope, "migrations/" + scope + ".sql"}, {"002-" + scope, "migrations/" + scope + "-constraints.sql"}}
	if !s.Mock {
		revisions = append(revisions, struct{ version, path string }{"003-shop", "migrations/shop-review-reason.sql"})
	}
	for _, revision := range revisions {
		if err = s.applyMigration(ctx, revision.version, revision.path); err != nil {
			return err
		}
	}
	return nil
}
func (s *Store) applyMigration(ctx context.Context, version, path string) error {
	b, err := assets.ReadFile(path)
	if err != nil {
		return err
	}
	sum := Hash(b)
	var old string
	err = s.DB.QueryRowContext(ctx, "SELECT checksum FROM schema_migrations WHERE version=?", version).Scan(&old)
	if err == nil {
		if old != sum {
			return errors.New("migration checksum mismatch")
		}
		return nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return err
	}
	for _, stmt := range strings.Split(string(b), ";") {
		if strings.TrimSpace(stmt) == "" {
			continue
		}
		if _, err = s.DB.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("migration: %w", err)
		}
	}
	_, err = s.DB.ExecContext(ctx, "INSERT INTO schema_migrations VALUES(?,?,?)", version, sum, time.Now().UTC())
	return err
}

type Tx struct {
	tx   *sql.Tx
	ctx  context.Context
	mock bool
	err  error
}

func (s *Store) Run(ctx context.Context, write bool, fn func(Unit) (any, error)) (any, error) {
	tx, err := s.DB.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelRepeatableRead, ReadOnly: !write})
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	t := &Tx{tx: tx, ctx: ctx, mock: s.Mock}
	if write {
		q := "SELECT id FROM demo_clock WHERE id=1 FOR UPDATE"
		if s.Mock {
			q = "SELECT id FROM runtime_lock WHERE id=1 FOR UPDATE"
		}
		var id int
		if err = tx.QueryRowContext(ctx, q).Scan(&id); err != nil {
			return nil, err
		}
	}
	v, e := fn(BindRequest(t, ctx))
	if t.err != nil {
		return nil, t.err
	}
	if e != nil {
		return nil, e
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return v, nil
}
func (t *Tx) metadata(table string) (map[string]string, bool) {
	key := table
	if t.mock {
		key = "mock." + table
	}
	m, ok := Schema[key]
	if !ok {
		t.err = errors.New("unknown repository table")
	}
	return m, ok
}
func (t *Tx) columns(table string) []string {
	m, _ := t.metadata(table)
	cols := make([]string, 0, len(m))
	for k := range m {
		cols = append(cols, k)
	}
	sort.Strings(cols)
	return cols
}
func (t *Tx) All(table string, where Row) []Row {
	if t.err != nil {
		return nil
	}
	cols := t.columns(table)
	if t.err != nil {
		return nil
	}
	conds := []string{}
	args := []any{}
	keys := make([]string, 0, len(where))
	for k := range where {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	m, _ := t.metadata(table)
	for _, k := range keys {
		if _, ok := m[k]; !ok {
			t.err = errors.New("unknown query column")
			return nil
		}
		if where[k] == nil {
			conds = append(conds, "`"+k+"` IS NULL")
		} else {
			conds = append(conds, "`"+k+"`=?")
			args = append(args, where[k])
		}
	}
	q := "SELECT `" + strings.Join(cols, "`,`") + "` FROM `" + table + "`"
	if len(conds) > 0 {
		q += " WHERE " + strings.Join(conds, " AND ")
	}
	q += " ORDER BY id"
	rows, err := t.tx.QueryContext(t.ctx, q, args...)
	if err != nil {
		t.err = err
		return nil
	}
	defer rows.Close()
	result := []Row{}
	for rows.Next() {
		vals := make([]any, len(cols))
		ptr := make([]any, len(cols))
		for i := range vals {
			ptr[i] = &vals[i]
		}
		if err = rows.Scan(ptr...); err != nil {
			t.err = err
			return nil
		}
		r := Row{}
		for i, k := range cols {
			v := vals[i]
			typ := m[k]
			if b, ok := v.([]byte); ok {
				switch typ {
				case "bigint", "smallint", "integer":
					v, err = strconv.ParseInt(string(b), 10, 64)
				case "boolean":
					v = string(b) == "1"
				case "jsonb":
					var obj any
					err = json.Unmarshal(b, &obj)
					v = obj
				default:
					v = string(b)
				}
			}
			if typ == "boolean" {
				if n, ok := v.(int64); ok {
					v = n != 0
				}
			}
			r[k] = v
			if err != nil {
				t.err = err
				return nil
			}
		}
		result = append(result, r)
	}
	t.err = rows.Err()
	return result
}
func (t *Tx) One(table string, where Row) Row {
	r := t.All(table, where)
	if len(r) == 0 {
		return nil
	}
	return r[0]
}
func (t *Tx) Add(table string, values Row) Row {
	m, ok := t.metadata(table)
	if !ok {
		return nil
	}
	r := Row{}
	now := time.Now().UTC()
	for k, typ := range m {
		switch typ {
		case "uuid":
			r[k] = nil
		case "bigint", "smallint", "integer":
			r[k] = int64(0)
		case "boolean":
			r[k] = false
		case "timestamptz":
			r[k] = nil
		case "jsonb":
			r[k] = Row{}
		default:
			r[k] = nil
		}
	}
	r["id"] = ID()
	for _, k := range []string{"created_at", "updated_at"} {
		if _, ok = m[k]; ok {
			r[k] = now
		}
	}
	for k, v := range values {
		r[k] = v
	}
	t.insert(table, r)
	return r
}
func bind(v any) any {
	switch v.(type) {
	case Row, map[string]any, []any, []Row:
		b, _ := json.Marshal(v)
		return string(b)
	}
	return v
}
func (t *Tx) insert(table string, r Row) {
	if t.err != nil {
		return
	}
	m, _ := t.metadata(table)
	keys := []string{}
	for k := range r {
		if _, ok := m[k]; !ok {
			t.err = errors.New("unknown insert column")
			return
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	args := []any{}
	qs := []string{}
	for _, k := range keys {
		args = append(args, bind(r[k]))
		qs = append(qs, "?")
	}
	_, t.err = t.tx.ExecContext(t.ctx, "INSERT INTO `"+table+"` (`"+strings.Join(keys, "`,`")+"`) VALUES("+strings.Join(qs, ",")+")", args...)
}
func (t *Tx) Patch(table string, r Row, changes Row) Row {
	if r == nil || t.err != nil {
		return r
	}
	m, _ := t.metadata(table)
	keys := []string{}
	for k := range changes {
		if _, ok := m[k]; !ok {
			t.err = errors.New("unknown update column")
			return r
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	set := []string{}
	args := []any{}
	for _, k := range keys {
		r[k] = changes[k]
		set = append(set, "`"+k+"`=?")
		args = append(args, bind(r[k]))
	}
	if len(set) == 0 {
		return r
	}
	args = append(args, r["id"])
	_, t.err = t.tx.ExecContext(t.ctx, "UPDATE `"+table+"` SET "+strings.Join(set, ",")+" WHERE id=?", args...)
	return r
}
func (t *Tx) Err() error { return t.err }
