# OSINT Username Scanner

A modern OSINT username enumeration tool and web application that scans dozens of platforms to determine whether a username exists.  
The scanner uses heuristic scoring to analyze profile pages and produces a clean, professional report with confidence ratings.

Built for investigators, security researchers, OSINT analysts, and CTF competitors.

---

## Live Web App

You can access the hosted scanner here:

**https://usernamescanner.streamlit.app/**

Simply enter a username and the scanner will check dozens of platforms and generate a structured OSINT report.

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