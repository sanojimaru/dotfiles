#!/usr/bin/env node
// development のガードレール: 規則の一覧と判定器。
//
// 規則は、導入先が外してはいけない設定（必須、required）と、外すなら理由を残す設定（任意、optional）を
// 並べる。必須の違反があれば終了コード 1 で落とす。任意の違反は警告にとどめ、導入先が理由と一緒に
// .guardrail/exceptions.json に書いた規則は警告も出さない。必須の規則は、そこに書いても外れない。
// CI（.github/workflows/guardrail.yml）も、導入先にあるこのファイルのコピーを呼ぶ。導入先でこのファイルを書き換えると、
// 規則 harness-files が配布版の一覧と比べて落とす。
//
//   node scripts/guardrail-rules.mjs               判定して、違反を出す（必須の違反があれば 1）
//   node scripts/guardrail-rules.mjs --json        判定の結果を JSON で出す（development の setup が読む）
//   node scripts/guardrail-rules.mjs --base <rev>  閾値を比べるマージ先を渡す（CI が PR のマージ先を渡す）。
//                                                  省くと、リモートのデフォルトブランチ（origin/HEAD）と比べる
//   node scripts/guardrail-rules.mjs --ci          判定に要る道具（Docker の Compose）が無ければ、判定を飛ばさずに
//                                                  落とす（CI の action が渡す）
//
// 依存パッケージを持たない（どのスタックでも node だけで動かし、CI でもインストール無しで呼ぶため）。
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const THRESHOLDS = ".guardrail/thresholds.json";
const EXCEPTIONS = ".guardrail/exceptions.json";
const FILES_MANIFEST = ".guardrail/files.tsv";
const CI = ".github/workflows/ci.yml";
const DIGEST = /@sha256:[0-9a-f]{64}$/;
const LOOPBACK = "127.0.0.1";
/**
 * 配布版の置き場所（このファイルの 1 つ上）。導入先の直下で動かすときは導入先の直下で、プラグインの
 * templates/common/files/ で動かすとそこになる。harness-files は、ここにある .guardrail/files.tsv と比べる。
 */
const DIST = fileURLToPath(new URL("..", import.meta.url));
/** 配る ci.yml の ci-required が待つジョブ。配布版の ci.yml と同じ（tools/development のテストが確かめる）。 */
const CI_JOBS = [
  "check",
  "prepare-check",
  "coverage",
  "diff-coverage",
  "coverage-thresholds",
  "check-scheduled",
  "guardrail-drift",
];
const DIFF_MINIMUM = 90;
/** カバレッジを測るスタックと、閾値を持つ種類（Go は分岐を測らない）。scripts/guardrail-coverage.mjs と同じ。 */
const COVERAGE_STACKS = [
  { stack: "go", metrics: ["total"] },
  { stack: "python", metrics: ["total", "branch"] },
  { stack: "typescript", metrics: ["total", "branch"] },
];

/**
 * 規則の一覧。id はエラーと例外の記録で規則を指す名前なので、一度決めたら変えない。
 * - level: required は必ず守らせ、外すと落とす。optional は外しても警告にとどめる。
 * - reason: なぜその設定が要るか（外すと何が起きるか）。
 * - expected: 満たすための設定。
 * - check: リポジトリの直下のパスと読んだ例外と引数（base）を受け取り、満たしていなければ外した内容を返す
 *   （満たせば undefined）。外したファイルが file と違うときは { message, file } を返す（CI の注釈がそのファイルを指す）。
 */
