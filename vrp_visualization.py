"""
Kartendarstellung der Touren (statisch und animiert) auf Basis von Plotly.
Nutzt das Straßennetz (vrp_network) und die Zeitfenster-Auswertung
(vrp_evaluation), um Verletzungen rot zu markieren.
"""

import numpy as np
import plotly.graph_objects as go

from vrp_constants import VEHICLE_COLORS
from vrp_evaluation import route_timeline
from vrp_network import route_polyline


def build_figure(depot, coords, ids, routes_snapshot, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, loads=None, capacity=None):
    """Baut die statische Plotly-Karte: Straßennetz im Hintergrund, Depot,
    eine farbige Linie + Marker je Fahrzeugtour, Zeitfenster-Verletzungen rot
    markiert (wenn tw_enabled)."""
    fig = go.Figure()

    normal_x, normal_y, asym_x, asym_y = r_edges_xy
    fig.add_trace(
        go.Scatter(
            x=normal_x, y=normal_y,
            mode="lines", line=dict(color="rgba(150,150,150,0.35)", width=1),
            hoverinfo="skip", showlegend=False, name="Straßennetz",
        )
    )
    if asym_x:
        fig.add_trace(
            go.Scatter(
                x=asym_x, y=asym_y,
                mode="lines", line=dict(color="rgba(234,88,12,0.55)", width=1.5, dash="dot"),
                hoverinfo="skip", showlegend=True, name="Einbahn-/Umweg-Abschnitt",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[depot[0]], y=[depot[1]],
            mode="markers+text", marker=dict(size=18, color="black", symbol="star"),
            text=["Depot"], textposition="top center", name="Depot", hoverinfo="text",
        )
    )

    violated_ids = set()
    if tw_enabled:
        for route in routes_snapshot:
            timeline = route_timeline(route, D, earliest, latest, service)
            violated_ids |= {t["stop"] for t in timeline if t["violation"]}

    for v_idx, route in enumerate(routes_snapshot):
        if not route:
            continue
        color = VEHICLE_COLORS[v_idx % len(VEHICLE_COLORS)]
        xs, ys = route_polyline(route, paths_lookup, node_positions)
        label = f"Fahrzeug {v_idx + 1}"
        if loads is not None and capacity is not None:
            label += f" ({loads[v_idx]:.0f}/{capacity:.0f})"

        fig.add_trace(
            go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=3), name=label, hoverinfo="skip")
        )
        marker_colors = ["#ef4444" if s in violated_ids else color for s in route]
        fig.add_trace(
            go.Scatter(
                x=[coords[s][0] for s in route], y=[coords[s][1] for s in route],
                mode="markers+text", marker=dict(size=10, color=marker_colors, line=dict(width=1, color="white")),
                text=[str(ids[s]) for s in route], textposition="top center",
                showlegend=False, hoverinfo="text",
            )
        )

    fig.update_layout(
        xaxis=dict(range=[-5, 105], title="x", zeroline=False),
        yaxis=dict(range=[-5, 105], title="y", zeroline=False, scaleanchor="x"),
        height=520, margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def interpolate_along_polyline(xs, ys, n_frames):
    """Gibt n_frames Punkte zurück, die gleichmäßig nach zurückgelegter
    Weglänge entlang der Polylinie verteilt sind (für die LKW-Animation)."""
    xs = np.array(xs, dtype=float)
    ys = np.array(ys, dtype=float)
    if len(xs) < 2:
        x0 = xs[0] if len(xs) else 0.0
        y0 = ys[0] if len(ys) else 0.0
        return np.full(n_frames, x0), np.full(n_frames, y0)
    seg = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1] if cum[-1] > 0 else 1.0
    targets = np.linspace(0, total, n_frames)
    return np.interp(targets, cum, xs), np.interp(targets, cum, ys)


def build_animated_figure(depot, coords, ids, routes_snapshot, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, capacity=None, n_frames=40):
    """Baut auf build_figure auf und lässt pro Fahrzeug ein echtes LKW-Emoji
    (🚚, mit farbigem Hintergrundkreis für die Fahrzeug-Zuordnung) die fertige
    Route entlangfahren (Fortschritt in % der Wegstrecke, synchron über alle
    Fahrzeuge - sie starten und enden gemeinsam, auch wenn die realen
    Streckenlängen unterschiedlich sind)."""
    fig = build_figure(depot, coords, ids, routes_snapshot, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, capacity=capacity)

    active = [v for v, r in enumerate(routes_snapshot) if r]
    if not active:
        return fig

    polylines = {}
    for v in active:
        xs, ys = route_polyline(routes_snapshot[v], paths_lookup, node_positions)
        polylines[v] = interpolate_along_polyline(xs, ys, n_frames)

    colors = [VEHICLE_COLORS[v % len(VEHICLE_COLORS)] for v in active]
    # Zwei uebereinanderliegende Spuren statt einer: ein farbiger Hintergrundkreis
    # (haelt die Fahrzeug-Farbcodierung, die die Routenlinien ebenfalls nutzen)
    # PLUS ein echtes LKW-Emoji als Text-Marker obenauf. Auf Nutzerhinweis
    # korrigiert - die vorherige Fassung nutzte nur ein einfaches Dreieck-Symbol
    # (symbol="triangle-right") und einen Trace-internen Namen "🚚", der wegen
    # showlegend=False/hoverinfo="skip" nirgends sichtbar war - die App-Texte
    # ("LKW-Animation", "LKW-Symbol") versprachen mehr, als tatsächlich zu sehen
    # war. Keine Richtungsrotation ging dabei verloren - das Dreieck zeigte
    # ohnehin immer starr nach rechts, unabhängig von der tatsächlichen
    # Fahrtrichtung.
    bg_trace_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=[polylines[v][0][0] for v in active], y=[polylines[v][1][0] for v in active],
            mode="markers", marker=dict(size=20, color=colors, line=dict(width=2, color="white")),
            showlegend=False, hoverinfo="skip",
        )
    )
    truck_trace_index = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=[polylines[v][0][0] for v in active], y=[polylines[v][1][0] for v in active],
            mode="text", text=["🚚"] * len(active), textfont=dict(size=15),
            showlegend=False, hoverinfo="skip",
        )
    )

    frames = []
    for f in range(n_frames):
        fx = [polylines[v][0][f] for v in active]
        fy = [polylines[v][1][f] for v in active]
        frames.append(
            go.Frame(
                data=[
                    go.Scatter(x=fx, y=fy, mode="markers", marker=dict(size=20, color=colors, line=dict(width=2, color="white"))),
                    go.Scatter(x=fx, y=fy, mode="text", text=["🚚"] * len(active), textfont=dict(size=15)),
                ],
                traces=[bg_trace_index, truck_trace_index], name=str(f),
            )
        )
    fig.frames = frames

    fig.update_layout(
        margin=dict(l=10, r=10, t=90, b=70),
        updatemenus=[
            dict(
                type="buttons", showactive=False, y=1.22, x=0.0, xanchor="left",
                buttons=[
                    dict(label="▶️ Abspielen", method="animate", args=[None, dict(frame=dict(duration=70, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
                    dict(label="⏸️ Pause", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
                ],
            )
        ],
        sliders=[
            dict(
                active=0, x=0.0, y=-0.12, len=1.0, currentvalue=dict(visible=False),
                steps=[
                    dict(method="animate", args=[[str(f)], dict(mode="immediate", frame=dict(duration=0, redraw=True))], label="")
                    for f in range(n_frames)
                ],
            )
        ],
    )
    return fig
