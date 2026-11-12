package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestLocalConfigAndWorkerLifecycle(t *testing.T) {
	dir := t.TempDir()
	if e := envFile(filepath.Join(dir, "missing")); e != nil {
		t.Fatal(e)
	}
	p := filepath.Join(dir, "env")
	t.Setenv("SCENE1_TEST_KEEP", "original")
	os.WriteFile(p, []byte("# example\n\nSCENE1_TEST_KEEP=other\nSCENE1_UNIT_CONFIG=value\n"), 0600)
	defer os.Unsetenv("SCENE1_UNIT_CONFIG")
	if e := envFile(p); e != nil || os.Getenv("SCENE1_TEST_KEEP") != "original" || os.Getenv("SCENE1_UNIT_CONFIG") != "value" {
		t.Fatal(e)
	}
	os.WriteFile(p, []byte("UNSUPPORTED=value\n"), 0600)
	if e := envFile(p); e == nil {
		t.Fatal("invalid key")
	}
	os.WriteFile(p, []byte(strings.Repeat("x", 100000)), 0600)
	if e := envFile(p); e == nil {
		t.Fatal("scanner error")
	}
	ctx, cancel := context.WithCancel(context.Background())
	var calls atomic.Int32
	done := make(chan struct{})
	go func() {
		every(ctx, time.Millisecond, func(context.Context) error { calls.Add(1); return errors.New("transient") })
		close(done)
	}()
	time.Sleep(5 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("worker leak")
	}
	if calls.Load() == 0 {
		t.Fatal("not run")
	}
}
