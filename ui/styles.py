"""Shared CSS for the FinSight dashboard. Theme colours and fonts are in .streamlit/config.toml.

Dark ink page (the portfolio's #060a13) with the particle canvas behind everything,
warm ivory text, glass cards, and lavender / champagne / peach / teal accents. Classes
start "mc-"; Streamlit containers are styled through their keys (st-key-<key>).
Motion: hovers 180 ms, cards 220 ms, page fade 300 ms; all off for reduced motion.
"""

from __future__ import annotations

INK = "#060a13"
IVORY = "#f1ece3"
MUTED = "#a7a094"
LAVENDER = "#c9b6f2"
CHAMPAGNE = "#e9cfa5"
PEACH = "#f2b38b"
TEAL = "#6cc5b8"
GLASS = "rgba(17, 22, 36, .62)"
LINE = "rgba(241, 236, 227, .10)"

CSS = f"""
<style>
html, body {{ background: {INK} !important; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stMain"],
[data-testid="stBottomBlockContainer"] {{ background: transparent !important; }}
[data-testid="stHeader"] {{ height: 0; }}
.block-container {{ padding-top: 1.6rem; max-width: 1320px; }}
.st-key-finsight-bg, .st-key-finsight-labels, .st-key-finsight-scroll {{ display: none; }}

/* Sidebar: glass over the particles. */
[data-testid="stSidebar"] {{ background: rgba(8, 12, 22, .72) !important; border-right: 1px solid {LINE};
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); }}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{
  [data-testid="stSidebar"] {{ background: rgba(8, 12, 22, .96) !important; }}
}}
[class*="st-key-nav-"] button {{ justify-content: flex-start; width: 100%; padding: .65rem .9rem; border-radius: 14px;
  color: #d9d3c8; border: 1px solid transparent; background: transparent;
  transition: background-color .18s ease, border-color .18s ease, color .18s ease; }}
[class*="st-key-nav-"] button > div {{ justify-content: flex-start; width: 100%; }}
[class*="st-key-nav-"] button:hover {{ background: rgba(241, 236, 227, .06); color: {IVORY}; border-color: {LINE}; }}
[class*="st-key-nav-"] button[kind="primary"], [class*="st-key-nav-"] [data-testid="stBaseButton-primary"] {{
  background: rgba(201, 182, 242, .14) !important; border-color: rgba(201, 182, 242, .30) !important;
  color: {IVORY} !important; box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06); }}

/* Glass surfaces. */
.mc-glass, [class*="st-key-panel-"], [class*="st-key-card-"], [class*="st-key-feed-"],
[class*="st-key-call-"], [class*="st-key-kpi-"] {{
  background: {GLASS}; border: 1px solid {LINE}; border-radius: 18px;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .25), inset 0 1px 0 rgba(255, 255, 255, .04); }}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{
  .mc-glass, [class*="st-key-panel-"], [class*="st-key-card-"], [class*="st-key-feed-"],
[class*="st-key-call-"], [class*="st-key-kpi-"] {{
    background: rgba(14, 19, 32, .94); }}
}}
[class*="st-key-panel-"], [class*="st-key-card-"] {{ padding: 1.1rem 1.25rem; }}
[class*="st-key-card-"] {{ transition: border-color .22s ease, box-shadow .22s ease; }}
[class*="st-key-card-"]:hover {{ border-color: rgba(201, 182, 242, .28); }}

/* Clickable cards: a transparent full-size button sits over the card's HTML. */
[class*="st-key-kpi-"], [class*="st-key-feed-"], [class*="st-key-call-"] {{ position: relative; gap: 0; padding: 0;
  transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease, background-color .22s ease; }}
[class*="st-key-kpi-"]:hover, [class*="st-key-kpi-"]:focus-within {{ transform: translateY(-2px);
  border-color: rgba(233, 207, 165, .38); box-shadow: 0 14px 36px rgba(0, 0, 0, .35), 0 0 0 1px rgba(233, 207, 165, .12),
  0 0 28px rgba(233, 207, 165, .08); }}
[class*="st-key-feed-"], [class*="st-key-call-"] {{ border-radius: 14px; margin-bottom: .1rem; }}
[class*="st-key-feed-"]:hover, [class*="st-key-feed-"]:focus-within, [class*="st-key-call-"]:hover,
[class*="st-key-call-"]:focus-within {{ background: rgba(28, 34, 52, .72);
  border-color: rgba(201, 182, 242, .30); }}
[class*="st-key-open-kpi-"], [class*="st-key-open-feed-"], [class*="st-key-open-call-"] {{ position: absolute !important; inset: 0; z-index: 2; }}
[class*="st-key-open-"] [data-testid="stButton"], [class*="st-key-open-"] [data-testid="stButton"] > div,
[class*="st-key-open-"] [data-testid="stTooltipIcon"], [class*="st-key-open-"] [data-testid="stTooltipHoverTarget"],
[class*="st-key-open-"] button {{ position: static; width: 100% !important; height: 100% !important; }}
[class*="st-key-open-"] button {{ opacity: 0; cursor: pointer; border: 0; }}
[class*="st-key-open-"] button:focus-visible {{ opacity: 1; background: transparent !important;
  outline: 2px solid {CHAMPAGNE}; outline-offset: -2px; border-radius: 18px; }}
[class*="st-key-open-"] button:focus-visible * {{ visibility: hidden; }}

/* Page fade on page change only: each page's container has its own key. */
[class*="st-key-page-"] {{ animation: mc-fade .3s ease both; }}
@keyframes mc-fade {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}

/* Brand, greeting. */
.mc-brand {{ display: flex; align-items: center; gap: .8rem; margin: .2rem 0 1.4rem .2rem; }}
.mc-brand svg {{ flex: none; }}
.mc-brand-name {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 1.55rem; letter-spacing: .14em;
  color: {IVORY}; line-height: 1; }}
.mc-brand-sub {{ font-size: .66rem; letter-spacing: .22em; text-transform: uppercase; color: {MUTED}; margin-top: .3rem; }}
.mc-greeting h1 {{ font-family: "Cormorant Garamond", Georgia, serif; font-weight: 500; font-size: clamp(2rem, 3.4vw, 2.9rem);
  color: {IVORY}; margin: 0; padding: 0; line-height: 1.1; }}
.mc-greeting p {{ color: #c9c2b6; font-size: 1.02rem; margin: .45rem 0 0; }}
.mc-page-title {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 2.2rem; color: {IVORY}; margin: 0; }}
.mc-page-sub {{ color: {MUTED}; margin: .2rem 0 1rem; }}

/* KPI cards. */
.mc-stat {{ display: flex; gap: 1.1rem; align-items: center; padding: 1.25rem 1.4rem; min-height: 8.2rem; }}
.mc-stat-icon {{ flex: none; width: 3.3rem; height: 3.3rem; border-radius: 50%; display: grid; place-items: center; }}
.mc-stat-value {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 2.6rem; line-height: 1; color: {IVORY}; }}
.mc-stat-label {{ font-size: 1.05rem; color: #ddd6ca; margin-top: .25rem; }}
.mc-stat-note {{ font-size: .8rem; color: {MUTED}; margin-top: .35rem; }}
.mc-icon-lavender {{ background: rgba(201, 182, 242, .14); color: {LAVENDER}; }}
.mc-icon-peach {{ background: rgba(242, 179, 139, .14); color: {PEACH}; }}
.mc-icon-teal {{ background: rgba(108, 197, 184, .14); color: {TEAL}; }}

/* Panels. */
.mc-panel-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: .6rem; }}
.mc-panel-title {{ font-size: 1.08rem; font-weight: 600; color: {IVORY}; }}
.mc-legend {{ display: grid; grid-template-columns: auto 1fr auto; gap: .45rem .6rem; align-items: center;
  font-size: .86rem; color: #ddd6ca; margin-top: .4rem; }}
.mc-legend-dot {{ width: .6rem; height: .6rem; border-radius: 50%; display: inline-block; }}
.mc-filter-chip {{ font-size: .78rem; color: {CHAMPAGNE}; }}

/* Feed items. */
.mc-feed {{ display: flex; gap: .8rem; padding: .75rem .85rem; }}
.mc-feed-icon {{ flex: none; width: 2.4rem; height: 2.4rem; border-radius: 50%; display: grid; place-items: center; }}
.mc-feed-main {{ flex: 1; min-width: 0; }}
.mc-feed-top {{ display: flex; flex-direction: column; gap: .05rem; }}
.mc-feed-title {{ font-weight: 600; color: {IVORY}; font-size: .93rem; }}
.mc-feed-when {{ font-size: .74rem; color: {CHAMPAGNE}; }}
.mc-feed-sub {{ font-size: .82rem; color: #c9c2b6; margin-top: .1rem; }}
.mc-preview {{ max-height: 0; overflow: hidden; opacity: 0; font-size: .78rem; color: #c9c2b6;
  transition: max-height .22s ease, opacity .18s ease, margin .22s ease; }}
[class*="st-key-feed-"]:hover .mc-preview, [class*="st-key-feed-"]:focus-within .mc-preview,
[class*="st-key-call-"]:hover .mc-preview, [class*="st-key-call-"]:focus-within .mc-preview {{
  max-height: 22rem; opacity: 1; margin-top: .5rem; }}
.mc-preview a {{ position: relative; z-index: 3; }}
.mc-preview dl {{ display: grid; grid-template-columns: auto 1fr; gap: .2rem .7rem; margin: 0; }}
.mc-preview dt {{ color: {MUTED}; }}
.mc-preview dd {{ margin: 0; }}

/* Shared pieces from ui/components.py, dark versions. */
.mc-panel {{ margin-bottom: 1rem; padding: 1.2rem 1.4rem; }}
.mc-event-title {{ display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }}
.mc-event-title h1 {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 2rem; font-weight: 500; margin: 0;
  padding: 0; color: {IVORY}; }}
.mc-meta {{ display: flex; flex-wrap: wrap; gap: 1.2rem 2.4rem; margin-top: .9rem; }}
.mc-label {{ font-size: .68rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: {MUTED};
  margin-bottom: .2rem; }}
.mc-value {{ font-size: .95rem; color: {IVORY}; }}
.mc-docs a {{ margin-right: .9rem; white-space: nowrap; }}
.mc-kpi {{ padding: .9rem 1.1rem; height: 100%; }}
.mc-kpi-value {{ font-size: 1.35rem; font-weight: 600; color: {IVORY}; font-variant-numeric: tabular-nums; line-height: 1.3; }}
.mc-kpi-sub {{ font-size: .8rem; color: {MUTED}; margin-top: .25rem; }}
.mc-card-head {{ display: flex; justify-content: space-between; gap: 1.5rem; align-items: flex-start; flex-wrap: wrap; }}
.mc-who {{ display: flex; gap: .9rem; align-items: baseline; min-width: 0; flex: 1 1 22rem; }}
.mc-rank {{ font-size: .85rem; font-weight: 600; color: {MUTED}; min-width: 1.8rem; }}
.mc-name {{ font-size: 1.06rem; font-weight: 600; color: {IVORY}; margin-right: .5rem; }}
.mc-why {{ font-size: .88rem; color: #c9c2b6; margin-top: .3rem; }}
.mc-amount {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 1.55rem; font-weight: 600; color: {IVORY};
  text-align: right; max-width: 26rem; line-height: 1.2; }}
.mc-card-foot {{ display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: .7rem; }}
.mc-timing-words {{ font-size: .82rem; color: #c9c2b6; }}
.mc-badge {{ display: inline-block; padding: .12rem .6rem; border-radius: 999px; font-size: .74rem; font-weight: 500;
  border: 1px solid transparent; white-space: nowrap; vertical-align: middle; }}
.mc-tone-accent {{ background: rgba(201, 182, 242, .14); color: {LAVENDER}; border-color: rgba(201, 182, 242, .32); }}
.mc-tone-neutral {{ background: rgba(241, 236, 227, .06); color: #ddd6ca; border-color: {LINE}; }}
.mc-tone-green {{ background: rgba(52, 211, 153, .12); color: #7ee2b8; border-color: rgba(52, 211, 153, .32); }}
.mc-tone-amber {{ background: rgba(233, 207, 165, .12); color: {CHAMPAGNE}; border-color: rgba(233, 207, 165, .34); }}
.mc-tone-grey {{ background: rgba(148, 163, 184, .10); color: #c3cad6; border-color: rgba(148, 163, 184, .28); }}
.mc-tone-red-outline {{ background: transparent; color: #fca5a5; border-color: rgba(248, 113, 113, .6); }}
.mc-unknown {{ color: #8d877d; font-style: italic; border-bottom: 1px dotted #8d877d; cursor: help; }}
.mc-chip {{ display: inline-block; font-size: .74rem; padding: .05rem .5rem; margin: .15rem .3rem .15rem 0;
  border: 1px solid rgba(201, 182, 242, .30); border-radius: 8px; color: {LAVENDER} !important;
  background: rgba(201, 182, 242, .06); text-decoration: none !important; white-space: nowrap;
  transition: background-color .18s ease; }}
.mc-chip:hover {{ background: rgba(201, 182, 242, .16); }}
.mc-brief {{ border-left: 2px solid {CHAMPAGNE}; background: rgba(233, 207, 165, .05); padding: .7rem 1rem;
  border-radius: 0 12px 12px 0; margin: 0 0 .4rem 0; }}
.mc-brief p {{ margin: .15rem 0; font-size: .93rem; color: {IVORY}; }}
.mc-section {{ font-size: .68rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: {MUTED};
  margin: 1rem 0 .35rem; }}
.mc-item {{ font-size: .9rem; color: {IVORY}; margin: .2rem 0 .5rem; }}
.mc-working {{ font-size: .84rem; color: #c9c2b6; font-variant-numeric: tabular-nums; }}
.mc-note {{ font-size: .82rem; color: {MUTED}; }}
.mc-quote {{ font-size: .8rem; color: #c9c2b6; font-style: italic; }}
.mc-list {{ margin: .2rem 0 .4rem 1.1rem; padding: 0; font-size: .86rem; color: #ddd6ca; }}
.mc-flag {{ background: rgba(233, 207, 165, .08); border: 1px solid rgba(233, 207, 165, .3); color: {CHAMPAGNE};
  border-radius: 10px; padding: .4rem .7rem; font-size: .85rem; }}
.mc-status {{ display: flex; gap: .6rem; align-items: baseline; font-size: .88rem; margin: .3rem 0; color: {IVORY}; }}
.mc-dot {{ flex: none; width: .55rem; height: .55rem; border-radius: 50%; display: inline-block; }}
.mc-dot-green {{ background: #34d399; }} .mc-dot-amber {{ background: {CHAMPAGNE}; }}
.mc-dot-red {{ background: #f87171; }} .mc-dot-grey {{ background: #94a3b8; }}
.mc-step {{ font-size: .88rem; font-variant-numeric: tabular-nums; margin: .15rem 0; }}
.mc-note-item {{ padding: .55rem 0; border-bottom: 1px solid {LINE}; }}
.mc-note-item:last-child {{ border-bottom: 0; }}
.mc-note-title {{ font-size: .88rem; color: {IVORY}; }}
.mc-note-detail {{ font-size: .78rem; color: {MUTED}; margin-top: .15rem; }}
a {{ color: {CHAMPAGNE}; }}

/* Streamlit widgets on dark glass. */
[data-testid="stExpander"] details {{ background: rgba(255, 255, 255, .02); border-color: {LINE}; border-radius: 12px; }}
[data-testid="stPopoverButton"], [data-testid="stPopover"] button {{ border-radius: 999px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: .3rem; }}


/* Today's calls rows. */
.mc-call-rank {{ flex: none; width: 2rem; height: 2rem; border-radius: 50%; display: grid; place-items: center;
  font-family: "Cormorant Garamond", Georgia, serif; font-size: 1.15rem; color: {CHAMPAGNE};
  border: 1px solid rgba(233, 207, 165, .35); }}
.mc-call-top {{ display: flex; flex-wrap: wrap; gap: .1rem .6rem; align-items: baseline; }}
.mc-call-company {{ font-size: .78rem; color: {MUTED}; }}
.mc-call-amount {{ font-family: "Cormorant Garamond", Georgia, serif; font-size: 1.2rem; color: {IVORY}; margin-top: .1rem; }}

/* Chart heads, pills, chips, breadcrumb. */
.mc-chart-head {{ margin-bottom: .2rem; }}
.mc-chart-sub {{ font-size: .8rem; color: {MUTED}; margin-top: .15rem; line-height: 1.35; }}
[class*="st-key-pill-"] {{ align-items: flex-end; }}
[class*="st-key-pill-"] [data-testid="stButtonGroup"] {{ justify-content: flex-end; flex-wrap: nowrap; }}
[class*="st-key-pill-"] [data-testid="stButtonGroup"] > div {{ flex-wrap: nowrap; }}
[class*="st-key-pill-"] button {{ font-size: .74rem !important; padding: .1rem .6rem !important; min-height: 1.7rem !important;
  border-radius: 999px !important; }}
.mc-pills {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .4rem; }}
.mc-chip-primary {{ background: rgba(201, 182, 242, .18); border-color: rgba(201, 182, 242, .55); font-weight: 600; }}
[class*="st-key-chips-"] {{ gap: .4rem; flex-wrap: wrap; }}
[class*="st-key-chip-"] button {{ border-radius: 999px; font-size: .78rem; padding: .1rem .75rem; min-height: 1.8rem;
  background: rgba(201, 182, 242, .10); border: 1px solid rgba(201, 182, 242, .35); color: {LAVENDER}; }}
[class*="st-key-chip-"] button:hover {{ background: rgba(201, 182, 242, .2); }}
.st-key-crumbs {{ gap: .35rem; margin-top: .3rem; }}
.st-key-crumbs button {{ padding: 0 .1rem; min-height: 0; font-size: .82rem; color: {MUTED}; }}
.st-key-crumbs button:hover {{ color: {CHAMPAGNE}; }}
.mc-crumb-sep {{ color: #6f6a62; font-size: .82rem; }}
.mc-crumb-here {{ font-size: .82rem; color: {CHAMPAGNE}; }}

/* Prospects: the filter bar stays on screen while the cards scroll. Streamlit wraps each
   keyed container in its own layout wrapper, so the wrapper is what sticks. */
[data-testid="stLayoutWrapper"]:has(> .st-key-filterbar) {{ position: sticky; top: .4rem; z-index: 30; }}
.st-key-filterbar {{ background: rgba(8, 12, 22, .97);
  border: 1px solid {LINE}; border-radius: 16px; padding: .5rem 1rem .7rem;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{
  .st-key-filterbar {{ background: rgba(8, 12, 22, .98); }}
}}

/* Primary buttons: dark text on the lavender fill (white on lavender is 1.8:1; this is over 10:1). */
[data-testid="stBaseButton-primary"]:not([class*="st-key-nav-"] *), a[kind="primary"],
[data-testid="stBaseButton-primary"] *:not(svg), a[kind="primary"] * {{ color: {INK} !important; }}
[class*="st-key-nav-"] [data-testid="stBaseButton-primary"], [class*="st-key-nav-"] [data-testid="stBaseButton-primary"] * {{
  color: {IVORY} !important; }}

/* Keyboard focus: a visible ring on every button, link, chip, card control, expander and toggle. */
button:focus-visible, a:focus-visible, summary:focus-visible, [role="option"]:focus-visible,
[tabindex]:focus-visible, input:focus-visible, textarea:focus-visible {{
  outline: 2px solid {CHAMPAGNE} !important; outline-offset: 2px !important; }}
label:has(input[type="checkbox"]:focus-visible), label:has(input[role="switch"]:focus-visible) {{
  outline: 2px solid {CHAMPAGNE}; outline-offset: 3px; border-radius: 8px; }}
[data-baseweb="select"]:focus-within {{ outline: 2px solid {CHAMPAGNE}; outline-offset: 2px; border-radius: 12px; }}
[data-testid="stBidiComponentIsolated"]:focus-visible, [data-testid="stBidiComponentIsolated"]:focus {{
  outline: 2px solid {CHAMPAGNE} !important; outline-offset: 2px; border-radius: 14px; }}

@media (max-width: 640px) {{
  [data-testid="stLayoutWrapper"]:has(> .st-key-filterbar) {{ position: static; }}
  .mc-amount {{ text-align: left; }}
  .mc-stat {{ min-height: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ transition: none !important; animation: none !important; }}
}}
</style>
"""


def page_css() -> str:
    """The <style> block, injected once per page with st.markdown(unsafe_allow_html=True)."""
    return CSS
