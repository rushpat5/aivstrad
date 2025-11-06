import streamlit as st
import pandas as pd
import requests
import tldextract
from urllib.parse import urlparse
from collections import Counter
import base64
import matplotlib.pyplot as plt
import re

# ---------------------------------------------------------------------
# Page Setup
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Search vs AI Visibility Analyzer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------
def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        ext = tldextract.extract(url)
        domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        return domain.lower()
    except Exception:
        return url.lower()

def parse_input(text: str) -> dict:
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
# Layout Tabs
# ---------------------------------------------------------------------
tab1, tab2 = st.tabs(["🔍 Run Analysis", "ℹ️ About & Explanation"])

# =====================================================================
# TAB 1 — MAIN TOOL
# =====================================================================
with tab1:
    st.title("Search vs AI Visibility Analyzer")
    st.caption("Quantify how much your Google SEO visibility carries into AI assistant citations (ChatGPT, Perplexity, etc.)")

    with st.sidebar:
        st.header("Setup")
        mode = st.radio("Mode", ["Manual", "Auto Google (SerpAPI)"], index=0)
        serpapi_key = st.text_input("SerpAPI Key (optional)", type="password")
        brand_domain = st.text_input("Your Brand Domain (e.g., myvi.in)").strip().lower()
        show_domains = st.checkbox("Show domain-level breakdown", True)

    # -----------------------------------------------------------------
    # Input Section
    # -----------------------------------------------------------------
    st.markdown("### Step 1 — Enter Queries")
    queries_text = st.text_area("One query per line", height=100)

    st.markdown("""
    ### Step 2 — Paste Assistant & Google Data  
    Use `::` to separate query and URLs.

    **Example format:**
    ```
    vi prepaid plans :: myvi.in, airtel.in, jio.com  
    google::vi prepaid plans :: myvi.in, jio.com, airtel.in, paytm.com
    ```
    """)

    assistant_input = st.text_area("Paste your data here", height=200)

    # -----------------------------------------------------------------
    # Run Analysis
    # -----------------------------------------------------------------
    if st.button("Run Analysis"):
        queries = [q.strip().lower() for q in queries_text.splitlines() if q.strip()]
        mapping = parse_input(assistant_input)
        results, domain_counter = [], Counter()

        for q in queries:
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
        # Smart Summary
        # -----------------------------------------------------------------
        st.success("✅ Analysis complete.")
        st.markdown("## 🔎 Executive Summary")

        avg_svr = round(df["SVR"].mean(), 2)
        avg_uavr = round(df["UAVR"].mean(), 2)
        top_domains = (
            pd.DataFrame(domain_counter.items(), columns=["Domain", "Count"])
            .sort_values("Count", ascending=False)
            .head(5)
        )

        # Brand Analysis
        brand_mentions = 0
        competitor_domains = []
        if brand_domain:
            brand_mentions = domain_counter.get(brand_domain, 0)
            competitor_domains = [d for d in top_domains["Domain"] if d != brand_domain]

        # Strength Classification
        if avg_svr >= 0.6:
            summary_label = "🟩 Strong Overlap"
            explanation = "AI assistants and Google trust the same content sources."
            recommendation = "Maintain structure and authoritative tone. You’re well aligned semantically."
        elif 0.3 <= avg_svr < 0.6:
            summary_label = "🟨 Moderate Overlap"
            explanation = "AI assistants cite your pages but also rely on competitors."
            recommendation = "Clarify headings, tighten schema markup, and simplify factual blocks."
        else:
            summary_label = "🟥 Low Overlap"
            explanation = "AI assistants prefer other domains over yours."
            recommendation = "Review competitor structure and improve factual precision and clarity."

        # Novelty Message
        novelty = "high" if avg_uavr >= 0.4 else "low"
        novelty_text = (
            "Assistants surface many new sources — possible content gaps."
            if novelty == "high"
            else "Assistants mostly reuse Google results — consistent trust base."
        )

        # Brand Statement
        if brand_domain:
            if brand_mentions == 0:
                brand_text = f"🟥 Your domain `{brand_domain}` did **not** appear in any AI citations — no semantic presence detected."
            elif brand_mentions <= len(df) // 2:
                brand_text = f"🟨 Your domain `{brand_domain}` appeared {brand_mentions} times — partial recognition across AI results."
            else:
                brand_text = f"🟩 Your domain `{brand_domain}` appeared {brand_mentions} times — strong recurring AI trust."
        else:
            brand_text = "_(Enter your brand domain in the sidebar for tailored analysis.)_"

        # Narrative Summary
        st.markdown(f"""
        **Overall Score:** {summary_label}  
        **Average SVR:** {avg_svr}  
        **Average UAVR:** {avg_uavr}  
        **Interpretation:** {explanation}  
        **Assistant Behavior:** {novelty_text}  
        **Recommendation:** {recommendation}  
        ---
        {brand_text}
        """)

        # Competitor Info
        if competitor_domains:
            st.markdown("### ⚔️ Top Competing Domains in AI Citations")
            for d in competitor_domains:
                st.write(f"- {d}")

        # -----------------------------------------------------------------
        # Data + Visuals
        # -----------------------------------------------------------------
        st.markdown("### 📊 Per-Query Breakdown")
        st.dataframe(df, use_container_width=True)
        st.markdown(make_download_link(df, "visibility_report.csv"), unsafe_allow_html=True)

        if show_domains:
            st.markdown("### 🌐 Domain Repeat Citations (RCC)")
            qn = len(queries) or 1
            rcc = pd.DataFrame(
                [{"Domain": d, "Citations": c, "RCC": round(c / qn, 3)} for d, c in domain_counter.items()]
            ).sort_values("RCC", ascending=False)
            st.dataframe(rcc, use_container_width=True)

        # -----------------------------------------------------------------
        # Improved Graph Handling Long Queries
        # -----------------------------------------------------------------
        st.markdown("### 📈 SVR (Shared Visibility Rate) per Query")

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(range(len(df)), df["SVR"], color="cornflowerblue")
        ax.set_ylabel("SVR (Overlap Score)")
        ax.set_ylim(0, 1)
        ax.set_xticks(range(len(df)))
        ax.set_xticklabels(df["Query"], rotation=35, ha="right", fontsize=9, wrap=True)
        for i, v in enumerate(df["SVR"]):
            ax.text(i, v + 0.02, str(v), ha="center", fontsize=8)
        plt.tight_layout()
        st.pyplot(fig)

        # -----------------------------------------------------------------
        # Clear Closing Guidance
        # -----------------------------------------------------------------
        st.markdown("---")
        st.markdown("### 🧭 How to Act on This Data")
        st.markdown(f"""
        - **SVR < 0.3:** Rewrite those pages — improve factual tone, internal linking, and structure.  
        - **SVR 0.3–0.6:** Align terminology, headings, and schema with how AI systems describe your topic.  
        - **SVR > 0.6:** Keep content stable; you’re semantically strong.  
        - **High RCC competitors:** Analyze their markup (schema.org, FAQ use) and page layout.  
        - **Goal:** Raise your average SVR toward 0.6+ while keeping low UAVR.
        """)