const RULES = [
  {
    id: "gitattributes-lf",
    level: "required",
    file: ".gitattributes",
    reason:
      "Windows の Git は既定で core.autocrlf=true なので、指定が無いとシェルスクリプトと mise のタスクファイルが " +
      "CRLF で展開され、`set -e\\r` のような文法エラーで検査そのものが動かなくなる。.guardrail/ の下の目印の" +
      "データも、CRLF だと Windows の手元で読めなくなる。",
    expected: [
      "*.sh text eol=lf",
      ".mise/tasks/** text eol=lf",
      ".guardrail/** text eol=lf",
    ],
    check: (root) => lfViolation(root),
  },
  {
    id: "coverage-thresholds",
    level: "required",
    file: THRESHOLDS,
    reason:
      "閾値が無いと、カバレッジの判定そのものが行われない。diff が無いか null だと PR の diff-coverage の" +
      "ジョブは報告だけになり、スタックの total・branch が無いと mise run check:full がそのスタックの下限を" +
      "判定しない。",
    expected: [
      '"diff": <0〜100 の数>',
      '"total": {"<スタック>": <0〜100 の数>}（.guardrail/answers/common.yml の stacks のうち go・python・typescript）',
      '"branch": {"<スタック>": <0〜100 の数>}（python・typescript）',
      "導入した直後で初回の計測の前は 0 を置く。main の CI の coverage-thresholds が引き上げ案を出したら、mise run check:full の後に mise run coverage:raise で上げて PR にする",
    ],
    check: (root) => thresholdsViolation(root),
  },
  {
    id: "coverage-thresholds-not-lowered",
    level: "required",
    file: THRESHOLDS,
    reason:
      "閾値はテストを足したぶんだけ CI が引き上げる値で、下げるとそのぶんのテストを消しても検査が通る。" +
      "例外の記録で任意の規則を外していても、マージ先より下げることは認めない（今より低い数字は認めない）。",
    expected: [
      "diff・total・branch の各値を、マージ先のブランチ（PR の base。手元では origin/HEAD との分岐点）の値以上にする",
      "マージ先に値が無いか 0 なら、0 を置いてよい（初回の計測の前）",
      "導入をやめたスタックの total・branch は、.guardrail/answers/common.yml の stacks から外せば消してよい",
    ],
    check: (root, _exceptions, options) => notLoweredViolation(root, options),
  },
  {
    id: "coverage-diff-minimum",
    level: "optional",
    file: THRESHOLDS,
    reason:
      `変更行のカバレッジの閾値（diff）が ${DIFF_MINIMUM} を下回ると、テストの通らない変更行が多く入っても、` +
      "PR の diff-coverage のジョブが落ちない（目安は Google Testing Blog「Code Coverage Best Practices」" +
      "（2020）の、変更ごとのカバレッジの下限 90%）。",
    expected: [`"diff": ${DIFF_MINIMUM} 以上`],
    check: (root) => diffMinimumViolation(root),
  },
  {
    id: "harness-files",
    level: "required",
    file: FILES_MANIFEST,
    reason:
      "ハーネスが持つファイル（検査のスクリプトとタスク）を書き換えると、手元の検査や CI の検査の中身が" +
      "導入先ごとに変わり、同じ水準で守れなくなる。変えたいときは engineering-standards に Issue を立てて" +
      "配布版を直す。",
    expected: [
      `${FILES_MANIFEST} で harness のファイルを、配布版と同じ中身にする（development:setup の apply で置き直す）`,
      "プロジェクトに要る変更は、そのファイルを読む別の設定（mise.toml・別の workflow など）に移す",
    ],
    check: (root) => harnessViolation(root),
  },
  {
    id: "ci-required-jobs",
    level: "required",
    file: CI,
    reason:
      "ruleset は ci-required を必須のチェックにする。検査のジョブを消すか ci-required の needs から外すと、" +
      "そのジョブが落ちても、無くても、ci-required が通ってマージできてしまう。",
    expected: [
      `${CI} に、ジョブ ${CI_JOBS.join("・")} と ci-required を置く`,
      `ci-required の needs に ${CI_JOBS.join("・")} を並べる`,
      "ci-required に if: always() を置く（待つジョブが落ちても skipped にせず、落ちたことを報告させる）",
    ],
    check: (root) => ciJobsViolation(root),
  },
  {
    id: "compose-image-digest",
    level: "required",
    file: "compose.yaml",
    reason:
      "digest で固定していない image: は、同じタグのまま中身が変わり、pull した時期によってローカルと CI で" +
      "別のイメージになる。",
    expected: [
      "compose ファイル（サブディレクトリのものも含む）で、build: の無いサービスの image: を <名前>:<タグ>@sha256:<digest> の形にする",
      "digest は docker buildx imagetools inspect <名前>:<タグ> で確かめられる",
    ],
    check: (root, _exceptions, options) =>
      composeViolation(root, options, {
        subject: "image の digest",
        find: unpinnedImages,
      }),
  },
  {
    id: "compose-ports-loopback",
    level: "required",
    file: "compose.yaml",
    reason:
      `${LOOPBACK} 以外への ports の公開は、同じネットワークの他の端末から DB などのサービスに届く。` +
      '"5432:5432" や "- 5432" はホストの全インターフェースに公開する。',
    expected: [
      `compose ファイル（サブディレクトリのものも含む）で、ports をホストの ${LOOPBACK} にだけ公開する（例: "${LOOPBACK}:5432:5432"）`,
    ],
    check: (root, _exceptions, options) =>
      composeViolation(root, options, {
        subject: "ports の公開先",
        find: exposedPorts,
        interpolate: true,
      }),
  },
  {
    id: "compose-version",
    level: "optional",
    file: "compose.yaml",
    reason:
      "最上位の version: は Compose の仕様で廃止され、書いても無視される。Compose は警告を出すだけで止まらないので、" +
      "残すと読み手がその版の書き方に従うと誤解する。",
    expected: [
      "compose ファイル（サブディレクトリのものも含む）から、最上位の version: の行を消す",
    ],
    check: (root) => composeVersionViolation(root),
  },
  {
    id: "exceptions-file",
    level: "required",
    file: EXCEPTIONS,
    reason:
      "例外の記録は、後から読む人が外したままでよいかを判断するためのもの。理由の無い記録や、形の誤り・" +
      "打ち間違いで、規則が黙って外れたり外れなかったりしないようにする。",
    expected: [
      '{"exceptions": [{"rule": "<任意の規則の id>", "reason": "<このプロジェクトで満たせない事情>"}]}',
    ],
    check: (_root, exceptions) =>
      exceptions.errors.length === 0
        ? undefined
        : exceptions.errors.join(" / "),
  },
];

/**
 * gitattributes-lf で、改行を LF に固定する対象の代表のパスと、追跡しているファイルを選ぶ pathspec。
 * git check-attr で、eol が lf に解決し、text が外されて（-text）いないことを確かめる。書いた行の有無でなく
 * 効いている指定で判定するので、後ろの行や入れ子の .gitattributes で取り消すと落ち、`* text=auto eol=lf` の
 * ように別の書き方で同じ効果を持つ導入先は通る。代表のパスは、まだ該当するファイルが無い導入先でも判定するため。
 */
const LF = {
  samples: [
    "x.sh",
    "dir/x.sh",
    ".mise/tasks/x",
    ".mise/tasks/dir/x",
    ".guardrail/x",
  ],
  tracked: ["*.sh", ".mise/tasks/", ".guardrail/"],
};

/** git を cwd で動かす。 */
function git(args, cwd) {
  return spawnSync("git", args, { cwd, encoding: "utf8" });
}

const failure = (result) =>
  `git が失敗した（git のリポジトリの中で実行する）: ${(result.stderr || String(result.error ?? "")).trim()}`;

/**
 * LF の代表のパスと追跡しているファイル（リポジトリの直下から見たパス）の text と eol の属性を
 * git check-attr で読む。利用者の全体の設定（core.attributesFile）は読まない。手元にだけある設定で通り、
 * CI で落ちることのないようにするため。
 */
function attributes(root) {
  const listed = git(["ls-files", "-z", "--", ...LF.tracked], root);
  if (listed.status !== 0) return { error: failure(listed) };
  const paths = [
    ...new Set([...LF.samples, ...listed.stdout.split("\0").filter(Boolean)]),
  ];
  const result = spawnSync(
    "git",
    [
      "-c",
      "core.attributesFile=",
      "check-attr",
      "-z",
      "--stdin",
      "text",
      "eol",
    ],
    {
      cwd: root,
      encoding: "utf8",
      input: `${paths.join("\0")}\0`,
      maxBuffer: 64 * 1024 * 1024,
    },
  );
  if (result.status !== 0) return { error: failure(result) };
  const values = new Map();
  // -z の出力は「パス・属性・値」の 3 つずつが NUL で並ぶ。
  const fields = result.stdout.split("\0");
  while (fields.length >= 3) {
    const [path, attribute, value] = fields.splice(0, 3);
    values.set(`${path}\0${attribute}`, value);
  }
  return { paths, values };
}

function lfViolation(root) {
  const read = attributes(root);
  if (read.error !== undefined) return read.error;
  // eol を指定すると、text を書かなくても git は改行を変換する。-text（unset）だけは変換しない。
  const wrong = read.paths.filter(
    (path) =>
      read.values.get(`${path}\0text`) === "unset" ||
      read.values.get(`${path}\0eol`) !== "lf",
  );
  if (wrong.length === 0) return undefined;
  const shown =
    wrong.slice(0, 10).join("・") +
    (wrong.length > 10 ? ` ほか ${wrong.length - 10} 件` : "");
  const expected = RULES.find(
    (rule) => rule.id === "gitattributes-lf",
  ).expected;
  return (
    `.gitattributes で、${shown} が LF に固定されていない（eol が lf にならないか、-text で外している）。` +
    `次の行を足すか、取り消している行を外す: ${expected.join(" / ")}`
  );
}

