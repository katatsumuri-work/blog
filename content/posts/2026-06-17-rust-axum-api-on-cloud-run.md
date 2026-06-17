---
title: 'Rust + axum の自己紹介 API を Cloud Run に載せた話（Docker 化の人柱メモ）'
slug: 'rust-axum-api-on-cloud-run'
date: 2026-06-17T09:00:00+09:00
categories: ['tech']
tags: ['rust', 'axum', 'docker', 'cloud-run', 'gcp']
draft: false
---

会社の自己紹介情報（会社概要・メンバー・サービスなど）を返す API を Rust + axum で書いて、Google Cloud Run に載せました。25.4MB のイメージで、コールドスタート 0.44 秒くらいで動いています。

この記事は **作る〜Docker 化〜デプロイ**の実装メモです。途中で Docker のキャッシュにわりと派手にハマったので、人柱記録として残しておきます。

> なお「なぜ Cloudflare ではなく Cloud Run なのか」という選定理由は別記事（[Cloudflare をやめて Cloud Run にした話](/2026/06/16/cloud-run-over-cloudflare/)）に書いたので、ここでは触れません。

## API は Rust + axum + utoipa

ルーティングは axum、OpenAPI のドキュメント生成に utoipa を使っています。`utoipa-axum` の `OpenApiRouter` を使うと、**ハンドラに付けた属性からそのまま OpenAPI スキーマが組み上がり**、`/docs` で SwaggerUI が見られます。ルーターとドキュメントが二重管理にならないのが気持ちいいところです。

```rust
let (router, api) = OpenApiRouter::with_openapi(ApiDoc::openapi())
    .routes(routes!(health))
    .routes(routes!(company))
    .routes(routes!(list_members))
    .routes(routes!(get_member))
    .routes(routes!(list_services))
    .routes(routes!(list_careers))
    .routes(routes!(contact))
    .split_for_parts();

let swagger = SwaggerUi::new("/_swagger-assets")
    .url("/api-docs/openapi.json", api);

router.route("/docs", get(docs)).merge(swagger)
    // セキュリティヘッダ（CSP / HSTS / X-Frame-Options ...）や
    // CORS・タイムアウト・ボディサイズ制限を tower-http の layer で重ねる
```

`tower-http` のレイヤーでセキュリティヘッダや CORS、タイムアウト、リクエストボディ上限を足しています。このあたりは素直に積めるので axum は楽でした。

