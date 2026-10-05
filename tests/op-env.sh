#!/usr/bin/env bash
# bin/op-env のテスト。本物の op は呼ばず、PATH の先頭に置いたスタブで差し替える。
# 実行: tests/op-env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OP_ENV="$ROOT/bin/op-env"
WORK="$(mktemp -d)"
trap 'chmod -R u+rw "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

mkdir -p "$WORK/stub" "$WORK/proj"
cat > "$WORK/stub/op" <<'EOF'
#!/bin/sh
# 呼び方 (op read op://<vault>/<KEY>/credential) が違えば失敗する
# トークンはファイルの中身 (dummy) でなければ失敗する。ただし空は通す (本物の op はデスクトップアプリ連携に
# 切り替わって動きうるので、op-env 側で止める必要がある)
case "${OP_SERVICE_ACCOUNT_TOKEN-unset}" in
  dummy | "") ;;
  *) echo "unexpected token" >&2; exit 1 ;;
esac
[ "$1" = read ] && [ $# -eq 2 ] || { echo "unexpected args: $*" >&2; exit 1; }
case "$2" in
  op://Dev/FOO/credential) echo foo-new ;;
  op://Dev/BAR/credential) echo bar-val ;;
  op://Other/FOO/credential) echo foo-other ;;
  op://Dev/SPECIAL/credential) printf '%s' 'a b#c$HOME"q;$(echo x)`id`&= x"' ;;
  op://Dev/EMPTY/credential) printf '' ;;
  op://Dev/QUOTE/credential) echo "it's" ;;
  op://Dev/NL/credential) printf 'a\nb' ;;
  op://Dev/BSLASH/credential) printf '%s' 'e\' ;;
  *) echo "[ERROR] not found: $2" >&2; exit 1 ;;
esac
EOF
chmod +x "$WORK/stub/op"
echo dummy > "$WORK/token"
export PATH="$WORK/stub:$PATH" OP_ENV_TOKEN_FILE="$WORK/token"
cd "$WORK/proj"

pass=0 fail=0
ok() { echo "ok   $1"; pass=$((pass + 1)); }
ng() { echo "FAIL $1"; fail=$((fail + 1)); }
check() { if eval "$2"; then ok "$1"; else ng "$1"; fi; }
check_rc() { # check_rc <名前> <期待する終了コード> <コマンド...>
  local name="$1" want_rc="$2" rc=0; shift 2
  "$@" >/dev/null 2>&1 || rc=$?
  if [ "$rc" -eq "$want_rc" ]; then ok "$name"; else ng "$name (rc=$rc)"; fi
}

# .env がまだ無いディレクトリでは新しく作る
mkdir -p "$WORK/fresh"
check ".env が無ければ新しく作る" '(cd "$WORK/fresh" && "$OP_ENV" FOO >/dev/null 2>&1) && [ "$(cat "$WORK/fresh/.env")" = "FOO='"'"'foo-new'"'"'" ]'
check "新しく作った .env も 600" '[ "$(stat -f %Lp "$WORK/fresh/.env")" = 600 ]'

# 同名キーだけ置き換え、他の行 (接頭辞が同じキー・export 付き・コメント) は残す
printf '# comment\nKEEP=1\nexport FOO=old\nFOO_X=x\n' > .env
check "成功で終了する" '"$OP_ENV" FOO BAR >/dev/null'
check "既存行が残る" '[ "$(grep -c -E "^(# comment|KEEP=1|FOO_X=x)$" .env)" -eq 3 ]'
check "同名キーが置き換わる" '[ "$(grep -c FOO= .env)" -eq 1 ] && grep -qx "FOO='"'"'foo-new'"'"'" .env'
check "新しいキーが足される" 'grep -qx "BAR='"'"'bar-val'"'"'" .env'
check ".env が 600" '[ "$(stat -f %Lp .env)" = 600 ]'

