package scaffold

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"unicode"
)

// TemplateData is the context passed to every template file.
type TemplateData struct {
	AgentName   string // the --name arg, kebab-case ("my-first-agent")
	AgentId     string // reverse-DNS id ("io.konstera.my-first-agent")
	DisplayName string // human title ("My First Agent")
	ClassName   string // PascalCase ("MyFirstAgent") — used in Python/TS/.NET source
	Namespace   string // .NET namespace ("MyFirstAgent")
	Version     string // SemVer ("0.1.0")
	Description string
	Icon        string // emoji or URL
	Author      string
}

// Options control a scaffold run.
type Options struct {
	Name     string // required — kebab-case agent name
	Language string // required — "python" | "typescript" | "dotnet"
	Template string // required — currently only "hello-world"
	Dir      string // output directory; defaults to Name
	Force    bool   // allow writing into a non-empty directory
}

// Supported languages for v0.1.
var supportedLanguages = map[string]bool{
	"python":     true,
	"typescript": true,
	"dotnet":     true,
}

// Create renders Options.Template for Options.Language into Options.Dir.
func Create(opts Options) error {
	if opts.Name == "" {
		return errors.New("agent name is required")
	}
	if !isKebabCase(opts.Name) {
		return fmt.Errorf("agent name %q must be kebab-case (lowercase a-z 0-9 and hyphens)", opts.Name)
	}
	if !supportedLanguages[opts.Language] {
		return fmt.Errorf("unsupported language %q (supported: python, typescript, dotnet)", opts.Language)
	}
	if opts.Template != "hello-world" {
		return fmt.Errorf("unsupported template %q (v0.1 only ships 'hello-world')", opts.Template)
	}
	if opts.Dir == "" {
		opts.Dir = opts.Name
	}

	// Fail unless the target directory is absent or empty, or --force was set.
	if err := checkTargetDir(opts.Dir, opts.Force); err != nil {
		return err
	}

	data := TemplateData{
		AgentName:   opts.Name,
		AgentId:     "io.konstera." + opts.Name,
		DisplayName: toTitle(opts.Name),
		ClassName:   toPascalCase(opts.Name),
		Namespace:   toPascalCase(opts.Name),
		Version:     "0.1.0",
		Description: fmt.Sprintf("A %s Konstera agent scaffolded by `konstera init`.", opts.Language),
		Icon:        iconFor(opts.Language),
		Author:      "Scaffolded by Konstera CLI",
	}

	srcPrefix := filepath.ToSlash(filepath.Join("templates", opts.Language))
	return fs.WalkDir(templatesFS, srcPrefix, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == srcPrefix {
			return nil
		}
		relPath, err := filepath.Rel(srcPrefix, path)
		if err != nil {
			return err
		}
		destPath := filepath.Join(opts.Dir, strings.TrimSuffix(relPath, ".tmpl"))

		// Rename the .NET project file: "project.csproj.tmpl" → "<AgentName>.csproj".
		if filepath.Base(destPath) == "project.csproj" {
			destPath = filepath.Join(filepath.Dir(destPath), data.AgentName+".csproj")
		}

		if d.IsDir() {
			return os.MkdirAll(destPath, 0o755)
		}

		if err := os.MkdirAll(filepath.Dir(destPath), 0o755); err != nil {
			return err
		}
		return renderOrCopyFile(path, destPath, strings.HasSuffix(path, ".tmpl"), data)
	})
}

func renderOrCopyFile(src, dest string, isTemplate bool, data TemplateData) error {
	body, err := templatesFS.ReadFile(src)
	if err != nil {
		return err
	}
	if !isTemplate {
		return os.WriteFile(dest, body, 0o644)
	}
	tmpl, err := template.New(filepath.Base(src)).Parse(string(body))
	if err != nil {
		return fmt.Errorf("parse %s: %w", src, err)
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	return tmpl.Execute(f, data)
}

func checkTargetDir(dir string, force bool) error {
	entries, err := os.ReadDir(dir)
	if errors.Is(err, os.ErrNotExist) {
		return os.MkdirAll(dir, 0o755)
	}
	if err != nil {
		return fmt.Errorf("read target dir: %w", err)
	}
	if len(entries) > 0 && !force {
		return fmt.Errorf("target directory %s is not empty (use --force to override)", dir)
	}
	return nil
}

// isKebabCase accepts lowercase a-z, 0-9, and hyphens, must start with a letter.
func isKebabCase(s string) bool {
	if s == "" {
		return false
	}
	if !unicode.IsLower(rune(s[0])) {
		return false
	}
	for _, r := range s {
		if !(unicode.IsLower(r) || unicode.IsDigit(r) || r == '-') {
			return false
		}
	}
	return true
}

// toPascalCase: "my-first-agent" → "MyFirstAgent".
func toPascalCase(kebab string) string {
	var sb strings.Builder
	nextUpper := true
	for _, r := range kebab {
		if r == '-' {
			nextUpper = true
			continue
		}
		if nextUpper {
			sb.WriteRune(unicode.ToUpper(r))
			nextUpper = false
		} else {
			sb.WriteRune(r)
		}
	}
	return sb.String()
}

// toTitle: "my-first-agent" → "My First Agent".
func toTitle(kebab string) string {
	parts := strings.Split(kebab, "-")
	for i, p := range parts {
		if p == "" {
			continue
		}
		parts[i] = strings.ToUpper(p[:1]) + p[1:]
	}
	return strings.Join(parts, " ")
}

func iconFor(language string) string {
	switch language {
	case "python":
		return "🐍"
	case "typescript":
		return "📘"
	case "dotnet":
		return "🔷"
	}
	return "🤖"
}
