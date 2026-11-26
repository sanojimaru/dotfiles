#!/usr/bin/env node
// development のガードレール: カバレッジの集計・閾値の判定・変更行のカバレッジ・閾値の引き上げ。
//
// どのスタックでも同じ形で扱うため、各スタックの unit・integration テストが出す LCOV を
// 層別の `.guardrail/coverage/{unit,integration}/<stack>.json` に保存し、両方を combine した
// `.guardrail/coverage/<stack>.json` で閾値を判定する。閾値は
// `.guardrail/thresholds.json` の1箇所に置く（vitest.config.ts・.coveragerc 等のツールの設定には書かない）。
//
//   node scripts/guardrail-coverage.mjs collect <stack> [--suite unit|integration] [--base <dir>] <lcov> ...
//                                                               LCOV を共通の JSON へ変換する（複数あればまとめる）
//     手元の TypeScript・Python unit では、今回の計測で変更行も報告する。比較先は GUARDRAIL_DIFF_BASE で指定できる。
//   node scripts/guardrail-coverage.mjs reset                   前回の計測を消す（check:full の最初）
//   node scripts/guardrail-coverage.mjs combine                 unit・integration の LCOV を合算する
//   node scripts/guardrail-coverage.mjs check                   合計のカバレッジを閾値と比べる
//   node scripts/guardrail-coverage.mjs diff [--base <ref>]     変更行のカバレッジを報告する
//   node scripts/guardrail-coverage.mjs raise                   閾値を実測に合わせて引き上げる
//
// 行カバレッジ（total）と分岐カバレッジ（branch）の両方に閾値を持つ。
// 閾値は上げる方向にだけ動かす。raise は閾値が無いスタックに初回の値を入れ、実測が閾値を
// 1ポイント以上上回ったスタックの閾値を上げる。どちらも実測を1刻みで切り捨てた値にする。
// 依存パッケージを持たない（どのスタックでも node だけで動かすため）。
import { Buffer } from "node:buffer";
import { execFileSync } from "node:child_process";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";

const COVERAGE_DIR = ".guardrail/coverage";
const THRESHOLDS = ".guardrail/thresholds.json";
const RAISE_BODY = `${COVERAGE_DIR}/raise.md`;
const STEP = 1;
const LOCAL_UNIT_DIFF_LABELS = new Map([
  ["typescript", "TypeScript"],
  ["python", "Python"],
]);
// 閾値の種類（thresholds.json のキー）と、カバレッジの JSON で対応する集計。キーの文字列で
// オブジェクトを引かず、取り出す関数で持つ（ESLint の security/detect-object-injection）。
const METRICS = [
  {
    key: "total",
    label: "行カバレッジ",
    pick: (data) => data.lines,
    thresholdsOf: (thresholds) => thresholds.total,
  },
  {
    key: "branch",
    label: "分岐カバレッジ",
    pick: (data) => data.branches,
    thresholdsOf: (thresholds) => thresholds.branch,
  },
];

/** 実測を STEP 刻みで切り捨てる。 */
function floorToStep(pct) {
  return Math.floor(pct / STEP) * STEP;
}

/** 表示用の割合（小数1桁に丸める）。閾値との比較には使わない（99.95% が 100% に見える）。 */
function percent(hit, found) {
  return found === 0 ? null : Math.round((hit / found) * 1000) / 10;
}

/** 丸めない割合。閾値との比較と、引き上げの切り捨てに使う。 */
function exactPercent({ hit, found }) {
  return found === 0 ? null : (hit * 100) / found;
}

/** hit/found が閾値（%）を下回るか。割り算の誤差を避けて整数の掛け算で比べる。 */
function isBelow({ hit, found }, threshold) {
  return hit * 100 < threshold * found;
}

function format(pct) {
  return pct === null ? "-" : `${pct.toFixed(1)}%`;
}

/**
 * LCOV のパスを、プロジェクト直下からの `/` 区切りの相対パスにする（絶対パス・Windows の `\` を揃える）。
 * 相対パスは base（LCOV を出したパッケージの場所。既定はプロジェクト直下）からのものとして読む。
 * 絶対パスはシンボリックリンクを解いてから比べる（macOS の /var と /private/var のように、
 * テストランナーと cwd で同じ場所の書き方が違うことがある）。
 */
