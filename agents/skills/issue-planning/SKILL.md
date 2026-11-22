---
name: issue-planning
description: 窓口（デフォルトブランチのセッション）が、次の着手を決める、利用者の依頼を backlog・単独タスク・Epic・マイルストーン Issue に振り分ける、単独タスクのワーカーの質問や終了通知に対応するときに読む。止まった Issue を確かめ、立て直す手順も持つ。Issue の計画や進行に関係しない質問、リポジトリや設定の調査、worktree 一覧の表示だけなら読まない。Epic の親は渡された指示に沿って該当する節を読み、ワーカーはこのスキルでなく渡された spec を読む。Orca の進行管理コマンドは `orchestration`、worktree と terminal の操作は `orca-cli` を読む。
---

# Epic の親が読む節

節の番号は窓口や Epic の親の運用場面を表す。Epic の親は、担当する場面に対応する参照を読む。会話の途中で別の場面に移ったときも、この一覧から該当する節を読み直す。

- [S3: Epic の計画を書く](references/epic-s3.md)
- [S4: 子を起動する](references/epic-s4.md)
- [S5: ワーカーからの質問や停止の通知に対応する](references/epic-s5.md)
- [S6: ワーカーの報告を実際の状態と照らし合わせる](references/epic-s6.md)
- [S7: Epic を閉じて利用者に報告する](references/epic-s7.md)
- [S8: 止まった親のセッションを再開する](references/epic-s8.md)

窓口と親は、ワーカーを起動する spec に[共通の型](references/spec.md)を使う。ワーカー自身は、このスキルではなく渡された spec を読む。

# 窓口の着手前の確認

窓口はリポジトリのファイルを変えない。変更する依頼は、Issue を立てるか再利用し、別の worktree でワーカーに任せる。

次に何に着手するかを決める前（利用者に「次は？」と聞かれたとき、Epic や単独タスクが閉じたとき）に、下の 3 つを毎回確かめる。見つけたものに対応してから、次の候補を返す。

GitHub の API の上限（GraphQL は 1 時間に 5,000 ポイント）は、利用者の全リポジトリ・全エージェントで共有している。一覧では番号・題名・type・親・件数だけを取り、本文・コメント・sub-issue の中身は、候補の Issue だけ読む。Orca で分かることは、先に手元の Orca で確かめる。開いている Issue の一覧は、次の 1 回で取り、下の 1・2 で使い回す。

```sh
gh issue list --state open --limit 200 --json number,title,issueType,parent,subIssuesSummary
```

`--limit` を必ず付ける。既定は 30 件で、31 件目以降を見落とす。返った件数が `--limit` と同じなら、`--limit` を増やして取り直す。上限で切れた古い Epic を、無いものと読まないため。

## 1. 止まった Epic と単独タスク

一覧の Epic（type: Feature）と、単独タスク（type: Task で、親が無いかマイルストーン Issue のもの。S3 で Epic から書き換えた Task を含む）について、coordinator が止まっていないかを、手元の Orca で探す。GitHub は使わない。

```sh
orca orchestration run-list --json
orca orchestration worker-list --run <Run の id> --json
orca orchestration inbox --terminal run:<Run の id> --limit 50 --json
orca worktree list --json
```

Run の objective は `<owner>/<repo>#<番号> ` で始まる（S2・S3）。一覧の番号で Run を選ぶ。親を起こす・立て直すために窓口が作った Run（`... の親を起こす`・`... の親を立て直す`）は、Epic の Run ではない。どの Run の objective にも番号が無い Issue と、同じ番号の Epic の Run が 2 つ以上ある Issue だけ、本文の Run id を読む。`run-list` と `worker-list` は、`nextCursor` が返ったら続きも読む。

候補は次のどれかに当たるもの。

- Epic の Run の受信箱に、未読（`read` が 0）の `question`・`worker_done` がある。生きている親は、届いた通知を読んでいる。
- Epic に開いている子が無い（`subIssuesSummary` の `total` と `completed` が同じ）。次の子を立てる親が動いていなければ、Epic は進まない。
- 単独タスクの worker が、`worker_done` を出さずに（`outcome` が `succeeded`・`failed` でない）`exited`・`lost` になっている。
- 単独タスクの Run の受信箱に、未読の `worker_done`・`question` がある。前の窓口のセッションが受けていない。ワーカーは Issue を閉じてから `worker_done` を送るので、Issue が閉じていても、objective に番号がある Run の受信箱は確かめる。

