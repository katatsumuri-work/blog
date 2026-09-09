---
title: 'pnpm 11 で esbuild と sharp のビルドが勝手にスキップされる ― ERR_PNPM_IGNORED_BUILDS'
slug: 'pnpm11-ignored-builds'
date: 2026-09-15T09:00:00+09:00
categories: ['tech']
tags: ['pnpm']
draft: false
---

pnpm を 11 系に上げたあと、`pnpm install` は成功するのに **`pnpm build` が落ちる**という状態になりました。

原因は pnpm 11 のセキュリティ強化で、**依存パッケージの postinstall がデフォルトでブロックされる**ようになったためです。短い話なので、解決までを一直線に書きます。同じところで検索している人向けのメモです。

## 症状

`install` 自体は成功します。ただ、最後にこんな警告が出ます。

```
Ignored build scripts: esbuild, sharp.
Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
```

エラーコードは `ERR_PNPM_IGNORED_BUILDS` です。

この状態でビルドすると、esbuild のネイティブバイナリが用意されていないので落ちます。sharp も同様で、画像処理が動きません。**`install` が緑で終わるので気づきにくい**のが厄介なところでした。

## 原因

pnpm 10 以降、**インストール時に任意のコードが走ることを防ぐ**方向に舵が切られています。`postinstall` はサプライチェーン攻撃の入口になりやすいので、既定でブロックし、**明示的に許可したパッケージだけ実行する**というモデルです。

方針としてはまったく正しいと思います。ただ esbuild や sharp のように**ネイティブバイナリの用意を postinstall でやるパッケージ**は、許可しないと動きません。Astro を使っていると両方とも間接的に入ってきます。

参考: [pnpm - Settings](https://pnpm.io/settings)

## 効かなかった方法

先に「効かなかったこと」を書いておきます。ここで一番時間を使いました。

**`package.json` の `pnpm.onlyBuiltDependencies`**

```json
{
  "pnpm": {
    "onlyBuiltDependencies": ["esbuild", "sharp"]
  }
}
```

検索するとよく出てくる書き方ですが、手元の **pnpm 11.0.4 では効きませんでした**。`install` し直しても警告が消えません。

**`.npmrc`**

`.npmrc` に書く方法も試しましたが、同じく効きませんでした。

どちらもバージョンによって扱いが変わっている部分なので、**「記事に書いてあったのに効かない」ときはまず自分の pnpm のバージョンを疑う**のがよさそうです。

実際、いま公式の設定ドキュメントを見ると `allowBuilds` は載っていますが、`onlyBuiltDependencies` は見当たりません。検索で出てくる情報のほうが古くなっている、という状況のようです。

## 効いた方法

`pnpm-workspace.yaml` に `allowBuilds` を書くことで解決しました。

```yaml
# pnpm 11 はビルドスクリプト（postinstall 等）をデフォルトでブロックする。
# Astro のビルドに必要な esbuild / sharp を明示的に許可する。
allowBuilds:
  esbuild: true
  sharp: true
```

ワークスペースを切っていないリポジトリでも、`pnpm-workspace.yaml` を置けば読まれます。ファイル名から「モノレポ用の設定」に見えますが、**pnpm の設定ファイルとして機能する**ということのようです。ここも直感に反しました。

設定を足したら、**`pnpm install` をやり直して反映させます**。既にインストール済みの状態で設定だけ書いても、ブロックされたままです。

いまブロックされているものは `pnpm ignored-builds` で確認できます。

```sh
pnpm ignored-builds
```

これで `install` の警告が消え、`build` も通るようになりました。

参考: [pnpm ignored-builds](https://pnpm.io/cli/ignored-builds)

## 対話的に許可することもできる

警告に出ている `pnpm approve-builds` を使うと、対話的にどのパッケージを許可するか選べます。手元で試すぶんにはこちらが早いです。

参考: [pnpm approve-builds](https://pnpm.io/cli/approve-builds)

ただ CI では対話できないので、**設定ファイルに書いてコミットしておく**必要があります。結局リポジトリに残す形になるので、最初から `pnpm-workspace.yaml` に書くほうが二度手間になりません。

## まとめ

- pnpm 11 は **postinstall を既定でブロック**します。`install` は成功するのにビルドが落ちるのはこれが原因です
- 手元の 11.0.4 では **`package.json` の `pnpm.onlyBuiltDependencies` も `.npmrc` も効きませんでした**
- **`pnpm-workspace.yaml` の `allowBuilds`** で解決しました。ワークスペースを使っていなくても置けます
- 情報が錯綜している領域なので、**自分の pnpm のバージョンを確認してから**手順を選ぶのが確実です

セキュリティ強化としては妥当な変更なので、「全部許可」に逃げず、**必要なパッケージだけ明示する**運用に落ち着かせるのがよいと思います。
