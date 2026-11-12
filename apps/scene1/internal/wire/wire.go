package wire

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"

	d "github.com/ovo133838-lang/scene1/apps/scene1/internal/domain"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

func scan(dec *json.Decoder) error {
	tok, e := dec.Token()
	if e != nil {
		return e
	}
	if delim, ok := tok.(json.Delim); ok {
		switch delim {
		case '{':
			seen := map[string]bool{}
			for dec.More() {
				key, e := dec.Token()
				if e != nil {
					return e
				}
				k, ok := key.(string)
				if !ok || seen[k] {
					return d.Invalid("JSON字段重复")
				}
				seen[k] = true
				if e = scan(dec); e != nil {
					return e
				}
			}
			_, e = dec.Token()
			return e
		case '[':
			for dec.More() {
				if e = scan(dec); e != nil {
					return e
				}
			}
			_, e = dec.Token()
			return e
		default:
			return d.Invalid("非法JSON")
		}
	}
	return nil
}
func Decode(r *http.Request) (repository.Row, []byte, error) {
	raw, e := io.ReadAll(io.LimitReader(r.Body, 65537))
	if e != nil {
		return nil, raw, d.Invalid("读取请求失败")
	}
	if len(raw) > 65536 {
		return nil, nil, d.Invalid("请求体超过64KiB")
	}
	if !utf8.Valid(raw) {
		return nil, raw, d.Invalid("请求须为UTF-8")
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if e = scan(dec); e != nil {
		return nil, raw, d.Invalid("请求JSON格式错误或字段重复")
	}
	if _, e = dec.Token(); e != io.EOF {
		return nil, raw, d.Invalid("存在尾随JSON")
	}
	dec = json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	var b repository.Row
	if e = dec.Decode(&b); e != nil || b == nil {
		return nil, raw, d.Invalid("请求须为JSON对象")
	}
	return b, raw, nil
}
func Validate(b repository.Row, required, optional string) error {
	allowed := map[string]bool{}
	for _, k := range strings.Fields(required + " " + optional) {
		allowed[k] = true
	}
	for _, k := range strings.Fields(required) {
		if b[k] == nil {
			return d.Invalid("缺少字段：" + k)
		}
	}
	for k, v := range b {
		if !allowed[k] {
			return d.Invalid("不支持字段：" + k)
		}
		if v == nil {
			return d.Invalid("字段不允许null：" + k)
		}
		integer := map[string]bool{"quantity": true, "version": true, "delta": true, "seconds": true, "attempt_no": true, "delay_ms": true, "repeat_count": true, "remaining_uses": true}
		if integer[k] {
			n, ok := v.(json.Number)
			if !ok {
				return d.Invalid("须为整数：" + k)
			}
			x, e := n.Int64()
			if e != nil {
				return d.Invalid("须为范围内整数：" + k)
			}
			if k != "delta" && x < 0 {
				return d.Invalid("整数不能为负：" + k)
			}
			continue
		}
		s, ok := v.(string)
		if !ok {
			return d.Invalid("须为字符串：" + k)
		}
		max := 80
		switch k {
		case "reason":
			max = 500
		case "name":
			max = 120
		case "password":
			max = 128
		case "login_name":
			max = 64
		}
		if !d.Text(s, max) {
			return d.Invalid("字段为空、超长、包含控制字符或首尾空格：" + k)
		}
		switch k {
		case "event_id", "merchant_ref", "request_id", "order_ref", "txn_id", "refund_id", "target_order_ref", "target_request_id":
			if !d.ExternalID(s, 1, 80) {
				return d.Invalid("外部业务ID须为1到80个安全ASCII字符：" + k)
			}
		}
		if k == "product_id" && !d.UUID(s) {
			return d.Invalid("商品ID格式错误")
		}
		if strings.HasSuffix(k, "_cents") {
			if _, e := d.Money(s); e != nil {
				return e
			}
		}
	}
	return nil
}
func Write(w http.ResponseWriter, r *http.Request, status int, data any, secret string) {
	raw, _ := json.Marshal(data)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	if secret != "" {
		w.Header().Set("X-Response-Signature", security.ResponseSignature(status, r.Header.Get("X-Nonce"), raw, secret))
	}
	w.WriteHeader(status)
	_, _ = w.Write(raw)
}
func Limit(r *http.Request) (int, error) {
	v := r.URL.Query().Get("limit")
	if v == "" {
		return 20, nil
	}
	n, e := strconv.Atoi(v)
	if e != nil || n < 1 || n > 100 {
		return 0, d.Invalid("limit须为1到100")
	}
	return n, nil
}
