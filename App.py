# app.py
import streamlit as st
import pandas as pd
import tldextract
from collections import Counter
import base64
import re
import matplotlib.pyplot as plt

# ---------- APP CONFIG ----------
st.set_page_config(page_title="Search vs AI Visibility Report", layout="wide")

# ---------- HELPERS ----------
def extract_domain(url: str) -> str:
    try:
        ext = tldextract.extract(url)
        domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        return domain.lower()
    except Exception:
        return url.lower()

def parse_input(text: str) -> dict:
    """Parse lines like 'google::query :: url1, url2' or 'assistant::query :: url1, url2'."""
    mapping = {}
    pattern = r"(?im)^(.*?::.*?)\s*::\s*(.+)$"
    for match in re.finditer(pattern, text):
        key = match.group(1).strip().lower()
        urls = [u.strip() for u in match.group(2).split(",") if u.strip()]
        mapping[key] = urls
    return mapping

def make_csv_download(df, name="report.csv"):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{name}">📥 Download CSV</a>'

def make_text_download(text_str, name="client_report.txt"):
    b = text_str.encode()
    b64 = base64.b64encode(b).decode()
    return f'<a href="data:file/txt;base64,{b64}" download="{name}">📄 Download Text Report</a>'

def summarize_results(avg_svr, avg_uavr, brand_mentions):
    if avg_svr >= 0.6:
        status = "🟩 Strong Overlap"
        interp = "AI assistants and Google trust the same content sources."
        action = "Maintain current clarity and authority. Keep updating structured data."
    elif avg_svr >= 0.3:
        status = "🟧 Moderate Overlap"
        interp = "Assistants cite your brand but also show competitors."
        action = "Add clearer markup, stronger linking, and FAQs to boost semantic trust."
    else:
        status = "🟥 Low Overlap"
        interp = "Assistants prefer competitor sources more often than Google does."
        action = "Rebuild clarity, fix schema, and publish short, factual explainers."

    if avg_uavr >= 0.4:
        novelty = "Assistants are showing many unique sources — AI is finding new trusted domains."
    else:
        novelty = "Assistants mostly reuse Google’s trusted set — stability is high."

    if brand_mentions == 0:
        brand_text = "Your domain does not appear in AI citations — low AI trust."
    elif brand_mentions == 1:
        brand_text = "Your domain appeared once in AI citations — limited but visible."
    else:
        brand_text = f"Your domain appeared {brand_mentions} times in AI citations — strong recurring AI trust."

    return status, interp, novelty, action, brand_text

# ---------- UI ----------
st.title("🔍 Search vs AI Visibility Report")
st.caption("Compare Google’s top results with AI assistant citations (ChatGPT, Perplexity, etc.).")

with st.sidebar:
    st.header("Setup")
    brand_domain = st.text_input("Brand domain (for highlight, e.g., myvi.in)", "")
    st.markdown("**Paste Data Format:**")
    st.code("google::fancy mobile number :: url1, url2, ...\nassistant::fancy mobile number :: urlA, urlB, ...", language="text")

st.markdown("### Step 1. Enter Query")
queries_text = st.text_area("Queries (one per line)", "fancy mobile number", height=80)

st.markdown("### Step 2. Paste Combined Data")
data_input = st.text_area("Paste Google and Assistant citation data below", height=300)

