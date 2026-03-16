from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Pattern, Tuple
from urllib.parse import urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

DEFAULT_TIMEOUT = 8.0
MAX_WORKERS = 32
MAX_BODY_BYTES = 300_000

_thread_local = threading.local()


def normalize_text(text: str) -> str:
    text = text or ""
    text = unquote(text)
    text = text.lower()
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def safe_domain_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return f"{parsed.netloc}{path}".lower()
    except Exception:
        return url.lower()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)

        retry = Retry(
            total=2,
            read=2,
            connect=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        _thread_local.session = session
    return session


def contains_any(text: str, needles: List[str]) -> Optional[str]:
    for needle in needles:
        if needle.lower() in text:
            return needle
    return None


def regex_hit(text: str, patterns: List[Pattern[str]]) -> Optional[str]:
    for pattern in patterns:
        if pattern.search(text):
            return pattern.pattern
    return None


def compile_patterns(items: List[str]) -> List[Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in items]


GLOBAL_NEGATIVE_TITLE = [
    "page not found",
    "not found",
    "404",
    "error",
    "oops",
    "missing page",
    "private site",
    "something went wrong",
    "access denied",
    "no such user",
]

GLOBAL_NEGATIVE_BODY = [
    "this page is no longer available",
    "we can't find that page",
    "we couldnt find that page",
    "we couldn't find that page",
    "this account doesn't exist",
    "this account does not exist",
    "the specified profile could not be found",
    "profile not found",
    "user not found",
    "username not found",
    "account not found",
    "page not found",
    "this page does not exist",
    "the page you requested could not be found",
    "the page you are looking for doesn't exist",
    "the page you are looking for does not exist",
    "nobody on reddit goes by that name",
    "sorry, this page isn't available",
    "sorry, this page isnt available",
    "something went wrong",
    "some error occurred while loading page for you",
    "some error occured while loading page for you",
    "this profile does not exist",
    "couldn't find this account",
    "could not find this account",
    "we couldn’t find that page",
    "we couldn't find that user",
    "user does not exist",
    "requested user was not found",
    "no such user",
    "sorry, this user was not found",
    "we looked everywhere but couldn't find this page",
    "we looked everywhere but couldnt find this page",
    "error code 404",
]

# Keep broad login strings OUT of challenge detection
GLOBAL_AUTH_STRINGS = [
    "sign in",
    "login",
    "log in",
    "sign up",
    "join now",
]

GLOBAL_CHALLENGE_STRINGS = [
    "just a moment",
    "attention required",
    "checking your browser",
    "verify you are human",
    "captcha",
    "recaptcha",
    "cf-browser-verification",
    "cloudflare",
    "temporarily blocked",
    "please enable javascript and cookies",
]

GLOBAL_NEGATIVE_URL_MARKERS = [
    "/404",
    "/404/",
    "/not-found",
    "/not_found",
    "/missing",
    "/error",
    "/errors/404",
]

GENERIC_SHELL_TITLES = {
    "tiktok - make your day",
    "threads",
    "instagram",
    "twitch",
    "500px",
    "mixcloud",
    "tryhackme | cyber security training",
    "hack the box",
    "spotify - web player",
    "spotify – web player",
    "trello",
    "programming problems and competitions :: hackerrank",
}

GENERIC_REDIRECT_PATHS = {
    "",
    "/",
    "/home",
    "/feed",
    "/explore",
    "/discover",
    "/login",
    "/signin",
    "/signup",
    "/join",
    "/auth",
    "/users/sign_in",
    "/accounts/login",
    "/404",
    "/not-found",
    "/error",
}


@dataclass
class PlatformRule:
    name: str
    url: str
    not_found_strings: List[str] = field(default_factory=list)
    title_not_found_strings: List[str] = field(default_factory=list)
    auth_strings: List[str] = field(default_factory=list)
    positive_strings: List[str] = field(default_factory=list)
    title_positive_strings: List[str] = field(default_factory=list)
    positive_regex: List[str] = field(default_factory=list)
    negative_regex: List[str] = field(default_factory=list)
    must_keep_username_in_final_url: bool = False
    allow_homepage_redirect: bool = False
    treat_403_as_unconfirmed: bool = True
    treat_429_as_unconfirmed: bool = True
    reliability: str = "high"


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


def make_rule(
    name: str,
    url: str,
    *,
    not_found_strings: Optional[List[str]] = None,
    title_not_found_strings: Optional[List[str]] = None,
    auth_strings: Optional[List[str]] = None,
    positive_strings: Optional[List[str]] = None,
    title_positive_strings: Optional[List[str]] = None,
    positive_regex: Optional[List[str]] = None,
    negative_regex: Optional[List[str]] = None,
    must_keep_username_in_final_url: bool = False,
    allow_homepage_redirect: bool = False,
    treat_403_as_unconfirmed: bool = True,
    treat_429_as_unconfirmed: bool = True,
    reliability: str = "high",
) -> PlatformRule:
    return PlatformRule(
        name=name,
        url=url,
        not_found_strings=not_found_strings or [],
        title_not_found_strings=title_not_found_strings or [],
        auth_strings=auth_strings or [],
        positive_strings=positive_strings or [],
        title_positive_strings=title_positive_strings or [],
        positive_regex=positive_regex or [],
        negative_regex=negative_regex or [],
        must_keep_username_in_final_url=must_keep_username_in_final_url,
        allow_homepage_redirect=allow_homepage_redirect,
        treat_403_as_unconfirmed=treat_403_as_unconfirmed,
        treat_429_as_unconfirmed=treat_429_as_unconfirmed,
        reliability=reliability,
    )


def build_platforms() -> Dict[str, PlatformRule]:
    rules: Dict[str, PlatformRule] = {}

    def add(rule: PlatformRule) -> None:
        rules[rule.name] = rule

    add(make_rule(
        "Reddit",
        "https://www.reddit.com/user/{}/",
        not_found_strings=[
            "nobody on reddit goes by that name",
            "page not found",
        ],
        title_not_found_strings=[
            "page not found",
        ],
        # login text exists on real reddit pages, so don't use it as auth_strings here
        auth_strings=[],
        positive_strings=[
            "posts",
            "comments",
            "karma",
            "cake day",
            "u/",
        ],
        title_positive_strings=[
            "reddit",
        ],
        positive_regex=[
            r"\bu/{u}\b",
            r"\bkarma\b",
            r"\bcake day\b",
        ],
        negative_regex=[
            r"nobody on reddit goes by that name",
        ],
        must_keep_username_in_final_url=True,
    ))

    add(make_rule(
        "Crates.io",
        "https://crates.io/users/{}",
        not_found_strings=[
            "user not found",
            "not found",
        ],
        title_not_found_strings=[
            "user not found",
            "not found",
        ],
        positive_strings=[
            "crates",
            "following",
        ],
        title_positive_strings=[
            "crates.io",
        ],
        negative_regex=[
            r"\b{u}\b\s*:\s*user not found",
            r"\buser not found\b",
        ],
        must_keep_username_in_final_url=True,
    ))

    add(make_rule(
        "PyPI",
        "https://pypi.org/user/{}",
        not_found_strings=[
            "we looked everywhere but couldn't find this page",
            "we looked everywhere but couldnt find this page",
            "error code 404",
            "404 not found",
            "not found",
        ],
        title_not_found_strings=[
            "404 not found",
            "not found",
        ],
        positive_strings=[
            "projects",
            "releases",
        ],
        negative_regex=[
            r"we looked everywhere but couldn'?t find this page",
            r"\berror code 404\b",
        ],
        must_keep_username_in_final_url=True,
    ))

    add(make_rule(
        "Hacker News",
        "https://news.ycombinator.com/user?id={}",
        not_found_strings=[
            "no such user",
            "user not found",
        ],
        title_not_found_strings=[
            "no such user",
        ],
        positive_strings=[
            "created",
            "karma",
            "about",
            "submissions",
            "comments",
        ],
        negative_regex=[
            r"\bno such user\b",
        ],
        must_keep_username_in_final_url=True,
    ))

    add(make_rule(
        "eBay",
        "https://www.ebay.com/usr/{}",
        not_found_strings=[
            "sorry, this user was not found",
            "user was not found",
            "this page could not be found",
            "no exact matches found",
        ],
        title_not_found_strings=[
            "sorry, this user was not found",
            "user was not found",
        ],
        positive_strings=[
            "feedback",
            "items for sale",
            "member since",
            "seller's other items",
        ],
        negative_regex=[
            r"sorry,\s*this user was not found",
            r"user was not found",
        ],
        must_keep_username_in_final_url=True,
    ))

    return rules


PLATFORMS: Dict[str, PlatformRule] = build_platforms()


def extract_json_ld_candidates(html_text: str) -> List[str]:
    return re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )


