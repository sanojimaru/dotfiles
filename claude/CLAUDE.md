# ローカル設定

## GitHub
- アカウント: sanojimaru

## SSH
- SSHはすべて1PasswordのSSHエージェントを使う
- 鍵の生成・`ssh-add`・キーチェーン登録はしない
- IdentityAgent: `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`

## APIキー（1Password CLI）
- APIキーは1Password の `Personal` vault に登録済み。アイテム名は環境変数名と同じ。フィールドは `credential`
  - `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `TYPESAFE_API_KEY`（Typesafe AI。jevプラグインが読む）
- キーの値を `.env`・コード・会話・ログに書かない。必ず `op` 経由で実行時に渡す
- コマンドに渡すとき: `op run --env-file=<(printf 'OPENAI_API_KEY=op://Personal/OPENAI_API_KEY/credential\n') -- <コマンド>`（必要なキーだけ列挙する）
- 単発で参照するとき: `op read "op://Personal/<アイテム名>/credential"`
- 確認で値を出すときは長さだけにする（例: `${#OPENAI_API_KEY}`）
- `op` はデスクトップアプリ連携のため、Claude Codeのサンドボックス内では接続できない。サンドボックス外での実行が必要

## バージョン管理
- 言語ランタイム・CLIのバージョンはOSワイドで `mise` が管理する（正本: `~/dotfiles/config/mise/config.toml`、`~/.config/mise/config.toml` へリンク）
- `python3` `node` などはmise shims（`~/.local/share/mise/shims`）経由で使う。システム標準の古い python3(3.9) は使わない
- ツールの追加・更新は `mise use -g <tool>@<version>` で行い、dotfiles側の config.toml をコミットする
