import streamlit as st
import pandas as pd
import requests
import tldextract
from urllib.parse import urlparse
from collections import Counter
import base64
import matplotlib.pyplot as plt

st.set_page_config(page_title="Search vs Assistant Visibility", layout="wide")

# ---------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------
def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            ext = tldextract.extract(url)
            domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
            return domain.lower()
        return url.lower()
    except Exception:
        return url.lower()

def parse_pasted_input(text: str) -> dict:
    """Parses pasted text into {query: [urls]} mapping."""
    mapping = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if "::" in line or "\t" in line or "|" in line:
            sep = "::" if "::" in line else ("\t" if "\t" in line else "|")
            parts = [p.strip() for p in line.split(sep, 1)]
            if len(parts) == 2:
                q, urls = parts
                mapping[q.lower()] = [u.strip() for u in urls.split(",") if u.strip()]
            i += 1
        elif i + 1 < len(lines) and ("http" in lines[i + 1] or "," in lines[i + 1]):
            q = line
            urls = [u.strip() for u in lines[i + 1].split(",") if u.strip()]
            mapping[q.lower()] = urls
            i += 2
        else:
            mapping[line.lower()] = []
            i += 1
    return mapping

def serpapi_search_top10(query: str, key: str):
    params = {"engine": "google", "q": query, "api_key": key, "num": 10}
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    data = resp.json()
    results = [r.get("link") for r in data.get("organic_results", []) if r.get("link")]
    return results[:10]

def make_download_link(df, name):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{name}">📥 Download {name}</a>'

# ---------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------
st.title("Search vs Assistant Visibility Analyzer")
st.caption("Compare how often your content appears in **Google Search** vs **AI Assistants** like ChatGPT Search or Perplexity.")

with st.sidebar:
    st.header("Setup")
    mode = st.radio("Choose Input Mode", ["Manual", "Auto Google (SerpAPI)"], index=0)
    serpapi_key = st.text_input("SerpAPI Key (optional)", type="password")
    show_domains = st.checkbox("Show domain-level breakdown", value=True)

st.markdown("""
### Step 1. Enter Queries
Type each search query on a new line.
""")
queries_text = st.text_area("Queries", height=120)

st.markdown("""
### Step 2. Paste Assistant & Google Data
Format examples:
how to bake sourdough :: sourdoughguide.com, breadtalk.com, thefreshloaf.com
google::how to bake sourdough :: thefreshloaf.com, kingarthurflour.com, seriouseats.com

Lines starting with `google::` are treated as **Google Top-10** results.  
Regular lines are **Assistant Citations**.
""")

assistant_input = st.text_area("Paste combined data here", height=250)

# ---------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------
if st.button("Run Analysis"):
    queries = [q.strip().lower() for q in queries_text.splitlines() if q.strip()]
    mapping = parse_pasted_input(assistant_input)

    results, domain_counter = [], Counter()

    for q in queries:
        # --- Flexible Google Top-10 lookup ---
        google_urls = []
        if mode == "Auto Google (SerpAPI)" and serpapi_key:
            try:
                google_urls = serpapi_search_top10(q, serpapi_key)
            except Exception as e:
                st.error(f"Error fetching Google results for '{q}': {e}")
        else:
            q_norm = q.replace(" ", "").lower()
            for key, urls in mapping.items():
                k = key.lower().replace(" ", "")
                if k.startswith("google") and (q_norm in k or k.endswith(q_norm)):
                    google_urls = urls
                    break

        # Assistant URLs
        assistant_urls = mapping.get(q, [])
        if not assistant_urls and q.lower() in mapping:
            assistant_urls = mapping[q.lower()]

        google_set = set(google_urls)
        assistant_set = set(assistant_urls)
        I = len(google_set & assistant_set)
        N = max(0, len(assistant_set) - I)
        SVR = I / 10 if google_urls else 0
        UAVR = N / len(assistant_set) if assistant_set else 0

        for url in assistant_urls:
            domain = extract_domain(url)
            if domain:
                domain_counter[domain] += 1

        results.append({
            "Query": q,
            "Google Results": len(google_urls),
            "Assistant Citations": len(assistant_urls),
            "Shared (I)": I,
            "Unique (N)": N,
            "SVR": round(SVR, 3),
            "UAVR": round(UAVR, 3)
        })

    results_df = pd.DataFrame(results)

    # ---------------- Output ----------------
    st.success("✅ Analysis complete.")
    st.markdown("### Per-Query Metrics")
    st.dataframe(results_df, use_container_width=True)
    st.markdown(make_download_link(results_df, "visibility_report.csv"), unsafe_allow_html=True)

    if show_domains:
        st.markdown("### Domain Repeat Citations (RCC)")
        num_queries = len(queries) or 1
        rcc_df = pd.DataFrame([
            {"Domain": d, "Citations": c, "RCC": round(c / num_queries, 3)}
            for d, c in domain_counter.items()
        ]).sort_values("RCC", ascending=False)
        st.dataframe(rcc_df, use_container_width=True)

    st.markdown("---")
    st.markdown("## How to Read the Results")
    st.markdown("""
**Shared (I):** URLs appearing in both Google and assistant results.  
**Unique (N):** URLs the assistant uses that Google didn’t rank.  
**SVR (Shared Visibility Rate):** I ÷ 10 → overlap of Google’s Top-10 with assistant citations.  
**UAVR (Unique Assistant Visibility Rate):** N ÷ assistant citations → how much new material the assistant adds.  
**RCC (Repeat Citation Count):** How often a domain is repeatedly cited across queries.

| Pattern | Meaning |
|----------|----------|
| SVR ≥ 0.6 | Strong overlap — assistants and Google trust the same sources. |
| 0.3 ≤ SVR < 0.6 | Moderate overlap — improve clarity, linking, or schema. |
| SVR < 0.3 with high UAVR | Assistant prefers other sources — review authority and structure. |
| High RCC for competitors | Indicates strong semantic trust — analyze their design or markup. |
""")

    st.markdown("### SVR Overview")
    fig, ax = plt.subplots()
    ax.bar(results_df["Query"], results_df["SVR"], color="cornflowerblue")
    ax.set_ylabel("SVR (Shared Visibility Rate)")
    ax.set_xlabel("Query")
    ax.set_ylim(0, 1)
    for i, v in enumerate(results_df["SVR"]):
        ax.text(i, v + 0.02, str(v), ha='center')
    st.pyplot(fig)

else:
    st.info("Enter your queries and paste data above, then click **Run Analysis**.")
