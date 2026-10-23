import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from cassandra.cluster import Cluster

st.set_page_config(page_title="YouTube Trending Dashboard", page_icon="🎬", layout="wide")
ROSE = ["#FDA4AF", "#FB7185", "#E11D48", "#9F1239"]
COUNTRIES = {"India": "IN", "USA": "US", "Great Britain": "GB", "Canada": "CA"}
LABELS = {"title": "Title", "channel_title": "Channel", "category": "Category", "views": "Views", "likes": "Likes",
          "comment_count": "Comments", "videos": "Trending videos", "total_views": "Total views",
          "countries": "Countries", "country_list": "Country list"}

@st.cache_resource
def connect():
    return Cluster(["127.0.0.1"]).connect("youtube")

@st.cache_data(ttl=600)
def query(cql, params=None):
    return pd.DataFrame(list(connect().execute(cql, params)))

def table(name, code):
    return query(f"SELECT * FROM {name} WHERE country = %s", (code,))

def style(fig, height=420):
    fig.update_layout(height=height, font_family="Poppins", title_font_size=17, coloraxis_showscale=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=20, t=55, b=10))
    return fig

def hbar(df, x, y, title, n=10, fmt=","):
    df = df.nlargest(n, x).sort_values(x)
    fig = px.bar(df, x=x, y=y, orientation="h", title=title, color=x, color_continuous_scale=ROSE)
    fig.update_traces(texttemplate="%{x:" + fmt + "}", textposition="outside", cliponaxis=False)
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    fig.update_xaxes(range=[0, df[x].max() * 1.18], showgrid=False, showticklabels=False)
    return style(fig)

def vbar(df, x, y, title, xlabel):
    fig = px.bar(df, x=x, y=y, title=title, color=y, color_continuous_scale=ROSE)
    fig.update_layout(xaxis_title=xlabel, yaxis_title="Videos")
    return style(fig, 380)

def card(fig):
    with st.container(border=True):
        st.plotly_chart(fig, config={"displayModeBar": False})

def show_table(df):
    nums = {c: st.column_config.NumberColumn(format="localized") for c in ["Views", "Likes", "Comments", "Total views"]}
    st.dataframe(df.rename(columns=LABELS), hide_index=True, column_config=nums)

# Sidebar
st.sidebar.title("Trending Insights")
name = st.sidebar.selectbox("Choose a country", list(COUNTRIES))
code = COUNTRIES[name]
st.sidebar.divider()
st.sidebar.markdown("**How it works**  \n1. PySpark cleans the data  \n2. Cassandra stores data and results  \n3. This dashboard reads Cassandra")
st.sidebar.caption("Data: Kaggle Trending YouTube Video Statistics, Nov 2017 to Jun 2018")

# Data from Cassandra summary tables
cat, ch, eng = table("category_summary", code), table("channel_summary", code), table("engagement_summary", code)
ttt, dur = table("time_to_trend", code), table("trending_duration", code)
up, tags = table("upload_time_summary", code), table("tag_summary", code)

st.markdown(f"""
<div style="background: linear-gradient(120deg, #E11D48 0%, #FB7185 55%, #FDA4AF 100%);
            padding: 26px 32px; border-radius: 18px; color: white; margin-bottom: 20px;">
  <div style="font-size: 2.1rem; font-weight: 700; line-height: 1.2;">YouTube Trending Videos Analysis</div>
  <div style="font-size: 1.05rem; opacity: 0.95; margin-top: 6px;">{name} &nbsp;|&nbsp; Nov 2017 to Jun 2018 &nbsp;|&nbsp; Apache Spark + Cassandra</div>
</div>""", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Trending videos", f"{dur.videos.sum():,}", border=True)
k2.metric("Channels", f"{len(ch):,}", border=True)
k3.metric("Trended within 1 day", f"{ttt[ttt.days <= 1].videos.sum() / ttt.videos.sum():.0%}", border=True)
k4.metric("Avg days on trending", f"{(dur.days_trending * dur.videos).sum() / dur.videos.sum():.1f}", border=True)

t1, t2, t3, t4, t5 = st.tabs(["Categories", "Channels & Tags", "Timing", "Search by date", "Global hits"])

with t1:
    a, b = st.columns(2)
    with a: card(hbar(cat, "videos", "category", "Trending videos by category"))
    with b: card(hbar(eng, "like_pct", "category", "Likes per 100 views", fmt=".2f"))

with t2:
    a, b = st.columns(2)
    with a: card(hbar(ch, "videos", "channel_title", "Top 10 channels"))
    with b: card(hbar(tags, "videos", "tag", "Top 10 tags"))
    search = st.text_input("Search a channel", placeholder="Type a channel name, e.g. zee")
    if search:
        found = ch[ch.channel_title.str.contains(search, case=False, na=False)]
        show_table(found.drop(columns="country").sort_values("videos", ascending=False))

with t3:
    a, b = st.columns(2)
    with a: card(vbar(ttt[ttt.days.between(0, 14)], "days", "videos", "Days from upload to trending", "Days after upload"))
    with b: card(vbar(dur, "days_trending", "videos", "Days a video stays on trending", "Days on trending list"))
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    heat = (up.pivot_table(index="publish_day", columns="publish_hour", values="videos", fill_value=0)
              .reindex(index=days, columns=range(24), fill_value=0))
    fig = px.imshow(heat, color_continuous_scale=["#FFF1F3", "#FECDD6"] + ROSE, aspect="auto",
                    labels=dict(x="Upload hour (UTC). IST = UTC + 5:30", y="", color="Videos"),
                    title="When were trending videos uploaded?")
    card(style(fig, 400))

with t4:
    day = st.date_input("Pick a date", datetime.date(2018, 1, 15),
                        min_value=datetime.date(2017, 11, 14), max_value=datetime.date(2018, 6, 14))
    cql = ("SELECT title, channel_title, category, views, likes, comment_count "
           "FROM trending_by_country WHERE country = %s AND trending_date = %s")
    vids = query(cql, (code, day))
    st.code(cql.replace("%s", "?").replace(" FROM", "\nFROM").replace(" WHERE", "\nWHERE"), language="sql")
    if vids.empty:
        st.info("No data for this date. Try another one.")
    else:
        st.badge(f"{len(vids)} videos were trending in {name} on {day:%d %b %Y}", icon="🎬", color="red")
        show_table(vids.sort_values("views", ascending=False))

with t5:
    glob = query("SELECT title, channel_title, countries, country_list FROM global_videos")
    n = st.slider("Trended in at least this many countries", 2, 4, 4)
    show = glob[glob.countries >= n].sort_values("countries", ascending=False)
    st.badge(f"{len(show)} videos trended in {n} or more countries", icon="🌍", color="red")
    show_table(show)
