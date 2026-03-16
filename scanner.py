from __future__ import annotations

import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

# --- CONFIGURATION & TARGETS ---

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
}

# Integrated all platforms with optimized Reddit/ArtStation targets
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

NEGATIVE_BODY_STRONG = [
    "page not found", "not found", "404", "missing page", "error", 
    "nobody on reddit goes by that name", "user not found", 
    "could not find the page", "doesn't exist", "doesn’t exist",
    "profile not found", "account not found", "this account is private"
]

AUTH_WALL_MARKERS = [
    "sign in", "login", "log in", "sign up", "join now", "recaptcha", 
    "verify you are human", "attention required", "checking your browser"
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
    positive_score: int = 0
    negative_score: int = 0
    friendly_reason: str = ""

# --- HELPERS FOR STREAMLIT ---

def results_summary(results: List[ScanResult]) -> Dict[str, int]:
    return {
        "found": sum(1 for r in results if r.state == "found"),
        "not_found": sum(1 for r in results if r.state == "not_found"),
        "unconfirmed": sum(1 for r in results if r.state == "unconfirmed"),
        "total": len(results)
    }

def humanize_reason(note: str, state: str, pos: int, neg: int) -> str:
    if state == "found":
        return f"Confirmed profile signals (Score: {pos})"
    if state == "not_found":
        return f"Platform confirmed user does not exist (Score: {neg})"
    if "403" in note or "Access" in note:
        return "Access restricted by site (anti-bot or login wall)"
    return note if note else "Insufficient evidence"

def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

# --- ENGINE ---

def score_response(username: str, response: requests.Response) -> tuple[str, str, str, int, int]:
    raw_html = response.text[:300000]
    body = raw_html.lower()
    title = extract_title(raw_html).lower()
    final_url = response.url.lower()
    uname_l = username.lower()
    
    # 1. SPECIAL REDDIT JSON
    if "reddit.com" in final_url and ".json" in final_url:
        if response.status_code == 404 or '"error": 404' in raw_html:
            return "not_found", "Reddit confirmed missing", "high", 0, 100
        if '"kind": "t2"' in raw_html:
            return "found", "Reddit account verified", "high", 100, 0

    # 2. HARD NEGATIVE
    if response.status_code in (404, 410):
        return "not_found", "HTTP 404", "high", 0, 100

    # 3. SOFT NEGATIVE (ArtStation Fix)
    for marker in NEGATIVE_BODY_STRONG:
        if marker in body or marker in title:
            return "not_found", f"Marker found: {marker}", "high", 0, 100

    # 4. AUTH WALL
    if response.status_code in (401, 403, 429):
        return "unconfirmed", f"Blocked (HTTP {response.status_code})", "low", 0, 50
    for marker in AUTH_WALL_MARKERS:
        if marker in title:
            return "unconfirmed", "Login wall detected", "low", 0, 50

    # 5. POSITIVE
    pos = 0
    if uname_l in title: pos += 55
    if uname_l in final_url: pos += 25
    signals = ["followers", "following", "repositories", "joined", "bio", "posts"]
    pos += sum(10 for s in signals if s in body)

    if pos >= 65:
        return "found", "Strong match", "high", pos, 0
    return "unconfirmed", "Limited evidence", "low", pos, 0

def check_platform(platform: str, username: str, timeout: float = 8.0) -> ScanResult:
    url = PLATFORMS[platform].format(username)
    try:
        res = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        state, note, conf, pos, neg = score_response(username, res)
        return ScanResult(
            platform=platform, url=url.replace(".json",""), final_url=res.url,
            state=state, status_code=res.status_code, confidence=conf, 
            note=note, title=extract_title(res.text[:5000]),
            positive_score=pos, negative_score=neg
        )
    except Exception as e:
        return ScanResult(platform, url, url, "unconfirmed", None, "low", str(e))

def scan_username(username: str, timeout: float = 8.0, workers: int = 30) -> List[ScanResult]:
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_platform, p, username, timeout): p for p in PLATFORMS}
        for f in as_completed(futures):
            results.append(f.result())
    
    order = {"found": 0, "unconfirmed": 1, "not_found": 2}
    results.sort(key=lambda x: (order.get(x.state, 3), x.platform))
    return results