function normalizePath(path, root, base = root) {
  // まだ無いパス（消えたファイル・計測しなかったパッケージ）は、実在する一番近い親で解く。
  const real = (p) => {
    try {
      return realpathSync.native(p);
    } catch {
      const parent = dirname(p);
      return parent === p ? p : join(real(parent), basename(p));
    }
  };
  return relative(real(root), real(resolve(base, path)))
    .split(sep)
    .join("/");
}

/** BRDA の通過回数。`-` はその分岐を含む行が実行されなかったことを表す（0 回として数える）。 */
function branchCount(taken) {
  return taken === "-" ? 0 : Number(taken);
}

/**
 * LCOV（SF・DA・BRDA・end_of_record だけを読む）を、ファイルごとの通過した行・通過しなかった行と、
 * 分岐の数・通過した分岐の数にする。同じファイルが複数回（複数の LCOV にまたがっても）出てきたら、
 * どれかで通過した行・分岐を通過とみなす。inputs は LCOV の中身と、その中の相対パスの起点（base）の組。
 */
function parseLcov(inputs, root) {
  const acc = { hits: new Map(), branches: new Map() };
  for (const input of inputs) readLcov(acc, input, root);
  return summarize(acc.hits, acc.branches);
}

/** 1つの LCOV（中身と相対パスの起点）を、acc の行と分岐の通過回数へ足す。 */
function readLcov({ hits, branches }, { text, base }, root) {
  let current;
  let currentBranches;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("SF:")) {
      const path = normalizePath(line.slice(3), root, base);
      current = hits.get(path) ?? new Map();
      hits.set(path, current);
      currentBranches = branches.get(path) ?? new Map();
      branches.set(path, currentBranches);
    } else if (line.startsWith("DA:") && current) {
      const [no, count] = line.slice(3).split(",");
      const n = Number(no);
      if (Number.isInteger(n))
        current.set(n, (current.get(n) ?? 0) + Number(count));
    } else if (line.startsWith("BRDA:") && currentBranches) {
      const [no, block, branch, taken] = line.slice(5).split(",");
      const id = `${no},${block},${branch}`;
      currentBranches.set(
        id,
        (currentBranches.get(id) ?? 0) + branchCount(taken),
      );
    } else if (line === "end_of_record") {
      current = undefined;
      currentBranches = undefined;
    }
  }
}

function summarize(hits, branches) {
  const entries = [];
  let found = 0;
  let hit = 0;
  for (const [path, lines] of [...hits].sort(([a], [b]) =>
    a.localeCompare(b),
  )) {
    const sorted = [...lines].sort(([a], [b]) => a - b);
    const covered = sorted.filter(([, c]) => c > 0).map(([n]) => n);
    const missed = sorted.filter(([, c]) => c <= 0).map(([n]) => n);
    entries.push([path, { covered, missed }]);
    found += sorted.length;
    hit += covered.length;
  }
  const files = Object.fromEntries(entries);
  let branchFound = 0;
  let branchHit = 0;
  for (const counts of branches.values()) {
    branchFound += counts.size;
    branchHit += [...counts.values()].filter((c) => c > 0).length;
  }
  return {
    lines: { found, hit, pct: percent(hit, found) },
    branches: {
      found: branchFound,
      hit: branchHit,
      pct: percent(branchHit, branchFound),
    },
    files,
  };
}

/** `.guardrail/coverage/*.json` を読む（スタック名 → 中身の Map）。無ければ空。 */
function loadCoverage(root) {
  const dir = join(root, COVERAGE_DIR);
  if (!existsSync(dir)) return new Map();
  return new Map(
    readdirSync(dir)
      .filter((name) => name.endsWith(".json"))
      .sort()
      .map((name) => [
        name.slice(0, -".json".length),
        JSON.parse(readFileSync(join(dir, name), "utf8")),
      ]),
  );
}

/** 呼び出し方や設定の誤り。終了コード 2 で止める（閾値を下回ったときの 1 と区別する）。 */
class UsageError extends Error {}

function isPercent(value) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 100
  );
}

/** `.guardrail/thresholds.json` の中身（無ければ空）。JSON として読めなければ設定の誤りとして止める。 */
function readThresholdsFile(root) {
  const path = join(root, THRESHOLDS);
  if (!existsSync(path)) return {};
  let data;
  try {
    data = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new UsageError(
      `${THRESHOLDS} が JSON として読めません: ${error.message}`,
    );
  }
  if (data === null || typeof data !== "object" || Array.isArray(data))
    throw new UsageError(
      `${THRESHOLDS} は {"total": {...}, "diff": ...} の形にしてください`,
    );
  return data;
}

