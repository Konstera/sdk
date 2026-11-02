package plugins

import "testing"

func TestBatchCmdLineQuotesScriptAndArgs(t *testing.T) {
	got := batchCmdLine(`C:\Windows\System32\cmd.exe`,
		`C:\Users\First Last\AppData\Roaming\npm\claude.cmd`,
		[]string{"plugin", "marketplace", "add", `C:\Users\First Last\.konstera\plugins`})
	want := `"C:\Windows\System32\cmd.exe" /d /s /c ""C:\Users\First Last\AppData\Roaming\npm\claude.cmd" "plugin" "marketplace" "add" "C:\Users\First Last\.konstera\plugins""`
	if got != want {
		t.Fatalf("batchCmdLine:\n got %s\nwant %s", got, want)
	}
}
