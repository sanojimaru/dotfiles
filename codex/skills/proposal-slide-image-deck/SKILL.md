---
name: proposal-slide-image-deck
description: Create a Japanese B2B proposal deck as sequential raster slide images and a PDF from a text document, proposal outline, or slide-design Markdown. Use when the user asks for image-only slides, ChatGPT Image proposal slides, a PNG slide deck, or reproduction of the image-generation-and-brand-frame workflow; do not use when the primary deliverable must be an editable PPTX or Google Slides deck.
---

# Proposal Slide Image Deck

テキスト資料を、`提案スライド設計.md`、raw PNG、ブランドフレーム合成済み PNG、PDF の順に制作する。最終成果物は画像デッキであり、編集可能なスライドファイルではない。

## 入力を決める

- 既存の `提案スライド設計.md` があれば、それを正本にする。
- 提案骨子・企画書・任意テキストだけの場合は、先に `references/slide-design-format.md` に従って設計書を作る。
- 過去デッキを参照する場合は、本文・固有名詞・数値を複製せず、構図、情報量、説明順、図版の役割だけを流用する。`references/sample-selection-policy.md` を読む。
- 既定の Spike Studio フレームを使えない場合は、依頼者が指定したサンプル PPTX からブランドフレームを抽出する。手順は `references/brand-frame-policy.md` を読む。

## 制作手順

1. `1スライド1メッセージ` に分解し、設計書を作る。表紙、背景・課題、提案、仕組み、効果・導入計画のように、1枚に論点を混在させない。
2. 各スライドに構造化スライド定義（JSON）と自己完結した `ChatGPT入力用完成プロンプト` を置く。最低限の形式は `references/slide-design-format.md` を使う。
3. プロンプトを検証する。

```bash
python3 skills/proposal-slide-image-deck/scripts/validate_chatgpt_prompts.py \
  --file /absolute/path/to/proposal-slide-design.md
```

4. manifest を作る。出力先を指定すると、再実行先を明示できる。

```bash
python3 skills/proposal-slide-image-deck/scripts/extract_slide_prompts.py \
  --file /absolute/path/to/proposal-slide-design.md \
  --output-dir /absolute/path/to/proposal-slide-images
```

5. `manifest.json` の `slides` を `slide_no` の昇順で処理する。built-in `image_gen` は必ず同一会話内で**1枚ずつ**呼び、各結果を対応する `raw_target_path` に保存する。並列生成しない。

6. raw を1枚生成するごとに検査する。詳細は `references/image-generation-loop.md` を読む。

```bash
python3 skills/proposal-slide-image-deck/scripts/check_slide_layout.py \
  --manifest /absolute/path/to/proposal-slide-images/manifest.json \
  --slide 1
```

`STATUS: fail`、`text_overlap`、`safe_zone_overlap`、`edge_intrusion`、`label_body_overlap_risk` は修正してから次ページへ進む。日本語 OCR は補助的なので、必ず `view_image` でも文字・余白・情報欠落を確認する。1スライドは合計3回まで生成し、それでも解決しなければ `needs-human-review` として残す。

7. raw にブランドフレームを後合成する。

```bash
python3 skills/proposal-slide-image-deck/scripts/apply_brand_frame.py \
  --manifest /absolute/path/to/proposal-slide-images/manifest.json
```

8. 合成済み画像だけを PDF に束ねる。

```bash
python3 skills/proposal-slide-image-deck/scripts/build_slide_pdf.py \
  --manifest /absolute/path/to/proposal-slide-images/manifest.json
```

## ブランドと品質の必須条件

- ロゴ、機密表示、コピーライト、ページ番号は画像生成で描かせない。後合成で統一する。
- 各プロンプトにフレーム種別（`cover`、`body`、`body-confidential`）を指定し、フレームの safe zone に重要な文字・図版を置かない。
- raw と final を混同しない。PDF には raw を使わない。
- デッキ全体で配色、余白、文字組み、図形密度を揃える。ただし、各ページの構図まで単調に繰り返さない。
- 画像生成ツールが使えない場合は停止する。無断で別の画像生成経路へ切り替えない。

## 完了条件

次がそろい、blocking issue がないことを確認して完了する。

- `*_提案スライド設計.md`
- `*_slide-images/manifest.json`
- `*_slide-images/raw/slide-*.png`
- `*_slide-images/slide-*.png`
- `*_slide-images.pdf`

最終報告には、入力、設計書、manifest、raw/final の枚数、PDF、再生成ページ、残った warning、利用したフレームを記録する。
