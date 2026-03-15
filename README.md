# BertSec – OSINT Username Scanner

A modern OSINT username enumeration tool and web application that scans dozens of platforms to determine whether a username exists.  
The scanner uses heuristic scoring to analyze profile pages and produces a clean, professional report with confidence ratings.

Built for investigators, security researchers, OSINT analysts, and CTF competitors.

---

## Overview

The **BertSec OSINT Username Scanner** automates the process of checking a username across many online platforms.  

Instead of relying on simple HTTP status checks alone, the scanner evaluates multiple signals from each page to estimate whether an account exists.

The results are presented in a structured report that groups findings into:

- **Found**
- **Not Found**
- **Unconfirmed**

Each result includes:

- Platform name
- Profile URL
- HTTP response status
- Confidence rating
- Positive signal score
- Negative signal score
- Human-readable explanation

---

## Features

- Scan **80+ platforms** automatically
- **Concurrent scanning** using multi-threading
- **Heuristic scoring engine** instead of fragile platform-specific rules
- **Confidence ratings** (High / Medium / Low)
- **Friendly explanations** for each result
- Clean **web report interface**
- **Professional OSINT-style report layout**
- Built-in **ethics reminder**
- Easily extendable platform list
- Optional JSON export for analysis or tuning

---

## How the Detection Engine Works

The scanner analyzes multiple indicators to determine whether a username exists on a platform.

### Positive Signals (+ Score)

Examples include:

- Username present in page title
- Username present in profile URL
- Username detected in page content
- Profile metadata or structured data
- Typical profile indicators (followers, posts, repositories, etc.)

### Negative Signals (- Score)

Examples include:

- “Page not found” language
- Missing profile indicators
- Login walls
- Access restrictions
- Anti-bot or verification pages

### Result Classification

Based on the signal balance:

| Result | Meaning |
|------|------|
| **Found** | Strong indicators that the account exists |
| **Not Found** | Strong indicators that the account does not exist |
| **Unconfirmed** | Mixed signals or restricted access |

Confidence levels indicate how strong the evidence is.

---

## Example Report Output

The web interface produces a clean report including:

- Username summary
- Statistics (Found / Not Found / Unconfirmed)
- Grouped results tables
- Direct profile links
- Friendly explanations

Example sections:
