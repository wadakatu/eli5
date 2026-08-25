# eli5

`/eli5` スキルで作った HTML 解説ページの置き場。

閲覧: https://www.wadakatu.dev/eli5/

## 追加のしかた

生成された HTML を `YYYY-MM-DD-slug.html` の名前でリポジトリ直下に置いて push するだけ。
`index.html` が Jekyll の `site.static_files` を走査して一覧を自動生成するので、
インデックスの手編集は不要。

```sh
cp /path/to/generated.html ~/www/eli5/2026-08-25-how-tcp-works.html
cd ~/www/eli5 && git add -A && git commit -m "Add: how TCP works" && git push
```

ファイル名の日付とスラッグがそのまま一覧の表示になる。
