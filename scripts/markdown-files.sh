#!/usr/bin/env sh
# development のガードレール: markdown の検査と整形の対象を、NUL 区切りで出す。
# 対象は git が無視しない Markdown（追跡しているものと、無視されていない未追跡のもの）にする。
# markdownlint-cli2 の gitignore と Prettier は .gitignore しか読まないので、グローバルの gitignore
# （core.excludesFile）や .git/info/exclude で外した手元だけの文書（CLAUDE.local.md など）まで
# 検査してしまうため（#258）。除外の設定（.markdownlint-cli2.jsonc の ignores・.prettierignore）は、
# それぞれのツールが渡されたファイルにも当てる。
set -eu
listed=$(mktemp)
trap 'rm -f "$listed"' EXIT
# git の失敗で対象が空になり、検査が素通りしないよう、一度ファイルに受けてから読む。
git ls-files -z --cached --others --exclude-standard -- '*.md' >"$listed"
# 追跡したまま消したファイルも ls-files に出るので、今あるものだけを残す。シンボリックリンクは、
# Prettier が明示されると失敗するので除く（リンク先がリポジトリにあれば、そちらを検査する）。
# 先頭に ./ を付けて、- で始まるファイル名をオプションと読ませない。
xargs -0 sh -c 'for f; do if [ -f "$f" ] && [ ! -L "$f" ]; then printf "./%s\0" "$f"; fi; done' sh <"$listed"
