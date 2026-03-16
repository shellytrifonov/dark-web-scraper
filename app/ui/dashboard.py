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
                        if url.startswith("search://"):
                            query_term = url[len("search://"):]
                            st.markdown(f"🔍 **Search:** `{query_term}`")
                        else:
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
                    
                    # Entity extraction tags
                    entities = site.get("entities")
                    if entities and entities.get("total_entities", 0) > 0:
                        tag_parts = []
                        wallets = entities.get("crypto_wallets", [])
                        pgp_keys = entities.get("pgp_keys", [])
                        emails = entities.get("emails", [])
                        onion_links = entities.get("onion_links", [])
                        if wallets:
                            tag_parts.append(
                                f'<span style="background:#b8860b;color:#fff;padding:2px 8px;'
                                f'border-radius:12px;font-size:0.8em;margin-right:4px;">'
                                f'💰 {len(wallets)} Crypto Wallet{"s" if len(wallets)!=1 else ""}</span>'
                            )
                        if pgp_keys:
                            tag_parts.append(
                                f'<span style="background:#2e7d32;color:#fff;padding:2px 8px;'
                                f'border-radius:12px;font-size:0.8em;margin-right:4px;">'
                                f'🔑 {len(pgp_keys)} PGP Key{"s" if len(pgp_keys)!=1 else ""}</span>'
                            )
                        if emails:
                            tag_parts.append(
                                f'<span style="background:#1565c0;color:#fff;padding:2px 8px;'
                                f'border-radius:12px;font-size:0.8em;margin-right:4px;">'
                                f'📧 {len(emails)} Email{"s" if len(emails)!=1 else ""}</span>'
                            )
                        if onion_links:
                            tag_parts.append(
                                f'<span style="background:#6a1b9a;color:#fff;padding:2px 8px;'
                                f'border-radius:12px;font-size:0.8em;margin-right:4px;">'
                                f'🧅 {len(onion_links)} Onion Link{"s" if len(onion_links)!=1 else ""}</span>'
                            )
                        if tag_parts:
                            st.markdown(" ".join(tag_parts), unsafe_allow_html=True)

                    # LLM analysis (if available)
                    if entities and entities.get("llm_summary"):
                        # Scam warning banner
                        score = entities.get("llm_legitimacy_score")
                        if score is not None and score < 30:
                            st.markdown(
                                '<div style="background:#c62828;color:#fff;padding:6px 12px;'
                                'border-radius:8px;margin:4px 0;">⚠️ <b>Scam Warning</b> — '
                                f'Legitimacy Score: {score}/100</div>',
                                unsafe_allow_html=True,
                            )
                        with st.expander("🧠 AI Analysis", expanded=False):
                            st.markdown(f"**Summary:** {entities.get('llm_summary')}")
                            cat = entities.get("llm_category")
                            if cat:
                                st.markdown(f"**Category:** `{cat}`")
                            if score is not None:
                                color = "#4caf50" if score >= 60 else "#ff9800" if score >= 30 else "#f44336"
                                st.markdown(
                                    f"**Legitimacy:** <span style='color:{color};font-weight:bold;'>"
                                    f"{score}/100</span>",
                                    unsafe_allow_html=True,
                                )
                                reason = entities.get("llm_legitimacy_reason")
                                if reason:
                                    st.caption(reason)

                    # Entity detail expander (regex results)
                    if entities and entities.get("total_entities", 0) > 0:
                        with st.expander(
                            f"🔍 Extracted Entities ({entities.get('total_entities', 0)})",
                            expanded=False,
                        ):
                            wallets = entities.get("crypto_wallets", [])
                            if wallets:
                                st.markdown("**💰 Crypto Wallets**")
                                for w in wallets:
                                    st.code(f"[{w['type']}] {w['address']}", language=None)
                            pgp_keys = entities.get("pgp_keys", [])
                            if pgp_keys:
                                st.markdown(f"**🔑 PGP Keys ({len(pgp_keys)})**")
                                for i, key in enumerate(pgp_keys):
                                    st.code(key[:300] + ("..." if len(key) > 300 else ""), language=None)
                            emails = entities.get("emails", [])
                            if emails:
                                st.markdown("**📧 Emails**")
                                for e in emails:
                                    st.markdown(f"- `{e}`")
                            onion_links = entities.get("onion_links", [])
                            if onion_links:
                                st.markdown("**🧅 Onion Links Found in Content**")
                                for link in onion_links:
                                    st.markdown(f"- `{link}`")

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

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        scrape_results = st.checkbox(
            "Auto-scrape discovered URLs",
            value=False,
            help="Automatically queue scrape tasks for all found .onion URLs"
        )
    with col_opt2:
        auto_poll = st.checkbox(
            "Wait for results automatically",
            value=True,
            help="Poll until search completes and show results inline"
        )

    if st.button("🔎 Search Dark Web", type="primary"):
        if not search_query.strip():
            st.error("Please enter a search query")
        else:
            with st.spinner("Queueing search task..."):
                result = api_post("/search/", {
                    "query": search_query,
                    "max_results": int(max_results),
                    "scrape_results": scrape_results,
                })
            if result:
                task_id = result.get("task_id")
                st.session_state["search_task_id"] = task_id
                st.session_state["search_query_label"] = search_query
                st.session_state["search_results"] = None
                st.success(f"✅ Search queued — Task ID: `{task_id}`")
                if auto_poll:
                    # Poll up to ~150s (search takes ~80s in practice)
                    poll_placeholder = st.empty()
                    for attempt in range(30):
                        time.sleep(5)
                        poll_placeholder.info(f"⏳ Searching… ({(attempt + 1) * 5}s elapsed)")
                        data = api_get(f"/search/results/{task_id}")
                        if data and data.get("status") == "success":
                            poll_placeholder.empty()
                            st.session_state["search_results"] = data
                            st.rerun()
                            break
                        elif data and data.get("status") == "failure":
                            poll_placeholder.error(f"Search failed: {data.get('error')}")
                            break
                    else:
                        poll_placeholder.warning(
                            "Search is still running. Come back and click "
                            "**'Check Results'** below when it completes (~80-120s total)."
                        )
            else:
                st.error("Failed to queue search task")

    # Manual check button when task is pending in session state
    task_id = st.session_state.get("search_task_id")
    if task_id and not st.session_state.get("search_results"):
        if st.button("🔄 Check Results"):
            data = api_get(f"/search/results/{task_id}")
            if data and data.get("status") == "success":
                st.session_state["search_results"] = data
                st.rerun()
            elif data and data.get("status") == "failure":
                st.error(f"Search failed: {data.get('error')}")
            else:
                st.info(f"Search still {data.get('status', 'pending')}… try again in a few seconds.")

    # Display results
    results_data = st.session_state.get("search_results")
    if results_data:
        query_label = st.session_state.get("search_query_label", "")
        results = results_data.get("results", [])
        total = results_data.get("total_results", len(results))
        scrape_ids = results_data.get("scrape_task_ids", [])

        st.markdown(f"### Results for **'{query_label}'** — {total} URLs found")
        if scrape_ids:
            st.info(f"🕷️ {len(scrape_ids)} scrape tasks auto-queued")

        if results:
            # Group by source engine
            sources = sorted(set(r.get("source", "Unknown") for r in results))
            source_filter = st.multiselect(
                "Filter by search engine",
                options=sources,
                default=sources,
                key="search_source_filter"
            )
            filtered = [r for r in results if r.get("source") in source_filter]

            st.markdown(f"*Showing {len(filtered)} of {total} results*")
            for r in filtered:
                link = r.get("link", "")
                title = r.get("title") or link
                source = r.get("source", "")
                is_onion = ".onion" in link

                badge = "🧅" if is_onion else "🌐"
                with st.container():
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(f"{badge} **{title}**")
                        st.caption(f"`{link}`")
                    with c2:
                        st.caption(f"*{source}*")
                        if st.button("Scrape", key=f"scrape_{hash(link)}"):
                            res = api_post("/scraper/scrape", {
                                "url": link,
                                "use_tor": True,
                                "timeout": 30,
                                "force_engine": "auto",
                            })
                            if res:
                                st.success(f"Queued ✓")
                            else:
                                st.error("Failed")
                st.divider()
        else:
            st.info("No results returned.")

        if st.button("🗑️ Clear Results"):
            st.session_state["search_results"] = None
            st.session_state["search_task_id"] = None
            st.rerun()

    # Show available search engines
    with st.expander("🔧 Available Search Engines"):
        engines = api_get("/search/engines")
        if engines:
            for eng in engines:
                st.markdown(f"- **{eng.get('name')}**")
        else:
            st.info("Failed to load search engines")


