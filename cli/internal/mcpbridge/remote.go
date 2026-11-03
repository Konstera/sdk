package mcpbridge

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// remoteProtocolVersion is the MCP version spoken to /mcp/devx (the same
// one the Claude Code plugin uses).
const remoteProtocolVersion = "2025-06-18"

// rpcError is a JSON-RPC error object.
type rpcError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

func (e *rpcError) Error() string { return e.Message }

// Remote is the MCP client side of the bridge: Streamable HTTP to
// <api>/mcp/devx with the paired bearer token. A refused token is renewed
// and a lost MCP session reopened, once each, without the caller seeing it.
type Remote struct {
	endpoint   string
	http       *http.Client
	session    *Session
	clientName string
	version    string

	mu        sync.Mutex
	sessionID string
	nextID    atomic.Int64
}

func NewRemote(apiBase string, session *Session, clientName, version string) *Remote {
	return &Remote{
		endpoint:   strings.TrimRight(apiBase, "/") + "/mcp/devx",
		http:       &http.Client{Timeout: 120 * time.Second},
		session:    session,
		clientName: clientName,
		version:    version,
	}
}

// Reset drops the MCP session, e.g. after a new sign-in.
func (r *Remote) Reset() {
	r.mu.Lock()
	r.sessionID = ""
	r.mu.Unlock()
}

// Call sends one request and returns its result, or the server's
// JSON-RPC error as *rpcError.
func (r *Remote) Call(ctx context.Context, method string, params any) (json.RawMessage, error) {
	token, err := r.session.Token(ctx, false)
	if err != nil {
		return nil, err
	}
	for attempt := 0; ; attempt++ {
		sid, err := r.ensureSession(ctx, token)
		if err == nil {
			var status int
			var reply *rpcReply
			status, reply, err = r.post(ctx, token, sid, method, params, true)
			if err == nil && status == http.StatusOK {
				if reply == nil {
					return nil, errors.New("Konstera sent no reply")
				}
				if reply.Error != nil {
					return nil, reply.Error
				}
				return reply.Result, nil
			}
			if err == nil {
				err = &httpStatusError{status}
			}
		}
		if attempt > 0 {
			return nil, err
		}
		r.Reset()
		var hs *httpStatusError
		if errors.As(err, &hs) && hs.status == http.StatusUnauthorized {
			if token, err = r.session.Token(ctx, true); err != nil {
				return nil, err
			}
		}
	}
}

type httpStatusError struct{ status int }

func (e *httpStatusError) Error() string { return fmt.Sprintf("Konstera answered HTTP %d", e.status) }

func (r *Remote) ensureSession(ctx context.Context, token string) (string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.sessionID != "" {
		return r.sessionID, nil
	}
	status, _, sid, err := r.postRaw(ctx, token, "", "initialize", map[string]any{
		"protocolVersion": remoteProtocolVersion,
		"capabilities":    map[string]any{},
		"clientInfo":      map[string]any{"name": "konstera-mcp-" + r.clientName, "version": r.version},
	}, true)
	if err != nil {
		return "", err
	}
	if status != http.StatusOK {
		return "", &httpStatusError{status}
	}
	if _, _, _, err := r.postRaw(ctx, token, sid, "notifications/initialized", nil, false); err != nil {
		return "", err
	}
	// Servers without sessions send no id; "-" marks the session as open.
	if sid == "" {
		sid = "-"
	}
	r.sessionID = sid
	return sid, nil
}

type rpcReply struct {
	ID     json.RawMessage `json:"id"`
	Result json.RawMessage `json:"result"`
	Error  *rpcError       `json:"error"`
}

func (r *Remote) post(ctx context.Context, token, sid, method string, params any, isRequest bool) (int, *rpcReply, error) {
	status, reply, _, err := r.postRaw(ctx, token, sid, method, params, isRequest)
	return status, reply, err
}

func (r *Remote) postRaw(ctx context.Context, token, sid, method string, params any, isRequest bool) (int, *rpcReply, string, error) {
	msg := map[string]any{"jsonrpc": "2.0", "method": method}
	if params != nil {
		msg["params"] = params
	}
	var id int64
	if isRequest {
		id = r.nextID.Add(1)
		msg["id"] = id
	}
	body, _ := json.Marshal(msg)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, r.endpoint, bytes.NewReader(body))
	if err != nil {
		return 0, nil, "", err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("MCP-Protocol-Version", remoteProtocolVersion)
	if sid != "" && sid != "-" {
		req.Header.Set("Mcp-Session-Id", sid)
	}
	resp, err := r.http.Do(req)
	if err != nil {
		return 0, nil, "", fmt.Errorf("could not reach Konstera: %w", err)
	}
	defer resp.Body.Close()
	newSID := resp.Header.Get("Mcp-Session-Id")
	if !isRequest || resp.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 64<<10))
		return resp.StatusCode, nil, newSID, nil
	}
	reply, err := readReply(resp, id)
	return resp.StatusCode, reply, newSID, err
}

// readReply reads the reply to request id from a JSON or SSE response.
func readReply(resp *http.Response, id int64) (*rpcReply, error) {
	want := fmt.Sprint(id)
	if !strings.HasPrefix(resp.Header.Get("Content-Type"), "text/event-stream") {
		var reply rpcReply
		if err := json.NewDecoder(io.LimitReader(resp.Body, 16<<20)).Decode(&reply); err != nil {
			return nil, fmt.Errorf("unreadable reply from Konstera: %w", err)
		}
		return &reply, nil
	}
	sc := bufio.NewScanner(resp.Body)
	sc.Buffer(make([]byte, 64<<10), 16<<20)
	var data strings.Builder
	flush := func() *rpcReply {
		defer data.Reset()
		if data.Len() == 0 {
			return nil
		}
		var reply rpcReply
		if json.Unmarshal([]byte(data.String()), &reply) != nil {
			return nil
		}
		if string(reply.ID) == want {
			return &reply
		}
		return nil // a notification or another message: not ours
	}
	for sc.Scan() {
		line := sc.Text()
		switch {
		case line == "":
			if reply := flush(); reply != nil {
				return reply, nil
			}
		case strings.HasPrefix(line, "data:"):
			if data.Len() > 0 {
				data.WriteByte('\n')
			}
			data.WriteString(strings.TrimPrefix(strings.TrimPrefix(line, "data:"), " "))
		}
	}
	if reply := flush(); reply != nil {
		return reply, nil
	}
	if err := sc.Err(); err != nil {
		return nil, fmt.Errorf("reading reply from Konstera: %w", err)
	}
	return nil, errors.New("Konstera closed the stream without a reply")
}
