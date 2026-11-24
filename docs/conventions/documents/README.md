# 日本語の技術文書の規則

文書を書く・直す人やエージェントと、文書を診断する人やエージェントが共通して読む規則である。出典とライセンスは [NOTICE](NOTICE.md) にある。

| ファイル                               | 読む場面                                             |
| -------------------------------------- | ---------------------------------------------------- |
| [document-types.md](document-types.md) | 文書の区分（stock・flow・record）と種類を決める      |
| [types/](types/)                       | 種類ごとの役割と、説明すべき内容を確かめる           |
| [structure.md](structure.md)           | 節の組み方、本文の形、図と表を決める                 |
| [accuracy.md](accuracy.md)             | 実態・前提・用語と、作業状態・経緯の保存先を確かめる |

`types/` の下は、書く文書に合うカテゴリのファイルを1つだけ読む。どれを読むかは [document-types.md](document-types.md#カテゴリから参照先を引く) で引く。

日本語の推敲は [yomiyasu](https://github.com/nanaism/yomiyasu) に任せ、このディレクトリには推敲の規則を複製しない。
