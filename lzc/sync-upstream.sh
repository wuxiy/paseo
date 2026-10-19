#!/bin/sh
# Follow getpaseo/paseo: fetch upstream, merge it into the current branch, then
# report whether the lpk still points at the upstream release.
#
#   sh lzc/sync-upstream.sh          # fetch + merge, report only
#   sh lzc/sync-upstream.sh --bump   # also write package.yml's version
#
# --bump only rewrites `version:` in package.yml so the image tag in
# lzc/build.sh keeps matching the upstream release. Review the diff and the
# agent pins in lzc/agents.env before building; `--bump` does not touch them.
set -e
cd "$(dirname "$0")/.."

bump=no
[ "$1" = "--bump" ] && bump=yes

git fetch upstream --tags

current_branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$current_branch" = "HEAD" ]; then
  echo "lzc/sync-upstream.sh: detached HEAD, check out a branch first" >&2
  exit 1
fi

echo "==> merging upstream/main into $current_branch"
git merge --no-edit upstream/main

upstream_version=$(git show upstream/main:package.json | sed -n 's/.*"version": "\([^"]*\)".*/\1/p' | head -1)
lpk_version=$(sed -n 's/^version:[[:space:]]*//p' package.yml | head -1 | tr -d ' "'"'"'')
image_version=${lpk_version%%+*}
upstream_tag=$(git describe --tags --abbrev=0 upstream/main 2>/dev/null || echo '(no tag)')

echo
echo "upstream package.json version : ${upstream_version:-unknown}"
echo "latest upstream tag           : ${upstream_tag}"
echo "package.yml version           : ${lpk_version:-missing} (image tag ${image_version})"

if [ -z "$upstream_version" ]; then
  echo "cannot read the upstream version; leaving package.yml alone" >&2
  exit 1
fi

if [ "$upstream_version" = "$lpk_version" ]; then
  echo "already on the upstream release; nothing to bump"
  exit 0
fi

if [ "$bump" = "yes" ]; then
  tmp=$(mktemp)
  sed "s/^version:.*/version: ${upstream_version}/" package.yml >"$tmp"
  mv "$tmp" package.yml
  echo "package.yml version -> ${upstream_version}"
  echo
  echo "next: review lzc/agents.env (agent pins) and README-lzc.md, then rebuild"
else
  echo "package.yml is behind upstream; rerun with --bump to update it"
fi
