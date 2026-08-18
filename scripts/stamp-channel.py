#!/usr/bin/env python3
"""给易知官方 Setup.exe 打上推广渠道尾标（协议与周易相同）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel_trailer import (  # noqa: E402
    normalize_code,
    read_channel_from_file,
    stamp_file,
    validate_code,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stamp channel trailer onto Yizhi Setup.exe")
    ap.add_argument("-i", "--input", required=True, type=Path)
    ap.add_argument("-c", "--code", required=True)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--product", default="yizhi", choices=("yizhi", "zhouyi"))
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    src: Path = args.input
    if not src.is_file():
        print(f"找不到输入文件: {src}", file=sys.stderr)
        return 2

    if args.verify_only:
        info = read_channel_from_file(src, require_sig=True)
        if not info:
            print("无有效渠道尾标或签名校验失败", file=sys.stderr)
            return 1
        print(f"OK code={info['code']} product={info['product']} t={info['t']}")
        return 0

    code = validate_code(args.code)
    dest = args.output or src.with_name(f"{src.stem}-{normalize_code(code)}{src.suffix}")
    info = stamp_file(src, dest, code, product=args.product)
    print(f"已写入: {dest}")
    print(f"渠道码: {info['code']}  产品: {info['product']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
