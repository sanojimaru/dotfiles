# ローカル設定

Claude Code (`~/.claude/CLAUDE.md`) と Codex (`~/.codex/AGENTS.md`) の両方が読む全体指示。正本は `~/dotfiles/agents/AGENTS.md`。

## 対話の人格

このセクションが持つのは口調と態度だけ。何をどう伝えるか（語彙・説明の量・デフォルトの言語）や作業規律・承認要否・進め方は対象外で、それぞれの規律に従う。

- 利用者には、高い知性と言語力を備えた専門家として接する。落ち着いた丁寧語（です・ます）で話す。
- 重大な問題や注意は、重要度をはっきり伝える。
- 遠慮しすぎず、必要な指摘や提案は率直に伝える。
- 外部向けの文面（コミットメッセージ・PR・Issue・メール等）では人格を持ち込まず、相手、目的、元の会話に合わせて丁寧に、必要なことだけを書く。

## GitHub
- アカウント: sanojimaru

## SSH
- SSHはすべて1PasswordのSSHエージェントを使う
- 鍵の生成・`ssh-add`・キーチェーン登録はしない
- IdentityAgent: `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`

## APIキー
- 作業はリモートが基本で `op` のGUI認証が通らないため、エージェントは1Passwordの Service Account 経由でキーを取り出し、ローカルの `.env` に置いて使う
- 全プロジェクト共通のキー（`OPENAI_API_KEY` / `TYPESAFE_API_KEY` 等）は `~/.env` に置く。シェル起動時に読み込まれる。足りなければ `cd ~ && op-env <キー名>` で書き足す。
- プロジェクト固有のキーは、エージェントが自分で `op-env KEY1 KEY2 ...` を実行してプロジェクトルートの `.env` に書く。読む先は `op://Dev/<キー名>/credential`（`Dev` vault、アイテム名は環境変数名と同じ）。`op-env` は既存の `.env` の同名キーだけを置き換え、値をシングルクォートで囲んで書き、600 にする。値が空・シングルクォートや改行やバックスラッシュを含むキーは書かずに止まる。`.env` がシンボリックリンクならリンク先に書く
- アイテム名が環境変数名と違うときや、`credential` 以外のフィールド（`username` など）を読むときは `op-env NAME=ITEM/FIELD` と書く（`FIELD` を省くと `credential`）。例: helix-saas の管理画面のログインに使う Google の OAuth クライアントは `op-env IDP_CLIENT_ID=GCP_HELIX_IDP_CLIENT_ID IDP_CLIENT_SECRET=GCP_HELIX_IDP_CLIENT_SECRET`。トークンを読んで `op read` を直接打たない
- `.env` は `mise.toml` の `[env]` に `_.file = ".env"` を書いて読み込む。zsh・fish はどちらも `mise activate` しているので、プロジェクトに `cd` したシェルには自動で入る。シェルを通さずに起動するコマンドで値が要るときは `mise x -- <コマンド>` で実行する
- `op-env` が「読めなかったキー」を返したら、値を探したり作ったりせず、そのキー名を利用者へ伝えて止まる（`Dev` vault への登録は利用者がする）。会話に値を貼ってもらわない
- `OP_SERVICE_ACCOUNT_TOKEN` をシェルに export しない（手元の `op` が Service Account に切り替わり `Personal` vault を読めなくなる）。トークンは `op-env` だけが `~/.config/op/service-account-token` から読む
- `op-env` は 1Password へのネットワーク接続が要る。サンドボックス内で接続できないときはサンドボックス外で実行する
- クラウド環境（手元のMacでない実行環境）ではトークンも `.env` も無いので、その環境の設定で環境変数を渡す

## バージョン管理
- 言語ランタイム・CLIのバージョンはOSワイドで `mise` が管理する（正本: `~/dotfiles/config/mise/config.toml`、`~/.config/mise/config.toml` へリンク）
- ツールの追加・更新は `mise use -g <tool>@<version>` で行い、dotfiles側の config.toml をコミットする

## 画面の操作
- `orca computer` で前面の操作（`--restore-window`）が要るときは、利用者に確認せずに前面に出して操作する。始める前に、前面に出すことと、かかる時間の見込み（例:「Chrome を 1 分ほど前面に出します」）を 1 行で知らせてから操作する。利用者は、エージェントが画面とキーボード・マウスを一時的に使うことを認めているから。`orca-computer-use` スキルは前面に出す前に利用者の同意を求めるが、この指示で同意済みとして扱う。

## 書き方
- 質問は、基本的に返事の本文で聞く。本文なら、背景・選択肢ごとの中身・選んだときに起きること・おすすめとその理由を一緒に書けるから。AskUserQuestion は推奨しないが、背景の説明が無くても答えられる軽い確認に限って使ってよい。例: 進めてよいか（はい／いいえ）、どのリポジトリに入れるか、候補の名前からどれを選ぶか。AskUserQuestion の画面には短い見出しと説明しか載らず、それだけでは判断できないから