if st.button("Run Analysis"):
    queries = [q.strip().lower() for q in queries_text.splitlines() if q.strip()]
    mapping = parse_input(data_input)
    results = []
    domain_counter = Counter()

    for q in queries:
        google_urls, assistant_urls = [], []
        for k, urls in mapping.items():
            if k.startswith("google") and q in k:
                google_urls = urls
            if k.startswith("assistant") and q in k:
                assistant_urls = urls

        google_set = set(google_urls)
        assistant_set = assistant_urls
        assistant_unique = [u for u in assistant_set if extract_domain(u) not in {extract_domain(x) for x in google_urls}]
        I = len(google_set & set(assistant_set))
        N = len(assistant_unique)

        SVR = I / 10 if google_urls else 0
        UAVR = N / len(assistant_set) if assistant_set else 0

        for url in assistant_set:
            domain_counter[extract_domain(url)] += 1

        results.append({
            "Query": q,
            "Google Results": len(google_urls),
            "Assistant Citations": len(assistant_set),
            "Shared (I)": I,
            "Unique (N)": N,
            "SVR": round(SVR, 2),
            "UAVR": round(UAVR, 2)
        })

    df = pd.DataFrame(results)
    avg_svr = round(df["SVR"].mean(), 2) if not df.empty else 0
    avg_uavr = round(df["UAVR"].mean(), 2) if not df.empty else 0
    brand_mentions = domain_counter.get(brand_domain.lower().strip(), 0)

    # ---------- Executive Summary ----------
    st.markdown("## 🧭 Executive Summary")
    status, interp, novelty, action, brand_text = summarize_results(avg_svr, avg_uavr, brand_mentions)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader(status)
        st.write(f"**Average SVR:** {avg_svr}")
        st.write(f"**Average UAVR:** {avg_uavr}")
        st.write(f"**Interpretation:** {interp}")
        st.write(f"**Assistant Behavior:** {novelty}")
        st.write(f"**Recommendation:** {action}")
        st.write(f"**Brand Insight:** {brand_text}")

    with col2:
        top_domains = pd.DataFrame(domain_counter.most_common(8), columns=["Domain", "Citations"])
        st.markdown("### 🔝 Top AI-Cited Domains")
        st.table(top_domains)

    # ---------- Visual Chart ----------
    st.markdown("## 📊 SVR (Shared Visibility Rate) per Query")
    fig, ax = plt.subplots(figsize=(8, max(2, len(df) * 0.6)))
    ax.barh(df["Query"], df["SVR"], color="#4f7bd8")
    ax.set_xlim(0, 1)
    ax.set_xlabel("SVR (0–1 scale)")
    for i, val in enumerate(df["SVR"]):
        ax.text(val + 0.02 if val < 0.95 else val - 0.06, i, str(val), va="center", fontsize=9)
    plt.tight_layout()
    st.pyplot(fig)

    # ---------- Tables ----------
    st.markdown("## 📋 Per-Query Breakdown")
    st.dataframe(df, use_container_width=True)
    st.markdown(make_csv_download(df, "visibility_report.csv"), unsafe_allow_html=True)

    st.markdown("## 🌐 Domain Repeat Citations (RCC)")
    rcc_df = pd.DataFrame(domain_counter.items(), columns=["Domain", "Citations"])
    rcc_df["RCC"] = rcc_df["Citations"]
    st.dataframe(rcc_df.sort_values("Citations", ascending=False), use_container_width=True)

    # ---------- Narrative Report ----------
    st.markdown("## 🧾 Client Narrative Report")
    report_lines = [
        f"Overall Visibility Status: {status}",
        f"Average SVR: {avg_svr}",
        f"Average UAVR: {avg_uavr}",
        "",
        f"Interpretation: {interp}",
        f"Assistant Behavior: {novelty}",
        f"Recommended Action: {action}",
        f"Brand Observation: {brand_text}",
        "",
        "Priority Actions:",
        "1. Fix low-SVR queries first with structured, concise content (200–300 words).",
        "2. Add FAQ, HowTo, or Product schema for all core pages.",
        "3. Add canonical PDFs for high-trust content.",
        "4. Standardize author/timestamp metadata.",
        "5. Track SVR monthly; target >= 0.6 as a strong benchmark."
    ]
    report_text = "\n".join(report_lines)
    st.text_area("Plain Report Summary", report_text, height=220)
    st.markdown(make_text_download(report_text, "client_report.txt"), unsafe_allow_html=True)

    # ---------- Explanation Tab ----------
    st.markdown("---")
    st.markdown("## 📘 How to Read This Report")
    st.markdown("""
**SVR (Shared Visibility Rate)** — The overlap between Google’s Top 10 results and AI assistant citations.
- **High SVR (≥ 0.6):** Google and AI align well — maintain clarity.
- **Moderate SVR (0.3–0.59):** AI occasionally cites you — optimize structure and schema.
- **Low SVR (< 0.3):** AI prefers other domains — rebuild topic clarity and authority.

**UAVR (Unique Assistant Visibility Rate)** — How many assistant citations do not appear in Google Top 10.
- **High UAVR (> 0.4):** AI is finding unique, niche sources — expand into these gaps.
- **Low UAVR (< 0.2):** AI is repeating Google’s trust set — stability is good.

**RCC (Repeat Citation Count)** — How many times each domain was cited across all queries.
High RCC = strong semantic trust. Analyze recurring competitor domains for structural patterns.

**What to do next:**
1. Prioritize fixing low-SVR queries.
2. Strengthen schema and structured data.
3. Keep canonical and timestamp stable.
4. Publish short, verifiable PDFs for high-trust pages.
5. Re-run monthly to track visibility alignment trends.
""")
