from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Pattern
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
}

PLATFORMS: Dict[str, str] = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "Bitbucket": "https://bitbucket.org/{}",
    "Codeberg": "https://codeberg.org/{}",
    "SourceHut": "https://git.sr.ht/~{}",
    "Gitea": "https://gitea.com/{}",
    "Forgejo": "https://codeberg.org/{}",
    "Launchpad": "https://launchpad.net/~{}",
    "Hugging Face": "https://huggingface.co/{}",
    "Replit": "https://replit.com/@{}",
    "CodePen": "https://codepen.io/{}",
    "JSFiddle": "https://jsfiddle.net/user/{}/",
    "StackBlitz": "https://stackblitz.com/@{}",
    "Glitch": "https://glitch.com/@{}",
    "Observable": "https://observablehq.com/@{}",
    "Kaggle": "https://www.kaggle.com/{}",
    "PyPI": "https://pypi.org/user/{}",
    "npm": "https://www.npmjs.com/~{}",
    "Docker Hub": "https://hub.docker.com/u/{}",
    "Crates.io": "https://crates.io/users/{}",
    "RubyGems": "https://rubygems.org/profiles/{}",
    "Packagist": "https://packagist.org/users/{}",
    "CPAN": "https://metacpan.org/author/{}",
    "Dev.to": "https://dev.to/{}",
    "Hashnode": "https://{}.hashnode.dev",
    "Medium": "https://medium.com/@{}",
    "Substack": "https://{}.substack.com",
    "Blogger": "https://{}.blogspot.com",
    "WordPress": "https://{}.wordpress.com",
    "Ghost": "https://{}.ghost.io",
    "Wix": "https://{}.wixsite.com",
    "About.me": "https://about.me/{}",
    "Linktree": "https://linktr.ee/{}",
    "Carrd": "https://{}.carrd.co",
    "Ko-fi": "https://ko-fi.com/{}",
    "Buy Me a Coffee": "https://www.buymeacoffee.com/{}",
    "Patreon": "https://www.patreon.com/{}",
    "Gumroad": "https://{}.gumroad.com",
    "Product Hunt": "https://www.producthunt.com/@{}",
    "Indie Hackers": "https://www.indiehackers.com/{}",
    "AngelList Legacy": "https://angel.co/u/{}",
    "Wellfound": "https://wellfound.com/u/{}",
    "Crunchbase People": "https://www.crunchbase.com/person/{}",
    "Freelancer": "https://www.freelancer.com/u/{}",
    "Fiverr": "https://www.fiverr.com/{}",
    "Upwork": "https://www.upwork.com/freelancers/~{}",
    "99designs": "https://99designs.com/profiles/{}",
    "Envato": "https://elements.envato.com/user/{}",
    "Codecanyon": "https://codecanyon.net/user/{}",
    "ThemeForest": "https://themeforest.net/user/{}",
    "Behance": "https://www.behance.net/{}",
    "Dribbble": "https://dribbble.com/{}",
    "DeviantArt": "https://www.deviantart.com/{}",
    "ArtStation": "https://www.artstation.com/{}",
    "Pixiv": "https://www.pixiv.net/en/users/{}",
    "500px": "https://500px.com/p/{}",
    "Flickr": "https://www.flickr.com/people/{}",
    "VSCO": "https://vsco.co/{}/gallery",
    "Unsplash": "https://unsplash.com/@{}",
    "Pexels": "https://www.pexels.com/@{}/",
    "Canva": "https://www.canva.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Threads": "https://www.threads.net/@{}",
    "X": "https://x.com/{}",
    "Facebook": "https://www.facebook.com/{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "Snapchat": "https://www.snapchat.com/add/{}",
    "Pinterest": "https://www.pinterest.com/{}/",
    "Reddit": "https://www.reddit.com/user/{}",
    "Tumblr": "https://{}.tumblr.com",
    "Mastodon Social": "https://mastodon.social/@{}",
    "Mastodon Online": "https://mastodon.online/@{}",
    "Pixelfed Social": "https://pixelfed.social/{}",
    "VK": "https://vk.com/{}",
    "OK": "https://ok.ru/{}",
    "Weibo": "https://www.weibo.com/{}",
    "Naver Blog": "https://blog.naver.com/{}",
    "Quora": "https://www.quora.com/profile/{}",
    "Bluesky": "https://bsky.app/profile/{}",
    "Discord Invite Vanity": "https://discord.com/users/{}",
    "Telegram": "https://t.me/{}",
    "Keybase": "https://keybase.io/{}",
    "Disqus": "https://disqus.com/by/{}/",
    "Gravatar": "https://gravatar.com/{}",
    "Hacker News": "https://news.ycombinator.com/user?id={}",
    "Lobsters": "https://lobste.rs/u/{}",
    "Stack Overflow": "https://stackoverflow.com/users/{}",
    "Stack Exchange": "https://stackexchange.com/users/{}",
    "Super User": "https://superuser.com/users/{}",
    "Server Fault": "https://serverfault.com/users/{}",
    "Ask Ubuntu": "https://askubuntu.com/users/{}",
    "LeetCode": "https://leetcode.com/{}",
    "HackerRank": "https://www.hackerrank.com/{}",
    "Codewars": "https://www.codewars.com/users/{}",
    "CodeChef": "https://www.codechef.com/users/{}",
    "AtCoder": "https://atcoder.jp/users/{}",
    "Topcoder": "https://www.topcoder.com/members/{}",
    "Exercism": "https://exercism.org/profiles/{}",
    "FreeCodeCamp": "https://www.freecodecamp.org/{}",
    "GeeksforGeeks": "https://auth.geeksforgeeks.org/user/{}/",
    "TryHackMe": "https://tryhackme.com/p/{}",
    "Hack The Box": "https://app.hackthebox.com/profile/{}",
    "Root Me": "https://www.root-me.org/{}",
    "CTFtime Team/User": "https://ctftime.org/team/{}",
    "Hackaday": "https://hackaday.io/{}",
    "Instructables": "https://www.instructables.com/member/{}/",
    "Roblox": "https://www.roblox.com/users/profile?username={}",
    "Steam": "https://steamcommunity.com/id/{}",
    "Xbox Gamertag": "https://xboxgamertag.com/search/{}",
    "PlayStation Profiles": "https://psnprofiles.com/{}",
    "Nintendo Life": "https://www.nintendolife.com/users/{}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Lichess": "https://lichess.org/@/{}",
    "Speedrun.com": "https://www.speedrun.com/user/{}",
    "Twitch": "https://www.twitch.tv/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Vimeo": "https://vimeo.com/{}",
    "Dailymotion": "https://www.dailymotion.com/{}",
    "SoundCloud": "https://soundcloud.com/{}",
    "Bandcamp": "https://{}.bandcamp.com",
    "Last.fm": "https://www.last.fm/user/{}",
    "Mixcloud": "https://www.mixcloud.com/{}",
    "Spotify User": "https://open.spotify.com/user/{}",
    "Deezer": "https://www.deezer.com/us/profile/{}",
    "Genius": "https://genius.com/{}",
    "IMDb": "https://www.imdb.com/user/{}",
    "Letterboxd": "https://letterboxd.com/{}/",
    "Goodreads": "https://www.goodreads.com/{}",
    "StoryGraph": "https://app.thestorygraph.com/profile/{}",
    "Wattpad": "https://www.wattpad.com/user/{}",
    "Archive of Our Own": "https://archiveofourown.org/users/{}",
    "FanFiction": "https://www.fanfiction.net/u/{}",
    "Tripadvisor": "https://tripadvisor.com/members/{}",
    "Tripadvisor Profile": "https://www.tripadvisor.com/Profile/{}",
    "AllTrails": "https://www.alltrails.com/members/{}",
    "Strava": "https://www.strava.com/athletes/{}",
    "Garmin Connect": "https://connect.garmin.com/modern/profile/{}",
    "Runkeeper": "https://runkeeper.com/user/{}",
    "Untappd": "https://untappd.com/user/{}",
    "Vivino": "https://www.vivino.com/users/{}",
    "Couchsurfing": "https://www.couchsurfing.com/people/{}",
    "TripIt": "https://www.tripit.com/people/{}",
    "Airbnb User": "https://www.airbnb.com/users/show/{}",
    "Venmo": "https://venmo.com/{}",
    "Cash App": "https://cash.app/${}",
    "PayPal.me": "https://paypal.me/{}",
    "Etsy": "https://www.etsy.com/people/{}",
    "Poshmark": "https://poshmark.com/closet/{}",
    "Depop": "https://www.depop.com/{}",
    "Mercari": "https://www.mercari.com/u/{}/",
    "eBay": "https://www.ebay.com/usr/{}",
    "Amazon Wishlist": "https://www.amazon.com/hz/wishlist/ls/{}",
    "Rakuten Viki": "https://www.viki.com/users/{}/about",
    "MyAnimeList": "https://myanimelist.net/profile/{}",
    "AniList": "https://anilist.co/user/{}",
    "Trakt": "https://trakt.tv/users/{}",
    "RAWG": "https://rawg.io/@{}",
    "Pastebin": "https://pastebin.com/u/{}",
    "Paste.ee": "https://paste.ee/u/{}",
    "IFTTT": "https://ifttt.com/p/{}",
    "Trello": "https://trello.com/{}",
    "Notion Site": "https://{}.notion.site",
    "Miro": "https://miro.com/app/board/{}",
    "Figma Community": "https://www.figma.com/@{}",
    "Sketchfab": "https://sketchfab.com/{}",
    "Polywork": "https://www.polywork.com/{}",
    "Peerlist": "https://peerlist.io/{}",
    "ResearchGate": "https://www.researchgate.net/profile/{}",
    "ORCID": "https://orcid.org/{}",
    "Academia": "https://independent.academia.edu/{}",
    "Google Scholar": "https://scholar.google.com/citations?user={}",
    "OpenSea": "https://opensea.io/{}",
    "Giters": "https://giters.com/{}",
    "LibraryThing": "https://www.librarything.com/profile/{}",
    "Houzz": "https://www.houzz.com/user/{}",
    "Ello": "https://ello.co/{}",
    "BuySellAds": "https://www.buysellads.com/{}",
    "SlideShare": "https://www.slideshare.net/{}",
    "Scribd": "https://www.scribd.com/{}",
    "Issuu": "https://issuu.com/{}",
    "Devpost": "https://devpost.com/{}",
    "Kofi Shop": "https://ko-fi.com/{}",
    "Battle.net": "https://worldofwarcraft.blizzard.com/en-us/search?q={}",
    "NameMC": "https://namemc.com/profile/{}",
    "NationStates": "https://www.nationstates.net/nation={}",
    "ReverbNation": "https://www.reverbnation.com/{}",
    "Smule": "https://www.smule.com/{}",
    "Polarsteps": "https://www.polarsteps.com/{}",
    "Codecademy": "https://www.codecademy.com/profiles/{}",
    "Erome": "https://www.erome.com/{}",
    "Flipboard": "https://flipboard.com/@{}",
    "DailyMotion Legacy": "https://www.dailymotion.com/{}",
    "Bento": "https://bento.me/{}",
    "Pearltrees": "https://www.pearltrees.com/{}",
    "Shutterstock": "https://www.shutterstock.com/g/{}",
    "EyeEm": "https://www.eyeem.com/u/{}",
    "Civitai": "https://civitai.com/user/{}",
    "Muck Rack": "https://muckrack.com/{}",
    "Giphy": "https://giphy.com/{}",
    "Thingiverse": "https://www.thingiverse.com/{}/designs",
    "Printables": "https://www.printables.com/@{}",
    "Myspace": "https://myspace.com/{}",
}


