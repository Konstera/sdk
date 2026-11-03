#!/usr/bin/env bash
# Packs the Konstera Claude Desktop extension (.mcpb) from GoReleaser's dist/.
#
#   cli/mcpb/pack.sh <version> <goreleaser-dist-dir> <out-dir>
#
# Run on Linux (CI: release-cli.yml) after `goreleaser release`, and after
# `npm ci` in cli/mcpb. Linux matters: mcpb pack only records Unix file modes
# when it runs on Unix, and the macOS binary must stay executable.
#
# One bundle per OS/arch, because a manifest's platform_overrides are keyed
# by OS only (win32, darwin), never by CPU:
#   konstera-windows-x64.mcpb    Windows x64
#   konstera-windows-arm64.mcpb  Windows on Arm
#   konstera-macos.mcpb          macOS, universal binary (Apple silicon + Intel)
# The names carry no version so releases/latest/download/<name> stays a
# stable link; the version is inside the manifest.
#
# Every bundle is checked after packing: it is unpacked again and its
# manifest version, binary and file mode are compared with what was meant.
set -euo pipefail

version="${1:?version, e.g. 0.4.1}"
dist="$(cd "${2:?goreleaser dist dir}" && pwd)"
out="${3:?out dir}"
here="$(cd "$(dirname "$0")" && pwd)"
mcpb="$here/node_modules/.bin/mcpb"

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+].*)?$ ]] || { echo "not a semver version: $version" >&2; exit 1; }
[[ -x "$mcpb" ]] || { echo "run 'npm ci' in $here first" >&2; exit 1; }
[[ -f "$dist/artifacts.json" ]] || { echo "no artifacts.json in $dist (run goreleaser first)" >&2; exit 1; }
mkdir -p "$out"
out="$(cd "$out" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# binary_path <goos> <goarch>: the build GoReleaser made for that target.
# goarch "all" is the macOS universal binary.
binary_path() {
  local p
  p="$(jq -r --arg os "$1" --arg arch "$2" \
    '[.[] | select((.type == "Binary" or .type == "Universal Binary") and .goos == $os and .goarch == $arch)][0].path // empty' \
    "$dist/artifacts.json")"
  [[ -n "$p" ]] || { echo "no $1/$2 binary in $dist/artifacts.json" >&2; exit 1; }
  # artifacts.json paths are relative to the GoReleaser workdir (dist's parent).
  [[ "$p" = /* ]] || p="$(dirname "$dist")/$p"
  echo "$p"
}

# pack <bundle-name> <goos> <goarch> <mcpb-platform> <binary-name> <expected `file` output>
pack() {
  local name="$1" goos="$2" goarch="$3" platform="$4" bin="$5" want_type="$6"
  local stage="$work/$name" src
  src="$(binary_path "$goos" "$goarch")"
  mkdir -p "$stage/server"
  install -m 0755 "$src" "$stage/server/$bin"
  cp "$here/icon.png" "$stage/icon.png"
  jq --arg v "$version" --arg p "$platform" --arg e "server/$bin" \
    '.version = $v | .compatibility.platforms = [$p] | .server.entry_point = $e' \
    "$here/manifest.json" > "$stage/manifest.json"

  "$mcpb" validate "$stage/manifest.json"
  "$mcpb" pack "$stage" "$out/$name.mcpb"

  # Check the packed file itself, not the staging folder.
  local check="$work/check-$name"
  "$mcpb" unpack "$out/$name.mcpb" "$check" >/dev/null
  local got_version got_platforms
  got_version="$(jq -r .version "$check/manifest.json")"
  got_platforms="$(jq -c .compatibility.platforms "$check/manifest.json")"
  [[ "$got_version" == "$version" ]] || { echo "$name: manifest version $got_version, want $version" >&2; exit 1; }
  [[ "$got_platforms" == "[\"$platform\"]" ]] || { echo "$name: platforms $got_platforms" >&2; exit 1; }
  [[ -x "$check/server/$bin" ]] || { echo "$name: server/$bin missing or not executable after unpack" >&2; exit 1; }
  file -b "$check/server/$bin" | grep -q "$want_type" || { echo "$name: server/$bin is $(file -b "$check/server/$bin"), want $want_type" >&2; exit 1; }
  cmp -s "$src" "$check/server/$bin" || { echo "$name: packed binary differs from $src" >&2; exit 1; }
  "$mcpb" info "$out/$name.mcpb"
  echo "ok  $name.mcpb  v$got_version  $(file -b "$check/server/$bin" | cut -c1-60)"
}

pack konstera-windows-x64   windows amd64 win32  konstera.exe "PE32+ executable.*x86-64"
pack konstera-windows-arm64 windows arm64 win32  konstera.exe "PE32+ executable.*Aarch64"
pack konstera-macos         darwin  all   darwin konstera     "Mach-O universal binary"

(cd "$out" && sha256sum konstera-*.mcpb > mcpb-checksums.txt && cat mcpb-checksums.txt)