/**
 * `.guardrail/thresholds.json`。無いときは閾値が1つも無いものとして扱う。値が 0〜100 の数でなければ
 * 止める（`"80%"` のような文字列は比較が常に偽になり、黙って合格してしまうため）。
 */
function loadThresholds(root) {
  const data = readThresholdsFile(root);
  const read = (value, key) => {
    const raw = value ?? {};
    if (raw === null || typeof raw !== "object" || Array.isArray(raw))
      throw new UsageError(
        `${THRESHOLDS} の ${key} は {"<スタック>": <閾値>} の形にしてください`,
      );
    for (const [stack, value] of Object.entries(raw)) {
      if (!isPercent(value))
        throw new UsageError(
          `${THRESHOLDS} の ${key}.${stack} は 0〜100 の数にしてください（${JSON.stringify(value)}）`,
        );
    }
    return new Map(Object.entries(raw));
  };
  const total = read(data.total, "total");
  const branch = read(data.branch, "branch");
  const diff = data.diff ?? null;
  if (diff !== null && !isPercent(diff))
    throw new UsageError(
      `${THRESHOLDS} の diff は 0〜100 の数か null にしてください（${JSON.stringify(diff)}）`,
    );
  return { total, branch, diff };
}

/** 1つのスタック・1種類の閾値について、引き上げ案（無ければ null）を返す。 */
function proposeRaise(metric, { stack, measured, current }) {
  const pct = measured?.pct;
  const exact = measured ? exactPercent(measured) : null;
  if (typeof pct !== "number" || exact === null) return null;
  const next = floorToStep(exact);
  const raises =
    current === undefined
      ? next > 0
      : exact >= current + STEP && next > current;
  if (!raises) return null;
  const { key, label } = metric;
  return { metric, key, label, stack, from: current ?? null, to: next, pct };
}

/**
 * 閾値の引き上げ案（行・分岐それぞれ）。閾値が無いスタックには初回の値を、実測が閾値を STEP 以上
 * 上回るスタックには実測の切り捨てを入れる。下げる案は出さない。実測の切り捨てが 0 のときは閾値にしない。
 */
function proposeRaises(coverage, thresholds) {
  const changes = [];
  for (const metric of METRICS) {
    const current = metric.thresholdsOf(thresholds);
    for (const [stack, data] of coverage) {
      const change = proposeRaise(metric, {
        stack,
        measured: metric.pick(data),
        current: current.get(stack),
      });
      if (change) changes.push(change);
    }
  }
  return changes;
}

const ESCAPES = new Map([
  ["a", 7],
  ["b", 8],
  ["t", 9],
  ["n", 10],
  ["v", 11],
  ["f", 12],
  ["r", 13],
  ['"', 34],
  ["\\", 92],
]);

/** git が引用符で囲んだパス（C の文字列のエスケープ。`\t`・`\"`・`\\`・`\ooo` の8進数のバイト）を戻す。 */
function unquote(text) {
  // コードポイント単位で読む（絵文字のようなサロゲートペアを半分ずつ UTF-8 にすると化ける）。
  const chars = Array.from(text);
  const bytes = [];
  for (let i = 0; i < chars.length; i++) {
    const octal = /^[0-7]{3}/.exec(chars.slice(i + 1, i + 4).join(""));
    const char = chars.at(i) ?? "";
    if (char !== "\\") {
      bytes.push(...Buffer.from(char, "utf8"));
    } else if (octal) {
      bytes.push(Number.parseInt(octal[0], 8));
      i += 3;
    } else {
      const next = chars.at(i + 1) ?? "";
      const escaped = ESCAPES.get(next);
      bytes.push(
        ...(escaped === undefined ? Buffer.from(next, "utf8") : [escaped]),
      );
      i += 1;
    }
  }
  return Buffer.from(bytes).toString("utf8");
}

/**
 * `+++ b/<path>` の行から変更後のパスを得る（削除されたファイルは undefined）。空白を含むパスには
 * git が行末にタブを付け、`"` や `\` を含むパスは引用符で囲んでエスケープする。
 */
