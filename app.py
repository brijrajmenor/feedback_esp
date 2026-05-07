"""
Feedback Kiosk — Analytics Dashboard
Hardcoded Firebase RTDB + Daily SLA (resets at 12am)
Run: streamlit run feedback_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import io
from datetime import datetime, timedelta, timezone
import numpy as np
import pytz
import firebase_admin
from firebase_admin import credentials, db as rtdb

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Feedback Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Hardcoded Firebase credentials (DO NOT SHARE THIS FILE PUBLICLY) ─────────

DATABASE_URL = "https://feedback-46e20-default-rtdb.firebaseio.com"

# ── Initialize Firebase (only once) ─────────────────────────────────────────
FIREBASE_CONFIG = dict(st.secrets["firebase"])
DATABASE_URL = FIREBASE_CONFIG.pop("database_url")

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(FIREBASE_CONFIG)
    firebase_admin.initialize_app(
        cred,
        {"databaseURL": DATABASE_URL}
    )

# ── Helper functions ─────────────────────────────────────────────────────────
def metric_card(col, label, value, delta=None, delta_type="neu"):
    delta_html = f'<div class="delta delta-{delta_type}">{delta}</div>' if delta else ""
    col.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {delta_html}
    </div>""", unsafe_allow_html=True)

def parse_json(raw: dict) -> pd.DataFrame:
    fb_node = raw.get("feedback", raw)
    rows = []
    for key, val in fb_node.items():
        if isinstance(val, dict) and "feedback" in val:
            ts = val.get("timestamp", 0)
            dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            dt_local = dt_utc.astimezone(pytz.timezone("Asia/Kolkata"))
            rows.append({
                "id": key,
                "feedback": val["feedback"].strip().lower(),
                "timestamp": ts,
                "datetime_utc": dt_utc,
                "datetime": dt_local,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    RATING_ORDER = ["worst", "bad", "avg", "good", "excellent"]
    SCORE_MAP = {"worst": 1, "bad": 2, "avg": 3, "good": 4, "excellent": 5}
    SENTIMENT = {"worst":"negative","bad":"negative","avg":"neutral","good":"positive","excellent":"positive"}
    df["feedback"] = pd.Categorical(df["feedback"], categories=RATING_ORDER, ordered=True)
    df["score"] = df["feedback"].map(SCORE_MAP).astype(float)
    df["sentiment"] = df["feedback"].map(SENTIMENT)
    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.day_name()
    df["week"] = df["datetime"].dt.isocalendar().week.astype(int)
    df["month"] = df["datetime"].dt.strftime("%b %Y")
    df = df.sort_values("datetime").reset_index(drop=True)
    return df

def satisfaction_index(avg_score):
    return ((avg_score - 1) / 4) * 100 if avg_score else 0

def daily_sla_metrics(df):
    if df.empty:
        return pd.DataFrame()
    daily = df.groupby("date").agg(
        count=("score", "size"),
        avg_score=("score", "mean")
    ).reset_index()
    daily["sat_index"] = daily["avg_score"].apply(satisfaction_index)
    return daily

def today_metrics(df):
    today = datetime.now(pytz.timezone("Asia/Kolkata")).date()
    today_df = df[df["date"] == today]
    if today_df.empty:
        return {"count": 0, "avg_score": None, "sat_index": None}
    avg = today_df["score"].mean()
    return {
        "count": len(today_df),
        "avg_score": avg,
        "sat_index": satisfaction_index(avg),
    }

@st.cache_data(ttl=10)
def load_from_firebase():
    try:
        ref = rtdb.reference("/feedback")
        data = ref.get()
        return parse_json({"feedback": data} if data else {})
    except Exception as e:
        st.error(f"Firebase error: {e}")
        return pd.DataFrame()

# ── CSS theme (same as before) ───────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; letter-spacing: -0.02em; }
[data-testid="stSidebar"] { background: #0d1117; border-right: 1px solid #21262d; }
[data-testid="stSidebar"] * { color: #e6edf3 !important; }
.metric-card {
    background: #161b22; border: 1px solid #21262d; border-radius: 12px;
    padding: 20px 24px; margin-bottom: 8px;
}
.metric-card .label {
    font-size: 11px; font-weight: 500; letter-spacing: 0.1em;
    text-transform: uppercase; color: #8b949e; margin-bottom: 6px;
}
.metric-card .value {
    font-family: 'DM Serif Display', serif; font-size: 36px;
    color: #e6edf3; line-height: 1;
}
.metric-card .delta { font-size: 12px; margin-top: 4px; }
.delta-pos { color: #3fb950; }
.delta-neg { color: #f85149; }
.delta-neu { color: #8b949e; }
.section-header {
    font-family: 'DM Serif Display', serif; font-size: 22px;
    color: #e6edf3; margin: 32px 0 16px;
    padding-bottom: 8px; border-bottom: 1px solid #21262d;
}
.insight-box {
    background: #161b22; border-left: 3px solid #f0b429;
    border-radius: 0 8px 8px 0; padding: 12px 16px;
    margin: 8px 0; font-size: 14px; color: #c9d1d9;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📡 Data Source")
    st.markdown("**Live Firebase RTDB** (hardcoded credentials)")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    df = load_from_firebase()
    if not df.empty:
        st.success(f"{len(df):,} records loaded")
        st.markdown("## 🔍 Filters")
        date_min = df["datetime"].min().date()
        date_max = df["datetime"].max().date()
        date_range = st.date_input("Date range", value=(date_min, date_max),
                                   min_value=date_min, max_value=date_max)
        RATING_ORDER = ["worst", "bad", "avg", "good", "excellent"]
        selected_ratings = st.multiselect(
            "Ratings", RATING_ORDER, default=RATING_ORDER,
            format_func=lambda x: x.capitalize()
        )
        selected_sentiment = st.multiselect(
            "Sentiment", ["positive", "neutral", "negative"],
            default=["positive", "neutral", "negative"]
        )
        if len(date_range) == 2:
            df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]
        if selected_ratings:
            df = df[df["feedback"].isin(selected_ratings)]
        if selected_sentiment:
            df = df[df["sentiment"].isin(selected_sentiment)]
        st.markdown(f"**{len(df):,}** responses after filters")
        st.divider()
        st.markdown("## 📥 Export")
        if not df.empty:
            csv_buf = io.StringIO()
            df.drop(columns=["timestamp"]).to_csv(csv_buf, index=False)
            st.download_button("⬇ Download filtered CSV", data=csv_buf.getvalue(),
                               file_name="feedback_export.csv", mime="text/csv",
                               use_container_width=True)
            summary = df.groupby("feedback", observed=True).size().reset_index(name="count")
            summary["pct"] = (summary["count"] / summary["count"].sum() * 100).round(1)
            sum_buf = io.StringIO()
            summary.to_csv(sum_buf, index=False)
            st.download_button("⬇ Download summary CSV", data=sum_buf.getvalue(),
                               file_name="feedback_summary.csv", mime="text/csv",
                               use_container_width=True)
    else:
        st.error("Could not load data from Firebase. Check credentials or internet.")

if df.empty:
    st.stop()

# ── Main Dashboard ───────────────────────────────────────────────────────────
st.markdown("# Feedback Analytics Dashboard")

# ── Today's SLA (resets at midnight local) ───────────────────────────────────
st.markdown('<div class="section-header">📅 Today’s SLA (Resets at 12am)</div>', unsafe_allow_html=True)
today = today_metrics(df)
col_t1, col_t2, col_t3, col_t4 = st.columns(4)
metric_card(col_t1, "Today's Responses", f"{today['count']:,}")
if today['avg_score'] is not None:
    metric_card(col_t2, "Today's Avg Score", f"{today['avg_score']:.2f} / 5")
    metric_card(col_t3, "Today's Satisfaction Index", f"{today['sat_index']:.0f}%",
                delta="Daily target > 70%", delta_type="pos" if today['sat_index'] >= 70 else "neg")
else:
    metric_card(col_t2, "Today's Avg Score", "No data yet")
    metric_card(col_t3, "Today's Satisfaction Index", "—")
now_local = datetime.now(pytz.timezone("Asia/Kolkata"))
midnight = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
hours_left = (midnight - now_local).total_seconds() / 3600
metric_card(col_t4, "Hours until reset", f"{hours_left:.1f}h")

# ── Daily satisfaction trend (last 30 days) ──────────────────────────────────
# ── Daily satisfaction trend (last 30 days) ──────────────────────────────────
daily = daily_sla_metrics(df).sort_values("date")
daily_last30 = daily.tail(30)
if not daily_last30.empty:
    from plotly.subplots import make_subplots   # already imported, but just in case
    fig_daily_sla = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig_daily_sla.add_trace(
        go.Bar(x=daily_last30["date"], y=daily_last30["count"],
               name="Responses", marker_color="#21262d"),
        secondary_y=True
    )
    fig_daily_sla.add_trace(
        go.Scatter(x=daily_last30["date"], y=daily_last30["sat_index"],
                   name="Satisfaction Index (%)",
                   line=dict(color="#f0b429", width=2.5),
                   mode="lines+markers"),
        secondary_y=False
    )
    
    fig_daily_sla.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#8b949e"),
        title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
        title="Daily Satisfaction Index (Last 30 days)",
        height=350,
        margin=dict(t=40, b=20, l=10, r=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#c9d1d9"))
    )
    
    fig_daily_sla.update_yaxes(
        title_text="Satisfaction Index (%)",
        range=[0, 100],
        secondary_y=False,
        gridcolor="#21262d",
        zerolinecolor="#21262d",
        color="#8b949e"
    )
    fig_daily_sla.update_yaxes(
        title_text="Response Count",
        secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
        color="#8b949e"
    )
    
    st.plotly_chart(fig_daily_sla, use_container_width=True)

# ── Overall KPIs ─────────────────────────────────────────────────────────────
total = len(df)
avg_score = df["score"].mean()
pos_pct = (df["sentiment"] == "positive").mean() * 100
mode_rating = df["feedback"].mode()[0] if not df.empty else "—"
sat_index = satisfaction_index(avg_score)

col1, col2, col3, col4, col5 = st.columns(5)
metric_card(col1, "Total Responses", f"{total:,}")
metric_card(col2, "Overall Avg Score", f"{avg_score:.2f} / 5")
metric_card(col3, "Overall Satisfaction Index", f"{sat_index:.0f}%")
metric_card(col4, "Positive Rate", f"{pos_pct:.1f}%")
metric_card(col5, "Most Common", mode_rating.capitalize())

# ── Distribution charts (bar + pie) ──────────────────────────────────────────
st.markdown('<div class="section-header">Rating Distribution</div>', unsafe_allow_html=True)
dist = df.groupby("feedback", observed=True).size().reset_index(name="count")
dist["pct"] = dist["count"] / dist["count"].sum() * 100
RATING_COLORS = {"worst":"#f85149","bad":"#fb8500","avg":"#8b949e","good":"#58a6ff","excellent":"#f0b429"}
dist["color"] = dist["feedback"].map(RATING_COLORS)

col_a, col_b = st.columns([3, 2])
with col_a:
    fig_bar = go.Figure(go.Bar(
        x=dist["feedback"].astype(str), y=dist["count"],
        marker_color=dist["color"],
        text=dist.apply(lambda r: f"{r['count']:,}<br>{r['pct']:.1f}%", axis=1),
        textposition="outside", textfont=dict(size=11, color="#c9d1d9"),
    ))
    fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="DM Sans", color="#8b949e"),
                          title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                          title="Count by Rating", bargap=0.3, height=320)
    fig_bar.update_yaxes(gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e")
    st.plotly_chart(fig_bar, use_container_width=True)
with col_b:
    fig_pie = go.Figure(go.Pie(
        labels=dist["feedback"].astype(str), values=dist["count"],
        marker_colors=dist["color"], hole=0.55, textinfo="percent", textfont=dict(size=12),
    ))
    fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="DM Sans", color="#8b949e"),
                          title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                          title="Share", height=320, showlegend=True)
    st.plotly_chart(fig_pie, use_container_width=True)

# Sentiment breakdown
sent_counts = df["sentiment"].value_counts().reset_index()
sent_counts.columns = ["sentiment", "count"]
sent_colors = {"positive": "#3fb950", "neutral": "#8b949e", "negative": "#f85149"}
col_c, col_d, col_e = st.columns(3)
for _, row in sent_counts.iterrows():
    col = {"positive": col_c, "neutral": col_d, "negative": col_e}.get(row["sentiment"], col_c)
    pct = row["count"] / total * 100
    col.markdown(f"""
    <div class="metric-card" style="border-left:3px solid {sent_colors[row['sentiment']]}">
        <div class="label">{row['sentiment'].upper()}</div>
        <div class="value" style="font-size:28px;color:{sent_colors[row['sentiment']]}">{pct:.1f}%</div>
        <div class="delta delta-neu">{row['count']:,} responses</div>
    </div>""", unsafe_allow_html=True)

# ── Time series (hourly/daily/weekly/monthly) ────────────────────────────────
st.markdown('<div class="section-header">Trends Over Time</div>', unsafe_allow_html=True)
time_grain = st.radio("Granularity", ["Hourly", "Daily", "Weekly", "Monthly"], horizontal=True, index=1)
if time_grain == "Hourly":
    ts = df.set_index("datetime").resample("1h")["score"].agg(["mean", "count"]).reset_index()
    ts.columns = ["period", "avg_score", "count"]
elif time_grain == "Daily":
    ts = df.groupby("date").agg(avg_score=("score","mean"), count=("score","count")).reset_index()
    ts.rename(columns={"date":"period"}, inplace=True)
elif time_grain == "Weekly":
    ts = df.groupby("week").agg(avg_score=("score","mean"), count=("score","count")).reset_index()
    ts.rename(columns={"week":"period"}, inplace=True)
else:
    ts = df.groupby("month").agg(avg_score=("score","mean"), count=("score","count")).reset_index()
    ts.rename(columns={"month":"period"}, inplace=True)

fig_ts = make_subplots(specs=[[{"secondary_y": True}]])
fig_ts.add_trace(go.Bar(x=ts["period"], y=ts["count"], name="Responses", marker_color="#21262d"), secondary_y=True)
fig_ts.add_trace(go.Scatter(x=ts["period"], y=ts["avg_score"], name="Avg Score",
                            line=dict(color="#f0b429", width=2.5), mode="lines+markers"), secondary_y=False)
fig_ts.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                     font=dict(family="DM Sans", color="#8b949e"),
                     title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                     title=f"{time_grain} Volume & Avg Score", height=340)
fig_ts.update_yaxes(title_text="Avg Score", range=[0,5.5], secondary_y=False,
                    gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e")
fig_ts.update_yaxes(title_text="Count", secondary_y=True,
                    gridcolor="rgba(0,0,0,0)", color="#8b949e")
st.plotly_chart(fig_ts, use_container_width=True)

# Stacked area (daily/hourly only)
if time_grain in ["Daily", "Hourly"]:
    if time_grain == "Daily":
        stacked = df.groupby(["date", "feedback"], observed=True).size().reset_index(name="count")
        stacked_pivot = stacked.pivot(index="date", columns="feedback", values="count").fillna(0)
    else:
        df["hour_dt"] = df["datetime"].dt.floor("1h")
        stacked = df.groupby(["hour_dt", "feedback"], observed=True).size().reset_index(name="count")
        stacked_pivot = stacked.pivot(index="hour_dt", columns="feedback", values="count").fillna(0)
    fig_stack = go.Figure()
    for rating in ["worst","bad","avg","good","excellent"]:
        if rating in stacked_pivot.columns:
            fig_stack.add_trace(go.Scatter(
                x=stacked_pivot.index, y=stacked_pivot[rating],
                name=rating.capitalize(), stackgroup="one",
                fillcolor=RATING_COLORS[rating],
                line=dict(color=RATING_COLORS[rating], width=0.5),
            ))
    fig_stack.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="DM Sans", color="#8b949e"),
                            title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                            title="Rating Composition Over Time", height=300)
    fig_stack.update_yaxes(gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e")
    st.plotly_chart(fig_stack, use_container_width=True)

# ── Temporal patterns (hour, weekday, heatmap) ───────────────────────────────
st.markdown('<div class="section-header">Temporal Patterns</div>', unsafe_allow_html=True)
col_f, col_g = st.columns(2)
with col_f:
    hour_data = df.groupby("hour").agg(count=("score","count"), avg_score=("score","mean")).reset_index()
    fig_hour = go.Figure()
    fig_hour.add_trace(go.Bar(x=hour_data["hour"], y=hour_data["count"], marker_color="#21262d", name="Count"))
    fig_hour.add_trace(go.Scatter(x=hour_data["hour"], y=hour_data["avg_score"], mode="lines+markers",
                                  name="Avg Score", line=dict(color="#f0b429", width=2), yaxis="y2"))
    fig_hour.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(family="DM Sans", color="#8b949e"),
                           title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                           title="By Hour of Day", height=300,
                           yaxis2=dict(overlaying="y", side="right", range=[0,5.5], gridcolor="rgba(0,0,0,0)"))
    st.plotly_chart(fig_hour, use_container_width=True)
with col_g:
    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    day_data = df.groupby("weekday").agg(count=("score","count"), avg_score=("score","mean")).reset_index()
    day_data["weekday"] = pd.Categorical(day_data["weekday"], categories=day_order, ordered=True)
    day_data = day_data.sort_values("weekday")
    fig_day = go.Figure()
    fig_day.add_trace(go.Bar(x=day_data["weekday"], y=day_data["count"], marker_color="#21262d", name="Count"))
    fig_day.add_trace(go.Scatter(x=day_data["weekday"], y=day_data["avg_score"], mode="lines+markers",
                                 name="Avg Score", line=dict(color="#58a6ff", width=2), yaxis="y2"))
    fig_day.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="DM Sans", color="#8b949e"),
                          title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                          title="By Day of Week", height=300,
                          yaxis2=dict(overlaying="y", side="right", range=[0,5.5], gridcolor="rgba(0,0,0,0)"))
    st.plotly_chart(fig_day, use_container_width=True)

