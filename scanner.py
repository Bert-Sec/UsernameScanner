from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PLATFORMS: Dict[str, str] = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "Bitbucket": "https://bitbucket.org/{}",
    "Codeberg": "https://codeberg.org/{}",
    "SourceHut": "https://git.sr.ht/~{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "X": "https://x.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Threads": "https://www.threads.net/@{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Pinterest": "https://www.pinterest.com/{}/",
    "Facebook": "https://www.facebook.com/{}",
    "Snapchat": "https://www.snapchat.com/add/{}",
    "LinkedIn Public": "https://www.linkedin.com/in/{}",
    "Medium": "https://medium.com/@{}",
    "Dev.to": "https://dev.to/{}",
    "Hashnode": "https://{}.hashnode.dev",
    "Substack": "https://{}.substack.com",
    "Blogger": "https://{}.blogspot.com",
    "WordPress": "https://{}.wordpress.com",
    "About.me": "https://about.me/{}",
    "Behance": "https://www.behance.net/{}",
    "Dribbble": "https://dribbble.com/{}",
    "DeviantArt": "https://www.deviantart.com/{}",
    "ArtStation": "https://www.artstation.com/{}",
    "500px": "https://500px.com/p/{}",
    "Flickr": "https://www.flickr.com/people/{}",
    "VSCO": "https://vsco.co/{}/gallery",
    "Patreon": "https://www.patreon.com/{}",
    "Ko-fi": "https://ko-fi.com/{}",
    "Buy Me a Coffee": "https://www.buymeacoffee.com/{}",
    "Gumroad": "https://{}.gumroad.com",
    "Product Hunt": "https://www.producthunt.com/@{}",
    "Keybase": "https://keybase.io/{}",
    "Hacker News": "https://news.ycombinator.com/user?id={}",
    "Stack Overflow": "https://stackoverflow.com/users/{}",
    "LeetCode": "https://leetcode.com/{}",
    "HackerRank": "https://www.hackerrank.com/{}",
    "Codewars": "https://www.codewars.com/users/{}",
    "CodePen": "https://codepen.io/{}",
    "Replit": "https://replit.com/@{}",
    "Kaggle": "https://www.kaggle.com/{}",
    "PyPI": "https://pypi.org/user/{}",
    "npm": "https://www.npmjs.com/~{}",
    "Docker Hub": "https://hub.docker.com/u/{}",
    "Steam": "https://steamcommunity.com/id/{}",
    "Xbox Gamertag": "https://xboxgamertag.com/search/{}",
    "PlayStation Profiles": "https://psnprofiles.com/{}",
    "Roblox": "https://www.roblox.com/users/profile?username={}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Lichess": "https://lichess.org/@/{}",
    "TryHackMe": "https://tryhackme.com/p/{}",
    "Hack The Box": "https://app.hackthebox.com/profile/{}",
    "Mastodon Social": "https://mastodon.social/@{}",
    "SoundCloud": "https://soundcloud.com/{}",
    "Bandcamp": "https://{}.bandcamp.com",
    "Last.fm": "https://www.last.fm/user/{}",
    "Mixcloud": "https://www.mixcloud.com/{}",
    "Spotify User": "https://open.spotify.com/user/{}",
    "Vimeo": "https://vimeo.com/{}",
    "Goodreads": "https://www.goodreads.com/{}",
    "Pastebin": "https://pastebin.com/u/{}",
    "Gravatar": "https://gravatar.com/{}",
    "VK": "https://vk.com/{}",
    "OK": "https://ok.ru/{}",
    "Wellfound": "https://wellfound.com/u/{}",
    "AngelList Legacy": "https://angel.co/u/{}",
    "Tripadvisor": "https://tripadvisor.com/members/{}",
    "Tripadvisor Profile": "https://www.tripadvisor.com/Profile/{}",
    "Disqus": "https://disqus.com/by/{}/",
    "Wattpad": "https://www.wattpad.com/user/{}",
    "Trello": "https://trello.com/{}",
    "Cash App": "https://cash.app/${}",
    "Venmo": "https://venmo.com/{}",
    "Linktree": "https://linktr.ee/{}",
    "Canva": "https://www.canva.com/{}",
    "IFTTT": "https://ifttt.com/p/{}",
    "Unsplash": "https://unsplash.com/@{}",
    "Instructables": "https://www.instructables.com/member/{}/",
    "Codecanyon": "https://codecanyon.net/user/{}",
    "Envato": "https://elements.envato.com/user/{}",
    "Freelancer": "https://www.freelancer.com/u/{}",
    "Fiverr": "https://www.fiverr.com/{}",
}

