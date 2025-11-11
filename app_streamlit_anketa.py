
import pandas as pd
import numpy as np
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except Exception:
    PLOTLY = False

st.set_page_config(page_title="📊 Prezentace dat – Auto dashboard", layout="wide")

st.title("📊 Auto‑Dashboard pro prezentaci dat")
st.write("""
Nahraj Excel/CSV a aplikace **automaticky navrhne** vhodné vizualizace podle typu dat.
Přepnutím do **Režimu prezentace** skryješ ovládací prvky a získáš čisté slidy s grafy.
""")

# ===== Sidebar: upload & options =====
st.sidebar.header("🗂️ Data")
uploaded = st.sidebar.file_uploader("Nahraj soubor (.xlsx, .xls, .csv)", type=["xlsx","xls","csv"])

# CSV options
csv_sep = st.sidebar.selectbox("Oddělovač (CSV)", [",",";","\t","|"], index=1)
csv_enc = st.sidebar.selectbox("Kódování (CSV)", ["utf-8","cp1250","latin1"], index=0)
header_row = st.sidebar.number_input("Řádek hlavičky (0‑index)", min_value=0, value=0, step=1)

st.sidebar.header("🖥️ Zobrazení")
preset = st.sidebar.selectbox("Šablona dashboardu", [
    "Přehled (auto)",
    "Dotazník – demografie & odpovědi",
    "Numerika & korelace",
    "Časové řady"
])
presentation_mode = st.sidebar.toggle("🎤 Režim prezentace", value=False)
show_table = st.sidebar.toggle("Zobrazit tabulku dat", value=False)

# ===== Helpers =====
def safe_read(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        sep = csv_sep.replace("\t","\t")
        return pd.read_csv(file, sep=sep, encoding=csv_enc, header=header_row)
    else:
        # Excel
        try:
            import openpyxl  # noqa: F401
        except Exception:
            st.warning("Pro čtení .xlsx je vhodné mít nainstalované openpyxl.")
        return pd.read_excel(file)

@st.cache_data(show_spinner=False)
def load(file):
    df = safe_read(file)
    # Gentle parsing to detect numerics/datetimes
    for col in df.columns:
        if df[col].dtype == object:
            # try numeric
            try:
                as_num = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
                if as_num.notna().mean() > 0.6:
                    df[col] = as_num
                    continue
            except Exception:
                pass
            # try datetime
            try:
                as_dt = pd.to_datetime(df[col], errors="coerce")
                if as_dt.notna().mean() > 0.6:
                    df[col] = as_dt
            except Exception:
                pass
    # Create Respondent_ID if none unique id exists
    potential_ids = [c for c in df.columns if df[c].is_unique and df[c].notna().all()]
    if not potential_ids:
        df.insert(0, "Respondent_ID", range(1, len(df)+1))
    return df

def type_buckets(df):
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dt = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    cat = [c for c in df.columns if c not in num and c not in dt]
    return num, dt, cat

def likert_candidates(df, cat_cols):
    # Heuristic: columns with limited set of ordered labels (1–5, strongly disagree–agree)
    out = []
    scale_words = ["souhlasím", "nesouhlasím", "agree", "disagree", "spokojen", "hodnocení"]
    for c in cat_cols:
        vals = pd.Series(df[c].dropna().astype(str).unique())
        if 2 <= len(vals) <= 7:
            text = " ".join(vals.str.lower().tolist())
            if any(w in text for w in scale_words) or vals.str.match(r"^[1-7]$").all():
                out.append(c)
    return out

def top_k_categories(s, k=20):
    vc = s.astype(str).value_counts().sort_values(ascending=False)
    if len(vc) > k:
        vc = vc.head(k)
    return vc.reset_index().rename(columns={"index": s.name, s.name: "Počet"})

# ===== Load =====
if not uploaded:
    st.info("⬆️ Nahraj soubor a já navrhnu vizualizace.")
    st.stop()

df = load(uploaded)
nrows, ncols = df.shape
st.success(f"Načteno {nrows:,} řádků × {ncols} sloupců z **{uploaded.name}**")

if show_table and not presentation_mode:
    st.dataframe(df.head(200), use_container_width=True)

# ===== Auto buckets =====
numeric_cols, datetime_cols, categorical_cols = type_buckets(df)

# ===== Templates =====
def section_title(text):
    if not presentation_mode:
        st.subheader(text)
    else:
        st.markdown(f"### {text}")

# ---- Template: Přehled (auto) ----
if preset == "Přehled (auto)":
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Počet záznamů", f"{nrows:,}")
    with c2: st.metric("Numerické sloupce", str(len(numeric_cols)))
    with c3: st.metric("Kategorické / Datumové", f"{len(categorical_cols)} / {len(datetime_cols)}")

    # Categorical summary
    if categorical_cols:
        section_title("Kategorie – top rozdělení")
        cols = st.columns(2)
        for i, col in enumerate(categorical_cols[:4]):
            data = top_k_categories(df[col])
            if PLOTLY:
                fig = px.bar(data, x=col, y="Počet", title=f"{col} – top kategorie")
                cols[i % 2].plotly_chart(fig, use_container_width=True)
            else:
                cols[i % 2].bar_chart(data.set_index(col))

    # Numeric distributions
    if numeric_cols:
        section_title("Numerika – rozdělení")
        cols = st.columns(2)
        for i, col in enumerate(numeric_cols[:4]):
            if PLOTLY:
                fig = px.histogram(df, x=col, nbins=30, marginal="box", title=f"Histogram: {col}")
                cols[i % 2].plotly_chart(fig, use_container_width=True)
            else:
                cols[i % 2].line_chart(df[col])

    # Correlation
    if len(numeric_cols) >= 2:
        section_title("Korelace (numerika)")
        corr = df[numeric_cols].corr(numeric_only=True)
        if PLOTLY:
            fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns,
                                            colorbar=dict(title="r")))
            fig.update_layout(margin=dict(l=40,r=10,t=30,b=40), title="Korelační matice")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(corr, use_container_width=True)

