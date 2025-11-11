import pandas as pd
import numpy as np
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except Exception:
    PLOTLY = False

st.set_page_config(page_title="📊 Bezpečná analýza dat", layout="wide")
st.title("📊 Interaktivní analýza dat – SAFE verze")

st.write(
    "Tato verze aplikace je odolná vůči chybám v grafických knihovnách."
)

# ----------- Pomocné funkce -----------
def safe_bar(df, x, y, title=""):
    if df is None or len(df) == 0:
        st.info("Žádná data pro graf.")
        return
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    if x not in df.columns or y not in df.columns:
        st.warning(f"Nelze vykreslit graf: chybí sloupce '{x}' nebo '{y}'.")
        st.dataframe(df.head(20), use_container_width=True)
        return
    if PLOTLY:
        try:
            fig = px.bar(df, x=x, y=y, title=title)
            st.plotly_chart(fig, use_container_width=True)
            return
        except Exception as e:
            st.warning(f"Plotly selhal ({type(e).__name__}): přepínám na jednoduchý graf.")
    st.bar_chart(df.set_index(x)[y])

def safe_hist(df, col, title=""):
    if col not in df.columns:
        st.warning(f"Sloupec '{col}' nebyl nalezen.")
        return
    if PLOTLY:
        try:
            fig = px.histogram(df, x=col, nbins=30, marginal="box", title=title or f"Histogram: {col}")
            st.plotly_chart(fig, use_container_width=True)
            return
        except Exception as e:
            st.warning(f"Plotly histogram selhal ({type(e).__name__}). Zobrazuji jednoduchý graf.")
    st.line_chart(df[col])

# ----------- Načtení dat -----------
st.sidebar.header("⚙️ Nastavení")
uploaded = st.sidebar.file_uploader("Nahraj datový soubor", type=["xlsx", "xls", "csv"])

read_kwargs = {}
delimiter = None
sheet_name = None
if uploaded is not None:
    if uploaded.name.lower().endswith(".csv"):
        delimiter = st.sidebar.selectbox("Oddělovač (CSV)", [",", ";", "\t", "|"], index=1)
        encoding = st.sidebar.selectbox("Kódování", ["utf-8", "cp1250", "latin1"], index=0)
        header_row = st.sidebar.number_input("Řádek hlavičky (0-index)", min_value=0, value=0, step=1)
        read_kwargs.update({"sep": delimiter.replace("\t", "\\t"), "encoding": encoding, "header": header_row})
    else:
        try:
            import openpyxl  # noqa
        except Exception:
            st.warning("Pro načtení .xlsx je potřeba modul openpyxl.")
        try:
            xls = pd.ExcelFile(uploaded)
            sheets = xls.sheet_names
            sheet_name = st.sidebar.selectbox("Vyber list v Excelu", sheets, index=0)
        except Exception as e:
            st.sidebar.error(f"Chyba při čtení Excel souboru: {e}")

@st.cache_data(show_spinner=False)
def load_data(file, sheet, kwargs):
    if file.name.lower().endswith(".csv"):
        return pd.read_csv(file, **kwargs)
    else:
        return pd.read_excel(file, sheet_name=sheet)

df = None
if uploaded is not None:
    try:
        df = load_data(uploaded, sheet_name, read_kwargs)
    except Exception as e:
        st.error(f"❌ Nepodařilo se načíst data: {e}")

if df is None:
    st.info("⬆️ Nahraj soubor a začneme.")
    st.stop()

# ----------- Předzpracování -----------
for col in df.columns:
    if df[col].dtype == object:
        try:
            cast_num = pd.to_numeric(df[col].astype(str).str.replace(",", ".", regex=False), errors="coerce")
            if cast_num.notna().mean() > 0.5:
                df[col] = cast_num
                continue
        except Exception:
            pass
        try:
            cast_dt = pd.to_datetime(df[col], errors="coerce")
            if cast_dt.notna().mean() > 0.5:
                df[col] = cast_dt
        except Exception:
            pass

numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
datetime_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
categorical_cols = [c for c in df.columns if (c not in numeric_cols and c not in datetime_cols)]

if not any(df[c].is_unique and df[c].notna().all() for c in df.columns):
    df.insert(0, "Respondent_ID", range(1, len(df) + 1))
    categorical_cols.insert(0, "Respondent_ID")

st.success(f"Soubor **{uploaded.name}** načten. Počet řádků: **{len(df):,}**, sloupců: **{df.shape[1]}**")

# ----------- Filtrování -----------
with st.expander("🔍 Filtrování (volitelné)"):
    filters = {}
    cols_left, cols_right = st.columns(2)
    half = (len(categorical_cols) + 1) // 2
    for i, col in enumerate(categorical_cols):
        vals = sorted([v for v in pd.Series(df[col].dropna().unique()).astype(str)])
        selected = st.multiselect(f"{col}", vals, default=vals)
        filters[col] = selected
    for col, selected in filters.items():
        if selected:
            df = df[df[col].astype(str).isin(selected)]

st.subheader("👀 Náhled dat")
st.dataframe(df.head(100), use_container_width=True)

# ----------- Vizualizace -----------
st.subheader("📈 Distribuce & rozdělení")
left, right = st.columns(2)

with left:
    if numeric_cols:
        num_col = st.selectbox("Numerický sloupec", numeric_cols, key="num_hist")
        safe_hist(df, num_col, title=f"Histogram: {num_col}")
    else:
        st.info("Nenalezen žádný numerický sloupec.")

with right:
    if categorical_cols:
        cat_col = st.selectbox("Kategorický sloupec", categorical_cols, key="cat_counts")
        vc = df[cat_col].astype(str).value_counts().reset_index()
        xname = str(cat_col)
        yname = "Počet hodnot"
        vc.columns = [xname, yname]
        safe_bar(vc, x=xname, y=yname, title=f"{xname} – rozdělení")
    else:
        st.info("Nenalezen žádný kategorický sloupec.")

# ----------- Porovnání -----------
st.subheader("🔗 Porovnání a vztahy")
if numeric_cols and categorical_cols:
    group_num = st.selectbox("Numerický (agregace)", numeric_cols, key="group_num")
    group_cat = st.selectbox("Skupina (kategorie)", categorical_cols, key="group_cat")
    aggfunc = st.selectbox("Agregace", ["mean", "median", "sum", "count"], index=0)
    grouped = getattr(df.groupby(group_cat, dropna=False)[group_num], aggfunc)().reset_index()
    grouped.columns = [str(group_cat), f"{aggfunc}({group_num})"]
    safe_bar(grouped, x=str(group_cat), y=grouped.columns[1], title=f"{aggfunc.upper()} {group_num} podle {group_cat}")
    st.dataframe(grouped, use_container_width=True)
else:
    st.info("Pro porovnání je potřeba alespoň jeden numerický a jeden kategorický sloupec.")

if len(numeric_cols) >= 2:
    st.subheader("📊 Korelace")
    corr = df[numeric_cols].corr(numeric_only=True)
    if PLOTLY:
        try:
            fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns, y=corr.columns, colorbar=dict(title="r")))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(corr, use_container_width=True)
    else:
        st.dataframe(corr, use_container_width=True)
else:
    st.info("Pro korelaci jsou potřeba alespoň dva numerické sloupce.")

st.caption("SAFE verze – ošetřené chyby, bezpečné fallbacky, robustní vykreslování grafů.")
