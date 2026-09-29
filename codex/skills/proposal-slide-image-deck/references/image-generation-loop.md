# 画像生成と評価ループ

1ページずつ、同じ会話コンテキストで次を繰り返す。

1. manifest の `final_prompt` を使って raw PNG を生成する。
2. `raw_target_path` へ保存する。
3. `check_slide_layout.py` を実行する。
4. `view_image` で日本語の可読性、事実・数値の欠落、ブランド safe zone、デッキとの統一感を確認する。
5. fail または重要な目視不良なら、原因を1つか2つに絞ってプロンプトを直し、設計書と manifest の両方を更新して再生成する。

以下は必ず解消する。

- `text_overlap`
- `safe_zone_overlap`
- `edge_intrusion`
- `label_body_overlap_risk`
- 表題・重要数値・結論の欠落、または読めない日本語

`left_column_underused`、`missing_text_density`、`vertical_whitespace` は警告であっても、情報量が必要なスライドでは改善する。再生成は合計3回までとし、残る問題は当該ページ番号と理由を `needs-human-review` として報告する。