# =====================================================================
# TAB 2 — ABOUT & EXPLANATION
# =====================================================================
with tab2:
    st.title("About This Tool")
    st.markdown("""
### Purpose
Search engines and AI assistants retrieve information differently.  
Search ranks pages **after** the answer is known.  
AI assistants retrieve and synthesize **before** any click.  

This tool measures **semantic visibility** — how much your SEO presence transfers into AI trust.

---

### Key Metrics
| Metric | What It Means | Good Range |
|--------|----------------|-------------|
| **SVR (Shared Visibility Rate)** | % of Google Top 10 also cited by AI | > 0.6 = strong |
| **UAVR (Unique Assistant Visibility Rate)** | % of assistant-only citations | < 0.4 preferred |
| **RCC (Repeat Citation Count)** | How often domains recur across queries | High = trusted |

---

### How to Apply
1. Choose your **brand domain** and key search queries.  
2. Run analysis using Google + AI citations.  
3. Check your **SVR** and **RCC** trends over time.  
4. Benchmark competitors’ RCC — their content is semantically favored.  
5. Optimize structure and schema on pages with low SVR.

---

### What High vs Low SVR Means
| SVR Range | Interpretation | Recommended Focus |
|------------|----------------|-------------------|
| ≥ 0.6 | AI and Search agree — you’re semantically strong. | Maintain clarity & structure |
| 0.3–0.6 | Mixed trust — some overlap, some gaps. | Improve content markup |
| < 0.3 | AI assistants ignore your site. | Fix structure, strengthen authority |

---

### Bottom Line
**SEO measures visibility.**  
**This tool measures trust.**  
Your goal: make your content equally discoverable by both Google and AI.
""")
