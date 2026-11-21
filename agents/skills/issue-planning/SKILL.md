---
name: issue-planning
description: 窓口（デフォルトブランチのセッション）が、次の着手を決める、利用者の依頼を backlog・単独タスク・Epic・マイルストーン Issue に振り分ける、単独タスクのワーカーの質問や終了通知に対応するときに読む。止まった Issue と報告漏れを確かめ、立て直す手順も持つ。Issue の計画や進行に関係しない質問、リポジトリや設定の調査、worktree 一覧の表示だけなら読まない。Epic の親は渡された指示に沿って該当する節を読み、ワーカーはこのスキルでなく渡された spec を読む。Orca の進行管理コマンドは `orchestration`、worktree と terminal の操作は `orca-cli` を読む。
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

次に何に着手するかを決める前（利用者に「次は？」と聞かれたとき、Epic や単独タスクが閉じたとき）に、下の 5 つを毎回確かめる。見つけたものに対応してから、次の候補を返す。

## 1. 止まった Epic

開いている Epic（type: Feature）のうち、開いている子が無いもの、または子が答えを待っているものを探す。

```sh
gh issue list --type Feature --state open --limit 200 \
  --json number,title,body,comments,subIssues,subIssuesSummary
```

候補ごとに、親のセッションが生きているかを Orca で確かめる。Epic の worktree は Epic の Issue に紐づいている。親の worker は Epic の Run に属するので、Epic の本文にある Run の id を `--run` に渡す（渡さないと、今の端末に紐づいた Run の worker だけが返り、別の Epic の親が「無い」ように見える）。

```sh
orca worktree list --json | jq '.result.worktrees[] | select(.linkedIssue == <Epic の番号>) | {path, identity: .identity.key}'
orca orchestration worker-list --run <Run の id> --json | jq '.result.workers[] | select(.workspace | endswith("<その path>"))'
```

同じ Issue に単独タスクから引き継いだ worktree も残っていれば、`displayName` が `<番号>-epic-` で始まる方を親の worktree として選ぶ。

`worker-list` は 1 回に最大 100 件を返す。`nextCursor` が返ったら、続きも読んでから「worker が無い」と判断する。

- `liveness` が `live` の親は、次の子を立てる途中か、子の質問を処理中。手を出さない。二重に起こすと、2 つの親が同じ Epic を進める
- `exited`・`lost` の親は、止まっている。立て直す
- `unverifiable` の親と、worker が見つからない Epic は、止まったと決められない（親がまだ動いているかもしれない）。立て直さず、Epic にその旨をコメントし、返事で利用者に確かめる
- 子が答えを待っている Epic では、子 Issue の最後のコメントが答えの無い質問かを読む。親が `live` なら待たせてよく、`exited`・`lost` なら立て直す

立て直し方（親の worktree は Epic に紐づいたまま残っている。`worktree create` は使えない）:

1. Epic の本文にある Run の id を取り、Epic に、立て直すことと理由をコメントする。コメントを先に書く。新しい親が Issue から続けられるようにするため
2. `orca orchestration run-use --id <Run の id>` で Run を再開する
3. `orca orchestration task-create --spec "<Epic #N の親のセッション（coordinator）を担当する。前の親のセッションは止まった。Epic の本文と Issue のコメントから続ける。>"` で Task を作る
4. `orca orchestration worker-start --task <task id> --worktree path:<Epic の worktree の絶対パス> --agent <エージェント> --model <モデル> --keep-open` で新しい親を起こす。worktree の選択子は `issue:<番号>` でなく `path:` にする。ほかのリポジトリに同じ番号の Issue に紐づいた worktree があると、`issue:` は拒否される

## 2. coordinator が居なくなった単独タスク

開いている単独タスク（type: Task で親の無いもの）で、ワーカーが `worker_done` を出さずに止まっているものを探す。

```sh
gh issue list --type Task --state open --limit 200 --json number,title,body,parent,comments \
  | jq '[.[] | select(.parent == null)]'
```

本文の Run の id で `run-use --id` を実行し、Issue のコメントで途中の状態を読んでから、同じ Task を起動し直すか新しい Task を立てて起動する。起こす前に、Task Issue にコメントする。

## 3. 報告の無い閉じた子 Issue

閉じた子 Issue には、片付いたこと・片付かなかったこと・計画に影響する発見の報告コメントがある。無いものは、coordinator が子の完了の中身を知らない。

```sh
gh issue list --type Task --state closed --limit 200 --json number,title,parent,comments,closedAt \
  | jq '[.[] | select(.parent != null) | select(([.comments[].body | select(test("片付いたこと"))] | length) == 0)]'
```