st.markdown("**Heatmap — Responses by Day & Hour**")
heat = df.groupby(["weekday","hour"]).size().reset_index(name="count")
heat["weekday"] = pd.Categorical(heat["weekday"], categories=day_order, ordered=True)
heat_pivot = heat.pivot(index="weekday", columns="hour", values="count").fillna(0)
fig_heat = px.imshow(heat_pivot, color_continuous_scale=[[0,"#0d1117"],[0.5,"#1f6feb"],[1,"#f0b429"]],
                     labels=dict(x="Hour", y="Day", color="Responses"), aspect="auto")
fig_heat.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       font=dict(family="DM Sans", color="#8b949e"), height=260,
                       margin=dict(t=20, b=20, l=10, r=10))
st.plotly_chart(fig_heat, use_container_width=True)

# ── Score analysis (rolling average, histogram) ──────────────────────────────
st.markdown('<div class="section-header">Score Analysis</div>', unsafe_allow_html=True)
col_h, col_i = st.columns(2)
with col_h:
    daily_score = df.groupby("date")["score"].mean().reset_index()
    daily_score["rolling_7"] = daily_score["score"].rolling(7, min_periods=1).mean()
    fig_roll = go.Figure()
    fig_roll.add_trace(go.Scatter(x=daily_score["date"], y=daily_score["score"],
                                  mode="markers", name="Daily Avg", marker=dict(color="#21262d", size=5)))
    fig_roll.add_trace(go.Scatter(x=daily_score["date"], y=daily_score["rolling_7"],
                                  mode="lines", name="7-day Rolling Avg", line=dict(color="#f0b429", width=2.5)))
    fig_roll.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(family="DM Sans", color="#8b949e"),
                           title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                           title="Daily Score + 7-Day Rolling Avg", height=300)
    fig_roll.update_yaxes(gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e", range=[0,5.5])
    st.plotly_chart(fig_roll, use_container_width=True)
with col_i:
    fig_hist = px.histogram(df, x="score", nbins=5, color_discrete_sequence=["#f0b429"])
    fig_hist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(family="DM Sans", color="#8b949e"),
                           title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                           title="Score Distribution", height=300, bargap=0.1)
    fig_hist.update_yaxes(gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e")
    st.plotly_chart(fig_hist, use_container_width=True)

# ── Response velocity (cumulative, peak hour, busiest day) ───────────────────
st.markdown('<div class="section-header">Response Velocity</div>', unsafe_allow_html=True)
df_sorted = df.sort_values("datetime").copy()
df_sorted["time_since_prev"] = df_sorted["datetime"].diff().dt.total_seconds()
avg_gap = df_sorted["time_since_prev"].median()
col_j, col_k, col_l = st.columns(3)
metric_card(col_j, "Median Gap Between Responses", f"{avg_gap:.0f}s" if pd.notna(avg_gap) else "—")
peak_hour = hour_data.loc[hour_data["count"].idxmax(), "hour"]
metric_card(col_k, "Peak Hour", f"{int(peak_hour):02d}:00")
busiest_day = day_data.loc[day_data["count"].idxmax(), "weekday"]
metric_card(col_l, "Busiest Day", str(busiest_day))

fig_cum = go.Figure(go.Scatter(
    x=df_sorted["datetime"],
    y=list(range(1, len(df_sorted)+1)),
    mode="lines", fill="tozeroy",
    line=dict(color="#3fb950", width=2),
    fillcolor="rgba(63,185,80,0.1)"
))
fig_cum.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="DM Sans", color="#8b949e"),
                      title_font=dict(family="DM Serif Display", color="#e6edf3", size=16),
                      title="Cumulative Responses", height=280)
