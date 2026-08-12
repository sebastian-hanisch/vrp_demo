"""
Wiederverwendbares Streamlit-UI-Panel für eine einzelne Heuristik (Sweep,
Savings, Beam Search oder GA): Iterations-Slider, Metriken (Distanz/Fahrzeit/
Kosten/CO2), Animation, PDF-Export und Distanzverlauf-Chart. Wird einmal pro
Heuristik-Tab in app.py aufgerufen.
"""

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from vrp_evaluation import distance_to_business, route_timeline
from vrp_pdf_export import generate_tour_plan_pdf
from vrp_visualization import build_animated_figure, build_figure


def render_heuristic_panel(prefix, label, history, infeasible_construction, depot, coords, ids, demands, D, paths_lookup, node_positions, r_edges_xy, earliest, latest, service, tw_enabled, capacity, speed_kmh, cost_per_km, co2_per_km):
    """Rendert ein komplettes Heuristik-Panel (Slider, Metriken, Animation,
    PDF-Export, Karte, Distanzverlauf) und gibt eine Zusammenfassung für den
    Vergleichs-Tab zurück. `history` ist die Rückgabe von
    local_search_history: eine Liste von (Routen-Snapshot, Distanz,
    Verletzungen) je Verbesserungsschritt."""
    n_steps = len(history)
    initial_dist, initial_viol = history[0][1], history[0][2]
    final_dist, final_viol = history[-1][1], history[-1][2]
    improvement_pct = 0.0 if initial_dist == 0 else 100 * (initial_dist - final_dist) / initial_dist

    if infeasible_construction:
        st.warning(f"⚠️ {label}: Mindestens ein Fahrzeug wird kapazitätsmäßig überladen (zu wenige Fahrzeuge/Kapazität für die Nachfrage).")

    if n_steps > 1:
        auto_play = st.checkbox("▶️ Automatisch abspielen", key=f"{prefix}_auto")
        step = st.slider(
            f"Verbesserungs-Iteration ({label})", 0, n_steps - 1, n_steps - 1, key=f"{prefix}_step",
            help="0 = erste Lösung nach Konstruktion, Maximum = beste gefundene Lösung nach 2-opt + Or-opt.",
        )
    else:
        auto_play = False
        step = 0
        st.info("Die lokale Suche hat keine verbessernde Vertauschung gefunden.")

    dist_delta_pct = 0.0 if initial_dist == 0 else 100 * (history[step][1] - initial_dist) / initial_dist
    hours, cost, co2 = distance_to_business(history[step][1], speed_kmh, cost_per_km, co2_per_km)

    # Volle Breite, mehrere schmale Spalten statt verschachtelt in einer engen
    # Seitenspalte - stapelt sich auf schmalen (mobilen) Bildschirmen sauber.
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Distanz", f"{history[step][1]:.1f} km",
        delta=f"{dist_delta_pct:+.1f} % ggü. Start", delta_color="inverse",
    )
    m2.metric("Fahrzeit (geschätzt)", f"{hours:.1f} h")
    m3.metric("Kraftstoffkosten (geschätzt)", f"{cost:.0f} €")
    m4.metric("CO₂ (geschätzt)", f"{co2:.0f} kg")
    if tw_enabled:
        st.metric("Zeitfenster-Verletzungen", history[step][2], delta=f"{history[step][2] - initial_viol:+d} ggü. Start", delta_color="inverse")
    if tw_enabled:
        st.caption(
            "ℹ️ Bei aktiven Zeitfenstern priorisiert die lokale Suche zuerst die Vermeidung von "
            "Verletzungen und erst danach eine kurze Distanz. Die Distanz kann dadurch steigen, "
            "wenn sich damit Verletzungen beheben lassen."
        )
    st.caption(
        f"ℹ️ Kartendistanz wird als km interpretiert; Fahrzeit/Kosten/CO₂ basieren auf "
        f"{speed_kmh} km/h, {cost_per_km:.2f} €/km und {co2_per_km:.2f} kg CO₂/km (einstellbar in der Seitenleiste)."
    )

    routes_snapshot = history[step][0]

    animate = st.checkbox("🚚 Route animiert abspielen", key=f"{prefix}_animate")
    pdf_bytes = generate_tour_plan_pdf(label, routes_snapshot, ids, demands, D, earliest, latest, service, tw_enabled, capacity, speed_kmh, cost_per_km, co2_per_km)
    st.download_button(
        "📄 Tourenplan als PDF herunterladen", data=pdf_bytes,
        file_name=f"tourenplan_{prefix}.pdf", mime="application/pdf", key=f"{prefix}_pdf_download",
    )

    if animate:
        fig = build_animated_figure(depot, coords, ids, routes_snapshot, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, capacity=capacity)
    else:
        fig = build_figure(depot, coords, ids, routes_snapshot, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, capacity=capacity)
    plot_slot = st.empty()
    plot_slot.plotly_chart(fig, use_container_width=True, key=f"{prefix}_plot_{step}_{animate}")

    if auto_play:
        for s in range(n_steps):
            snap = history[s][0]
            f = build_figure(depot, coords, ids, snap, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled, capacity=capacity)
            plot_slot.plotly_chart(f, use_container_width=True, key=f"{prefix}_auto_{s}")
            time.sleep(0.12)

    st.markdown("**Distanzverlauf über die Verbesserungsschritte**")
    dist_series = [h[1] for h in history]
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=list(range(n_steps)), y=dist_series, mode="lines+markers", line=dict(color="#2563eb")))
    fig_line.add_vline(x=step, line_dash="dash", line_color="gray")
    fig_line.update_layout(xaxis_title="Iteration", yaxis_title="Gesamtdistanz (km)", height=260, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_line, use_container_width=True, key=f"{prefix}_line")

    if tw_enabled:
        st.markdown("**Ankunftszeiten je Fahrzeug (aktueller Schritt)**")
        rows = []
        for v_idx, route in enumerate(routes_snapshot):
            for entry in route_timeline(route, D, earliest, latest, service):
                s = entry["stop"]
                rows.append(
                    {
                        "Fahrzeug": v_idx + 1,
                        "Stopp": ids[s],
                        "Ankunft": round(entry["arrival"], 1),
                        "Start (nach Warten)": round(entry["start"], 1),
                        "Fenster": f"{earliest[s]:.0f}–{latest[s]:.0f}",
                        "Status": "⚠️ verletzt" if entry["violation"] else "✅ ok",
                    }
                )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    return {
        "label": label, "initial_dist": initial_dist, "final_dist": final_dist,
        "initial_viol": initial_viol, "final_viol": final_viol,
        "improvement_pct": improvement_pct, "final_routes": history[-1][0],
        "n_used": sum(1 for r in history[-1][0] if r), "infeasible": infeasible_construction,
    }
