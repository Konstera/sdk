# Dev shortcuts for the Konstera CLI. Not required (plain `go` works) —
# just handy for the common loops.

BINARY := konstera
VERSION ?= dev
LDFLAGS := -s -w -X github.com/Konstera/sdk/cli/internal/version.Version=$(VERSION)

.PHONY: help build install test lint tidy run clean release-snapshot

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the binary into ./bin/
	go build -ldflags "$(LDFLAGS)" -o bin/$(BINARY) ./cmd/konstera

install: ## Install into $GOBIN (or $GOPATH/bin)
	go install -ldflags "$(LDFLAGS)" ./cmd/konstera

test: ## Run unit tests
	go test -race -cover ./...

lint: ## Run golangci-lint (install: brew install golangci-lint)
	golangci-lint run ./...

tidy: ## Tidy go.mod + go.sum
	go mod tidy

run: build ## Build + run (e.g. make run ARGS="version")
	./bin/$(BINARY) $(ARGS)

clean: ## Remove build artifacts
	rm -rf bin dist

release-snapshot: ## GoReleaser dry-run (local only, no publish)
	goreleaser release --snapshot --clean --skip=publish
