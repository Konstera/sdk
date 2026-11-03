package mcpbridge

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
)

// fakeKonstera serves the pairing endpoints and /mcp/devx.
type fakeKonstera struct {
	mu            sync.Mutex
	approved      bool
	accessToken   string
	refreshToken  string
	revoked       bool
	refreshes     int
	initializes   int
	rejectNextMCP int    // answer 401 to this many /mcp/devx calls
	dropSession   bool   // answer 404 to the next call with a session id
	lastAuth      string // Authorization on the last tools/call
	sse           bool   // answer tools/call as an event stream
}

func (f *fakeKonstera) handler(t *testing.T) http.Handler {
	mux := http.NewServeMux()
	writeJSON := func(w http.ResponseWriter, v any) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(v)
	}
	tokens := func() map[string]any {
		return map[string]any{
			"pairingId": "11111111-1111-1111-1111-111111111111", "tenantId": "22222222-2222-2222-2222-222222222222",
			"tenantSlug": "acme", "tenantDisplayName": "Acme", "accessToken": f.accessToken,
			"refreshToken": f.refreshToken, "expiresAt": time.Now().Add(time.Hour).UTC().Format(time.RFC3339),
			"grantedScopes": []string{"devx.metadata.read"},
		}
	}
	mux.HandleFunc("/api/dev-pair/device-code", func(w http.ResponseWriter, r *http.Request) {
		var body login.InitiateRequest
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body.ClientName != "claude-desktop" {
			t.Errorf("clientName = %q", body.ClientName)
		}
		writeJSON(w, map[string]any{
			"deviceCode": "dev-code", "userCode": "ABCD-EFGH", "expiresAt": time.Now().Add(time.Minute).UTC().Format(time.RFC3339),
			"verificationUri": "https://portal/pair", "verificationUriComplete": "https://portal/pair?code=ABCD-EFGH",
			"pollIntervalSeconds": 1,
		})
	})
	mux.HandleFunc("/api/dev-pair/poll", func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		if !f.approved {
			w.WriteHeader(http.StatusAccepted)
			return
		}
		f.accessToken, f.refreshToken = "access-1", "refresh-1"
		writeJSON(w, tokens())
	})
	mux.HandleFunc("/api/dev-pair/refresh", func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		var body struct{ RefreshToken string }
		_ = json.NewDecoder(r.Body).Decode(&body)
		if f.revoked || body.RefreshToken != f.refreshToken {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		f.refreshes++
		f.accessToken = fmt.Sprintf("access-%d", f.refreshes+1)
		f.refreshToken = fmt.Sprintf("refresh-%d", f.refreshes+1)
		writeJSON(w, tokens())
	})
	mux.HandleFunc("/api/dev-pair/revoke", func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		f.revoked = true
		w.WriteHeader(http.StatusNoContent)
	})
	mux.HandleFunc("/mcp/devx", func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		if f.rejectNextMCP > 0 || r.Header.Get("Authorization") != "Bearer "+f.accessToken {
			if f.rejectNextMCP > 0 {
				f.rejectNextMCP--
			}
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		var msg struct {
			ID     json.RawMessage `json:"id"`
			Method string          `json:"method"`
			Params json.RawMessage `json:"params"`
		}
		_ = json.NewDecoder(r.Body).Decode(&msg)
		if msg.Method != "initialize" && r.Header.Get("Mcp-Session-Id") != "sess-1" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if f.dropSession && msg.Method != "initialize" && len(msg.ID) > 0 {
			f.dropSession = false
			w.WriteHeader(http.StatusNotFound)
			return
		}
		switch msg.Method {
		case "initialize":
			f.initializes++
			w.Header().Set("Mcp-Session-Id", "sess-1")
			writeJSON(w, map[string]any{"jsonrpc": "2.0", "id": msg.ID, "result": map[string]any{"protocolVersion": "2025-06-18"}})
		case "notifications/initialized":
			w.WriteHeader(http.StatusAccepted)
		case "tools/list":
			writeJSON(w, map[string]any{"jsonrpc": "2.0", "id": msg.ID, "result": map[string]any{"tools": []any{
				map[string]any{"name": "list_connectors", "description": "Connectors", "inputSchema": map[string]any{"type": "object"}},
			}}})
		case "tools/call":
			f.lastAuth = r.Header.Get("Authorization")
			reply, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": msg.ID, "result": map[string]any{
				"content": []any{map[string]any{"type": "text", "text": "echo " + string(msg.Params)}},
			}})
			if f.sse {
				w.Header().Set("Content-Type", "text/event-stream")
				fmt.Fprintf(w, "event: message\ndata: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}\n\n")
				fmt.Fprintf(w, "event: message\ndata: %s\n\n", reply)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write(reply)
		default:
			writeJSON(w, map[string]any{"jsonrpc": "2.0", "id": msg.ID, "error": map[string]any{"code": -32601, "message": "nope"}})
		}
	})
	return mux
}

