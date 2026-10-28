package login

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"time"
)

// Credentials is the shape persisted at ~/.konstera/credentials.json.
// One file per machine; a re-pair overwrites the active credential.
// Multiple-pairings-per-machine is a follow-up (ADR-055 §Follow-ups);
// for M1 the CLI tracks one active pairing.
type Credentials struct {
	APIBaseURL        string    `json:"api_base_url"`
	TenantID          string    `json:"tenant_id"`
	TenantSlug        string    `json:"tenant_slug"`
	TenantDisplayName string    `json:"tenant_display_name"`
	PairingID         string    `json:"pairing_id"`
	AccessToken       string    `json:"access_token"`
	RefreshToken      string    `json:"refresh_token"`
	ExpiresAt         time.Time `json:"expires_at"`
	GrantedScopes     []string  `json:"granted_scopes"`
	ClientName        string    `json:"client_name"`
	MachineFingerprint string   `json:"machine_fingerprint"`
	PairedAt          time.Time `json:"paired_at"`
}

// CredentialsPath returns the path on disk where credentials live for
// this user. Honours KONSTERA_HOME when set (handy for scripted testing
// and multi-user CI). Otherwise:
//
//   - POSIX: ~/.konstera/credentials.json
//   - Windows: %USERPROFILE%\.konstera\credentials.json
func CredentialsPath() (string, error) {
	root, err := KonsteraHome()
	if err != nil {
		return "", err
	}
	return filepath.Join(root, "credentials.json"), nil
}

// KonsteraHome returns the per-user Konstera config directory. Creates it
// if it does not yet exist. The directory is 0700 on POSIX (no best-effort
// Windows ACL work for M1; the OS user's profile dir is already private).
func KonsteraHome() (string, error) {
	if override := os.Getenv("KONSTERA_HOME"); override != "" {
		if err := os.MkdirAll(override, 0o700); err != nil {
			return "", err
		}
		return override, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	root := filepath.Join(home, ".konstera")
	if err := os.MkdirAll(root, 0o700); err != nil {
		return "", err
	}
	return root, nil
}

// SaveCredentials writes the credential file atomically — temp file in
// the same directory, then rename over the target. 0600 on POSIX so other
// users on a shared machine cannot read the token. Windows: the parent
// directory lives under the user's profile, which is private by default.
func SaveCredentials(c *Credentials) error {
	path, err := CredentialsPath()
	if err != nil {
		return err
	}
	body, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".credentials.*.tmp")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	// Clean up tmp on any error path.
	success := false
	defer func() {
		if !success {
			_ = os.Remove(tmpPath)
		}
	}()
	if _, err := tmp.Write(body); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if runtime.GOOS != "windows" {
		if err := os.Chmod(tmpPath, 0o600); err != nil {
			return err
		}
	}
	if err := os.Rename(tmpPath, path); err != nil {
		return err
	}
	success = true
	return nil
}

// LoadCredentials returns the saved credentials, or an error wrapping
// os.ErrNotExist when no pairing has happened on this machine.
func LoadCredentials() (*Credentials, error) {
	path, err := CredentialsPath()
	if err != nil {
		return nil, err
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c Credentials
	if err := json.Unmarshal(body, &c); err != nil {
		return nil, fmt.Errorf("parse credentials: %w", err)
	}
	return &c, nil
}

// MachineFingerprint returns a short, stable, non-identifying hash of
// hostname + OS + a per-install UUID. Part of the logical pairing identity
// (same user + same tool + different machine = different pairing); kept
// in ~/.konstera/install.uuid so a laptop that gets re-paired after a wipe
// produces a new fingerprint.
func MachineFingerprint() (string, error) {
	root, err := KonsteraHome()
	if err != nil {
		return "", err
	}
	uuidPath := filepath.Join(root, "install.uuid")
	raw, err := os.ReadFile(uuidPath)
	if errors.Is(err, os.ErrNotExist) {
		buf := make([]byte, 16)
		if _, err := rand.Read(buf); err != nil {
			return "", err
		}
		raw = []byte(hex.EncodeToString(buf))
		if err := os.WriteFile(uuidPath, raw, 0o600); err != nil {
			return "", err
		}
	} else if err != nil {
		return "", err
	}
	host, _ := os.Hostname()
	// 12 hex chars = 48 bits — plenty of entropy for a logical-identity hash,
	// short enough to display in portal admin UIs without clutter.
	sum := sha256.Sum256([]byte(host + "|" + runtime.GOOS + "|" + string(raw)))
	return hex.EncodeToString(sum[:6]), nil
}
