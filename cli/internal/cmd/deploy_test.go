package cmd

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDeployImageNeedsARegistryTheWorkspaceCanPull(t *testing.T) {
	for _, c := range []struct {
		image, api string
		ok         bool
	}{
		{"ghcr.io/acme/agent:0.1.0", "https://api.konstera.ai", true},
		{"localhost:4505/acme/agent:0.1.0", "http://localhost:4500", true},
		{"localhost:4505/acme/agent:0.1.0", "https://api.konstera.ai", false},
		{"agent:0.1.0", "https://api.konstera.ai", false},
		{"ghcr.io/acme/agent", "https://api.konstera.ai", false},
		{"", "https://api.konstera.ai", false},
	} {
		if err := checkDeployImage(c.image, c.api); (err == nil) != c.ok {
			t.Errorf("checkDeployImage(%q, %q) = %v", c.image, c.api, err)
		}
	}
}

// fakeDevx answers the MCP handshake and agent_publish, recording the manifest.
func fakeDevx(t *testing.T, reply map[string]any, gotManifest *map[string]any) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var msg struct {
			ID     any             `json:"id"`
			Method string          `json:"method"`
			Params json.RawMessage `json:"params"`
		}
		_ = json.NewDecoder(r.Body).Decode(&msg)
		w.Header().Set("Content-Type", "application/json")
		switch msg.Method {
		case "initialize":
			w.Header().Set("Mcp-Session-Id", "s1")
			_ = json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": msg.ID, "result": map[string]any{}})
		case "notifications/initialized":
			w.WriteHeader(http.StatusAccepted)
		case "tools/call":
			var p struct {
				Name      string `json:"name"`
				Arguments struct {
					ManifestJSON string `json:"manifestJson"`
				} `json:"arguments"`
			}
			_ = json.Unmarshal(msg.Params, &p)
			if p.Name != "agent_publish" {
				t.Errorf("tool %q", p.Name)
			}
			_ = json.Unmarshal([]byte(p.Arguments.ManifestJSON), gotManifest)
			text, _ := json.Marshal(reply)
			_ = json.NewEncoder(w).Encode(map[string]any{"jsonrpc": "2.0", "id": msg.ID, "result": map[string]any{
				"content": []map[string]any{{"type": "text", "text": string(text)}},
			}})
		}
	}))
}

func writeManifest(t *testing.T) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "manifest.json")
	_ = os.WriteFile(p, []byte(`{"id":"order-helper","version":"0.1.0","runtime":{"kind":"container","image":"order-helper:0.1.0"}}`), 0o600)
	return p
}

func TestDeployPublishesWithTheImageItPushed(t *testing.T) {
	var got map[string]any
	srv := fakeDevx(t, map[string]any{"published": true, "agentId": "order-helper", "version": "0.1.0", "action": "inserted"}, &got)
	defer srv.Close()
	signedIn(t, srv.URL, deployScope)

	var out bytes.Buffer
	err := runDeploy(context.Background(), &out, &out, deployOptions{
		manifestPath: writeManifest(t), image: "localhost:4505/acme/order-helper:0.1.0", noBuild: true,
	})
	if err != nil {
		t.Fatalf("deploy: %v\n%s", err, out.String())
	}
	if rt, _ := got["runtime"].(map[string]any); rt["image"] != "localhost:4505/acme/order-helper:0.1.0" {
		t.Fatalf("published manifest: %v", got)
	}
	if !strings.Contains(out.String(), "Published order-helper 0.1.0") || !strings.Contains(out.String(), "Agents › Catalog") {
		t.Fatalf("output:\n%s", out.String())
	}
}

func TestDeployShowsManifestErrors(t *testing.T) {
	var got map[string]any
	srv := fakeDevx(t, map[string]any{"published": false, "reason": "manifest_invalid",
		"errors": []map[string]any{{"path": "/capabilities/needs/0", "message": "unknown capability tickets.nope"}}}, &got)
	defer srv.Close()
	signedIn(t, srv.URL, deployScope)

	err := runDeploy(context.Background(), &bytes.Buffer{}, &bytes.Buffer{}, deployOptions{
		manifestPath: writeManifest(t), image: "localhost:4505/acme/order-helper:0.1.0", noBuild: true,
	})
	if err == nil || !strings.Contains(err.Error(), "tickets.nope") {
		t.Fatalf("want manifest error, got %v", err)
	}
}

func TestDeployWithoutTheScopeStopsBeforeBuilding(t *testing.T) {
	signedIn(t, "https://api.konstera.ai", "devx.metadata.read")
	err := runDeploy(context.Background(), &bytes.Buffer{}, &bytes.Buffer{}, deployOptions{manifestPath: "nope.json"})
	if err == nil || !strings.Contains(err.Error(), deployScope) {
		t.Fatalf("want scope error, got %v", err)
	}
}
