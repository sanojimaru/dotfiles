# issue-planning の評価器

評価の指標、条件、ケースの割り付けは [dotfiles#88 の事前登録](https://github.com/sanojimaru/dotfiles/issues/88#issuecomment-7041081077) に従います。

## GitHub の代役

既定（`--gh fake`）では、種の Issue とラベルを試行ごとの手元の状態（`gh-state.json`）に立てます。被験エージェントの `gh issue`・`gh label`・`gh repo view`・`gh api repos/<owner>/<repo>/...` は代役（`fake_gh.py`）が状態から返し、書き込みも状態に記録します。採点は、状態から終わった状態を読みます。GitHub の API の上限は利用者の全リポジトリ・全エージェントで共有しているので、試行では本物の GitHub を呼びません。代役は GraphQL（`gh api graphql`）を返さず、`gh issue view --json` か REST を使うよう案内して失敗します。

### 代役と本物のずれを確かめる

代役や評価ケースを直したあと、代役の返す形が本物とずれていないかを確かめるときは、同じケースを本物の GitHub と代役で 1 試行ずつ（合わせて 2 試行）流して比べます。`--gh real` は評価用リポジトリ（`ipe-N`）に種を立てて戻すため、`gh api rate_limit` で GraphQL の残りを確かめてから流します。

```sh
orca-nested python3 run_eval.py trial S1a-A1 --cond with --agent claude --gh real --repo ipe-1 --out "$REAL_OUT"
orca-nested python3 run_eval.py trial S1a-A1 --cond with --agent claude --out "$FAKE_OUT"
```

比べるのは、`trial.json` の `grade` と、`calls.jsonl` のうち `tool` が `gh` で `rc` が 0 でない呼び出しです。代役でだけ失敗した呼び出しは、代役が対応していない形なので、`fake_gh.py` に足します。

## PR の種

ケースの `seed.prs` に `key`・`title`・`state`（`OPEN`・`CLOSED`・`MERGED`）を書きます。閉じた Issue との関係には `closes: ["issue_key"]` を使います。Issue の本文やコメントに `#<<pr_key>>` と書くと、試行で生成した PR 番号に置き換わります。

評価中に GitHub に本物の PR を作ることはありません。PR を確かめるときは、代役が再生する `gh pr list`、`gh pr view`、`gh api repos/{owner}/{repo}/pulls`（一覧または番号指定）を使います。GraphQL や Issue のタイムラインには再生した PR は出ません。

## dev ケースと評価データセット

既定では `cases/<ケース名>.json` の dev ケースを使います。評価データセット（スキルを書くセッションに見せない評価ケース。英語では held-out set）は `--split holdout` を指定し、同じリポジトリの `holdout/<ケース名>.json` を読みます。各ファイルの `split` を対応する値にしてください。評価データセットは公開リポジトリに置くため、次の手順は秘密を守るためではなく、スキルを書くセッションへの偶発的な混入を防ぐために使います。

```sh
orca-nested python3 run_eval.py trial CASE --split holdout --cond with --agent claude --out "$HOLDOUT_OUTPUT"
```

`--gh real` で評価データセットを流すときは、スキルの開発と並行で使っていない評価用リポジトリを割り当てます。評価データセットの種は共有キャッシュに書き込まず、試行後に評価用リポジトリから削除します。

### スキルを書くワーカーの起動と確認

1. スキルを書く子の worktree は、エージェントを指定せずに `orca worktree create` で作成します。親の checkout にある実行器で `python3 run_eval.py hide-holdout "$CHILD_WORKTREE"` を実行し、子の checkout から評価データセット（`evals/holdout/`）を外します。親や評価ケースを書く子の checkout は変更しません。
2. Claude Code と Codex のプロジェクトの `PreToolUse` フックは、子の worktree でツールの入力に明記された `evals/holdout/` へのアクセスを止めます。Codex は、リンクされた worktree では主 checkout の `.codex/hooks.json` を読みます。Codex の子を起動する前に、主 checkout にそのファイルがあり、対象の worktree から Codex がプロジェクトを信頼していることを確かめます。Codex CLI の `/hooks` でこのフックを確認し、信頼して有効にしてから `worker-start` で起動します。フックの定義が変わると信頼が外れます。フックを有効にできなければ Claude Code を使います。`ISSUE_PLANNING_EVAL_RUNNER=1` は、評価データセットで評価する側の CLI を起動するときだけ設定します。評価器はこの値を被験の CLI に引き継ぎません。
3. 評価データセットを流す前に `python3 run_eval.py audit-holdout "$CLAUDE_TRANSCRIPT" "$CODEX_TRANSCRIPT"` を使い、スキルを書いた子の JSONL 会話記録をすべて確認します。パスを含むツール入力を見つけた場合は終了コード 1 と記録の行番号・ケース名を返します。該当するケースは無効として、評価ケースを書く子に差し替えを依頼します。ケース名を特定できないアクセスは `*` と表示し、その入力が対象にしたケースを確認します。ツール入力ではない説明文や spec の記述は検査結果に含めません。呼び方を変える前の `evals/test/` へのアクセスも同じく検出します。

## S1 の GitHub の予算

S1（窓口の着手前の確認。S1a・S1b の評価ケース）は、1 回の GitHub の消費を GraphQL 10 ポイントまでとし、超えた試行は `graphql-budget` の確認で失敗にします。代役は GitHub を呼ばないので、`calls.jsonl` に記録した `gh` の呼び出しから、#138 で本物に流して測った単価で見積もります（`grading.py` の `graphql_points`）。

- 成功した（終了コード 0 の）`gh` の呼び出し 1 回を 1 ポイントと数えます。書き込み（`issue comment`・`issue close`・`issue edit` など）と `gh repo view` も含めます。
- 一覧（`gh issue list`・`gh pr list`）は、返した行数 100 件ごとに 1 ポイント（最低 1）と数えます。GitHub の GraphQL は 1 ページ 100 件で、ページごとに 1 ポイントを使うためです。
- REST（`gh api repos/...`）は GraphQL のポイントを使わないので数えません。代役が断った呼び出し（GraphQL の `gh api graphql` など）は GitHub に届かないので数えません。

#138 の実測では、S1 の一覧 2 回で 3 ポイント前後、候補の Issue を読むのは 1 件 1 ポイントでした。`report` は、ケースごとの見積もりの最大を `gql=` に出します。

## 判定器の較正

dev の試行から、判定器の問いがある試行を混ぜて 20 件選び、人が判定器と同じ証拠に yes/no を付けます（#88 の決定 4）。

```sh
orca-nested python3 run_eval.py batch CASES --n 1 --cond with,without --out "$DEV_OUTPUT"
python3 run_eval.py labels "$DEV_OUTPUT" --out "$LABEL_DIR" --count 20
python3 run_eval.py agreement "$LABEL_DIR/human.json" "$LABEL_DIR/answers.json"
```

`labels.md` には、問いごとに判定器に渡した証拠（返事、Issue の本文やコメント、`orca` の呼び出し）をそのまま出します。条件（スキルの有無）は並びから分からないよう混ぜ、判定器の答えは `answers.json` に分けます。

新しく書いた判定の問いを較正するときは、`--count` の代わりに `--cover` を付けます。ケースの問いがそれぞれ 1 回以上入るまで試行を選び、どの試行でも証拠が空で入れられなかった問いを表示します。評価データセットの試行も渡せます。判定器の違う組（被験が Claude の試行と Codex の試行）を 1 回のラベル付けにまとめるときは、組ごとに `--prefix` を変え、2 組目から `--append` を付けます。`agreement` は、キーの頭の英字の組ごとに一致率を出します。

```sh
python3 run_eval.py labels "$CODEX_DEV_OUTPUT" --out "$LABEL_DIR" --count 20 --prefix A --title "組 A"
python3 run_eval.py labels "$CLAUDE_HOLDOUT_OUTPUT" --out "$LABEL_DIR" --cover --prefix B --append --title "組 B"
```

### ラベラー（エージェントのラベル）

`labeler.py` は、`labels.md` の問いと証拠だけを読み、別の会社の 2 モデルが同じ yes か no を返した問いにそのラベルを、unsure か食い違いの問いに保留（`null`）を付けます（dotfiles#193）。被験と同じ系統のモデルだけでラベルを決めないためです。保留が問いの 20%（`--hold`）に満たなければ、2 モデルが答えた確信度の小さいほうが低い問いから、20% に達するまで保留に回します。保留した問いは利用者が付けます。`label_metrics.py` は、`human.json`・`answers.json` とラベラーの `agent.json` から、#193 の事前登録の合格線 1〜4 と、報告だけの指標を出します。`agent.json` を省くと、すべて yes の代役と判定器だけを出します。test（`190-labels`）を測るときは `--groups A,B` を付け、どちらかの組が `answers.json` に無ければ未判定にします。

```sh
orca-nested python3 labeler.py "$LABEL_DIR/labels.md" --out "$AGENT_DIR"
python3 label_metrics.py "$LABEL_DIR/human.json" "$LABEL_DIR/answers.json" "$AGENT_DIR/agent.json" --reasons "$AGENT_DIR/reasons.json"
```

## 会話の途中から始める

`history` に、着信前に終わった会話を話者付きで書きます。評価器は手前の会話を新しいセッションの準備ターンで読み込ませ、確認応答のあとに、同じセッション ID で再開して `prompt` を送ります。準備ターンではケースの操作を実行せず、採点には再開後のターンだけを使います。準備ターンと再開後の記録は、それぞれ `history.jsonl` と `transcript.jsonl` に保存します。

`history` と `prompt` は、`<<issue_key>>` を種の番号に置き換えます。スキルありの条件だけに渡す案内は `<!--skill-->` と `<!--/skill-->` の間に書きます。

読み込みの記録には、入口の `SKILL.md` と、そこから読む節の参照ファイルを含めます。

## ワーカーのケース（spec から始める）

`spec` を持つケースは、`prompt` の代わりに [`references/spec.md`](../references/spec.md) の型へ番号とパスを入れて渡します。`issue`（作業 Issue の key）・`epic`（親の Epic の key）・`hours`（作業時間の目安）を書きます。型を直すと、次の試行から直した型で走ります。ワーカーは `issue-planning` を読まないので、`--cond without` で流します。

ワーカーの worktree には `checkout` と `current: true` を付け、同名のブランチの PR を種に置きます。マージまで確かめるケースの PR には、`replay_checks`（`bucket: pass` の CI）を付けます。

## 試行の隔離

被験は `sandbox-exec` の下で起動し、`/private/tmp` を読み書きさせません（Claude Code 自身が使う `/private/tmp/claude-<uid>` だけ許します）。被験が固定名の `/tmp/x.md` を使うと、並行する試行や前のセッションの同名のファイルと衝突し、別の試行の本文を Issue や `ask` に送ってしまうためです。同じ理由で、`TMPDIR` は試行ごとの `<出力先>/tmp/` に向けます。macOS の `mktemp` は `TMPDIR` でなく利用者ごとの一時ディレクトリに乱数の名前で作るので、止まらず、衝突もしません。Codex の準備ターン（`--sandbox read-only`）だけは、Codex 自身が `sandbox-exec` を使い入れ子にできないので包みません。準備ターンは道具を使わないことを確かめているので、一時ファイルは書きません。

代役の `orca` は、`--help` を本物に渡し、本物に無い `orchestration` のサブコマンドを本物と同じ `invalid_argument` で失敗させます。代役が知らないコマンドを成功で返すと、被験は誤ったコマンドのまま進むためです。

## Orca の着信

`orca.messages` に `kind` を指定したレコードを並べます。利用できる `kind` は `ask`、`reply`、`send`、`worker_done`、`escalation` です。`id`・`body`・`subject`・`payload` などの指定で、記録の値を差し替えます。例えば、`ask` の `payload` にある `question` と本文には同じ質問を書けます。

ワーカーを評価するときは、`orca.ask_reply.body` で coordinator の答えを用意できます。代役への `ask` のあと、次の `check` でその答えを受け取れます。`check --peek` や `inbox` では既読にせず、通常の `check` で既読にします。

### Orca の出力を録り直す

[`orca-recordings.json`](orca-recordings.json) は、Orca の `orchestration inbox` が実際に返したレコードの構造を保ち、識別子・日時・文面を架空の値に差し替えたものです。

1. 実験用の Run で、ワーカーから `ask`、coordinator から `reply` と `send`、最後にワーカーから `send --type worker_done` を 1 回ずつ送ります。
2. 送受信後、`orca orchestration inbox --terminal run:<Run ID> --limit 50 --full --json` と `orca orchestration inbox --terminal dispatch:<Dispatch ID> --limit 50 --full --json` を実行します。どちらも既読状態を変えません。
3. `result.messages` から、`question`、`status` で返信スレッドを持つもの（`reply`）、`status` で返信スレッドを持たないもの（`send`）、`worker_done` を 1 件ずつ選びます。実データを架空の値に差し替え、`payload` が JSON 文字列または `null` であることを保ったまま、対応するキーのレコードを更新します。
