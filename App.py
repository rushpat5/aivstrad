import streamlit as st
import pandas as pd
import requests
import tldextract
from urllib.parse import urlparse
from collections import Counter
import base64
import matplotlib.pyplot as plt
import re

st.set_page_config(page_title="Search vs Assistant Visibility Analyzer", layout="wide")

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

def parse_input(text: str) -> dict:
    """Robust parser that supports google::, google:, or any variant on newlines."""
    mapping = {}
    pattern = r"(?im)^(google[:]*\s*.+?|.+?)\s*::\s*(.+)$"
    for match in re.finditer(pattern, text):
        key = match.group(1).strip().lower()
        urls = [u.strip() for u in match.group(2).split(",") if u.strip()]
        mapping[key] = urls
    return mapping

def serpapi_search_top10(query: str, key: str):
    params = {"engine": "google", "q": query, "api_key": key, "num": 10}
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
    data = r.json()
    return [res.get("link") for res in data.get("organic_results", []) if res.get("link")][:10]

def make_download_link(df, name):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{name}">📥 Download {name}</a>'


# ---------------------------------------------------------------------
# TAB STRUCTURE
# ---------------------------------------------------------------------
tab1, tab2 = st.tabs(["🔍 Run Analysis", "ℹ️ About & Explanation"])

# =====================================================================
# TAB 1 — MAIN TOOL
# =====================================================================
with tab1:
    st.title("Search vs Assistant Visibility Analyzer")
    st.caption("Quantify how much your SEO visibility overlaps with AI assistant citations (ChatGPT Search, Perplexity, etc.)")

    with st.sidebar:
        st.header("Setup")
        mode = st.radio("Mode", ["Manual", "Auto Google (SerpAPI)"], index=0)
        serpapi_key = st.text_input("SerpAPI Key (optional)", type="password")
        show_domains = st.checkbox("Show domain-level breakdown", True)

    st.markdown("### Step 1 – Enter Queries (one per line)")
    queries_text = st.text_area("Queries", height=120)

    st.markdown("""
    ### Step 2 – Paste Assistant and Google Data  
    Use `::` as a separator between query and URLs.

    **Examples:**
    ```
    how to bake sourdough :: sourdoughguide.com, breadtalk.com, thefreshloaf.com
    google::how to bake sourdough :: thefreshloaf.com, kingarthurflour.com, seriouseats.com
    ```

    Acceptable forms:  
    - `google::query`  
    - `google: query`  
    - `google query`
    """)

    assistant_input = st.text_area("Paste your data here", height=250)

    if st.button("Run Analysis"):
        queries = [q.strip().lower() for q in queries_text.splitlines() if q.strip()]
        mapping = parse_input(assistant_input)
        results, domain_counter = [], Counter()

        for q in queries:
            # Find Google list
            google_urls = []
            if mode == "Auto Google (SerpAPI)" and serpapi_key:
                try:
                    google_urls = serpapi_search_top10(q, serpapi_key)
                except Exception as e:
                    st.error(f"SerpAPI error for '{q}': {e}")
            else:
                q_norm = q.replace(" ", "")
                for k, urls in mapping.items():
                    if k.startswith("google") and q_norm in k.replace(" ", ""):
                        google_urls = urls
                        break

            # Assistant list
            assistant_urls = []
            for k, urls in mapping.items():
                if not k.startswith("google") and q in k:
                    assistant_urls = urls
                    break

            google_set, assistant_set = set(google_urls), set(assistant_urls)
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

        df = pd.DataFrame(results)

        # -----------------------------------------------------------------
        # Output
        # -----------------------------------------------------------------
        st.success("✅ Analysis complete.")
        st.markdown("### Per-Query Metrics")
        st.dataframe(df, use_container_width=True)
        st.markdown(make_download_link(df, "visibility_report.csv"), unsafe_allow_html=True)

        if show_domains:
            st.markdown("### Domain Repeat Citations (RCC)")
            qn = len(queries) or 1
            rcc = pd.DataFrame(
                [{"Domain": d, "Citations": c, "RCC": round(c / qn, 3)} for d, c in domain_counter.items()]
            ).sort_values("RCC", ascending=False)
            st.dataframe(rcc, use_container_width=True)

        st.markdown("### SVR Overview")
        fig, ax = plt.subplots()
        ax.bar(df["Query"], df["SVR"], color="cornflowerblue")
        ax.set_ylabel("SVR (Shared Visibility Rate)")
        ax.set_ylim(0, 1)
        for i, v in enumerate(df["SVR"]):
            ax.text(i, v + 0.02, str(v), ha="center")
        st.pyplot(fig)

