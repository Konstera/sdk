// Package manifest wraps gojsonschema for agent manifest validation.
//
// This package exists so the CLI can swap validator implementations later
// (e.g. switch to santhosh-tekuri/jsonschema for 2020-12 support) without
// changing callers.
package manifest

import (
	"fmt"
	"path/filepath"

	"github.com/xeipuuv/gojsonschema"
)

// Result is a thin wrapper over gojsonschema.Result exposing just what the
// CLI needs — swap-in-friendly if we switch libraries.
type Result struct {
	raw *gojsonschema.Result
}

// Valid reports whether the manifest conforms to the schema.
func (r *Result) Valid() bool { return r.raw.Valid() }

// Errors returns the list of schema violations.
func (r *Result) Errors() []gojsonschema.ResultError { return r.raw.Errors() }

// Validate loads the schema and the manifest from disk and reports a Result.
// Both paths must be absolute or resolvable from the caller's working dir.
func Validate(schemaPath, manifestPath string) (*Result, error) {
	absSchema, err := filepath.Abs(schemaPath)
	if err != nil {
		return nil, fmt.Errorf("schema path: %w", err)
	}
	absManifest, err := filepath.Abs(manifestPath)
	if err != nil {
		return nil, fmt.Errorf("manifest path: %w", err)
	}

	schemaLoader := gojsonschema.NewReferenceLoader("file://" + filepath.ToSlash(absSchema))
	manifestLoader := gojsonschema.NewReferenceLoader("file://" + filepath.ToSlash(absManifest))

	result, err := gojsonschema.Validate(schemaLoader, manifestLoader)
	if err != nil {
		return nil, err
	}
	return &Result{raw: result}, nil
}