見つけた Issue は、リンクされた PR と Issue の実際の状態から、報告を同じ Issue に書き足す。ほかの Issue は変えない。

## 4. 開いた Epic の無いマイルストーン Issue

type の無い開いた Issue で、sub-issue を持つものがマイルストーン Issue。開いた Epic が 1 つも無ければ、次の着手待ち。

```sh
gh issue list --state open --limit 200 --json number,title,issueType,subIssues,subIssuesSummary \
  | jq '[.[] | select(.issueType == null and .subIssuesSummary.total > 0)]'
```

Epic を勝手に立てない。sub-issue の `backlog` の候補を、おすすめと理由を付けて返す。成功の条件を満たしているなら、利用者に確かめてから閉じる。

## 5. `backlog` の全件

```sh
gh issue list --label backlog --state open --limit 500 --json number,title,body,createdAt
```

`--limit` を必ず付ける。既定は 30 件で、31 件目以降を見落とす。本文が指す事実（別の Issue・不具合・ファイル）がもう当てはまらないものは、確かめた理由をコメントしてから閉じる。ほかの `backlog` は閉じない。

## 返事

立て直したこと・書き足したこと・閉じたことを先に書く。そのあと、次の着手の候補を、おすすめとその理由を付けて返す。親が `live` で手を出さなかった Epic があれば、その旨も 1 行で書く。

# S2: 依頼を振り分ける

「〜したい」だけで着手の意思が分からなければ、最初は「今着手しますか」とだけ聞く。計画や技術の選択は、今やると決まってから考える。「〜して」と明確に頼まれたら、着手するかは聞き直さない。

今は着手しないと決まったら、利用者の言葉、分かっている事実や根拠、困る人を `backlog` の Issue に残し、URL を返す。不明なことは未確認とし、解決策は書かない。既に同じ要望が `backlog` にあれば、新しい Issue を立てず、その Issue を使う。着手する場合は必要な内容を書き足し、`backlog` ラベルを外して作業に合う type にする。

- 作業時間が 4 時間以内で閉じるなら Task（単独タスク）にする。1 時間未満の作業は、依存関係の近い次のストーリーと束ねる。1 時間と 4 時間は仮の値とする。窓口が coordinator としてワーカーを起動する。
- 4 時間を超え、利用者が使える変化が 1 つなら Epic（type: Feature）にする。困りごとと確認した事実だけを書き、`orca worktree create --name <番号>-epic-<slug> --issue <番号> --no-parent --agent <エージェント> --prompt <引き継ぎ>` で親に渡す。引き継ぎに Epic の番号とこのスキルの親の手順を読むことを書く。親は Run を作って id を Issue に記録し、目的・完了の状態・計画は調べてから書く。
- 複数の Epic にまたがるならマイルストーン Issue（type なし）を立て、利用者の言葉と成功の条件を利用者と合意する。成功の条件に向かう最小の変化を最初の Epic として sub-issue にし、親に渡す。残りの候補は、分かった時点で `backlog` の sub-issue にする。

## 単独タスクのワーカーを起動する

何ができたら終わりかを Task Issue に書く。結果を左右する情報が依頼から分からないときだけ、起動前に一度に聞く。例えば README のリンク修正なら「README のリンクを開くと対象のガイドが表示される」と書けるので、確認を挟まず任せる。

単独タスクごとに `run-create` で Run を作り、Run の id を Task Issue の本文に書く。次に worktree、Orca の Task、ワーカーの順に作る。Orca の Task の spec には[共通の型](references/spec.md)を使い、報告先を窓口にする。ワーカーを起動する前に、spec の全文を Task Issue にコメントする。

```sh
orca orchestration run-create --objective "<作業の目的>" --json
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
2. Issue の type を Task から Feature に変え、利用者が確認できる完了の状態と、調査を受けて見直せる計画案を本文に書く。元の質問で分かった事実と、利用者と合意済みの範囲は引き継ぐ。
3. Epic の新しい Run を作り、本文の Run の id を置き換える。`orca worktree create --name <番号>-epic-<slug> --issue <番号> --no-parent` で別の worktree を作る。親に送る spec を同じ Issue にコメントしてから、新しい Run と `path:<worktree の絶対パス>` を指定し、`worker-start --keep-open` で Epic の親を起こす。親には Epic の番号と、このスキルの親の手順を読むことを伝える。親は利用者との相談を受けるので、セッションを残す。

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
