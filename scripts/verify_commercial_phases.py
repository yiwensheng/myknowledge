#!/usr/bin/env python3
"""商业化交付物自检（本地文件与脚本是否存在）。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS: list[tuple[str, Path | str, str]] = [
    ("env.user.example", ROOT / "env.user.example", "file"),
    ("build-portable.ps1", ROOT / "scripts" / "build-portable.ps1", "file"),
    ("build-installer.ps1", ROOT / "scripts" / "build-installer.ps1", "file"),
    ("Inno Setup 脚本", ROOT / "scripts" / "installer" / "YizhiSetup.iss", "file"),
    ("test_license_flow.py", ROOT / "scripts" / "test_license_flow.py", "file"),
    ("license deploy nginx", ROOT / "license-server" / "deploy" / "nginx.conf.example", "file"),
    ("license deploy systemd", ROOT / "license-server" / "deploy" / "yizhi-license.service", "file"),
    ("购买与激活指南", ROOT / "docs" / "commercial" / "购买与激活指南.md", "file"),
    ("FAQ", ROOT / "docs" / "commercial" / "FAQ.md", "file"),
    ("隐私说明", ROOT / "docs" / "commercial" / "隐私说明.md", "file"),
    ("GPL说明", ROOT / "docs" / "commercial" / "GPL说明.md", "file"),
    ("客服SOP", ROOT / "docs" / "commercial" / "客服SOP.md", "file"),
    ("T1-T8验收清单", ROOT / "docs" / "commercial" / "T1-T8验收清单.md", "file"),
    ("购买页 HTML", ROOT / "docs" / "commercial" / "purchase.html", "file"),
    ("IIS 部署清单", ROOT / "license-server" / "deploy" / "deploy-windows-iis-checklist.md", "file"),
    ("backup_license_db", ROOT / "scripts" / "backup_license_db.ps1", "file"),
    ("run_commercial_preflight", ROOT / "scripts" / "run_commercial_preflight.ps1", "file"),
    ("test_xunhupay_connect", ROOT / "license-server" / "scripts" / "test_xunhupay_connect.py", "file"),
    ("setup_license_backup_task", ROOT / "scripts" / "setup_license_backup_task.ps1", "file"),
    ("发布前最后三步", ROOT / "docs" / "commercial" / "发布前最后三步.md", "file"),
    ("commercial_links 模块", ROOT / "lib" / "commercial_links.py", "file"),
    ("update_check 模块", ROOT / "lib" / "update_check.py", "file"),
    ("便携 python 启动器", ROOT / "launch-yizhi.bat", "contains:BUNDLED_MODE"),
]


def main() -> int:
    failed = 0
    for name, path, kind in CHECKS:
        p = Path(path) if isinstance(path, Path) else ROOT / str(path)
        if kind == "file":
            ok = p.is_file()
        elif kind.startswith("contains:"):
            needle = kind.split(":", 1)[1]
            ok = p.is_file() and needle in p.read_text(encoding="utf-8", errors="ignore")
        else:
            ok = False
        status = "OK" if ok else "MISSING"
        print(f"[{status}] {name}")
        if not ok:
            failed += 1
    if failed:
        print(f"\n{failed} 项未就绪")
        return 1
    print("\n商业化本地交付物检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
