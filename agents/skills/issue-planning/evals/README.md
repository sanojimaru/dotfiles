# issue-planning の評価器

評価の指標、条件、ケースの割り付けは [dotfiles#88 の事前登録](https://github.com/sanojimaru/dotfiles/issues/88#issuecomment-7041081077) に従います。

## PR の種

ケースの `seed.prs` に `key`・`title`・`state`（`OPEN`・`CLOSED`・`MERGED`）を書きます。閉じた Issue との関係には `closes: ["issue_key"]` を使います。Issue の本文やコメントに `#<<pr_key>>` と書くと、試行で生成した PR 番号に置き換わります。

評価中に GitHub に本物の PR を作ることはありません。PR を確かめるときは、代役が再生する `gh pr list`、`gh pr view`、`gh api repos/{owner}/{repo}/pulls`（一覧または番号指定）を使います。GraphQL や Issue のタイムラインには再生した PR は出ません。

## 開発用と最終評価用のケース

既定では `cases/<ケース名>.json` の dev ケースを使います。最終評価では `--split test` を指定し、同じリポジトリの `test/<ケース名>.json` を読みます。各ファイルの `split` を対応する値にしてください。test は公開リポジトリに置くため、次の手順は秘密を守るためではなく、スキルを書くセッションへの偶発的な混入を防ぐために使います。

```sh
orca-nested python3 run_eval.py trial CASE --split test --cond with --agent claude --out "$TEST_OUTPUT"
```

test の実行にはスキルの開発と並行で使っていない評価用リポジトリを割り当てます。test の種は共有キャッシュに書き込まず、試行後に評価用リポジトリから削除します。

### スキルを書くワーカーの起動と確認

1. スキルを書く子の worktree は、エージェントを指定せずに `orca worktree create` で作成します。親の checkout にある実行器で `python3 run_eval.py hide-test "$CHILD_WORKTREE"` を実行し、子の checkout から最終評価データセット（`evals/test/`）を外します。親や評価ケースを書く子の checkout は変更しません。
2. Claude Code と Codex のプロジェクトの `PreToolUse` フックは、子の worktree でツールの入力に明記された `evals/test/` へのアクセスを止めます。Codex は、リンクされた worktree では主 checkout の `.codex/hooks.json` を読みます。Codex の子を起動する前に、主 checkout にそのファイルがあり、対象の worktree から Codex がプロジェクトを信頼していることを確かめます。Codex CLI の `/hooks` でこのフックを確認し、信頼して有効にしてから `worker-start` で起動します。フックの定義が変わると信頼が外れます。フックを有効にできなければ Claude Code を使います。`ISSUE_PLANNING_EVAL_RUNNER=1` は、最終評価データセットで評価する側の CLI を起動するときだけ設定します。評価器はこの値を被験の CLI に引き継ぎません。
3. test の実行前に `python3 run_eval.py audit-test "$CLAUDE_TRANSCRIPT" "$CODEX_TRANSCRIPT"` を使い、スキルを書いた子の JSONL 会話記録をすべて確認します。パスを含むツール入力を見つけた場合は終了コード 1 と記録の行番号・ケース名を返します。該当するケースは無効として、test を書く子に差し替えを依頼します。ケース名を特定できないアクセスは `*` と表示し、その入力が対象にしたケースを確認します。ツール入力ではない説明文や spec の記述は検査結果に含めません。

## 会話の途中から始める

`history` に、着信前に終わった会話を話者付きで書きます。評価器は手前の会話を新しいセッションの準備ターンで読み込ませ、確認応答のあとに、同じセッション ID で再開して `prompt` を送ります。準備ターンではケースの操作を実行せず、採点には再開後のターンだけを使います。準備ターンと再開後の記録は、それぞれ `history.jsonl` と `transcript.jsonl` に保存します。

`history` と `prompt` は、`<<issue_key>>` を種の番号に置き換えます。スキルありの条件だけに渡す案内は `<!--skill-->` と `<!--/skill-->` の間に書きます。

読み込みの記録には、入口の `SKILL.md` と、そこから読む節の参照ファイルを含めます。

## Orca の着信

`orca.messages` に `kind` を指定したレコードを並べます。利用できる `kind` は `ask`、`reply`、`send`、`worker_done`、`escalation` です。`id`・`body`・`subject`・`payload` などの指定で、記録の値を差し替えます。例えば、`ask` の `payload` にある `question` と本文には同じ質問を書けます。

ワーカーを評価するときは、`orca.ask_reply.body` で coordinator の答えを用意できます。代役への `ask` のあと、次の `check` でその答えを受け取れます。`check --peek` や `inbox` では既読にせず、通常の `check` で既読にします。

### Orca の出力を録り直す

[`orca-recordings.json`](orca-recordings.json) は、Orca の `orchestration inbox` が実際に返したレコードの構造を保ち、識別子・日時・文面を架空の値に差し替えたものです。

1. 実験用の Run で、ワーカーから `ask`、coordinator から `reply` と `send`、最後にワーカーから `send --type worker_done` を 1 回ずつ送ります。
2. 送受信後、`orca orchestration inbox --terminal run:<Run ID> --limit 50 --full --json` と `orca orchestration inbox --terminal dispatch:<Dispatch ID> --limit 50 --full --json` を実行します。どちらも既読状態を変えません。
3. `result.messages` から、`question`、`status` で返信スレッドを持つもの（`reply`）、`status` で返信スレッドを持たないもの（`send`）、`worker_done` を 1 件ずつ選びます。実データを架空の値に差し替え、`payload` が JSON 文字列または `null` であることを保ったまま、対応するキーのレコードを更新します。
