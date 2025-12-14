"""Result export helpers."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from smartflow.viz.charts import build_active_agents_series, build_travel_time_histogram
from smartflow.viz.heatmap import build_heatmap_figure


def export_csv(path: Path, rows: Iterable[dict]) -> None:
    """Write simulation metrics to CSV."""

    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    header = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _fig_to_image(fig: Any, width: int = 400, height: int = 300) -> Image:
    """Convert a Matplotlib figure to a ReportLab Image."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    return Image(buf, width=width, height=height)


def export_pdf(path: Path, results: Any, floorplan: Any, config: Dict[str, Any]) -> None:
    """Generate a PDF report using ReportLab."""
    
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title = Paragraph("SmartFlow Simulation Report", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))

    # Configuration Summary
    story.append(Paragraph("Configuration", styles['Heading2']))
    config_data = [
        ["Parameter", "Value"],
        ["Layout", floorplan.node_ids().__class__.__name__ if floorplan else "Unknown"], # Just a placeholder name
        ["Duration", f"{config.get('duration', 0)}s"],
        ["Seed", str(config.get('seed', 'N/A'))],
        ["Agents", str(results.summary().get('total_agents', 0))]
    ]
    t = Table(config_data, colWidths=[200, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Metrics Summary
    story.append(Paragraph("Key Metrics", styles['Heading2']))
    summary = results.summary()
    metrics_data = [
        ["Metric", "Value"],
        ["Mean Travel Time", f"{summary.get('mean_travel_time_s', 0):.2f} s"],
        ["P90 Travel Time", f"{summary.get('p90_travel_time_s', 0):.2f} s"],
        ["Max Edge Density", f"{summary.get('max_edge_density', 0):.2f}"],
        ["Congestion Events", str(summary.get('congestion_events', 0))],
        ["Total Throughput", str(summary.get('total_throughput', 0))]
    ]
    t2 = Table(metrics_data, colWidths=[200, 200])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t2)
    story.append(Spacer(1, 20))

    # Visualisations
    story.append(Paragraph("Visualisations", styles['Heading2']))
    
    # Heatmap
    story.append(Paragraph("Network Heatmap", styles['Heading3']))
    graph = floorplan.to_networkx()
    fig_heatmap = build_heatmap_figure(graph, results.edge_metrics)
    story.append(_fig_to_image(fig_heatmap, width=450, height=350))
    story.append(Spacer(1, 12))
    
    # Charts
    story.append(Paragraph("Performance Charts", styles['Heading3']))
    
    fig_hist = build_travel_time_histogram(results.agent_metrics)
    story.append(_fig_to_image(fig_hist, width=400, height=300))
    story.append(Spacer(1, 12))
    
    total_ticks = len(next(iter(results.edge_metrics.values())).occupancy_over_time) if results.edge_metrics else 0
    fig_series = build_active_agents_series(results.edge_metrics, total_ticks)
    story.append(_fig_to_image(fig_series, width=400, height=300))

    doc.build(story)