Epic の候補は、親の生死を確かめる。未読の通知や開いている子が無いことは、調べるきっかけで、親が止まった証拠ではない。親の worktree は、`worktree list` の `linkedIssue` が Epic の番号で、`displayName` が `<番号>-epic-` で始まるもの。どの Run の `worker-list` でも、その worktree で動く worker が親にあたる。同じ worktree の worker が複数の Run に出ているときは、すべて集めてから判断する（起こした Run に止まった親、立て直した Run に新しい親が出る）。窓口が S2 で起こした親と立て直した親は、窓口の Run（`... の親を起こす`・`... の親を立て直す`）に出る。以前の手順で立て直した親は、Epic の Run に出る。古い起こし方（`worktree create --agent`）で起こされた親は、どの Run の worker でもないので `worker-list` に出ず、下の「worker が見つからない」親として扱う。

- `liveness` が `live` の親は、次の子を立てる途中か、子の質問を処理中。手を出さない。二重に起こすと、2 つの親が同じ Epic を進める
- `exited`・`lost` の親は、止まっている。立て直す
- `unverifiable` の親と、worker が見つからない Epic の親（古い起こし方の親を含む）は、止まったと決められない（親がまだ動いているかもしれない）。立て直さず、Epic にその旨と見つけたこと（未読の通知など）をコメントし、返事で利用者に確かめる

本文とコメントは、立て直す・確かめる Issue だけ `gh issue view <番号> --json body,comments` で読む。

### Epic の親の立て直し方

親の worktree は Epic に紐づいたまま残っている。`worktree create` は使えない。窓口は Epic の Run を `run-use` しない。窓口がその Run を束ねると、子の質問が窓口に届き、新しい親もその Run の worker になって Run を引き継げない（`worker_cannot_coordinate_own_run`）。

1. Epic に、立て直すことと理由をコメントする。コメントを先に書く。新しい親が Issue から続けられるようにするため
2. 窓口の Run を `orca orchestration run-create --objective "<owner>/<repo>#<番号> の親を立て直す" --json` で作る
3. 次の spec を一時ファイルに書き、`orca orchestration worker-start --run <窓口の Run の id> --spec-file <spec の一時ファイル> --worktree path:<Epic の worktree の絶対パス> --agent <エージェント> --model <モデル> --effort high --keep-open` で新しい親を起こす。worktree の選択子は `issue:<番号>` でなく `path:` にする。ほかのリポジトリに同じ番号の Issue に紐づいた worktree があると、`issue:` は拒否される

   ```text
   Epic #<番号> の親のセッション（coordinator）を担当する。前の親のセッションは止まった。
   Epic の本文に Run の id があれば、最初に `orca orchestration run-use --id <その Run の id>` で Epic の Run を引き継ぎ、issue-planning の S8 の手順で、Epic の本文と Issue のコメントから続ける。本文に Run の id が無ければ、S8 の「Epic の本文に Run の id が無いとき」に従う。
   ```

新しい親は、子を待つ間、`worker_done` を送らずにターンを終える。そのとき窓口に `Worker stopped without reporting`（`stopReason`: `finished`）の escalation が 1 回届く。親が待っている合図なので、対応しない。

### 単独タスクの立て直し方

