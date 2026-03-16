import streamlit as st
from scanner import scan_username, results_summary, humanize_reason

st.set_page_config(
    page_title="OSINT Username Scanner",
    page_icon="🔎",
    layout="wide",
)

st.title("OSINT Username Scanner")
st.caption(
    "Use this tool only for authorized OSINT, defensive research, your own accounts, lawful investigations, or CTFs."
)

username = st.text_input("Enter a username to scan")

col1, col2 = st.columns([1, 4])
with col1:
    run_scan = st.button("Run Scan", use_container_width=True)

if run_scan:
    username = username.strip()

    if not username:
        st.error("Please enter a username.")
    else:
        with st.spinner(f"Scanning platforms for '{username}'..."):
            try:
                results = scan_username(username=username, timeout=6.0, workers=25)
                summary = results_summary(results)

                for r in results:
                    r.friendly_reason = humanize_reason(
                        r.note,
                        r.state,
                        r.positive_score,
                        r.negative_score,
                    )

                st.subheader(f"Results for: {username}")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Found", summary["found"])
                c2.metric("Not Found", summary["not_found"])
                c3.metric("Unconfirmed", summary["unconfirmed"])
                c4.metric("Total", summary["total"])

                st.markdown("### How to Read This Report")
                st.info(
                    "Found means the page showed enough profile-style evidence to suggest the account likely exists. "
                    "Not Found means the page showed strong signs that the account does not exist. "
                    "Unconfirmed means the site showed mixed signals, a restriction, or not enough evidence."
                )

                found_results = [r for r in results if r.state == "found"]
                not_found_results = [r for r in results if r.state == "not_found"]
                unconfirmed_results = [r for r in results if r.state == "unconfirmed"]

                def render_section(title, items):
                    st.markdown(f"## {title}")
                    if not items:
                        st.write("No results in this section.")
                        return

                    rows = []
                    for r in items:
                        rows.append({
                            "Platform": r.platform,
                            "Status": r.state.replace("_", " ").title(),
                            "HTTP": r.status_code if r.status_code is not None else "-",
                            "Confidence": r.confidence.upper(),
                            "+ Score": r.positive_score,
                            "- Score": r.negative_score,
                            "URL": r.final_url,
                            "Reason": r.friendly_reason,
                        })

                    st.dataframe(rows, use_container_width=True)

                render_section("Found Accounts", found_results)
                render_section("Not Found", not_found_results)
                render_section("Unconfirmed / Restricted", unconfirmed_results)

            except Exception as e:
                st.error(f"Scan failed: {e}")
