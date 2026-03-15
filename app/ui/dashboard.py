"""
Dark Web Scraper Dashboard

Streamlit UI for controlling and monitoring the dark web scraper.
"""

import time
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

# API Configuration
API_BASE_URL = "http://api:8000/api"

# Page config
st.set_page_config(
    page_title="Dark Web Scraper",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for dark/red theme enhancements
st.markdown("""
<style>
    .stApp {
        background-color: #0f0f0f;
    }
    .status-healthy {
        color: #22c55e;
        font-weight: bold;
    }
    .status-unhealthy {
        color: #ef4444;
        font-weight: bold;
    }
    .status-warning {
        color: #f59e0b;
        font-weight: bold;
    }
    .metric-card {
        background-color: #1a1a1a;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #dc2626;
    }
    .job-pending { color: #f59e0b; }
    .job-running { color: #3b82f6; }
    .job-completed { color: #22c55e; }
    .job-failed { color: #ef4444; }
    h1, h2, h3 {
        color: #dc2626 !important;
    }
    .stButton>button {
        background-color: #dc2626;
        color: white;
        border: none;
    }
    .stButton>button:hover {
        background-color: #b91c1c;
    }
</style>
""", unsafe_allow_html=True)


def api_get(endpoint: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Make GET request to API."""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=timeout)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None


def api_post(endpoint: str, data: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Make POST request to API."""
    try:
        response = requests.post(f"{API_BASE_URL}{endpoint}", json=data, timeout=timeout)
        return response.json()
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None


def render_status_indicator(status: bool, label: str) -> str:
    """Render a colored status indicator."""
    if status:
        return f'<span class="status-healthy">● {label}: Online</span>'
    return f'<span class="status-unhealthy">● {label}: Offline</span>'


def render_sidebar_health():
    """Render the sidebar health monitor."""
    st.sidebar.markdown("## 🔒 System Health")
    
    with st.sidebar.container():
        # Fetch health status
        health = api_get("/health")
        anonymity = api_get("/health/anonymity")
        
        if health:
            services = health.get("services", {})

            # Database
            db_ok = services.get("database", {}).get("status") == "healthy"
            st.sidebar.markdown(render_status_indicator(db_ok, "Database"), unsafe_allow_html=True)
            
            # Redis
            redis_ok = services.get("redis", {}).get("status") == "healthy"
            st.sidebar.markdown(render_status_indicator(redis_ok, "Redis"), unsafe_allow_html=True)
            
            # Selenium Grid
            selenium_ok = services.get("selenium_grid", {}).get("status") == "healthy"
            st.sidebar.markdown(render_status_indicator(selenium_ok, "Selenium Grid"), unsafe_allow_html=True)
            
            # Tor Proxy
            tor_ok = services.get("tor_proxy", {}).get("status") == "healthy"
            st.sidebar.markdown(render_status_indicator(tor_ok, "Tor Proxy"), unsafe_allow_html=True)
        else:
            st.sidebar.error("Failed to fetch health status")
        
        st.sidebar.markdown("---")
        
        # Anonymity status
        st.sidebar.markdown("## 🎭 Anonymity Status")
        
        if anonymity:
            is_anonymous = anonymity.get("status") == "anonymous"
            tor_ip = anonymity.get("tor_ip", "Unknown")
            is_tor = anonymity.get("is_tor_exit_node", False)
            
            if is_anonymous:
                st.sidebar.markdown(
                    '<span class="status-healthy">● Anonymous: Yes</span>',
                    unsafe_allow_html=True
                )
            else:
                st.sidebar.markdown(
                    '<span class="status-unhealthy">● Anonymous: No</span>',
                    unsafe_allow_html=True
                )
            
            st.sidebar.markdown(f"**Tor IP:** `{tor_ip}`")
            st.sidebar.markdown(
                render_status_indicator(is_tor, "Tor Exit Node"),
                unsafe_allow_html=True
            )
            
            # Warnings
            warnings = anonymity.get("warnings", [])
            if warnings:
                st.sidebar.markdown("### ⚠️ Warnings")
                for warning in warnings:
                    st.sidebar.warning(warning)
        else:
            st.sidebar.warning("Anonymity check unavailable")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"*Last updated: {datetime.now().strftime('%H:%M:%S')}*")
        
        if st.sidebar.button("🔄 Refresh Status"):
            st.rerun()


def render_scraper_control():
    """Render the scraper control center."""
    st.markdown("## 🎯 Scraper Control Center")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        target_url = st.text_input(
            "Target URL",
            placeholder="http://example.onion or https://example.com",
            help="Enter the URL you want to scrape"
        )
    
    with col2:
        engine = st.selectbox(
            "Scrape Engine",
            options=["auto", "bs4", "selenium"],
            index=0,
            help="Auto: BS4 first, escalates to Selenium if needed"
        )
    
    col3, col4, col5 = st.columns([1, 1, 2])
    
    with col3:
        use_tor = st.checkbox("Use Tor", value=True)
    
    with col4:
        timeout = st.number_input("Timeout (s)", min_value=10, max_value=120, value=30)
    
    with col5:
        st.write("")  # Spacer
    
    if st.button("🚀 Launch Scrape", type="primary", use_container_width=True):
        if not target_url:
            st.error("Please enter a target URL")
        else:
            with st.spinner("Queueing scrape task..."):
                result = api_post("/scraper/scrape", {
                    "url": target_url,
                    "use_tor": use_tor,
                    "timeout": timeout,
                    "force_engine": engine,
                })
                
                if result:
                    st.success(f"✅ Task queued! ID: `{result.get('task_id')}`")
                    st.info(f"Engine: **{result.get('engine', engine)}**")
                else:
                    st.error("Failed to queue scrape task")
    
    st.markdown("---")
    
    # Bulk scrape section
    with st.expander("📦 Bulk Scrape"):
        urls_text = st.text_area(
            "URLs (one per line)",
            placeholder="http://site1.onion\nhttp://site2.onion\nhttp://site3.onion",
            height=150
        )
        
        bulk_engine = st.selectbox(
            "Engine for Bulk",
            options=["auto", "bs4", "selenium"],
            index=0,
            key="bulk_engine"
        )
        
        if st.button("🚀 Launch Bulk Scrape"):
            urls = [u.strip() for u in urls_text.strip().split("\n") if u.strip()]
            if not urls:
                st.error("Please enter at least one URL")
            else:
                with st.spinner(f"Queueing {len(urls)} URLs..."):
                    result = api_post("/scraper/bulk", {
                        "urls": urls,
                        "use_tor": use_tor,
                        "force_engine": bulk_engine,
                    })
                    
                    if result:
                        st.success(f"✅ Bulk task queued! Parent ID: `{result.get('parent_task_id')}`")
                        st.info(f"Total URLs: **{result.get('total_urls')}**")
                    else:
                        st.error("Failed to queue bulk scrape")


def render_job_monitor():
    """Render the job monitor table."""
    st.markdown("## 📊 Job Monitor")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Jobs"):
            st.rerun()
    
    jobs = api_get("/jobs/?limit=10")
    
    if jobs:
        if len(jobs) == 0:
            st.info("No jobs found. Start scraping to see jobs here!")
        else:
            # Create a styled table
            for job in jobs:
                status = job.get("status", "unknown")
                status_class = f"job-{status.lower()}"
                
                with st.container():
                    cols = st.columns([2, 3, 1, 2])
                    
                    with cols[0]:
                        st.markdown(f"**ID:** `{job.get('id', 'N/A')}`")
                    
                    with cols[1]:
                        url = job.get("target_url", "N/A")
                        if len(url) > 50:
                            url = url[:50] + "..."
                        st.markdown(f"**URL:** {url}")
                    
                    with cols[2]:
                        st.markdown(
                            f'<span class="{status_class}">{status.upper()}</span>',
                            unsafe_allow_html=True
                        )
                    
                    with cols[3]:
                        started = job.get("started_at", "N/A")
                        if started and started != "N/A":
                            try:
                                dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                                started = dt.strftime("%m/%d %H:%M")
                            except:
                                pass
                        st.markdown(f"**Started:** {started}")
                    
                    st.markdown("---")
    else:
        st.warning("Failed to fetch jobs")


def render_data_gallery():
    """Render the scraped data gallery."""
    st.markdown("## 📚 Data Gallery")
    
    col1, col2 = st.columns([2, 2])
    
    with col1:
        search_query = st.text_input(
            "Search",
            placeholder="Search by URL, title, or content...",
            key="gallery_search"
        )
    
    with col2:
        if st.button("🔄 Refresh Gallery"):
            st.rerun()
    
    # Fetch scraped sites
    endpoint = "/scraper/results?limit=20"
    if search_query:
        endpoint += f"&search={search_query}"
    
    sites = api_get(endpoint)
    
    if sites:
        if len(sites) == 0:
            st.info("No scraped data yet. Launch a scrape to see results here!")
        else:
            # Stats row
            stats = api_get("/scraper/stats")
            if stats:
                stat_cols = st.columns(4)
                with stat_cols[0]:
                    st.metric("Total Sites", stats.get("total_scraped_sites", 0))
                with stat_cols[1]:
                    jobs_data = stats.get("jobs", {})
                    st.metric("Total Jobs", jobs_data.get("total", 0))
                with stat_cols[2]:
                    st.metric("Completed", jobs_data.get("completed", 0))
                with stat_cols[3]:
                    st.metric("Failed", jobs_data.get("failed", 0))
            
            st.markdown("---")
            
            # Display sites as rich cards
            for idx, site in enumerate(sites):
                with st.container():
                    # Title row
                    title = site.get("title") or "No Title"
                    engine = site.get("engine_used") or "unknown"
                    escalated = site.get("escalated", False)
                    engine_badge = f"🔧 {engine.upper()}"
                    if escalated:
                        engine_badge += " (escalated)"
                    
                    st.markdown(f"### 🌐 {title}")
                    
                    # URL
                    url = site.get("url", "N/A")
                    st.code(url, language=None)
                    
                    # Meta description
                    meta_desc = site.get("meta_description")
                    if meta_desc:
                        st.markdown(f"*{meta_desc}*")
                    
                    # Metrics row
                    m1, m2, m3, m4, m5 = st.columns(5)
                    with m1:
                        status_code = site.get("status_code", "N/A")
                        color = "🟢" if status_code == 200 else "🔴"
                        st.markdown(f"**{color} Status**\n\n`{status_code}`")
                    with m2:
                        st.markdown(f"**⚙️ Engine**\n\n`{engine_badge}`")
                    with m3:
                        content_len = site.get("content_length") or 0
                        if content_len >= 1000:
                            display_len = f"{content_len / 1000:.1f}K"
                        else:
                            display_len = str(content_len)
                        st.markdown(f"**📝 Content**\n\n`{display_len} chars`")
                    with m4:
                        links_count = site.get("links_count") or 0
                        st.markdown(f"**🔗 Links**\n\n`{links_count} found`")
                    with m5:
                        response_ms = site.get("response_time_ms")
                        if response_ms is not None:
                            if response_ms >= 1000:
                                time_str = f"{response_ms / 1000:.1f}s"
                            else:
                                time_str = f"{response_ms}ms"
                        else:
                            time_str = "N/A"
                        st.markdown(f"**⏱️ Speed**\n\n`{time_str}`")
                    
                    # HTML size + timestamp row
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        html_bytes = site.get("html_size_bytes") or 0
                        if html_bytes >= 1024 * 1024:
                            size_str = f"{html_bytes / (1024*1024):.1f} MB"
                        elif html_bytes >= 1024:
                            size_str = f"{html_bytes / 1024:.1f} KB"
                        else:
                            size_str = f"{html_bytes} B"
                        st.markdown(f"**HTML Size:** {size_str}")
                    with info_col2:
                        scraped_at = site.get("scraped_at", "N/A")
                        if scraped_at and scraped_at != "N/A":
                            try:
                                dt = datetime.fromisoformat(str(scraped_at).replace("Z", "+00:00"))
                                scraped_at = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                            except Exception:
                                pass
                        st.markdown(f"**Scraped:** {scraped_at}")
                    
                    # Content preview
                    content = site.get("content") or ""
                    if content:
                        with st.expander("📄 Text Content", expanded=False):
                            st.text(content)
                    
                    # Links found
                    links_json = site.get("links")
                    if links_json:
                        try:
                            import json
                            link_list = json.loads(links_json)
                            if link_list:
                                with st.expander(f"🔗 Discovered Links ({len(link_list)})", expanded=False):
                                    for link in link_list:
                                        is_onion = ".onion" in str(link)
                                        prefix = "🧅" if is_onion else "🔗"
                                        st.markdown(f"- {prefix} `{link}`")
                        except Exception:
                            pass
                    
                    # Raw HTML
                    html_content = site.get("html_content")
                    if html_content:
                        html_col, dl_col = st.columns([5, 1])
                        with html_col:
                            with st.expander("🖥️ Raw HTML", expanded=False):
                                st.code(html_content[:5000], language="html")
                                if len(html_content) > 5000:
                                    st.caption(f"Showing first 5,000 of {len(html_content):,} characters")
                        with dl_col:
                            site_url = site.get("url", "page")
                            safe_name = re.sub(r"[^\w\-.]", "_", site_url.split("//")[-1])[:60]
                            st.download_button(
                                label="⬇️ HTML",
                                data=html_content.encode("utf-8"),
                                file_name=f"{safe_name}.html",
                                mime="text/html",
                                key=f"dl_html_{site.get('id')}",
                                use_container_width=True,
                            )
                    
                    st.markdown("---")
    else:
        st.warning("Failed to fetch scraped sites")


def render_search_section():
    """Render the dark web search section."""
    st.markdown("## 🔍 Dark Web Search")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_query = st.text_input(
            "Search Query",
            placeholder="Enter keywords to search dark web...",
            key="darkweb_search"
        )
    
    with col2:
        max_results = st.number_input(
            "Max Results",
            min_value=10,
            max_value=100,
            value=50,
            key="max_results"
        )
    
    scrape_results = st.checkbox(
        "Auto-scrape discovered URLs",
        value=False,
        help="Automatically queue scrape tasks for found .onion URLs"
    )
    
    if st.button("🔎 Search Dark Web", type="primary"):
        if not search_query:
            st.error("Please enter a search query")
        else:
            with st.spinner("Queueing search task..."):
                result = api_post("/search/", {
                    "query": search_query,
                    "max_results": max_results,
                    "scrape_results": scrape_results,
                })
                
                if result:
                    st.success(f"✅ Search queued! Task ID: `{result.get('task_id')}`")
                else:
                    st.error("Failed to queue search task")
    
    # Show available search engines
    with st.expander("🔧 Available Search Engines"):
        engines = api_get("/search/engines")
        if engines:
            for eng in engines:
                st.markdown(f"- **{eng.get('name')}**")
        else:
            st.info("Failed to load search engines")


def main():
    """Main application."""
    # Header
    st.markdown("# 🕸️ Dark Web Scraper")
    st.markdown("*Professional dark web scraping platform with anonymity protection*")
    st.markdown("---")
    
    # Sidebar
    render_sidebar_health()
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🎯 Scraper",
        "📊 Jobs",
        "📚 Gallery",
        "🔍 Search"
    ])
    
    with tab1:
        render_scraper_control()
    
    with tab2:
        render_job_monitor()
    
    with tab3:
        render_data_gallery()
    
    with tab4:
        render_search_section()
    
    # Footer
    st.markdown("---")
    st.markdown(
        "*Built with FastAPI, Celery, Selenium Grid & Tor | "
        f"Dashboard running on Streamlit*"
    )


if __name__ == "__main__":
    main()
