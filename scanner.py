from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Pattern, Tuple
from urllib.parse import urlparse, unquote

import requests


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
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
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


def visible_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.path or "/").lower()
    except Exception:
        return "/"


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
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
    "just a moment",
    "attention required",
    "access denied",
    "sign in",
    "login",
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
]

GLOBAL_AUTH_STRINGS = [
    "sign in",
    "login",
    "log in",
    "sign up",
    "join now",
    "checking your browser",
    "attention required",
    "verify you are human",
    "captcha",
    "recaptcha",
    "access denied",
    "temporarily restricted",
    "enable javascript and cookies to continue",
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
    )


def build_platforms() -> Dict[str, PlatformRule]:
    rules: Dict[str, PlatformRule] = {}

    def add(rule: PlatformRule) -> None:
        rules[rule.name] = rule

    # Core high-value platforms with site-specific tuning
    add(make_rule(
        "GitHub", "https://github.com/{}",
        not_found_strings=["not found"],
        title_positive_strings=["github", "@"],
        positive_strings=["followers", "following", "repositories", "contributions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "GitLab", "https://gitlab.com/{}",
        not_found_strings=["page not found", "the page could not be found"],
        positive_strings=["projects", "followers", "following", "activity"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Bitbucket", "https://bitbucket.org/{}",
        not_found_strings=["this page doesn't exist", "404"],
        positive_strings=["repositories", "snippets", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Codeberg", "https://codeberg.org/{}",
        not_found_strings=["not found"],
        positive_strings=["repositories", "activity", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "SourceHut", "https://git.sr.ht/~{}",
        not_found_strings=["not found"],
        positive_strings=["repositories", "activity"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Hugging Face", "https://huggingface.co/{}",
        not_found_strings=["user not found", "404"],
        positive_strings=["models", "datasets", "spaces", "followers"],
        title_positive_strings=["hugging face"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "PyPI", "https://pypi.org/user/{}",
        not_found_strings=["404 not found", "not found"],
        positive_strings=["projects", "releases"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "npm", "https://www.npmjs.com/~{}",
        not_found_strings=["not found"],
        positive_strings=["packages", "collaborators"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Docker Hub", "https://hub.docker.com/u/{}",
        not_found_strings=["404 page not found", "page not found"],
        positive_strings=["repositories", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Crates.io", "https://crates.io/users/{}",
        not_found_strings=["user not found", "not found"],
        title_not_found_strings=["user not found", "not found"],
        positive_strings=["crates", "following"],
        title_positive_strings=["crates.io"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "RubyGems", "https://rubygems.org/profiles/{}",
        not_found_strings=["this page could not be found", "not found"],
        positive_strings=["gems", "downloads", "versions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Packagist", "https://packagist.org/users/{}",
        not_found_strings=["404 not found", "not found"],
        positive_strings=["packages", "downloads"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "CPAN", "https://metacpan.org/author/{}",
        not_found_strings=["not found"],
        positive_strings=["release", "distribution", "favorites"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Dev.to", "https://dev.to/{}",
        not_found_strings=["404 not found", "page not found"],
        positive_strings=["followers", "following", "posts", "articles"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Hashnode", "https://{}.hashnode.dev",
        not_found_strings=["page not found", "this site can't be reached", "dns_probe_finished_nxdomain"],
        positive_strings=["posts", "followers", "following"],
        title_positive_strings=["hashnode"],
    ))
    add(make_rule(
        "Medium", "https://medium.com/@{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["followers", "following", "member since"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Substack", "https://{}.substack.com",
        not_found_strings=["this site can’t be reached", "this site can't be reached", "dns_probe_finished_nxdomain"],
        positive_strings=["subscribe", "archive", "posts"],
        title_positive_strings=["substack"],
    ))
    add(make_rule(
        "WordPress", "https://{}.wordpress.com",
        not_found_strings=["do you want to register", "site unavailable", "doesn’t exist", "doesn't exist"],
        positive_strings=["posts", "comments", "wordpress.com"],
    ))
    add(make_rule(
        "About.me", "https://about.me/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["about.me", "follow", "message"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Linktree", "https://linktr.ee/{}",
        not_found_strings=["not found", "this profile doesn't exist", "this profile does not exist"],
        positive_strings=["followers", "links"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Ko-fi", "https://ko-fi.com/{}",
        not_found_strings=["404", "not found"],
        positive_strings=["support", "posts", "shop", "gallery"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Patreon", "https://www.patreon.com/{}",
        not_found_strings=["looks like this page is missing", "not found"],
        positive_strings=["members", "posts", "join"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Behance", "https://www.behance.net/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["followers", "following", "projects", "appreciations"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Dribbble", "https://dribbble.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["shots", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "DeviantArt", "https://www.deviantart.com/{}",
        not_found_strings=["page not found", "this page does not exist"],
        positive_strings=["watchers", "deviations", "favourites"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "ArtStation", "https://www.artstation.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["followers", "following", "portfolio"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Pixiv", "https://www.pixiv.net/en/users/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["illustrations", "manga", "bookmarks"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "500px", "https://500px.com/p/{}",
        not_found_strings=["404", "not found"],
        positive_strings=["followers", "following", "photos"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Flickr", "https://www.flickr.com/people/{}",
        not_found_strings=["not found", "page not found"],
        positive_strings=["photostream", "albums", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Unsplash", "https://unsplash.com/@{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["photos", "collections", "likes"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Pexels", "https://www.pexels.com/@{}/",
        not_found_strings=["page not found", "not found"],
        positive_strings=["followers", "following", "photos", "videos"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Instagram", "https://www.instagram.com/{}/",
        not_found_strings=["sorry, this page isn't available", "page isn't available", "page isnt available"],
        auth_strings=["login", "sign up", "log in"],
        positive_strings=["posts", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Threads", "https://www.threads.net/@{}",
        not_found_strings=["sorry, this page isn't available", "page not found"],
        auth_strings=["log in", "sign up"],
        positive_strings=["threads", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "X", "https://x.com/{}",
        not_found_strings=["this account doesn’t exist", "this account doesn't exist"],
        auth_strings=["join x today", "log in", "sign up"],
        positive_strings=["followers", "following", "posts"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Facebook", "https://www.facebook.com/{}",
        not_found_strings=["this content isn't available right now", "content isn't available right now"],
        auth_strings=["log into facebook", "log in to facebook"],
        positive_strings=["friends", "photos", "posts", "about"],
    ))
    add(make_rule(
        "TikTok", "https://www.tiktok.com/@{}",
        not_found_strings=["couldn't find this account", "could not find this account", "page not available"],
        auth_strings=["log in", "sign up", "verify to continue"],
        positive_strings=["followers", "following", "likes"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Snapchat", "https://www.snapchat.com/add/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["snapchat"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Pinterest", "https://www.pinterest.com/{}/",
        not_found_strings=["sorry, we couldn't find that page", "we couldn't find that page"],
        positive_strings=["followers", "following", "boards", "pins"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Reddit", "https://www.reddit.com/user/{}",
        not_found_strings=["nobody on reddit goes by that name", "page not found"],
        positive_strings=["karma", "cake day", "posts", "comments"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Tumblr", "https://{}.tumblr.com",
        not_found_strings=["there's nothing here", "there's nothing here.", "not found"],
        positive_strings=["tumblr", "archive", "following"],
    ))
    add(make_rule(
        "Mastodon Social", "https://mastodon.social/@{}",
        not_found_strings=["not found", "404"],
        positive_strings=["followers", "following", "statuses"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Mastodon Online", "https://mastodon.online/@{}",
        not_found_strings=["not found", "404"],
        positive_strings=["followers", "following", "statuses"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Bluesky", "https://bsky.app/profile/{}",
        not_found_strings=["profile not found", "not found"],
        positive_strings=["followers", "following", "posts"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Telegram", "https://t.me/{}",
        not_found_strings=["if you have telegram, you can contact", "page not found"],
        positive_strings=["send message", "telegram"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Keybase", "https://keybase.io/{}",
        not_found_strings=["we couldn't find", "not found"],
        positive_strings=["proofs", "following", "followers", "keybase"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Disqus", "https://disqus.com/by/{}/",
        not_found_strings=["page not found", "not found"],
        positive_strings=["comments", "disqus"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Gravatar", "https://gravatar.com/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["profile", "contact", "about"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Hacker News", "https://news.ycombinator.com/user?id={}",
        not_found_strings=["no such user", "user not found"],
        positive_strings=["created", "karma", "about", "submissions", "comments"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Lobsters", "https://lobste.rs/u/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["karma", "stories", "comments"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "LeetCode", "https://leetcode.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["ranking", "reputation", "solutions", "submissions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "HackerRank", "https://www.hackerrank.com/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["badges", "certificates", "submissions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Codewars", "https://www.codewars.com/users/{}",
        not_found_strings=["404", "not found"],
        positive_strings=["honor", "completed kata", "allies"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "CodeChef", "https://www.codechef.com/users/{}",
        not_found_strings=["user does not exist", "page not found"],
        positive_strings=["rating", "stars", "global rank"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "AtCoder", "https://atcoder.jp/users/{}",
        not_found_strings=["user not found", "404"],
        positive_strings=["rating", "highest rating", "rank"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Topcoder", "https://www.topcoder.com/members/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["member", "challenges", "stats"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Exercism", "https://exercism.org/profiles/{}",
        not_found_strings=["404", "not found"],
        positive_strings=["tracks", "mentoring", "solutions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "freeCodeCamp", "https://www.freecodecamp.org/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["certifications", "portfolio", "projects"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "TryHackMe", "https://tryhackme.com/p/{}",
        not_found_strings=["404", "not found"],
        auth_strings=["sign in", "login"],
        positive_strings=["badges", "rooms", "rank"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Root Me", "https://www.root-me.org/{}",
        not_found_strings=["not found", "404"],
        positive_strings=["score", "challenges", "profile"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Hackaday", "https://hackaday.io/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["projects", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Instructables", "https://www.instructables.com/member/{}/",
        not_found_strings=["page not found", "404"],
        positive_strings=["instructables", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Steam", "https://steamcommunity.com/id/{}",
        not_found_strings=["the specified profile could not be found", "profile could not be found"],
        positive_strings=["friends", "games", "screenshots", "inventory"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Chess.com", "https://www.chess.com/member/{}",
        not_found_strings=["member not found", "page not found"],
        positive_strings=["ratings", "joined", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Lichess", "https://lichess.org/@/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["rating", "games", "puzzles", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Twitch", "https://www.twitch.tv/{}",
        not_found_strings=["sorry. unless you’ve got a time machine", "page not found"],
        auth_strings=["log in", "sign up"],
        positive_strings=["followers", "schedule", "videos", "clips"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "YouTube", "https://www.youtube.com/@{}",
        not_found_strings=["this page isn't available", "page not found"],
        positive_strings=["videos", "subscribers", "joined"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Vimeo", "https://vimeo.com/{}",
        not_found_strings=["sorry, we couldn’t find that page", "sorry, we couldn't find that page"],
        positive_strings=["followers", "following", "videos"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "SoundCloud", "https://soundcloud.com/{}",
        not_found_strings=["not found", "404"],
        positive_strings=["tracks", "followers", "following", "likes"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Bandcamp", "https://{}.bandcamp.com",
        not_found_strings=["sorry, that something isn't here", "sorry, that something isn’t here"],
        positive_strings=["track", "album", "merch", "bandcamp"],
    ))
    add(make_rule(
        "Last.fm", "https://www.last.fm/user/{}",
        not_found_strings=["user not found", "not found"],
        positive_strings=["scrobbles", "loved tracks", "playlists"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Mixcloud", "https://www.mixcloud.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["followers", "following", "shows"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Genius", "https://genius.com/{}",
        not_found_strings=["page not found", "404"],
        positive_strings=["lyrics", "contributors", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Letterboxd", "https://letterboxd.com/{}/",
        not_found_strings=["sorry, we can’t find the page", "sorry, we can't find the page"],
        positive_strings=["films", "followers", "following", "reviews"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Wattpad", "https://www.wattpad.com/user/{}",
        not_found_strings=["page not found", "user not found"],
        positive_strings=["stories", "reading lists", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Archive of Our Own", "https://archiveofourown.org/users/{}",
        not_found_strings=["error 404", "not found"],
        positive_strings=["works", "bookmarks", "subscriptions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "AllTrails", "https://www.alltrails.com/members/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["completed trails", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Untappd", "https://untappd.com/user/{}",
        not_found_strings=["not found", "page not found"],
        positive_strings=["beers", "check-ins", "friends"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Vivino", "https://www.vivino.com/users/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["followers", "following", "wines"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Venmo", "https://venmo.com/{}",
        not_found_strings=["page not found", "profile unavailable"],
        positive_strings=["venmo"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "PayPal.me", "https://paypal.me/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["paypal"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Etsy", "https://www.etsy.com/people/{}",
        not_found_strings=["uh oh!", "page not found"],
        positive_strings=["favorites", "followers", "etsy"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Poshmark", "https://poshmark.com/closet/{}",
        not_found_strings=["this page could not be found", "not found"],
        positive_strings=["closet", "listings", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Depop", "https://www.depop.com/{}",
        not_found_strings=["not found", "404"],
        positive_strings=["reviews", "followers", "following", "listings"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "eBay", "https://www.ebay.com/usr/{}",
        not_found_strings=["no exact matches found", "this page could not be found"],
        positive_strings=["feedback", "items for sale", "member since"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "MyAnimeList", "https://myanimelist.net/profile/{}",
        not_found_strings=["404 not found", "page not found"],
        positive_strings=["anime list", "manga list", "friends", "favorites"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "AniList", "https://anilist.co/user/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["anime", "manga", "following", "followers"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Trakt", "https://trakt.tv/users/{}",
        not_found_strings=["404", "not found"],
        positive_strings=["history", "collection", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Pastebin", "https://pastebin.com/u/{}",
        not_found_strings=["not found", "404"],
        positive_strings=["public pastes", "views", "pastebin"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Devpost", "https://devpost.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["projects", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "ResearchGate", "https://www.researchgate.net/profile/{}",
        not_found_strings=["page not found", "not found"],
        positive_strings=["publications", "citations", "reads"],
    ))
    add(make_rule(
        "ORCID", "https://orcid.org/{}",
        not_found_strings=["record not found", "not found"],
        positive_strings=["works", "employment", "education"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Muck Rack", "https://muckrack.com/{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["articles", "portfolio", "mentions"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Thingiverse", "https://www.thingiverse.com/{}/designs",
        not_found_strings=["404", "page not found"],
        positive_strings=["designs", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))
    add(make_rule(
        "Printables", "https://www.printables.com/@{}",
        not_found_strings=["404", "page not found"],
        positive_strings=["models", "followers", "following"],
        must_keep_username_in_final_url=True,
    ))

    # Large extension set to break 200+
    bulk_rules = [
        ("Gitea", "https://gitea.com/{}"),
        ("Forgejo", "https://codeberg.org/{}"),
        ("Launchpad", "https://launchpad.net/~{}"),
        ("Replit", "https://replit.com/@{}"),
        ("CodePen", "https://codepen.io/{}"),
        ("JSFiddle", "https://jsfiddle.net/user/{}/"),
        ("StackBlitz", "https://stackblitz.com/@{}"),
        ("Glitch", "https://glitch.com/@{}"),
        ("Observable", "https://observablehq.com/@{}"),
        ("Kaggle", "https://www.kaggle.com/{}"),
        ("Blogger", "https://{}.blogspot.com"),
        ("Ghost", "https://{}.ghost.io"),
        ("Wix", "https://{}.wixsite.com"),
        ("Carrd", "https://{}.carrd.co"),
        ("Buy Me a Coffee", "https://www.buymeacoffee.com/{}"),
        ("Gumroad", "https://{}.gumroad.com"),
        ("Product Hunt", "https://www.producthunt.com/@{}"),
        ("Indie Hackers", "https://www.indiehackers.com/{}"),
        ("Wellfound", "https://wellfound.com/u/{}"),
        ("Freelancer", "https://www.freelancer.com/u/{}"),
        ("Fiverr", "https://www.fiverr.com/{}"),
        ("99designs", "https://99designs.com/profiles/{}"),
        ("Envato", "https://elements.envato.com/user/{}"),
        ("Codecanyon", "https://codecanyon.net/user/{}"),
        ("ThemeForest", "https://themeforest.net/user/{}"),
        ("VSCO", "https://vsco.co/{}/gallery"),
        ("Canva", "https://www.canva.com/{}"),
        ("VK", "https://vk.com/{}"),
        ("OK", "https://ok.ru/{}"),
        ("Weibo", "https://www.weibo.com/{}"),
        ("Naver Blog", "https://blog.naver.com/{}"),
        ("Quora", "https://www.quora.com/profile/{}"),
        ("Pixelfed Social", "https://pixelfed.social/{}"),
        ("Discord Vanity Guess", "https://discord.com/users/{}"),
        ("Stack Overflow", "https://stackoverflow.com/users/{}"),
        ("Stack Exchange", "https://stackexchange.com/users/{}"),
        ("Super User", "https://superuser.com/users/{}"),
        ("Server Fault", "https://serverfault.com/users/{}"),
        ("Ask Ubuntu", "https://askubuntu.com/users/{}"),
        ("GeeksforGeeks", "https://auth.geeksforgeeks.org/user/{}/"),
        ("Hack The Box", "https://app.hackthebox.com/profile/{}"),
        ("CTFtime", "https://ctftime.org/team/{}"),
        ("Roblox", "https://www.roblox.com/users/profile?username={}"),
        ("XboxGamertag", "https://xboxgamertag.com/search/{}"),
        ("PSNProfiles", "https://psnprofiles.com/{}"),
        ("Nintendo Life", "https://www.nintendolife.com/users/{}"),
        ("Speedrun.com", "https://www.speedrun.com/user/{}"),
        ("Dailymotion", "https://www.dailymotion.com/{}"),
        ("Spotify User", "https://open.spotify.com/user/{}"),
        ("Deezer", "https://www.deezer.com/us/profile/{}"),
        ("IMDb", "https://www.imdb.com/user/{}"),
        ("Goodreads", "https://www.goodreads.com/{}"),
        ("StoryGraph", "https://app.thestorygraph.com/profile/{}"),
        ("FanFiction", "https://www.fanfiction.net/u/{}"),
        ("Tripadvisor", "https://www.tripadvisor.com/Profile/{}"),
        ("Strava", "https://www.strava.com/athletes/{}"),
        ("Garmin Connect", "https://connect.garmin.com/modern/profile/{}"),
        ("Runkeeper", "https://runkeeper.com/user/{}"),
        ("Couchsurfing", "https://www.couchsurfing.com/people/{}"),
        ("TripIt", "https://www.tripit.com/people/{}"),
        ("Cash App", "https://cash.app/${}"),
        ("Mercari", "https://www.mercari.com/u/{}/"),
        ("Rakuten Viki", "https://www.viki.com/users/{}/about"),
        ("RAWG", "https://rawg.io/@{}"),
        ("Paste.ee", "https://paste.ee/u/{}"),
        ("IFTTT", "https://ifttt.com/p/{}"),
        ("Trello", "https://trello.com/{}"),
        ("Notion Site", "https://{}.notion.site"),
        ("Miro", "https://miro.com/app/board/{}"),
        ("Figma Community", "https://www.figma.com/@{}"),
        ("Sketchfab", "https://sketchfab.com/{}"),
        ("Polywork", "https://www.polywork.com/{}"),
        ("Peerlist", "https://peerlist.io/{}"),
        ("Academia", "https://independent.academia.edu/{}"),
        ("Google Scholar", "https://scholar.google.com/citations?user={}"),
        ("OpenSea", "https://opensea.io/{}"),
        ("Giters", "https://giters.com/{}"),
        ("LibraryThing", "https://www.librarything.com/profile/{}"),
        ("Houzz", "https://www.houzz.com/user/{}"),
        ("Ello", "https://ello.co/{}"),
        ("SlideShare", "https://www.slideshare.net/{}"),
        ("Scribd", "https://www.scribd.com/{}"),
        ("Issuu", "https://issuu.com/{}"),
        ("Battle.net Search", "https://worldofwarcraft.blizzard.com/en-us/search?q={}"),
        ("NameMC", "https://namemc.com/profile/{}"),
        ("NationStates", "https://www.nationstates.net/nation={}"),
        ("ReverbNation", "https://www.reverbnation.com/{}"),
        ("Smule", "https://www.smule.com/{}"),
        ("Polarsteps", "https://www.polarsteps.com/{}"),
        ("Codecademy", "https://www.codecademy.com/profiles/{}"),
        ("Flipboard", "https://flipboard.com/@{}"),
        ("Bento", "https://bento.me/{}"),
        ("Pearltrees", "https://www.pearltrees.com/{}"),
        ("Shutterstock", "https://www.shutterstock.com/g/{}"),
        ("EyeEm", "https://www.eyeem.com/u/{}"),
        ("Civitai", "https://civitai.com/user/{}"),
        ("Giphy", "https://giphy.com/{}"),
        ("Myspace", "https://myspace.com/{}"),
        ("Ko-fi Shop", "https://ko-fi.com/{}"),
        ("AngelList Legacy", "https://angel.co/u/{}"),
        ("Crunchbase People", "https://www.crunchbase.com/person/{}"),
        ("Pixelfed", "https://pixelfed.social/{}"),
        ("Mastodon", "https://mastodon.social/@{}"),
        ("PeerTube", "https://peertube.tv/accounts/{}"),
        ("BookBub", "https://www.bookbub.com/profile/{}"),
        ("Bookshop", "https://bookshop.org/shop/{}"),
        ("Rumble", "https://rumble.com/user/{}"),
        ("Kick", "https://kick.com/{}"),
        ("Locals", "https://{}.locals.com"),
        ("Newgrounds", "https://{}.newgrounds.com"),
        ("Itch.io", "https://{}.itch.io"),
        ("Modrinth", "https://modrinth.com/user/{}"),
        ("CurseForge", "https://www.curseforge.com/members/{}"),
        ("Planet Minecraft", "https://www.planetminecraft.com/member/{}/"),
        ("MCPEDL", "https://mcpedl.com/user/{}"),
        ("Amino", "https://aminoapps.com/u/{}"),
        ("Koo", "https://www.kooapp.com/profile/{}"),
        ("Ravelry", "https://www.ravelry.com/people/{}"),
        ("Inkbunny", "https://inkbunny.net/{}"),
        ("Fur Affinity", "https://www.furaffinity.net/user/{}"),
        ("Tapas", "https://tapas.io/{}"),
        ("Webtoon Canvas", "https://www.webtoons.com/creator/{}"),
        ("Reedsy", "https://reedsy.com/{}"),
        ("Contently", "https://{}.contently.com"),
        ("Clapper", "https://clapperapp.com/{}"),
        ("Speakrj", "https://speakerhub.com/speaker/{}"),
        ("Speaker Deck", "https://speakerdeck.com/{}"),
        ("Tripadvisor Legacy", "https://tripadvisor.com/members/{}"),
        ("Vero", "https://vero.co/{}"),
        ("MeWe", "https://mewe.com/i/{}"),
        ("Gab", "https://gab.com/{}"),
        ("Parler", "https://parler.com/profile/{}"),
        ("Truth Social", "https://truthsocial.com/@{}"),
        ("Minds", "https://www.minds.com/{}"),
        ("LiveJournal", "https://{}.livejournal.com"),
        ("Dreamwidth", "https://{}.dreamwidth.org"),
        ("Blogger Profile", "https://www.blogger.com/profile/{}"),
        ("Soundgasm", "https://soundgasm.net/u/{}"),
        ("Replit Teams", "https://replit.com/@{}"),
        ("Read.cv", "https://read.cv/{}"),
        ("Cara", "https://cara.app/{}"),
        ("Mastodon Art", "https://mastodon.art/@{}"),
        ("Fosstodon", "https://fosstodon.org/@{}"),
        ("Mstdn Social", "https://mstdn.social/@{}"),
        ("Lemmy World", "https://lemmy.world/u/{}"),
        ("Kbin Social", "https://kbin.social/u/{}"),
        ("Write.as", "https://write.as/{}"),
        ("BuySellAds", "https://www.buysellads.com/{}"),
        ("DailyMotion Legacy", "https://www.dailymotion.com/{}"),
        ("GitHub Gist", "https://gist.github.com/{}"),
        ("ReadTheDocs", "https://readthedocs.org/profiles/{}"),
        ("Amino Profile", "https://aminoapps.com/u/{}"),
        ("Mastodon Cloud", "https://mstdn.jp/@{}"),
        ("Flickr NSID Guess", "https://www.flickr.com/photos/{}"),
        ("Canva Profile Guess", "https://www.canva.com/{}"),
        ("AudioJungle", "https://audiojungle.net/user/{}"),
        ("VideoHive", "https://videohive.net/user/{}"),
        ("GraphicRiver", "https://graphicriver.net/user/{}"),
        ("CodeCanyon Author", "https://codecanyon.net/user/{}"),
        ("Envato Market", "https://themeforest.net/user/{}"),
        ("Crowdin", "https://crowdin.com/profile/{}"),
        ("Transifex", "https://www.transifex.com/user/profile/{}"),
        ("Kofi Page", "https://ko-fi.com/{}"),
        ("Maven Repository", "https://mvnrepository.com/artifact/{}"),
        ("Anaconda", "https://anaconda.org/{}"),
        ("npmjs Org Guess", "https://www.npmjs.com/~{}"),
        ("DevRant", "https://devrant.com/users/{}"),
        ("Gitee", "https://gitee.com/{}"),
        ("SourceForge", "https://sourceforge.net/u/{}/profile"),
        ("OpenCollective", "https://opencollective.com/{}"),
        ("Liberapay", "https://liberapay.com/{}"),
        ("Blogger Custom", "https://{}.blogspot.com"),
        ("Bookmeter", "https://bookmeter.com/users/{}"),
        ("Pixelfed FR", "https://pixelfed.fr/{}"),
        ("Pixelfed UNO", "https://pixelfed.uno/{}"),
        ("Mastodon Cloud Alt", "https://mastodon.cloud/@{}"),
        ("ChessTempo", "https://chesstempo.com/profile/{}"),
        ("BoardGameGeek", "https://boardgamegeek.com/user/{}"),
        ("RateYourMusic", "https://rateyourmusic.com/~{}"),
        ("Discogs", "https://www.discogs.com/user/{}"),
        ("Setlist.fm", "https://www.setlist.fm/user/{}"),
        ("Replit Bounties", "https://replit.com/@{}"),
        ("MobyGames", "https://www.mobygames.com/user/{}"),
        ("Backloggd", "https://www.backloggd.com/u/{}/"),
        ("HowLongToBeat", "https://howlongtobeat.com/user/{}"),
        ("Amino Games", "https://aminoapps.com/u/{}"),
        ("OpenLibrary", "https://openlibrary.org/people/{}"),
        ("Blipfoto", "https://www.blipfoto.com/{}"),
        ("Ello Art", "https://ello.co/{}"),
        ("Ulule", "https://ulule.com/{}"),
        ("Kickstarter Creator Guess", "https://www.kickstarter.com/profile/{}"),
        ("Product Hunt Makers", "https://www.producthunt.com/@{}"),
        ("Pearltrees User", "https://www.pearltrees.com/{}"),
        ("Shapr3D Community", "https://discourse.shapr3d.com/u/{}"),
        ("Discourse Meta", "https://meta.discourse.org/u/{}"),
        ("Kitsu", "https://kitsu.io/users/{}"),
        ("VNDB", "https://vndb.org/u{}"),
        ("Mastodon Tech", "https://techhub.social/@{}"),
        ("SpaceHey", "https://spacehey.com/{}"),
        ("ModDB", "https://www.moddb.com/members/{}"),
        ("Nexus Mods", "https://next.nexusmods.com/profile/{}"),
        ("AO3 Profile", "https://archiveofourown.org/users/{}"),
        ("Comic Fury", "https://{}.comicfury.com"),
        ("Neocities", "https://{}.neocities.org"),
        ("GitLab Snippets", "https://gitlab.com/{}"),
        ("Mastodon World", "https://mastodon.world/@{}"),
        ("Squabbles", "https://squabbles.io/u/{}"),
        ("Mastodon XYZ", "https://mastodon.xyz/@{}"),
        ("CounterSocial", "https://counter.social/@{}"),
        ("Pillowfort", "https://www.pillowfort.social/{}"),
        ("WikiTree", "https://www.wikitree.com/wiki/{}"),
        ("Bookwyrm Social", "https://bookwyrm.social/user/{}"),
        ("Mastodon Books", "https://bookstodon.com/@{}"),
        ("Aether", "https://getaether.net/{}"),
        ("Lemmy ML", "https://lemmy.ml/u/{}"),
        ("Mastodon Linux", "https://fosstodon.org/@{}"),
        ("Micro.blog", "https://micro.blog/{}"),
        ("Post.news", "https://post.news/{}"),
        ("Mastodon Design", "https://mastodon.design/@{}"),
        ("Mastodon Games", "https://mastodon.gamedev.place/@{}"),
        ("Mastodon Social Alt", "https://mastodon.social/@{}"),
    ]

    for name, url in bulk_rules:
        add(make_rule(
            name,
            url,
            not_found_strings=["page not found", "not found", "404"],
            auth_strings=["sign in", "login", "log in", "just a moment", "attention required"],
            positive_strings=["followers", "following", "posts", "projects", "activity", "about", "joined", "profile", "member since"],
        ))

    return rules


PLATFORMS: Dict[str, PlatformRule] = build_platforms()


def looks_like_generic_redirect(final_url: str, username: str) -> bool:
    username_l = username.lower()
    parsed = urlparse(final_url if "://" in final_url else "https://" + final_url)
    path = (parsed.path or "/").lower().rstrip("/") or "/"
    if username_l in final_url.lower():
        return False
    return path in GENERIC_REDIRECT_PATHS


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


def score_response(username: str, rule: PlatformRule, response: requests.Response) -> Tuple[str, str, str, int, int]:
    raw_html = response.text[:MAX_BODY_BYTES]
    body = normalize_text(raw_html)
    early_body = body[:50000]
    title_raw = extract_title(raw_html)
    title = normalize_text(title_raw)
    final_url = safe_domain_path(response.url)
    request_url = safe_domain_path(response.request.url)
    username_l = username.lower()

    positive = 0
    negative = 0
    reasons: List[str] = []

    if response.status_code in (404, 410):
        return "not_found", "hard_404_status", "high", 0, 100

    if response.status_code == 401:
        return "unconfirmed", "auth_required_status", "medium", 0, 35

    if response.status_code == 403 and rule.treat_403_as_unconfirmed:
        negative += 25
        reasons.append("restricted_403")

    if response.status_code == 429 and rule.treat_429_as_unconfirmed:
        return "unconfirmed", "rate_limited_429", "medium", 0, 35

    if 500 <= response.status_code <= 599:
        return "unconfirmed", "server_error", "low", 0, 30

    global_title_hit = contains_any(title, GLOBAL_NEGATIVE_TITLE)
    global_body_hit = contains_any(body, GLOBAL_NEGATIVE_BODY)
    global_auth_hit = contains_any(early_body, GLOBAL_AUTH_STRINGS)
    url_negative_hit = contains_any(final_url, GLOBAL_NEGATIVE_URL_MARKERS)

    site_body_negative = contains_any(body, rule.not_found_strings)
    site_title_negative = contains_any(title, rule.title_not_found_strings)
    site_auth_negative = contains_any(early_body, rule.auth_strings)

    negative_regexes = compile_patterns(rule.negative_regex)
    neg_regex_hit = regex_hit(body, negative_regexes)

    # ------------------------------------------------------------
    # HARD STOPS: site-specific negatives must win immediately
    # ------------------------------------------------------------
    # Example: "bertsec: user not found" on crates.io
    if site_title_negative:
        return "not_found", f"site_not_found_title:{site_title_negative}", "high", 0, 100

    # If the title includes both the username and a not-found marker, this is also a hard stop
    if username_l in title and (
        "user not found" in title
        or "profile not found" in title
        or "account not found" in title
        or "page not found" in title
        or "this account doesn't exist" in title
        or "this account does not exist" in title
    ):
        return "not_found", "title_username_plus_not_found", "high", 0, 100

    # Strong site body negatives should also beat generic positives
    if site_body_negative and username_l in body:
        return "not_found", f"site_not_found_body:{site_body_negative}", "high", 0, 95

    if neg_regex_hit:
        return "not_found", f"negative_regex:{neg_regex_hit}", "high", 0, 95

    # ------------------------------------------------------------
    # Continue with weighted scoring only if no hard stop matched
    # ------------------------------------------------------------
    if global_title_hit:
        negative += 35
        reasons.append(f"title_negative:{global_title_hit}")

    if global_body_hit:
        negative += 45
        reasons.append(f"body_negative:{global_body_hit}")

    if global_auth_hit:
        negative += 18
        reasons.append(f"auth_wall:{global_auth_hit}")

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

    # IMPORTANT:
    # Do NOT award username_in_title if title is negative in any way
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
    if site_positive_body and not site_body_negative:
        positive += 16
        reasons.append(f"site_positive_body:{site_positive_body}")

    site_positive_title = contains_any(title, rule.title_positive_strings)
    if site_positive_title and not site_title_negative:
        positive += 18
        reasons.append(f"site_positive_title:{site_positive_title}")

    pos_regexes = compile_patterns([
        p.replace("{u}", re.escape(username_l)) for p in rule.positive_regex
    ])
    pos_regex_hit = regex_hit(body, pos_regexes)
    if pos_regex_hit and not site_body_negative:
        positive += 24
        reasons.append(f"positive_regex:{pos_regex_hit}")

    if site_specific_positive_from_json_ld(username, raw_html):
        positive += 28
        reasons.append("jsonld_person_with_username")

    if any(x in body for x in ["followers", "following", "posts", "projects", "repositories", "member since", "joined", "about"]):
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

    if positive >= 45 and delta >= 12:
        confidence = "high" if positive >= 70 else "medium"
        return "found", "; ".join(reasons), confidence, positive, negative

    if negative >= 55 and delta <= -10:
        confidence = "high" if negative >= 85 else "medium"
        return "not_found", "; ".join(reasons), confidence, positive, negative

    if positive >= 35 and negative < 35:
        return "found", "; ".join(reasons), "medium", positive, negative

    return "unconfirmed", "; ".join(reasons) if reasons else "weak_or_conflicting_signals", "low", positive, negative

def check_platform(rule: PlatformRule, username: str, timeout: float = DEFAULT_TIMEOUT) -> ScanResult:
    url = rule.url.format(username)
    session = get_session()
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
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
            matched_rule="site_aware_soft404_engine_v2",
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

    if "hard_404_status" in note:
        return "The site returned a hard 404 or 410 response, so the account was classified as not found."

    if "site_not_found_body" in note or "site_not_found_title" in note:
        return "The page contained site-specific not-found language, which is strong evidence the account does not exist."

    if "redirected_to_generic_page" in note or "username_missing_from_final_url" in note:
        return "The username URL redirected to a generic page or dropped the username entirely, which usually indicates no profile."

    if "jsonld_person_with_username" in note and "username_in_title" in note:
        return "The page exposed structured profile metadata and matched the username in the title, which is strong evidence the profile exists."

    if "generic_shell_title" in note or "tiny_body_without_username" in note:
        return "The response looked like a generic shell page or weak wrapper page rather than a real user profile."

    if "auth_wall" in note or "site_auth" in note or "restricted_403" in note or "rate_limited_429" in note:
        return "The site presented a login wall, anti-bot control, or request restriction, so the result was left unconfirmed."

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
    # Example usage:
    username = "bertsec"
    results = scan_username(username, timeout=8.0, workers=32)
    print(json.dumps({
        "summary": results_summary(results),
        "results": results_to_dicts(results),
    }, indent=2))