def site_specific_positive_from_json_ld(username: str, html_text: str) -> bool:
    username_l = username.lower()
    for blob in extract_json_ld_candidates(html_text[:120000]):
        norm = normalize_text(blob)
        if '"@type":"person"' in norm or '"@type":"profilepage"' in norm:
            if username_l in norm:
                return True
    return False


def title_is_explicit_not_found(title: str, username: str) -> bool:
    title = normalize_text(title)
    username_l = username.lower()
    hard_patterns = [
        f"{username_l}: user not found",
        f"{username_l} - user not found",
        f"{username_l} | user not found",
        "user not found",
        "profile not found",
        "account not found",
        "page not found",
        "no such user",
        "sorry, this user was not found",
        "we looked everywhere but couldn't find this page",
        "we looked everywhere but couldnt find this page",
        "this account doesn't exist",
        "this account does not exist",
    ]
    return any(p in title for p in hard_patterns)


def body_is_explicit_not_found(body: str) -> bool:
    body = normalize_text(body)
    hard_patterns = [
        "user not found",
        "profile not found",
        "account not found",
        "username not found",
        "requested user was not found",
        "this account doesn't exist",
        "this account does not exist",
        "this profile does not exist",
        "couldn't find this account",
        "could not find this account",
        "the specified profile could not be found",
        "nobody on reddit goes by that name",
        "this page does not exist",
        "the page you requested could not be found",
        "no such user",
        "sorry, this user was not found",
        "we looked everywhere but couldn't find this page",
        "we looked everywhere but couldnt find this page",
        "error code 404",
        "couldn't find this page",
        "could not find this page",
    ]
    return any(p in body for p in hard_patterns)