fig_cum.update_yaxes(gridcolor="#21262d", zerolinecolor="#21262d", color="#8b949e")
st.plotly_chart(fig_cum, use_container_width=True)

# ── Auto insights ────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Auto Insights</div>', unsafe_allow_html=True)
insights = []
top_rating = dist.loc[dist["count"].idxmax()]
insights.append(f"🔴 <b>{top_rating['feedback'].capitalize()}</b> is the most common rating ({top_rating['pct']:.1f}% of all responses).")
if sat_index >= 70:
    insights.append(f"🟢 Overall satisfaction index is <b>{sat_index:.0f}%</b> — strong positive sentiment.")
elif sat_index >= 40:
    insights.append(f"🟡 Overall satisfaction index is <b>{sat_index:.0f}%</b> — mixed sentiment, room to improve.")
else:
    insights.append(f"🔴 Overall satisfaction index is <b>{sat_index:.0f}%</b> — significant negative sentiment.")
if len(daily_score) > 1:
    worst_day = daily_score.loc[daily_score["score"].idxmin(), "date"]
    insights.append(f"📉 Lowest average score day: <b>{worst_day}</b>.")
insights.append(f"⏰ Most feedback submitted at <b>{int(peak_hour):02d}:00</b>.")
exc_pct = dist[dist["feedback"] == "excellent"]["pct"].values
if len(exc_pct):
    insights.append(f"⭐ Excellent responses: <b>{exc_pct[0]:.1f}%</b> of total.")
for ins in insights:
    st.markdown(f'<div class="insight-box">{ins}</div>', unsafe_allow_html=True)

# ── Raw data table ───────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Raw Data</div>', unsafe_allow_html=True)
show_cols = ["datetime", "feedback", "score", "sentiment"]
display_df = df[show_cols].copy()
display_df["datetime"] = display_df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
display_df["feedback"] = display_df["feedback"].astype(str).str.capitalize()
display_df["sentiment"] = display_df["sentiment"].str.capitalize()
st.dataframe(display_df.rename(columns={"datetime":"Timestamp","feedback":"Rating","score":"Score","sentiment":"Sentiment"}),
             use_container_width=True, height=340)
st.caption(f"Showing {len(display_df):,} records · Feedback Kiosk Analytics · Built with 🤍 by Netcreators Automation")