// harness drives a Server over pipes like an MCP client would.
type harness struct {
	t       *testing.T
	in      *io.PipeWriter
	mu      sync.Mutex
	replies map[string]json.RawMessage
	notes   []string
	nextID  int
	opened  []string
	path    string
}

func newHarness(t *testing.T, fake *fakeKonstera) *harness {
	t.Helper()
	t.Setenv("KONSTERA_HOME", t.TempDir())
	srv := httptest.NewServer(fake.handler(t))
	t.Cleanup(srv.Close)

	path, err := SessionPath("claude-desktop")
	if err != nil {
		t.Fatal(err)
	}
	h := &harness{t: t, replies: map[string]json.RawMessage{}, path: path}
	session := NewSession(path, login.NewClient(srv.URL))
	server := NewServer(Options{
		APIBase: srv.URL, ClientName: "claude-desktop", Version: "test", Fingerprint: "fp",
		OpenBrowser: func(url string) error { h.mu.Lock(); h.opened = append(h.opened, url); h.mu.Unlock(); return nil },
	}, session, io.Discard)

	inR, inW := io.Pipe()
	outR, outW := io.Pipe()
	h.in = inW
	go func() { _ = server.Serve(context.Background(), inR, outW); _ = outW.Close() }()
	go func() {
		sc := bufio.NewScanner(outR)
		sc.Buffer(make([]byte, 1<<20), 1<<20)
		for sc.Scan() {
			var m struct {
				ID     json.RawMessage `json:"id"`
				Method string          `json:"method"`
			}
			line := append([]byte(nil), sc.Bytes()...)
			if err := json.Unmarshal(line, &m); err != nil {
				t.Errorf("bridge wrote a line that is not JSON: %q", line)
				continue
			}
			h.mu.Lock()
			if m.Method != "" {
				h.notes = append(h.notes, m.Method)
			} else {
				h.replies[string(m.ID)] = line
			}
			h.mu.Unlock()
		}
	}()
	t.Cleanup(func() { _ = inW.Close() })
	return h
}