# 特殊文字を含む値を zsh の source がそのまま読める
"$OP_ENV" SPECIAL >/dev/null
export want
want="$(OP_SERVICE_ACCOUNT_TOKEN=dummy op read op://Dev/SPECIAL/credential)"
check "特殊文字の値を zsh が文字どおり読む" '[ "$(zsh -fc "set -a; . ./.env; printf %s \"\$SPECIAL\"")" = "$want" ]'
if command -v mise >/dev/null; then
  printf '[env]\n_.file = ".env"\n' > mise.toml
  check "特殊文字の値を mise が文字どおり読む" '[ "$(MISE_TRUSTED_CONFIG_PATHS="$PWD" mise x -C "$PWD" -- sh -c "printf %s \"\$SPECIAL\"")" = "$want" ]'
  rm mise.toml
else
  echo "skip mise が無い"
fi
if command -v fish >/dev/null; then
  # config.fish の ~/.env 読み込み部分だけを取り出し、このディレクトリの .env に向けて動かす
  sed -n '/^if test -f \$HOME\/.env/,/^end/p' "$ROOT/config/fish/config.fish" | sed "s|\$HOME/.env|$PWD/.env|g" > "$WORK/loader.fish"
  check "特殊文字の値を config.fish が文字どおり読む" '[ "$(fish --no-config -c "source $WORK/loader.fish; printf %s \$SPECIAL")" = "$want" ]'
else
  echo "skip fish が無い"
fi

check "OP_ENV_VAULT で読む vault を変えられる" 'OP_ENV_VAULT=Other "$OP_ENV" FOO >/dev/null && grep -qx "FOO='"'"'foo-other'"'"'" .env'

# 失敗するときは .env を変えず、一時ファイルも残さない
cp .env "$WORK/before"
for key in NOPE EMPTY QUOTE NL BSLASH; do
  check_rc "$key は exit 1" 1 "$OP_ENV" FOO "$key"
  check "$key で .env が変わらない" 'cmp -s .env "$WORK/before"'
done
check "一時ファイルが残らない" '[ -z "$(ls -A | grep op-env || true)" ]'

chmod 000 .env
check_rc "読めない .env では exit 1" 1 "$OP_ENV" FOO
chmod 600 .env
check "読めない .env を変えない" 'cmp -s .env "$WORK/before"'

# 引数とトークンの検査
check_rc "引数なしは exit 2" 2 "$OP_ENV"
check_rc "不正なキー名は exit 2" 2 "$OP_ENV" 'A|B'
check_rc "トークンが無ければ exit 1" 1 env OP_ENV_TOKEN_FILE=/nonexistent "$OP_ENV" FOO
: > "$WORK/empty-token"
check_rc "トークンが空なら exit 1" 1 env OP_ENV_TOKEN_FILE="$WORK/empty-token" "$OP_ENV" FOO

# シンボリックリンクの .env はリンクを残したままリンク先に書く
mkdir -p "$WORK/shared" "$WORK/linked"
printf 'KEEP=1\n' > "$WORK/shared/.env"
ln -s "$WORK/shared/.env" "$WORK/linked/.env"
(cd "$WORK/linked" && "$OP_ENV" FOO >/dev/null)
check "リンクが残る" '[ -L "$WORK/linked/.env" ]'
check "リンク先に書く" 'grep -qx "FOO='"'"'foo-new'"'"'" "$WORK/shared/.env" && grep -qx KEEP=1 "$WORK/shared/.env"'
check "リンク先も 600" '[ "$(stat -f %Lp "$WORK/shared/.env")" = 600 ]'
check "リンク先のディレクトリに一時ファイルが残らない" '[ -z "$(ls -A "$WORK/shared" | grep op-env || true)" ]'
ln -s "$WORK/nowhere/.env" "$WORK/dangling.env"
mkdir -p "$WORK/dangling" && mv "$WORK/dangling.env" "$WORK/dangling/.env"
check_rc "リンク先が無ければ exit 1" 1 sh -c 'cd "$1" && "$2" FOO' _ "$WORK/dangling" "$OP_ENV"

echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