/** 改行を LF にそろえた中身の sha256（tools/development の files.ts の contentHash と同じ）。 */
function contentHash(text) {
  return createHash("sha256").update(text.replace(/\r\n/g, "\n")).digest("hex");
}

/** .guardrail/files.tsv の行（part・path・区別・sha256・置くスタック）。 */
function manifestRows(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => line !== "" && !line.startsWith("#"))
    .map((line) => {
      const [part, path, ownership, sha256, stacks = "-"] = line.split("\t");
      const placedWith = stacks === "-" ? [] : stacks.split(",");
      return { part, path, ownership, sha256, stacks: placedWith };
    });
}

/**
 * ハーネスが持つファイルのうち、配布版（DIST の .guardrail/files.tsv の sha256）と違うものと、無いもの。
 * part は、直下に置く part のうち導入したもの（common と、.guardrail/answers/<part>.yml があるもの）だけを見る。
 * プラグインの判定器で動かすと、一覧そのものも、プラグインの一覧と比べる（導入先がファイルと一覧を両方書き換えても通さないため）。
 */
function harnessViolation(root) {
  const manifest = join(DIST, FILES_MANIFEST);
  if (!existsSync(manifest))
    return `配布版の ${FILES_MANIFEST} が無い（development:setup の apply で置き直す）`;
  const text = readFileSync(manifest, "utf8");
  const installed = (part) =>
    part === "common" ||
    existsSync(join(root, ".guardrail/answers", `${part}.yml`));
  const stacks = installedStacks(root);
  // 決まったスタックのときだけ置くファイルは、そのスタックを導入していなければ無くてよい。
  const placed = (row) =>
    row.stacks.length === 0 ||
    stacks === undefined ||
    row.stacks.some((stack) => stacks.includes(stack));
  const changed = [];
  const missing = [];
  const compare = (row, wanted) => {
    const full = join(root, row.path);
    if (!existsSync(full)) missing.push(row.path);
    else if (contentHash(readFileSync(full, "utf8")) !== wanted)
      changed.push(row.path);
  };
  const rows = manifestRows(text);
  // 一覧が空か壊れていると、何も比べずに通ってしまう（書きかけや衝突の解き違い）。
  const malformed = rows.filter(
    (row) =>
      row.ownership === undefined ||
      !["harness", "shared", "project"].includes(row.ownership) ||
      !(row.sha256 === "-" || /^[0-9a-f]{64}$/.test(row.sha256 ?? "")),
  );
  if (rows.every((row) => row.ownership !== "harness") || malformed.length > 0)
    return `${FILES_MANIFEST} が壊れている（ハーネスが持つファイルの行が無いか、形の誤った行がある。development:setup の apply で置き直す）`;
  for (const row of rows) {
    // 置かないファイル（導入していない part・スタック）は、あっても無くても見ない。
    if (row.ownership !== "harness" || !installed(row.part) || !placed(row))
      continue;
    if (row.path === FILES_MANIFEST) {
      if (resolve(DIST) !== resolve(root)) compare(row, contentHash(text));
    } else if (/^[0-9a-f]{64}$/.test(row.sha256 ?? ""))
      compare(row, row.sha256);
    // Jinja で描くファイルは中身を比べられないので、あることだけを確かめる。
    else if (!existsSync(join(root, row.path))) missing.push(row.path);
  }
  const problems = [];
  if (changed.length > 0)
    problems.push(`配布版から書き換えている: ${changed.join("・")}`);
  if (missing.length > 0) problems.push(`無い: ${missing.join("・")}`);
  return problems.length === 0
    ? undefined
    : `ハーネスが持つファイルが配布版と同じでない（${problems.join("。")}）`;
}

/**
 * Dependabot の docker-compose が拾う名前か（(docker-)?compose(-<語>)?(.<語>)?.ya?ml）。setup が Dependabot の
 * docker-compose の設定を足すかを決める tools/development の isComposeFile と同じ（判定器は依存を持たないので
 * 写して持つ。tools/development のテストが、同じ名前を選ぶことを確かめる）。検査する compose ファイルに、
 * 更新の PR が届くようにするため。
 */
function isComposeFile(name) {
  const parts = name.split(".");
  const ext = parts.pop();
  if ((ext !== "yml" && ext !== "yaml") || parts.length > 2) return false;
  const [head = "", suffix] = parts;
  const base = head.startsWith("docker-") ? head.slice("docker-".length) : head;
  const variant = base.startsWith("compose-")
    ? base.slice("compose-".length)
    : "";
  return (
    (base === "compose" || /^\w+$/.test(variant)) &&
    (suffix === undefined || /^[\w-]+$/.test(suffix))
  );
}