NEGATIVE_TITLE_MARKERS = [
    "page not found",
    "not found",
    "404",
    "missing page",
    "error",
    "private site",
    "checking your browser",
    "attention required",
    "just a moment",
]

NEGATIVE_BODY_STRONG = [
    "this page is no longer available",
    "we can't find that page",
    "we couldn’t find that page",
    "this account doesn't exist",
    "this account doesn’t exist",
    "the specified profile could not be found",
    "nobody on reddit goes by that name",
    "steam community :: error",
    "page not found",
    "profile not found",
    "user not found",
    "username not found",
    "account not found",
]

AUTH_WALL_TITLE_MARKERS = [
    "sign in",
    "login",
    "log in",
    "sign up",
    "join now",
    "checking your browser",
    "just a moment",
    "attention required",
    "recaptcha",
]

AUTH_WALL_URL_MARKERS = [
    "/login",
    "/signin",
    "/signup",
    "/join",
    "/auth",
    "session/new",
]

POSITIVE_TITLE_PATTERNS = [
    r"\b{u}\b.*\bgithub\b",
    r"\b{u}\b.*\broblox\b",
    r"\b{u}\b.*\bpastebin\b",
    r"\b{u}\b.*\bkeybase\b",
    r"\b{u}\b.*\bfreelancer\b",
    r"\b{u}\b.*\bsnapchat\b",
]

POSITIVE_META_PATTERNS = [
    r'"@type":"Person"',
    r'"profile"',
    r'"alternateName":"{u}"',
    r'"identifier":"{u}"',
    r'"channelId":"',
    r'"ownerChannelName"',
    r'"og:title"',
    r'"twitter:title"',
]

POSITIVE_BODY_PATTERNS = [
    r"\bfollowers\b",
    r"\bfollowing\b",
    r"\bsubscribers\b",
    r"\brepositories\b",
    r"\bcontributions\b",
    r"\bjoined\b",
    r"\bposts\b",
    r"\bprojects\b",
    r"\bplaylists\b",
    r"\btracks\b",
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
    title: Optional[str] = None
    matched_rule: Optional[str] = None
    response_length: Optional[int] = None
    positive_score: int = 0
    negative_score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def extract_early_body(html_text: str, limit: int = 25000) -> str:
    return html_text[:limit]


def safe_domain_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}".lower()
    except Exception:
        return url.lower()


def contains_any(text: str, needles: List[str]) -> Optional[str]:
    for needle in needles:
        if needle.lower() in text:
            return needle
    return None


