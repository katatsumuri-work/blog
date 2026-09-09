---
title: 'テーマなし Hugo でブログを組む ― タクソノミーのレイアウト名が直感と逆だった話'
slug: 'hugo-themeless-blog'
date: 2026-09-12T09:00:00+09:00
categories: ['tech']
tags: ['hugo']
draft: false
---

このブログは Hugo で作っていますが、**テーマを一切入れていません**。`layouts/` に自分で 7 ファイル書いただけです。

その過程で 1 つ、はっきりハマったところがありました。**カテゴリの個別ページが空になる**という症状で、原因は Hugo のレイアウト名が（少なくとも私の）直感と逆だったことです。同じところで止まる人がいそうなので、構成の紹介がてら書き残しておきます。

## なぜテーマを入れなかったか

理由は 2 つです。

1 つは、**全部わかっている状態にしたかった**こと。テーマを入れると、表示がおかしいときに「自分の設定が悪いのか、テーマの仕様なのか」を切り分けるところから始まります。自分で書いた 7 ファイルなら、少なくとも原因は自分の中にあります。

もう 1 つは、**見た目の方向性が「飾らない」**だったからです。社内では「老人会風」と呼んでいます。serif で、段組は狭く、リンクは青と紫のまま。

```css
/* 老人会風: 飾りすぎず、文章を読みやすく。serif・狭めの段組・古典的なリンク色。 */
body {
  max-width: 720px;
  font-family: Georgia, 'Times New Roman', 'Hiragino Mincho ProN', 'Yu Mincho', serif;
  line-height: 1.9;
  color: #1a1a1a;
  background: #fffef9;
}

a { color: #0000ee; }
a:visited { color: #551a8b; }
```

訪問済みリンクの紫を残しているのは、**読んだ記事が一目でわかる**からです。今どきのサイトはここを潰しがちですが、読み物としては残っているほうが親切だと思っています。

こういう方向性だと、テーマを入れてから削る作業のほうが大変になります。

## ハマったところ: `terms.html` と `taxonomy.html`

本題です。カテゴリを整理していたとき、`/categories/zatsudan/` を開くと**記事が 1 件も出ない**状態になりました。`/categories/` のほうは正しく出ています。

原因は、2 つのレイアウトの割り当てを取り違えていたことでした。名前から受ける印象と、実際の役割が逆なんです。

| ファイル | 実際に使われるページ | 中身 |
|---|---|---|
| `terms.html` | `/categories/`（**一覧**） | カテゴリの一覧と件数 |
| `taxonomy.html` | `/categories/zatsudan/`（**個別**） | そのカテゴリに属する記事一覧 |

`taxonomy.html` という名前だと「タクソノミーそのもの＝カテゴリの一覧ページ」を、`terms.html` だと「ターム（＝個々のカテゴリ）のページ」を想像しませんか。私はそう読んで、逆に書いていました。

結果、件数表示のテンプレートが個別ページに当たり、`{{ range .Data.Terms.ByCount }}` が個別ページでは空になるので、**何も出ない**という症状になっていました。

### さらにややこしい: 新しいレイアウトでは名前が入れ替わっている

この記事を書きながら公式ドキュメントを読み直して気づいたのですが、**新しいレイアウト配置では名前が整理されていて、`taxonomy.html` の指すページが逆になっています**。

| 配置 | タームの一覧（`/categories/`） | そのタームの記事一覧（`/categories/tech/`） |
|---|---|---|
| 旧（`layouts/_default/`） | `terms.html` | **`taxonomy.html`** |
| 新（`layouts/` 直下） | **`taxonomy.html`** | `term.html` |

新しいほうは「taxonomy＝タクソノミー全体の一覧」「term＝個々のターム」で、名前と役割が素直に対応しています。名前としては明らかに改善されているのですが、**`taxonomy.html` という同じファイル名が新旧で別のページを指す**ので、移行するときは注意が必要です。うっかり中身をそのまま移すと、また空のページができあがります。

現行の公式ドキュメントはこう説明しています。

> A taxonomy template renders a list of terms in a taxonomy.
> A term template renders a list of pages associated with a term.

