#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
prefix="${OPENCODE_PREFIX:-$root/.tools/opencode-2.2.7}"
mkdir -p "$prefix"
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
cli="$prefix/bin/opencode"
check_version() {
  env -i HOME="$scratch" PATH=/usr/bin:/bin "$cli" --version
}

if [[ ! -x "$cli" ]] || [[ "$(check_version)" != "opencode v2.2.7" ]]; then
  # Use only public package metadata and scoped, empty npm config/cache.
  touch "$scratch/user.npmrc" "$scratch/global.npmrc"
  env -i HOME="$scratch" PATH="$(dirname -- "$(command -v node)"):/usr/bin:/bin" \
    HTTPS_PROXY="${HTTPS_PROXY:-}" HTTP_PROXY="${HTTP_PROXY:-}" NO_PROXY="${NO_PROXY:-}" \
    https_proxy="${https_proxy:-}" http_proxy="${http_proxy:-}" no_proxy="${no_proxy:-}" \
    NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-}" \
    "$(command -v npm)" --userconfig="$scratch/user.npmrc" --globalconfig="$scratch/global.npmrc" \
    --cache="$scratch/npm" --registry=https://registry.npmjs.org \
    install --global --prefix="$prefix" --no-audit --no-fund \
    --allow-scripts=@opencode/cli @opencode/cli@2.2.7
fi

version="$(check_version)"
[[ "$version" == "opencode v2.2.7" ]] || { printf 'Unexpected OpenCode version: %s\n' "$version" >&2; exit 1; }
printf '%s at %s\n' "$version" "$cli"
