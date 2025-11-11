
import io
import pandas as pd
import numpy as np
import streamlit as st

# Prefer Plotly for interactive charts; fall back to Streamlit's native charts if Plotly isn't available
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except Exception:
    PLOTLY = False

st.set_page_config(page_title="Analýza dotazníku – interaktivní", layout="wide")

st.title("📊 Interaktivní analýza dat (Excel/CSV)")
st.write(
    """
    Nahraj soubor (📄 **.xlsx**, 📄 **.xls**, nebo 📄 **.csv**). Aplikace automaticky načte data,
    umožní ti je filtrovat, dělat přehledy a zobrazovat interaktivní grafy.
    """
)

# ========== SIDEBAR – NAHRÁNÍ A NASTAVENÍ ==========
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
        # Excel
        try:
            import openpyxl  # noqa
        except Exception:
            st.warning("Pro načtení .xlsx je potřeba modul openpyxl (běžně je dostupný).")
        # Zjistit listy
        try:
            xls = pd.ExcelFile(uploaded)
            sheets = xls.sheet_names
            sheet_name = st.sidebar.selectbox("Vyber list v Excelu", sheets, index=0)
        except Exception as e:
            st.sidebar.error(f"Chyba při čtení Excel souboru: {e}")

# ========== NAČTENÍ DAT ==========
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

# ========== PŘEDZPRACOVÁNÍ ==========
# pokus o parsování datových sloupců (datum/čas)
for col in df.columns:
    if df[col].dtype == object:
        # bezpečný pokus převést na číslo nebo datum
        # (bez chyb – hodnoty, které nejdou, zůstanou původní)
        # čísla
        try:
            cast_num = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")
            # jen pokud dává smysl (alespoň 50 % hodnot konvertovatelných)
            if cast_num.notna().mean() > 0.5:
                df[col] = cast_num
                continue
        except Exception:
            pass
        # datumy
        try:
            cast_dt = pd.to_datetime(df[col], errors="coerce")
            if cast_dt.notna().mean() > 0.5:
                df[col] = cast_dt
        except Exception:
            pass

# Rozdělení typů
numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
datetime_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
categorical_cols = [c for c in df.columns if (c not in numeric_cols and c not in datetime_cols)]

st.success(f"Soubor **{uploaded.name}** načten. Počet řádků: **{len(df):,}**, sloupců: **{df.shape[1]}**")

