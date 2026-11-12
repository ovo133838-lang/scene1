package domain

import (
	"errors"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
)

type Row = repository.Row
type Fault struct {
	Code    string
	Status  int
	Message string
}

func (f *Fault) Error() string                           { return f.Code }
func Fail(code string, status int, message string) error { return &Fault{code, status, message} }
func Conflict(message string) error                      { return Fail("STATE_CONFLICT", 409, message) }
func Invalid(message string) error                       { return Fail("INVALID_ARGUMENT", 400, message) }
func Require(r Row) error {
	if r == nil {
		return Fail("NOT_FOUND", 404, "记录不存在或无权查看")
	}
	return nil
}
func UUID(s string) bool { u, e := uuid.Parse(s); return e == nil && u.String() == s }
func Text(s string, max int) bool {
	if !utf8.ValidString(s) || s != strings.TrimSpace(s) || utf8.RuneCountInString(s) < 1 || utf8.RuneCountInString(s) > max {
		return false
	}
	for _, c := range s {
		if unicode.IsControl(c) {
			return false
		}
	}
	return true
}
func ASCII(s string, min, max int) bool {
	if len(s) < min || len(s) > max {
		return false
	}
	for _, c := range s {
		if c < 33 || c > 126 {
			return false
		}
	}
	return true
}

// ExternalID is safe as one URL path segment and never contains query/fragment delimiters.
func ExternalID(s string, min, max int) bool {
	if len(s) < min || len(s) > max {
		return false
	}
	for _, c := range s {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '-' || c == '_' || c == '.') {
			return false
		}
	}
	return s != "." && s != ".."
}
func Money(s string) (int64, error) {
	if s == "" || s[0] == '0' {
		return 0, Invalid("金额须为正整数分的十进制字符串")
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, Invalid("金额格式错误")
		}
	}
	n, e := strconv.ParseInt(s, 10, 64)
	if e != nil || n <= 0 {
		return 0, Invalid("金额超出范围")
	}
	return n, nil
}
func Expired(order Row, now time.Time) bool { return !now.Before(order.T("expires_at")) }
func CanShip(order Row) bool {
	return order.S("status") == "PENDING_SHIPMENT" && order["active_application_id"] == nil
}
func CanApply(order Row) bool { return CanShip(order) }
func StockVector(kind string, q int64) (int64, int64, int64, int64, error) {
	switch kind {
	case "RESERVE":
		return -q, q, 0, 0, nil
	case "CLOSE_RELEASE", "REFUND_RELEASE":
		return q, -q, 0, 0, nil
	case "SHIP":
		return 0, -q, q, 0, nil
	case "ADJUST":
		return q, 0, 0, q, nil
	}
	return 0, 0, 0, 0, errors.New("unknown inventory event")
}
func Conserved(p Row) bool {
	return p.N("available_quantity") >= 0 && p.N("reserved_quantity") >= 0 && p.N("shipped_quantity") >= 0 && p.N("initial_quantity")+p.N("adjustment_net") == p.N("available_quantity")+p.N("reserved_quantity")+p.N("shipped_quantity")
}
