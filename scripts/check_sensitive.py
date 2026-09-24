#!/usr/bin/env python3
"""公開物に載せてはいけない情報が残っていないかを機械的に検査する。

blog-snail skill の手順2「ぼかす」は必須工程だが、手順としての指示だけでは
そのときの注意力に依存する。公開物は一度出ると取り返しがつかないので、
機械の網を最後に1枚かける。

2段構え:
  BLOCK … 出たら落とす。認証情報・個人パス・内部 IP・機微な固有名詞
  WARN  … 落とさず一覧で見せる。金額・住所・URL のように文脈で可否が変わるもの

機微な固有名詞（顧客名・個人名）は **この repo に書けない**（public なので
リスト自体が漏れる）。環境変数か外部ファイルから読む。

使い方:
  python3 scripts/check_sensitive.py                       # 手元。用語リストが無ければ警告
  python3 scripts/check_sensitive.py --require-terms       # CI。用語リストが無ければ落とす
  BLOG_SENSITIVE_TERMS="$(cat terms.txt)" python3 scripts/check_sensitive.py
  python3 scripts/check_sensitive.py --terms-file ~/path/to/terms.txt
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

# --- 落とすもの（この repo に書いても安全なパターンだけ置く） -----------------

BLOCK_PATTERNS: list[tuple[str, str]] = [
    ("認証情報らしき文字列", r"ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}"),
    ("認証情報らしき文字列", r"AIza[0-9A-Za-z_\-]{30,}"),
    ("認証情報らしき文字列", r"sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("秘密鍵", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Slack webhook の実 URL", r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+"),
    ("個人の絶対パス", r"/Users/[A-Za-z0-9._-]+"),
    ("個人の絶対パス", r"[A-Z]:\\Users\\[A-Za-z0-9._-]+"),
    # オクテット数を分岐ごとに揃える。10 は 3 つ、192.168 と 172.x は 2 つ続く。
    # まとめて書くと 10.1.2.3 のような 4 オクテットを取り逃す。
    ("内部 IP", r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\d.])"),
]

# --- 一覧で見せるだけのもの（文脈で可否が変わる） ---------------------------

WARN_PATTERNS: list[tuple[str, str]] = [
    # 「200 万リクエスト」のような助数詞に釣られるので、円が付くものだけ見る。
    ("金額", r"[0-9][0-9,]*\s*(?:万|億)?\s*円"),
    # 「実行履歴から区別」の「から区」に釣られたので、区/市の一般パターンは持たない。
    # 具体的な地名は機微な固有名詞リスト側（secret）に入れる。
    ("住所らしき語", r"東京都|丁目|番地|ビル\s*[0-9]+\s*[FＦ階]"),
]

URL_RE = re.compile(r"https?://[^\s)\"'`<>\]]+")

# 既定の検査対象。公開されるもの全部。
DEFAULT_TARGETS = ("content", "README.md", "hugo.toml", "cloudbuild.yaml")

ALLOW_FILE = "scripts/sensitive-allow.txt"


def load_terms(args: argparse.Namespace) -> tuple[list[str], str]:
    """機微な固有名詞のリストを読む。戻り値は (用語, 出どころ)。"""
    if args.terms_file:
        path = pathlib.Path(args.terms_file).expanduser()
        if not path.exists():
            sys.exit(f"ERROR: --terms-file が見つかりません: {path}")
        return _split_terms(path.read_text()), str(path)

    env = os.environ.get("BLOG_SENSITIVE_TERMS", "")
    if env.strip():
        return _split_terms(env), "環境変数 BLOG_SENSITIVE_TERMS"

    return [], ""


def _split_terms(raw: str) -> list[str]:
    out = []
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def term_to_regex(term: str) -> re.Pattern[str]:
    """短い ASCII 略称は単語境界を付ける。

    2026-09-09 の実点検で `nss` が `openssl` の一部にマッチした。
    日本語には単語境界が効かないので、その場合は素の部分一致にする。
    """
    escaped = re.escape(term)
    if term.isascii():
        flags = re.IGNORECASE
        if len(term) <= 4:
            return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", flags)
        return re.compile(escaped, flags)
    return re.compile(escaped)


def load_allowlist(root: pathlib.Path) -> list[str]:
    """既知の誤検出を素通しするための文字列。行に含まれていれば見逃す。"""
    path = root / ALLOW_FILE
    if not path.exists():
        return []
    return _split_terms(path.read_text())


def iter_files(root: pathlib.Path, targets: tuple[str, ...]):
    for t in targets:
        p = root / t
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".md", ".toml", ".yaml", ".yml", ".html", ".json"):
                    yield f


def scan(root: pathlib.Path, targets: tuple[str, ...], terms: list[str]):
    allow = load_allowlist(root)
    block_rules = [(label, re.compile(pat)) for label, pat in BLOCK_PATTERNS]
    block_rules += [("機微な固有名詞", term_to_regex(t)) for t in terms]
    warn_rules = [(label, re.compile(pat)) for label, pat in WARN_PATTERNS]

    blocks, warns, urls = [], [], set()

    for f in iter_files(root, targets):
        rel = f.relative_to(root)
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            if any(a in line for a in allow):
                continue
            for label, rx in block_rules:
                for m in rx.finditer(line):
                    blocks.append((rel, i, label, m.group(0), line.strip()))
            for label, rx in warn_rules:
                for m in rx.finditer(line):
                    warns.append((rel, i, label, m.group(0), line.strip()))
            urls.update(URL_RE.findall(line))

    return blocks, warns, sorted(urls)


def render(blocks, warns, urls, terms_source: str, show_urls: bool) -> None:
    def show(rows, head):
        print(f"\n## {head}（{len(rows)} 件）")
        if not rows:
            print("  なし")
            return
        for rel, ln, label, hit, line in rows:
            print(f"  {rel}:{ln}  [{label}] {hit}")
            print(f"      {line[:160]}")

    show(blocks, "落とすもの")
    show(warns, "確認だけしてほしいもの")

    if show_urls:
        print(f"\n## 外部 URL の一覧（{len(urls)} 件・目視用）")
        for u in urls:
            print(f"  {u}")

    print(f"\n機微な固有名詞の出どころ: {terms_source or '（無し）'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="公開物のぼかし漏れを検査する")
    ap.add_argument("--root", default=".", help="repo のルート（既定: カレント）")
    ap.add_argument("--terms-file", help="機微な固有名詞のリスト（1行1語・# でコメント）")
    ap.add_argument("--require-terms", action="store_true",
                    help="固有名詞リストが取れなければ落とす（CI 用）")
    ap.add_argument("--no-urls", action="store_true", help="URL 一覧を出さない")
    ap.add_argument("targets", nargs="*", help="検査対象（既定: content README.md ほか）")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    targets = tuple(args.targets) if args.targets else DEFAULT_TARGETS

    terms, source = load_terms(args)
    if not terms:
        msg = ("機微な固有名詞のリストが空です。顧客名・個人名の検査は行われません。"
               " BLOG_SENSITIVE_TERMS か --terms-file を与えてください。")
        if args.require_terms:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 2
        print(f"WARNING: {msg}", file=sys.stderr)

    blocks, warns, urls = scan(root, targets, terms)
    render(blocks, warns, urls, source, show_urls=not args.no_urls)

    if blocks:
        print(f"\nNG: 落とすべき検出が {len(blocks)} 件あります。", file=sys.stderr)
        return 1
    print("\nOK: 落とすべき検出はありません。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