NEGATIVE_TITLE_MARKERS = [
    "page not found",
    "not found",
    "404",
    "missing page",
    "error",
    "private site",
    "just a moment",
    "attention required",
    "something went wrong",
    "oops",
]

NEGATIVE_BODY_STRONG = [
    "this page is no longer available",
    "we can't find that page",
    "we couldnt find that page",
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
    "the page you requested could not be found",
    "this page does not exist",
    "the page you are looking for doesn't exist",
    "the page you are looking for doesn’t exist",
]

NEGATIVE_URL_MARKERS = [
    "/404",
    "/404/",
    "/not-found",
    "/not_found",
    "/error",
    "/errors/404",
    "/missing",
]

AUTH_WALL_MARKERS = [
    "sign in",
    "login",
    "log in",
    "sign up",
    "join now",
    "checking your browser",
    "just a moment",
    "attention required",
    "verify you are human",
    "recaptcha",
    "captcha",
    "access denied",
]

GENERIC_SHELL_TITLES = {
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
    "programming problems and competitions :: hackerrank",
    "tryhackme | cyber security training",
}


@dataclass
class PlatformRule:
    name: str
    url_template: str
    profile_url_regex: Optional[str] = None
    explicit_not_found_body: List[str] = field(default_factory=list)
    explicit_not_found_title: List[str] = field(default_factory=list)
    explicit_auth_body: List[str] = field(default_factory=list)
    required_positive_body: List[str] = field(default_factory=list)
    required_positive_meta: List[str] = field(default_factory=list)
    forbidden_generic_titles: List[str] = field(default_factory=list)
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


