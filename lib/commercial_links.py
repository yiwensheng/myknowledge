"""Public help / purchase URLs for commercial distribution."""

from __future__ import annotations

import os

from .config import load_dotenv

_DEFAULT_PURCHASE = "https://www.yzwhysxx.cn/yizhi/purchase.html"
_DEFAULT_FAQ = "https://www.yzwhysxx.cn/yizhi/faq.html"
_DEFAULT_CHANGELOG = "https://www.yzwhysxx.cn/yizhi/changelog.html"


def commercial_links() -> dict[str, str]:
    load_dotenv()
    purchase = os.environ.get("MYKNOWLEDGE_HELP_PURCHASE_URL", "").strip() or _DEFAULT_PURCHASE
    faq = os.environ.get("MYKNOWLEDGE_HELP_FAQ_URL", "").strip() or _DEFAULT_FAQ
    changelog = os.environ.get("MYKNOWLEDGE_HELP_CHANGELOG_URL", "").strip() or _DEFAULT_CHANGELOG
    return {"purchase_url": purchase, "faq_url": faq, "changelog_url": changelog}
