from __future__ import annotations
import re
# Switch to curl_cffi to bypass TLS fingerprinting blocks on Reddit/Instagram/Twitch
from curl_cffi import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

# --- CONFIGURATION ---

PLATFORMS: Dict[str, str] = {
    "GitHub": "https://github.com/{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "TikTok": "https://www.tiktok.com/@{}",
    "ArtStation": "https://www.artstation.com/{}",
    # ... keep your other 180+ platforms here
}

NEGATIVE_MARKERS = [
    "page not found", "404", "user not found", "doesn't exist",
    "nobody on reddit goes by that name", "profile not found",
    "this account is private", "this account has been suspended"
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

# --- STREAMLIT HELPERS ---

def results_summary(results: List[ScanResult]) -> Dict[str, int]:
    return {
        "found": sum(1 for r in results if r.state == "found"),
        "not_found": sum(1 for r in results if r.state == "not_found"),
        "unconfirmed": sum(1 for r in results if r.state == "unconfirmed"),
        "total": len(results)
    }

def humanize_reason(note: str, state: str, pos: int, neg: int) -> str:
    if state == "found": return f"Presence confirmed via metadata (Score: {pos})"
    if state == "not_found": return "Platform confirmed account does not exist."
    return note if note else "Platform restricted access or insufficient data."

# --- ENGINE ---

def score_response(platform: str, username: str, html: str, status_code: int, final_url: str) -> tuple[str, str, str, int, int]:
    body = html.lower()
    uname_l = username.lower()
    pos, neg = 0, 0
    
    # 1. Platform-Specific Fingerprinting (Bypasses generic blocks)
    if platform == "GitHub" and (f'"{username}"' in body or "contributions" in body):
        pos += 90
    if platform == "Twitch" and ("channelid" in body or 'login":"' + uname_l in body):
        pos += 90
    if platform == "YouTube" and (f"@{uname_l}" in body or "channelid" in body):
        pos += 90
    if platform == "Reddit" and ("karma" in body or "cake day" in body):
        pos += 90
    if platform == "TikTok" and ("webapp.user-detail" in body or f'uniqueid":"{uname_l}"' in body):
        pos += 90

    # 2. Hard Status Checks
    if status_code == 404:
        return "not_found", "HTTP 404", "high", 0, 100
    
    # If we found metadata signals but got a 403/429, it's still a "Found"
    if status_code in (401, 403, 429) and pos > 50:
        return "found", f"Detected via metadata despite HTTP {status_code}", "medium", pos, 0

    # 3. Negative Markers (Soft 404s)
    for marker in NEGATIVE_MARKERS:
        if marker in body:
            return "not_found", f"Confirmed missing: {marker}", "high", 0, 100

    # 4. General Scoring
    if uname_l in body: pos += 30
    if uname_l in final_url: pos += 20

    if pos >= 60:
        return "found", "Positive match", "high", pos, 0
    if status_code in (403, 429):
        return "unconfirmed", f"Access Restricted ({status_code})", "low", 0, 50
        
    return "unconfirmed", "Insufficient signals", "low", pos, 0

def check_platform(platform: str, username: str, timeout: float = 10.0) -> ScanResult:
    url = PLATFORMS[platform].format(username)
    try:
        # Using impersonate="chrome110" makes the script look like a real browser
        response = requests.get(
            url, 
            impersonate="chrome110", 
            timeout=timeout, 
            allow_redirects=True,
            headers={"Referer": "https://www.google.com/"}
        )
        
        state, note, conf, pos, neg = score_response(
            platform, username, response.text, response.status_code, response.url
        )
        
        return ScanResult(
            platform=platform, url=url, final_url=response.url,
            state=state, status_code=response.status_code, confidence=conf, 
            note=note, positive_score=pos, negative_score=neg
        )
    except Exception as e:
        return ScanResult(platform, url, url, "unconfirmed", None, "low", str(e))

def scan_username(username: str, timeout: float = 10.0, workers: int = 25) -> List[ScanResult]:
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_platform, p, username, timeout): p for p in PLATFORMS}
        for f in as_completed(futures):
            results.append(f.result())
    
    order = {"found": 0, "unconfirmed": 1, "not_found": 2}
    results.sort(key=lambda x: (order.get(x.state, 3), x.platform))
    return results