function diffTarget(line) {
  let target = line.slice(4).replace(/\t$/, "");
  if (target.length > 1 && target.startsWith('"') && target.endsWith('"'))
    target = unquote(target.slice(1, -1));
  return target === "/dev/null" ? undefined : target.replace(/^b\//, "");
}

/** `@@ -a,b +c,d @@` の行から、変更後の行番号（c から d 行）を得る。`-U0` なのでこれが追加・変更した行になる。 */
function hunkLines(line) {
  // `@@ -a,b +c,d @@` を空白で区切って読む（正規表現の入れ子の繰り返しを避ける）。
  const [open, , added, close] = line.split(" ");
  if (open !== "@@" || close !== "@@" || !added?.startsWith("+")) return [];
  const [startText, countText] = added.slice(1).split(",");
  const isNumber = (text) =>
    text !== "" && [...text].every((c) => c >= "0" && c <= "9");
  if (!isNumber(startText) || (countText !== undefined && !isNumber(countText)))
    return [];
  const start = Number(startText);
  const count = countText === undefined ? 1 : Number(countText);
  return Array.from({ length: count }, (_, i) => start + i);
}

/**
 * `git diff -U0` の出力から、ファイルごとに追加・変更した行番号を得る。`+++ ` はファイルの見出し
 * （`diff --git` から最初の `@@` まで）の中だけで読む（`++ ` で始まる行を足すと本文にも `+++ ` が出る）。
 */
function parseDiff(text) {
  const changed = new Map();
  let current = [];
  let inHeader = false;
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("diff --git ")) {
      inHeader = true;
      current = [];
    } else if (inHeader && line.startsWith("+++ ")) {
      const target = diffTarget(line);
      if (target !== undefined) changed.set(target, current);
    } else if (line.startsWith("@@ ")) {
      inHeader = false;
      current.push(...hunkLines(line));
    }
  }
  return changed;
}

/** 変更行のうち、カバレッジの計測対象になった行（LCOV に DA がある行）だけを数える。 */
function diffCoverage(changed, coverage) {
  const byFile = new Map();
  for (const data of coverage.values()) {
    for (const [path, lines] of Object.entries(data.files ?? {}))
      byFile.set(path, lines);
  }
  const files = [];
  for (const [path, lines] of changed) {
    const measured = byFile.get(path);
    if (!measured) continue;
    const covered = new Set(measured.covered);
    const missed = new Set(measured.missed);
    const hit = lines.filter((n) => covered.has(n));
    const miss = lines.filter((n) => missed.has(n));
    if (hit.length + miss.length > 0)
      files.push({ path, hit: hit.length, missed: miss });
  }
  const found = files.reduce((sum, f) => sum + f.hit + f.missed.length, 0);
  const hit = files.reduce((sum, f) => sum + f.hit, 0);
  return { found, hit, pct: percent(hit, found), files };
}

/** 連続する行番号を `10-12` の形にまとめる。 */
function ranges(numbers) {
  const parts = [];
  for (let i = 0; i < numbers.length;) {
    let j = i;
    while (
      j + 1 < numbers.length &&
      numbers.at(j + 1) === (numbers.at(j) ?? 0) + 1
    )
      j++;
    parts.push(
      i === j ? `${numbers.at(i)}` : `${numbers.at(i)}-${numbers.at(j)}`,
    );
    i = j + 1;
  }
  return parts.length === 0 ? "-" : parts.join(", ");
}

