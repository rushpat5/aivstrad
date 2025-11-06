# app.py
import streamlit as st
import pandas as pd
import tldextract
from urllib.parse import urlparse
from collections import Counter
import base64
import matplotlib.pyplot as plt
import re
import io

st.set_page_config(page_title="Search vs AI Visibility — Client Report", layout="wide")

# ---------- Helpers ----------
def extract_domain(url: str) -> str:
    try:
        ext = tldextract.extract(url)
        domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        return domain.lower()
    except Exception:
        return url.lower()

def parse_input(text: str) -> dict:
    """Parse lines like 'key :: url1, url2' robustly."""
    mapping = {}
    pattern = r"(?im)^(google[:]*\s*.+?|.+?)\s*::\s*(.+)$"
    for match in re.finditer(pattern, text):
        key = match.group(1).strip().lower()
        urls = [u.strip() for u in match.group(2).split(",") if u.strip()]
        mapping[key] = urls
    return mapping

def make_csv_download(df, name="report.csv"):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{name}">Download CSV</a>'

def make_text_download(text_str, name="client_report.txt"):
    b = text_str.encode()
    b64 = base64.b64encode(b).decode()
    return f'<a href="data:file/txt;base64,{b64}" download="{name}">Download client report (TXT)</a>'

def one_line_action(svr, uavr, brand_mentions):
    if svr >= 0.6:
        status = "Strong overlap. Search and AI agree."
        immediate = "Maintain content structure and schema. Monitor monthly."
    elif svr >= 0.3:
        status = "Moderate overlap. AI cites your site sometimes."
        immediate = "Improve headings, add short factual blocks, add schema."
    else:
        status = "Low overlap. AI prefers other sources."
        immediate = "Create clear explainers and FAQ-style content; add schema and canonical PDFs."
    # UAVR nuance
    if uavr >= 0.4:
        novelty = "AI is surfacing many new sources — address content gaps with educational pages."
    else:
        novelty = "AI largely follows Google — focus on clarity and trust signals."
    # Brand nuance
    if brand_mentions == 0:
        brand_text = "Your domain did not appear in AI citations."
    elif brand_mentions == 1:
        brand_text = "Your domain appeared once in AI citations."
    else:
        brand_text = f"Your domain appeared {brand_mentions} times in AI citations."
    return status, immediate, novelty, brand_text

def build_client_report_text(query_list, df, domain_counter, brand_domain):
    lines = []
    avg_svr = round(df["SVR"].mean(), 2) if not df.empty else 0
    avg_uavr = round(df["UAVR"].mean(), 2) if not df.empty else 0
    brand_mentions = domain_counter.get(brand_domain, 0) if brand_domain else 0
    status, immediate, novelty, brand_text = one_line_action(avg_svr, avg_uavr, brand_mentions)

    lines.append("Executive summary")
    lines.append(f"Overall status: {status}")
    lines.append(f"Average SVR (overlap): {avg_svr}")
    lines.append(f"Average UAVR (assistant-unique share): {avg_uavr}")
    lines.append(f"Immediate recommendation: {immediate}")
    lines.append(f"Assistant behavior: {novelty}")
    lines.append(brand_text)
    lines.append("")
    lines.append("Top repeating domains (by assistant citations):")
    for d, c in domain_counter.most_common(8):
        lines.append(f"- {d} : {c} citations")
    lines.append("")
    lines.append("Per-query actionable notes:")
    for _, row in df.iterrows():
        q = row["Query"]
        svr = row["SVR"]
        uavr = row["UAVR"]
        shared = row["Shared (I)"]
        unique = row["Unique (N)"]
        note = ""
        if svr >= 0.6:
            note = "Good overlap. Keep this page format and schema."
        elif svr >= 0.3:
            note = "Partial overlap. Add a short 'claim + evidence' section and FAQ schema."
        else:
            note = "Low overlap. Create a concise explainer (200-300 words), add structured data, and ensure canonical URL."
        if uavr >= 0.4:
            note += " Assistants are citing alternative sources — add factual anchors and references."
        lines.append(f"- {q} : SVR={svr}, Shared={shared}, Unique={unique}. Action: {note}")
    lines.append("")
    lines.append("Priority action list (ordered):")
    lines.append("1) Create one short factual explainer per low-SVR query (200-300 words).")
    lines.append("2) Add FAQ/HowTo/Product schema to those pages.")
    lines.append("3) Stabilize canonical URLs and author/timestamp metadata.")
    lines.append("4) Produce a single PDF authority guide for the topic and publish it on the site.")
    lines.append("5) Re-run this analysis monthly and track SVR trend; target average SVR >= 0.6.")
    return "\n".join(lines)

