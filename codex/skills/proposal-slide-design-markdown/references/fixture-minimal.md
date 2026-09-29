# 受注判断を早める 提案スライド設計

## 0. 本資料の目的

初回商談後の意思決定者に、短期検証の提案内容と判断材料を伝える。

## 0.1 根拠台帳

```json
{
  "sources": [
    {
      "source_id": "S1",
      "locator": "営業ヒアリングメモ",
      "retrieved_at": "2026-07-13"
    }
  ],
  "confirmed_facts": [
    {
      "fact_id": "F1",
      "statement": "意思決定者は導入効果と開始までの期間を判断材料にしている。",
      "source_ids": ["S1"],
      "as_of": "2026-07-13"
    }
  ],
  "proposal_hypotheses": [],
  "open_issues": [],
  "brand_profile": {
    "brand_id": "spike-studio",
    "frame_spec": {
      "path": "../../proposal-slide-image-deck/assets/spike-studio-brand-frame/frame-spec.json",
      "schema_version": "zuno.proposal-slide-brand-frame.v1",
      "sha256": "1fbd0c4a3b8ca68d25a48f8ddb27cee1263fd7d5dd9d42c88af8b7b700037b42"
    },
    "canvas": {
      "aspect_ratio": "16:9",
      "width_px": 1920,
      "height_px": 1080,
      "coordinate_system": "percent"
    },
    "allowed_frame_variants": ["cover", "body", "body-confidential"],
    "variants": {
      "cover": {
        "safe_zones": [
          {"label": "cover-1", "box_pct": {"left_pct": 74.5, "top_pct": 9.4, "width_pct": 19.1, "height_pct": 7.7}},
          {"label": "cover-2", "box_pct": {"left_pct": 67.4, "top_pct": 83.6, "width_pct": 26.3, "height_pct": 7.2}},
          {"label": "footer", "box_pct": {"left_pct": 2.1, "top_pct": 93.6, "width_pct": 55.8, "height_pct": 6.0}},
          {"label": "page-number", "box_pct": {"left_pct": 92.7, "top_pct": 90.7, "width_pct": 6.0, "height_pct": 7.7}}
        ]
      },
      "body": {
        "safe_zones": [
          {"label": "body-1", "box_pct": {"left_pct": 81.6, "top_pct": 4.4, "width_pct": 15.5, "height_pct": 4.2}},
          {"label": "footer", "box_pct": {"left_pct": 2.1, "top_pct": 93.6, "width_pct": 55.8, "height_pct": 6.0}},
          {"label": "page-number", "box_pct": {"left_pct": 92.7, "top_pct": 90.7, "width_pct": 6.0, "height_pct": 7.7}}
        ]
      },
      "body-confidential": {
        "safe_zones": [
          {"label": "body-confidential-1", "box_pct": {"left_pct": 70.1, "top_pct": 4.4, "width_pct": 10.5, "height_pct": 4.2}},
          {"label": "body-confidential-2", "box_pct": {"left_pct": 81.6, "top_pct": 4.4, "width_pct": 15.5, "height_pct": 4.2}},
          {"label": "footer", "box_pct": {"left_pct": 2.1, "top_pct": 93.6, "width_pct": 55.8, "height_pct": 6.0}},
          {"label": "page-number", "box_pct": {"left_pct": 92.7, "top_pct": 90.7, "width_pct": 6.0, "height_pct": 7.7}}
        ]
      }
    },
    "overlay": {
      "mode": "post-generate",
      "do_not_render": ["logo", "confidential", "copyright", "page_number"]
    }
  }
}
```

## 1. スライド全体の方針

### 想定枚数

- 1枚

### トンマナ

- 落ち着いた日本語 B2B 提案資料

### 画像生成で避けること

- ロゴ、機密表示、コピーライト、ページ番号を描かない

### 生成時の共通ルール

- 16:9、日本語、重要要素は safe zone を避ける

## 2. スライド構成

| # | タイトル | 1枚で言い切ること | フレーム種別 |
| --- | --- | --- | --- |
| 1 | まず短期検証で判断材料をそろえる | 導入効果と開始までの期間を短期検証で可視化する | cover |

## 3. スライド別プロンプト

### Slide 1

#### タイトル

`まず短期検証で判断材料をそろえる`

#### このスライドで言い切ること

導入効果と開始までの期間を短期検証で可視化する

#### 構造化スライド定義 (JSON)

```json
{
  "slide_no": 1,
  "title": "まず短期検証で判断材料をそろえる",
  "frame_variant": "cover",
  "message": "導入効果と開始までの期間を短期検証で可視化する",
  "evidence_refs": ["F1"],
  "layout": "中央に短期検証の流れを置き、左右に導入効果と開始までの期間を置く。",
  "must_include": ["まず短期検証で判断材料をそろえる"],
  "visuals": ["短期検証の流れを示す三段階の概念図"],
  "safe_zone_notes": "右上・右下・左下の safe zone を空ける"
}
```

#### ChatGPT入力用完成プロンプト

```text
16:9 の日本語 B2B 提案スライドを作成してください。

デザインの方向:
- 落ち着いた日本語 B2B 提案資料にする。

レイアウト:
- 中央に短期検証の流れを置き、左右に導入効果と開始までの期間を置く。

必ず入れたい文字:
- まず短期検証で判断材料をそろえる

スライドに載せる説明文:
- 導入効果と開始までの期間を短期検証で可視化する

ビジュアル指示:
- 短期検証の流れを示す三段階の概念図を描く。

ブランドフレーム前提:
- SPIKE STUDIO ロゴ、CONFIDENTIAL、コピーライト、ページ番号は描画しない。
- 生成後に cover の透過フレームを合成する。
- 右上・右下・左下の safe zone に重要な要素を置かない。

避けること:
- 小さすぎる文字、文章の密集、装飾過多を避ける。

配色と文字組み:
- 白を基調に緑のアクセントを使い、余白を広く取る。

仕上がり条件:
- 日本語が正しく読め、主張が一目で分かる。
```
