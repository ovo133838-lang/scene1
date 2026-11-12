package channel

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/security"
)

type Client struct {
	Base, Secret string
	HTTP         *http.Client
}

func New(base, secret string) *Client {
	return &Client{strings.TrimRight(base, "/"), secret, &http.Client{Timeout: 1500 * time.Millisecond}}
}

type HTTPError struct{ Status int }

func (e *HTTPError) Error() string { return http.StatusText(e.Status) }
func (c *Client) Do(ctx context.Context, method, path string, b any) (repository.Row, error) {
	var body []byte
	var err error
	if b != nil {
		body, err = json.Marshal(b)
		if err != nil {
			return nil, err
		}
	}
	r, err := http.NewRequestWithContext(ctx, method, c.Base+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	r.Header.Set("Content-Type", "application/json")
	security.Sign(r, body, c.Secret)
	resp, err := c.HTTP.Do(r)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 128*1024))
	if err != nil {
		return nil, err
	}
	if !security.VerifyResponse(resp.StatusCode, r.Header.Get("X-Nonce"), raw, resp.Header.Get("X-Response-Signature"), c.Secret) {
		return nil, errors.New("invalid channel response signature")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, &HTTPError{resp.StatusCode}
	}
	var envelope struct {
		Data repository.Row `json:"data"`
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err = dec.Decode(&envelope); err != nil {
		return nil, err
	}
	return envelope.Data, nil
}
