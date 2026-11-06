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
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
)

func TestSecretsFileNameMatchesThePlatformRule(t *testing.T) {
	// Same cases as the platform's ConnectionSecretFields.FileName tests.
	for alias, want := range map[string]string{
		"zendesk-support":  "zendesk-support.json",
		"Amazon  MA Login": "amazon--ma-login.json",
		"../x":             "---x.json",
	} {
		if got := secretsFileName(alias); got != want {
			t.Errorf("secretsFileName(%q) = %q, want %q", alias, got, want)
		}
	}
}

func TestReadSecretsFileErrorsNeverQuoteValues(t *testing.T) {
	dir := t.TempDir()
	write := func(name, body string) string {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		return p
	}

	_, _, err := readSecretsFile(write("bad.json", `{"api_key": "s3cr3t-value",`))
	if err == nil || strings.Contains(err.Error(), "s3cr3t") {
		t.Fatalf("broken JSON: got %v", err)
	}
	_, _, err = readSecretsFile(write("num.json", `{"api_key": 12345678}`))
	if err == nil || !strings.Contains(err.Error(), "api_key") || strings.Contains(err.Error(), "12345678") {
		t.Fatalf("non-string: got %v", err)
	}
	_, _, err = readSecretsFile(write("empty.json", `{"api_key": "  "}`))
	if err == nil {
		t.Fatal("empty values should be refused")
	}
	got, _, err := readSecretsFile(write("ok.json", "\xef\xbb\xbf"+`{"api_key": "k", "optional": "", "n": null}`))
	if err != nil || len(got) != 1 || got["api_key"] != "k" {
		t.Fatalf("BOM + blanks: got %v, %v", got, err)
	}
	if _, _, err := readSecretsFile(filepath.Join(dir, "missing.json")); err == nil || !strings.Contains(err.Error(), "no secrets file") {
		t.Fatalf("missing: got %v", err)
	}
}

func TestSecretsAreNeverSentOverPlainHTTP(t *testing.T) {
	for base, ok := range map[string]bool{
		"https://api.konstera.ai":  true,
		"http://localhost:4500":    true,
		"http://127.0.0.1:4500":    true,
		"http://api.konstera.ai":   false,
		"http://192.168.1.10:4500": false,
	} {
		if err := checkSecureBase(base); (err == nil) != ok {
			t.Errorf("checkSecureBase(%q) = %v", base, err)
		}
	}
}

// signedIn writes a pairing under a temp KONSTERA_HOME that needs no refresh.
func signedIn(t *testing.T, api string, scopes ...string) string {
	t.Helper()
	home := t.TempDir()
	t.Setenv("KONSTERA_HOME", home)
	err := login.SaveCredentials(&login.Credentials{
		APIBaseURL: api, TenantID: "t", PairingID: "p",
		AccessToken: "access-1", RefreshToken: "refresh-1",
		ExpiresAt: time.Now().Add(time.Hour), GrantedScopes: scopes,
	})
	if err != nil {
		t.Fatal(err)
	}
	return home
}

func fakeKonstera(t *testing.T, testOK bool, got *map[string]any) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut || r.URL.Path != "/mcp/devx/connections/zendesk-support/secrets" {
			http.NotFound(w, r)
			return
		}
		if r.Header.Get("Authorization") != "Bearer access-1" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		_ = json.NewDecoder(r.Body).Decode(got)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"saved": []string{"api_token"}, "missingRequired": []string{},
			"test": map[string]any{"ok": testOK, "message": "401 from Zendesk"},
		})
	}))
}

func TestUploadSendsTheFileThenDeletesIt(t *testing.T) {
	var got map[string]any
	srv := fakeKonstera(t, true, &got)
	defer srv.Close()
	home := signedIn(t, srv.URL, "devx.metadata.read", secretsScope)
	path := filepath.Join(home, "secrets", "zendesk-support.json")
	_ = os.MkdirAll(filepath.Dir(path), 0o700)
	_ = os.WriteFile(path, []byte(`{"api_token":"s3cr3t-value"}`), 0o600)

	var out bytes.Buffer
	if err := runConnectionSecret(context.Background(), &out, "zendesk-support", "", false); err != nil {
		t.Fatalf("upload: %v\n%s", err, out.String())
	}
	if s, _ := got["secrets"].(map[string]any); s["api_token"] != "s3cr3t-value" {
		t.Fatalf("server got %v", got)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("file should be deleted after a passing test")
	}
	if strings.Contains(out.String(), "s3cr3t") {
		t.Fatalf("output shows the value:\n%s", out.String())
	}
}

func TestAFailingTestKeepsTheFile(t *testing.T) {
	var got map[string]any
	srv := fakeKonstera(t, false, &got)
	defer srv.Close()
	home := signedIn(t, srv.URL, secretsScope)
	path := filepath.Join(home, "z.json")
	_ = os.WriteFile(path, []byte(`{"api_token":"wrong"}`), 0o600)

	var out bytes.Buffer
	err := runConnectionSecret(context.Background(), &out, "zendesk-support", path, false)
	if err == nil || !strings.Contains(err.Error(), "test failed") {
		t.Fatalf("want test-failed error, got %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal("file should stay so the value can be fixed")
	}
}

func TestWithoutTheScopeNothingIsRead(t *testing.T) {
	signedIn(t, "https://api.konstera.ai", "devx.metadata.read")
	err := runConnectionSecret(context.Background(), &bytes.Buffer{}, "zendesk-support", "/does/not/matter.json", false)
	if err == nil || !strings.Contains(err.Error(), secretsScope) {
		t.Fatalf("want scope error, got %v", err)
	}
}
