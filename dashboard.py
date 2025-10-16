
import os, re
import pandas as pd
import streamlit as st
import plotly.express as px

# ------------------ Page config ------------------
st.set_page_config(page_title="Steel Plant Dashboard", layout="wide")
st.title("🌍 Global Steel Plant Dashboard")
st.caption("Data source: dataset_globalsteeltracker.xlsx • sheet: 'Plant data'")

# ------------------ Helpers ------------------
def pick(cols, *keys):
    keys = [k.lower() for k in keys]
    for c in cols:
        if any(k in str(c).lower() for k in keys):
            return c
    return None

def parse_coordinates(series: pd.Series):
    """Parse 'lat, lon' strings into two float columns."""
    pat = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
    lat, lon = [], []
    for v in series.astype(str):
        m = pat.match(v)
        if m:
            lat.append(float(m.group(1))); lon.append(float(m.group(2)))
        else:
            lat.append(None); lon.append(None)
    return pd.Series(lat, name="Latitude"), pd.Series(lon, name="Longitude")

@st.cache_data
def load_data():
    path = "dataset_globalsteeltracker.xlsx"
    if not os.path.exists(path):
        raise FileNotFoundError(" 'dataset_globalsteeltracker.xlsx' not found in this folder.")

    # ---- Read the specified sheet ----
    sheet = "Plant data"
    xls = pd.ExcelFile(path)
    if sheet not in xls.sheet_names:
        raise KeyError(f" Sheet '{sheet}' not found. Available: {xls.sheet_names}")

    df = pd.read_excel(xls, sheet_name=sheet)
    df.columns = df.columns.str.strip()

    # ---- Parse coordinates ----
    coord_col = pick(df.columns, "coordinates")
    if coord_col is None:
        raise KeyError(" Column 'Coordinates' was not found in the 'Plant data' sheet.")
    lat, lon = parse_coordinates(df[coord_col])
    df = df.join([lat, lon]).dropna(subset=["Latitude", "Longitude"])

    # ---- Identify key columns ----
    owner_col  = pick(df.columns, "owner")
    region_col = pick(df.columns, "country/area") or pick(df.columns, "country", "region")

    # ---- Build TotalCapacity by summing any *capacity (ttpa) columns ----
    cap_cols = [c for c in df.columns if str(c).lower().endswith("capacity (ttpa)")]
    if cap_cols:
        for c in cap_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["TotalCapacity"] = df[cap_cols].sum(axis=1, min_count=1)
    else:
        # No capacity columns → create a placeholder so the app still runs
        df["TotalCapacity"] = pd.NA

    # Ensure numeric
    df["Latitude"]  = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    return df, {"owner": owner_col, "region": region_col, "sheet": sheet, "cap_cols": cap_cols}

# ------------------ Load ------------------
try:
    df, meta = load_data()
    st.success(f" Loaded {len(df):,} rows from sheet **{meta['sheet']}**.")
    if not meta["cap_cols"]:
        st.info("ℹ No '*capacity (ttpa)' columns found — bubbles will have uniform size.")
except Exception as e:
    st.error(str(e))
    st.stop()

# ------------------ Sidebar filters ------------------
st.sidebar.header("Filters")
owner_col  = meta["owner"]
region_col = meta["region"]

if owner_col:
    owners = sorted(df[owner_col].dropna().astype(str).unique().tolist())
    sel_owners = st.sidebar.multiselect("Owner", owners, default=owners)
else:
    sel_owners = None

if region_col:
    regions = sorted(df[region_col].dropna().astype(str).unique().tolist())
    sel_regions = st.sidebar.multiselect("Country/Area", regions, default=regions)
else:
    sel_regions = None

if df["TotalCapacity"].notna().any():
    min_cap = int(df["TotalCapacity"].min(skipna=True))
    max_cap = int(df["TotalCapacity"].max(skipna=True))
    cap_range = st.sidebar.slider(
        "Capacity Range (ttpa)",
        min_value=min_cap, max_value=max_cap,
        value=(min_cap, max_cap)
    )
else:
    cap_range = None

# Apply filters
f = df.copy()
if sel_owners and owner_col:
    f = f[f[owner_col].astype(str).isin(sel_owners)]
if sel_regions and region_col:
    f = f[f[region_col].astype(str).isin(sel_regions)]
if cap_range and f["TotalCapacity"].notna().any():
    f = f[f["TotalCapacity"].between(cap_range[0], cap_range[1])]

# ------------------ KPIs ------------------
st.subheader("Key Performance Indicators")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Plants", f"{len(f):,}")
with c2:
    total_cap = f["TotalCapacity"].sum(skipna=True) if f["TotalCapacity"].notna().any() else 0
    st.metric("Total Capacity (ttpa)", f"{total_cap:,.0f}")
with c3:
    avg_cap = f["TotalCapacity"].mean(skipna=True) if f["TotalCapacity"].notna().any() else 0
    st.metric("Average Capacity (ttpa)", f"{avg_cap:,.1f}")

# ------------------ Bar: capacity by owner ------------------
if owner_col and f["TotalCapacity"].notna().any():
    st.subheader("🏭 Capacity by Owner")
    by_owner = (f.groupby(owner_col)["TotalCapacity"]
                  .sum(min_count=1)
                  .reset_index()
                  .sort_values("TotalCapacity", ascending=False))
    st.plotly_chart(
        px.bar(by_owner, x=owner_col, y="TotalCapacity", title="Total Capacity by Owner"),
        use_container_width=True
    )

# ------------------ Map ------------------
st.subheader("Plant Locations")
size_arg = f["TotalCapacity"] if f["TotalCapacity"].notna().any() else None
fig_map = px.scatter_geo(
    f,
    lat="Latitude", lon="Longitude",
    hover_name=pick(f.columns, "plant name", "plant name (english)") or owner_col,
    hover_data={
        (owner_col or "Owner"): True,
        (region_col or "Country/Area"): True,
        "TotalCapacity": ":,.0f" if f["TotalCapacity"].notna().any() else False,
        "Latitude": ":.3f",
        "Longitude": ":.3f",
    },
    size=size_arg,
    projection="natural earth",
    title="Global Steel Plant Locations"
)
st.plotly_chart(fig_map, use_container_width=True)

# ------------------ Table ------------------
st.subheader(" Data Table")
st.dataframe(f, use_container_width=True, height=420)

st.markdown("---")
st.caption("© 2025 Elise Deyris — Data Sources : LitPop, Global Energy Monitor")