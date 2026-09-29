# ブランドフレーム方針

既定アセットは `assets/spike-studio-brand-frame/` にある。`frame-spec.json` が位置と safe zone の正本であり、次のフレームを使う。

- `cover`: 表紙。右上に機密表示、右下寄りにロゴ。
- `body`: 通常ページ。右上にロゴ。
- `body-confidential`: 章扉・機密性が高いページ。右上帯に機密表示とロゴ。

ロゴ、機密表示、コピーライト、ページ番号は生成画像に含めない。`apply_brand_frame.py` が後合成し、ページ番号もそこで描画する。

別ブランドを使う場合だけ、依頼者が指定した PPTX を入力にして次を実行する。

```bash
python3 skills/proposal-slide-image-deck/scripts/extract_brand_frame_spec.py \
  --pptx /absolute/path/to/sample.pptx \
  --out-dir /absolute/path/to/brand-frame \
  --force

python3 skills/proposal-slide-image-deck/scripts/render_brand_frame_assets.py \
  --spec /absolute/path/to/brand-frame/frame-spec.json
```

その後、manifest 作成時に `--brand-frame-spec` で新しい spec を指定する。フレーム抽出・合成スクリプトは macOS の AppKit を利用する。
