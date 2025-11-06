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
# UI
# ---------------------------------------------------------------------
st.title("Search vs Assistant Visibility Analyzer")
st.caption("Quantify how much your existing SEO visibility overlaps with AI assistant citations like ChatGPT Search or Perplexity.")

with st.sidebar:
    st.header("Setup")
    mode = st.radio("Mode", ["Manual", "Auto Google (SerpAPI)"], index=0)
    serpapi_key = st.text_input("SerpAPI Key (optional)", type="password")
    show_domains = st.checkbox("Show domain-level breakdown", True)

st.markdown("### Step 1 – Enter Queries (one per line)")
queries_text = st.text_area("Queries", height=120)

st.markdown("""
### Step 2 – Paste Assistant and Google Data  
Each block uses a `::` separator between the query and URLs.

**Examples:**
how to bake sourdough :: sourdoughguide.com, breadtalk.com, thefreshloaf.com
google::how to bake sourdough :: thefreshloaf.com, kingarthurflour.com, seriouseats.com

Acceptable forms include:
- `google::query`
- `google: query`
- `google query`
""")

assistant_input = st.text_area("Paste your data here", height=250)

# ---------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------
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

    st.markdown("---")
    st.markdown("## Reading the Results")
    st.markdown("""
**Shared (I):** URLs appearing in both Google and assistant results  
**Unique (N):** URLs the assistant uses that Google didn’t rank  
**SVR (Shared Visibility Rate):** I ÷ 10 → overlap strength  
**UAVR (Unique Assistant Visibility Rate):** N ÷ assistant citations → novelty fraction  
**RCC (Repeat Citation Count):** Domain citations ÷ queries → citation consistency  

| Pattern | Meaning |
|----------|----------|
| SVR ≥ 0.6 | High overlap – semantic and lexical agree |
| 0.3 ≤ SVR < 0.6 | Partial alignment – improve clarity or linking |
| SVR < 0.3 & high UAVR | Assistants prefer other sources |
| High RCC | Competitors trusted repeatedly |
""")

    st.markdown("### SVR Overview")
    fig, ax = plt.subplots()
    ax.bar(df["Query"], df["SVR"], color="cornflowerblue")
    ax.set_ylabel("SVR (Shared Visibility Rate)")
    ax.set_ylim(0, 1)
    for i, v in enumerate(df["SVR"]):
        ax.text(i, v + 0.02, str(v), ha="center")
    st.pyplot(fig)

    # -----------------------------------------------------------------
    # Detailed Educational Explanation
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("## Understanding This Tool (for Non-Technical SEOs)")
    st.markdown("""
### 1. The Challenge
AI assistants like **ChatGPT Search**, **Perplexity**, and others are changing SEO.  
They answer questions directly — often before a user clicks — and cite only a handful of trusted sources.  

Marketers can’t see how often their content appears there.  
This tool shows **how much of your existing SEO visibility carries into AI assistant visibility**.

---

### 2. What the Tool Actually Does
For each query you provide, it compares:
- **Google’s Top-10 URLs** (classic keyword-based ranking)
- **Assistant citations** (sources the AI assistant used)

It then measures:
- How often the same pages appear in both lists (**Shared Visibility**)
- How many assistant sources are unique (**Novelty**)
- Which domains are cited repeatedly (**Consistency**)

This helps you see whether your SEO strategy aligns with how AI assistants retrieve and trust information.

---

### 3. The Core Metrics Explained Simply
| Metric | Plain Definition | Why It Matters |
|--------|------------------|----------------|
| **SVR (Shared Visibility Rate)** | Portion of Google’s top results that also appear in the assistant’s citations. | Shows how well your content “transfers” from search to AI assistants. |
| **UAVR (Unique Assistant Visibility Rate)** | Portion of assistant sources that Google didn’t include. | Reveals new or alternative sources assistants prefer. |
| **RCC (Repeat Citation Count)** | How often a domain is cited across multiple queries. | Indicates which sites have earned the model’s trust. |

---

### 4. How to Interpret Your Results
| Scenario | Meaning | What To Do |
|-----------|----------|------------|
| **SVR ≥ 0.6** | Strong overlap. Your content is understood by both Google and AI. | Keep structure clean; maintain authority and clarity. |
| **0.3 ≤ SVR < 0.6** | Partial overlap. AI recognizes you, but not as often. | Improve on-page clarity, headings, and schema markup. |
| **SVR < 0.3 with High UAVR** | Assistants trust other sources. | Study high-RCC competitors and their content style. |
| **High RCC for Competitors** | They are repeatedly cited by assistants. | Learn from their formatting, factual clarity, and structured data. |

---

### 5. How to Apply This in Real SEO Work
**1. Monitor Overlap:**  
Track your SVR across queries monthly. If it drops, AI visibility is slipping.  

**2. Identify Semantic Leaders:**  
High-RCC competitor domains show who the AI consistently trusts.  
Audit those sites for structure and schema.  

**3. Improve Semantic Clarity:**  
Use headings, bullet lists, and schema (`FAQ`, `HowTo`, `TechArticle`) to make pages machine-readable.  

**4. Bridge the Visibility Gap:**  
If Google ranks you high but assistants ignore you, focus on factual precision, authorship fields, and clean structure.  

**5. Report to Management:**  
Turn “AI Visibility” into a metric.  
Example: *Our SVR is 0.45 → about 45% of our Google visibility carries into AI assistant discovery.*

---

### 6. The Takeaway
- **Old SEO:** Optimized for clicks and ranks.  
- **New SEO:** Must also optimize for *citations and semantic trust*.  

This tool helps you measure that invisible layer — **where your content stands in the AI discovery ecosystem**.
""")

else:
    st.info("Enter queries and data above, then click **Run Analysis**.")