def is_challenge_page(title: str, body: str) -> bool:
    combined = normalize_text(f"{title} {body[:20000]}")
    return any(m in combined for m in GLOBAL_CHALLENGE_STRINGS)


def looks_like_generic_redirect(final_url: str, username: str) -> bool:
    username_l = username.lower()
    parsed = urlparse(final_url if "://" in final_url else "https://" + final_url)
    path = (parsed.path or "/").lower().rstrip("/") or "/"
    if username_l in final_url.lower():
        return False
    return path in GENERIC_REDIRECT_PATHS


def has_strong_positive_evidence(
    username: str,
    final_url: str,
    title: str,
    reasons: List[str],
) -> bool:
    username_l = username.lower()
    signals = 0

    if username_l in final_url.lower():
        signals += 1
    if username_l in title:
        signals += 1
    if "jsonld_person_with_username" in reasons:
        signals += 2
    if any(r.startswith("site_positive_body:") for r in reasons):
        signals += 1
    if any(r.startswith("site_positive_title:") for r in reasons):
        signals += 1
    if "stayed_on_username_url" in reasons:
        signals += 1

    return signals >= 2


def site_override(username: str, rule: PlatformRule, response: requests.Response) -> Optional[Tuple[str, str, str, int, int]]:
    raw_html = response.text[:MAX_BODY_BYTES]
    body = normalize_text(raw_html)
    title = normalize_text(extract_title(raw_html))
    final_url = safe_domain_path(response.url)
    username_l = username.lower()

    # Crates.io hard rules
    if rule.name == "Crates.io":
        if "user not found" in title or "user not found" in body:
            return ("not_found", "cratesio_explicit_not_found", "high", 0, 100)
        if response.status_code in (404, 410):
            return ("not_found", "cratesio_404", "high", 0, 100)

    # PyPI hard rules
    if rule.name == "PyPI":
        if response.status_code in (404, 410):
            return ("not_found", "pypi_404", "high", 0, 100)
        if (
            "we looked everywhere but couldn't find this page" in body
            or "we looked everywhere but couldnt find this page" in body
            or "error code 404" in body
        ):
            return ("not_found", "pypi_explicit_not_found", "high", 0, 100)

    # Hacker News hard rules
    if rule.name == "Hacker News":
        if "no such user" in body or "no such user" in title:
            return ("not_found", "hn_explicit_not_found", "high", 0, 100)

    # eBay hard rules
    if rule.name == "eBay":
        if "sorry, this user was not found" in body or "sorry, this user was not found" in title:
            return ("not_found", "ebay_explicit_not_found", "high", 0, 100)

    # Reddit special handling
    if rule.name == "Reddit":
        # Explicit negative
        if "nobody on reddit goes by that name" in body:
            return ("not_found", "reddit_explicit_not_found", "high", 0, 100)

        # If the page is on the expected user URL and has clear reddit profile signals,
        # do not let login/signup text downgrade it.
        if (
            username_l in final_url
            and (
                f"u/{username_l}" in body
                or "posts" in body
                or "comments" in body
                or "karma" in body
                or "cake day" in body
                or username_l in title
            )
        ):
            return ("found", "reddit_profile_signals", "high", 85, 5)

    return None