/** GitHub Actions のジョブの Summary とステップの出力へ書く（Actions の外では何もしない）。 */
function summary(markdown) {
  if (process.env.GITHUB_STEP_SUMMARY)
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${markdown}\n`);
}

function thresholdLabel(value) {
  return value === null ? "未設定" : `${value}%`;
}

function output(name, value) {
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
}

/** collect の引数（`[--base <dir>] <lcov>` の繰り返し）を、LCOV の場所と相対パスの起点の組にする。 */
function collectInputs(root, args) {
  const inputs = [];
  let base = root;
  for (let i = 0; i < args.length; i += 1) {
    const arg = args.at(i) ?? "";
    if (arg === "--base") {
      const dir = args.at(i + 1);
      if (dir === undefined)
        throw new UsageError("--base の後にディレクトリがありません");
      base = resolve(root, dir);
      i += 1;
    } else {
      const path = resolve(base, arg);
      inputs.push({ path, base, label: normalizePath(path, root) });
    }
  }
  return inputs;
}

function collect(root, stack, args) {
  const suite = args[0] === "--suite" ? args[1] : undefined;
  if (args[0] === "--suite") {
    if (suite !== "unit" && suite !== "integration")
      throw new UsageError("--suite は unit か integration にしてください");
    args = args.slice(2);
  }
  const inputs = collectInputs(root, args);
  if (!stack || inputs.length === 0)
    throw new UsageError(
      "使い方: collect <stack> [--suite unit|integration] [--base <dir>] <lcov> ...",
    );
  const dir = join(root, COVERAGE_DIR, suite ?? "");
  const out = join(dir, `${stack}.json`);
  const missing = inputs.filter((input) => !existsSync(input.path));
  if (missing.length > 0) {
    // テストが通った後に LCOV が無いのは出力先の設定の誤り（テストが0件なら、その前に unit が落ちる）。
    // 全部無いまま通すと閾値の判定も引き上げも黙って効かなくなり、一部だけ無いまま残りで計算すると、
    // 無いパッケージのコードが分母から消えて実際より高く出る。前回の結果も消して、失敗させる。
    rmSync(out, { force: true });
    for (const input of missing)
      console.error(
        `${stack}: ${input.label} が無いので、カバレッジを記録しませんでした（そのパッケージの LCOV の出力先の設定を確かめてください）`,
      );
    return 1;
  }
  // レポートの出力先は層ごとに分ける。LCOV の内容も保存し、元のレポートの削除や
  // パッケージの起点の違いに左右されず、同じ行・分岐を後で重複なく合算できるようにする。
  const records = inputs.map(({ path, base }) => ({
    text: readFileSync(path, "utf8"),
    base: relative(root, base),
  }));
  const parsed = parseLcov(
    records.map((record) => ({ ...record, base: resolve(root, record.base) })),
    root,
  );
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    out,
    `${JSON.stringify({ stack, source: inputs.map((input) => input.label), ...parsed, ...(suite ? { inputs: records } : {}) }, null, 2)}\n`,
  );
  console.log(
    `${stack}: 行カバレッジ ${format(parsed.lines.pct)}（${parsed.lines.hit}/${parsed.lines.found} 行）・分岐カバレッジ ${format(parsed.branches.pct)}（${parsed.branches.hit}/${parsed.branches.found} 分岐）`,
  );
  const label = LOCAL_UNIT_DIFF_LABELS.get(stack);
  if (suite === "unit" && label)
    reportUnitDiff(root, { stack, coverage: parsed, label });
  return 0;
}

/** unit と integration がそろったスタックを、LCOV の行・分岐の和集合で集計する。 */
function combine(root) {
  const suites = ["unit", "integration"].map((suite) => {
    const dir = join(root, COVERAGE_DIR, suite);
    return new Map(
      (existsSync(dir) ? readdirSync(dir) : [])
        .filter((name) => name.endsWith(".json"))
        .map((name) => [
          name.slice(0, -5),
          JSON.parse(readFileSync(join(dir, name), "utf8")),
        ]),
    );
  });
  const stacks = new Set(suites.flatMap((suite) => [...suite.keys()]));
  for (const stack of stacks) {
    const records = suites.map((suite) => suite.get(stack));
    if (records.some((record) => !record)) {
      rmSync(join(root, COVERAGE_DIR, `${stack}.json`), { force: true });
      throw new UsageError(
        `${stack}: unit と integration のカバレッジがそろっていません（check:full を実行してください）`,
      );
    }
    const parsed = parseLcov(
      records.flatMap((record) =>
        record.inputs.map((input) => ({
          ...input,
          base: resolve(root, input.base),
        })),
      ),
      root,
    );
    writeFileSync(
      join(root, COVERAGE_DIR, `${stack}.json`),
      `${JSON.stringify({ stack, source: records.flatMap((record) => record.source), ...parsed }, null, 2)}\n`,
    );
  }
  return 0;
}

/** 1種類の閾値（行か分岐）について判定する。失敗があれば true。 */
function checkMetric(coverage, thresholds, metric) {
  const { key, label } = metric;
  let failed = false;
  // 閾値のあるスタックのカバレッジが無いとき（LCOV が出なくなった・計測対象が 0 行）は失敗にする。
  // 黙って通すと、閾値の判定が外れたことに誰も気づかない。閾値が 0 のスタック（導入した直後で、初回の計測の
  // 前の値。テストがまだ無いこともある）は、下限が無いので落とさない。
  for (const [stack, threshold] of thresholds) {
    const data = coverage.get(stack);
    if (threshold > 0 && typeof (data && metric.pick(data))?.pct !== "number") {
      console.error(
        `${stack}: ${label}の閾値 ${threshold}% があるのに、カバレッジが記録されていません（${COVERAGE_DIR}/${stack}.json。スタックを外したなら ${THRESHOLDS} の ${key} からも消してください）`,
      );
      failed = true;
    }
  }
  for (const [stack, data] of coverage) {
    const measured = metric.pick(data);
    const pct = measured?.pct ?? null;
    const threshold = thresholds.get(stack);
    if (pct === null || !measured) continue;
    if (threshold === undefined) {
      console.log(
        `${stack}: ${label} ${format(pct)}（閾値は未設定。main の CI が初回の閾値を PR で提案します）`,
      );
    } else if (isBelow(measured, threshold)) {
      console.error(
        `${stack}: ${label} ${format(pct)} が閾値 ${threshold}% を下回っています（${THRESHOLDS} の ${key}）`,
      );
      failed = true;
    } else {
      console.log(`${stack}: ${label} ${format(pct)}（閾値 ${threshold}%）`);
    }
  }
  return failed;
}

function check(root) {
  const coverage = loadCoverage(root);
  const thresholds = loadThresholds(root);
  let failed = false;
  for (const metric of METRICS) {
    if (checkMetric(coverage, metric.thresholdsOf(thresholds), metric))
      failed = true;
  }
  if (coverage.size === 0)
    console.log("カバレッジを記録したスタックはありません");
  return failed ? 1 : 0;
}

function gitDiff(root, base, unitOnly) {
  return execFileSync(
    "git",
    [
      "-c",
      "core.quotePath=false",
      "diff",
      "--unified=0",
      "--no-color",
      "--no-ext-diff",
      "--dst-prefix=b/",
      ...(unitOnly ? ["--merge-base", base, "--"] : [`${base}...HEAD`]),
    ],
    { cwd: root, encoding: "utf8", maxBuffer: 256 * 1024 * 1024 },
  );
}

/** 比べる相手。`--base` > PR の base ブランチ（GitHub Actions の GITHUB_BASE_REF）> origin/main。 */
function diffBase(args) {
  if (args.length > 0) {
    // 知らない引数（`--base=main` 等）を黙って無視すると、違う相手と比べた数字を出してしまう。
    const [flag, base, ...rest] = args;
    if (flag !== "--base" || !base || base.startsWith("-") || rest.length > 0)
      throw new UsageError("使い方: diff [--base <ref>]");
    return base;
  }
  const ref = process.env.GITHUB_BASE_REF;
  return ref ? `origin/${ref}` : "origin/main";
}

function diff(root, args, unitReport) {
  const unitOnly = unitReport !== undefined;
  const base = diffBase(args);
  const { diff: threshold } = loadThresholds(root);
  const coverage = unitOnly
    ? new Map([[unitReport.stack, unitReport.coverage]])
    : loadCoverage(root);
  let text;
  try {
    text = gitDiff(root, base, unitOnly);
  } catch (error) {
    console.error(
      `${base} との差分を取れませんでした: ${String(error.message ?? error).trim()}`,
    );
    // 閾値が無ければ報告だけの検査なので、差分が取れなくても止めない。
    return threshold === null ? 0 : 2;
  }
  const result = diffCoverage(parseDiff(text), coverage);
  const thresholdText =
    threshold === null ? "未設定（報告のみ）" : `${threshold}%`;
  const lines = ["## 変更行のカバレッジ", ""];
  if (unitOnly)
    lines.push(
      `${unitReport.label} の unit のみの参考値です。CI は integration と合算して判定します。`,
      "",
    );
  if (coverage.size === 0) {
    lines.push("カバレッジを記録したスタックがありません。");
  } else if (result.found === 0) {
    lines.push(`${base} からの変更に、カバレッジの計測対象の行はありません。`);
  } else {
    lines.push(
      `${base} からの変更で計測対象になった ${result.found} 行のうち、テストが通ったのは ${result.hit} 行（**${format(result.pct)}**）。閾値: ${thresholdText}`,
      "",
      "| ファイル | 計測対象の変更行 | 通った行 | 通らなかった行 |",
      "| --- | --- | --- | --- |",
      ...result.files.map(
        (f) =>
          `| \`${f.path}\` | ${f.hit + f.missed.length} | ${f.hit} | ${ranges(f.missed)} |`,
      ),
    );
  }
  const markdown = lines.join("\n");
  console.log(markdown);
  summary(markdown);
  if (threshold !== null && result.found > 0 && isBelow(result, threshold)) {
    const advisoryPrefix = unitOnly
      ? `${unitReport.label} unit の参考値: `
      : "";
    console.error(
      `${advisoryPrefix}変更行のカバレッジ ${format(result.pct)} が閾値 ${threshold}% を下回っています（${THRESHOLDS} の diff）`,
    );
    // integration だけが通す行も未カバーに見えるため、unit の結果で push を止めない。
    return unitOnly ? 0 : 1;
  }
  return 0;
}