/** docker compose を cwd で、引数で動かす。daemon に接続しない。 */
function dockerCompose(cwd, args, env = process.env) {
  return spawnSync("docker", ["compose", ...args], {
    cwd,
    env,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
}

/**
 * Compose が -f の無いときに読むベースと override のファイルの名前。Compose はそれぞれ、この順で最初に見つけた
 * 1 つだけを読み、ほかは警告して読まない（Docker Compose v2 と compose-go の既定の名前と順）。
 */
const COMPOSE_DEFAULTS = [
  "compose.yaml",
  "compose.yml",
  "docker-compose.yml",
  "docker-compose.yaml",
];
const COMPOSE_OVERRIDES = [
  "compose.override.yml",
  "compose.override.yaml",
  "docker-compose.override.yml",
  "docker-compose.override.yaml",
];

/** リポジトリの直下から見た、ディレクトリ dir（直下は ""）の中のパス。 */
function pathIn(dir, name) {
  return dir === "" ? name : `${dir}/${name}`;
}

/**
 * 判定する compose ファイルを、ディレクトリ（リポジトリの直下から見たパス。直下は ""）ごとに並べる。直下は、
 * これまでどおり置いてあるすべての compose ファイル。サブディレクトリは、git が追跡しているか追跡の対象になりうる
 * （.gitignore で外していない）compose ファイル。monorepo のようにサブディレクトリにだけ compose を置く導入先も、
 * 直下と同じ規則で判定するため。.gitignore で外したもの（node_modules の中や、手元だけの override など）は、
 * リポジトリの設定ではなく CI にも無いので見ない。追跡したまま作業ツリーから消したファイルは読むものが無いので
 * 外す（リンク先の無いシンボリックリンクは残し、読めないとして落とす）。.github/ の下（workflow の
 * docker-compose.yml など）は compose ファイルではないので見ない。git で一覧を求められなければ、サブディレクトリを判定せずに通さないため { error } を返す。
 */
/**
 * 作業ツリーにパスがあるか。リンク先の無いシンボリックリンクや、権限が無くて確かめられないパスも、あるとする
 * （読めないとして落とし、判定せずに通さないため）。
 */
function present(path) {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    return error.code !== "ENOENT" && error.code !== "ENOTDIR";
  }
}

function composeLayout(root) {
  const listed = spawnSync(
    "git",
    [
      "ls-files",
      "-z",
      "--cached",
      "--others",
      "--exclude-standard",
      "--",
      "*compose*.yml",
      "*compose*.yaml",
    ],
    { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
  );
  if (listed.error !== undefined || listed.status !== 0)
    return {
      error: `サブディレクトリの compose ファイルを一覧にできない（${failure(listed)}）`,
    };
  const dirs = new Map([["", composeFiles(root)]]);
  for (const path of new Set(listed.stdout.split("\0"))) {
    const slash = path.lastIndexOf("/");
    const name = path.slice(slash + 1);
    if (
      slash === -1 ||
      !isComposeFile(name) ||
      path.startsWith(".github/") ||
      !present(join(root, path))
    )
      continue;
    const dir = path.slice(0, slash);
    dirs.set(dir, [...(dirs.get(dir) ?? []), name].sort());
  }
  return { dirs };
}

/**
 * 判定する compose の設定。ディレクトリごとに、Compose をそのディレクトリで -f 無しで動かしたときと同じ設定を
 * 読む。既定の名前のベースがあれば、Compose が -f 無しで読むベースと override を -f で並べて Compose に合成させ
 * （include・extends と .env の値も、そのディレクトリを基準に Compose が解決する）、1 つの対象にする。override が
 * ベースの build を外す（!reset）ような設定を、合成した結果で判定するため。override があれば、-f でベースだけを
 * 指定して動かすときの設定も、同じく Compose に解決させて判定する。COMPOSE_FILE は読まない（並べるファイルを
 * 判定器が決めて、どのファイルも判定から漏らさないため）。合成に入らないファイル（compose.acceptance.yml や、
 * Compose が読まない 2 つめの既定の名前のファイルなど）は、-f で 1 つずつ判定する。
 * label は違反の文に出す名前、file は CI の注釈が指すファイル（どちらもリポジトリの直下から見たパス）、dir と cwd は
 * Compose を動かすディレクトリ（直下から見たパスと絶対パス）、resolved は image の変数も展開するか、merged は Compose が -f 無しで読む設定か
 * （build も image も無いサービスを、確かめられないとして落とす）。
 */
function composeTargets(root, dir, files) {
  const cwd = join(root, dir);
  const base = COMPOSE_DEFAULTS.find((name) => files.includes(name));
  const override = COMPOSE_OVERRIDES.find((name) => files.includes(name));
  const merged = base === undefined ? [] : [base, override].filter(Boolean);
  const target = (names, more = {}) => ({
    label: names.map((name) => pathIn(dir, name)).join(" + "),
    file: pathIn(dir, names[0]),
    dir,
    cwd,
    args: names.flatMap((name) => ["-f", name]),
    ...more,
  });
  return [
    ...(base === undefined
      ? []
      : [target(merged, { resolved: true, merged: true })]),
    ...(override === undefined || base === undefined
      ? []
      : [target([base], { resolved: true })]),
    ...files
      .filter((file) => !merged.includes(file))
      .map((file) => target([file])),
  ];
}

/** 判定するすべての compose の設定（composeLayout の各ディレクトリの composeTargets）。 */
function allComposeTargets(layout, root) {
  return [...layout.dirs].flatMap(([dir, files]) =>
    composeTargets(root, dir, files),
  );
}

/**
 * 変数を展開する docker compose config。Compose が値を持たないと報告した必須の変数（${VAR:?...}）にだけ
 * 0.0.0.0 を渡して動かし直す。CI に無い起動用の必須の変数（environment のパスワードなど）で、ports と関係なく
 * 落ちないようにする。Compose が環境変数か .env から解決できる変数は渡さないので、Compose の値を上書きしない。
 * 0.0.0.0 は、ports のホスト側に置いた変数なら全インターフェースへの公開として落ち、公開する番号の側なら config が
 * 解釈できずに落ちるので、ports を見逃さない。image に置いた変数なら digest が無いとして落ちる。
 */
function interpolatedConfig(cwd, args) {
  let env = process.env;
  const filled = new Set();
  for (;;) {
    const result = dockerCompose(cwd, args, env);
    const missing = /required variable (\S+) is missing a value/.exec(
      result.stderr ?? "",
    )?.[1];
    if (result.status === 0 || missing === undefined || filled.has(missing))
      return result;
    filled.add(missing);
    env = { ...env, [missing]: "0.0.0.0" };
  }
}

/**
 * docker compose config で正規化したサービス。profiles 付きのサービスも含め、override のような部分的なファイルも、
 * CI に無い env_file も読まずに解釈する。interpolate が true なら変数を展開する。
 * 既定の名前のベースに入らないファイルの image は、展開せずに判定する（--no-interpolate）。展開すると、CI に無い
 * 変数の image: "${DB_IMAGE}" が空になって image ごと消え、手元で渡すタグだけのイメージを見逃すから。既定の名前の
 * ベース（resolved）は include や extends のパスの変数を解決するために展開し、Compose が -f 無しで読む設定で
 * image の無いサービスを判定できないものとして落とす（unpinnedImages）。ports は展開して判定する。展開しないと短い書き方（"5432:5432"）が host_ip に正規化され
 * ない。展開すると CI に無い変数は空になり、host_ip が無い（全インターフェースへの公開）として落ちる。値の無い
 * 必須の変数の扱いは interpolatedConfig にある。
 * Docker CLI か Compose が無ければ { absent }、読めなければ { error }。error には Compose の出力を入れない。
 * Compose のエラーは、展開した変数の値や設定の中身を含みうるので、CI のログに残さず、手元で確かめる手順を示す。
 */
function composeServices(target, interpolate) {
  const args = [
    ...target.args,
    "--profile",
    "*",
    "config",
    "--no-consistency",
    "--no-env-resolution",
    "--format",
    "json",
  ];
  const result = interpolate
    ? interpolatedConfig(target.cwd, args)
    : dockerCompose(target.cwd, [...args, "--no-interpolate"]);
  if (result.error?.code === "ENOENT") return { absent: true };
  if (
    result.status !== 0 &&
    dockerCompose(target.cwd, ["version"]).status !== 0
  )
    return { absent: true };
  // 判定と同じ引数で、設定の中身を出さない（--quiet）コマンド。Compose のエラーだけが手元に出る。
  const command = [
    "docker compose",
    ...args
      .filter((arg) => arg !== "--format" && arg !== "json")
      .map((arg) => (arg === "*" ? "'*'" : arg)),
    ...(interpolate ? [] : ["--no-interpolate"]),
    "--quiet",
  ].join(" ");
  const where = target.dir === "" ? "リポジトリの直下" : target.dir;
  const retry = `手元の ${where} で ${command} を実行して原因を確かめる`;
  if (result.error !== undefined || result.status !== 0)
    return {
      error: `${target.label} を docker compose config で解釈できない（${retry}）`,
    };
  try {
    const services = JSON.parse(result.stdout).services;
    return { services: isRecord(services) ? services : {} };
  } catch {
    return {
      error: `${target.label} の docker compose config の結果を読めない（${retry}）`,
    };
  }
}

/** ディレクトリ dir の直下の compose ファイル（Dependabot の docker-compose が拾う名前）。 */
function composeFiles(dir) {
  return readdirSync(dir).filter(isComposeFile).sort();
}

/**
 * build: の無いサービスの image: のうち、digest で固定していないもの。合成した設定では、build も image も provider も無い
 * サービス（変数が空で image が消えたものなど）も、pull するイメージを確かめられないので違反にする。image の値は
 * 出さない。Compose が環境変数から展開した値を、CI のログに残さないため。
 */
function unpinnedImages(target, services) {
  return Object.entries(services).flatMap(([name, service]) => {
    if (!isRecord(service) || service.build !== undefined) return [];
    if (typeof service.image === "string" && service.image !== "")
      return DIGEST.test(service.image)
        ? []
        : [
            `${target.label}: サービス ${name} の image が digest で固定されていない`,
          ];
    // image の無い provider のサービスは、Compose が外部の provider に任せ、イメージを pull しない。
    return target.merged && service.provider === undefined
      ? [
          `${target.label}: サービス ${name} に build も image も無く、pull するイメージを確かめられない（image の変数が空など）`,
        ]
      : [];
  });
}

/**
 * ports のうち、ホストの 127.0.0.1 以外（host_ip の無いものは全インターフェース）に公開するもの。ホストのアドレスと
 * 番号は出さず、コンテナ側の番号で ports の行を指す。環境変数から展開した値を、CI のログに残さないため。
 */
function exposedPorts(target, services) {
  return Object.entries(services).flatMap(([name, service]) =>
    (isRecord(service) && Array.isArray(service.ports) ? service.ports : [])
      .filter((port) => !isRecord(port) || port.host_ip !== LOOPBACK)
      .map((port) => {
        const host =
          port?.host_ip === undefined
            ? "ホストの全インターフェース"
            : `ホストの ${LOOPBACK} 以外のアドレス`;
        return `${target.label}: サービス ${name} が ports（コンテナの ${String(port?.target)} 番）を${host}に公開している`;
      }),
  );
}

/**
 * compose の設定（allComposeTargets）を docker compose config で正規化し、find が返す違反をまとめる。subject
 * は判定を飛ばしたときに知らせる対象、interpolate は 1 つずつ読むファイルの変数を展開して正規化するか。compose
 * ファイルがあれば、導入したスタックの記録に関わらず判定する（PR で記録から docker を外しても、必須の
 * 規則が外れないため）。解釈できなければ、判定せずに通さないため落とす。Docker CLI か Compose の無い手元（macOS・
 * Windows で check だけを回すときなど）では、知らせて通す。CI の action が --ci を付けて呼ぶ判定器は、無ければ
 * 落とす。サブディレクトリの compose ファイルを一覧にできなければ、判定せずに通さないため落とす。
 */
function composeViolation(
  root,
  options,
  { subject, find, interpolate = false },
) {
  const layout = composeLayout(root);
  if (layout.error !== undefined) return layout.error;
  const problems = [];
  const violated = [];
  for (const target of allComposeTargets(layout, root)) {
    const read = composeServices(
      target,
      interpolate || target.resolved === true,
    );
    if (read.absent && !options.ci) {
      console.error(
        `guardrail-rules: Docker CLI か Compose が無いので、compose の ${subject} を判定していない（PR では CI が判定する）`,
      );
      return undefined;
    }
    if (read.absent)
      read.error = `${target.label} を判定する Docker CLI か Compose が無い`;
    const found =
      read.error === undefined ? find(target, read.services) : [read.error];
    if (found.length > 0) violated.push(target.file);
    problems.push(...found);
  }
  return problems.length === 0
    ? undefined
    : { message: problems.join(" / "), file: violated[0] };
}

/**
 * compose ファイル（composeLayout の各ディレクトリ）の最上位（インデントなし）の version。docker compose
 * config は version を捨てるので、元のファイルを読む。Docker が無くても判定できる。
 */
function composeVersionViolation(root) {
  const layout = composeLayout(root);
  if (layout.error !== undefined) return layout.error;
  const problems = [...layout.dirs].flatMap(([dir, files]) =>
    files.flatMap((name) => {
      const file = pathIn(dir, name);
      let text;
      try {
        text = readFileSync(join(root, file), "utf8");
      } catch (error) {
        // 読めないファイル（リンク先の無いシンボリックリンクなど）で、ほかの規則の結果まで失わないため。
        return [{ file, message: `${file} を読めない: ${error.message}` }];
      }
      return /^["']?version["']?\s*:/m.test(text)
        ? [{ file, message: `${file}: 最上位に version: がある` }]
        : [];
    }),
  );
  return problems.length === 0
    ? undefined
    : {
        message: problems.map((problem) => problem.message).join(" / "),
        file: problems[0].file,
      };
}

/** 行の先頭の空白の数。 */
function indentOf(line) {
  return line.length - line.trimStart().length;
}

/** YAML の `<キー>:` の行のキー（引用符を外す）。キーの行でなければ undefined。 */
function keyOf(line) {
  const text = line.trimStart();
  const quote = text.at(0);
  const quoted = quote === '"' || quote === "'";
  // 引用符のキーは閉じる引用符まで、引用符の無いキーは最初の : まで。
  const end = quoted ? text.indexOf(quote, 1) + 1 : text.indexOf(":");
  if (end <= 0 || (!quoted && /^[#-]/.test(text))) return undefined;
  const rest = text.slice(end).trimStart();
  const after = rest.at(1);
  if (!rest.startsWith(":") || (after !== undefined && after.trim() !== ""))
    return undefined;
  return scalar(text.slice(0, end));
}

/**
 * workflow の jobs の、ジョブの id ごとの本文の行。依存を持たないので YAML のパーサは使わず、ブロックの形
 * （jobs: の下に、同じ深さで `<id>:` が並ぶ）だけを読む。読めなければ undefined。
 */
function workflowJobs(text) {
  const lines = text
    .split(/\r?\n/)
    .filter((line) => stripComment(line).trim() !== "");
  const start = lines.findIndex(
    (line) =>
      indentOf(line) === 0 &&
      keyOf(line) === "jobs" &&
      stripComment(line).trim().endsWith(":"),
  );
  if (start === -1) return undefined;
  const body = [];
  for (const line of lines.slice(start + 1)) {
    if (indentOf(line) === 0) break;
    body.push(line);
  }
  if (body.length === 0) return undefined;
  const depth = indentOf(body[0]);
  const jobs = new Map();
  let current;
  for (const line of body) {
    if (indentOf(line) < depth) return undefined;
    if (indentOf(line) === depth) {
      current = keyOf(line);
      if (current === undefined) return undefined;
      jobs.set(current, []);
    } else jobs.get(current).push(line);
  }
  return jobs;
}

/** ジョブの本文の、直下のキーの 1 行の値（コメントと引用符を外す）。無ければ undefined。 */
function jobValue(lines, key) {
  if (lines.length === 0) return undefined;
  const depth = indentOf(lines[0]);
  const line = lines.find(
    (candidate) => indentOf(candidate) === depth && keyOf(candidate) === key,
  );
  return line === undefined
    ? undefined
    : scalar(line.slice(line.indexOf(":") + 1));
}

/** ジョブの本文から needs のジョブの id（1 つ・`[a, b]`・行をまたぐ `[...]`・`- a` の並び）。 */
function jobNeeds(lines) {
  if (lines.length === 0) return [];
  const depth = indentOf(lines[0]);
  const at = lines.findIndex(
    (line) => indentOf(line) === depth && keyOf(line) === "needs",
  );
  if (at === -1) return [];
  const first = lines.at(at) ?? "";
  const rest = [];
  for (const line of lines.slice(at + 1)) {
    const text = stripComment(line).trim();
    // `- <id>` の並びは、needs: と同じ深さにも書ける。
    const item = indentOf(line) === depth && text.startsWith("- ");
    if (indentOf(line) < depth || (indentOf(line) === depth && !item)) break;
    rest.push(text);
  }
  const inline = stripComment(first.slice(first.indexOf(":") + 1)).trim();
  const value = [inline, ...rest].join(" ").trim();
  if (value.startsWith("["))
    return value
      .replace(/^\[|\]$/g, "")
      .split(",")
      .map(scalar)
      .filter(Boolean);
  if (inline !== "") return [scalar(inline)];
  return rest
    .filter((item) => item.startsWith("- "))
    .map((item) => scalar(item.slice(2)));
}

function ciJobsViolation(root) {
  const path = join(root, CI);
  if (!existsSync(path)) return `${CI} が無い`;
  const jobs = workflowJobs(readFileSync(path, "utf8"));
  if (jobs === undefined)
    return `${CI} の jobs を読めない（jobs: の下にジョブを並べる形にする）`;
  const problems = [];
  const absent = CI_JOBS.filter((job) => !jobs.has(job));
  if (absent.length > 0) problems.push(`ジョブ ${absent.join("・")} が無い`);
  const required = jobs.get("ci-required");
  if (required === undefined) problems.push("ジョブ ci-required が無い");
  else {
    // always() が無いと、待つジョブが落ちたときに ci-required が skipped になり、必須のチェックが通る。
    const condition = (jobValue(required, "if") ?? "").replace(/\s+/g, "");
    if (condition !== "always()" && condition !== "${{always()}}")
      problems.push("ci-required の if が always() でない");
    const needs = jobNeeds(required);
    const unwaited = CI_JOBS.filter(
      (job) => jobs.has(job) && !needs.includes(job),
    );
    if (unwaited.length > 0)
      problems.push(`ci-required の needs に ${unwaited.join("・")} が無い`);
  }
  return problems.length === 0 ? undefined : `${CI} で、${problems.join("。")}`;
}

function isPercent(value) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 100
  );
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** JSON のファイルを読む。無ければ { missing: true }、読めなければ { error }。 */
function readJson(root, path) {
  const full = join(root, path);
  if (!existsSync(full)) return { missing: true };
  try {
    return { data: JSON.parse(readFileSync(full, "utf8")) };
  } catch (error) {
    return { error: `${path} が JSON として読めない: ${error.message}` };
  }
}

/** コメント（行頭か、空白の後の # から行末まで）を外す。 */
function stripComment(text) {
  if (text.trimStart().startsWith("#")) return "";
  const at = text.search(/\s#/);
  return at === -1 ? text : text.slice(0, at);
}

/** YAML の値 1 つから、コメントと前後の空白と引用符を外す。 */
function scalar(text) {
  const value = stripComment(text).trim();
  const quote = value.at(0);
  const quoted =
    (quote === '"' || quote === "'") &&
    value.length >= 2 &&
    value.at(-1) === quote;
  return quoted ? value.slice(1, -1) : value;
}

/** `[a, b]` の形の一覧。行をまたぐ形（閉じていない）は読めないので undefined。 */
function flowStacks(inline) {
  if (!inline.endsWith("]")) return undefined;
  return inline.slice(1, -1).split(",").map(scalar).filter(Boolean);
}

/** `stacks:` の次の行から並ぶ `- <名前>`。1 つも無ければ読めないので undefined。 */
function blockStacks(lines) {
  const stacks = [];
  for (const line of lines) {
    const text = stripComment(line).trim();
    if (text === "") continue;
    if (!text.startsWith("- ")) break;
    stacks.push(scalar(text.slice(2)));
  }
  return stacks.length === 0 ? undefined : stacks;
}

/**
 * 導入したスタック（apply が書く .guardrail/answers/common.yml の stacks）。依存を持たないので YAML の
 * パーサは使わず、copier が書く形（`stacks:` の下の `- <名前>` の並びか、`stacks: []`）だけを読む。
 * 読めなければ undefined を返す（スタックが無いものとして、スタックごとの閾値の判定を抜かさないため）。
 */
function installedStacks(root) {
  const path = join(root, ".guardrail/answers/common.yml");
  if (!existsSync(path)) return undefined;
  const lines = readFileSync(path, "utf8").split(/\r?\n/);
  const keys = ["stacks:", '"stacks":', "'stacks':"];
  const start = lines.findIndex((line) =>
    keys.some((key) => line.startsWith(key)),
  );
  if (start === -1) return undefined;
  const first = lines.at(start) ?? "";
  const inline = stripComment(first.slice(first.indexOf(":") + 1)).trim();
  if (inline.startsWith("[")) return flowStacks(inline);
  if (inline !== "") return undefined;
  return blockStacks(lines.slice(start + 1));
}

/** 導入したスタックごとの total・branch の問題（数が入っていないもの）。 */
function stackThresholdProblems(root, data) {
  const stacks = installedStacks(root);
  if (stacks === undefined)
    return [
      "導入したスタックを .guardrail/answers/common.yml の stacks から読めない（development:setup をやり直す）",
    ];
  const tables = new Map(Object.entries(data));
  const problems = [];
  for (const { stack, metrics } of COVERAGE_STACKS) {
    if (!stacks.includes(stack)) continue;
    for (const metric of metrics) {
      const values = tables.get(metric);
      const value = isRecord(values)
        ? new Map(Object.entries(values)).get(stack)
        : undefined;
      if (!isPercent(value))
        problems.push(
          `${metric}.${stack} が 0〜100 の数でない（${JSON.stringify(value ?? null)}）`,
        );
    }
  }
  return problems;
}

function thresholdsViolation(root) {
  const read = readJson(root, THRESHOLDS);
  if (read.missing) return `${THRESHOLDS} が無い`;
  if (read.error !== undefined) return read.error;
  if (!isRecord(read.data))
    return `${THRESHOLDS} が {"total": {...}, "branch": {...}, "diff": ...} の形でない`;
  const problems = [];
  if (!isPercent(read.data.diff))
    problems.push(
      `diff が 0〜100 の数でない（${JSON.stringify(read.data.diff ?? null)}）`,
    );
  problems.push(...stackThresholdProblems(root, read.data));
  return problems.length === 0
    ? undefined
    : `${THRESHOLDS} の ${problems.join("・")}`;
}

function diffMinimumViolation(root) {
  const read = readJson(root, THRESHOLDS);
  const diff = isRecord(read.data) ? read.data.diff : undefined;
  // diff が数でないときは、必須の coverage-thresholds が落とす。
  if (!isPercent(diff) || diff >= DIFF_MINIMUM) return undefined;
  return `${THRESHOLDS} の diff が ${diff} で、${DIFF_MINIMUM} を下回っている`;
}

/**
 * マージ先の thresholds.json。base を渡されたら（CI）その commit との分岐点を、省いたら origin/HEAD との分岐点を
 * 読む。分岐点と比べるのは、枝を切った後に main の CI が閾値を引き上げても、枝が触っていない値を下げたと
 * 見なさないため（GitHub の PR のマージコミットでは、マージ先の先端がそのまま分岐点になる）。
 * 返すのは { data }（無ければ data は undefined）か、比べられないときの { skipped } か { error }。
 */
function baseThresholds(root, base) {
  let rev = base;
  if (rev === undefined) {
    const head = git(["symbolic-ref", "-q", "refs/remotes/origin/HEAD"], root);
    if (head.status !== 0)
      return {
        skipped:
          "リモートのデフォルトブランチ（origin/HEAD）が無いので、閾値をマージ先と比べていない" +
          "（git remote set-head origin --auto で作れる。PR では CI が比べる）",
      };
    rev = head.stdout.trim();
  }
  const fork = git(["merge-base", "HEAD", rev], root);
  if (fork.status !== 0) {
    const message = `閾値を比べるマージ先（${rev}）との分岐点を git で求められない`;
    // 手元では浅い clone などで履歴が足りないことがある。PR では CI が --base を渡して比べるので、知らせて通す。
    if (base === undefined)
      return {
        skipped: `${message}ので、比べていない（git fetch --unshallow で履歴を足せる。PR では CI が比べる）`,
      };
    return { error: `${message}: ${(fork.stderr || "").trim()}` };
  }
  const commit = fork.stdout.trim();
  const listed = git(
    ["ls-tree", "--name-only", commit, "--", THRESHOLDS],
    root,
  );
  if (listed.status !== 0) return { error: failure(listed) };
  if (listed.stdout.trim() === "") return { data: undefined };
  const shown = git(["show", `${commit}:${THRESHOLDS}`], root);
  if (shown.status !== 0) return { error: failure(shown) };
  try {
    return { data: JSON.parse(shown.stdout) };
  } catch {
    // マージ先で壊れているなら、比べる値が無い（今の値の形は coverage-thresholds が確かめる）。
    return { data: undefined };
  }
}

/** thresholds.json の比べる値（diff と、total・branch のスタックごとの値）を「キー → 値」で並べる。 */
function thresholdValues(data) {
  const values = new Map();
  if (!isRecord(data)) return values;
  const tables = new Map(Object.entries(data));
  values.set("diff", tables.get("diff"));
  for (const metric of ["total", "branch"]) {
    const table = tables.get(metric);
    if (!isRecord(table)) continue;
    for (const [stack, value] of Object.entries(table))
      values.set(`${metric}.${stack}`, value);
  }
  return values;
}

function notLoweredViolation(root, options) {
  const read = baseThresholds(root, options.base);
  if (read.skipped !== undefined) {
    console.error(`guardrail-rules: ${read.skipped}`);
    return undefined;
  }
  if (read.error !== undefined) return read.error;
  const now = readJson(root, THRESHOLDS);
  const current = thresholdValues(now.data);
  const stacks = installedStacks(root);
  const lowered = [];
  for (const [key, before] of thresholdValues(read.data)) {
    // マージ先に 0〜100 の数が無いか 0 なら、比べない（初回の計測の前。範囲外の値は直せるようにする）。
    if (!isPercent(before) || before <= 0) continue;
    const after = current.get(key);
    const stack = key.split(".")[1];
    // 導入をやめたスタックの閾値は、消してよい（残すとそのスタックのカバレッジが無いので check:full が落ちる）。
    // 導入したスタックを読めないか、そのスタックの unit・integration のタスク（カバレッジを測る）が残っていれば、
    // 消したものも下げたものとして扱う。
    const measured = ["unit", "it"].some((kind) =>
      existsSync(join(root, ".mise/tasks/check", kind, stack ?? "")),
    );
    const removed =
      after === undefined &&
      stack !== undefined &&
      stacks !== undefined &&
      !stacks.includes(stack) &&
      !measured;
    if (removed) continue;
    if (!isPercent(after) || after < before)
      lowered.push(
        `${key} を ${before} から ${JSON.stringify(after ?? null)} に`,
      );
  }
  return lowered.length === 0
    ? undefined
    : `${THRESHOLDS} の ${lowered.join("・")}下げている（マージ先の値より下げられない）`;
}

/**
 * 導入先の例外の記録（.guardrail/exceptions.json）。外した任意の規則の id と理由の Map と、記録の誤りを返す。
 * 誤りが 1 つでもあれば、どの記録も効かせない（判定できないまま警告を消さないため）。知らないキーを落とすのは、
 * 対応していない書き方（例えば対象のファイルを絞るつもりのキー）で、規則全体が黙って外れないようにするため。
 */
function readExceptions(root) {
  const read = readJson(root, EXCEPTIONS);
  if (read.missing) return { reasons: new Map(), errors: [] };
  if (read.error !== undefined)
    return { reasons: new Map(), errors: [read.error] };
  const errors = [];
  const reasons = new Map();
  const { data } = read;
  const unknownKeys = (record, allowed) =>
    Object.keys(record).filter((key) => !allowed.includes(key));
  if (!isRecord(data) || !Array.isArray(data.exceptions))
    return {
      reasons,
      errors: [`${EXCEPTIONS} が {"exceptions": [...]} の形でない`],
    };
  const extra = unknownKeys(data, ["exceptions"]);
  if (extra.length > 0)
    errors.push(`知らないキーがある（${extra.join("・")}）`);
  data.exceptions.forEach((record, index) => {
    const at = `exceptions[${index}]`;
    if (!isRecord(record)) {
      errors.push(`${at} が {"rule": ..., "reason": ...} の形でない`);
      return;
    }
    const keys = unknownKeys(record, ["rule", "reason"]);
    if (keys.length > 0)
      errors.push(`${at} に知らないキーがある（${keys.join("・")}）`);
    const rule = RULES.find((r) => r.id === record.rule);
    if (rule === undefined)
      errors.push(
        `${at} の rule ${JSON.stringify(record.rule ?? null)} は規則の一覧に無い`,
      );
    else if (rule.level === "required")
      errors.push(`${at} の ${rule.id} は必須の規則なので、例外にできない`);
    else if (reasons.has(rule.id))
      errors.push(`${at} の ${rule.id} は、ほかの記録と重なっている`);
    if (typeof record.reason !== "string" || record.reason.trim() === "")
      errors.push(`${at} の reason が空か、文字列でない`);
    else if (rule?.level === "optional") reasons.set(rule.id, record.reason);
  });
  return { reasons: errors.length === 0 ? reasons : new Map(), errors };
}

/** リポジトリの直下。git で求められなければ cwd（gitattributes-lf が git の失敗を出す）。 */
function repositoryRoot(cwd) {
  const top = git(["rev-parse", "--show-toplevel"], cwd);
  return top.status === 0 ? top.stdout.trim() : cwd;
}

/**
 * すべての規則を判定する。ok が false なら message に外した内容を書く。例外の記録で外した任意の規則には、
 * exception に記録した理由を付ける。
 */
function judgeAll(cwd, options) {
  const root = repositoryRoot(cwd);
  const exceptions = readExceptions(root);
  return RULES.map(({ id, level, file, reason, expected, check }) => {
    const found = check(root, exceptions, options);
    if (found === undefined)
      return { id, level, file, reason, expected, ok: true };
    const { message, file: violated = file } =
      typeof found === "string" ? { message: found } : found;
    const base = { id, level, file: violated, reason, expected };
    const excepted = exceptions.reasons.get(id);
    return excepted === undefined
      ? { ...base, ok: false, message }
      : { ...base, ok: false, message, exception: { reason: excepted } };
  });
}

/** 引数の --base <rev>。値が無いか --base=<rev> の形なら投げる（比べずに通さないため）。 */
function parseBase(argv) {
  if (argv.some((arg) => arg.startsWith("--base=")))
    throw new Error("--base は --base <rev> の形で渡す");
  const at = argv.indexOf("--base");
  if (at === -1) return undefined;
  const value = argv.at(at + 1);
  if (value === undefined || value === "" || value.startsWith("--"))
    throw new Error("--base には、比べるマージ先の commit か ref を渡す");
  return value;
}

/** GitHub Actions のワークフローコマンドの値の書き方（% と改行を逃がす）。 */
function escapeData(text) {
  return text.replace(/%/g, "%25").replace(/\r/g, "%0D").replace(/\n/g, "%0A");
}

/** ワークフローコマンドの属性の値の書き方。サブディレクトリのパスの : と , で属性が切れないようにする。 */
function escapeProperty(text) {
  return escapeData(text).replace(/:/g, "%3A").replace(/,/g, "%2C");
}

function main(argv) {
  const results = judgeAll(process.cwd(), {
    base: parseBase(argv),
    ci: argv.includes("--ci"),
  });
  const failed = results.some(
    (result) => !result.ok && result.level === "required",
  );
  if (argv.includes("--json")) {
    process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
    return failed ? 1 : 0;
  }
  const shown = results.filter((r) => !r.ok && r.exception === undefined);
  for (const result of shown) {
    const label = result.level === "required" ? "必須" : "任意";
    const line = `[${result.id}] ${label}の規則を満たしていない: ${result.message}\n  理由: ${result.reason}`;
    // GitHub Actions では、PR の画面にも出るように注釈にする。
    if (process.env.GITHUB_ACTIONS === "true") {
      const kind = result.level === "required" ? "error" : "warning";
      console.log(
        `::${kind} file=${escapeProperty(result.file)},title=${result.id}::${escapeData(result.message)}`,
      );
    }
    console.error(line);
  }
  const warned = shown.filter((r) => r.level === "optional").length;
  const excepted = results.filter((r) => r.exception !== undefined).length;
  if (!failed)
    console.log(
      `guardrail-rules: 規則 ${results.length} 件の判定を終えた（必須の違反なし。任意の違反の警告 ${warned} 件、` +
        `${EXCEPTIONS} で外した任意の規則 ${excepted} 件）`,
    );
  return failed ? 1 : 0;
}

process.exitCode = main(process.argv.slice(2));
