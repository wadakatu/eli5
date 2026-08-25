# eli5

`/eli5` スキルで作った HTML 解説ページの置き場。

閲覧: https://www.wadakatu.dev/eli5/

## 追加のしかた

通常は Claude Code の `eli5-archive` スキルが自動でやる。手でやる場合は、
生成された HTML を `<category>/YYYY-MM-DD-slug.html` の名前で置いて push するだけ。

```sh
cp /path/to/generated.html ~/www/eli5/network/2026-08-25-how-tcp-works.html
```

`index.html` が Jekyll の `site.static_files` を走査して一覧を自動生成するので、
インデックスの手編集は不要。ディレクトリ名がカテゴリ見出しに、
ファイル名の日付とスラッグが各行の表示になる。カテゴリはディレクトリを掘れば増え、
中身が空になれば見出しごと消える。

## 決まりごと

- ファイル名・ディレクトリ名は英語の kebab-case（URL が percent-encode されないように）
- HTML は必ずカテゴリのディレクトリ配下に置く（直下に置くと見出しが壊れる）
- 保存する HTML に front matter を足さない（Jekyll がページ扱いして一覧から消え、
  中身の `{{ }}` が Liquid 展開されて壊れる）
