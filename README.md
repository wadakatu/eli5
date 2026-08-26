# eli5

`/eli5` スキルで作った HTML 解説ページの置き場。

閲覧: https://www.wadakatu.dev/eli5/

## 追加のしかた

通常は Claude Code の `eli5-archive` スキルが自動でやる。手でやる場合は、
生成された HTML を `<category>/YYYY-MM-DD-slug.html` の名前で置いてから、
`_tools/archive.py` を通して push する。

```sh
cp /path/to/generated.html ~/www/eli5/network/2026-08-25-how-tcp-works.html
python3 _tools/archive.py network/2026-08-25-how-tcp-works.html \
  --summary "TCP が三回の握手で接続を作る理由と、その間に何が確かめられているか"
```

スクリプトは 4 つやる。何度通しても結果は変わらない。

1. **private な情報が混じっていないか見る** — 見つけたら保存を拒否する（下記）
2. **完全な文書に整える** — Artifact 用に書いた HTML は `<!doctype>` も `<head>` も
   持たない断片で、そのまま配信すると quirks mode になり `lang` も付かない。断片なら
   包み、最初から完全な文書ならそのまま通す
3. **戻る線を差し込む** — `chrome.css` への `<link>` と、一覧に戻る `<a>` の 2 行
4. **`_data/pages.json` に登録する** — `<title>` は自動で拾い、`--summary` の一行を添える

## private リポジトリの情報を出さない

このリポジトリは public で、解説は private リポジトリで作業しながら書かれる。
だから ticket 番号やサービス名が、誰も公開の判断をしないまま footer や eyebrow から漏れる。
実際、最初の 5 本のうち 3 本に repo 名・issue 番号・内部クラス名が入っていた。

保存時に検査し、見つけたら**拒否する**（消さない。消すと文が壊れるし、消し漏れたときに
気づけない）。

- 機械的に見つかるもの: ticket 参照（`PR #123`）、`github.com/owner/repo`、ローカルパス、
  メールアドレス、内部ホスト名、そして `~/.config/eli5/private-terms.txt` に列挙した固有名
- 見つからないもの: 教えていない内部クラス名・ストア名・エンドポイント名

つまり **検査は部分的**。保存の前に本文を読んで、private な repo / サービス / クラス /
チケットを指す語を一般名詞に言い換えること。

用語リストを repo に置かないのは、private な名前の一覧そのものが同じ情報を漏らすから。
新しい private リポジトリの話を書いたら、そのつどリストに足す。

全ページの棚卸し:

```sh
python3 _tools/archive.py --scan
```

## 一覧の作られかた

`index.html` が Jekyll の `site.static_files` を走査して自動生成する。ディレクトリ名が
カテゴリ見出しに、ファイル名の日付が各行の日付になる。カテゴリはディレクトリを掘れば増え、
中身が空になれば見出しごと消える。**インデックスの手編集は不要。**

静的ファイルは Liquid から中身を読めないので、タイトルと概要だけは `_data/pages.json`
から引く。これは足すだけの補強で、登録が無いページもスラッグ表示で一覧に残る。

`/eli5` の付けるタイトルは「組織を選ぶ引換券」のように比喩的で、一覧で見ても中身が
分からない。概要は**それを補うための一行**なので、比喩ではなく具体的な題材を書く。

## 決まりごと

- ファイル名・ディレクトリ名は英語の kebab-case（URL が percent-encode されないように）
- HTML は必ずカテゴリのディレクトリ配下に置く（直下に置くと見出しが壊れる。
  `../chrome.css` という戻る線の相対パスも 1 階層であることに依存している）
- 保存する HTML に front matter を足さない（Jekyll がページ扱いして一覧から消え、
  中身の `{{ }}` が Liquid 展開されて壊れる）
- 記事に戻るリンクを手で書かない。`_tools/archive.py` が入れる。見た目を変えたいときは
  `chrome.css` だけ直せば全記事に効く
- private リポジトリの名前・ticket 番号・内部識別子を記事に残さない（検査は補助であって
  保証ではない）
- `_` で始まるディレクトリは Jekyll が公開対象から外す。`_tools/` `_data/` はそのため

## 手を入れたら

```sh
python3 _tools/archive.py --selftest
```