# Možnost vyfiltrovat řádky (globální filtry)
with st.expander("🔍 Filtrování dat (volitelné)"):
    # Dynamicky vytvořit filtry pro kategorické a datumové sloupce
    filters = {}
    cols_left, cols_right = st.columns(2)
    with cols_left:
        for col in categorical_cols[: max(1, len(categorical_cols)//2 + len(categorical_cols)%2)]:
            vals = sorted([v for v in pd.Series(df[col].dropna().unique()).astype(str)])
            selected = st.multiselect(f"{col}", vals, default=vals)
            filters[col] = selected
    with cols_right:
        for col in categorical_cols[max(1, len(categorical_cols)//2 + len(categorical_cols)%2):]:
            vals = sorted([v for v in pd.Series(df[col].dropna().unique()).astype(str)])
            selected = st.multiselect(f"{col}", vals, default=vals)
            filters[col] = selected

    # datumové filtry
    for col in datetime_cols:
        st.markdown(f"**{col}** (interval)")
        min_dt, max_dt = pd.to_datetime(df[col].dropna()).min(), pd.to_datetime(df[col].dropna()).max()
        if pd.isna(min_dt) or pd.isna(max_dt):
            continue
        start, end = st.slider(
            f"Interval pro {col}",
            min_value=min_dt.to_pydatetime(),
            max_value=max_dt.to_pydatetime(),
            value=(min_dt.to_pydatetime(), max_dt.to_pydatetime()),
            format="DD.MM.YYYY"
        )
        df = df[(df[col] >= pd.to_datetime(start)) & (df[col] <= pd.to_datetime(end))]

    # aplikace kategoriálních filtrů
    for col, selected in filters.items():
        if selected:
            df = df[df[col].astype(str).isin(selected)]

# ========== NÁHLED DAT ==========
st.subheader("👀 Náhled dat")
st.dataframe(df.head(100), use_container_width=True)

# ========== ZÁKLADNÍ PŘEHLEDY ==========
st.subheader("🧮 Základní statistiky a kvalita dat")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Počet řádků", f"{len(df):,}")
with c2:
    st.metric("Počet sloupců", f"{df.shape[1]}")
with c3:
    missing_total = int(df.isna().sum().sum())
    st.metric("Chybějící hodnoty (celkem)", f"{missing_total:,}")

# tabulka chybějících hodnot na sloupec
miss = df.isna().mean().sort_values(ascending=False).rename("Podíl NA").to_frame()
st.markdown("**Chybějící hodnoty podle sloupce**")
st.dataframe((miss * 100).round(1), use_container_width=True)

# ========== VIZUALIZACE: DISTRIBUCE ==========
st.subheader("📈 Distribuce & rozdělení")
col_left, col_right = st.columns(2)

with col_left:
    if numeric_cols:
        num_col = st.selectbox("Numerický sloupec", numeric_cols, key="num_hist")
        if PLOTLY:
            fig = px.histogram(df, x=num_col, nbins=30, marginal="box", title=f"Histogram + boxplot: {num_col}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(df[num_col].value_counts().sort_index())
    else:
        st.info("Nenalezen žádný numerický sloupec.")

with col_right:
    if categorical_cols:
        cat_col = st.selectbox("Kategorický sloupec", categorical_cols, key="cat_counts")
        vc = df[cat_col].astype(str).value_counts().reset_index()
        vc.columns = [cat_col, "Počet"]
        if PLOTLY:
            fig = px.bar(vc, x=cat_col, y="Počet", title=f"Počty kategorií: {cat_col}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(vc.set_index(cat_col))
    else:
        st.info("Nenalezen žádný kategorický sloupec.")

# ========== VZTAHY: SKUPINY A KORELACE ==========
st.subheader("🔗 Porovnání a vztahy")
cA, cB = st.columns(2)

with cA:
    if numeric_cols and categorical_cols:
        group_num = st.selectbox("Numerický (agregace)", numeric_cols, key="group_num")
        group_cat = st.selectbox("Skupina (kategorie)", categorical_cols, key="group_cat")
        aggfunc = st.selectbox("Agregace", ["mean", "median", "sum", "count"], index=0)
        grouped = getattr(df.groupby(group_cat)[group_num], aggfunc)().reset_index()
        grouped.columns = [group_cat, f"{aggfunc}({group_num})"]
        if PLOTLY:
            fig = px.bar(grouped, x=group_cat, y=grouped.columns[1],
                         title=f"{aggfunc.upper()} {group_num} podle {group_cat}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(grouped.set_index(group_cat))
        st.dataframe(grouped, use_container_width=True)
    else:
        st.info("Pro porovnání je potřeba alespoň jeden numerický a jeden kategorický sloupec.")

with cB:
    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr(numeric_only=True)
        if PLOTLY:
            fig = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.columns,
                colorbar=dict(title="r"),
                hovertemplate="x=%{x}<br>y=%{y}<br>r=%{z:.2f}<extra></extra>"
            ))
            fig.update_layout(title="Korelační matice", xaxis_nticks=len(corr.columns), yaxis_nticks=len(corr.columns))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(corr, use_container_width=True)
    else:
        st.info("Pro korelaci jsou potřeba alespoň dva numerické sloupce.")

# ========== PIVOT BUILDER ==========
st.subheader("🧭 Kontingenční tabulka (Pivot)")
pivot_cols = st.columns(4)
rows = pivot_cols[0].multiselect("Řádky", df.columns.tolist())
cols = pivot_cols[1].multiselect("Sloupce", df.columns.tolist())
values = pivot_cols[2].multiselect("Hodnoty (numerické)", numeric_cols)
agg = pivot_cols[3].selectbox("Agregace", ["mean", "sum", "median", "count"], index=0)

pivot_df = None
if rows and values:
    try:
        if agg == "count":
            pivot_df = pd.pivot_table(df, index=rows, columns=cols if cols else None, values=values,
                                      aggfunc="count", fill_value=0)
        else:
            pivot_df = pd.pivot_table(df, index=rows, columns=cols if cols else None, values=values,
                                      aggfunc=agg, fill_value=0)
        st.dataframe(pivot_df, use_container_width=True)
        # pokud je jen jedna hodnota, zobrazit i graf
        if PLOTLY and len(values) == 1:
            plot_data = pivot_df.copy()
            plot_data = plot_data.reset_index()
            if cols:
                # rozpad do širokého formátu je již hotový; uděláme stacked bar
                melted = plot_data.melt(id_vars=rows, var_name="Sloupce", value_name=values[0])
                fig = px.bar(melted, x=rows[0], y=values[0], color="Sloupce", barmode="group",
                             title="Pivot – sloupcový graf")
            else:
                fig = px.bar(plot_data, x=rows[0], y=values[0], title="Pivot – sloupcový graf")
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Pivot se nepodařilo vytvořit: {e}")
else:
    st.info("Vyber alespoň **Řádky** a **Hodnoty** pro vytvoření pivotu.")

# ========== EXPORT ==========
st.subheader("💾 Export dat")
colE1, colE2 = st.columns(2)

def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")

with colE1:
    st.download_button(
        "Stáhnout vyfiltrovaná data (CSV)",
        data=to_csv_bytes(df.copy()),
        file_name="data_vyfiltrovana.csv",
        mime="text/csv"
    )

with colE2:
    if pivot_df is not None:
        # pokud má pivot vícero úrovní, plošně ho zploštit
        flat = pivot_df.copy()
        if isinstance(flat.columns, pd.MultiIndex):
            flat.columns = [' | '.join([str(c) for c in col if c is not None]) for col in flat.columns]
        flat = flat.reset_index()
        st.download_button(
            "Stáhnout pivot (CSV)",
            data=to_csv_bytes(flat),
            file_name="pivot.csv",
            mime="text/csv"
        )

st.caption("Vyvinuto pro rychlou analýzu dotazníků a tabulkových dat. Funguje i na mobilu 📱.")