def score_response(username: str, rule: PlatformRule, response: requests.Response) -> Tuple[str, str, str, int, int]:
    raw_html = response.text[:MAX_BODY_BYTES]
    body = normalize_text(raw_html)
    early_body = body[:50000]
    title_raw = extract_title(raw_html)
    title = normalize_text(title_raw)
    final_url = safe_domain_path(response.url)
    request_url = safe_domain_path(response.request.url)
    username_l = username.lower()

    override = site_override(username, rule, response)
    if override is not None:
        return override

    positive = 0
    negative = 0
    reasons: List[str] = []

    if response.status_code in (404, 410):
        return "not_found", "hard_404_status", "high", 0, 100

    if response.status_code == 401:
        return "unconfirmed", "auth_required_status", "medium", 0, 35

    if response.status_code == 403 and rule.treat_403_as_unconfirmed:
        return "unconfirmed", "restricted_403", "medium", 0, 35

    if response.status_code == 429 and rule.treat_429_as_unconfirmed:
        return "unconfirmed", "rate_limited_429", "medium", 0, 35

    if 500 <= response.status_code <= 599:
        return "unconfirmed", "server_error", "low", 0, 30

    if title_is_explicit_not_found(title_raw, username):
        return "not_found", "explicit_not_found_title", "high", 0, 100

    if body_is_explicit_not_found(body):
        return "not_found", "explicit_not_found_body", "high", 0, 95

    if is_challenge_page(title_raw, raw_html):
        return "unconfirmed", "challenge_page", "medium", 0, 40

    global_title_hit = contains_any(title, GLOBAL_NEGATIVE_TITLE)
    global_body_hit = contains_any(body, GLOBAL_NEGATIVE_BODY)
    # Only weak auth text here now
    global_auth_hit = contains_any(early_body, GLOBAL_AUTH_STRINGS)
    url_negative_hit = contains_any(final_url, GLOBAL_NEGATIVE_URL_MARKERS)

    site_body_negative = contains_any(body, rule.not_found_strings)
    site_title_negative = contains_any(title, rule.title_not_found_strings)
    site_auth_negative = contains_any(early_body, rule.auth_strings)

    negative_regexes = compile_patterns([
        p.replace("{u}", re.escape(username_l)) for p in rule.negative_regex
    ])
    neg_regex_hit = regex_hit(body, negative_regexes)

    if site_title_negative:
        return "not_found", f"site_not_found_title:{site_title_negative}", "high", 0, 100

    if site_body_negative:
        return "not_found", f"site_not_found_body:{site_body_negative}", "high", 0, 95

    if neg_regex_hit:
        return "not_found", f"negative_regex:{neg_regex_hit}", "high", 0, 95

    if global_title_hit:
        negative += 35
        reasons.append(f"title_negative:{global_title_hit}")

    if global_body_hit:
        negative += 45
        reasons.append(f"body_negative:{global_body_hit}")

    # Do not make weak login text decisive anymore
    if global_auth_hit:
        negative += 5
        reasons.append(f"weak_auth_ui:{global_auth_hit}")

    if url_negative_hit:
        negative += 50
        reasons.append(f"url_negative:{url_negative_hit}")

    if site_auth_negative:
        negative += 20
        reasons.append(f"site_auth:{site_auth_negative}")

    redirected = response.url.rstrip("/").lower() != response.request.url.rstrip("/").lower()
    if redirected:
        reasons.append("redirected")

    if looks_like_generic_redirect(final_url, username) and not rule.allow_homepage_redirect:
        negative += 35
        reasons.append("redirected_to_generic_page")

    if rule.must_keep_username_in_final_url:
        if username_l in final_url:
            positive += 25
            reasons.append("username_in_final_url")
        else:
            negative += 35
            reasons.append("username_missing_from_final_url")

    if username_l in title and not global_title_hit and not site_title_negative:
        positive += 24
        reasons.append("username_in_title")

    if username_l in final_url:
        positive += 12
        reasons.append("username_in_url")

    if username_l in body and not site_body_negative:
        positive += 8
        reasons.append("username_in_body")

    site_positive_body = contains_any(body, rule.positive_strings)
    if site_positive_body and not site_body_negative and not global_body_hit:
        positive += 16
        reasons.append(f"site_positive_body:{site_positive_body}")

    site_positive_title = contains_any(title, rule.title_positive_strings)
    if site_positive_title and not site_title_negative and not global_title_hit:
        positive += 18
        reasons.append(f"site_positive_title:{site_positive_title}")

    if site_specific_positive_from_json_ld(username, raw_html):
        positive += 28
        reasons.append("jsonld_person_with_username")

    if (
        not global_body_hit
        and not global_title_hit
        and not site_body_negative
        and not site_title_negative
        and any(x in body for x in [
            "followers", "following", "posts", "projects",
            "repositories", "member since", "joined", "about"
        ])
    ):
        positive += 10
        reasons.append("generic_profile_signal")

    if title in GENERIC_SHELL_TITLES and username_l not in body and username_l not in final_url:
        negative += 45
        reasons.append("generic_shell_title")

    if response.status_code == 200 and len(raw_html) < 8000 and username_l not in body and username_l not in title:
        negative += 20
        reasons.append("tiny_body_without_username")

    if response.status_code == 200 and len(raw_html) > 50000 and username_l in body and negative < 50:
        positive += 12
        reasons.append("large_body_username_present")

    if request_url == final_url and username_l in final_url:
        positive += 8
        reasons.append("stayed_on_username_url")

    delta = positive - negative

    if negative >= 70 and delta <= -15:
        confidence = "high" if negative >= 90 else "medium"
        return "not_found", "; ".join(reasons), confidence, positive, negative

    if (
        positive >= 45
        and delta >= 12
        and has_strong_positive_evidence(username, final_url, title, reasons)
    ):
        confidence = "high" if positive >= 70 else "medium"
        return "found", "; ".join(reasons), confidence, positive, negative

    if negative >= 55 and delta <= -10:
        confidence = "high" if negative >= 85 else "medium"
        return "not_found", "; ".join(reasons), confidence, positive, negative

    if positive >= 35 and negative < 35 and has_strong_positive_evidence(username, final_url, title, reasons):
        return "found", "; ".join(reasons), "medium", positive, negative

    return "unconfirmed", "; ".join(reasons) if reasons else "weak_or_conflicting_signals", "low", positive, negative


