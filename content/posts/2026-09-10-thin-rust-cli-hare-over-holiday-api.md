---
title: 'ロジックは API、CLI は薄く ― 祝日 API に被せる Rust 製クライアント hare の作り方と配布'
slug: 'thin-rust-cli-hare-over-holiday-api'
date: 2026-07-05T09:00:00+09:00
categories: ['tech']
tags: ['rust', 'cli', 'cloudflare-workers', 'clap']
draft: false
---

祝日 API 3 部作の最後です。1 本目で `/calendar` を**設計**し、2 本目で Excel ツールから**消費**しました。今回は同じ API を、日常的にサッと叩けるように**薄い Rust 製 CLI**として被せた話です。`hare` という名前にしています。

方針は最初から一つで、**判定ロジックは全部 API 側に置き、CLI は「叩いて整形するだけ」の薄いクライアント**に徹すること。おかげで CLI 本体は驚くほど小さく保てました。

## 方針：ロジックは API、CLI は薄く

このシリーズを通してずっと同じことを言っています。稼働日か・祝日か・振替かの判定は全部 API（`isBusinessDay` など）に閉じ込めてあるので、CLI がやることは「URL を組んで、叩いて、返ってきたものを見やすく出す」だけです。

同じ API を web・Excel・LLM・CLI という複数のフロントで共有できて、**CLI 単体には判定ロジックが 1 行も無い**。機能を足したくなったら API 側を直せば、全フロントに一斉に効きます。この費用対効果が薄いクライアントの旨味だなと思います。

## 依存を絞る：tokio も OpenSSL も要らない

手元用の小さな CLI に非同期ランタイムは大げさなので、HTTP は **`ureq`**（blocking + rustls）を選びました。`tokio` を引かずに済むし、rustls なのでシステムの OpenSSL にも依存しません。依存はこれだけです。

```toml
[dependencies]
clap = { version = "4.5", features = ["derive", "env"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
anyhow = "1.0"
chrono = "0.4"
ureq = { version = "2", features = ["json"] }
```

`clap` の derive で引数を定義し、`serde` でレスポンスを型に落とし、`anyhow` でエラーを扱う ── Rust の CLI としてはかなり定番の最小構成に収まりました。

参考: [ureq](https://docs.rs/ureq/latest/ureq/) / [clap - Derive](https://docs.rs/clap/latest/clap/_derive/index.html)

## 構成：型・引数・整形・薄い dispatch

ファイルは役割ごとに 4 つに分けています。

- `api.rs` … レスポンス型と HTTP クライアント（`ureq` を薄くラップ）
- `cli.rs` … `clap` のサブコマンド定義
- `output.rs` … 色付きの整形（`NO_COLOR` と非 TTY に対応）
- `main.rs` … サブコマンドを API 呼び出しに振り分ける薄い dispatch

`main.rs` の dispatch は本当に薄くて、各サブコマンドが「パスを組んで叩いて整形する」だけです。しかも `--json` や `--format csv` が付いたときは、**API の出力を一切加工せずそのまま素通し**します。

```rust
fn calendar(client: &Client, month: &str, format: Option<String>, json: bool) -> Result<()> {
    // --format (csv/json) が付いたら API の出力をそのまま流す
    if let Some(fmt) = format.as_deref() {
        match fmt {
            "csv" | "json" => {
                print!("{}", client.raw(&format!("/calendar/{month}?format={fmt}"))?);
                return Ok(());
            }
            other => anyhow::bail!("未対応のフォーマットです: {other} (csv|json)"),
        }
    }
    // 素の表示だけ CLI 側で整形する
    let days: Vec<api::CalendarDay> = client.get(&path)?;
    output::render_calendar(month, &days);
    Ok(())
}
```

CSV が欲しいときは前回の Excel ツールと同じものが CLI からも取れる、というわけです。CLI が独自に CSV を組み立てたりはしません。

ちなみに色付けは、`NO_COLOR` が設定されていたり出力先が端末でない（パイプやリダイレクト）ときは自動で無効化します。CSV をファイルに落とすときにエスケープシーケンスが混ざらないようにするためです。

```rust
fn color_enabled() -> bool {
    std::env::var_os("NO_COLOR").is_none() && std::io::stdout().is_terminal()
}
```

参考: [NO_COLOR](https://no-color.org/)

## エラー整形：API の `{"error": "..."}` を拾う

薄いとはいえ、ここだけはひと手間かけました。API が 4xx/5xx を返したとき、ステータスコードだけ出すのではなく、**API が返す `{"error": "..."}` の中身を拾って**「API エラー (code): メッセージ」の形で見せています。

```rust
Err(ureq::Error::Status(code, resp)) => {
    let msg = resp
        .into_json::<serde_json::Value>()
        .ok()
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string));
    match msg {
        Some(m) => anyhow::bail!("API エラー ({code}): {m}"),
        None => anyhow::bail!("API エラー ({code})"),
    }
}
```

`400` とだけ言われるより「API エラー (400): month must be YYYY-MM」と言われたほうが、圧倒的にデバッグしやすいです。API 側がせっかくエラーメッセージを返しているので、それを握りつぶさず拾うだけで体験がだいぶ変わりました。

## 配布のハマり：asdf の Rust だと `cargo install` 先が PATH に無い

最後に人柱ポイントです。ビルドした `hare` を手元に入れようと `cargo install --path .` したのですが、**インストールは成功するのにコマンドが見つからない**。

原因は `cargo install` の既定インストール先が `~/.cargo/bin` である一方、私は **asdf で Rust を管理している**ため、その `~/.cargo/bin` が PATH に入っていなかったことでした（asdf の shim が別の場所にあるので）。

`~/.cargo/bin` を PATH に足してもいいのですが、私はふだん `~/.local/bin` に手元ツールを集めているので、インストール先をそちらに向けて解決しました。

```sh
cargo install --path . --root ~/.local   # → ~/.local/bin/hare に入る
```

asdf で Rust を使っていて「`cargo install` したのにコマンドが無い」で詰まったら、まず**インストール先が PATH に入っているか**を疑うと早いです。

参考: [cargo install](https://doc.rust-lang.org/cargo/commands/cargo-install.html)

## おまけ：命名を holi から hare へ

最初は祝日（holiday）から `holi` という名前にしていたのですが、将来ほかの国にも対応するかもと思って、国に依存しない `hare`（晴れ・ハレの日）に改名しました。バイナリ名を変えるのは `Cargo.toml` の `[[bin]] name` を一行変えるだけです。

```toml
[[bin]]
name = "hare"
path = "src/main.rs"
```

## まとめ

「API を正にして、CLI は薄く」という方針で作ってみて、良かった点はこんな感じでした。

- **判定ロジックが CLI に無い** → 機能追加は API 側だけで済む
- **`ureq` で blocking** → tokio も OpenSSL も要らず、依存が小さい
- **`--json` / `--format` は素通し** → 表計算・LLM 向けの出力を CLI からもそのまま取れる
- **エラーは API のメッセージを拾う** → コードだけより圧倒的に分かりやすい
- 配布は **asdf の PATH 問題**にだけ注意（`--root` で回避）

3 回に分けて、同じ祝日 API を「設計 → Excel から消費 → CLI から消費」と追ってきました。producer 側で `isBusinessDay` を確定させておいたおかげで、消費側（Excel も CLI も）は本当に薄く書けた、というのがシリーズを通しての実感です。API を「誰が消費するか」から設計すると、まわりの道具が全部小さくなるなと思いました。
