---
name: issue-planning
description: 窓口（デフォルトブランチのセッション）が、次に何に着手するかを決める前、または利用者の依頼を Issue にする前に読む。開いたまま誰も動かしていない Issue（親のセッションが止まった Epic、coordinator が居なくなった単独タスク、報告のコメントが無い閉じた子 Issue、開いた Epic の無いマイルストーン Issue、`backlog` の全件）を `gh` で確かめ、見つけたものを立て直す・書き足す・閉じる手順を持つ。Epic の親は、渡された指示に従って該当する節を読む。質問への回答、調べもの、ファイルの変更、ワーカーとして渡された作業の中では読まない。Orca のコマンドそのもの（`worker-start`・`ask`・`reply` など）は `orchestration`、worktree と terminal の操作は `orca-cli` を読む。
---

# Epic の親が読む節

Epic の親は、担当する場面に対応する参照を読む。会話の途中で別の場面に移ったときや、セッションを立て直したときも、この一覧から読み直す。

- [S3: Epic の計画を書く](references/epic-s3.md)
- [S4: 子を起動する](references/epic-s4.md)
- [S5: ワーカーからの質問や停止の通知に対応する](references/epic-s5.md)
- [S6: ワーカーの報告を実際の状態と照らし合わせる](references/epic-s6.md)
- [S7: Epic を閉じて利用者に報告する](references/epic-s7.md)
- [S8: 止まった親のセッションを再開する](references/epic-s8.md)

窓口と親は、ワーカーを起動する spec に[共通の型](references/spec.md)を使う。ワーカー自身は、このスキルではなく渡された spec を読む。

# 窓口の着手前の確認

窓口はファイルを変えない。Issue を読み、コメントを書き、止まった親のセッションを `worker-start` で起こすだけにする。変更は、起動したワーカーにさせる。

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