def render_monitor_tab():
    """Render the Site Pulse monitoring tab."""
    st.markdown("## 💓 Site Pulse Monitor")

    # --- Add new monitor ---
    with st.expander("➕ Add URL to Monitor", expanded=False):
        mc1, mc2, mc3 = st.columns([4, 1, 1])
        with mc1:
            new_url = st.text_input(
                "URL", placeholder="http://example.onion", key="mon_new_url"
            )
        with mc2:
            new_label = st.text_input("Label (optional)", key="mon_new_label")
        with mc3:
            new_freq = st.number_input(
                "Check every (hours)", min_value=1, max_value=168, value=6, key="mon_new_freq"
            )
        if st.button("🚀 Start Monitoring", type="primary"):
            if not new_url.strip():
                st.error("Enter a URL")
            else:
                res = api_post("/monitor/", {
                    "url": new_url.strip(),
                    "label": new_label.strip() or None,
                    "frequency_hours": int(new_freq),
                })
                if res:
                    st.success(f"✅ Now monitoring `{new_url}`")
                    st.rerun()
                else:
                    st.error("Failed to add monitor (URL may already be tracked)")

    # --- List monitors ---
    monitors = api_get("/monitor/")
    if not monitors:
        st.info("No monitored sites yet. Add one above to get started.")
        return

    # Refresh button
    rc1, rc2 = st.columns([4, 1])
    with rc2:
        if st.button("🔄 Refresh", key="mon_refresh"):
            st.rerun()

    for mon in monitors:
        mon_id = mon.get("id")
        url = mon.get("url", "")
        label = mon.get("label") or url
        is_active = mon.get("is_active", True)
        last_status = mon.get("last_status")
        uptime_pct = mon.get("uptime_pct", 0)
        total_checks = mon.get("total_checks", 0)
        version_count = mon.get("version_count", 0)
        last_change_at = mon.get("last_change_at")
        last_change_summary = mon.get("last_change_summary")
        last_checked = mon.get("last_checked_at")
        freq = mon.get("frequency_hours", 6)

        # Status indicator
        if not is_active:
            status_icon = "⏸️"
            status_color = "#666"
        elif last_status == "up":
            status_icon = "🟢"
            status_color = "#22c55e"
        elif last_status in ("down", "error"):
            status_icon = "🔴"
            status_color = "#ef4444"
        elif last_status == "timeout":
            status_icon = "🟡"
            status_color = "#f59e0b"
        else:
            status_icon = "⚪"
            status_color = "#888"

        # Card container
        with st.container():
            # Header row
            h1, h2, h3, h4 = st.columns([3, 1, 1, 1])
            with h1:
                badge_html = f"{status_icon} **{label}**"
                # Version badge
                if last_change_at:
                    try:
                        change_dt = datetime.fromisoformat(
                            str(last_change_at).replace("Z", "+00:00")
                        )
                        hours_ago = (datetime.utcnow() - change_dt.replace(tzinfo=None)).total_seconds() / 3600
                        if hours_ago < 24:
                            badge_html += (
                                ' <span style="background:#f59e0b;color:#000;padding:2px 8px;'
                                'border-radius:12px;font-size:0.75em;">🆕 New Version</span>'
                            )
                    except Exception:
                        pass
                st.markdown(badge_html, unsafe_allow_html=True)
                st.caption(f"`{url}`")
            with h2:
                # Uptime percentage
                up_color = "#22c55e" if uptime_pct >= 90 else "#f59e0b" if uptime_pct >= 50 else "#ef4444"
                st.markdown(
                    f"**Uptime**\n\n"
                    f"<span style='color:{up_color};font-size:1.3em;font-weight:bold;'>"
                    f"{uptime_pct}%</span>",
                    unsafe_allow_html=True,
                )
            with h3:
                st.markdown(f"**Versions**\n\n`{version_count}`")
            with h4:
                st.markdown(f"**Checks**\n\n`{total_checks}`")

            # Info row
            i1, i2, i3 = st.columns(3)
            with i1:
                checked_str = "Never"
                if last_checked:
                    try:
                        dt = datetime.fromisoformat(str(last_checked).replace("Z", "+00:00"))
                        checked_str = dt.strftime("%m/%d %H:%M UTC")
                    except Exception:
                        checked_str = str(last_checked)
                st.caption(f"Last checked: {checked_str}")
            with i2:
                st.caption(f"Frequency: every {freq}h")
            with i3:
                if last_change_summary:
                    st.caption(f"Last change: {last_change_summary}")

            # Uptime bar (visual timeline from uptime records)
            uptime_records = api_get(f"/monitor/{mon_id}/uptime?hours=168")
            if uptime_records:
                _render_uptime_bar(uptime_records)

            # Action buttons
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("⚡ Check Now", key=f"mon_check_{mon_id}"):
                    res = api_post(f"/monitor/{mon_id}/check", {})
                    if res:
                        st.success(f"Check queued (task: `{res.get('task_id')}`)")
                    else:
                        st.error("Failed to trigger check")
            with a2:
                new_active = not is_active
                btn_label = "▶️ Activate" if not is_active else "⏸️ Pause"
                if st.button(btn_label, key=f"mon_toggle_{mon_id}"):
                    api_patch(f"/monitor/{mon_id}", {"is_active": new_active})
                    st.rerun()
            with a3:
                if st.button("🗑️ Remove", key=f"mon_del_{mon_id}"):
                    api_delete(f"/monitor/{mon_id}")
                    st.rerun()

            st.markdown("---")


