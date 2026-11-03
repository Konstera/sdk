package manifest

import (
	"strings"
	"testing"
)

func TestCopy_CleanManifest(t *testing.T) {
	r, err := CopyFromJSON([]byte(`{
		"id": "demo", "version": "0.1.0",
		"description": "Drafts replies to support tickets. Version 2 of our process; see the airplane FAQ.",
		"llmRequirements": [{"purpose": "drafter", "description": "Writes the reply. Without its own model, it uses the drafter's."}],
		"capabilities": {"needs": [{"name": "tickets.reply", "reason": "Posts the approved reply"}]}
	}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(r.Issues) != 0 || r.Err() != nil {
		t.Fatalf("expected clean, got %+v", r.Issues)
	}
}

func TestCopy_FlagsEachLeakedPattern(t *testing.T) {
	r, err := CopyFromJSON([]byte(`{
		"description": "Drafts replies. v0.6.0 (glossary): reads the glossary.",
		"llmRequirements": [{"purpose": "classifier", "description": "Triage (ADR-030): labels each ticket."}],
		"capabilities": {"needs": [{"name": "customers.lookup_by_email", "reason": "Primary identity path (Sub-slice B.3), from migration 115"}]}
	}`))
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]string{}
	for _, is := range r.Issues {
		got[is.Rule] = is.Pointer
	}
	want := map[string]string{
		"release_history":  "$.description",
		"design_record":    "$.llmRequirements[0].description",
		"work_item":        "$.capabilities.needs[0].reason",
		"migration_number": "$.capabilities.needs[0].reason",
	}
	for rule, ptr := range want {
		if got[rule] != ptr {
			t.Errorf("rule %s: pointer %q, want %q (all: %+v)", rule, got[rule], ptr, r.Issues)
		}
	}
	err = r.Err()
	if err == nil || !strings.Contains(err.Error(), "--allow-internal-refs") || !strings.Contains(err.Error(), "ADR-030") {
		t.Fatalf("error should name the match and the override, got: %v", err)
	}
}

func TestCopy_KeysAreNotChecked(t *testing.T) {
	r, err := CopyFromJSON([]byte(`{"ADR-1": "fine", "x": {"Sub-slice": 1}}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(r.Issues) != 0 {
		t.Fatalf("keys must not be linted, got %+v", r.Issues)
	}
}
