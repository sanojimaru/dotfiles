# S8: 止まった親のセッションを再開する

親が、既存の Orca Run を再開し、GitHub の状態と照合して作業を引き継ぐ。窓口が、前の親が止まった Epic に新しい親を起こしたときに行う。前の親が残した状態は、Epic の本文・コメントと子 Issue にある。

## 手順

1. Epic の本文にある Run の id で Run を再開する。窓口が worker として起こした親でも、その Run の worker でなければ `run-use` できる。窓口が Run を束ねていても、引き継げる。

   ```sh
   orca orchestration run-use --id <Run の id>
   ```

2. 状態を組み立てる。GitHub の API の上限は全リポジトリで共有しているので、手元の Orca を先に読み、コメントは必要な子だけ読む。
   - 子ごとの worker の状態: `orca orchestration worker-list --run <Run の id> --json`。1 回に最大 100 件で、`nextCursor` が返ったら続きも読む。
   - 答えの無い質問と、受けていない終了の通知: `orca orchestration check --run <Run の id>` で、前の親が読んでいない `question`・`worker_done` を受ける（読んだ通知は既読になる）。
   - Epic の本文・コメントと子の番号・状態: `gh issue view <Epic の番号> --json body,comments,subIssues`。
   - 子 Issue のコメントは、worker が `exited`・`lost` の子と、閉じているのに Epic の観測が無い子だけ読む。
3. 子ごとに対応する。
   - worker が `live` の子: 何も起動しない。前の親が起動した worker が動いていて、新しく起動すると 2 つのセッションが同じ作業を進める。
   - worker が `exited` または `lost` の子で、答えの無い質問がある: 答えを子 Issue にコメントしてから、`orca orchestration send --to dispatch:<id>` で元の worker に続けさせる。送れなかったときだけ、同じ Task を既存の worktree で起動し直す。

     ```sh
     orca orchestration worker-start --run <Run の id> --task <Task の id> \
       --worktree path:<子の worktree の絶対パス> --agent <エージェント> --model <モデル> --effort <effort>
     ```

     `issue:` でなく `path:` で指定する。ほかのリポジトリに同じ番号の Issue があると、`issue:` は拒否される。
   - 答えの無い質問に答えるときも、[S5](epic-s5.md) の判断に従う。利用者にしか決められない質問（`hold-merge` の PR のマージの承認など）は、利用者の答えが作業 Issue のコメントに記録されていなければ、利用者に聞いてから子を続けさせる。
   - 閉じている子: [S6](epic-s6.md) の照合に入る。
4. 状態を確かめたことと、何を起動した（しなかった）かを、Epic にコメントする。完了の状態に近づいていれば S4・S7 に進む。

## Epic の本文に Run の id が無いとき

`orca orchestration run-create --objective "#<Epic の番号> <Epic の目的>" --json` で新しい Run を作り、返った id を Epic の本文に「Run id: `<id>`」の形で書く（本文のほかの部分は消さない）。そのうえで、上の 2・3 の手順で、Issue のコメントと worker の状態から状態を組み立てる。生きている worker の子は、起動し直さない。
