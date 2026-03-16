from __future__ import annotations
from curl_cffi import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

PLATFORMS: Dict[str, str] = {
    "Twitch": "https://www.twitch.tv/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "GitHub": "https://github.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "TikTok": "https://www.tiktok.com/@{}",
}

# Negative markers must be very specific to avoid false negatives
NEGATIVE_MARKERS = [
    "nobody on reddit goes by that name", 
    "this account has been suspended",
    "404 not found"
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

def score_response(platform: str, username: str, html: str, status_code: int, final_url: str) -> tuple[str, str, str, int, int]:
    body = html.lower()
    uname_l = username.lower()
    
    # 1. Platform-Specific "Fingerprints" for Positive Matches
    pos = 0
    
    # Twitch: Look for unique 'channelID' or 'streamer' keywords in the JS
    if platform == "Twitch":
        if any(x in body for x in ["channelid", "isavailable", 'login":"' + uname_l]):
            pos += 90
            
    # YouTube: Look for the specific @handle in the metadata
    if platform == "YouTube":
        if f"youtube.com/@{uname_l}" in body or "channelid" in body:
            pos += 90

    # Reddit: Look for 'karma' or 'cake day'
    if platform == "Reddit":
        if any(x in body for x in ["karma", "cake day", "comment-karma"]):
            pos += 90

    # General Fallbacks
    if uname_l in body: pos += 20
    if uname_l in final_url: pos += 20

    # 2. Re-evaluating 403s
    # If we get a 403 but the username is in the HTML, it's a "Found" account behind a bot-block
    if status_code == 403 and pos > 40:
        return "found", "Profile detected despite bot-block (403)", "medium", pos, 0

    # 3. Hard Negatives
    if status_code == 404:
        # Check if it's a 'Fake' 404 (Twitch does this sometimes)
        if pos > 70: return "found", "Confirmed via Metadata", "high", pos, 0
        return "not_found", "HTTP 404", "high", 0, 100

    for marker in NEGATIVE_MARKERS:
        if marker in body:
            return "not_found", f"Confirmed: {marker}", "high", 0, 100

    if pos >= 60:
        return "found", "Matches found", "high", pos, 0
        
    return "unconfirmed", "Ambiguous signals", "low", pos, 0

def check_platform(platform: str, username: str, timeout: float = 12.0) -> ScanResult:
    url = PLATFORMS[platform].format(username)
    try:
        # We rotate the impersonation target to see if it helps
        target = "chrome110" if platform != "Twitch" else "safari_ios"
        
        response = requests.get(
            url, 
            impersonate=target, 
            timeout=timeout, 
            allow_redirects=True,
            headers={"Referer": "https://www.google.com/"} # Adding a referer helps
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
        return ScanResult(platform, url, url, "unconfirmed", None, "low", f"Error: {str(e)}")

def scan_username(username: str, timeout: float = 12.0, workers: int = 20) -> List[ScanResult]:
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_platform, p, username, timeout): p for p in PLATFORMS}
        for f in as_completed(futures):
            results.append(f.result())
    
    order = {"found": 0, "unconfirmed": 1, "not_found": 2}
    results.sort(key=lambda x: (order.get(x.state, 3), x.platform))
    return results

def results_summary(results: List[ScanResult]) -> Dict[str, int]:
    return {
        "found": sum(1 for r in results if r.state == "found"),
        "not_found": sum(1 for r in results if r.state == "not_found"),
        "unconfirmed": sum(1 for r in results if r.state == "unconfirmed"),
        "total": len(results)
    }

def humanize_reason(note: str, state: str, pos: int, neg: int) -> str:
    if state == "found": return f"Presence confirmed (Score: {pos})"
    if state == "not_found": return "Account definitely not found."
    return note if note else "Checking platform constraints..."
