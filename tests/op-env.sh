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
[ -n "$OP_SERVICE_ACCOUNT_TOKEN" ] || { echo "no token" >&2; exit 1; }
case "$2" in
  */FOO/*) echo foo-new ;;
  */BAR/*) echo bar-val ;;
  */SPECIAL/*) printf '%s' 'a b#c$HOME"q;$(echo x)`id`&\y' ;;
  */EMPTY/*) printf '' ;;
  */QUOTE/*) echo "it's" ;;
  */NL/*) printf 'a\nb' ;;
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
want="$(OP_SERVICE_ACCOUNT_TOKEN=x op read op://Dev/SPECIAL/credential)"
check "特殊文字の値を zsh が文字どおり読む" '[ "$(zsh -fc "set -a; . ./.env; printf %s \"\$SPECIAL\"")" = "$want" ]'

# 失敗するときは .env を変えず、一時ファイルも残さない
cp .env "$WORK/before"
for key in NOPE EMPTY QUOTE NL; do
  check "$key は exit 1" '! "$OP_ENV" FOO "$key" 2>/dev/null'
  check "$key で .env が変わらない" 'cmp -s .env "$WORK/before"'
done
check "一時ファイルが残らない" '[ -z "$(ls -A | grep op-env || true)" ]'

chmod 000 .env
check "読めない .env では exit 1" '! "$OP_ENV" FOO 2>/dev/null'
chmod 600 .env
check "読めない .env を変えない" 'cmp -s .env "$WORK/before"'

# 引数とトークンの検査
check_rc "引数なしは exit 2" 2 "$OP_ENV"
check_rc "不正なキー名は exit 2" 2 "$OP_ENV" 'A|B'
check_rc "トークンが無ければ exit 1" 1 env OP_ENV_TOKEN_FILE=/nonexistent "$OP_ENV" FOO

echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
