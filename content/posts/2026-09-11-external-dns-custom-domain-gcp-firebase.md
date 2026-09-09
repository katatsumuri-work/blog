---
title: '外部 DNS（ムームードメイン）のまま GCP と Firebase にカスタムドメインを生やす ― 足すレコード早見表'
slug: 'external-dns-custom-domain-gcp-firebase'
date: 2026-09-11T09:00:00+09:00
categories: ['tech']
tags: ['dns', 'gcp', 'firebase', 'cloud-run']
draft: false
---

`katatsumuri.work` はムームードメインで DNS を管理していて、そのドメインで Google Workspace のメールが動いています。**ネームサーバーを移管せずに**、この 1 ドメインの下に GCP と Firebase のサービスを 3 つぶら下げました。

- `api.katatsumuri.work` → Cloud Run
- `katatsumuri.work`（apex） → Firebase Hosting
- `blog.katatsumuri.work` → Firebase Hosting（別サイト）

どれも「提示されたレコードをムームードメイン側に足すだけ」で済んでいます。以前 [Cloudflare をやめて Cloud Run にした話]({{< ref "2026-06-16-cloud-run-over-cloudflare.md" >}}) で「なぜそうしたか」を書いたので、今回はその実務編として、**実際に足したレコードと、証明書まわりでハマった点**をまとめておきます。

## 前提：ネームサーバーは動かさない

大前提として、`katatsumuri.work` のネームサーバーはムームードメインのままにしています。

理由は前回書いたとおりで、このドメインで会社のメールが本番稼働しているためです。ネームサーバーを移管すると **MX レコードを含む全レコードを移管先で作り直す**ことになり、その過程で一通でもメールを落とすリスクを負います。サブドメインを 1 つ生やしたいだけなのに、ドメイン全体を引っ越すのは釣り合いません。