def regex_hit(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def score_response(username: str, response: requests.Response) -> tuple[str, str, str, int, int]:
    raw_html = response.text[:250000]
    body = normalize_text(raw_html)
    early_body = normalize_text(extract_early_body(raw_html))
    title = normalize_text(extract_title(raw_html))
    final_url = safe_domain_path(response.url)
    username_l = username.lower()

    positive = 0
    negative = 0
    reasons: List[str] = []

    if response.status_code in (404, 410):
        return "not_found", "The site returned a missing-page response.", "high", 0, 100

    if response.status_code in (401, 403, 429):
        negative += 25
        reasons.append(f"restricted_status:{response.status_code}")

    if 500 <= response.status_code <= 599:
        return (
            "unconfirmed",
            "The site returned a server error, so the result could not be confirmed.",
            "low",
            0,
            30,
        )

    title_bad = contains_any(title, NEGATIVE_TITLE_MARKERS)
    if title_bad:
        negative += 50
        reasons.append(f"title_negative:{title_bad}")

    body_bad = contains_any(body, NEGATIVE_BODY_STRONG)
    if body_bad:
        negative += 35
        reasons.append(f"body_negative:{body_bad}")

    title_auth = contains_any(title, AUTH_WALL_TITLE_MARKERS)
    if title_auth:
        negative += 30
        reasons.append(f"title_auth:{title_auth}")

    url_auth = contains_any(final_url, AUTH_WALL_URL_MARKERS)
    if url_auth:
        negative += 40
        reasons.append(f"url_auth:{url_auth}")

    early_auth = contains_any(
        early_body,
        [
            "sign in",
            "login",
            "log in",
            "sign up",
            "checking your browser",
            "attention required",
            "just a moment",
            "verify you are human",
            "recaptcha",
            "captcha",
            "access denied",
            "temporarily restricted",
        ],
    )
    if early_auth:
        negative += 20
        reasons.append(f"early_auth:{early_auth}")

    if username_l in title and not title_bad:
        positive += 30
        reasons.append("title_has_username")

    if username_l in final_url:
        positive += 20
        reasons.append("final_url_has_username")

    if response.url.rstrip("/").lower() != response.request.url.rstrip("/").lower():
        positive += 10
        reasons.append("redirect_or_canonicalization")

    for pattern in POSITIVE_TITLE_PATTERNS:
        if regex_hit(title, pattern.format(u=re.escape(username_l))):
            positive += 35
            reasons.append(f"title_pattern:{pattern}")
            break

    metadata_sample = body[:80000]
    for pattern in POSITIVE_META_PATTERNS:
        if regex_hit(metadata_sample, pattern.format(u=re.escape(username_l))):
            positive += 25
            reasons.append(f"meta_pattern:{pattern}")
            break

    if username_l in body:
        for pattern in POSITIVE_BODY_PATTERNS:
            if regex_hit(body, pattern):
                positive += 15
                reasons.append(f"body_profile_signal:{pattern}")
                break

    if response.status_code == 200 and len(raw_html) > 50000 and username_l in body and negative < 50:
        positive += 15
        reasons.append("large_body_username_present")

    generic_shell_titles = {
        "tiktok - make your day",
        "threads",
        "instagram",
        "twitch",
        "spotify – web player",
        "spotify - web player",
        "500px",
        "hack the box",
        "mixcloud",
        "trello",
    }
    if title in generic_shell_titles and username_l not in body:
        negative += 40
        reasons.append("generic_shell_title_without_username")

    delta = positive - negative

    if positive >= 45 and delta >= 15:
        confidence = "high" if positive >= 70 else "medium"
        return "found", "; ".join(reasons), confidence, positive, negative

    if negative >= 70 and delta <= -20:
        confidence = "high" if negative >= 90 else "medium"
        return "not_found", "; ".join(reasons), confidence, positive, negative

    if positive >= 35 and negative < 35:
        return "found", "; ".join(reasons), "medium", positive, negative

    return "unconfirmed", "; ".join(reasons) if reasons else "weak_or_conflicting_signals", "low", positive, negative


def check_platform(platform: str, username: str, timeout: float = 6.0) -> ScanResult:
    url = PLATFORMS[platform].format(username)
    session = build_session()

    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        title = extract_title(response.text[:250000]) or None
        state, note, confidence, pos, neg = score_response(username, response)

        return ScanResult(
            platform=platform,
            url=url,
            final_url=response.url,
            state=state,
            status_code=response.status_code,
            confidence=confidence,
            note=note,
            title=title,
            matched_rule="scored_engine_v5_1",
            response_length=len(response.text) if response.text else 0,
            positive_score=pos,
            negative_score=neg,
        )
    except requests.RequestException as exc:
        return ScanResult(
            platform=platform,
            url=url,
            final_url=url,
            state="unconfirmed",
            status_code=None,
            confidence="low",
            note=f"request_error:{exc}",
            title=None,
            matched_rule="request_exception",
            response_length=None,
            positive_score=0,
            negative_score=0,
        )


def scan_username(
    username: str,
    timeout: float = 6.0,
    workers: int = 25,
    platforms: Optional[Dict[str, str]] = None,
) -> List[ScanResult]:
    if not username or not username.strip():
        raise ValueError("username cannot be empty")

    username = username.strip()
    platform_map = platforms or PLATFORMS
    results: List[ScanResult] = []

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 100))) as executor:
        futures = {
            executor.submit(_check_platform_from_map, platform, username, timeout, platform_map): platform
            for platform in platform_map
        }
        for future in as_completed(futures):
            results.append(future.result())

    order = {"found": 0, "not_found": 1, "unconfirmed": 2}
    results.sort(key=lambda r: (order.get(r.state, 99), r.platform.lower()))
    return results


