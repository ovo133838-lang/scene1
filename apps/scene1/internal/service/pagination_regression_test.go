package service

import (
	"testing"
	"time"
)

// DTOs may omit created_at; pagination must still follow the stored creation time.
func TestListSortDoesNotDependOnDTOTimeWhitelist(t *testing.T) {
	f := setup(t)
	a, b := f.m.Tables["products"][0], f.m.Tables["products"][1]
	if a.S("id") > b.S("id") {
		a, b = b, a
	}
	a["created_at"] = time.Date(2026, 11, 12, 12, 0, 0, 0, time.UTC)
	b["created_at"] = a.T("created_at").Add(-time.Hour)
	first, e := f.s.Read(ctx, f.op, "products", "", Row{}, 1, "")
	if e != nil {
		t.Fatal(e)
	}
	page := first.(Row)
	rows := page["items"].([]Row)
	if len(rows) != 1 || rows[0].S("id") != a.S("id") {
		t.Fatal("newer product must precede lexically larger older ID", rows)
	}
	if rows[0]["created_at"] != nil || rows[0]["_sort_time"] != nil {
		t.Fatal("internal sorting field leaked", rows[0])
	}
	second, e := f.s.Read(ctx, f.op, "products", "", Row{}, 1, page.S("next_cursor"))
	if e != nil || second.(Row)["items"].([]Row)[0].S("id") != b.S("id") {
		t.Fatal("second page", second, e)
	}
}
