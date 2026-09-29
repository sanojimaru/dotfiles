---
name: proposal-slide-design-markdown
description: Create and validate evidence-backed Japanese B2B proposal slide-design Markdown before image generation. Use when Codex needs to turn a proposal outline, source materials, or planning notes into `*_提案スライド設計.md`, define one message per slide, prepare self-contained Japanese image-generation prompts, track facts versus hypotheses, or hand a validated design to the `proposal-slide-image-deck` skill. Do not use when the primary task is generating slide images, applying brand frames, or building a PDF.
---

# Proposal Slide Design Markdown

提案の根拠資料から、画像生成の前段となる `*_提案スライド設計.md` を作る。

このスキルの編集正本は設計 Markdown である。

manifest は後続の画像デッキ工程のために抽出する派生成果物であり、手編集しない。

## 入力を確定する

- 根拠資料、提案骨子、顧客条件、または既存の設計 Markdown を受け取る。
- 既存の設計 Markdown があるときは、それを正本として更新する。
- サンプルデッキを参照するときは、構図、情報量、説明順、図版の役割だけを使う。
  本文、固有名詞、数値、顧客課題、結論、ロゴ、機密情報は流用しない。
  詳細は `../proposal-slide-image-deck/references/sample-selection-policy.md` を読む。
- 根拠資料が不足し、結論、数値、固有名詞を安全に確定できないときは、`open_issues` に残すか、依頼者へ確認する。
  推測で確定事実を補わない。

## 設計 Markdown を作る

作成前に `references/design-markdown-contract.md` を読む。

次の順で書く。

1. 本資料の目的と、根拠台帳を作る。
   `sources`、`confirmed_facts`、`proposal_hypotheses`、`open_issues` を分ける。
   `brand_profile` は `scripts/build_brand_profile.py` で作る。
2. 構成表で、各ページを `1スライド1メッセージ` に分解する。
   表紙、課題、提案、仕組み、効果、導入計画の論点を同じページに混在させない。
3. 各 `### Slide n` に、タイトル、言い切ること、構造化 JSON、`ChatGPT入力用完成プロンプト` を置く。
   JSON の `slide_no`、`title`、`message`、`frame_variant` は、見出しと構成表に一致させる。
4. 各スライドの `evidence_refs` に、主張と数値を支える `fact_id` または `hypothesis_id` を入れる。
   仮説を示すページは、仮説であることをプロンプト内でも読者に分かる表現にする。
5. `frame_variant` は `cover`、`body`、`body-confidential` から明示的に選ぶ。
   既定値による推測に頼らない。
6. 完成プロンプトには、16:9、日本語、正確に描く文字、説明文、ビジュアル、safe zone、後合成、禁止要素を含める。
   ロゴ、機密表示、コピーライト、ページ番号は画像生成で描かせない。

## ブランド情報を作る

既定の Spike Studio フレームを使うときは、次を実行して出力を根拠台帳の `brand_profile` に貼り付ける。

```bash
python3 scripts/build_brand_profile.py \
  --frame-spec ../proposal-slide-image-deck/assets/spike-studio-brand-frame/frame-spec.json \
  --brand-id spike-studio
```

カスタムブランドは、依頼者指定の PPTX からフレーム仕様を抽出してから扱う。

`../proposal-slide-image-deck/references/brand-frame-policy.md` を読んで、生成した frame spec を `--frame-spec` に指定する。

現行の画像デッキ skill は Spike Studio 固定の検証を含むため、カスタムブランドの manifest を後続工程へ渡す前に、既存 skill 側のブランド非依存化を完了させる。

## 検証する

設計 Markdown を書いたら、まず契約検証を行う。

```bash
python3 scripts/validate_design_markdown.py \
  --file /absolute/path/to/deck_提案スライド設計.md
```

`brand_id` が `spike-studio` のときだけ、既存の画像デッキ skill のプロンプト検証も行う。

```bash
python3 ../proposal-slide-image-deck/scripts/validate_chatgpt_prompts.py \
  --file /absolute/path/to/deck_提案スライド設計.md
```

両方が通ったら、manifest を抽出する。

```bash
python3 ../proposal-slide-image-deck/scripts/extract_slide_prompts.py \
  --file /absolute/path/to/deck_提案スライド設計.md \
  --output-dir /absolute/path/to/deck_slide-images \
  --brand-frame-spec /absolute/path/to/frame-spec.json
```

生成直後に manifest の実行契約を検証する。

```bash
python3 scripts/validate_design_manifest.py \
  --manifest /absolute/path/to/deck_slide-images/manifest.json \
  --design /absolute/path/to/deck_提案スライド設計.md
```

検証エラーは設計 Markdown を直してから extractor を再実行する。

manifest を直接直さない。

## 後続工程へ渡す

次のすべてがそろったときだけ、`proposal-slide-image-deck` を使う。

- `*_提案スライド設計.md`
- 設計契約 validator の成功結果
- 既定ブランドでは既存プロンプト validator の成功結果
- manifest validator の成功結果
- 実在し、digest が根拠台帳と一致するブランド frame spec

このスキルは raw PNG、合成済み PNG、PDF を作らない。

画像生成、ページごとの目視確認、再生成、後合成、PDF 化は `proposal-slide-image-deck` の責務である。

## 完了報告

最終報告には、入力資料、確定事実数、仮説数、未確定事項、設計 Markdown、スライド数、manifest、ブランド ID、frame spec の digest、検証結果を記録する。
