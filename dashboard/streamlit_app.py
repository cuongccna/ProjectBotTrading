"""
Institutional-Grade Monitoring & Decision Dashboard

Streamlit MVP Frontend for live trading supervision.

PRINCIPLES:
- Read-only: No trading actions from dashboard
- All data from database via API
- Every metric maps to a real module
- Full auditability

Run with:
    streamlit run dashboard/streamlit_app.py
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time

# =============================================================
# CONFIGURATION
# =============================================================

API_BASE_URL = "http://127.0.0.1:8000"
REFRESH_INTERVAL = 5  # seconds

st.set_page_config(
    page_title="Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================
# API HELPERS
# =============================================================

def fetch_api(endpoint: str) -> dict:
    """Fetch data from API endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {e}")
        return None

# =============================================================
# SIDEBAR
# =============================================================

with st.sidebar:
    st.title("⚙️ Dashboard Settings")
    
    # Auto-refresh toggle
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    if auto_refresh:
        refresh_rate = st.slider("Refresh rate (seconds)", 5, 60, 10)
    
    st.divider()
    
    # Manual refresh button
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()
    
    st.divider()
    
    st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    st.caption("📖 Read-only dashboard")
    st.caption("🔒 No trading actions available")

# =============================================================
# HEADER
# =============================================================

st.title("📊 Institutional Trading Dashboard")
st.caption("Operational Control Panel for Live Trading Supervision")

# =============================================================
# PANEL 1: SYSTEM HEALTH
# =============================================================

st.header("1️⃣ System Health Panel")
st.caption("Source: `system_monitoring` table | Module: All")

health_data = fetch_api("/health/system")

if health_data and health_data.get("success"):
    modules = health_data.get("data", [])
    
    if modules:
        cols = st.columns(len(modules) if len(modules) <= 4 else 4)
        
        for i, module in enumerate(modules):
            col_idx = i % 4
            with cols[col_idx]:
                status = module.get("status", "UNKNOWN")
                
                if status == "UP":
                    st.success(f"✅ {module['module_name']}")
                elif status == "DEGRADED":
                    st.warning(f"⚠️ {module['module_name']}")
                else:
                    st.error(f"❌ {module['module_name']}")
                
                st.caption(f"Errors (1h): {module.get('error_count_1h', 0)}")
                
                last_hb = module.get("last_heartbeat")
                if last_hb:
                    st.caption(f"Last: {last_hb[:19]}")
    else:
        st.info("No module health data available yet.")
else:
    st.warning("Could not fetch system health data.")

st.divider()

# =============================================================
# PANEL 2: DATA PIPELINE VISIBILITY
# =============================================================

st.header("2️⃣ Data Pipeline Visibility")
st.caption("Source: `raw_news`, `cleaned_news`, `sentiment_scores`, `onchain_flow_raw` | Window: 24h")

pipeline_data = fetch_api("/pipeline/stats")

if pipeline_data and pipeline_data.get("success"):
    stats = pipeline_data.get("data", [])
    
    if stats:
        cols = st.columns(4)
        
        for i, stat in enumerate(stats):
            col_idx = i % 4
            with cols[col_idx]:
                status = stat.get("status", "UNKNOWN")
                
                if status == "HEALTHY":
                    st.metric(
                        label=f"📦 {stat['metric'].replace('_', ' ').title()}",
                        value=stat.get("count_24h", 0),
                        delta="Healthy"
                    )
                else:
                    st.metric(
                        label=f"⚠️ {stat['metric'].replace('_', ' ').title()}",
                        value=stat.get("count_24h", 0),
                        delta="Stale",
                        delta_color="inverse"
                    )
                
                st.caption(f"Module: `{stat.get('source_module')}`")
    else:
        st.info("No pipeline data available yet.")
else:
    st.warning("Could not fetch pipeline stats.")

st.divider()

# =============================================================
# PANEL 3: RISK STATE PANEL (CRITICAL)
# =============================================================

st.header("3️⃣ Risk State Panel")
st.caption("Source: `risk_state` table | Module: `risk_scoring`")

risk_data = fetch_api("/risk/state")