def _check_platform_from_map(
    platform: str,
    username: str,
    timeout: float,
    platform_map: Dict[str, str],
) -> ScanResult:
    url_template = platform_map[platform]
    url = url_template.format(username)
    session = build_session()

    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        title = extract_title(response.text[:250000]) or None
        state, note, confidence, pos, neg = score_response(username, response)

        return ScanResult(
            platform=platform,
            url=url,
            final_url=response.url,
            state=state,
            status_code=response.status_code,
            confidence=confidence,
            note=note,
            title=title,
            matched_rule="scored_engine_v5_1",
            response_length=len(response.text) if response.text else 0,
            positive_score=pos,
            negative_score=neg,
        )
    except requests.RequestException as exc:
        return ScanResult(
            platform=platform,
            url=url,
            final_url=url,
            state="unconfirmed",
            status_code=None,
            confidence="low",
            note=f"request_error:{exc}",
            title=None,
            matched_rule="request_exception",
            response_length=None,
            positive_score=0,
            negative_score=0,
        )


def results_summary(results: List[ScanResult]) -> Dict[str, int]:
    return {
        "found": sum(1 for r in results if r.state == "found"),
        "not_found": sum(1 for r in results if r.state == "not_found"),
        "unconfirmed": sum(1 for r in results if r.state == "unconfirmed"),
        "total": len(results),
    }


def results_to_dicts(results: List[ScanResult]) -> List[Dict[str, Any]]:
    return [r.to_dict() for r in results]


def humanize_reason(note: Optional[str], state: str, positive_score: int, negative_score: int) -> str:
    if not note:
        if state == "found":
            return "The page showed enough profile signals to classify this account as likely found."
        if state == "not_found":
            return "The page showed strong signs that this account does not exist."
        return "The page did not provide enough reliable evidence to make a confident decision."

    if note.startswith("request_error:"):
        return "The site could not be checked cleanly because the request failed or timed out."

    if note == "The site returned a missing-page response.":
        return note

    if note == "The site returned a server error, so the result could not be confirmed.":
        return note

    if "title_has_username" in note and "body_profile_signal" in note:
        return "The page title and profile-style page content both matched the username, which is a strong sign the account exists."

    if "title_has_username" in note and "meta_pattern" in note:
        return "The page title and embedded page metadata matched the username, which is a strong sign the account exists."

    if "final_url_has_username" in note and "large_body_username_present" in note:
        return "The page stayed on a username-based profile URL and contained substantial page content tied to the username."

    if "body_negative" in note or "title_negative" in note:
        return "The page contained strong missing-page language, so this account was classified as not found."

    if "restricted_status" in note or "title_auth" in note or "url_auth" in note or "early_auth" in note:
        return "The site showed a login wall, restriction, or anti-bot gate, so the result could not be confirmed confidently."

    if state == "found":
        if positive_score >= 70:
            return "Multiple strong profile signals matched the username, so this account was classified as found with high confidence."
        return "Several positive profile signals matched the username, so this account was classified as likely found."

    if state == "not_found":
        if negative_score >= 90:
            return "Multiple strong missing-page signals were detected, so this account was classified as not found with high confidence."
        return "The page showed enough missing-page evidence to classify this account as not found."

    return "The result contained mixed or limited evidence, so it was marked unconfirmed for manual review."