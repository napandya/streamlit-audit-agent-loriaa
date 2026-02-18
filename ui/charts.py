"""
Revenue trend charts and visualizations
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict
import pandas as pd
from datetime import date

from utils.helpers import format_currency, format_percentage


def render_revenue_trend(trend_data: List[Dict]):
    """
    Render revenue trend chart with lease cliff visualization
    """
    st.header("📉 Revenue Trend Analysis")
    
    if not trend_data:
        st.info("No transaction data available for the selected period.")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(trend_data)
    df['month_str'] = df['month'].apply(lambda x: x.strftime('%b %Y'))
    
    # Create figure with secondary y-axis
    fig = go.Figure()
    
    # Add revenue line
    fig.add_trace(go.Scatter(
        x=df['month_str'],
        y=df['revenue'],
        name='Net Revenue',
        line=dict(color='#1f77b4', width=3),
        mode='lines+markers',
        marker=dict(size=8),
        hovertemplate='%{x}<br>Revenue: $%{y:,.2f}<extra></extra>'
    ))
    
    # Add rent component
    fig.add_trace(go.Scatter(
        x=df['month_str'],
        y=df['rent'],
        name='Rent',
        line=dict(color='#2ca02c', width=2, dash='dot'),
        mode='lines',
        hovertemplate='%{x}<br>Rent: $%{y:,.2f}<extra></extra>'
    ))
    
    # Add concessions (as negative for visualization)
    fig.add_trace(go.Scatter(
        x=df['month_str'],
        y=[-c for c in df['concessions']],
        name='Concessions',
        line=dict(color='#d62728', width=2, dash='dot'),
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(214, 39, 40, 0.1)',
        hovertemplate='%{x}<br>Concessions: $%{y:,.2f}<extra></extra>'
    ))
    
    # Highlight lease cliffs (drops > 20%)
    cliff_months = []
    cliff_values = []
    for i, row in df.iterrows():
        if row['change_pct'] is not None and row['change_pct'] < -0.20:
            cliff_months.append(row['month_str'])
            cliff_values.append(row['revenue'])
    
    if cliff_months:
        fig.add_trace(go.Scatter(
            x=cliff_months,
            y=cliff_values,
            name='Lease Cliff',
            mode='markers',
            marker=dict(
                size=15,
                color='red',
                symbol='x',
                line=dict(width=2, color='darkred')
            ),
            hovertemplate='%{x}<br>Cliff Detected: $%{y:,.2f}<extra></extra>'
        ))
    
    # Update layout
    fig.update_layout(
        title='Month-over-Month Revenue Trend',
        xaxis_title='Month',
        yaxis_title='Amount ($)',
        hovermode='x unified',
        height=500,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Revenue change table
    st.subheader("📊 Month-over-Month Changes")
    
    # Create change dataframe
    change_df = df[['month_str', 'revenue', 'change', 'change_pct']].copy()
    change_df.columns = ['Month', 'Revenue', 'Change ($)', 'Change (%)']
    
    # Format the dataframe
    def format_row(row):
        if row['Change ($)'] is not None:
            row['Change ($)'] = format_currency(row['Change ($)'])
            row['Change (%)'] = format_percentage(row['Change (%)'])
        else:
            row['Change ($)'] = '-'
            row['Change (%)'] = '-'
        row['Revenue'] = format_currency(row['Revenue'])
        return row
    
    change_df = change_df.apply(format_row, axis=1)
    
    st.dataframe(
        change_df,
        hide_index=True,
        use_container_width=True
    )


def render_concession_analysis(transactions: List):
    """Render concession and credit analysis"""
    st.subheader("💸 Concession & Credit Analysis")
    
    # Group concessions by month
    from collections import defaultdict
    monthly_concessions = defaultdict(float)
    
    for txn in transactions:
        if txn.category == 'concession' and txn.month:
            monthly_concessions[txn.month] += abs(txn.amount)
    
    if not monthly_concessions:
        st.info("No concessions found in the selected period.")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame([
        {'Month': month.strftime('%b %Y'), 'Concessions': amount}
        for month, amount in sorted(monthly_concessions.items())
    ])
    
    # Create bar chart
    fig = px.bar(
        df,
        x='Month',
        y='Concessions',
        title='Monthly Concession Totals',
        labels={'Concessions': 'Amount ($)'},
        color='Concessions',
        color_continuous_scale='Reds'
    )
    
    fig.update_layout(
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Concession tapering analysis
    st.write("**Tapering Trend:**")
    total_conc = sum(monthly_concessions.values())
    first_half = sum(list(monthly_concessions.values())[:len(monthly_concessions)//2])
    second_half = sum(list(monthly_concessions.values())[len(monthly_concessions)//2:])
    
    if first_half > 0:
        taper_pct = ((first_half - second_half) / first_half) * 100
        if taper_pct > 10:
            st.success(f"✅ Concessions are tapering down ({taper_pct:.1f}% reduction)")
        elif taper_pct < -10:
            st.warning(f"⚠️ Concessions are increasing ({abs(taper_pct):.1f}% increase)")
        else:
            st.info(f"→ Concessions are relatively stable ({taper_pct:.1f}% change)")


def render_lease_cliff_heatmap(findings: List):
    """Render lease cliff risk heatmap"""
    st.subheader("🔥 Lease Cliff Risk Heatmap")
    
    # Filter lease cliff findings
    cliff_findings = [f for f in findings if f.rule_id == 'LEASE_CLIFF']
    
    if not cliff_findings:
        st.success("✅ No lease cliffs detected in the selected period.")
        return
    
    # Create heatmap data
    heatmap_data = []
    for finding in cliff_findings:
        drop_pct = finding.evidence.get('drop_pct', 0)
        heatmap_data.append({
            'Unit': finding.unit_number,
            'Month': finding.month.strftime('%b %Y') if finding.month else 'Unknown',
            'Drop %': drop_pct * 100,
            'Amount': abs(finding.delta) if finding.delta else 0
        })
    
    df = pd.DataFrame(heatmap_data)
    
    # Display as table with color coding
    st.dataframe(
        df.style.background_gradient(subset=['Drop %'], cmap='Reds'),
        hide_index=True,
        use_container_width=True
    )