def normalize_text(text: str) -> str:
    text = text or ""
    text = unquote(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def compile_word_boundary_username(username: str) -> Pattern[str]:
    return re.compile(rf"(?<![a-z0-9_]){re.escape(username.lower())}(?![a-z0-9_])", re.IGNORECASE)


def contains_any(text: str, needles: List[str]) -> Optional[str]:
    text_l = normalize_text(text)
    for needle in needles:
        if normalize_text(needle) in text_l:
            return needle
    return None


def path_contains_username(final_url: str, username: str) -> bool:
    parsed = urlparse(final_url)
    path = normalize_text(parsed.path)
    username_l = username.lower()
    return f"/{username_l}" in path or path.endswith(f"@{username_l}") or path.endswith(f"~{username_l}")


def looks_like_generic_redirect(final_url: str, username: str) -> bool:
    parsed = urlparse(final_url)
    path = (parsed.path or "/").strip("/").lower()
    username_l = username.lower()

    if username_l in parsed.path.lower():
        return False

    generic_paths = {
        "",
        "/",
        "home",
        "discover",
        "explore",
        "feed",
        "login",
        "signin",
        "signup",
        "join",
        "404",
        "error",
        "not-found",
        "search",
        "users",
    }
    return path in generic_paths


_thread_local = threading.local()


def build_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _thread_local.session = session
    return session


def default_rule_map(platforms: Dict[str, str]) -> Dict[str, PlatformRule]:
    rules: Dict[str, PlatformRule] = {}
    for name, url_template in platforms.items():
        rules[name] = PlatformRule(name=name, url_template=url_template)

    # Site-specific hardening
    if "Crates.io" in rules:
        rules["Crates.io"] = PlatformRule(
            name="Crates.io",
            url_template=platforms["Crates.io"],
            profile_url_regex=r"^https://crates\.io/users/[A-Za-z0-9_-]+/?$",
            explicit_not_found_body=[
                "user not found",
                "this user does not exist",
                "could not find that user",
            ],
            explicit_not_found_title=[
                "user not found",
                "not found",
            ],
            required_positive_body=[
                "crates",
                "downloads",
            ],
            required_positive_meta=[
                '"@type":"person"',
                '"alternateName"',
            ],
        )

    if "GitHub" in rules:
        rules["GitHub"] = PlatformRule(
            name="GitHub",
            url_template=platforms["GitHub"],
            profile_url_regex=r"^https://github\.com/[A-Za-z0-9-]+/?$",
            explicit_not_found_body=[
                "not found",
                "there isn’t a github pages site here",
            ],
            required_positive_body=[
                "followers",
                "following",
                "repositories",
                "contributions",
            ],
            required_positive_meta=[
                'octolytics-dimension-user_login',
                'og:type" content="profile',
            ],
        )

    if "Reddit" in rules:
        rules["Reddit"] = PlatformRule(
            name="Reddit",
            url_template=platforms["Reddit"],
            profile_url_regex=r"^https://(www\.)?reddit\.com/user/[A-Za-z0-9_-]+/?$",
            explicit_not_found_body=[
                "nobody on reddit goes by that name",
                "page not found",
            ],
            required_positive_body=[
                "post karma",
                "comment karma",
                "cake day",
            ],
        )

    if "PyPI" in rules:
        rules["PyPI"] = PlatformRule(
            name="PyPI",
            url_template=platforms["PyPI"],
            profile_url_regex=r"^https://pypi\.org/user/[A-Za-z0-9._-]+/?$",
            explicit_not_found_body=[
                "user not found",
                "404 not found",
                "page not found",
            ],
            required_positive_body=[
                "projects",
            ],
        )

    return rules


def classify_response(rule: PlatformRule, username: str, response: requests.Response) -> tuple[str, str, str, int, int]:
    raw_html = response.text[:250000]
    body = normalize_text