function reportUnitDiff(root, unitReport) {
  if (process.env.CI || !existsSync(join(root, ".git"))) return;
  // check だけでなく、check を上書きして unit タスクを呼ぶ導入先でも、今回の計測で報告する。
  // unit の参考値を判定できなくても、unit 自体が失敗したとは扱わない。
  const base = process.env.GUARDRAIL_DIFF_BASE;
  try {
    diff(root, base ? ["--base", base] : [], unitReport);
  } catch (error) {
    console.error(
      `${unitReport.label} の変更行のカバレッジを確認できませんでした: ${String(error)}`,
    );
  }
}

function raise(root) {
  const coverage = loadCoverage(root);
  const path = join(root, THRESHOLDS);
  const existing = readThresholdsFile(root);
  const thresholds = loadThresholds(root);
  const changes = proposeRaises(coverage, thresholds);
  if (changes.length === 0) {
    console.log("閾値を変える必要はありません");
    output("changed", "false");
    return 0;
  }
  for (const c of changes) c.metric.thresholdsOf(thresholds).set(c.stack, c.to);
  const sorted = (values) =>
    Object.fromEntries([...values].sort(([a], [b]) => a.localeCompare(b)));
  mkdirSync(join(root, ".guardrail"), { recursive: true });
  writeFileSync(
    path,
    `${JSON.stringify(
      {
        ...existing,
        total: sorted(thresholds.total),
        branch: sorted(thresholds.branch),
        diff: existing.diff ?? null,
      },
      null,
      2,
    )}\n`,
  );
  const body = [
    "main の実測カバレッジが閾値を上回っています。`.guardrail/thresholds.json` の閾値を、次のとおり引き上げられます。",
    "",
    "| スタック | 種類 | 現在の閾値 | 実測 | 新しい閾値 |",
    "| --- | --- | --- | --- | --- |",
    ...changes.map(
      (c) =>
        `| ${c.stack} | ${c.label} | ${thresholdLabel(c.from)} | ${format(c.pct)} | ${c.to}% |`,
    ),
    "",
    `行カバレッジ・分岐カバレッジのそれぞれについて、閾値の無いスタックには初回の値を、実測が閾値を${STEP}ポイント以上上回ったスタックには実測を${STEP}刻みで切り捨てた値を入れます。閾値は下げません。`,
    "",
    "手元で上げるには、`mise run check:full` の成功後に `mise run coverage:raise` を実行し、書き換わった `.guardrail/thresholds.json` を PR で出してください。",
  ].join("\n");
  mkdirSync(join(root, COVERAGE_DIR), { recursive: true });
  writeFileSync(join(root, RAISE_BODY), `${body}\n`);
  for (const c of changes)
    console.log(
      `${c.stack}: ${c.label} ${thresholdLabel(c.from)} → ${c.to}%（実測 ${format(c.pct)}）`,
    );
  output("changed", "true");
  return 0;
}

function run(command, args, root) {
  switch (command) {
    case "collect":
      return collect(root, args[0], args.slice(1));
    case "reset":
      rmSync(join(root, COVERAGE_DIR), { recursive: true, force: true });
      return 0;
    case "combine":
      return combine(root);
    case "check":
      return check(root);
    case "diff":
      return diff(root, args);
    case "raise":
      return raise(root);
    default:
      console.error(
        "使い方: guardrail-coverage.mjs collect <stack> [--suite unit|integration] [--base <dir>] <lcov> ... | reset | combine | check | diff [--base <ref>] | raise",
      );
      return 2;
  }
}

function main(argv) {
  const [command, ...args] = argv;
  try {
    return run(command, args, process.cwd());
  } catch (error) {
    if (!(error instanceof UsageError)) throw error;
    console.error(error.message);
    return 2;
  }
}

process.exitCode = main(process.argv.slice(2));
