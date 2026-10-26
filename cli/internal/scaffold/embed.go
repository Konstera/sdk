// Package scaffold renders agent templates embedded at build time.
//
// Templates live under scaffold/templates/<language>/. Each file whose name
// ends with .tmpl is rendered through text/template with the TemplateData
// struct; other files are copied verbatim.
package scaffold

import "embed"

//go:embed all:templates
var templatesFS embed.FS
