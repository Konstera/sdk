// Package mcpbridge is `konstera mcp`: a local MCP server (stdio) that MCP
// clients without a Konstera plugin start themselves — Claude Desktop
// first, also Cursor and Windsurf. It signs in with the same device flow
// as `konstera login`, keeps its own pairing per client, renews tokens,
// and passes tool calls on to <api>/mcp/devx.
//
// Why a bridge: /mcp/devx takes a short-lived bearer token from the
// device flow, and these clients can only start a local command or call a
// URL with fixed headers. A fixed header goes stale within the hour. The
// bridge goes once /mcp/devx supports the MCP authorization spec (OAuth),
// which clients then speak natively.
package mcpbridge

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/Konstera/sdk/cli/internal/login"
)

// Local tool names. Prefixed so they never clash with a /mcp/devx tool.
const (
	toolSignIn  = "konstera_sign_in"
	toolStatus  = "konstera_status"
	toolSignOut = "konstera_sign_out"
)

const defaultScopes = "devx.metadata.read"

var supportedVersions = []string{"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"}

// Options configure one bridge process.
type Options struct {
	APIBase     string
	ClientName  string // recorded on the pairing; also names the session file
	Version     string
	Fingerprint string
	// OpenBrowser opens the approval page; nil means never (tests).
	OpenBrowser func(url string) error
}

// Server is one stdio MCP server.
type Server struct {
	opts    Options
	session *Session
	remote  *Remote
	pairing *login.Client
	logger  *log.Logger

	outMu sync.Mutex
	out   io.Writer

	signinMu sync.Mutex
	pending  *pendingSignin
}

type pendingSignin struct {
	userCode, uri string
	expires       time.Time
}

func NewServer(opts Options, session *Session, logOut io.Writer) *Server {
	pairing := login.NewClient(opts.APIBase)
	return &Server{
		opts:    opts,
		session: session,
		remote:  NewRemote(opts.APIBase, session, opts.ClientName, opts.Version),
		pairing: pairing,
		logger:  log.New(logOut, "konstera mcp: ", log.LstdFlags),
	}
}

type message struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
}

// Serve reads newline-delimited JSON-RPC from in until EOF. Requests run
// concurrently; replies are written whole, one per line.
func (s *Server) Serve(ctx context.Context, in io.Reader, out io.Writer) error {
	s.out = out
	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 64<<10), 16<<20)
	var wg sync.WaitGroup
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		var m message
		if err := json.Unmarshal([]byte(line), &m); err != nil {
			s.reply(nil, nil, &rpcError{Code: -32700, Message: "parse error"})
			continue
		}
		if m.Method == "" || len(m.ID) == 0 {
			continue // a notification or a reply to us: nothing to answer
		}
		wg.Add(1)
		go func(m message) {
			defer wg.Done()
			result, err := s.handle(ctx, m)
			s.reply(m.ID, result, err)
		}(m)
	}
	wg.Wait()
	return sc.Err()
}

func (s *Server) handle(ctx context.Context, m message) (any, error) {
	switch m.Method {
	case "initialize":
		var p struct {
			ProtocolVersion string `json:"protocolVersion"`
		}
		_ = json.Unmarshal(m.Params, &p)
		version := supportedVersions[1]
		for _, v := range supportedVersions {
			if v == p.ProtocolVersion {
				version = v
			}
		}
		return map[string]any{
			"protocolVersion": version,
			"capabilities":    map[string]any{"tools": map[string]any{"listChanged": true}},
			"serverInfo":      map[string]any{"name": "konstera", "version": s.opts.Version},
			"instructions": "Konstera tools show your Konstera tenant (connectors, models, glossary, capabilities) " +
				"while you build agents. If you are not signed in, call " + toolSignIn + " first.",
		}, nil
	case "ping":
		return map[string]any{}, nil
	case "tools/list":
		return s.listTools(ctx), nil
	case "tools/call":
		var p struct {
			Name      string          `json:"name"`
			Arguments json.RawMessage `json:"arguments"`
		}
		if err := json.Unmarshal(m.Params, &p); err != nil {
			return nil, &rpcError{Code: -32602, Message: "invalid params"}
		}
		return s.callTool(ctx, p.Name, p.Arguments), nil
	default:
		return nil, &rpcError{Code: -32601, Message: "method not found: " + m.Method}
	}
}

