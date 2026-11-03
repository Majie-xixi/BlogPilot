from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import unescape
import json
import os
import re
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MAX_PROFILE_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """Small, public snapshot of a 51CTO profile page."""

    profile_url: str
    checked_at: datetime
    latest_published_at: datetime | None
    month_count: int | None
    latest_title: str | None
    latest_url: str | None
    display_name: str | None = None
    articles_empty: bool = False

    def has_publication_on(self, day: date) -> bool | None:
        if self.latest_published_at is None:
            return False if self.articles_empty else None
        return self.latest_published_at.date() == day


def parse_profile_display_name(html: str) -> str | None:
    """Extract the public blog owner name without starting a browser."""
    json_patterns = (
        r'"nickname"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"',
        r'"nickName"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"',
        r'"userName"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"',
    )
    for pattern in json_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            value = _decode_json_text(match.group("value"))
            name = _normalize_profile_name(value)
            if name:
                return name

    for tag in re.findall(r"<meta\b[^>]*>", html, re.IGNORECASE):
        attributes = {
            key.lower(): unescape(value)
            for key, _quote, value in re.findall(
                r"""([:\w-]+)\s*=\s*(["'])(.*?)\2""",
                tag,
                re.IGNORECASE | re.DOTALL,
            )
        }
        kind = (attributes.get("name") or attributes.get("property") or "").lower()
        if kind in {"author", "og:title", "twitter:title"}:
            name = _normalize_profile_name(attributes.get("content", ""))
            if name:
                return name

    title = re.search(r"<title[^>]*>(?P<value>.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title:
        return _normalize_profile_name(title.group("value"))
    return None


def parse_profile_html(
    html: str,
    profile_url: str,
    *,
    now: datetime | None = None,
) -> ProfileSnapshot:
    checked_at = now or datetime.now()
    current_year = checked_at.year
    current_month = checked_at.month

    article_box = re.search(
        r'<div[^>]+id=["\']common-article-listbox-1["\'][^>]*>(?P<body>.*)',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    latest_text = None
    latest_title = None
    latest_url = None
    if article_box:
        article = re.search(
            r'<div[^>]*class=["\'][^"\']*\bcommon-article-list\b[^"\']*["\'][^>]*>.*?'
            r'<h3[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>\s*'
            r'<a[^>]+href=["\'](?P<url>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>',
            article_box.group("body"),
            re.IGNORECASE | re.DOTALL,
        )
        if article:
            latest_title = _plain_text(article.group("title")) or None
            latest_url = unescape(article.group("url")).strip() or None
        action = re.search(
            r'<span[^>]*class=["\'][^"\']*\bactions\b[^"\']*["\'][^>]*>(.*?)</span>',
            article_box.group("body"),
            re.IGNORECASE | re.DOTALL,
        )
        if action:
            latest_text = _plain_text(action.group(1))

    month_pattern = re.compile(
        rf'<span>\s*0?{current_month}\s*月\s*</span>\s*<strong>\s*(\d+)\s*篇\s*</strong>',
        re.IGNORECASE,
    )
    year_anchor = re.search(
        rf'<span>\s*{current_year}\s*年\s*</span>\s*<strong>\s*\d+\s*篇\s*</strong>',
        html,
        re.IGNORECASE,
    )
    month_match = month_pattern.search(html, year_anchor.end() if year_anchor else 0)

    articles_empty = False
    page_markup = re.sub(
        r"<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    section = re.search(
        r'<section\b[^>]*\sid=["\']common-section-one["\'][^>]*>(?P<body>.*?)</section\s*>',
        page_markup,
        re.IGNORECASE | re.DOTALL,
    )
    if section and article_box is None:
        body = section.group("body")
        empty_marker = re.search(
            r'<div\b[^>]*\sclass=["\']common-nodata["\'][^>]*>\s*暂无内容\s*</div\s*>\s*$',
            body,
            re.IGNORECASE,
        )
        if empty_marker:
            profile_links = {profile_url.rstrip("/"), urlsplit(profile_url).path.rstrip("/")}
            for tag in re.findall(r"<a\b[^>]*>\s*全部\s*</a\s*>", body, re.IGNORECASE):
                attributes = {
                    key.lower(): unescape(value)
                    for key, _quote, value in re.findall(
                        r"""([:\w-]+)\s*=\s*(["'])(.*?)\2""", tag, re.DOTALL
                    )
                }
                if (
                    "cur" in attributes.get("class", "").split()
                    and attributes.get("href", "").rstrip("/") in profile_links
                ):
                    articles_empty = True
                    break

    return ProfileSnapshot(
        profile_url=profile_url.rstrip("/"),
        checked_at=checked_at,
        latest_published_at=parse_51cto_time(latest_text, checked_at) if latest_text else None,
        month_count=0 if articles_empty else int(month_match.group(1)) if month_match else None,
        latest_title=latest_title,
        latest_url=latest_url,
        display_name=parse_profile_display_name(html),
        articles_empty=articles_empty,
    )


def fetch_profile_snapshot(
    profile_url: str,
    *,
    now: datetime | None = None,
    timeout: float = 12,
) -> ProfileSnapshot:
    url = profile_url.strip().rstrip("/")
    if not re.fullmatch(r"https://blog\.51cto\.com/u_\d+", url):
        raise ValueError("51CTO 主页地址无效")

    for attempt in range(2):
        try:
            html = _download_profile_html(url, timeout)
            return parse_profile_html(html, url, now=now)
        except (OSError, subprocess.TimeoutExpired):
            if attempt == 1:
                raise
            time.sleep(0.35)
    raise RuntimeError("unreachable")


def _download_profile_html(url: str, timeout: float) -> str:
    # 51CTO returns a small JavaScript shell to Python's TLS client, while the
    # Windows web client receives the server-rendered public article list.  The
    # application is Windows-only, so use that client without launching Chrome.
    if os.name == "nt":
        script = (
            "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false);"
            "$ProgressPreference='SilentlyContinue';$ErrorActionPreference='Stop';"
            f"$r=Invoke-WebRequest -UseBasicParsing -Uri '{url}' -TimeoutSec {max(1, int(timeout))} "
            "-Headers @{'User-Agent'='Mozilla/5.0 BlogPilotStatusCheck/1.0'};"
            f"if($r.RawContentLength -gt {MAX_PROFILE_BYTES}){{throw 'response too large'}};"
            "$r.Content"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise ConnectionError(completed.stderr.strip() or "51CTO 主页读取失败")
        return completed.stdout

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 BlogPilotStatusCheck/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        length_text = response.headers.get("Content-Length")
        if length_text and int(length_text) > MAX_PROFILE_BYTES:
            raise ValueError("51CTO 主页响应异常，已停止读取")
        payload = response.read(MAX_PROFILE_BYTES + 1)
        if len(payload) > MAX_PROFILE_BYTES:
            raise ValueError("51CTO 主页超过状态检查大小限制")
        encoding = response.headers.get_content_charset() or "utf-8"
    return payload.decode(encoding, errors="replace")


def parse_51cto_time(value: str, now: datetime) -> datetime | None:
    text = _plain_text(value)
    if not text:
        return None
    if text in {"刚刚", "刚才"}:
        return now
    if text == "昨天":
        return now - timedelta(days=1)

    relative = re.fullmatch(r"(\d+)\s*(秒|分钟|小时|天)前", text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = {
            "秒": timedelta(seconds=amount),
            "分钟": timedelta(minutes=amount),
            "小时": timedelta(hours=amount),
            "天": timedelta(days=amount),
        }[unit]
        return now - delta

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            pass
    for pattern in ("%m-%d %H:%M", "%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.replace(year=now.year)
        except ValueError:
            pass
    return None


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", value))).strip()


def _decode_json_text(value: str) -> str:
    try:
        return str(json.loads(f'"{value}"'))
    except (json.JSONDecodeError, TypeError):
        return value.replace(r"\/", "/").replace(r"\"", '"').replace(r"\\", "\\")


def _normalize_profile_name(value: str) -> str | None:
    name = _plain_text(value)
    name = re.split(
        r"\s*的博客(?:_|-|\s|$)|[_-]\s*(?:原创文章[_-]?)?51CTO博客|[_-]\s*51CTO",
        name,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" _-|")
    if not name or name.lower() in {"51cto", "51cto博客"} or len(name) > 80:
        return None
    return name
