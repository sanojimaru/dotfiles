# S4: 子を起動する

親が、先行する作業がそろった子を起動する。S3 の合意の直後と、S6 の見直しの後に行う。

## 起動してよいノード

依存グラフで、先行が無いノード、または先行がすべて閉じているノードだけを起動する。先行の条件は「先行の子 Issue が閉じていること」。先行が PR を伴う作業なら、後続が必要とする変更が main に入っているように、その PR が `MERGED` であることも確かめる。どの先行でも、閉じていることに加え、後続が必要とする成果（マージされた変更・調べた結果・反映された設定）が実際に使えることを確かめる。ワーカーは受け入れ条件を片付いた範囲に狭めて閉じることがあるので、閉じていても前提がそろったとは限らない。

次のノードは起動しない。

- 先行が閉じていないノード。Issue も立てない。後で必要になった時点の状況で書くほうが、正確だから。
- 既に子 Issue があるノード。閉じた子（完了済み）も、開いている子も、新しい Issue を立てない。worker が `live` の子を起動し直すと、2 つのセッションが同じ作業を進めてしまう。起動の前に、Epic の sub-issue と `orca orchestration worker-list --run <Run の id>` で確かめる。子 Issue が開いているのに worker が居ない子（`worker-start` が失敗したとき、worktree を作った直後に親が止まったときなど）は、その Issue と、あれば既存の worktree を使って、同じ Task を起動し直す。

Epic の目的と独立した作業（この Epic が無くても同じ作業が要るもの。例: CI の不具合・flaky なテスト・アカウントや上限の設定）は、今着手が要らなければ `backlog` の Issue にする。子の着手にその作業が要るときだけ、Epic の子として依存グラフに先行として描き、ほかの子と同じように起動する。別の Run や別の coordinator に分けると、親の立て直しや窓口の確認から漏れるから。

同じファイルやインターフェースを触るのに、依存の線が無いノードがあれば、起動の前に Epic の本文のグラフへ線を足し、先行にしたほうだけを起動する。同時に動かすと、変更がぶつかるから。

## 起動の手順

起動するノードごとに、子 Issue（type: Task、親は Epic）を立て、worktree、Orca の Task、worker の順に作る。子 Issue の受け入れ条件は、ストーリー（「〜として〜できる」）ごとに、観測できる確認項目を置く。`--deps` は使わない（計画を直すたびに Task を作り直すことになる）。`worker-start` に `--issue` は無いので、worktree を `path:` で指定する。

```sh
gh issue create --type Task --parent <Epic の番号> --title "<ストーリー>" --body-file <受け入れ条件のファイル>
orca worktree create --name <Epic の番号>.<子の番号>-<slug> --issue <子の番号> --parent-worktree active --json
orca orchestration task-create --run <Run の id> --spec-file <spec の一時ファイル> --json
gh issue comment <子の番号> --body-file <spec の一時ファイル>
orca orchestration worker-start --run <Run の id> --task <Task の id> \
  --worktree path:<worktree の絶対パス> --agent <エージェント> --model <モデル> --effort <effort>
```

エージェント・モデル・effort は、作業 Issue なら Opus か Sol の `--effort medium` にする。ごく小さい修正（lint の指摘直し・リネームなど）は、Sonnet の medium か Sol の low にしてよい。Fable と Astra は、利用者が指定したときだけ使う。

Task の spec には[共通の型](spec.md)を使い、報告先を Epic の親にする。作業時間の目安は 4 時間を入れる。worker を起動する前に、spec の全文を子 Issue にコメントする。

`worker-start` が失敗したら、同じ引数で繰り返さず、エラーを読んで原因を直す。
