"""
InfographicEngine — McKinsey/Goldman-Grade Chart Generation

Generates publication-quality charts for embedding in PDF, PPTX, and Excel reports.
Uses Matplotlib + Seaborn for static charts, Plotly + Kaleido for interactive-style exports.
"""

import io
import math
from typing import Dict, Any, List, Optional, Tuple
import structlog

logger = structlog.get_logger()

# Lazy imports to avoid slow startup
_MPL_LOADED = False
_PLOTLY_LOADED = False


def _ensure_matplotlib():
    global _MPL_LOADED
    if not _MPL_LOADED:
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend for server
        _MPL_LOADED = True


def _ensure_plotly():
    global _PLOTLY_LOADED
    if not _PLOTLY_LOADED:
        import plotly.io as pio

        pio.kaleido.scope.default_format = "png"
        _PLOTLY_LOADED = True


# ─── Color Palette (McKinsey / Goldman-inspired) ───
PALETTE = {
    "primary": "#003A70",  # Deep navy
    "secondary": "#0072CE",  # Bright blue
    "accent": "#00B4D8",  # Teal
    "positive": "#2D9F45",  # Green
    "negative": "#D32F2F",  # Red
    "warning": "#F9A825",  # Amber
    "neutral": "#607D8B",  # Blue-grey
    "bg": "#F7F9FC",  # Light bg
    "grid": "#E0E6ED",  # Grid lines
    "text": "#1A2332",  # Dark text
}

CHART_COLORS = [
    "#003A70",
    "#0072CE",
    "#00B4D8",
    "#2D9F45",
    "#F9A825",
    "#D32F2F",
    "#8E24AA",
    "#FF6F00",
    "#00695C",
    "#37474F",
]