# ---------- UI ----------
st.title("Search vs AI Visibility — Client-friendly Report")
st.write("Paste your queries, Google top results (manual or via SerpAPI), and assistant citations. The app will generate a clear, prioritized client report.")

with st.sidebar:
    st.header("Inputs")
    brand_domain = st.text_input("Brand domain (for branded insights, e.g., myvi.in)", "")
    mode = st.selectbox("Mode", ["Manual"], index=0)
    st.markdown("Data format (paste in the main page):")
    st.markdown("`query :: url1, url2, url3` and `google::query :: url1, url2` and `assistant::query :: url1, url2`")

st.markdown("### 1) Queries (one per line)")
queries_text = st.text_area("", height=80, placeholder="fancy mobile number")

st.markdown("### 2) Paste Google + Assistant data (use :: separator)")
data_input = st.text_area("", height=240, placeholder="fancy mobile number :: site1, site2\ngoogle::fancy mobile number :: site1, site2\nassistant::fancy mobile number :: siteA, siteB")

if st.button("Generate client report"):
    queries = [q.strip().lower() for q in queries_text.splitlines() if q.strip()]
    if not queries:
        st.error("Enter at least one query in the Queries box.")
    else:
        mapping = parse_input(data_input)
        results = []
        domain_counter = Counter()

        for q in queries:
            # Google list
            google_urls = []
            q_norm = q.replace(" ", "")
            for k, urls in mapping.items():
                if k.startswith("google") and q_norm in k.replace(" ", ""):
                    google_urls = urls
                    break
            # Assistant list
            assistant_urls = []
            for k, urls in mapping.items():
                if k.startswith("assistant") and q in k:
                    assistant_urls = urls
                    break
            # fallback: keys without 'assistant' or 'google' that match query
            if not google_urls:
                for k, urls in mapping.items():
                    if k.startswith("google") is False and k.startswith("assistant") is False and q in k:
                        # if user pasted generic blocks
                        google_urls = []
                        break

            google_set = set(google_urls)
            assistant_set = list(assistant_urls)  # preserve repeats
            assistant_set_set = set(assistant_set)

            # Intersection count: count distinct URLs in both lists
            I = len(google_set & assistant_set_set)
            # Unique assistant citations: total assistant citations minus those that also appear in Google (counts repeats)
            N = sum(1 for u in assistant_set if extract_domain(u) not in {extract_domain(x) for x in google_urls})
            # SVR uses Google top 10 baseline
            SVR = I / 10 if google_urls else 0
            UAVR = N / len(assistant_set) if assistant_set else 0

            # count domains by appearance in assistant citations (count repeats)
            for url in assistant_set:
                domain = extract_domain(url)
                domain_counter[domain] += 1

            results.append({
                "Query": q,
                "Google Results": len(google_urls),
                "Assistant Citations": len(assistant_set),
                "Shared (I)": I,
                "Unique (N)": N,
                "SVR": round(SVR, 3),
                "UAVR": round(UAVR, 3)
            })

        df = pd.DataFrame(results)

        # Build simple client narrative
        report_text = build_client_report_text(queries, df, domain_counter, brand_domain.lower().strip())

        # Clean, single-screen Executive Summary box
        st.header("Executive summary (one screen)")
        avg_svr = round(df["SVR"].mean(), 2) if not df.empty else 0
        avg_uavr = round(df["UAVR"].mean(), 2) if not df.empty else 0
        brand_mentions = domain_counter.get(brand_domain.lower().strip(), 0) if brand_domain else 0
        status, immediate, novelty, brand_text = one_line_action(avg_svr, avg_uavr, brand_mentions)

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(status)
            st.write(f"Average SVR (overlap): {avg_svr}  — fraction of Google top-10 that also appears in AI citations.")
            st.write(f"Average UAVR (assistant-unique share): {avg_uavr}  — fraction of assistant citations not present in Google top-10.")
            st.write(f"Assistant behavior summary: {novelty}")
            st.write(f"Primary recommendation: {immediate}")
            st.write(brand_text)
        with col2:
            st.markdown("Top cited domains (assistant)")
            top_domains_df = pd.DataFrame(domain_counter.most_common(8), columns=["Domain", "Citations"])
            st.table(top_domains_df)

        st.markdown("---")
        st.header("Actionable item list (prioritized)")
        # Priority generation: low SVR queries first
        df_sorted = df.sort_values("SVR")
        for _, r in df_sorted.iterrows():
            q = r["Query"]
            svr = r["SVR"]
            uavr = r["UAVR"]
            if svr < 0.3:
                priority = "High priority — Fix now"
                actions = [
                    "Write a concise explainer (200-300 words) with a clear heading containing the query.",
                    "Add FAQ schema: 3–5 Q&A pairs that answer common sub-questions.",
                    "Add citations and a canonical PDF for permanence."
                ]
            elif svr < 0.6:
                priority = "Medium priority — Improve"
                actions = [
                    "Add a short claim + evidence block near the top (bullet list).",
                    "Add schema (FAQ or HowTo) where appropriate.",
                    "Improve heading clarity and internal links to authority pages."
                ]
            else:
                priority = "Low priority — Maintain"
                actions = [
                    "Keep current structure and monitor for changes.",
                    "Ensure timestamps and author fields are stable."
                ]
            st.markdown(f"**{q}** — {priority} — SVR={svr}, UAVR={uavr}")
            for a in actions:
                st.markdown(f"- {a}")

        st.markdown("---")
        st.header("Per-query table (raw metrics)")
        st.dataframe(df, use_container_width=True)
        st.markdown(make_csv_download(df, "visibility_metrics.csv"), unsafe_allow_html=True)

        st.markdown("---")
        st.header("Downloadable one-page client report (plain text)")
        st.markdown(make_text_download(report_text, "client_report.txt"), unsafe_allow_html=True)

        st.markdown("---")
        st.header("SVR chart")
        # horizontal bar for clarity (handles long labels)
        fig, ax = plt.subplots(figsize=(8, max(2, len(df) * 0.6)))
        ax.barh(df["Query"], df["SVR"], color="#4f7bd8")
        ax.set_xlim(0, 1)
        ax.set_xlabel("SVR (Shared Visibility Rate, 0-1)")
        for i, (val, label) in enumerate(zip(df["SVR"], df["Query"])):
            ax.text(val + 0.02 if val < 0.95 else val - 0.06, i, str(val), va="center", fontsize=9)
        plt.tight_layout()
        st.pyplot(fig)

        st.markdown("---")
        st.header("How to read this report (plain)")
        st.mark.markdown = st.markdown  # silence linter
        st.markdown("""
- SVR is the proportion of Google top results that also appear in AI citations. Aim for average SVR >= 0.6.
- UAVR is the share of assistant citations that Google did not include. High UAVR (>=0.4) means assistants bring in new sources.
- Priority actions target low SVR queries first. Producing short, factual explainers and adding schema increases the chance assistants cite your site.
- Re-run monthly and track SVR trend. Use the downloaded client report to present to stakeholders.
""")
