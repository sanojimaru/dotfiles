#!/usr/bin/env node
// development のガードレール: push する中身に mise run check が通ったかを、pre-push が数ミリ秒で確かめる。
//
// gh stack は push のあいだ、全 worktree が共有するロックを持ち続け、待つ側は 5 秒で諦める。pre-push で
// 検査そのものを走らせると、そのあいだ別の worktree の gh stack が「another process is currently
// editing the stack」で止まった（spikestudio/engineering-standards#174）。そこで検査はロックの外の
// mise run check で走らせ、通った作業ツリーのハッシュを worktree ごとの git ディレクトリに残す。
// pre-push は push する ref の中身がそのハッシュと同じか、同じ中身の commit の祖先かだけを見る。
//
//   node scripts/guardrail-check.mjs run <command> ...   検査を走らせ、通ったら作業ツリーを記録する（mise run check）
//   node scripts/guardrail-check.mjs verify --refs       stdin の ref に通った記録が無ければ失敗する（pre-push）
//   node scripts/guardrail-check.mjs verify              HEAD に通った記録が無ければ失敗する（手で確かめる）
//
// 作業ツリーのハッシュは、未コミットの変更を含めたツリーのハッシュ。検査してからコミットしても、
// そのコミットのツリーと一致する。追跡していないファイル（.gitignore の対象を除く）があるときは記録せず、
// 失敗で終わる。
// 依存パッケージを持たない（どのスタックでも node だけで動かすため）。
import { execFileSync, spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { resolve } from "node:path";

const PASSED = "guardrail-check-passed";

function git(args, env = process.env) {
  return execFileSync("git", args, {
    encoding: "utf8",
    env,
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

/** worktree ごとの git ディレクトリの中のパス（worktree どうしで記録を混ぜないため）。 */
function gitPath(name) {
  return resolve(git(["rev-parse", "--git-path", name]));
}

/**
 * 追跡していないファイル（.gitignore の対象を除く）があるか。名前が空白だけのファイルも見落とさないように、
 * NUL 区切りで読み、trim しない。
 */
function hasUntracked() {
  return (
    execFileSync("git", ["ls-files", "-z", "--others", "--exclude-standard"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }) !== ""
  );
}

/**
 * 作業ツリーの中身のハッシュ。本物の index には触れず、写しに git add -u してから書き出す。
 * git add は中身を blob としてオブジェクト DB に書くので、追跡していないファイル（秘密情報のこともある）は
 * 加えない（#208）。追跡していないファイルの有無は run が別に確かめる。
 */
function worktreeTree() {
  const index = gitPath("index");
  const temp = gitPath(`guardrail-check-index-${process.pid}`);
  try {
    // 写しから始めると、変わっていないファイルを読み直さずに済む。
    if (existsSync(index)) copyFileSync(index, temp);
    const env = { ...process.env, GIT_INDEX_FILE: temp };
    git(["add", "-u"], env);
    return git(["write-tree"], env);
  } finally {
    rmSync(temp, { force: true });
  }
}

function run(command) {
  const passed = gitPath(PASSED);
  // 前の記録は先に消す。同じ中身の検査をやり直して落ちた・途中で止めたときに、古い記録で push が通らないように。
  rmSync(passed, { force: true });
  // 始めのツリーはこのプロセスだけが持つ。同じ worktree で検査が重なっても、別の検査のツリーを記録しない。
  const before = worktreeTree();
  // 追跡していないファイルは git ls-files で対象を選ぶ検査には見えず、git add すると記録するツリーが変わる。
  // 検査が見ていない中身を通ったと記録しないように、あれば記録しない。
  const untracked = hasUntracked();
  const [file, ...args] = command;
  const result = spawnSync(file, args, { stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) return result.status ?? 1;
  // 記録しないときも失敗で終わる。終了コードだけを見る呼び出し側（mise run check && git push、CI）が
  // 成功と取り違え、次の push で初めて止まらないように（#207）。
  if (untracked) {
    console.error(
      "guardrail-check: 検査は通りましたが、追跡していないファイルがあるので、通ったとは記録しません。git add するか .gitignore に入れてから、mise run check を走らせ直してください。",
    );
    return 1;
  }
  if (hasUntracked() || worktreeTree() !== before) {
    // 検査の途中で書き換えた・作ったファイルは、検査が見た中身と違うかもしれないので、通ったとは記録しない。
    console.error(
      "guardrail-check: 検査は通りましたが、検査の途中で作業ツリーが変わったので、通ったとは記録しません。push の前に mise run check をもう一度走らせてください。",
    );
    return 1;
  }
  writeFileSync(passed, `${before}\n`);
  return 0;
}

const ZERO = /^0+$/;

/**
 * pre-push の stdin（`<local ref> <local sha> <remote ref> <remote sha>` の行）から、push する ref と object を読む。
 * local ref には空白を含む式（`HEAD^{/fix typo}` など）も来るので、後ろの 3 つを切り出した残りを local ref とする。
 * リモートが最新で送るものが無いとき、git は行を渡さないので、空のまま返す。
 */
function pushedRefs() {
  return readFileSync(0, "utf8")
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => {
      const fields = line.split(" ");
      const [object, remote] = fields.slice(-3, -1);
      return { ref: fields.slice(0, -3).join(" "), object, remote };
    })
    .filter(({ object }) => !ZERO.test(object)); // 削除は中身を送らない
}

/** object のツリー。注釈付きタグは指す commit まで剥がす。ツリーを持たない object は null。 */
function treeOf(object) {
  try {
    return git(["rev-parse", "--verify", "--quiet", `${object}^{tree}`]);
  } catch {
    return null;
  }
}

function isAncestor(object, commit) {
  return (
    spawnSync("git", ["merge-base", "--is-ancestor", object, commit], {
      stdio: "ignore",
    }).status === 0
  );
}

/**
 * push する ref ごとに、中身が記録と同じか、ブランチへの push で記録と同じ中身の commit の祖先なら通す。
 * HEAD ではなく ref を見るのは、HEAD と違う ref（別の commit に付けたタグなど）を検査無しで送らないため（#206）。
 * 祖先を通すのは、gh stack push が最上段の層と一緒に下の層を送るから。タグは公開の起点になりうるので、
 * 祖先でも中身が記録と同じでなければ通さない。--refs が無い（手で走らせた）ときは HEAD を見る。
 */
function verify(fromStdin) {
  const passed = gitPath(PASSED);
  const recorded = existsSync(passed)
    ? readFileSync(passed, "utf8").trim()
    : null;
  const refs = fromStdin
    ? pushedRefs()
    : [{ ref: "HEAD", object: "HEAD", remote: "refs/heads/HEAD" }];
  const anchors = [...refs.map(({ object }) => object), "HEAD"].filter(
    (object) => recorded !== null && treeOf(object) === recorded,
  );
  const unverified = refs.filter(
    ({ object, remote }) =>
      !anchors.includes(object) &&
      !(
        remote.startsWith("refs/heads/") &&
        anchors.some((anchor) => isAncestor(object, anchor))
      ),
  );
  if (unverified.length === 0) return 0;
  console.error(
    [
      `guardrail-check: push する ${unverified.map(({ ref }) => ref).join(", ")} の中身に、mise run check が通った記録がありません。`,
      "pre-push は検査を走らせず、記録だけを確かめます（検査のあいだ gh stack のロックを持ち続けないため）。",
      "その ref の commit をチェックアウトして mise run check を走らせ、通ったら gh stack push（または git push）でもう一度 push してください。",
      "記録は worktree ごとに 1 つなので、中身の違うタグは 1 つずつ検査して push してください。",
      "gh stack sync・rebase・amend で中身が変わったときも、同じように走らせ直します。",
    ].join("\n"),
  );
  return 1;
}

const [command, ...rest] = process.argv.slice(2);
if (command === "run" && rest.length > 0) process.exitCode = run(rest);
else if (command === "verify" && rest.length === 0)
  process.exitCode = verify(false);
else if (command === "verify" && rest.join(" ") === "--refs")
  process.exitCode = verify(true);
else {
  console.error(
    "使い方: node scripts/guardrail-check.mjs run <command> ... | verify [--refs]",
  );
  process.exitCode = 2;
}
