from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database import get_connection, get_dashboard_stats

# Page configuration with custom theme
st.set_page_config(page_title="AP AI Automation Dashboard", page_icon="🧾", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for enhanced styling
st.markdown("""
<style>
    /* Main background */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    
    /* Status badges */
    .status-match {
        background: #10b981;
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    .status-discrepancy {
        background: #ef4444;
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    .status-pending {
        background: #f59e0b;
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    
    /* Header styling */
    .main-header {
        background: white;
        padding: 30px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin-bottom: 30px;
    }
    
    /* Section headers */
    .section-header {
        background: white;
        padding: 15px 20px;
        border-radius: 10px;
        margin: 20px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# Header Section
st.markdown("""
<div class="main-header">
    <h1 style='margin: 0; color: #2d3748; font-size: 2.5em;'>🧾 AP AI Automation Dashboard</h1>
    <p style='margin: 10px 0 0 0; color: #718096; font-size: 1.1em;'>Intelligent 3-Way/4-Way Invoice Matching for Accounts Payable</p>
    <p style='margin: 5px 0 0 0; color: #a0aec0; font-size: 0.9em;'>Last Updated: """ + datetime.now().strftime("%B %d, %Y at %I:%M %p") + """</p>
</div>
""", unsafe_allow_html=True)

# Fetch Dashboard Stats
stats = get_dashboard_stats()

# Calculate percentages
total = stats['total_invoices']
matched_pct = (stats['matched'] / total * 100) if total > 0 else 0
discrepancy_pct = (stats['discrepancy'] / total * 100) if total > 0 else 0
pending_pct = (stats['pending'] / total * 100) if total > 0 else 0

# KPI Cards with Enhanced Design
st.markdown("### 📊 Key Performance Indicators", unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div style='font-size: 0.9em; color: #718096; margin-bottom: 10px;'>📄 Total Invoices</div>
        <div style='font-size: 2.5em; font-weight: bold; color: #2d3748;'>{stats['total_invoices']}</div>
        <div style='font-size: 0.85em; color: #a0aec0; margin-top: 5px;'>All processed invoices</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div style='font-size: 0.9em; color: #718096; margin-bottom: 10px;'>✅ Matched</div>
        <div style='font-size: 2.5em; font-weight: bold; color: #10b981;'>{stats['matched']}</div>
        <div style='font-size: 0.85em; color: #10b981; margin-top: 5px;'>{matched_pct:.1f}% success rate</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div style='font-size: 0.9em; color: #718096; margin-bottom: 10px;'>⚠️ Discrepancy</div>
        <div style='font-size: 2.5em; font-weight: bold; color: #ef4444;'>{stats['discrepancy']}</div>
        <div style='font-size: 0.85em; color: #ef4444; margin-top: 5px;'>{discrepancy_pct:.1f}% need review</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div style='font-size: 0.9em; color: #718096; margin-bottom: 10px;'>⏳ Pending Info</div>
        <div style='font-size: 2.5em; font-weight: bold; color: #f59e0b;'>{stats['pending']}</div>
        <div style='font-size: 0.85em; color: #f59e0b; margin-top: 5px;'>{pending_pct:.1f}% awaiting docs</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)

# Two Column Layout for Charts and Table
col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown("""
    <div class="section-header">
        <h3 style='margin: 0; color: #2d3748;'>📊 Top Discrepancy Reasons</h3>
    </div>
    """, unsafe_allow_html=True)

    if stats['top_reasons']:
        df_reasons = pd.DataFrame(stats['top_reasons'])

        # Create enhanced bar chart with Plotly
        fig = px.bar(
            df_reasons,
            x='count',
            y='reason',
            orientation='h',
            color='count',
            color_continuous_scale='Reds',
            text='count'
        )

        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis_title='Number of Occurrences',
            yaxis_title='',
            showlegend=False,
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
            yaxis=dict(showgrid=False)
        )

        fig.update_traces(
            textposition='outside',
            textfont=dict(color='#2d3748', size=11, weight='bold'),
            hovertemplate='<b>%{y}</b><br>Count: %{x}<extra></extra>'
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("🎉 No discrepancies found! All invoices matched perfectly.")

with col_right:
    st.markdown("""
    <div class="section-header">
        <h3 style='margin: 0; color: #2d3748;'> Invoice Processing Log</h3>
    </div>
    """, unsafe_allow_html=True)

    # Fetch all match results with invoice details
    conn = get_connection()
    query = """
        SELECT 
            mr.INV_ID as "Invoice No", 
            ih.Vendor as "Vendor", 
            ih.Date as "Invoice Date", 
            mr.PO_ID as "PO Number", 
            ih.Total as "Amount ($)", 
            mr.Status as "Status", 
            ROUND(mr.Score * 100, 1) as "Confidence (%)", 
            mr.Remark as "Remarks"
        FROM MATCH_RESULT mr
        JOIN INVOICE_HEADER ih ON mr.INV_ID = ih.INV_ID
        ORDER BY mr.Processed_Date DESC
    """
    df_invoices = pd.read_sql_query(query, conn)
    conn.close()

    if not df_invoices.empty:
        # Format the dataframe for display
        df_display = df_invoices.copy()

        # Add status badges using HTML
        def format_status(status):
            if status == 'MATCH':
                return f'<span class="status-match">✓ {status}</span>'
            elif status == 'DISCREPANCY':
                return f'<span class="status-discrepancy">✗ {status}</span>'
            else:
                return f'<span class="status-pending">⏳ {status}</span>'

        df_display['Status'] = df_display['Status'].apply(format_status)

        # Color code confidence
        def format_confidence(conf):
            if conf >= 90:
                return f'<span style="color: #10b981; font-weight: bold;">{conf}%</span>'
            elif conf >= 70:
                return f'<span style="color: #f59e0b; font-weight: bold;">{conf}%</span>'
            else:
                return f'<span style="color: #ef4444; font-weight: bold;">{conf}%</span>'

        df_display['Confidence (%)'] = df_display['Confidence (%)'].apply(format_confidence)

        # Display the table with HTML rendering
        st.markdown(
            df_display.to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
    else:
        st.info("📭 No invoices processed yet. Run the AI engine to populate data.")

# Footer with processing stats
st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05);'>
    <p style='margin: 0; color: #718096; font-size: 0.9em;'>
        <strong>AP AI Automation Prototype</strong> • Powered by PaddleOCR & Rule-Based AI Engine<br>
        <span style='color: #a0aec0; font-size: 0.85em;'>Intelligent document processing for modern accounts payable</span>
    </p>
</div>
""", unsafe_allow_html=True)

# Add a refresh button
if st.sidebar.button("🔄 Refresh Dashboard"):
    st.rerun()

# Sidebar with additional info
with st.sidebar:
    st.markdown("### 🎯 Quick Stats")
    st.markdown(f"""
    - **Processing Rate**: {matched_pct:.1f}% auto-approved
    - **Review Needed**: {stats['discrepancy'] + stats['pending']} invoices
    - **Efficiency Gain**: ~85% time saved
    """)

    st.markdown("###  Actions")
    st.markdown("""
    - Process New Invoice
    - Export Reports
    - Configure Rules
    - View Documentation
    """)
