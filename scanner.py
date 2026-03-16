from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from curl_cffi import requests


PLATFORMS: Dict[str, str] = {
    "GitHub": "https://github.com/{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "TikTok": "https://www.tiktok.com/@{}",
    "ArtStation": "https://www.artstation.com/{}",
    # add the rest of your platforms here
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

GLOBAL_NEGATIVE_URL_MARKERS = [
    "/404",
    "/404/",
    "/not-found",
    "/not_found",
    "/missing",
    "/error",
]

GLOBAL_AUTH_URL_MARKERS = [
    "/login",
    "/signin",
    "/signup",
    "/join",
    "/accounts/login",
    "/auth",
]

GLOBAL_AUTH_BODY_MARKERS = [
    "sign in",
    "log in",
    "login",
    "sign up",
    "join now",
    "verify you are human",
    "captcha",
    "recaptcha",
    "checking your browser",
    "attention required",
]

GENERIC_NEGATIVE_BODY = [
    "page not found",
    "profile not found",
    "user not found",
    "username not found",
    "account not found",
    "the page you are looking for doesn't exist",
    "the page you are looking for doesn’t exist",
    "this page does not exist",
    "we could not find the page you were looking for",
]

@dataclass
class ScanResult:
    platform: str
    url: str
    final_url: str
    state: str
    status_code: Optional[int]
    confidence: str
    note: Optional[str] = None
    positive_score: int = 0
    negative_score: int = 0
    friendly_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def safe_domain_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        return f"{parsed.netloc}{path}".lower()
    except Exception:
        return url.lower()


def contains_any(text: str, needles: List[str]) -> Optional[str]:
    for needle in needles:
        if needle.lower() in text:
            return needle
    return None


def generic_profile_score(username: str, body: str, title: str, final_url: str) -> Tuple[int, int, List[str]]:
    reasons: List[str] = []
    pos = 0
    neg = 0
    uname = username.lower()

    if uname in final_url:
        pos += 20
        reasons.append("final_url_has_username")

    if uname in title:
        pos += 25
        reasons.append("title_has_username")

    if uname in body:
        pos += 15
        reasons.append("body_has_username")

    if any(token in body for token in ["followers", "following", "repositories", "posts", "joined", "profile"]):
        pos += 10
        reasons.append("generic_profile_terms")

    bad_url = contains_any(final_url, GLOBAL_NEGATIVE_URL_MARKERS)
    if bad_url:
        neg += 80
        reasons.append(f"url_negative:{bad_url}")

    bad_body = contains_any(body, GENERIC_NEGATIVE_BODY)
    if bad_body:
        neg += 60
        reasons.append(f"body_negative:{bad_body}")

    auth_url = contains_any(final_url, GLOBAL_AUTH_URL_MARKERS)
    if auth_url:
        neg += 35
        reasons.append(f"url_auth:{auth_url}")

    auth_body = contains_any(body[:15000], GLOBAL_AUTH_BODY_MARKERS)
    if auth_body:
        neg += 20
        reasons.append(f"body_auth:{auth_body}")

    return pos, neg, reasons


def validate_github(username: str, body: str, title: str, final_url: str) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if f"github.com/{uname}" in final_url:
        pos += 20
        reasons.append("github_profile_url")

    github_profile_signals = [
        f"@{uname}",
        f">{uname}<",
        "followers",
        "following",
        "repositories",
        "popular repositories",
        "contributions",
    ]
    signal_hits = sum(1 for s in github_profile_signals if s in body)

    if signal_hits >= 3:
        pos += 60
        reasons.append("github_profile_signals")

    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    if neg >= 80 and pos < 40:
        return "not_found", "; ".join(reasons), "high", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_reddit(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    # Canonical Reddit user page
    if "/user/" in final_url:
        pos += 15
        reasons.append("reddit_user_url")

    # Real profile signals
    reddit_positive_signals = [
        f"u/{uname}",
        f"u/{username}",
        f"#{uname}",
        "overview",
        "posts",
        "comments",
        "cake day",
        "karma",
        "commented",
        "posted by",
    ]
    hits = sum(1 for s in reddit_positive_signals if s in body)
    if hits >= 3:
        pos += 70
        reasons.append("reddit_profile_signals")

    # Actual missing signal
    if "nobody on reddit goes by that name" in body:
        neg += 100
        reasons.append("reddit_missing_phrase")

    # If blocked but profile signals are still present, trust the profile
    if status_code in (403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", "reddit_blocked_or_rate_limited", "low", pos, max(neg, 40)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    if pos >= 50:
        return "found", "; ".join(reasons), "medium", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_youtube(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if f"/@{uname}" in final_url:
        pos += 25
        reasons.append("youtube_handle_url")

    if f"@{uname}" in body:
        pos += 30
        reasons.append("youtube_handle_in_body")

    if '"channelid"' in body or '"ownerchannelname"' in body:
        pos += 35
        reasons.append("youtube_channel_metadata")

    if "this page isn't available" in body or "this page isn’t available" in body:
        neg += 100
        reasons.append("youtube_missing_phrase")

    if status_code in (403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", "youtube_blocked_or_rate_limited", "low", pos, max(neg, 40)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_twitch(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if f"twitch.tv/{uname}" in final_url:
        pos += 20
        reasons.append("twitch_channel_url")

    twitch_positive_signals = [
        f'"login":"{uname}"',
        f'"displaylogin":"{uname}"',
        f'"displayname":"{username}"'.lower(),
        '"channelid"',
        '"followerscount"',
        '"profileimageurl"',
        '"streamtitle"',
        '"description"',
    ]
    hits = sum(1 for s in twitch_positive_signals if s in body)
    if hits >= 2:
        pos += 75
        reasons.append("twitch_channel_metadata")

    if "sorry. unless you’ve got a time machine" in body or "sorry. unless you've got a time machine" in body:
        neg += 100
        reasons.append("twitch_missing_phrase")

    if status_code in (403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", "twitch_blocked_or_rate_limited", "low", pos, max(neg, 40)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_instagram(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if f"instagram.com/{uname}" in final_url:
        pos += 15
        reasons.append("instagram_profile_url")

    # Strong positive signals you described
    insta_positive_signals = [
        f"see more from {uname}",
        f"see photos, videos and more from {uname}",
        f'"username":"{uname}"',
        f'"alternate_name":"{uname}"',
        '"profilepage_"',
        '"xdt_api__v1__users__web_profile_info"',
    ]
    hits = sum(1 for s in insta_positive_signals if s in body)
    if hits >= 1:
        pos += 80
        reasons.append("instagram_profile_signals")

    # Strong negative signals you described
    insta_negative_signals = [
        "profile isn't available",
        "profile isn’t available",
        "the link may be broken, or the profile may have been removed",
    ]
    neg_hit = contains_any(body, insta_negative_signals)
    if neg_hit:
        neg += 100
        reasons.append(f"instagram_missing_phrase:{neg_hit}")

    # If redirected to login, don't auto-fail; Instagram does that a lot
    if "/accounts/login/" in final_url:
        neg += 20
        reasons.append("instagram_login_redirect")

    if status_code in (403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", "instagram_blocked_or_rate_limited", "low", pos, max(neg, 45)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_tiktok(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if f"/@{uname}" in final_url:
        pos += 15
        reasons.append("tiktok_handle_url")

    # Strong positive signals from your example
    tiktok_positive_signals = [
        f"@{uname}",
        f'"uniqueid":"{uname}"',
        f'"uniqueid":"@{uname}"',
        "following",
        "followers",
        "likes",
        "no bio yet",
        "webapp.user-detail",
    ]
    hits = sum(1 for s in tiktok_positive_signals if s in body)
    if hits >= 3:
        pos += 85
        reasons.append("tiktok_profile_signals")

    # Strong negative signal from your example
    tiktok_negative_signals = [
        "couldn't find this account",
        "couldn’t find this account",
        "looking for videos? try browsing our trending creators, hashtags, and sounds.",
    ]
    if "couldn't find this account" in body or "couldn’t find this account" in body:
        neg += 100
        reasons.append("tiktok_missing_phrase")
    elif "looking for videos? try browsing our trending creators, hashtags, and sounds." in body and pos < 40:
        neg += 70
        reasons.append("tiktok_no_results_shell")

    if status_code in (403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", "tiktok_blocked_or_rate_limited", "low", pos, max(neg, 45)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 70:
        return "found", "; ".join(reasons), "high", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_artstation(username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    uname = username.lower()
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    # Hard fail if redirected to /404
    if "/404" in final_url or final_url.endswith("artstation.com/404"):
        neg += 120
        reasons.append("artstation_404_url")

    # Hard fail if the page itself says page not found and there's no real profile evidence
    if "page not found" in body and uname not in body:
        neg += 100
        reasons.append("artstation_page_not_found")

    # Generic sign-in shell should not count as a profile
    if "sign in with epic games" in body and uname not in body:
        neg += 35
        reasons.append("artstation_generic_signin_shell")

    # Positive profile signals
    if f"artstation.com/{uname}" in final_url and uname in body:
        pos += 35
        reasons.append("artstation_profile_url_and_body")

    if "artstation" in title and uname in title:
        pos += 25
        reasons.append("artstation_title_has_username")

    if status_code == 404:
        return "not_found", "artstation_http_404", "high", 0, 100

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 65:
        return "found", "; ".join(reasons), "medium", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def validate_default(platform: str, username: str, body: str, title: str, final_url: str, status_code: int) -> Tuple[str, str, str, int, int]:
    pos, neg, reasons = generic_profile_score(username, body, title, final_url)

    if status_code == 404:
        return "not_found", "http_404", "high", 0, 100

    if status_code in (401, 403, 429):
        if pos >= 60:
            return "found", "; ".join(reasons), "medium", pos, neg
        return "unconfirmed", f"access_restricted:{status_code}", "low", pos, max(neg, 40)

    if neg >= 100:
        return "not_found", "; ".join(reasons), "high", pos, neg
    if pos >= 60 and neg < 60:
        return "found", "; ".join(reasons), "medium", pos, neg
    if neg >= 70 and pos < 40:
        return "not_found", "; ".join(reasons), "medium", pos, neg
    return "unconfirmed", "; ".join(reasons), "low", pos, neg


def score_response(
    platform: str,
    username: str,
    html: str,
    status_code: int,
    final_url: str,
) -> Tuple[str, str, str, int, int]:
    body = normalize_text(html[:300000])
    title = normalize_text(extract_title(html[:100000]))
    final_url_norm = safe_domain_path(final_url)

    if status_code == 404:
        return "not_found", "http_404", "high", 0, 100

    if 500 <= status_code <= 599:
        return "unconfirmed", f"server_error:{status_code}", "low", 0, 25

    validators = {
        "GitHub": lambda: validate_github(username, body, title, final_url_norm),
        "Reddit": lambda: validate_reddit(username, body, title, final_url_norm, status_code),
        "YouTube": lambda: validate_youtube(username, body, title, final_url_norm, status_code),
        "Twitch": lambda: validate_twitch(username, body, title, final_url_norm, status_code),
        "Instagram": lambda: validate_instagram(username, body, title, final_url_norm, status_code),
        "TikTok": lambda: validate_tiktok(username, body, title, final_url_norm, status_code),
        "ArtStation": lambda: validate_artstation(username, body, title, final_url_norm, status_code),
    }

    if platform in validators:
        return validators[platform]()

    return validate_default(platform, username, body, title, final_url_norm, status_code)


def humanize_reason(note: Optional[str], state: str, pos: int, neg: int) -> str:
    if state == "found":
        if pos >= 70:
            return f"Strong platform-specific signals matched this username (score {pos})."
        return f"Likely found based on multiple positive signals (score {pos})."

    if state == "not_found":
        if note and ("404" in note or "missing" in note or "not_found" in note):
            return "The platform returned clear missing-page signals."
        return "The platform strongly indicates that this account does not exist."

    if note:
        if "restricted" in note or "blocked" in note or "login" in note:
            return "The platform blocked the request or forced authentication, so this result is not reliable."
        if "server_error" in note:
            return "The platform returned an error page, so the result could not be confirmed."

    return "Not enough reliable evidence to classify this account."


def check_platform(platform: str, username: str, timeout: float = 10.0) -> ScanResult:
    url = PLATFORMS[platform].format(username)

    try:
        response = requests.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            allow_redirects=True,
            headers=BROWSER_HEADERS,
        )

        state, note, conf, pos, neg = score_response(
            platform=platform,
            username=username,
            html=response.text or "",
            status_code=response.status_code,
            final_url=response.url,
        )

        return ScanResult(
            platform=platform,
            url=url,
            final_url=response.url,
            state=state,
            status_code=response.status_code,
            confidence=conf,
            note=note,
            positive_score=pos,
            negative_score=neg,
            friendly_reason=humanize_reason(note, state, pos, neg),
        )

    except Exception as exc:
        return ScanResult(
            platform=platform,
            url=url,
            final_url=url,
            state="unconfirmed",
            status_code=None,
            confidence="low",
            note=f"request_error:{exc}",
            positive_score=0,
            negative_score=0,
            friendly_reason="The request failed, timed out, or was blocked.",
        )


def scan_username(username: str, timeout: float = 10.0, workers: int = 25) -> List[ScanResult]:
    username = username.strip()
    if not username:
        raise ValueError("username cannot be empty")

    results: List[ScanResult] = []

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 100))) as executor:
        futures = {
            executor.submit(check_platform, platform, username, timeout): platform
            for platform in PLATFORMS
        }
        for future in as_completed(futures):
            results.append(future.result())

    order = {"found": 0, "unconfirmed": 1, "not_found": 2}
    results.sort(key=lambda x: (order.get(x.state, 3), x.platform.lower()))
    return results


def results_summary(results: List[ScanResult]) -> Dict[str, int]:
    return {
        "found": sum(1 for r in results if r.state == "found"),
        "not_found": sum(1 for r in results if r.state == "not_found"),
        "unconfirmed": sum(1 for r in results if r.state == "unconfirmed"),
        "total": len(results),
    }


def results_to_dicts(results: List[ScanResult]) -> List[Dict[str, Any]]:
    return [r.to_dict() for r in results]