class InfographicEngine:
    """Generate McKinsey/IB-grade infographic charts as PNG bytes."""

    # ── 1. Football Field Chart ──────────────────────────────
    @staticmethod
    def football_field_chart(
        valuations: List[Dict[str, Any]],
        title: str = "Valuation Summary",
        width: int = 900,
        height: int = 500,
        current_price: Optional[float] = None,
        unit: str = "$B",
    ) -> bytes:
        """
        Generate a 'Football Field' valuation summary chart.

        Args:
            valuations: List of dicts with keys: method, low, mid, high
            title: Chart title
            current_price: Optional current price to show as a vertical marker
            unit: Unit label (e.g., "$B", "$M", "$")
        Returns:
            PNG bytes
        """
        _ensure_plotly()
        import plotly.graph_objects as go

        methods = [v["method"] for v in valuations]
        lows = [v["low"] for v in valuations]
        mids = [v.get("mid", (v["low"] + v["high"]) / 2) for v in valuations]
        highs = [v["high"] for v in valuations]

        fig = go.Figure()

        # Range bars
        for i, (m, lo, mi, hi) in enumerate(zip(methods, lows, mids, highs)):
            color = CHART_COLORS[i % len(CHART_COLORS)]
            fig.add_trace(
                go.Bar(
                    y=[m],
                    x=[hi - lo],
                    base=[lo],
                    orientation="h",
                    marker=dict(
                        color=color, opacity=0.3, line=dict(color=color, width=2)
                    ),
                    name=m,
                    showlegend=False,
                    text=f"{lo:,.1f}{unit} \u2013 {hi:,.1f}{unit}",
                    textposition="inside",
                    hovertemplate=f"<b>{m}</b><br>Range: {lo:,.1f}{unit} \u2013 {hi:,.1f}{unit}<br>Mid: {mi:,.1f}{unit}",
                )
            )
            # Midpoint marker
            fig.add_trace(
                go.Scatter(
                    y=[m],
                    x=[mi],
                    mode="markers+text",
                    marker=dict(color=color, size=14, symbol="diamond"),
                    text=[f"{mi:,.1f}{unit}"],
                    textposition="middle right",
                    showlegend=False,
                )
            )

        # Current Price Marker
        if current_price is not None:
            fig.add_vline(
                x=current_price,
                line_dash="dash",
                line_color=PALETTE["negative"],
                annotation_text=f"Current: {current_price:,.1f}{unit}",
                annotation_position="top",
            )

        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color=PALETTE["text"])),
            xaxis=dict(title=f"Enterprise Value ({unit})", gridcolor=PALETTE["grid"]),
            yaxis=dict(autorange="reversed"),
            plot_bgcolor=PALETTE["bg"],
            paper_bgcolor="white",
            height=height,
            width=width,
            margin=dict(l=140, r=40, t=60, b=60),
            barmode="overlay",
            font=dict(family="Liberation Sans, Helvetica, Arial"),
        )

        return fig.to_image(format="png", scale=2)

    # ── 2. Revenue Waterfall Chart ───────────────────────────
    @staticmethod
    def revenue_waterfall(
        labels: List[str],
        values: List[float],
        title: str = "Revenue Bridge",
    ) -> bytes:
        """Waterfall chart showing revenue/value build-up or breakdown."""
        _ensure_matplotlib()
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
        fig.patch.set_facecolor("white")
        ax.set_facecolor(PALETTE["bg"])

        cumulative = [0]
        for v in values[:-1]:
            cumulative.append(cumulative[-1] + v)

        colors = []
        for i, v in enumerate(values):
            if i == 0 or i == len(values) - 1:
                colors.append(PALETTE["primary"])  # base / total
            elif v >= 0:
                colors.append(PALETTE["positive"])
            else:
                colors.append(PALETTE["negative"])

        bottoms = cumulative[:-1] + [0]
        bars = ax.bar(
            labels,
            [abs(v) for v in values],
            bottom=[max(b, b + v) if v < 0 else b for b, v in zip(bottoms, values)],
            color=colors,
            edgecolor="white",
            linewidth=1.5,
            width=0.55,
        )

        # Add value labels
        for bar, v in zip(bars, values):
            y_pos = bar.get_y() + bar.get_height() / 2
            sign = "+" if v > 0 else ""
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y_pos,
                f"{sign}{v:,.0f}",
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                color="white",
            )

        # Connector lines
        for i in range(len(values) - 2):
            ax.plot(
                [i + 0.3, i + 0.7],
                [cumulative[i + 1], cumulative[i + 1]],
                color=PALETTE["neutral"],
                linewidth=0.8,
                linestyle="--",
            )

        ax.set_title(
            title, fontsize=14, fontweight="bold", color=PALETTE["text"], pad=15
        )
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3, color=PALETTE["grid"])
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── 3. Risk Heatmap ──────────────────────────────────────
    @staticmethod
    def risk_heatmap(
        risk_data: Dict[str, Dict[str, float]],
        title: str = "Risk Assessment Matrix",
    ) -> bytes:
        """
        Heatmap of risk categories vs dimensions.

        Args:
            risk_data: {"Market Risk": {"Probability": 0.7, "Impact": 0.9, ...}, ...}
        """
        _ensure_matplotlib()
        import matplotlib.pyplot as plt
        import seaborn as sns
        import numpy as np

        categories = list(risk_data.keys())
        dimensions = list(next(iter(risk_data.values())).keys())
        matrix = np.array(
            [[risk_data[cat].get(dim, 0) for dim in dimensions] for cat in categories]
        )

        fig, ax = plt.subplots(
            figsize=(max(8, len(dimensions) * 1.2), max(5, len(categories) * 0.6)),
            dpi=150,
        )
        fig.patch.set_facecolor("white")

        cmap = sns.diverging_palette(145, 6, s=85, l=45, as_cmap=True)
        sns.heatmap(
            matrix,
            annot=True,
            fmt=".1f",
            cmap=cmap,
            xticklabels=dimensions,
            yticklabels=categories,
            linewidths=2,
            linecolor="white",
            cbar_kws={"label": "Risk Score", "shrink": 0.8},
            vmin=0,
            vmax=1,
            ax=ax,
        )

        ax.set_title(
            title, fontsize=14, fontweight="bold", color=PALETTE["text"], pad=15
        )
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── 4. Deal Score Radar Chart ────────────────────────────
    @staticmethod
    def deal_score_radar(
        scores: Dict[str, float],
        title: str = "Deal Score",
        max_score: float = 10.0,
    ) -> bytes:
        """Spider/radar chart for multi-dimensional deal scoring."""
        _ensure_matplotlib()
        import matplotlib.pyplot as plt
        import numpy as np

        categories = list(scores.keys())
        values = [scores[c] / max_score for c in categories]
        values += values[:1]  # close the polygon

        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True), dpi=150)
        fig.patch.set_facecolor("white")

        ax.fill(angles, values, color=PALETTE["secondary"], alpha=0.15)
        ax.plot(
            angles,
            values,
            color=PALETTE["secondary"],
            linewidth=2.5,
            marker="o",
            markersize=7,
        )

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=10)
        ax.set_ylim(0, 1)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(
            ["2", "4", "6", "8", "10"], fontsize=8, color=PALETTE["neutral"]
        )
        ax.yaxis.grid(True, color=PALETTE["grid"], linewidth=0.5)
        ax.set_title(
            title, fontsize=14, fontweight="bold", color=PALETTE["text"], pad=25, y=1.08
        )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── 5. Cash Flow Sankey Diagram ──────────────────────────
    @staticmethod
    def cash_flow_sankey(
        sources: List[str],
        targets: List[str],
        values: List[float],
        title: str = "Cash Flow Allocation",
    ) -> bytes:
        """Sankey diagram showing cash flow allocation between categories."""
        _ensure_plotly()
        import plotly.graph_objects as go

        all_labels = list(dict.fromkeys(sources + targets))
        source_idx = [all_labels.index(s) for s in sources]
        target_idx = [all_labels.index(t) for t in targets]

        fig = go.Figure(
            go.Sankey(
                node=dict(
                    pad=20,
                    thickness=25,
                    line=dict(color=PALETTE["primary"], width=1),
                    label=all_labels,
                    color=[
                        CHART_COLORS[i % len(CHART_COLORS)]
                        for i in range(len(all_labels))
                    ],
                ),
                link=dict(
                    source=source_idx,
                    target=target_idx,
                    value=values,
                    color=[f"rgba(0, 114, 206, 0.3)"] * len(values),
                ),
            )
        )

        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color=PALETTE["text"])),
            font=dict(family="Liberation Sans, Helvetica, Arial", size=12),
            width=900,
            height=500,
            paper_bgcolor="white",
        )

        return fig.to_image(format="png", scale=2)

    # ── 6. Sensitivity Table ─────────────────────────────────
    @staticmethod
    def sensitivity_table(
        row_label: str,
        col_label: str,
        row_values: List[float],
        col_values: List[float],
        result_matrix: List[List[float]],
        title: str = "Sensitivity Analysis",
        fmt: str = "{:,.0f}",
        unit: str = "$B",
    ) -> bytes:
        """Color-coded sensitivity analysis grid."""
        _ensure_matplotlib()
        import matplotlib.pyplot as plt
        import seaborn as sns
        import numpy as np

        data = np.array(result_matrix)
        fig, ax = plt.subplots(
            figsize=(max(8, len(col_values) * 1.3), max(5, len(row_values) * 0.7)),
            dpi=150,
        )
        fig.patch.set_facecolor("white")

        cmap = sns.diverging_palette(6, 145, s=80, l=55, as_cmap=True)
        mid = np.median(data)

        sns.heatmap(
            data,
            annot=True,
            fmt=".0f",
            cmap=cmap,
            center=mid,
            xticklabels=[f"{v:.1%}" if abs(v) < 1 else f"{v:.1f}" for v in col_values],
            yticklabels=[f"{v:.1%}" if abs(v) < 1 else f"{v:.1f}" for v in row_values],
            linewidths=2,
            linecolor="white",
            cbar_kws={"label": f"Value ({unit})", "shrink": 0.8},
            ax=ax,
        )

        ax.set_xlabel(col_label, fontsize=11, fontweight="bold")
        ax.set_ylabel(row_label, fontsize=11, fontweight="bold")
        ax.set_title(
            title, fontsize=14, fontweight="bold", color=PALETTE["text"], pad=15
        )
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ── 7. Market Position Bubble Chart ──────────────────────
    @staticmethod
    def market_position_bubble(
        companies: List[Dict[str, Any]],
        title: str = "Competitive Landscape",
    ) -> bytes:
        """
        Bubble chart: x=Revenue, y=Growth, size=Market Cap, color=Margin.

        Args:
            companies: [{"name": "Co", "revenue": 100, "growth": 0.15, "market_cap": 500, "margin": 0.2}, ...]
        """
        _ensure_plotly()
        import plotly.graph_objects as go

        fig = go.Figure()
        for i, c in enumerate(companies):
            fig.add_trace(
                go.Scatter(
                    x=[c["revenue"]],
                    y=[c["growth"] * 100],
                    mode="markers+text",
                    marker=dict(
                        size=max(15, min(80, c.get("market_cap", 100) / 10)),
                        color=c.get("margin", 0.15),
                        colorscale="RdYlGn",
                        cmin=0,
                        cmax=0.4,
                        line=dict(color="white", width=2),
                    ),
                    text=[c["name"]],
                    textposition="top center",
                    name=c["name"],
                    hovertemplate=(
                        f"<b>{c['name']}</b><br>Revenue: ${c['revenue']:,.0f}M<br>"
                        f"Growth: {c['growth']:.1%}<br>Margin: {c.get('margin', 0):.1%}"
                    ),
                )
            )

        fig.update_layout(
            title=dict(text=title, font=dict(size=18, color=PALETTE["text"])),
            xaxis=dict(title="Revenue ($M)", gridcolor=PALETTE["grid"]),
            yaxis=dict(title="Revenue Growth (%)", gridcolor=PALETTE["grid"]),
            plot_bgcolor=PALETTE["bg"],
            paper_bgcolor="white",
            showlegend=False,
            width=900,
            height=550,
            font=dict(family="Liberation Sans, Helvetica, Arial"),
        )

        return fig.to_image(format="png", scale=2)

    # ── 8. DCF Bridge Chart ──────────────────────────────────
    @staticmethod
    def dcf_bridge_chart(
        components: Dict[str, float],
        title: str = "DCF Value Bridge",
    ) -> bytes:
        """
        Bridge/waterfall chart for DCF components.

        Args:
            components: OrderedDict like {"PV of FCF": 450, "Terminal Value": 620,
                        "- Net Debt": -180, "Equity Value": 890}
        """
        labels = list(components.keys())
        values = list(components.values())
        return InfographicEngine.revenue_waterfall(labels, values, title=title)

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
