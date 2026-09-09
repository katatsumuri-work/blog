---
title: '法人口座の締切に追われて会社サイトを Astro + Firebase Hosting で立てた話'
slug: 'astro-firebase-corporate-site'
date: 2026-09-14T09:00:00+09:00
categories: ['tech']
tags: ['astro', 'firebase']
draft: false
---

会社を作ると、思ったより早い段階で**会社のウェブサイトを求められます**。法人口座の開設です。

審査では会社の実在性を確認されるので、サイトがあるに越したことはありません。登記が済んで、口座を開きたい、でもサイトがない。そういう「締切ドリブン」で、コーポレートサイトを Astro + Firebase Hosting で立てました。

凝ったことは何もしていません。**1 ページの静的サイト**です。ただ、締切がある状況で何を選び、何を捨てたかは記録に残す価値があると思うので書いておきます。

## 何を優先したか

決めたのは 3 つだけです。

- **早い**こと。数日で出せる
- **落ちない**こと。審査中に見られない状態は避けたい
- **安い**こと。売上ゼロの会社なので

逆に捨てたのは、CMS、問い合わせフォームのバックエンド、凝ったアニメーション。**動的な要素をすべて後回し**にしました。静的 1 枚なら壊れる余地がほとんどありません。

## なぜ Astro か

静的サイトジェネレータなら何でもよかったのですが、Astro にしました。

理由は、**既定で JavaScript を出力しない**ことです。会社概要と事業内容を並べるだけのページに、フレームワークのランタイムを載せる必要はありません。必要になったらアイランドで足せばいい、という順序が状況に合っていました。

もう 1 つは**ビルド時に外部データを取れる**ことです。会社情報（設立年月日、代表者名、所在地）は後に API へ集約したのですが、その受け皿として素直でした。この設計の話は別記事にします。

参考: [Astro - Why Astro?](https://docs.astro.build/en/concepts/why-astro/)

設定はこれだけです。

```js
import { defineConfig } from 'astro/config';

// 本番は https://katatsumuri.work（Firebase Hosting）で配信する想定。
export default defineConfig({
  site: 'https://katatsumuri.work',
});
```

## 人柱: `<style is:global>` がビルドエラーになる

書き始めてすぐ、`.astro` ファイルの中でグローバル CSS を書こうとして詰まりました。Astro は **5.7 系**です。

```
Expected } but found is
```

パーサーが `is:global` の `is` のところで転んでいるように見えるエラーです。構文自体は Astro のドキュメントにあるものなので、しばらく自分の書き方を疑って時間を溶かしました。

解決は単純で、**グローバル CSS はファイルに出して import する**ことにしました。

```astro
---
import '../styles/global.css';
---
```

考えてみれば、こちらのほうが素直です。`.astro` の中に長い CSS を抱えるより、`src/styles/global.css` に置いて import するほうが見通しがいい。**エラーに押し出される形で、結果的にまともな構成になりました**。

同じエラーで止まっている人は、`is:global` にこだわらず外部ファイルへ出すのが早いと思います。

参考: [Astro - Styling & CSS（Global Styles）](https://docs.astro.build/en/guides/styling/#global-styles)

## Firebase Hosting をマルチサイトで使う

ホスティングは Firebase Hosting です。GCP プロジェクトは API（Cloud Run）と同じものを使い、**Hosting サイトだけ分けています**。

- `katatsumuri-work` サイト … コーポレートサイト（`katatsumuri.work`）
- `katatsumuri-blog` サイト … このブログ（`blog.katatsumuri.work`）

1 プロジェクトに複数の Hosting サイトを持てるので、請求もアクセス管理もまとまります。リポジトリは別々なので、それぞれの `firebase.json` にどのサイトへ出すかを書いておくと、**デプロイ先を間違えて上書きする事故**を防げます。

参考: [Firebase Hosting - 複数のサイトをホストする](https://firebase.google.com/docs/hosting/multisites)

デプロイは npm scripts に 1 行置いただけです。

```json
"deploy": "pnpm build && npx -y firebase-tools deploy --only hosting"
```

締切に追われている時期は、これで十分でした。

## apex ドメインを外部 DNS のまま当てる

`katatsumuri.work` の DNS はムームードメインで管理していて、**そのドメインで Google Workspace のメールが動いています**。ネームサーバーを移すと MX を含む全レコードを作り直すことになるので、絶対に触りたくありませんでした。

Firebase Hosting は外部 DNS のままカスタムドメインを使えます。apex は CNAME を張れないので、提示された **A レコードと所有権確認の TXT** を追加するだけです。**MX には一切触りません**。

このあたりの詳細は [外部 DNS のまま GCP と Firebase にカスタムドメインを生やす]({{< ref "2026-09-11-external-dns-custom-domain-gcp-firebase.md" >}}) に、3 パターンの早見表としてまとめました。

## 結果

数日で公開まで漕ぎ着けて、口座開設にも間に合いました。

振り返ると、**選択肢を減らしたことが効いた**と思います。静的 1 枚、JS なし、DB なし、フォームなし。作るものが小さいほど、決めることも壊れるところも減ります。

会社サイトは「立てたあと放置される」ことが多いですが、静的サイトなら放置しても落ちません。あとから API 連携を足したり、ブログをサブドメインに生やしたりと、必要になった順に育てられています。

## まとめ

- 締切があるときは**動的な要素を全部後回し**にすると早いです
- Astro は既定で JS を出さないので、静的 1 枚に向いています
- `.astro` 内の `<style is:global>` で `Expected } but found is` が出たら、**CSS をファイルに出して import** するのが早いです
- Firebase Hosting は 1 プロジェクトに複数サイトを持てます。`firebase.json` に出力先を書いておくと誤爆しません
- apex は A ＋ TXT を足すだけで当たります。**MX を触らない**のが最重要です