参考: [Google Workspace の MX レコードを設定する](https://support.google.com/a/answer/140034)

幸い、GCP も Firebase も**外部 DNS のまま使えます**。どちらも「このレコードを追加してください」と提示してくるので、それをムームードメインのカスタム設定に**追加**するだけです。既存行は一切編集しません。

## パターン 1：サブドメイン → Cloud Run

Cloud Run の**ドメインマッピング**を作ると、追加すべきレコードが提示されます。サブドメインの場合は CNAME 1 本です。

| サブドメイン | 種別 | 内容 |
|---|---|---|
| `api` | CNAME | `ghs.googlehosted.com.` |

参考: [Cloud Run - カスタム ドメインのマッピング](https://cloud.google.com/run/docs/mapping-custom-domains)

`ghs.googlehosted.com` は Google 共通のホスト名なので、どのサービスに向くかは DNS 側では決まりません。**「どのドメインをどの Cloud Run サービスに繋ぐか」は GCP 側のドメインマッピングが持っている**という分担です。ここが少し直感に反するところで、DNS レコードだけ見ても行き先が分からないので、最初は不安になりました。

なお、apex（`katatsumuri.work` そのもの）を Cloud Run に向けたい場合は CNAME が使えないため A / AAAA を並べることになります。今回 apex は Firebase に使ったので、この構成は採っていません。

## パターン 2：apex → Firebase Hosting

apex は CNAME を張れない（DNS の仕様上、apex に CNAME を置くと他のレコードと共存できない）ので、**A レコード**になります。Firebase コンソールでカスタムドメインを追加すると、A レコードと、所有権確認用の TXT が提示されます。

| サブドメイン | 種別 | 内容 |
|---|---|---|
| （空欄＝apex） | A | `199.36.158.100` |
| （空欄＝apex） | TXT | `hosting-site=<サイト ID>` |

参考: [Firebase Hosting - カスタム ドメインを接続する](https://firebase.google.com/docs/hosting/custom-domain)

TXT は「このドメインは確かにあなたのものですね」を確認するためのものなので、検証が終わったあとも消さずに残しています。

## パターン 3：サブドメイン → Firebase Hosting（別サイト）

今回ブログを公開するにあたって追加したのがこれです。**サブドメインなら CNAME 1 本で、TXT すら要りませんでした**。

| サブドメイン | 種別 | 内容 |
|---|---|---|
| `blog` | CNAME | `<サイト ID>.web.app` |

apex と違って、向き先が `*.web.app` という**自分専用のホスト名**になっているのがポイントです。このホスト名自体が既にサイトを特定しているので、追加の所有権確認が要らない、という理屈だと理解しています。

同じ Firebase Hosting でも、apex は「A + TXT」、サブドメインは「CNAME だけ」と手数が違います。**サブドメインで済ませられるなら、そのほうがずっと楽**です。

### 1 プロジェクトに複数サイトを置く

コーポレートサイトとブログは別物なので、同じ GCP プロジェクトの中で Hosting サイトを分けました。

```sh
npx firebase-tools hosting:sites:create katatsumuri-blog
```

デプロイ先は `firebase.json` の `site` で固定できます。

```json
{
  "hosting": {
    "site": "katatsumuri-blog",
    "public": "public",
    "ignore": ["firebase.json", "**/.*"],
    "trailingSlash": true
  }
}
```

参考: [Firebase Hosting - 複数のサイトをホストする](https://firebase.google.com/docs/hosting/multisites)

ここに `site` を書いておくと、`firebase deploy` にサイト名を渡し忘れても**既定サイト（＝コーポレートサイト）を上書きしてしまう事故が起きません**。リポジトリが分かれている場合、この 1 行があるかないかで安心感がだいぶ違います。

## 足すレコード早見表

3 パターンをまとめるとこうなります。

| やりたいこと | 種別 | 内容 | 備考 |
|---|---|---|---|
| サブドメイン → Cloud Run | CNAME | `ghs.googlehosted.com.` | 行き先は GCP のドメインマッピングが持つ |
| apex → Firebase Hosting | A ＋ TXT | 提示された IP ／ `hosting-site=<サイト ID>` | apex に CNAME は張れない |
| サブドメイン → Firebase Hosting | CNAME | `<サイト ID>.web.app` | TXT 不要 |

そして、**触らないもの**のほうが大事です。

- **MX レコード** — メールの生命線。今回のどの作業でも一切触りません
- **apex の A レコード** — サブドメインを足すときに巻き込まない
- **既存の TXT** — 各種サービスの所有権確認。消すと検証が外れます

ムームードメインの管理画面は行ごとに「編集」「削除」ボタンが並んでいるので、**追加のつもりで既存行を編集してしまわないよう**、作業前に `dig` で現状を控えておくと安心です。

```sh
dig +short katatsumuri.work A
dig +short katatsumuri.work MX
```

作業後に同じコマンドを叩いて、値が変わっていないことを確認します。地味ですが、メールを止めないための保険としては一番効きました。

## ハマり：証明書が出るまでは「別のサイトの証明書」が返る

DNS を追加した直後にブラウザで開くと、こうなります。

```
NET::ERR_CERT_COMMON_NAME_INVALID
このサーバーのセキュリティ証明書は firebaseapp.com から発行されています
```

一瞬「レコードを間違えたか」と焦りますが、これは**証明書の発行がまだ終わっていないだけ**でした。実際に何が返っているか見てみると、はっきりします。

```sh
$ echo | openssl s_client -connect blog.katatsumuri.work:443 \
    -servername blog.katatsumuri.work 2>/dev/null \
  | openssl x509 -noout -subject
subject=CN=firebaseapp.com
```

自分のドメイン用の証明書がまだ無いので、Firebase 共用の証明書がそのまま返っている状態です。発行が終わると、ここが自分のドメイン名に変わります。

```sh
$ echo | openssl s_client -connect katatsumuri.work:443 \
    -servername katatsumuri.work 2>/dev/null \
  | openssl x509 -noout -subject
subject=CN=katatsumuri.work
```

この間、**HTTP は先に通ります**。`curl -o /dev/null -s -w '%{http_code}' http://blog.katatsumuri.work/` が `301` を返せば、リクエスト自体は Firebase に届いています。DNS は合っていて、証明書だけ待ち、という切り分けができます。

待ち時間は数十分から、長いと 24 時間ほど見ておくとよさそうです。慌てて設定を変えると、かえって検証がやり直しになります。**「HTTP が 301、証明書の CN が共用のまま」なら正常な途中経過**と覚えておくと、無駄に触らずに済みます。

## まとめ

- ネームサーバーを移管しなくても、GCP も Firebase も外部 DNS のままカスタムドメインを使えます
- サブドメインなら CNAME 1 本。apex だけは A ＋ TXT が必要です
- Firebase で複数サイトを持つなら `firebase.json` の `site` を書いておくと、既定サイトへの誤爆を防げます
- DNS 追加直後の証明書エラーは想定内。HTTP が 301 なら待つのが正解です

「メールを止められないから DNS を触りたくない」という理由でホスティングの選択肢を狭めていたのですが、実際にやってみると**足すだけ**で済みました。同じ理由で足踏みしている方の参考になればと思います。
