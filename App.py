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
    """Flexible parser supporting google::, google:, or multiline entries."""
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
# Tabs
# ---------------------------------------------------------------------
tab1, tab2 = st.tabs(["🔍 Run Analysis", "ℹ️ About & Explanation"])

# =====================================================================
# TAB 1 — MAIN TOOL
# =====================================================================
with tab1:
    st.title("Search vs Assistant Visibility Analyzer")
    st.caption("Measure how much your Google SEO visibility carries into AI assistant citations like ChatGPT Search or Perplexity.")

    with st.sidebar:
        st.header("Setup")
        mode = st.radio("Mode", ["Manual", "Auto Google (SerpAPI)"], index=0)
        serpapi_key = st.text_input("SerpAPI Key (optional)", type="password")
        show_domains = st.checkbox("Show domain-level breakdown", True)

    st.markdown("### Step 1 – Enter Queries (one per line)")
    queries_text = st.text_area("Queries", height=120)

    st.markdown("""
    ### Step 2 – Paste Assistant and Google Data  
    Use `::` to separate query names and URLs.

    **Example:**
    ```
    vi prepaid plans :: myvi.in, airtel.in, jio.com
    google::vi prepaid plans :: myvi.in, jio.com, airtel.in, paytm.com
    ```

    Formats supported:  
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
            # Get Google URLs
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

            # Assistant URLs
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
        # Plain-English Summary
        # -----------------------------------------------------------------
        st.success("✅ Analysis complete.")
        st.markdown("### Results Summary (Plain English)")

        avg_svr = round(df["SVR"].mean(), 2)
        avg_uavr = round(df["UAVR"].mean(), 2)
        top_domains = (
            pd.DataFrame(domain_counter.items(), columns=["Domain", "Count"])
            .sort_values("Count", ascending=False)
            .head(3)
        )

        if avg_svr >= 0.6:
            strength = "🟩 Strong overlap — AI assistants and Google trust the same pages."
            action = "Maintain clarity, factual tone, and structured data. You’re semantically aligned."
        elif 0.3 <= avg_svr < 0.6:
            strength = "🟨 Moderate overlap — assistants cite you but also show competitors."
            action = "Tighten on-page clarity, headings, and schema markup to raise semantic trust."
        else:
            strength = "🟥 Low overlap — assistants prefer other domains."
            action = "Study top-cited competitors. Improve structure, evidence blocks, and factual precision."

        if avg_uavr >= 0.4:
            novelty = "Assistants surface many new sources (high UAVR)."
        else:
            novelty = "Assistants mostly reuse Google’s top results (low UAVR)."

        st.markdown(f"""
        **Average SVR:** {avg_svr}  
        **Average UAVR:** {avg_uavr}  
        **Overall Assessment:** {strength}  
        **Assistant Behavior:** {novelty}  
        **Recommended Action:** {action}
        """)

        st.markdown("### Top Repeated Domains (High RCC = Trusted Sources)")
        st.table(top_domains)

        # -----------------------------------------------------------------
        # Full Data Tables
        # -----------------------------------------------------------------
        st.markdown("### Per-Query Breakdown")
        st.dataframe(df, use_container_width=True)
        st.markdown(make_download_link(df, "visibility_report.csv"), unsafe_allow_html=True)

        if show_domains:
            st.markdown("### Domain Repeat Citations (RCC)")
            qn = len(queries) or 1
            rcc = pd.DataFrame(
                [{"Domain": d, "Citations": c, "RCC": round(c / qn, 3)} for d, c in domain_counter.items()]
            ).sort_values("RCC", ascending=False)
            st.dataframe(rcc, use_container_width=True)

        # -----------------------------------------------------------------
        # Chart Visualization
        # -----------------------------------------------------------------
        st.markdown("### SVR Overview (Overlap by Query)")
        fig, ax = plt.subplots()
        ax.bar(df["Query"], df["SVR"], color="cornflowerblue")
        ax.set_ylabel("SVR (Shared Visibility Rate)")
        ax.set_ylim(0, 1)
        for i, v in enumerate(df["SVR"]):
            ax.text(i, v + 0.02, str(v), ha="center")
        st.pyplot(fig)

        # -----------------------------------------------------------------
        # Contextual Explanation
        # -----------------------------------------------------------------
        st.markdown("---")
        st.markdown("### Interpreting These Results")
        st.markdown(f"""
        - **SVR (Shared Visibility Rate)** → how much Google visibility carries into AI assistants.  
          • 0.6+ = Strong alignment  
          • 0.3–0.6 = Partial alignment  
          • < 0.3 = AI not using your pages  

        - **UAVR (Unique Assistant Visibility Rate)** → how many new sources assistants use.  
          • High UAVR = assistants trust new sources (potential gaps).  
          • Low UAVR = assistants echo Google (consistent trust).  

        - **RCC (Repeat Citation Count)** → domains that repeatedly appear in AI citations.  
          High RCC for competitors = they’re semantically trusted — study their structure and markup.  

        **Action Plan Example (for Vi-type brands):**
        1. Focus on pages with SVR < 0.3 and rework structure (short factual paragraphs, FAQs).  
        2. Add structured data (FAQ, Product, HowTo) to recharge and plan pages.  
        3. Monitor SVR monthly; rising SVR = better AI visibility.  
        4. Track high-RCC competitors and analyze their formatting and metadata.
        """)

# =====================================================================
# TAB 2 — ABOUT / EXPLANATION
# =====================================================================
with tab2:
    st.title("About & Explanation")
    st.markdown("""
### Purpose
Traditional SEO reports stop at Google rankings.  
AI assistants like **ChatGPT Search**, **Perplexity**, and **Gemini** now filter and summarize before the click — changing visibility itself.  
This tool helps measure **semantic visibility** — how often your content is cited or trusted by AI.

---

### What It Measures
- **Overlap (SVR):** How often Google’s Top-10 results also appear in AI assistant citations.  
- **Novelty (UAVR):** How many assistant sources are new or different.  
- **Consistency (RCC):** How frequently domains appear across multiple queries.

---

### Why It Matters
| Challenge | Impact | Metric |
|------------|---------|---------|
| Google ranks pages by keyword match | Traditional visibility | SVR shows carryover into AI |
| AI assistants summarize before clicks | Lost traffic measurement | UAVR shows new visibility gaps |
| Competitors cited repeatedly | Semantic authority | RCC identifies trusted competitors |

---

### How to Use This Practically
1. Run your brand’s key queries (plans, features, FAQs).  
2. Compare **SVR** — low values mean AI assistants aren’t surfacing your content.  
3. Study **RCC** — repeated domains = trusted information sources.  
4. Adjust structure and schema until overlap improves.

---

### Quick Reference
| Metric | Target | Interpretation |
|--------|--------|----------------|
| **SVR ≥ 0.6** | Strong alignment | Google + AI both trust your pages |
| **0.3 ≤ SVR < 0.6** | Partial overlap | Improve clarity and linking |
| **SVR < 0.3** | Low overlap | AI ignoring your pages |
| **High RCC** | Consistent trust | You (or a competitor) are semantically authoritative |

---

### Example Application
For **Vi (Vodafone Idea):**
- SVR ≈ 0.45 → assistants cite Vi pages about half as often as Google does.  
- RCC shows Airtel and Jio appear equally often → equal semantic trust.  
- Recommended: tighten FAQ schema, make recharge pages more structured, maintain factual phrasing.

---

### Bottom Line
- **SEO measures discoverability.**  
- **This tool measures trust.**  
It bridges traditional search visibility with emerging AI-driven discovery.
""")