func (h *harness) request(method string, params any) map[string]any {
	h.t.Helper()
	h.nextID++
	id := fmt.Sprint(h.nextID)
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": h.nextID, "method": method, "params": params})
	if _, err := h.in.Write(append(body, '\n')); err != nil {
		h.t.Fatal(err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		h.mu.Lock()
		raw, ok := h.replies[id]
		h.mu.Unlock()
		if ok {
			var out map[string]any
			_ = json.Unmarshal(raw, &out)
			return out
		}
		time.Sleep(5 * time.Millisecond)
	}
	h.t.Fatalf("no reply to %s", method)
	return nil
}

func (h *harness) toolNames() []string {
	h.t.Helper()
	res := h.request("tools/list", map[string]any{})["result"].(map[string]any)
	var names []string
	for _, tool := range res["tools"].([]any) {
		names = append(names, tool.(map[string]any)["name"].(string))
	}
	return names
}

func (h *harness) call(name string, args any) (string, bool) {
	h.t.Helper()
	res, ok := h.request("tools/call", map[string]any{"name": name, "arguments": args})["result"].(map[string]any)
	if !ok {
		h.t.Fatalf("tools/call %s: no result", name)
	}
	text := res["content"].([]any)[0].(map[string]any)["text"].(string)
	isErr, _ := res["isError"].(bool)
	return text, isErr
}

func (h *harness) waitFor(cond func() bool, what string) {
	h.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	h.t.Fatalf("timed out waiting for %s", what)
}

func (h *harness) noteCount() int {
	h.mu.Lock()
	defer h.mu.Unlock()
	n := 0
	for _, m := range h.notes {
		if m == "notifications/tools/list_changed" {
			n++
		}
	}
	return n
}

// signIn runs the device flow to approval.
func (h *harness) signIn(fake *fakeKonstera) {
	h.t.Helper()
	text, isErr := h.call(toolSignIn, map[string]any{})
	if isErr || !strings.Contains(text, "ABCD-EFGH") {
		h.t.Fatalf("sign-in text = %q (error %v)", text, isErr)
	}
	before := h.noteCount()
	fake.mu.Lock()
	fake.approved = true
	fake.mu.Unlock()
	h.waitFor(func() bool { return h.noteCount() > before }, "tools/list_changed after approval")
}

func equal(a, b []string) bool { return strings.Join(a, ",") == strings.Join(b, ",") }

func TestInitializeAndSignedOutTools(t *testing.T) {
	h := newHarness(t, &fakeKonstera{})
	res := h.request("initialize", map[string]any{"protocolVersion": "2025-03-26", "capabilities": map[string]any{}})["result"].(map[string]any)
	if res["protocolVersion"] != "2025-03-26" {
		t.Errorf("protocolVersion = %v, want the client's", res["protocolVersion"])
	}
	if got := h.toolNames(); !equal(got, []string{toolSignIn, toolStatus}) {
		t.Errorf("signed-out tools = %v", got)
	}
	if text, isErr := h.call("list_connectors", map[string]any{}); !isErr || !strings.Contains(text, toolSignIn) {
		t.Errorf("remote tool while signed out = %q, %v", text, isErr)
	}
	if e := h.request("resources/list", map[string]any{})["error"].(map[string]any); e["code"].(float64) != -32601 {
		t.Errorf("unknown method error = %v", e)
	}
}

func TestSignInThenToolsAreProxied(t *testing.T) {
	fake := &fakeKonstera{sse: true}
	h := newHarness(t, fake)
	h.signIn(fake)

	if len(h.opened) != 1 || !strings.Contains(h.opened[0], "ABCD-EFGH") {
		t.Errorf("browser opened %v", h.opened)
	}
	if got := h.toolNames(); !equal(got, []string{"list_connectors", toolStatus, toolSignOut}) {
		t.Errorf("signed-in tools = %v", got)
	}
	text, isErr := h.call("list_connectors", map[string]any{"category": "ticketing"})
	if isErr || !strings.Contains(text, `"category":"ticketing"`) {
		t.Errorf("proxied call = %q, %v", text, isErr)
	}
	if fake.lastAuth != "Bearer access-1" {
		t.Errorf("Authorization = %q", fake.lastAuth)
	}
	saved, err := login.LoadCredentialsAt(h.path)
	if err != nil || saved.RefreshToken != "refresh-1" || saved.TenantSlug != "acme" || saved.ClientName != "claude-desktop" {
		t.Errorf("saved session = %+v, %v", saved, err)
	}
	if text, _ := h.call(toolStatus, map[string]any{}); !strings.Contains(text, "Acme (acme)") {
		t.Errorf("status = %q", text)
	}
}

func TestRefusedTokenIsRenewedOnce(t *testing.T) {
	fake := &fakeKonstera{}
	h := newHarness(t, fake)
	h.signIn(fake)
	h.toolNames() // opens the MCP session

	fake.mu.Lock()
	fake.rejectNextMCP = 1
	fake.mu.Unlock()
	if text, isErr := h.call("list_connectors", map[string]any{}); isErr {
		t.Fatalf("call after 401 = %q", text)
	}
	if fake.refreshes != 1 || fake.lastAuth != "Bearer access-2" {
		t.Errorf("refreshes = %d, auth = %q", fake.refreshes, fake.lastAuth)
	}
	if saved, _ := login.LoadCredentialsAt(h.path); saved.RefreshToken != "refresh-2" {
		t.Errorf("rotated refresh token not saved: %q", saved.RefreshToken)
	}
}

func TestLostSessionIsReopened(t *testing.T) {
	fake := &fakeKonstera{}
	h := newHarness(t, fake)
	h.signIn(fake)
	h.toolNames()
	fake.mu.Lock()
	fake.dropSession = true
	fake.mu.Unlock()
	if text, isErr := h.call("list_connectors", map[string]any{}); isErr {
		t.Fatalf("call after 404 = %q", text)
	}
	if fake.initializes != 2 {
		t.Errorf("initializes = %d, want 2", fake.initializes)
	}
}

func TestRevokedPairingSignsOut(t *testing.T) {
	fake := &fakeKonstera{}
	h := newHarness(t, fake)
	h.signIn(fake)
	h.toolNames()

	fake.mu.Lock()
	fake.revoked = true
	fake.rejectNextMCP = 1
	fake.mu.Unlock()
	text, isErr := h.call("list_connectors", map[string]any{})
	if !isErr || !strings.Contains(text, "ended this sign-in") {
		t.Errorf("revoked call = %q, %v", text, isErr)
	}
	if _, err := os.Stat(h.path); !os.IsNotExist(err) {
		t.Errorf("session file still there: %v", err)
	}
	if got := h.toolNames(); !equal(got, []string{toolSignIn, toolStatus}) {
		t.Errorf("tools after revoke = %v", got)
	}
}

func TestSignOutRevokesAndForgets(t *testing.T) {
	fake := &fakeKonstera{}
	h := newHarness(t, fake)
	h.signIn(fake)

	text, isErr := h.call(toolSignOut, map[string]any{})
	if isErr || !strings.Contains(text, "Signed out") {
		t.Errorf("sign-out = %q, %v", text, isErr)
	}
	if !fake.revoked {
		t.Error("pairing was not revoked on Konstera")
	}
	if _, err := os.Stat(h.path); !os.IsNotExist(err) {
		t.Errorf("session file still there: %v", err)
	}
	if text, _ := h.call(toolSignOut, map[string]any{}); !strings.Contains(text, "Not signed in") {
		t.Errorf("second sign-out = %q", text)
	}
}

func TestSecondSignInWhilePendingReusesCode(t *testing.T) {
	h := newHarness(t, &fakeKonstera{})
	h.call(toolSignIn, map[string]any{})
	text, _ := h.call(toolSignIn, map[string]any{})
	if !strings.Contains(text, "ABCD-EFGH") || len(h.opened) != 1 {
		t.Errorf("second sign-in = %q, browser opened %d times", text, len(h.opened))
	}
	if text, _ := h.call(toolStatus, map[string]any{}); !strings.Contains(text, "waiting for approval") {
		t.Errorf("status while pending = %q", text)
	}
}
