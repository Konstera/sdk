// Package login runs the developer-tenant pairing device-flow against
// a Konstera Platform API and persists the resulting access/refresh
// tokens + fan-outs MCP configs into every known coding-agent config
// path on the local machine (ADR-055 M1.2 / M1.5).
//
// Everything here is a thin orchestrator around the Platform API —
// no cryptography, no persistence other than the credential file and
// MCP config writes. The Platform owns the handshake; the CLI's job is
// to show the user a nice flow and plumb the resulting token into the
// right places on their machine.
package login

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client talks to a Konstera Platform API. One instance per `konstera
// login` invocation; no shared state.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

// NewClient returns a Client pointed at baseURL (e.g. "http://localhost:4500"
// or "https://api.konstera.ai"). The HTTP client has sane timeouts; callers
// may override Client.HTTP for tests.
func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTP:    &http.Client{Timeout: 30 * time.Second},
	}
}

// InitiateRequest is the body of POST /api/dev-pair/device-code.
type InitiateRequest struct {
	ClientName         string   `json:"clientName"`
	ClientVersion      string   `json:"clientVersion,omitempty"`
	MachineFingerprint string   `json:"machineFingerprint"`
	RequestedScopes    []string `json:"requestedScopes"`
	SuggestedTenantSlug string  `json:"suggestedTenantSlug,omitempty"`
}

// InitiateResponse is the device-flow authorization response (RFC 8628 §3.2).
type InitiateResponse struct {
	DeviceCode              string    `json:"deviceCode"`
	UserCode                string    `json:"userCode"`
	ExpiresAt               time.Time `json:"expiresAt"`
	VerificationURI         string    `json:"verificationUri"`
	VerificationURIComplete string    `json:"verificationUriComplete"`
	PollIntervalSeconds     int       `json:"pollIntervalSeconds"`
}

// PollResponse is a successful poll — the pairing is approved and a
// JWT has been minted.
type PollResponse struct {
	PairingID         string    `json:"pairingId"`
	TenantID          string    `json:"tenantId"`
	TenantSlug        string    `json:"tenantSlug"`
	TenantDisplayName string    `json:"tenantDisplayName"`
	AccessToken       string    `json:"accessToken"`
	RefreshToken      string    `json:"refreshToken"`
	ExpiresAt         time.Time `json:"expiresAt"`
	GrantedScopes     []string  `json:"grantedScopes"`
}

// Terminal poll outcomes other than Approved.
var (
	// ErrPollPending — the user has not approved yet. Retry after
	// PollIntervalSeconds (adjusted by any slow_down the server sends).
	ErrPollPending = errors.New("authorization_pending")
	// ErrPollExpired — the device_code expired or was never valid.
	ErrPollExpired = errors.New("expired")
	// ErrPollAlreadyConsumed — the pairing was already claimed by another poller.
	ErrPollAlreadyConsumed = errors.New("already_consumed")
)

// Initiate opens the device-flow handshake. Returns the user_code the
// developer types in the portal, the verification URI the CLI should
// open in a browser, and a device_code the CLI holds secret.
func (c *Client) Initiate(ctx context.Context, req InitiateRequest) (*InitiateResponse, error) {
	body, _ := json.Marshal(req)
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/dev-pair/device-code", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("initiate device-flow: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("initiate device-flow: HTTP %d: %s", resp.StatusCode, bodyPreview(resp.Body))
	}
	var out InitiateResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("decode initiate response: %w", err)
	}
	return &out, nil
}

// Poll makes one poll attempt. Returns a PollResponse when the pairing
// is approved; one of the ErrPoll* sentinels otherwise.
func (c *Client) Poll(ctx context.Context, deviceCode string) (*PollResponse, error) {
	body, _ := json.Marshal(map[string]string{"deviceCode": deviceCode})
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/api/dev-pair/poll", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("poll: %w", err)
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		var out PollResponse
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			return nil, fmt.Errorf("decode poll response: %w", err)
		}
		return &out, nil
	case http.StatusAccepted:
		return nil, ErrPollPending
	case http.StatusGone:
		return nil, ErrPollExpired
	case http.StatusConflict:
		return nil, ErrPollAlreadyConsumed
	default:
		return nil, fmt.Errorf("poll: HTTP %d: %s", resp.StatusCode, bodyPreview(resp.Body))
	}
}

// PollUntilApproved blocks until the pairing is approved, the device_code
// expires, or ctx is cancelled. Writes "." to progress each poll so the
// developer sees the CLI is alive. Honours the server-suggested poll
// interval.
func (c *Client) PollUntilApproved(ctx context.Context, init *InitiateResponse, progress io.Writer) (*PollResponse, error) {
	interval := time.Duration(max(1, init.PollIntervalSeconds)) * time.Second
	deadline := init.ExpiresAt
	for {
		if time.Now().After(deadline) {
			return nil, ErrPollExpired
		}
		result, err := c.Poll(ctx, init.DeviceCode)
		if err == nil {
			if progress != nil {
				fmt.Fprintln(progress)
			}
			return result, nil
		}
		switch {
		case errors.Is(err, ErrPollPending):
			if progress != nil {
				fmt.Fprint(progress, ".")
			}
		case errors.Is(err, ErrPollExpired), errors.Is(err, ErrPollAlreadyConsumed):
			if progress != nil {
				fmt.Fprintln(progress)
			}
			return nil, err
		default:
			// Transient network / server error — one retry then surface.
			if progress != nil {
				fmt.Fprint(progress, "?")
			}
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(interval):
		}
	}
}

func bodyPreview(r io.Reader) string {
	buf, _ := io.ReadAll(io.LimitReader(r, 512))
	return strings.TrimSpace(string(buf))
}