このブログはまだ旧配置（`layouts/_default/`）のままで、それで動いています。後方互換が効いているので急ぐ必要はありませんが、いずれ移すときはこの表を見返すつもりです。

参考: [Hugo - Template types](https://gohugo.io/templates/types/)

正しく割り当て直すと、それぞれこうなります。一覧側は `.Data.Terms.ByCount` を回します。

```go-html-template
{{/* layouts/_default/terms.html … /categories/ に当たる */}}
<ul class="term-list">
  {{ range .Data.Terms.ByCount }}
  <li>
    <a href="{{ .Page.RelPermalink }}">{{ .Page.Title }}</a>（{{ .Count }}）
  </li>
  {{ end }}
</ul>
```

個別側はふつうに `.Pages` を回すだけです。

```go-html-template
{{/* layouts/_default/taxonomy.html … /categories/zatsudan/ に当たる */}}
<ul class="post-list">
  {{ range .Pages }}
  <li>
    <time datetime="{{ .Date.Format "2006-01-02" }}">{{ .Date.Format "2006-01-02" }}</time>
    <a href="{{ .RelPermalink }}">{{ .Title }}</a>
  </li>
  {{ end }}
</ul>
```

**エラーにならず、ただ空になる**のがこの手のハマりの厄介なところです。ビルドは通るので、ブラウザで個別ページを開くまで気づけません。テーマを使っていれば踏まない穴ですが、踏んだおかげで両者の役割は忘れなくなりました。

## パーマリンクとアーカイブ

記事の URL は日付階層にしています。

```toml
[permalinks]
  posts = '/:year/:month/:day/:slug/'
```

`slug` は frontmatter の値を使うので、日本語タイトルでも URL は英語スラッグに保てます。

アーカイブは `GroupByDate` を二段で回して、年 → 月にまとめています。

```go-html-template
{{ $posts := where .Site.RegularPages "Section" "posts" }}
{{ range $posts.GroupByDate "2006" }}
  <h2>{{ .Key }}年</h2>
  {{ range .Pages.GroupByDate "2006-01" }}
    <h3>{{ dateFormat "1月" (printf "%s-01" .Key) }}</h3>
    ...
  {{ end }}
{{ end }}
```

月見出しで `printf "%s-01"` と日を足しているのは、`GroupByDate "2006-01"` のキーが `2026-09` という日付として不完全な文字列で返るためです。そのままでは `dateFormat` に渡せないので、`-01` を足して日付にしてから「9月」に整形しています。

## タグを小文字のまま出す

Hugo は既定で一覧の見出しを先頭大文字にします。ただこのブログのタグは `cloud-run` や `github-actions` のような**小文字スラッグをそのまま見せたい**ので、切っています。

```toml
capitalizeListTitles = false
```

一方でカテゴリは日本語で見せたいので、`content/categories/tech/_index.md` に `title: 技術` を書いています。**URL は英語スラッグ、表示は日本語**という使い分けです。

## ページネーション

これは設定 1 行と、テンプレート側で `.Paginate` を呼ぶだけです。

```toml
[pagination]
  pagerSize = 14
```

```go-html-template
{{ $paginator := .Paginate (where .Site.RegularPages "Section" "posts") }}
{{ range $paginator.Pages }} ... {{ end }}
```

参考: [Hugo - Pagination](https://gohugo.io/templates/pagination/)

## まとめ

- テーマなしでも `layouts/` に 7 ファイルで一通り動きます。全部自分で把握できる安心感があります
- 旧配置（`layouts/_default/`）では **`terms.html` が一覧、`taxonomy.html` が個別**。名前の印象と逆です
- 新配置では **`taxonomy.html` が一覧、`term.html` が個別**に整理されています。同じ `taxonomy.html` が別物を指すので、移行時は要注意です
- レイアウトの取り違えは**エラーではなく「空」**として出ます。ビルドが通っても、実際にページを開いて確かめたほうがいいです
- `capitalizeListTitles` や `_index.md` の `title` で、URL と表示名を分けられます

凝ったことをしなければ、テーマなしは思ったより現実的でした。同じように素から組む人の参考になればと思います。
