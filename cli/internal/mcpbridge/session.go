package mcpbridge

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
)

// refreshLeeway renews the access token when it has less than this left,
// so a tool call never starts with a token about to expire.
const refreshLeeway = 10 * time.Minute

// errNotSignedIn — no pairing saved for this client yet, or it was ended.
var errNotSignedIn = errors.New("not signed in")

// Session owns the pairing for one MCP client (one file per client, so
// Claude Desktop and Cursor are separate pairings an admin can revoke on
// their own). Safe for concurrent use.
type Session struct {
	path   string
	client *login.Client

	mu    sync.Mutex
	creds *login.Credentials
}

// SessionPath is ~/.konstera/mcp-<client>.json.
func SessionPath(clientName string) (string, error) {
	home, err := login.KonsteraHome()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "mcp-"+clientName+".json"), nil
}

func NewSession(path string, client *login.Client) *Session {
	return &Session{path: path, client: client}
}

// Current returns the saved pairing, or nil when signed out.
func (s *Session) Current() *login.Credentials {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.loadLocked()
}

func (s *Session) loadLocked() *login.Credentials {
	if s.creds != nil {
		return s.creds
	}
	c, err := login.LoadCredentialsAt(s.path)
	if err != nil || c == nil || c.AccessToken == "" || c.RefreshToken == "" {
		return nil
	}
	s.creds = c
	return c
}

// Save stores a newly approved pairing.
func (s *Session) Save(c *login.Credentials) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := login.SaveCredentialsAt(s.path, c); err != nil {
		return err
	}
	s.creds = c
	return nil
}

// Token returns an access token that is good for at least refreshLeeway,
// renewing it first when needed. force renews regardless (after a 401).
func (s *Session) Token(ctx context.Context, force bool) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	c := s.loadLocked()
	if c == nil {
		return "", errNotSignedIn
	}
	if !force && time.Until(c.ExpiresAt) > refreshLeeway {
		return c.AccessToken, nil
	}
	used := c.RefreshToken
	poll, err := s.client.Refresh(ctx, used)
	if errors.Is(err, login.ErrRefreshRejected) {
		// A refresh token works once. If another process sharing this file
		// renewed first, its saved copy is the good one.
		if fresh, rerr := login.LoadCredentialsAt(s.path); rerr == nil && fresh.RefreshToken != "" && fresh.RefreshToken != used {
			s.creds = fresh
			return fresh.AccessToken, nil
		}
		s.clearLocked()
		return "", errNotSignedIn
	}
	if err != nil {
		return "", err
	}
	next := *c
	next.AccessToken = poll.AccessToken
	next.RefreshToken = poll.RefreshToken
	next.ExpiresAt = poll.ExpiresAt
	next.GrantedScopes = poll.GrantedScopes
	next.TenantSlug = poll.TenantSlug
	next.TenantDisplayName = poll.TenantDisplayName
	if err := login.SaveCredentialsAt(s.path, &next); err != nil {
		return "", err
	}
	s.creds = &next
	return next.AccessToken, nil
}

// SignOut revokes the pairing on Konstera and empties the file. The file is
// emptied even when the revoke call fails, and the error is returned so the
// caller can say the pairing may still be listed in the portal.
func (s *Session) SignOut(ctx context.Context) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	c := s.loadLocked()
	if c == nil {
		return false, nil
	}
	err := s.client.Revoke(ctx, c.RefreshToken, "signed out from konstera mcp")
	if errors.Is(err, login.ErrRefreshRejected) {
		err = nil // already ended on Konstera
	}
	s.clearLocked()
	return true, err
}

func (s *Session) clearLocked() {
	s.creds = nil
	_ = os.Remove(s.path)
}
