# eli5

`/eli5` スキルで作った HTML 解説ページの置き場。

閲覧: https://www.wadakatu.dev/eli5/

## 仕組み

**何もビルドしない。** GitHub Pages はブランチをそのまま配信し、`.nojekyll` が Jekyll を止める。
つまり **commit した内容がそのまま配信される**。`index.html` も実ファイルで、
`tools/archive.py` がディスクの中身から書き出す（だからローカルで開いて確認できる）。

```
eli5.css              全記事に共通のデザイン。色・書体・部品はここだけ
tools/archive.py      保存時に走る唯一の道具
pages.json            一覧に出すタイトルと概要
<category>/*.html     記事。フラグメントで書き、archive.py が外枠を被せる
```

記事ごとに違ってよいのは**絵と文だけ**。以前は 1 本ごとにパレットも書体も構造も作り込んでいて、
同じ「番号付きの節」を `step` `beat` `scene` `page` と 4 通りに呼んでいた。

## 追加のしかた

通常は Claude Code の `eli5` スキルが書き、`eli5-archive` スキルが保存する。手でやる場合:

```sh
cp /path/to/generated.html ~/www/eli5/network/2026-08-25-how-tcp-works.html
python3 tools/archive.py network/2026-08-25-how-tcp-works.html
```

`archive.py` は 4 つやる。何度通しても結果は変わらない。

1. **private な情報が混じっていないか見る** — 見つけたら保存を拒否する（下記）
2. **共通の外枠を被せる** — doctype・言語・フォント・`eli5.css`・一覧へ戻る線。
   すでに組み立て済みのページは一度フラグメントに戻してから組み直すので、
   **外枠を変えたら `--rebuild` で全記事に反映できる**
3. **`pages.json` に登録する** — `<title>` と `<meta name="description">` を拾う
   （`--summary` で上書きできる）
4. **`index.html` を書き直す**

| コマンド | すること |
|---|---|
| `--reindex` | ディスクから `index.html` を作り直す（手で足した / 消したとき） |
| `--rebuild` | 全記事に外枠を当て直す（`eli5.css` の追加や外枠の変更後） |
| `--scan` | 全記事を private 情報について棚卸し |
| `--selftest` | 組み立て・冪等性・検査パターンの確認 |

## デザイン

`eli5.css` が全部持っている。記事側の `<style>` は**自分の絵を動かす / 塗るときだけ**。
パレット・書体・`e-` の見た目は上書きしない。

絵は**トークンで塗る**（`var(--e-ink)` `var(--e-accent)` `var(--e-warn)` `var(--e-mark)` …）。
リテラルの色で描いた絵はダークモードで消える。語彙は `eli5.css` のコメントと
`~/.claude/skills/eli5/SKILL.md` にある。

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

## 決まりごと

- ファイル名・ディレクトリ名は英語の kebab-case（URL が percent-encode されないように）
- HTML は必ずカテゴリのディレクトリ配下に置く（カテゴリ見出しが壊れる。
  外枠の `../eli5.css` も 1 階層であることに依存している）
- `index.html` を手で編集しない。`archive.py` が上書きする
- 記事に戻るリンクを手で書かない。`archive.py` が入れる
- private リポジトリの名前・ticket 番号・内部識別子を記事に残さない（検査は補助であって
  保証ではない）

## 手を入れたら

```sh
python3 tools/archive.py --selftest
```
