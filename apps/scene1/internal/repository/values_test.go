package repository

import "database/sql/driver"

func toValues(values []any) []driver.Value {
	r := make([]driver.Value, len(values))
	for i, v := range values {
		r[i] = v
	}
	return r
}