def _render_uptime_bar(records):
    """Render a visual uptime bar from uptime records."""
    if not records:
        return

    segments = []
    for rec in records:
        status = rec.get("status", "unknown")
        changed = rec.get("content_changed", False)

        if status == "up":
            color = "#f59e0b" if changed else "#22c55e"
            title_text = "Content changed" if changed else "Up"
        elif status == "timeout":
            color = "#f59e0b"
            title_text = "Timeout"
        elif status in ("down", "error"):
            color = "#ef4444"
            title_text = rec.get("error_message", status).replace('"', "'")[:60]
        else:
            color = "#555"
            title_text = "Unknown"

        checked = rec.get("checked_at", "")
        try:
            dt = datetime.fromisoformat(str(checked).replace("Z", "+00:00"))
            ts = dt.strftime("%m/%d %H:%M")
        except Exception:
            ts = str(checked)

        segments.append(
            f'<div title="{ts}: {title_text}" style="'
            f"display:inline-block;width:{max(4, 100 / len(records)):.1f}%;"
            f'height:18px;background:{color};margin:0;border-radius:2px;"></div>'
        )

    bar_html = (
        '<div style="display:flex;gap:1px;border-radius:6px;overflow:hidden;'
        'margin:4px 0 8px 0;">' + "".join(segments) + "</div>"
    )

    # Legend
    bar_html += (
        '<div style="font-size:0.7em;color:#888;">'
        '<span style="color:#22c55e;">■</span> Up &nbsp;'
        '<span style="color:#f59e0b;">■</span> Changed/Timeout &nbsp;'
        '<span style="color:#ef4444;">■</span> Down/Error'
        "</div>"
    )

    st.markdown(bar_html, unsafe_allow_html=True)


