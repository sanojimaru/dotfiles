# S6: ワーカーの報告を実際の状態と照らし合わせる

親が、報告と Issue・PR・worktree の状態を照合し、片付けと次の着手を判断する。`worker_done` の通知を受けたときに行う。通知は完了の合図で、完了の証拠は Issue と PR の状態にある。

## 照合

1. 子 Issue の報告コメント（片付いたこと・片付かなかったこと・計画に影響する発見）を読む。
2. 実際の状態と照らす。子 Issue が閉じている。マージが要る PR は `gh pr view <番号> --json state,mergedAt` で `MERGED`。報告と食い違えば、片付けず、子 Issue にコメントして続けさせるか、利用者に伝える。

`worker_done` の outcome が `failed` なら、完了として扱わない。子 Issue のコメントから原因を読み、同じ Task を起動し直すか、新しい子を立てるかを決める。この決定は親が行い、利用者には聞かない（利用者に聞くのは、目的や完了の状態に関わる選択だけ）。決めた内容を子 Issue か Epic にコメントしてから、起動し直す（終わったワーカーには `orca orchestration send --to dispatch:<id>` で続きを送れる）。

## 片付け

次の 3 つがそろったときだけ、子の worktree を片付ける。

- `git -C "<worktree の絶対パス>" status --porcelain` に何も出ない。
- push 済みで、`git -C "<worktree の絶対パス>" rev-list --count '@{upstream}..HEAD'` が 0。マージ後に upstream が消えていれば、`HEAD` がマージ済み PR の `headRefOid` と一致するかを見る。
- マージが要る PR の state が `MERGED` で、子 Issue が閉じている。PR を作らず、リポジトリを変えなかった子（調べものなど）は、代わりに `git -C "<worktree の絶対パス>" rev-list --count origin/main..HEAD` が 0 であることを確かめる。

```sh
orca worktree rm --worktree "path:<worktree の絶対パス>" --delete-branch
```

`issue:` でなく `path:` で指定する。ほかのリポジトリに同じ番号の Issue があると、`issue:` は取り違える。1 つでも確かめられなければ、`--force` を使わず、消さずに残した理由を利用者に伝える。

## 計画の見直しと次の着手

- 報告の「計画に影響する発見」と「片付かなかったこと」を読む。Epic の完了の状態の確認項目に紐づく作業は、Epic の計画に足す（依存グラフも同じ編集で直す）。紐づかない作業は、子が backlog の Issue にしていなければ、backlog の Issue にする。紐づかない作業を計画に積むと、Epic が膨らむ。
- Epic に、観測を 1 行コメントする（何が閉じたか、足したノード）。利用者には知らせない。進み具合は Epic の観測コメントにあり、子が閉じるたびに利用者を呼ぶと、判断が要る通知が埋もれる。
- 完了の状態を満たしていれば [S7](epic-s7.md) へ進む。満たしていなければ、先行がそろった次のノードを [S4](epic-s4.md) の手順で起動する。