def check_platform(rule: PlatformRule, username: str, timeout: float = DEFAULT_TIMEOUT) -> ScanResult:
    url = rule.url.format(username)
    session = get_session()
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return ScanResult(
                platform=rule.name,
                url=url,
                final_url=response.url,
                state="unconfirmed",
                status_code=response.status_code,
                confidence="low",
                note=f"unexpected_content_type:{content_type}",
                title=None,
                matched_rule="content_type_guard",
                response_length=len(response.text) if response.text else 0,
                positive_score=0,
                negative_score=0,
            )

        title = extract_title(response.text[:MAX_BODY_BYTES]) or None
        state, note, confidence, pos, neg = score_response(username, rule, response)
        return ScanResult(
            platform=rule.name,
            url=url,
            final_url=response.url,
            state=state,
            status_code=response.status_code,
            confidence=confidence,
            note=note,
            title=title,
            matched_rule="site_aware_soft404_engine_v5",
            response_length=len(response.text) if response.text else 0,
            positive_score=pos,
            negative_score=neg,
        )
    except requests.RequestException as exc:
        return ScanResult(
            platform=rule.name,
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
    timeout: float = DEFAULT_TIMEOUT,
    workers: int = MAX_WORKERS,
    platforms: Optional[Dict[str, PlatformRule]] = None,
) -> List[ScanResult]:
    if not username or not username.strip():
        raise ValueError("username cannot be empty")

    username = username.strip()
    platform_map = platforms or PLATFORMS
    results: List[ScanResult] = []

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 100))) as executor:
        futures = {
            executor.submit(check_platform, rule, username, timeout): name
            for name, rule in platform_map.items()
        }
        for future in as_completed(futures):
            results.append(future.result())

    order = {"found": 0, "not_found": 1, "unconfirmed": 2}
    results.sort(key=lambda r: (order.get(r.state, 99), r.platform.lower()))
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


