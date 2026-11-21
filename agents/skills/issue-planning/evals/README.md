# issue-planning の評価器

評価の指標、条件、ケースの割り付けは [dotfiles#88 の事前登録](https://github.com/sanojimaru/dotfiles/issues/88#issuecomment-7041081077) に従います。

## PR の種

ケースの `seed.prs` に `key`・`title`・`state`（`OPEN`・`CLOSED`・`MERGED`）を書きます。閉じた Issue との関係には `closes: ["issue_key"]` を使います。Issue の本文やコメントに `#<<pr_key>>` と書くと、試行で生成した PR 番号に置き換わります。

評価中に GitHub に本物の PR を作ることはありません。PR を確かめるときは、代役が再生する `gh pr list`、`gh pr view`、`gh api repos/{owner}/{repo}/pulls`（一覧または番号指定）を使います。GraphQL や Issue のタイムラインには再生した PR は出ません。

## 非公開の test ケース

test の GitHub リポジトリは、スキルを書くセッションが使う GitHub 認証ではアクセスできない非公開のリポジトリに置きます。ケース作成用の認証と、評価器が取得するための読み取り専用の認証を分けます。ケースは `cases/<ケース名>.json` に置き、`"split": "test"` を指定します。評価器は通常の GitHub 認証で 404 が返ることを確認し、標準入力で受け取ったトークンだけで取得します。

```sh
orca-nested python3 run_eval.py trial CASE --holdout-repo OWNER/REPO \
  --cond with --agent claude --out "$PRIVATE_EVAL_DIR" < "$READ_TOKEN_FILE"
```

トークンを被験の CLI に渡すことはありません。test の試行ログは、スキルを書くセッションがアクセスできない場所に保存します。test の実行にはスキルの開発と並行で使っていない評価用リポジトリを割り当てます。test の種は共有キャッシュに書き込まず、試行後に評価用リポジトリから削除します。

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