本文の Run の id で `run-use --id` を実行し、Issue のコメントで途中の状態を読んでから、同じ Task を起動し直すか新しい Task を立てて起動する。起こす前に、Task Issue にコメントする。未読の `worker_done`・`question` は、[S9](#s9-単独タスクの-coordinator-として対応する) の手順で受ける。

## 2. 開いた Epic の無いマイルストーン Issue

一覧で type が無く、`subIssuesSummary.total` が 0 より大きいものがマイルストーン Issue。一覧の Epic のうち、`parent` がそのマイルストーン Issue のものが無ければ、次の着手待ち。

Epic を勝手に立てない。sub-issue の `backlog` の候補（下の 3 の一覧で `parent` がそのマイルストーン Issue のもの）を、おすすめと理由を付けて返す。成功の条件を満たしているなら、利用者に確かめてから閉じる。

## 3. `backlog` の全件

```sh
gh issue list --label backlog --state open --limit 500 --json number,title,parent
```

番号と題名から次の候補を選び、候補として挙げる Issue だけ本文を読む。本文が指す事実（別の Issue・不具合・ファイル）がもう当てはまらないものは、確かめた理由をコメントしてから閉じる。ほかの `backlog` は閉じない。

## 返事

立て直したことと閉じたことを先に書く。そのあと、次の着手の候補を、おすすめとその理由を付けて返す。親が `live` で手を出さなかった Epic があれば、その旨も 1 行で書く。

# S2: 依頼を振り分ける

「〜したい」だけで着手の意思が分からなければ、最初は「今着手しますか」とだけ聞く。計画や技術の選択は、今やると決まってから考える。「〜して」と明確に頼まれたら、着手するかは聞き直さない。

今は着手しないと決まったら、利用者の言葉、分かっている事実や根拠、困る人を `backlog` の Issue に残し、URL を返す。不明なことは未確認とし、解決策は書かない。既に同じ要望が `backlog` にあれば、新しい Issue を立てず、その Issue を使う。探すときは `gh issue list --label backlog --state open --limit 500 --json number,title` の題名で絞り、似た Issue だけ本文を読む。着手する場合は必要な内容を書き足し、`backlog` ラベルを外して作業に合う type にする。

- 作業時間が 4 時間以内で閉じるなら Task（単独タスク）にする。1 時間未満の作業は、依存関係の近い次のストーリーと束ねる。束ねる相手が無ければ、単独タスクにしてよい。1 時間と 4 時間は仮の値とする。窓口が coordinator としてワーカーを起動する。
- 4 時間を超え、利用者が使える変化が 1 つなら Epic（type: Feature）にする。困りごとと確認した事実だけを書き、[Epic の親を起こす](#epic-の親を起こす)手順で親に渡す。親は Run を作って id を Issue に記録し、目的・完了の状態・計画は調べてから書く。
- 着手が決まり、利用者が使える変化が 1 つなのに、作業時間が 4 時間に収まるかが依頼から分からないときは、大きさを利用者に聞き直さず、Epic にして親に渡す。親は調べた結果 4 時間以内と分かれば、Task に書き換えて自分で coordinator を務める（S3）。大きさは調べないと分からず、利用者に聞くと答えが返るまで着手が止まるから。
- 複数の Epic にまたがるならマイルストーン Issue（type なし）を立て、利用者の言葉と成功の条件を利用者と合意する。成功の条件に向かう最小の変化を最初の Epic として sub-issue にし、同じ手順で親に渡す。残りの候補は、分かった時点で `backlog` の sub-issue にする。

## Epic の親を起こす

窓口は、自分の Run から親を起こす。親は S3 の手順 2 で自分の Epic の Run を作り、coordinator になる。窓口は Epic の Run を作らない。窓口が作った Run で親を起こすと、親はその Run の worker になり、その Run の coordinator になれない（`worker_cannot_coordinate_own_run`）。親は利用者と直接話すので、`--keep-open` でセッションを残す。

worktree は、`--agent` と `--prompt` を付けずに作る。付けると、親が窓口の Run の worker にならず、窓口が `worker-list` で親の生死を確かめられない。

```sh
orca worktree create --name <番号>-epic-<slug> --issue <番号> --no-parent --json
orca orchestration run-create --objective "<owner>/<repo>#<番号> の親を起こす" --json
gh issue comment <番号> --body-file <spec の一時ファイル>
orca orchestration worker-start --run <窓口の Run の id> --spec-file <spec の一時ファイル> \
  --worktree path:<worktree の絶対パス> --agent <エージェント> --model <モデル> --effort high --keep-open
```

spec は、Epic の番号と、このスキルの親の手順（上の「Epic の親が読む節」）を読むことを書く。ワーカーを起動する前に、spec の全文を Epic にコメントする。窓口の Run の id は本文に書かない。親が S3 の手順 2 で Epic の Run を作り、本文に Run の id を書く。

親が子を待つか、計画の承認を待ってターンを終えたときに届く `stopReason`: `finished` の escalation は、窓口の確認（1）の立て直しと同じく、対応しない。`exited`・`lost` は対応する。

## 単独タスクのワーカーを起動する

何ができたら終わりかを Task Issue に書く。結果を左右する情報が依頼から分からないときだけ、起動前に一度に聞く。例えば README のリンク修正なら「README のリンクを開くと対象のガイドが表示される」と書けるので、確認を挟まず任せる。

単独タスクごとに `run-create` で Run を作り、Run の id を Task Issue の本文に書く。objective は `<owner>/<repo>#<番号> ` で始める。窓口の確認（1）が、GitHub を読まずに Issue と Run を対応づけるため。Run はリポジトリをまたいで 1 つの一覧に並ぶので、リポジトリも入れる。次に worktree、Orca の Task、ワーカーの順に作る。Orca の Task の spec には[共通の型](references/spec.md)を使い、報告先を窓口にする。ワーカーを起動する前に、spec の全文を Task Issue にコメントする。

```sh
orca orchestration run-create --objective "<owner>/<repo>#<番号> <作業の目的>" --json
orca worktree create --name <番号>-<slug> --issue <番号> --no-parent --json
orca orchestration task-create --run <Run の id> --spec-file <spec の一時ファイル> --json
gh issue comment <番号> --body-file <spec の一時ファイル>
orca orchestration worker-start --run <Run の id> --task <Task の id> \
  --worktree path:<worktree の絶対パス> --agent <エージェント> --model <モデル> --effort <effort>
```

起動したことと Task Issue の URL を利用者に返す。ワーカーとのやり取りは窓口が受ける。

# S9: 単独タスクの coordinator として対応する

通知が届いたら、Task Issue の本文とコメントを読み、同じ作業への通知かを確かめる。新しい Run を作っても以前の Run の通知は届くので、`orca orchestration check --terminal run:<Run の id>` で通知が届いた Run の受信箱を読む。`reply` と `send` にも、その Run の id を `--run` で指定する。

## ワーカーから質問が来たとき

Issue と利用者の決定から答えられるなら、利用者に聞き直さない。目的の変更や `hold-merge` の PR の承認など、利用者にしか決められないことは、判断に必要な中身・選択肢・おすすめをその場に書いて聞く。利用者の答えを待っている間はまだ `reply` しない。答えが決まったら、同じ全文を Task Issue にコメントしてから `reply` する。

最小の 1 本まで絞っても作業時間が 4 時間に収まらないとワーカーから `ask` が来たら、単独タスクを Epic に引き継ぐ。新しい GitHub Issue や子は立てず、元の Issue を使う。

1. 元のワーカーが済ませた範囲と、元の Run の id を同じ Issue にコメントする。元のワーカーには、単独タスクの実装を続けず、Issue を閉じないことを伝える。返信に送る本文だけを別のコメントに書き、そのまま `reply` の本文に使う。
2. Issue の type を Task から Feature に変え、利用者が確認できる完了の状態と、調査を受けて見直せる計画案を本文に書く。本文の元の Run の id は消す（元の Run の id は手順 1 のコメントに残っている）。Epic の Run の id は、親が S3 で書く。親が書く前に止まっても、立て直した親が元の単独タスクの Run を Epic の Run と取り違えないため。元の質問で分かった事実と、利用者と合意済みの範囲は引き継ぐ。
3. [Epic の親を起こす](#epic-の親を起こす)手順で、別の worktree を作って親を起こす。親に送る spec は同じ Issue にコメントする。親には Epic の番号と、このスキルの親の手順を読むことを伝える。

Epic へ引き継いだ後、元の Run の終了通知を受けても単独タスクを起こし直さない。元のワーカーが終了し、下の片付けの条件がすべてそろったことを確認できた場合にだけ、元の worktree を消す。未反映の変更があれば worktree を残し、パスと残りを Epic の親に引き継ぐ。

## ワーカーから終了の通知が来たとき

Epic に引き継いでいない単独タスクでは、`worker_done` が `succeeded` でも、それだけで完了としない。Task Issue が閉じていて報告コメントがあることを読み、報告にある PR を `gh pr view <番号> --json state,mergedAt,headRefOid` で確かめる。Issue が開いている、報告が無い、またはマージが必要な PR が未マージなら、worktree を消さず、完了とも報告しない。理由と残りを利用者に伝えるか、Task Issue に続きをコメントし、同じ全文を `send` でワーカーに送る。失敗の通知なら、同じ Task を起こし直すか、新しい Task にするかを決める。

片付ける worktree は、`orca worktree list --json` で Issue と対応する絶対パスを確認する。以下のすべてがそろったときだけ片付ける。

- `git -C "<worktree の絶対パス>" status --porcelain` に何も出ない。
- `git -C "<worktree の絶対パス>" rev-list --count '@{upstream}..HEAD'` が 0 で、push 済みと確認できる。マージ後に upstream が消えていれば、worktree の `HEAD` がマージ済み PR の `headRefOid` と一致するかを確認する。PR がなくリポジトリを変更しなかった作業では、代わりに `origin/main..HEAD` が空かを確認する。
- マージが必要な PR の state が `MERGED` である。

```sh
orca worktree rm --worktree "path:<worktree の絶対パス>" --delete-branch
```

一つでも確かめられなければ、`--force` は使わず、残した理由を利用者に伝える。片付けたら、利用者ができるようになったことと、残りがあれば開いている Issue の URL を報告する。
