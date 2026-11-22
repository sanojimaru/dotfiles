#!/usr/bin/env bash
# 実行: bash tests/install.sh（本物のホームは変更しない）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-install.XXXXXX")"
TMP="$(cd "$TMP" && pwd)"
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo with spaces"
TEST_HOME="$TMP/home with spaces"
mkdir -p "$REPO" "$TEST_HOME"
cp "$ROOT/install.sh" "$REPO/"
for dir in home config bin vscode agents claude codex; do cp -R "$ROOT/$dir" "$REPO/"; done

check_link() {
  [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] || {
    echo "FAIL link: $1 -> $2" >&2; exit 1;
  }
}
install_test() { env HOME="$TEST_HOME" bash "$REPO/install.sh" >"$TMP/install.log" 2>&1; }
expect_conflict() {
  if install_test; then echo "FAIL 衝突しても成功した" >&2; exit 1; fi
  grep -q 'error.*共通スキル' "$TMP/install.log" || { cat "$TMP/install.log"; exit 1; }
}

# 共通スキルがまだ無い checkout もインストールできる。
rm -rf "$REPO/agents/skills"
install_test
echo "ok   共通スキルが無くても成功する"

mkdir -p "$REPO/agents/skills/delivery-test/references" "$REPO/agents/skills/not-a-skill"
# インストールの検査に本文は不要。実機での認識は Issue に証拠を残す。
touch "$REPO/agents/skills/delivery-test/SKILL.md"
printf 'resource\n' >"$REPO/agents/skills/delivery-test/references/example.txt"
mkdir -p "$TEST_HOME/.agents/skills/orchestration" "$TEST_HOME/.claude/skills"
touch "$TEST_HOME/.agents/skills/orchestration/SKILL.md"
ln -s ../../.agents/skills/orchestration "$TEST_HOME/.claude/skills/orchestration"
install_test
for base in .agents .claude; do
  check_link "$TEST_HOME/$base/skills/delivery-test" "$REPO/agents/skills/delivery-test"
  [ "$(cat "$TEST_HOME/$base/skills/delivery-test/references/example.txt")" = resource ]
  [ ! -e "$TEST_HOME/$base/skills/not-a-skill" ]
done
check_link "$TEST_HOME/.claude/skills/orchestration" ../../.agents/skills/orchestration
for skill in proposal-slide-design-markdown proposal-slide-image-deck; do
  check_link "$TEST_HOME/.codex/skills/$skill" "$REPO/codex/skills/$skill"
done
echo "ok   共通スキルと参照を配布し、Orca 管理リンクと Codex 専用スキルを保つ"

install_test
if grep -Eq '^(link|backup) ' "$TMP/install.log"; then
  echo "FAIL 再実行でリンクが変更された" >&2; exit 1
fi
echo "ok   再実行してもリンクの変更・退避は無い"

# 実体・他のリンク・壊れたリンクのどれも上書きしない。
for base in .claude .agents; do
  dst="$TEST_HOME/$base/skills/delivery-test"
  rm "$dst"
  printf 'keep\n' >"$dst"
  expect_conflict
  [ "$(cat "$dst")" = keep ]
  rm "$dst"
  ln -s "$TMP/missing-skill" "$dst"
  expect_conflict
  check_link "$dst" "$TMP/missing-skill"
  rm "$dst"
  mkdir "$dst"
  touch "$dst/keep"
  expect_conflict
  [ -f "$dst/keep" ]
  rm -r "$dst"
  ln -s "$REPO/agents/skills/delivery-test" "$dst"
done
echo "ok   同名の既存ファイル・リンク・ディレクトリは保護する"

# Codex の旧配置先・リポジトリ内の専用スキルとも名前を分ける。
ln -s "$TMP/missing-codex-skill" "$TEST_HOME/.codex/skills/delivery-test"
expect_conflict
check_link "$TEST_HOME/.codex/skills/delivery-test" "$TMP/missing-codex-skill"
rm "$TEST_HOME/.codex/skills/delivery-test"
mkdir -p "$REPO/agents/skills/proposal-slide-image-deck"
touch "$REPO/agents/skills/proposal-slide-image-deck/SKILL.md"
expect_conflict
check_link "$TEST_HOME/.codex/skills/proposal-slide-image-deck" "$REPO/codex/skills/proposal-slide-image-deck"
echo "ok   Codex 専用スキルと同名なら停止する"

# 後ろのスキルで衝突しても、前のスキルやほかの設定は途中まで配らない。
rm -r "$REPO/agents/skills/proposal-slide-image-deck"
mkdir -p "$REPO/agents/skills/aaa-first" "$REPO/agents/skills/zzz-conflict"
touch "$REPO/agents/skills/aaa-first/SKILL.md" "$REPO/agents/skills/zzz-conflict/SKILL.md"
TEST_HOME="$TMP/conflict home"
mkdir -p "$TEST_HOME/.claude/skills/zzz-conflict"
printf 'keep\n' >"$TEST_HOME/.zshrc"
expect_conflict
[ "$(cat "$TEST_HOME/.zshrc")" = keep ]
[ ! -e "$TEST_HOME/.dotfiles_backup" ]
[ ! -e "$TEST_HOME/.codex/AGENTS.md" ]
for base in .claude .agents; do
  [ ! -L "$TEST_HOME/$base/skills/aaa-first" ]
done
echo "ok   後ろのスキルの衝突でも、スキル・設定とも変更前に止まる"

# ~/.local/bin に本物の codex があれば、ラッパーで置き換えない。
TEST_HOME="$TMP/codex home"
mkdir -p "$TEST_HOME/.local/bin"
printf 'real\n' >"$TEST_HOME/.local/bin/codex"
install_test || { cat "$TMP/install.log"; exit 1; }
[ "$(cat "$TEST_HOME/.local/bin/codex")" = real ]
check_link "$TEST_HOME/.local/bin/codex-hook-trust" "$REPO/bin/codex-hook-trust"
echo "ok   ~/.local/bin の本物の codex は置き換えない"