# ---- Template: Dotazník ----
if preset == "Dotazník – demografie & odpovědi":
    # Guess demographics by common names
    demo_keywords = ["pohlaví","gender","věk","age","vzdělání","education","kraj","region","město","obec"]
    demo_cols = [c for c in categorical_cols if any(k in c.lower() for k in demo_keywords)]
    if demo_cols:
        section_title("Demografie")
        cols = st.columns(2)
        for i, col in enumerate(demo_cols[:6]):
            data = top_k_categories(df[col])
            if PLOTLY:
                fig = px.bar(data, x=col, y="Počet", title=col)
                cols[i % 2].plotly_chart(fig, use_container_width=True)
            else:
                cols[i % 2].bar_chart(data.set_index(col))
    else:
        st.info("Nenalezeny typické demografické sloupce – zobrazím obecné kategorie.")
        section_title("Kategorie (obecné)")
        cols = st.columns(2)
        for i, col in enumerate(categorical_cols[:4]):
            data = top_k_categories(df[col])
            if PLOTLY:
                fig = px.bar(data, x=col, y="Počet", title=col)
                cols[i % 2].plotly_chart(fig, use_container_width=True)
            else:
                cols[i % 2].bar_chart(data.set_index(col))

    # Likert / rating style
    likerts = likert_candidates(df, categorical_cols)
    rating_like = [c for c in df.columns if any(w in c.lower() for w in ["hodnocení","rating","skóre","score"])]
    q_cols = list(dict.fromkeys(likerts + rating_like))
    if q_cols:
        section_title("Hodnocení / Likert")
        for col in q_cols[:6]:
            # try to order categories if numeric-like
            s = df[col].astype(str)
            ordered = None
            if s.str.match(r"^[1-7]$").all():
                ordered = sorted(s.unique(), key=lambda x:int(x))
            if PLOTLY:
                counts = s.value_counts().reindex(ordered) if ordered else s.value_counts()
                data = counts.reset_index().rename(columns={"index": col, col: "Počet"})
                fig = px.bar(data, x=col, y="Počet", title=col)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(s.value_counts())

# ---- Template: Numerika & korelace ----
if preset == "Numerika & korelace":
    if numeric_cols:
        section_title("Distribuce numerických sloupců")
        cols = st.columns(2)
        for i, col in enumerate(numeric_cols[:6]):
            if PLOTLY:
                fig = px.histogram(df, x=col, nbins=40, marginal="violin", title=col)
                cols[i % 2].plotly_chart(fig, use_container_width=True)
            else:
                cols[i % 2].line_chart(df[col])
    if len(numeric_cols) >= 2:
        section_title("Korelace")
        corr = df[numeric_cols].corr(numeric_only=True)
        if PLOTLY:
            fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns,
                                            colorbar=dict(title="r")))
            fig.update_layout(margin=dict(l=40,r=10,t=30,b=40), title="Korelační matice")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(corr, use_container_width=True)

    # Category vs numeric comparison (auto-pick)
    if numeric_cols and categorical_cols:
        section_title("Porovnání: kategorie × numerika (průměr)")
        # pick top categorical by cardinality (but not too many)
        cats = sorted(categorical_cols, key=lambda c: df[c].nunique())[:3]
        for cat in cats:
            num = numeric_cols[0]
            grp = df.groupby(cat)[num].mean().reset_index()
            if PLOTLY:
                fig = px.bar(grp, x=cat, y=num, title=f"Průměr {num} podle {cat}")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.bar_chart(grp.set_index(cat))

# ---- Template: Časové řady ----
if preset == "Časové řady":
    if datetime_cols:
        section_title("Počty záznamů v čase")
        dtc = datetime_cols[0]
        tmp = df[[dtc]].dropna().copy()
        tmp["date"] = pd.to_datetime(tmp[dtc]).dt.date
        series = tmp.groupby("date").size().reset_index(name="Počet")
        if PLOTLY:
            fig = px.line(series, x="date", y="Počet", markers=True, title=f"Aktivity podle dne ({dtc})")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.line_chart(series.set_index("date"))
    else:
        st.info("Nenalezen žádný datumový sloupec.")

# ===== Footer / Export =====
if not presentation_mode:
    st.caption("Tip: Zapni 🎤 Režim prezentace v levém panelu pro čisté slidy bez ovládacích prvků.")
