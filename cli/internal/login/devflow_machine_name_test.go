package login

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// Initiate sends this computer's hostname as machineName unless the caller set one.
func TestInitiateSendsMachineName(t *testing.T) {
	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&got)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"deviceCode":"d","userCode":"ABCD-EFGH","expiresAt":"2030-01-01T00:00:00Z","verificationUri":"x","verificationUriComplete":"x","pollIntervalSeconds":5}`))
	}))
	defer srv.Close()
	c := &Client{BaseURL: srv.URL, HTTP: srv.Client()}

	if _, err := c.Initiate(context.Background(), InitiateRequest{ClientName: "c", MachineFingerprint: "f", RequestedScopes: []string{"s"}}); err != nil {
		t.Fatal(err)
	}
	if want := MachineName(); want != "" && got["machineName"] != want {
		t.Fatalf("machineName = %v, want %q", got["machineName"], want)
	}

	if _, err := c.Initiate(context.Background(), InitiateRequest{ClientName: "c", MachineFingerprint: "f", RequestedScopes: []string{"s"}, MachineName: "custom"}); err != nil {
		t.Fatal(err)
	}
	if got["machineName"] != "custom" {
		t.Fatalf("machineName = %v, want custom", got["machineName"])
	}
}