def humanize_reason(note: Optional[str], state: str, positive_score: int, negative_score: int) -> str:
    if not note:
        if state == "found":
            return "The page showed enough profile signals to classify the account as likely found."
        if state == "not_found":
            return "The page showed strong missing-page or soft-404 signals, so the account was classified as not found."
        return "The page did not provide enough reliable evidence to make a confident decision."

    if note.startswith("request_error:"):
        return "The site could not be checked cleanly because the request failed, timed out, or was blocked."

    if note.startswith("unexpected_content_type:"):
        return "The site returned a non-HTML response, so the result could not be evaluated confidently."

    if "reddit_profile_signals" in note:
        return "The Reddit page showed real profile signals, so weak login UI text was ignored."

    if "cratesio_explicit_not_found" in note:
        return "Crates.io explicitly said the user was not found."

    if "pypi_explicit_not_found" in note or "pypi_404" in note:
        return "PyPI returned an explicit missing-page response."

    if "hn_explicit_not_found" in note:
        return "Hacker News explicitly said no such user exists."

    if "ebay_explicit_not_found" in note:
        return "eBay explicitly said the user was not found."

    if "hard_404_status" in note:
        return "The site returned a hard 404 or 410 response, so the account was classified as not found."

    if "explicit_not_found_title" in note or "explicit_not_found_body" in note:
        return "The page explicitly stated the user or profile was not found."

    if "site_not_found_body" in note or "site_not_found_title" in note or "negative_regex" in note:
        return "The page contained site-specific not-found language, which is strong evidence the account does not exist."

    if "redirected_to_generic_page" in note or "username_missing_from_final_url" in note:
        return "The username URL redirected to a generic page or dropped the username entirely, which usually indicates no profile."

    if "jsonld_person_with_username" in note and "username_in_title" in note:
        return "The page exposed structured profile metadata and matched the username in the title, which is strong evidence the profile exists."

    if "generic_shell_title" in note or "tiny_body_without_username" in note:
        return "The response looked like a generic shell page or weak wrapper page rather than a real user profile."

    if "challenge_page" in note or "restricted_403" in note or "rate_limited_429" in note:
        return "The site presented a real anti-bot control or request restriction, so the result was left unconfirmed."

    if state == "found":
        if positive_score >= 70:
            return "Multiple strong profile signals matched the username, so the account was classified as found with high confidence."
        return "Several profile signals matched the username, so the account was classified as likely found."

    if state == "not_found":
        if negative_score >= 90:
            return "Multiple strong missing-page signals were detected, so the account was classified as not found with high confidence."
        return "The page showed enough negative evidence to classify the account as not found."

    return "The result contained mixed or limited evidence, so it was marked unconfirmed for manual review."


if __name__ == "__main__":
    username = "bertsec"
    results = scan_username(username, timeout=8.0, workers=32)
    print(json.dumps({
        "summary": results_summary(results),
        "results": results_to_dicts(results),
    }, indent=2))
