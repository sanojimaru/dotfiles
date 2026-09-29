# 提案スライド設計 Markdown 契約

## 編集正本

`*_提案スライド設計.md` を唯一の編集正本にする。

`manifest.json` は extractor が生成する実行用の派生成果物であり、直接編集しない。

## 文書構造

次の見出しをこの順で置く。

```text
# {デッキ名} 提案スライド設計
## 0. 本資料の目的
## 0.1 根拠台帳
## 1. スライド全体の方針
## 2. スライド構成
## 3. スライド別プロンプト
### Slide 1
```

構成表は次の列を使う。

```text
| # | タイトル | 1枚で言い切ること | フレーム種別 |
```

## 根拠台帳

`## 0.1 根拠台帳` の直下に JSON コードブロックを置く。

```json
{
  "sources": [
    {
      "source_id": "S1",
      "locator": "資料名、URL、またはファイルパス",
      "retrieved_at": "2026-07-13"
    }
  ],
  "confirmed_facts": [
    {
      "fact_id": "F1",
      "statement": "根拠資料から確認した事実",
      "source_ids": ["S1"],
      "as_of": "2026-07-13"
    }
  ],
  "proposal_hypotheses": [
    {
      "hypothesis_id": "H1",
      "statement": "提案として検証する仮説",
      "based_on": ["F1"],
      "validation": "検証方法または次の判断条件",
      "display_as_hypothesis": true
    }
  ],
  "open_issues": [
    {
      "issue_id": "O1",
      "question": "未確定の質問",
      "impact": "提案へ与える影響",
      "owner": "確認担当",
      "decision_gate": "確定が必要な時点"
    }
  ],
  "brand_profile": {}
}
```

`sources` と `confirmed_facts` は一件以上必要である。

`proposal_hypotheses` と `open_issues` は空配列にできる。

## ブランドプロファイル

`brand_profile` は `scripts/build_brand_profile.py` の出力を使う。

frame spec が正本である。

プロファイルには、brand ID、frame spec のパス、schema version、SHA-256 digest、キャンバス、variant、解決済み safe zone、後合成する要素を残す。

profile 内の digest または safe zone が frame spec と一致しないとき、設計 Markdown は不正とする。

## スライド定義

各スライドに、次の JSON を置く。

```json
{
  "slide_no": 1,
  "title": "スライドタイトル",
  "frame_variant": "cover",
  "message": "1枚で言い切る主張",
  "evidence_refs": ["F1", "H1"],
  "layout": "読み順と要素配置",
  "must_include": ["正確に描く文字"],
  "visuals": ["図版または図解の役割"],
  "safe_zone_notes": "右上・右下・左下の safe zone を空ける"
}
```

`slide_no`、`title`、`message`、`frame_variant` は、スライド見出しと構成表で一致させる。

`evidence_refs` は、根拠台帳の `fact_id` または `hypothesis_id` を一件以上含める。

## 完成プロンプト

各スライドに `#### ChatGPT入力用完成プロンプト` と `text` コードブロックを置く。

プロンプトには次の見出しをすべて含める。

```text
デザインの方向:
レイアウト:
必ず入れたい文字:
スライドに載せる説明文:
ビジュアル指示:
ブランドフレーム前提:
避けること:
配色と文字組み:
仕上がり条件:
```

プロンプトには、16:9、日本語、タイトル、主張、`must_include` の全要素、選んだ frame variant、safe zone、後合成、描画禁止を明記する。

未置換の `{...}` は残さない。

## manifest の受け渡し

extractor が出力する manifest は `zuno.proposal-slide-imagegen-manifest.v2` を使う。

各スライドには、連番の `slide_no`、有効な `frame_variant`、`final_prompt`、raw と final の出力パスが必要である。

frame spec のパスは実在し、すべての利用 variant を含む必要がある。

manifest validator には対応する設計 Markdown を `--design` で渡す。

manifest の frame spec のパスと digest が、設計 Markdown の `brand_profile` と一致しないときは不正とする。