参考: [axum](https://docs.rs/axum/latest/axum/) / [utoipa](https://docs.rs/utoipa/latest/utoipa/)

## Docker 化：distroless + musl で 25.4MB

Cloud Run はコンテナを動かすので、まずイメージを作ります。方針は **完全 static link したバイナリ 1 個だけの最小イメージ**です。

- builder: `rust:1-alpine`（musl ネイティブで static link）
- runtime: `gcr.io/distroless/static-debian12:nonroot`（shell もパッケージも無い・非 root 起動）

```dockerfile
# syntax=docker/dockerfile:1
FROM rust:1-alpine AS builder
RUN apk add --no-cache musl-dev curl ca-certificates
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY assets ./assets
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release \
    && cp target/release/katatsumuri-api /app/katatsumuri-api

FROM gcr.io/distroless/static-debian12:nonroot AS runtime
COPY --from=builder /app/katatsumuri-api /usr/local/bin/katatsumuri-api
ENV API_BIND_ADDR=0.0.0.0:8080
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/katatsumuri-api"]
```

最終イメージは **25.4MB**。SwaggerUI の資材を同梱しているぶん 10MB は切れませんでしたが、distroless/static は攻撃面が小さく、これくらいなら満足です。

### 人柱ポイント1：alpine に curl が無くてビルドが panic する

`utoipa-swagger-ui` の `build.rs` は、SwaggerUI の資材を**ビルド時に `curl` でダウンロード**しに行きます（reqwest フィーチャを無効にしているとこうなる）。ところが alpine には curl が入っていないので、ビルドが panic しました。

→ `apk add curl ca-certificates` を足して解決。`ca-certificates` も無いと TLS で取得できないので一緒に入れています。

### 人柱ポイント2：定番のキャッシュ術で「空バイナリ」が焼き込まれる

ここが一番ハマりました。Rust の Docker ビルドでよく使われる、

> 「`Cargo.toml` だけ先に COPY → ダミーの `main.rs` で一度ビルドして依存をキャッシュ → 後から本物の `src` を COPY して再ビルド」

という stub 方式を使ったところ、**2 回目の `cargo build` が 0.06 秒で終了**してしまいました。つまり再ビルドされず、**ダミーの空バイナリがそのままイメージに入って**いたのです。ローカルでは動くのに、コンテナだと何も返さない、という地味に厄介な症状でした。

原因は、**BuildKit の `COPY` がコピー元ファイルの mtime（更新時刻）を保持する**こと。本物の `src` を COPY しても、ファイルの mtime が前のビルド成果物より古いままだと、cargo が「ソースは成果物より古い＝変更なし」と判断して再コンパイルをスキップしてしまいます。

→ stub 方式をやめて、**BuildKit の cache mount**（`--mount=type=cache`）で `registry` と `target` をキャッシュする方式に変更しました。これなら**毎回ちゃんと本物をビルドしつつ、依存のコンパイル結果はキャッシュから再利用**できます。cache mount の中身はイメージレイヤに残らないので、ビルドした成果物だけ `cp` でマウント外に取り出してから `COPY` しています。

参考: [Docker Build cache の管理（cache mount）](https://docs.docker.com/build/cache/optimize/#use-cache-mounts)

## Cloud Run へデプロイ

イメージができたら、Artifact Registry に push して Cloud Run にデプロイします。ローカルは arm64 なので、Cloud Run 向けには **`--platform linux/amd64` でビルド**する点に注意です（これを忘れると起動しません）。

おおまかな流れ:

```sh
# Artifact Registry に push（asia-northeast1 / 東京）
docker build --platform linux/amd64 -t \
  asia-northeast1-docker.pkg.dev/<project>/api/katatsumuri-api .
docker push asia-northeast1-docker.pkg.dev/<project>/api/katatsumuri-api

# Cloud Run へ（未認証許可・ポート8080・min0/max3・mem256Mi）
gcloud run deploy api \
  --image asia-northeast1-docker.pkg.dev/<project>/api/katatsumuri-api \
  --region asia-northeast1 --allow-unauthenticated \
  --port 8080 --memory 256Mi --min-instances 0 --max-instances 3
```

`*.run.app` の URL で全エンドポイント（`/health`・`/company`・`/docs` など）が応答することを確認してから、カスタムドメイン `api.katatsumuri.work` をドメインマッピングで割り当てました。マッピングで提示された **CNAME（`api` → `ghs.googlehosted.com.`）をムームー側に 1 本追加するだけ**で、apex も MX も触りません（この設計の理由は前述の別記事に書いています）。

### 人柱ポイント3：domain-mappings は GA に無い

`gcloud run domain-mappings` を叩こうとしたら、**GA のコマンド群に無くて `--region` も使えません**でした。

→ `gcloud components install beta` して、`gcloud beta run domain-mappings ... --region asia-northeast1` で作成できました。リージョンによってはドメインマッピング自体が未対応のこともあるので、そこは事前に確認しておくと安心です。

参考: [Cloud Run - カスタム ドメインのマッピング](https://cloud.google.com/run/docs/mapping-custom-domains)

## 実測とコスト

記事用に測った値です（東京リージョン、cpu1 / mem256Mi）。

| 項目 | 値 |
|---|---|
| イメージサイズ | 25.4MB |
| コールドスタート | 約 0.44 秒 |
| ウォーム時レスポンス | 約 0.07 秒 |

Rust + distroless だとコンテナが軽いので、コールドスタートが 0.5 秒を切ってくれるのは嬉しいところでした。

コスト面は、Cloud Run の無料枠（月 200 万リクエストなど）に対して、自己紹介 API のトラフィックは誤差みたいなものなので、**実質 $0** で回っています。ドメインマッピングと TLS 証明書も無料です。

参考: [Cloud Run の料金](https://cloud.google.com/run/pricing)

## まとめ

- Rust + axum + utoipa は、ルーティングと OpenAPI が一体で気持ちよく書けた
- distroless + musl static で **25.4MB**、コールドスタート **0.44 秒**
- Docker のキャッシュは、**stub 方式より cache mount のほうが事故りにくい**（mtime 由来の「空バイナリ」事件は本当に気づきにくい）
- Cloud Run は既存の Dockerfile をそのまま載せられて、外部 DNS のままカスタムドメインも張れる

小さい API を安く・軽く・安全に出すなら、この構成はかなり気に入っています。同じ落とし穴にハマった人の助けになれば嬉しいです 🐌
