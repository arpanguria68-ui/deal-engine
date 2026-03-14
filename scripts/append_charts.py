import sys

new_methods = """
    # ── 9. SaaS Cohort Retention Heatmap ─────────────────────
    @staticmethod
    def cohort_retention_heatmap(cohorts: list, periods: list, data: list, title: str = "Cohort Retention") -> bytes:
        _ensure_matplotlib()
        import matplotlib.pyplot as plt
        import seaborn as sns
        import numpy as np

        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
        fig.patch.set_facecolor("white")
        cmap = sns.light_palette(PALETTE["primary"], as_cmap=True)
        sns.heatmap(np.array(data), annot=True, fmt=".0%", cmap=cmap,
                    xticklabels=periods, yticklabels=cohorts, 
                    linewidths=.5, cbar=False, ax=ax)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── 10. Geographic Heatmap (Choropleth) ──────────────────
    @staticmethod
    def geographic_heatmap(locations: list, values: list, title: str = "Geographic Revenue") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure(data=go.Choropleth(
            locations=locations, locationmode='USA-states', z=values,
            colorscale='Blues', colorbar_title="Revenue"
        ))
        fig.update_layout(title_text=title, geo_scope='usa', width=900, height=500)
        return fig.to_image(format="png", scale=2)

    # ── 11. EBITDA Waterfall ─────────────────────────────────
    @staticmethod
    def ebitda_waterfall(labels: list, values: list, title: str = "EBITDA Bridge") -> bytes:
        return InfographicEngine.revenue_waterfall(labels, values, title=title)

    # ── 12. Scenario Comparison Table ────────────────────────
    @staticmethod
    def scenario_comparison_table(metrics: list, base: list, bull: list, bear: list, title: str = "Scenario Analysis") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Table(
            header=dict(values=['Metric', 'Bear', 'Base', 'Bull'], fill_color=PALETTE["primary"], font=dict(color='white', size=12)),
            cells=dict(values=[metrics, bear, base, bull], fill_color=[[PALETTE["bg"]]*len(metrics)])
        )])
        fig.update_layout(title_text=title, width=800, height=400)
        return fig.to_image(format="png", scale=2)

    # ── 13. Driver Sensitivity Tornado ───────────────────────
    @staticmethod
    def driver_sensitivity_tornado(drivers: list, low_impacts: list, high_impacts: list, base_val: float = 0, title: str = "Sensitivity Tornado") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Bar(y=drivers, x=[l - base_val for l in low_impacts], base=base_val, orientation='h', name='Low', marker_color=PALETTE["negative"]))
        fig.add_trace(go.Bar(y=drivers, x=[h - base_val for h in high_impacts], base=base_val, orientation='h', name='High', marker_color=PALETTE["positive"]))
        fig.update_layout(title_text=title, barmode='overlay', width=800, height=500)
        return fig.to_image(format="png", scale=2)

    # ── 14. Capital Structure Tower ──────────────────────────
    @staticmethod
    def capital_structure_tower(layers: list, amounts: list, cost: list, title: str = "Capital Structure") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Bar(name='Capital', x=['Capital Structure'], y=amounts, text=[f"{l}<br>${a}M" for l,a in zip(layers, amounts)], textposition='inside')])
        fig.update_layout(barmode='stack', title_text=title, width=600, height=600)
        return fig.to_image(format="png", scale=2)

    # ── 15. WACC Breakdown Pie ───────────────────────────────
    @staticmethod
    def wacc_breakdown_pie(labels: list, weights: list, title: str = "WACC Breakdown") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Pie(labels=labels, values=weights, hole=.4)])
        fig.update_layout(title_text=title, width=600, height=500)
        return fig.to_image(format="png", scale=2)

    # ── 16. Regulatory Timeline Gantt ────────────────────────
    @staticmethod
    def regulatory_timeline_gantt(tasks: list, starts: list, finishes: list, title: str = "Regulatory Timeline") -> bytes:
        _ensure_plotly()
        import plotly.express as px
        import pandas as pd
        df = pd.DataFrame([dict(Task=t, Start=s, Finish=f) for t,s,f in zip(tasks, starts, finishes)])
        fig = px.timeline(df, x_start="Start", x_end="Finish", y="Task", title=title)
        fig.update_yaxes(autorange="reversed")
        return fig.to_image(format="png", scale=2, engine="kaleido")

    # ── 17. Customer Concentration Bubble ────────────────────
    @staticmethod
    def customer_concentration_bubble(customers: list, revenues: list, margins: list, title: str = "Customer Concentration") -> bytes:
        _ensure_plotly()
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Scatter(x=revenues, y=margins, mode='markers+text', text=customers, marker=dict(size=[r/max(revenues)*50 for r in revenues], color=revenues, colorscale='Viridis'))])
        fig.update_layout(title_text=title, xaxis_title="Revenue ($M)", yaxis_title="Margin (%)", width=800, height=500)
        return fig.to_image(format="png", scale=2)
"""

with open(
    r"f:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\app\core\reports\infographic_engine.py",
    "a",
    encoding="utf-8",
) as f:
    f.write(new_methods)
print("appended")