func (s *Server) listTools(ctx context.Context) map[string]any {
	tools := []any{}
	if s.session.Current() != nil {
		result, err := s.remote.Call(ctx, "tools/list", map[string]any{})
		if err == nil {
			var listed struct {
				Tools []json.RawMessage `json:"tools"`
			}
			if json.Unmarshal(result, &listed) == nil {
				for _, t := range listed.Tools {
					tools = append(tools, t)
				}
			}
		} else {
			s.logger.Printf("tools/list from Konstera failed: %v", err)
		}
	}
	tools = append(tools, localTools(s.session.Current() != nil)...)
	return map[string]any{"tools": tools}
}

func localTools(signedIn bool) []any {
	signIn := map[string]any{
		"name": toolSignIn,
		"description": "Sign in to Konstera. Opens the Konstera portal in the browser, where a tenant admin approves " +
			"this app; Konstera tools appear once approved. Call this when Konstera tools are missing.",
		"inputSchema": map[string]any{
			"type": "object",
			"properties": map[string]any{
				"scopes": map[string]any{"type": "string", "description": "Comma-separated scopes to ask for. Default: " + defaultScopes},
			},
		},
	}
	status := map[string]any{
		"name":        toolStatus,
		"description": "Show which Konstera tenant this app is signed in to, the granted scopes and when the token renews.",
		"inputSchema": map[string]any{"type": "object", "properties": map[string]any{}},
	}
	signOut := map[string]any{
		"name":        toolSignOut,
		"description": "Sign out of Konstera: ends this app's pairing on Konstera and removes its tokens from this machine.",
		"inputSchema": map[string]any{"type": "object", "properties": map[string]any{}},
	}
	if signedIn {
		return []any{status, signOut}
	}
	return []any{signIn, status}
}

func (s *Server) callTool(ctx context.Context, name string, args json.RawMessage) map[string]any {
	switch name {
	case toolSignIn:
		var a struct {
			Scopes string `json:"scopes"`
		}
		_ = json.Unmarshal(args, &a)
		return s.signIn(ctx, a.Scopes)
	case toolStatus:
		return s.status()
	case toolSignOut:
		return s.signOut(ctx)
	}
	if s.session.Current() == nil {
		return toolText("Not signed in to Konstera. Call "+toolSignIn+" first.", true)
	}
	var arguments any = map[string]any{}
	if len(args) > 0 && string(args) != "null" {
		arguments = args
	}
	result, err := s.remote.Call(ctx, "tools/call", map[string]any{"name": name, "arguments": arguments})
	if err != nil {
		return toolText(s.explain(err), true)
	}
	var out map[string]any
	if json.Unmarshal(result, &out) != nil {
		return toolText("Konstera sent a reply this app could not read.", true)
	}
	return out
}

// explain turns a bridge error into a sentence for the user.
func (s *Server) explain(err error) string {
	if errors.Is(err, errNotSignedIn) {
		s.notifyToolsChanged()
		return "Konstera ended this sign-in (it was revoked or expired). Call " + toolSignIn + " to sign in again."
	}
	var re *rpcError
	if errors.As(err, &re) {
		return re.Message
	}
	return err.Error()
}

func (s *Server) signIn(ctx context.Context, scopesCSV string) map[string]any {
	if c := s.session.Current(); c != nil {
		return toolText(fmt.Sprintf("Already signed in to %s (%s). Call %s first to switch tenant.", c.TenantDisplayName, c.TenantSlug, toolSignOut), false)
	}
	s.signinMu.Lock()
	defer s.signinMu.Unlock()
	if p := s.pending; p != nil && time.Now().Before(p.expires) {
		return toolText(approveText(p.uri, p.userCode), false)
	}

	scopes := splitScopes(scopesCSV)
	init, err := s.pairing.Initiate(ctx, login.InitiateRequest{
		ClientName:         s.opts.ClientName,
		ClientVersion:      s.opts.Version,
		MachineFingerprint: s.opts.Fingerprint,
		RequestedScopes:    scopes,
	})
	if err != nil {
		return toolText("Could not start sign-in: "+err.Error(), true)
	}
	s.pending = &pendingSignin{userCode: init.UserCode, uri: init.VerificationURI, expires: init.ExpiresAt}
	if s.opts.OpenBrowser != nil {
		if err := s.opts.OpenBrowser(init.VerificationURIComplete); err != nil {
			s.logger.Printf("could not open the browser: %v", err)
		}
	}
	// Approval can take minutes; finish in the background and tell the
	// client the tool list changed.
	go s.finishSignin(init)
	return toolText(approveText(init.VerificationURI, init.UserCode), false)
}

