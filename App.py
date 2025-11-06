# app.py
import streamlit as st
import pandas as pd
import requests
import tldextract
from urllib.parse import urlparse
import io
import base64
from typing import List, Dict
from collections import Counter
import matplotlib.pyplot as plt

st.set_page_config(page_title="Assistant vs Search Visibility", layout="wide")

# -------------------------
# Utilities
# -------------------------
def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            ext = tldextract.extract(url)
            if ext.domain:
                return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
            return parsed.netloc
        # fallback
        return url
    except Exception:
        return url

def parse_pasted_assistant_input(text: str) -> Dict[str, List[str]]:
    """
    Expecting input in the format:
    query 1 <TAB or ::> url1, url2, url3
    OR
    one query per block separated by newlines: first line query, second line comma separated urls...
    We'll accept flexible formats. Returns a mapping query -> [urls]
    """
    mapping = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        # If line contains a separator between query and urls
        if "::" in line or "\t" in line or "|" in line:
            sep = "::" if "::" in line else ("\t" if "\t" in line else "|")
            parts = [p.strip() for p in line.split(sep, 1)]
            q = parts[0]
            urls = [u.strip() for u in parts[1].split(",") if u.strip()]
            mapping[q] = urls
            i += 1
            continue
        # If next line looks like a list of urls, treat current as query
        if i + 1 < len(lines) and ("," in lines[i+1] or "http" in lines[i+1]):
            q = line
            urls = [u.strip() for u in lines[i+1].split(",") if u.strip()]
            mapping[q] = urls
            i += 2
            continue
        # Single-line: query followed by urls on same line separated by " - " or " : "
        if " - " in line or " : " in line:
            sep = " - " if " - " in line else " : "
            parts = [p.strip() for p in line.split(sep, 1)]
            q = parts[0]
            urls = [u.strip() for u in parts[1].split(",") if u.strip()]
            mapping[q] = urls
            i += 1
            continue
        # Otherwise treat as query with no citations
        mapping[line] = []
        i += 1
    return mapping

def serpapi_search_top10(query: str, serpapi_key: str) -> List[str]:
    """
    Uses SerpAPI Google Search JSON. Expects SERPAPI API key.
    Returns top 10 organic result URLs.
    """
    params = {
        "engine": "google",
        "q": query,
        "api_key": serpapi_key,
        "num": 10,
    }
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"SerpAPI error: {resp.status_code} {resp.text}")
    data = resp.json()
    urls = []
    # organic_results may exist
    for item in data.get("organic_results", [])[:10]:
        link = item.get("link") or item.get("url")
        if link:
            urls.append(link)
    # fallback: serpapi sometimes returns 'top_results' or 'inline'
    if not urls:
        for block in data.get("top_results", []):
            link = block.get("link")
            if link:
                urls.append(link)
    return urls[:10]

def make_download_link(df: pd.DataFrame, filename: str):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV</a>'
    return href

# -------------------------
# Metric logic
# -------------------------
def compute_metrics_for_query(google_top10: List[str], assistant_citations: List[str]):
    # domain-level or URL-level comparison? We'll compute both; primary uses URL intersection as article suggests.
    google_set = set([u.strip() for u in google_top10 if u])
    assistant_set = set([u.strip() for u in assistant_citations if u])

    I = len(google_set & assistant_set)  # intersection count (URL-level)
    total_assistant = len(assistant_citations)
    N = max(0, total_assistant - I) if total_assistant > 0 else 0

    # frequency will be handled at domain aggregation stage
    return {"I": I, "N": N, "assistant_count": total_assistant, "google_count": len(google_top10)}

# -------------------------
# Streamlit UI
# -------------------------
st.title("Assistant vs Search Visibility — Minimalist Tool")
st.markdown("Compute overlap between Google Top 10 and assistant citations. Paste queries, optionally fetch Google via SerpAPI, or paste Google results manually. Paste or upload assistant citation lists per query.")

with st.sidebar:
    st.header("Modes & Inputs")
    mode = st.radio("Input mode (choose one)", ["Manual all", "Auto Google (SerpAPI) + Manual assistant", "CSV Upload"], index=0)
    serpapi_key = st.text_input("SerpAPI Key (optional; required for Auto Google mode)", type="password")
    st.markdown("SerpAPI is optional. If you don't have a key, use Manual mode and paste Google results.")

    show_domains = st.checkbox("Also show domain-level metrics", value=True)
    export_name = st.text_input("Export filename", value="visibility_report.csv")

# Main inputs
queries_text = st.text_area("Enter queries (one per line)", height=160)
if mode == "CSV Upload":
    uploaded = st.file_uploader("Upload CSV: must have columns 'query','google_urls','assistant_urls' (urls comma-separated)", type=["csv"])
else:
    uploaded = None

assistant_input = st.text_area("Assistant citations input (format examples below)", height=200,
    help=("Format examples:\n"
          "1) query :: url1, url2, url3\n"
          "2) Query on one line, next line comma-separated urls\n"
          "3) query | url1, url2\n"
          "If assistant produced no citations for a query, omit or leave empty list."))

run_button = st.button("Run analysis")

st.markdown("---")
st.markdown("Output")

