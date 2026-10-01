# ローカル設定

## GitHub
- アカウント: sanojimaru

## SSH
- SSHはすべて1PasswordのSSHエージェントを使う
- 鍵の生成・`ssh-add`・キーチェーン登録はしない
- IdentityAgent: `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`

## バージョン管理
- 言語ランタイム・CLIのバージョンはOSワイドで `mise` が管理する（正本: `~/dotfiles/config/mise/config.toml`、`~/.config/mise/config.toml` へリンク）
- `python3` `node` などはmise shims（`~/.local/share/mise/shims`）経由で使う。システム標準の古い python3(3.9) は使わない
- ツールの追加・更新は `mise use -g <tool>@<version>` で行い、dotfiles側の config.toml をコミットする