func approveText(uri, code string) string {
	return fmt.Sprintf("Approve this sign-in in your browser: open %s and enter the code %s.\n"+
		"A tenant admin approves the request. Konstera tools appear here once it is approved "+
		"(if they don't, start a new chat).", uri, code)
}

func (s *Server) finishSignin(init *login.InitiateResponse) {
	ctx, cancel := context.WithDeadline(context.Background(), init.ExpiresAt.Add(30*time.Second))
	defer cancel()
	poll, err := s.pairing.PollUntilApproved(ctx, init, nil)
	s.signinMu.Lock()
	s.pending = nil
	s.signinMu.Unlock()
	if err != nil {
		s.logger.Printf("sign-in did not complete: %v", err)
		return
	}
	creds := &login.Credentials{
		APIBaseURL:         s.opts.APIBase,
		TenantID:           poll.TenantID,
		TenantSlug:         poll.TenantSlug,
		TenantDisplayName:  poll.TenantDisplayName,
		PairingID:          poll.PairingID,
		AccessToken:        poll.AccessToken,
		RefreshToken:       poll.RefreshToken,
		ExpiresAt:          poll.ExpiresAt,
		GrantedScopes:      poll.GrantedScopes,
		ClientName:         s.opts.ClientName,
		MachineFingerprint: s.opts.Fingerprint,
		PairedAt:           time.Now(),
	}
	if err := s.session.Save(creds); err != nil {
		s.logger.Printf("approved, but could not save the sign-in: %v", err)
		return
	}
	s.remote.Reset()
	s.logger.Printf("signed in to %s (%s), scopes %s", poll.TenantDisplayName, poll.TenantSlug, strings.Join(poll.GrantedScopes, ","))
	s.notifyToolsChanged()
}

func (s *Server) status() map[string]any {
	c := s.session.Current()
	if c == nil {
		s.signinMu.Lock()
		p := s.pending
		s.signinMu.Unlock()
		if p != nil && time.Now().Before(p.expires) {
			return toolText("Sign-in is waiting for approval: "+approveText(p.uri, p.userCode), false)
		}
		return toolText("Not signed in to Konstera. Call "+toolSignIn+" to sign in.", false)
	}
	return toolText(fmt.Sprintf("Signed in to %s (%s)\nKonstera: %s\nScopes: %s\nAccess token valid until %s (renewed automatically)\nPairing: %s, %s",
		c.TenantDisplayName, c.TenantSlug, c.APIBaseURL, strings.Join(c.GrantedScopes, ", "),
		c.ExpiresAt.Local().Format(time.RFC1123), c.PairingID, c.ClientName), false)
}

func (s *Server) signOut(ctx context.Context) map[string]any {
	had, err := s.session.SignOut(ctx)
	s.remote.Reset()
	if !had {
		return toolText("Not signed in to Konstera.", false)
	}
	s.notifyToolsChanged()
	if err != nil {
		return toolText("Signed out on this machine, but Konstera could not be told ("+err.Error()+
			"). An admin can revoke the pairing under Settings › Developer pairings.", true)
	}
	return toolText("Signed out of Konstera. The pairing is ended and the tokens are removed from this machine.", false)
}

func (s *Server) notifyToolsChanged() {
	s.write(map[string]any{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
}

func (s *Server) reply(id json.RawMessage, result any, err error) {
	msg := map[string]any{"jsonrpc": "2.0", "id": id} // nil id encodes as null
	var re *rpcError
	switch {
	case err == nil:
		msg["result"] = result
	case errors.As(err, &re):
		msg["error"] = re
	default:
		msg["error"] = &rpcError{Code: -32603, Message: err.Error()}
	}
	s.write(msg)
}

func (s *Server) write(msg any) {
	body, err := json.Marshal(msg)
	if err != nil {
		s.logger.Printf("could not encode a message: %v", err)
		return
	}
	s.outMu.Lock()
	defer s.outMu.Unlock()
	if s.out == nil {
		return
	}
	_, _ = s.out.Write(append(body, '\n'))
}

func toolText(text string, isError bool) map[string]any {
	return map[string]any{
		"content": []any{map[string]any{"type": "text", "text": text}},
		"isError": isError,
	}
}

func splitScopes(csv string) []string {
	var out []string
	for _, p := range strings.Split(csv, ",") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	if len(out) == 0 {
		return []string{defaultScopes}
	}
	return out
}
