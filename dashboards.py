import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from database import get_recent_workouts

def render_dashboards(user_id: str):
    st.markdown("<h2 style='color: #38BDF8;'>📈 Performance Dashboard</h2>", unsafe_allow_html=True)
    
    workouts = get_recent_workouts(user_id, limit=30)
    
    if not workouts:
        st.info("No workout data found. Sync your Polar account to see dashboards!")
        return
        
    df = pd.DataFrame(workouts)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # 1. Volume Chart
    st.markdown("### Weekly Volume (Minutes)")
    volume_df = df.groupby(df['date'].dt.isocalendar().week)['duration_minutes'].sum().reset_index()
    fig_vol = px.bar(volume_df, x='week', y='duration_minutes', 
                     color_discrete_sequence=['#10B981'],
                     labels={'duration_minutes': 'Total Minutes', 'week': 'Week Number'})
    fig_vol.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#E2E8F0")
    st.plotly_chart(fig_vol, use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    # 2. Sport Distribution
    with col1:
        st.markdown("### Sport Breakdown")
        fig_pie = px.pie(df, names='sport', values='duration_minutes', hole=0.4, 
                         color_discrete_sequence=px.colors.sequential.Plasma)
        fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#E2E8F0")
        st.plotly_chart(fig_pie, use_container_width=True)
        
    # 3. Heart Rate Trend
    with col2:
        st.markdown("### Avg Heart Rate Trend")
        fig_hr = px.line(df, x='date', y='heart_rate_avg', markers=True, 
                         color_discrete_sequence=['#A855F7'])
        fig_hr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#E2E8F0")
        st.plotly_chart(fig_hr, use_container_width=True)