# =====================================================================
# TAB 2 — ABOUT / EXPLANATION
# =====================================================================
with tab2:
    st.title("About This Tool")
    st.markdown("""
### Purpose
Traditional SEO metrics show what ranks in Google, but AI assistants like **ChatGPT Search**, **Perplexity**, and **Gemini** now act as new intermediaries.  
They answer questions directly, summarizing from sources they trust — often before a user clicks.  
This tool quantifies **how much of your search visibility carries into AI assistant visibility.**

---

### How It Works
1. **You provide:**
   - Google’s Top-10 results for your query.
   - AI assistant’s cited sources for the same query.
2. **The tool compares them.**
   - Finds overlap (shared URLs/domains).
   - Finds unique assistant citations.
   - Measures how often competitors appear across queries.

---

### Metrics in Simple Terms
| Metric | Definition | Why It Matters |
|--------|-------------|----------------|
| **Shared (I)** | Number of URLs appearing in both Google & AI lists. | Shows alignment between search and assistant. |
| **Unique (N)** | Assistant-only citations. | Reveals new sources AI trusts. |
| **SVR (Shared Visibility Rate)** | % of Google’s Top-10 also cited by AI. | Measures overlap strength. |
| **UAVR (Unique Assistant Visibility Rate)** | % of assistant citations not in Google’s Top-10. | Measures novelty or divergence. |
| **RCC (Repeat Citation Count)** | Domain consistency across multiple queries. | Identifies semantically trusted competitors. |

---

### Interpreting Results
| Pattern | Meaning | SEO Implication |
|----------|----------|-----------------|
| **SVR ≥ 0.6** | Strong overlap | Your content ranks well *and* is semantically trusted by AI. |
| **0.3 ≤ SVR < 0.6** | Partial overlap | Improve clarity, structure, and schema markup. |
| **SVR < 0.3 & UAVR high** | Divergence | Assistants trust other content types—analyze their formats. |
| **High RCC** | Repeated domain trust | Indicates who LLMs “believe” most—study those sites. |

---

### How SEOs Can Use This
1. **Visibility Mapping:**  
   Track how much of your Google visibility carries into AI discovery.

2. **Competitor Discovery:**  
   Identify domains repeatedly cited by assistants even if they rank lower in Google.

3. **Content Optimization:**  
   - Use **short, factual paragraphs (200–300 words)**.  
   - Add **structured data** (`FAQ`, `HowTo`, `TechArticle`).  
   - Keep **author and timestamp metadata** consistent.  
   - Include canonical PDFs for credibility on factual content.

4. **Reporting:**  
   Present to management:  
   *“Our SVR = 0.45 → roughly 45% of our SEO visibility extends into AI visibility.”*

---

### Why It Matters
- **Search is now hybrid.**  
  Google uses both lexical and semantic retrieval.  
  AI assistants use semantic retrieval only.  
  Measuring their intersection is essential to understanding how your brand is represented in AI-generated answers.

- **This tool is your first diagnostic layer.**  
  It shows *where you stand* between two worlds —  
  **SEO rankings** and **AI-driven discovery**.

---

### Summary
- SEO still drives measurable traffic.  
- AI assistants shape *perception* and *trust*.  
- This tool bridges that gap by turning invisible AI citations into quantifiable metrics.

---
**Author:** Built for marketers adapting to the post-SEO landscape.  
**Goal:** Make AI visibility measurable, actionable, and trackable.
""")
