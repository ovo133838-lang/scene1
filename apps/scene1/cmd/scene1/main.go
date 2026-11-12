package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/ovo133838-lang/scene1/apps/scene1/internal/channel"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/httpapi"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/mockpay"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/repository"
	"github.com/ovo133838-lang/scene1/apps/scene1/internal/service"
	"github.com/ovo133838-lang/scene1/apps/scene1/web"
	"github.com/zeromicro/go-zero/core/conf"
	"github.com/zeromicro/go-zero/rest"
)

var version = "dev-worktree"

func envFile(path string) error {
	f, e := os.Open(path)
	if os.IsNotExist(e) {
		return nil
	}
	if e != nil {
		return e
	}
	defer f.Close()
	scan := bufio.NewScanner(f)
	for scan.Scan() {
		line := strings.TrimSpace(scan.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok || !strings.HasPrefix(k, "SCENE1_") {
			return fmt.Errorf("invalid local configuration key")
		}
		if _, set := os.LookupEnv(k); !set {
			os.Setenv(k, v)
		}
	}
	return scan.Err()
}
func main() {
	mode := flag.String("mode", "shop", "shop or mock")
	env := flag.String("env", ".env.local", "local environment file (never committed)")
	migrate := flag.Bool("migrate-only", false, "apply migrations and exit")
	flag.Parse()
	if e := envFile(*env); e != nil {
		log.Fatal("cannot load local configuration")
	}
	secret, admin := os.Getenv("SCENE1_HMAC_SECRET"), os.Getenv("SCENE1_ADMIN_TOKEN")
	if len(secret) < 32 || len(admin) < 32 {
		log.Fatal("HMAC and admin secrets must each contain at least 32 characters")
	}
	demo := os.Getenv("SCENE1_DEMO") == "true"
	isMock := *mode == "mock"
	if !isMock && *mode != "shop" {
		log.Fatal("unknown mode")
	}
	dsn := os.Getenv("SCENE1_MYSQL_DSN")
	if isMock {
		dsn = os.Getenv("SCENE1_MOCK_DSN")
	}
	store, e := repository.Open(dsn, isMock)
	if e != nil {
		log.Fatal("database connection failed; check local credentials and service")
	}
	defer store.DB.Close()
	ctx := context.Background()
	if e = store.Migrate(ctx); e != nil {
		log.Fatalf("migration failed: %v", e)
	}
	shopURL := os.Getenv("SCENE1_SHOP_URL")
	if shopURL == "" {
		shopURL = "http://127.0.0.1:18080"
	}
	mockURL := os.Getenv("SCENE1_MOCK_URL")
	if mockURL == "" {
		mockURL = "http://127.0.0.1:18081"
	}
	api := &httpapi.API{Secret: secret, Admin: admin, Demo: demo, Version: version}
	var handler http.Handler
	port := 18080
	routes := httpapi.ShopRoutes
	if isMock {
		port = 18081
		routes = httpapi.MockRoutes
		p := &mockpay.Provider{Store: store, Shop: channel.New(shopURL, secret), Secret: secret, Admin: admin, Demo: demo}
		api.Mock = p
		handler = api.Handler(nil)
		if !*migrate {
			go every(ctx, 100*time.Millisecond, p.DeliverOnce)
		}
	} else {
		s := &service.Service{Store: store, Secret: secret, Demo: demo}
		if e = s.Seed(ctx, os.Getenv("SCENE1_PASSWORD")); e != nil {
			log.Fatal("seed failed (password requires at least 12 characters)")
		}
		api.Shop = s
		api.Channel = channel.New(mockURL, secret)
		sub, _ := fs.Sub(web.Files, "public")
		handler = api.Handler(http.FileServer(http.FS(sub)))
		if !*migrate {
			go every(ctx, 100*time.Millisecond, func(ctx context.Context) error { return s.WorkOnce(ctx, api.Channel) })
			go every(ctx, time.Second, s.Expire)
		}
	}
	if *migrate {
		fmt.Println("migrations and seed complete")
		return
	}
	if p := os.Getenv("SCENE1_PORT"); p != "" {
		port, _ = strconv.Atoi(p)
	}
	host := os.Getenv("SCENE1_HOST")
	if host == "" {
		host = "127.0.0.1"
	}
	raw, _ := json.Marshal(map[string]any{"Name": "scene1-" + *mode, "Host": host, "Port": port, "Mode": "dev", "MaxBytes": 131072, "Timeout": 10000, "Log": map[string]any{"Mode": "console", "Level": "error"}, "Middlewares": map[string]any{"Log": false, "Trace": false, "Prometheus": false, "Metrics": false, "Shedding": false}})
	var cfg rest.RestConf
	if e = conf.LoadFromJsonBytes(raw, &cfg); e != nil {
		log.Fatal("HTTP configuration failed")
	}
	server, e := rest.NewServer(cfg, rest.WithNotFoundHandler(handler))
	if e != nil {
		log.Fatal("HTTP initialization failed")
	}
	defer server.Stop()
	for _, r := range routes {
		path := strings.ReplaceAll(strings.ReplaceAll(r.Path, "{", ":"), "}", "")
		server.AddRoute(rest.Route{Method: r.Method, Path: path, Handler: handler.ServeHTTP})
	}
	fmt.Printf("scene1 %s ready on %s:%d version=%s\n", *mode, host, port, version)
	server.Start()
}
func every(ctx context.Context, duration time.Duration, fn func(context.Context) error) {
	tick := time.NewTicker(duration)
	defer tick.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			if e := fn(ctx); e != nil {
				log.Print("background job deferred; dependency or storage error (no credentials logged)")
			}
		}
	}
}
