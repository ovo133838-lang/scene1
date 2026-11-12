// Package testsupport is an isolated unit-test double, never imported by production binaries.
// SQL constraints, durability and HTTP processes are tested separately against real MySQL.
package testsupport

import (
	"context"
	"fmt"
	"reflect"
	"sync"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
)

type Row = repository.Row
type Memory struct {
	mu      sync.Mutex
	Tables  map[string][]Row
	Failure error
	Mock    bool
}

func New() *Memory {
	return &Memory{Tables: map[string][]Row{"demo_clock": {{"id": int64(1), "offset_seconds": int64(0), "version": int64(0)}}}}
}
func (m *Memory) InitClock(context.Context) error { return m.Failure }
func (m *Memory) Ping(context.Context) error      { return m.Failure }
func clone(v any) any {
	switch x := v.(type) {
	case Row:
		r := Row{}
		for k, v := range x {
			r[k] = clone(v)
		}
		return r
	case map[string]any:
		r := map[string]any{}
		for k, v := range x {
			r[k] = clone(v)
		}
		return r
	case []Row:
		r := []Row{}
		for _, v := range x {
			r = append(r, clone(v).(Row))
		}
		return r
	}
	return v
}
func (m *Memory) Run(ctx context.Context, write bool, fn func(repository.Unit) (any, error)) (any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.Failure != nil {
		return nil, m.Failure
	}
	if e := ctx.Err(); e != nil {
		return nil, e
	}
	next := map[string][]Row{}
	for k, v := range m.Tables {
		next[k] = clone(v).([]Row)
	}
	u := &unit{tables: next, mock: m.Mock}
	v, e := fn(repository.BindRequest(u, ctx))
	if e == nil && write {
		m.Tables = next
	}
	return v, e
}

type unit struct {
	tables map[string][]Row
	mock   bool
}

func (u *unit) Err() error { return nil }
func (u *unit) All(table string, where Row) []Row {
	out := []Row{}
	for _, r := range u.tables[table] {
		ok := true
		for k, v := range where {
			if !reflect.DeepEqual(r[k], v) && fmt.Sprint(r[k]) != fmt.Sprint(v) {
				ok = false
				break
			}
		}
		if ok {
			out = append(out, r)
		}
	}
	return out
}
func (u *unit) One(table string, where Row) Row {
	r := u.All(table, where)
	if len(r) == 0 {
		return nil
	}
	return r[0]
}
func (u *unit) Add(table string, values Row) Row {
	key := table
	if u.mock {
		key = "mock." + table
	}
	r := Row{}
	for k, typ := range repository.Schema[key] {
		switch typ {
		case "integer", "smallint", "bigint":
			r[k] = int64(0)
		case "boolean":
			r[k] = false
		case "jsonb":
			r[k] = Row{}
		default:
			r[k] = nil
		}
	}
	r["id"] = repository.ID()
	r["created_at"] = time.Now().UTC()
	r["updated_at"] = time.Now().UTC()
	for k, v := range values {
		r[k] = v
	}
	u.tables[table] = append(u.tables[table], r)
	return r
}
func (u *unit) Patch(_ string, r Row, changes Row) Row {
	for k, v := range changes {
		r[k] = v
	}
	return r
}