if risk_data and risk_data.get("success"):
    data = risk_data.get("data", {})
    
    # Main risk metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        risk_level = data.get("risk_level", "unknown").upper()
        risk_score = data.get("global_risk_score", 0)
        
        if risk_level == "LOW":
            st.success(f"🟢 Risk Level: {risk_level}")
        elif risk_level == "MEDIUM":
            st.warning(f"🟡 Risk Level: {risk_level}")
        else:
            st.error(f"🔴 Risk Level: {risk_level}")
        
        st.metric("Global Risk Score", f"{risk_score:.1f}/100")
    
    with col2:
        trading_allowed = data.get("trading_allowed", False)
        if trading_allowed:
            st.success("✅ Trading: ALLOWED")
        else:
            st.error("🚫 Trading: BLOCKED")
            blocked_reason = data.get("blocked_reason")
            if blocked_reason:
                st.caption(f"Reason: {blocked_reason}")
    
    with col3:
        ts = data.get("timestamp", "")
        if ts:
            st.info(f"📅 Last Update: {ts[:19]}")
    
    # Risk Components Breakdown
    st.subheader("Risk Component Breakdown")
    
    components = data.get("components", [])
    if components:
        df = pd.DataFrame(components)
        
        # Display as table with all columns
        st.dataframe(
            df[["name", "raw_score", "normalized_score", "weight", "risk_contribution"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No component data available.")

elif risk_data and not risk_data.get("success"):
    st.info("No risk state recorded yet. Waiting for first pipeline cycle.")
else:
    st.warning("Could not fetch risk state data.")

st.divider()

# =============================================================
# PANEL 4: DECISION TRACE PANEL
# =============================================================

st.header("4️⃣ Decision Trace Panel")
st.caption("Source: `entry_decision` table | Module: `decision_engine`")

decision_data = fetch_api("/decisions/latest?limit=10")

if decision_data and decision_data.get("success"):
    decisions = decision_data.get("data", [])
    
    if decisions:
        for d in decisions[:5]:  # Show last 5
            decision = d.get("decision", "UNKNOWN")
            token = d.get("token", "?")
            reason = d.get("reason_code", "N/A")
            trade_guard = d.get("trade_guard_intervention", False)
            
            with st.container():
                cols = st.columns([1, 2, 2, 1])
                
                with cols[0]:
                    if decision == "ALLOW":
                        st.success(f"✅ {decision}")
                    else:
                        st.error(f"🚫 {decision}")
                
                with cols[1]:
                    st.write(f"**Token:** {token}")
                    direction = d.get("direction", "N/A")
                    st.caption(f"Direction: {direction}")
                
                with cols[2]:
                    st.write(f"**Reason:** `{reason}`")
                    details = d.get("reason_details")
                    if details:
                        st.caption(details[:50])
                
                with cols[3]:
                    if trade_guard:
                        st.warning("🛡️ Guard")
                    else:
                        st.caption("No intervention")
                
                st.divider()
    else:
        st.info("No trade decisions recorded yet.")
else:
    st.warning("Could not fetch decision data.")

st.divider()

# =============================================================
# PANEL 5: POSITION & EXECUTION MONITOR
# =============================================================

st.header("5️⃣ Position & Execution Monitor")
st.caption("Source: `execution_records`, `position_sizing` | Module: `execution`")

position_data = fetch_api("/positions/monitor")

if position_data and position_data.get("success"):
    # Recent Executions
    st.subheader("Recent Executions")
    
    executions = position_data.get("recent_executions", [])
    if executions:
        exec_df = pd.DataFrame(executions)
        
        # Format columns
        display_cols = ["order_id", "token", "side", "status", "executed_size", 
                       "executed_price", "slippage_percent", "latency_ms"]
        available_cols = [c for c in display_cols if c in exec_df.columns]
        
        st.dataframe(exec_df[available_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No recent executions.")
    
    # Position Summary
    st.subheader("Position Sizing (Latest)")
    
    positions = position_data.get("positions", [])
    if positions:
        pos_df = pd.DataFrame(positions)
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("No position data available.")

else:
    st.warning("Could not fetch position data.")

st.divider()

# =============================================================
# PANEL 6: ALERT & INCIDENT PANEL
# =============================================================

st.header("6️⃣ Alert & Incident Panel")
st.caption("Source: `system_monitoring` (severity: warning/error/critical) | Module: Various")

alert_data = fetch_api("/alerts/active?limit=20")

if alert_data and alert_data.get("success"):
    alerts = alert_data.get("data", [])
    
    if alerts:
        # Count by severity
        critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
        warning = sum(1 for a in alerts if a.get("severity") == "WARNING")
        
        cols = st.columns(3)
        with cols[0]:
            st.metric("🔴 Critical", critical)
        with cols[1]:
            st.metric("🟡 Warning", warning)
        with cols[2]:
            st.metric("📋 Total Alerts", len(alerts))
        
        st.subheader("Active Alerts")
        
        for alert in alerts[:10]:
            severity = alert.get("severity", "INFO")
            
            if severity == "CRITICAL":
                st.error(f"🔴 **{alert.get('module')}**: {alert.get('message')}")
            elif severity == "WARNING":
                st.warning(f"🟡 **{alert.get('module')}**: {alert.get('message')}")
            else:
                st.info(f"ℹ️ **{alert.get('module')}**: {alert.get('message')}")
            
            st.caption(f"Time: {alert.get('timestamp', '')[:19]}")
    else:
        st.success("✅ No active alerts!")
else:
    st.warning("Could not fetch alert data.")

st.divider()

# =============================================================
# PANEL 7: HUMAN REVIEW PANEL
# =============================================================

st.header("7️⃣ Human Review Panel")
st.caption("Source: `review_events`, `human_decisions` | Human-in-the-Loop Oversight")

# Fetch review queue
review_data = fetch_api("/review/queue?limit=20")

if review_data:
    total_pending = review_data.get("total_pending", 0)
    total_in_progress = review_data.get("total_in_progress", 0)
    total_resolved = review_data.get("total_resolved", 0)
    avg_resolution = review_data.get("avg_resolution_time_hours")
    
    # Summary metrics
    cols = st.columns(4)
    with cols[0]:
        if total_pending > 0:
            st.error(f"🔴 Pending: {total_pending}")
        else:
            st.success(f"✅ Pending: 0")
    with cols[1]:
        st.info(f"🔵 In Progress: {total_in_progress}")
    with cols[2]:
        st.metric("📋 Resolved", total_resolved)
    with cols[3]:
        if avg_resolution:
            st.metric("⏱️ Avg Resolution", f"{avg_resolution:.1f}h")
        else:
            st.metric("⏱️ Avg Resolution", "N/A")
    
    # Pending reviews list
    events = review_data.get("events", [])
    
    if events:
        st.subheader("📋 Pending Reviews")
        
        for event in events[:10]:
            priority = event.get("priority", "normal")
            trigger_type = event.get("trigger_type", "unknown")
            event_id = event.get("id", "?")
            
            # Priority-based styling
            if priority == "critical":
                st.error(f"🚨 **[#{event_id}] {trigger_type.replace('_', ' ').title()}** - CRITICAL")
            elif priority == "high":
                st.warning(f"🟠 **[#{event_id}] {trigger_type.replace('_', ' ').title()}** - HIGH")
            else:
                st.info(f"🔵 **[#{event_id}] {trigger_type.replace('_', ' ').title()}** - {priority.upper()}")
            
            # Event details
            st.caption(f"Reason: {event.get('trigger_reason', 'N/A')[:100]}")
            
            trigger_val = event.get("trigger_value")
            trigger_thresh = event.get("trigger_threshold")
            if trigger_val is not None:
                thresh_str = f" (threshold: {trigger_thresh})" if trigger_thresh else ""
                st.caption(f"Value: {trigger_val}{thresh_str}")
            
            st.caption(f"Created: {event.get('created_at', '')[:19]}")
            
            # Expandable section for decision form
            with st.expander(f"📝 Review Event #{event_id}"):
                st.write("**Allowed Actions:**")
                st.write("• Adjust risk thresholds (drawdown 5-20%, position limit 1-10%)")
                st.write("• Pause strategy (max 168 hours)")
                st.write("• Enable/disable data sources")
                st.write("• Mark as anomaly")
                st.write("• Reduce position limit")
                
                st.warning("⚠️ **Forbidden Actions:**")
                st.write("• Place trades directly")
                st.write("• Force trade execution")
                st.write("• Override Trade Guard manually")
                st.write("• Modify historical data")
                
                st.info("Use the Review API to submit decisions. See `/review/event/{id}/decision`")
    else:
        st.success("✅ No pending reviews! System is operating normally.")
        
else:
    st.warning("Could not fetch review queue data. Review API may not be available.")

# =============================================================
# FOOTER
# =============================================================

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.caption("📊 Institutional Trading Dashboard v1.0")
with col2:
    st.caption("🔒 Read-only mode | No trading actions")
with col3:
    st.caption(f"⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# =============================================================
# AUTO-REFRESH
# =============================================================

if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