if run_button:
    # Build query list
    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]
    if uploaded:
        try:
            df_in = pd.read_csv(uploaded)
            # Expect columns: query, google_urls, assistant_urls (comma separated)
            queries = df_in['query'].astype(str).tolist()
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")
            st.stop()

    # Parse assistant mapping
    assistant_map = parse_pasted_assistant_input(assistant_input) if assistant_input.strip() else {}

    results_rows = []
    domain_counter = Counter()
    domain_per_query = {}

    # loop queries
    for q in queries:
        # Get Google top10
        google_urls = []
        if mode == "Auto Google (SerpAPI) + Manual assistant":
            if not serpapi_key:
                st.error("SerpAPI key required for Auto Google mode.")
                st.stop()
            try:
                google_urls = serpapi_search_top10(q, serpapi_key)
            except Exception as e:
                st.error(f"Error fetching Google results for '{q}': {e}")
                google_urls = []
        elif uploaded:
            # get from CSV row
            row = df_in[df_in['query'].astype(str) == q]
            if not row.empty:
                raw_g = str(row.iloc[0].get('google_urls', "") or "")
                google_urls = [u.strip() for u in raw_g.split(",") if u.strip()]
        else:
            # Manual mode: assume user didn't paste Google results; offer empty list or require user to paste Google results per query in assistant_input (same format)
            # We'll attempt to find google results in assistant_input mapping if provided
            # Alternatively, user may paste google results in assistant_input using special prefix "google::"
            # Search assistant_map for entries where key startswith "google::"
            google_key = f"google::{q}"
            google_urls = assistant_map.get(google_key, [])
            # Also allow user to paste a block like "q - google: url1, url2" but not required
            # If no google data provided, leave empty and continue
        # Get assistant citations
        assistant_urls = assistant_map.get(q, [])
        # Also accept assistant map keys that are lowercased version
        if not assistant_urls and q.lower() in assistant_map:
            assistant_urls = assistant_map[q.lower()]

        metrics = compute_metrics_for_query(google_urls, assistant_urls)
        # domain counters
        domains = [extract_domain(u) for u in assistant_urls if u]
        for d in domains:
            if d:
                domain_counter[d] += 1
        domain_per_query[q] = domains

        row = {
            "query": q,
            "google_top10_count": len(google_urls),
            "assistant_citation_count": metrics["assistant_count"],
            "I": metrics["I"],
            "N": metrics["N"],
            "SVR": round(metrics["I"] / 10.0 if metrics["google_count"] else 0.0, 3),
            "UAVR": round((metrics["N"] / metrics["assistant_count"]) if metrics["assistant_count"] else 0.0, 3),
        }
        results_rows.append(row)

    results_df = pd.DataFrame(results_rows)

    # RCC calculation: for each domain, RCC = occurrences / number of queries
    num_queries = len(queries) if queries else 1
    rcc = {d: round(cnt / num_queries, 3) for d, cnt in domain_counter.items()}
    rcc_df = pd.DataFrame([{"domain": d, "count": cnt, "RCC": rcc[d]} for d, cnt in domain_counter.items()]).sort_values("RCC", ascending=False)

    st.subheader("Per-query metrics")
    st.dataframe(results_df, use_container_width=True)

    st.markdown(make_download_link(results_df, export_name), unsafe_allow_html=True)

    st.subheader("Aggregate domain repeat citation counts (RCC)")
    if not rcc_df.empty:
        st.dataframe(rcc_df.head(50), use_container_width=True)
    else:
        st.write("No assistant citation domains detected from inputs.")

    # Quick interpretation guidance (minimal)
    st.subheader("Quick interpretation")
    st.markdown(
        "- SVR = Shared Visibility Rate = I ÷ 10 (how much of Google top 10 also cited by assistant).\n"
        "- UAVR = Unique Assistant Visibility Rate = N ÷ total assistant citations (how much new material assistant introduces).\n"
        "- RCC = Repeat Citation Count per domain = times domain appears ÷ number of queries."
    )

    # Plot SVR distribution
    fig, ax = plt.subplots()
    ax.hist(results_df['SVR'].fillna(0), bins=10)
    ax.set_xlabel("SVR")
    ax.set_ylabel("Number of queries")
    st.pyplot(fig)

    # Offer CSV with full details including domain-level breakdown
    expanded_rows = []
    for q in queries:
        google_urls = []
        if mode == "Auto Google (SerpAPI) + Manual assistant" and serpapi_key:
            try:
                google_urls = serpapi_search_top10(q, serpapi_key)
            except Exception:
                google_urls = []
        elif uploaded:
            row = df_in[df_in['query'].astype(str) == q]
            if not row.empty:
                raw_g = str(row.iloc[0].get('google_urls', "") or "")
                google_urls = [u.strip() for u in raw_g.split(",") if u.strip()]

        assistant_urls = assistant_map.get(q, [])
        for u in assistant_urls:
            expanded_rows.append({"query": q, "assistant_url": u, "assistant_domain": extract_domain(u)})
    expanded_df = pd.DataFrame(expanded_rows)
    if not expanded_df.empty:
        st.markdown(make_download_link(expanded_df, "assistant_expanded.csv"), unsafe_allow_html=True)

    st.success("Analysis complete.")

else:
    st.info("Provide queries and assistant citation input, then click 'Run analysis'. For Auto Google mode add a SerpAPI key in the sidebar.")