def api_patch(endpoint: str, data: dict) -> Optional[Dict]:
    """Send a PATCH request to the API."""
    try:
        response = requests.patch(f"{API_BASE_URL}{endpoint}", json=data, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def api_delete(endpoint: str) -> bool:
    """Send a DELETE request to the API."""
    try:
        response = requests.delete(f"{API_BASE_URL}{endpoint}", timeout=10)
        return response.status_code == 200
    except Exception:
        return False


def main():
    """Main application."""
    # Header
    st.markdown("# 🕸️ Dark Web Scraper")
    st.markdown("*Professional dark web scraping platform with anonymity protection*")
    st.markdown("---")
    
    # Sidebar
    render_sidebar_health()
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 Scraper",
        "📊 Jobs",
        "📚 Gallery",
        "🔍 Search",
        "💓 Monitor",
    ])
    
    with tab1:
        render_scraper_control()
    
    with tab2:
        render_job_monitor()
    
    with tab3:
        render_data_gallery()
    
    with tab4:
        render_search_section()

    with tab5:
        render_monitor_tab()
    
    # Footer
    st.markdown("---")
    st.markdown(
        "*Built with FastAPI, Celery, Selenium Grid & Tor | "
        f"Dashboard running on Streamlit*"
    )


if __name__ == "__main__":
    main()
