"""
Mini-Tourenplanung (Vehicle Routing Problem) – interaktive Demo
Sebastian Hanisch - Operations Research und Machine Learning

Features:
- Synthetisches Straßennetz (statt Luftlinie) über networkx: Distanzen und
  Routen folgen kürzesten Wegen auf einem gerichteten Graphen, nicht der
  direkten Linie. Optional asymmetrisch (Einbahn-/Umweg-Simulation).
- Vier selbst implementierte Konstruktionsheuristiken im Vergleich: Sweep,
  Clarke-&-Wright-Savings, Beam Search und ein genetischer Algorithmus.
- Verbesserung per lokaler Suche: 2-opt (innerhalb einer Tour) + Or-opt
  (verschiebt 1-2 Stopps auch zwischen Fahrzeugen), lexikografisch zuerst
  nach Zeitfenster-Verletzungen, dann nach Distanz optimiert.
- OR-Tools (Google, Open Source) als fünfter, unabhängiger Solver zum
  Vergleich (Guided Local Search, button-gesteuert wegen Rechenzeit).
- Optionale Zeitfenster pro Stopp (frühester/spätester Start, Servicezeit).
- Geschäftliche Kennzahlen: Fahrzeit, Kraftstoffkosten, CO2 statt abstrakter
  Distanzwerte.
- LKW-Animation (Play/Pause + Scrub-Regler) und PDF-Tourenplan-Export.
- Drei Ein-Klick-Beispielszenarien für Erstbesucher, Permalink (URL spiegelt
  die aktuelle Konfiguration), Feedback-Mechanismus.

Lauffähig mit: streamlit run app.py

Hinweis zum Straßennetz: Es handelt sich um ein prozedural generiertes,
synthetisches Netz (keine echten OpenStreetMap-Daten). Das macht die Demo
unabhängig von externen Kartendiensten/APIs - sie läuft zuverlässig,
schnell und ohne Rate-Limits, auch auf einem kostenlosen Hosting-Tarif.
Für ein reales Kundenprojekt würde man an dieser Stelle echte
Straßennetz-/Routingdaten einbinden (z. B. via OSM/OSRM).

Code-Struktur: Die eigentliche Logik (Algorithmen, Straßennetz, PDF-Export,
Visualisierung, Feedback) liegt in den Modulen vrp_*.py neben dieser Datei.
app.py enthält nur noch den Streamlit-Ablauf (Sidebar, Tabs, Vergleich). Das
hält die Logik unabhängig von einer laufenden Streamlit-Session testbar -
die Testsuite importiert sie direkt, ohne Umweg über Skript-Extraktion.
"""

import time

import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st

from vrp_constants import (
    BEAM_WIDTH,
    BEAM_WIDTH_NO_TW,
    GA_NO_TW_GENERATIONS,
    GA_NO_TW_POP_SIZE,
    GA_SEEDED_GENERATIONS,
    GA_SEEDED_POP_SIZE,
    ORTOOLS_COOLDOWN_BUFFER,
    ORTOOLS_MAX_TIME_LIMIT,
)
from vrp_construction import (
    beam_savings,
    decode_giant_tour,
    genetic_algorithm_construction,
    savings_construction,
    sweep_construction,
)
from vrp_evaluation import distance_to_business, solution_totals
from vrp_feedback import log_feedback
from vrp_local_search import local_search_history
from vrp_network import build_road_network, compute_network_distances, road_edges_xy
from vrp_ortools_solver import solve_with_ortools
from vrp_pdf_export import generate_tour_plan_pdf
from vrp_presets import (
    apply_preset,
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sync_query_params,
)
from vrp_ui_panel import render_heuristic_panel
from vrp_visualization import build_animated_figure, build_figure

st.set_page_config(page_title="Mini-Tourenplanung (VRP) – Sebastian Hanisch", layout="wide")

st.title("🚚 Mini-Tourenplanung (Vehicle Routing Problem)")
st.markdown(
    """
Interaktive Demo zur (LKW-)Tourenplanung mit mehreren Fahrzeugen, Kapazitätsrestriktion,
einem **synthetischen Straßennetz** (optional mit asymmetrischen Einbahn-/Umweg-Abschnitten)
und optionalen **Zeitfenstern** je Stopp. Vier selbst implementierte Heuristiken – **Sweep**,
**Savings**, **Beam Search** und ein **genetischer Algorithmus** – werden mit **2-opt +
Or-opt Local Search** verbessert und zusätzlich mit **Google OR-Tools** verglichen. Routen
lassen sich als **animierter LKW** abspielen und als **PDF-Tourenplan** herunterladen.
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
preset_col1, preset_col2, preset_col3 = st.columns(3)
with preset_col1:
    st.button(
        "📦 Innenstadt-Zustellung", use_container_width=True,
        on_click=apply_preset, args=(15, 3, 27, False, 10),
        help="15 Stopps, 3 Fahrzeuge, moderate Kapazität, keine Zeitfenster.",
    )
with preset_col2:
    st.button(
        "⏰ Enge Zeitfenster", use_container_width=True,
        on_click=apply_preset, args=(12, 3, 25, True, 5),
        help="12 Stopps mit engen Zeitfenstern – zeigt Zielkonflikte zwischen Distanz und Pünktlichkeit.",
    )
with preset_col3:
    st.button(
        "🚚 Große Flotte, knappe Kapazität", use_container_width=True,
        on_click=apply_preset, args=(28, 5, 34, False, 3),
        help="28 Stopps, 5 Fahrzeuge mit knapper Kapazität – viele kurze Touren nötig.",
    )

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen (z. B. für ein Kundengespräch). Hinweis: manuell in der "
    "Stopp-Tabelle bearbeitete Positionen sind darin nicht enthalten, nur die Einstellungen, "
    "aus denen die Stopps erzeugt werden."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    # Wertebereiche kommen aus SETTING_SPECS (vrp_presets.py) - dieselbe Quelle,
    # aus der auch die Permalink-Begrenzung liest. Nicht hier hartkodieren:
    # ein Auseinanderlaufen brächte den Absturz-Bug bei Permalinks mit Werten
    # außerhalb des Slider-Bereichs zurück.
    n_stops = st.slider("Anzahl Lieferstopps", *bounds("n_stops_slider"), key="n_stops_slider")
    n_vehicles = st.slider("Anzahl Fahrzeuge", *bounds("n_vehicles_slider"), key="n_vehicles_slider")
    capacity = st.slider("Kapazität pro Fahrzeug", *bounds("capacity_slider"), key="capacity_slider")
    seed = st.number_input("Zufalls-Seed", step=1, key="seed_input")

    st.markdown("**Depot-Position**")
    depot_x = st.slider("Depot x", 0, 100, 50)
    depot_y = st.slider("Depot y", 0, 100, 50)

    st.markdown("**Straßennetz**")
    n_extra = st.slider("Zusätzliche Kreuzungen", *bounds("n_extra_slider"), key="n_extra_slider", help="Mehr Kreuzungen = feineres, realistischeres Netz.")
    asym_enabled = st.checkbox(
        "🔀 Asymmetrisches Netz (Einbahnstraßen simulieren)", key="asym_checkbox",
        help="Ein Teil der Straßenabschnitte wird in einer Richtung künstlich verlängert (Faktor 1,4–2,5) - Distanzen sind dann nicht mehr symmetrisch (Hin- ≠ Rückweg).",
    )

    st.markdown("**Nebenbedingungen**")
    tw_enabled = st.checkbox("Zeitfenster je Stopp berücksichtigen", key="tw_checkbox")

    st.markdown("**Geschäftliche Kennzahlen**")
    speed_kmh = st.slider(
        "Ø Geschwindigkeit (km/h)", *bounds("speed_slider"), key="speed_slider",
        help="Rechnet Distanz (interpretiert als km) in Fahrzeit um.",
    )
    cost_per_km = st.slider(
        "Kosten pro km (€)", *bounds("cost_slider"), step=0.05, key="cost_slider",
        help="Kraftstoff-/Betriebskosten je gefahrenem Kilometer.",
    )
    co2_per_km = st.slider(
        "CO₂-Ausstoß (kg/km)", *bounds("co2_slider"), step=0.05, key="co2_slider",
        help="Richtwert für einen kleinen/mittleren Diesel-Lieferwagen; je nach Fahrzeugtyp anpassbar.",
    )

    st.button(
        "🎲 Neue Stopps generieren", use_container_width=True, on_click=randomize_seed,
        help="Würfelt einen neuen Zufalls-Seed und erzeugt damit ein komplett neues Szenario - "
        "praktisch, ohne selbst eine neue Seed-Zahl eintippen zu müssen.",
    )

sync_query_params(n_stops, n_vehicles, capacity, seed, tw_enabled, asym_enabled, n_extra, speed_kmh, cost_per_km, co2_per_km)

if "force_regen" not in st.session_state:
    st.session_state.force_regen = False

# Beide Stopp-Generierungs-relevanten Parameter erfassen, nicht nur n_stops.
# (Bug gefunden und behoben - identisches Muster wie in der Packungsoptimierung-
# Demo: vorher wurde nur n_stops geprüft, wodurch ein reiner Seed-Wechsel die
# Stopps NICHT neu erzeugt hat, obwohl die Sidebar bereits den neuen Seed
# anzeigte. n_vehicles, capacity, tw_enabled, asym_enabled etc. beeinflussen
# die Stopp-GENERIERUNG selbst nicht - nur n_stops und seed tun das, siehe
# den RNG-Aufruf direkt unten.)
gen_key = (n_stops, int(seed))
needs_init = (
    "stops" not in st.session_state or st.session_state.force_regen
    or st.session_state.get("gen_key_cache") != gen_key
)
if needs_init:
    rng = np.random.default_rng(int(seed))
    coords0 = rng.uniform(5, 95, size=(n_stops, 2))
    demands0 = rng.integers(1, 10, size=n_stops)
    earliest0 = rng.uniform(0, 120, size=n_stops).round(0)
    width0 = rng.uniform(20, 60, size=n_stops).round(0)
    latest0 = earliest0 + width0
    service0 = rng.integers(0, 6, size=n_stops)
    st.session_state.stops = pd.DataFrame(
        {
            "id": range(1, n_stops + 1),
            "x": coords0[:, 0].round(1),
            "y": coords0[:, 1].round(1),
            "bedarf": demands0,
            "fruehester_start": earliest0,
            "spaetester_start": latest0,
            "servicezeit": service0,
        }
    )
    st.session_state.gen_key_cache = gen_key
    st.session_state.force_regen = False

st.subheader("📍 Lieferstopps (direkt editierbar)")
display_cols = ["id", "x", "y", "bedarf"] + (["fruehester_start", "spaetester_start", "servicezeit"] if tw_enabled else [])
edited = st.data_editor(
    st.session_state.stops,
    num_rows="dynamic",
    use_container_width=True,
    column_order=display_cols,
    column_config={
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "x": st.column_config.NumberColumn("x-Position", min_value=0.0, max_value=100.0, step=1.0),
        "y": st.column_config.NumberColumn("y-Position", min_value=0.0, max_value=100.0, step=1.0),
        "bedarf": st.column_config.NumberColumn("Bedarf", min_value=1, max_value=50, step=1),
        "fruehester_start": st.column_config.NumberColumn("Frühester Start", min_value=0.0, step=5.0),
        "spaetester_start": st.column_config.NumberColumn("Spätester Start", min_value=0.0, step=5.0),
        "servicezeit": st.column_config.NumberColumn("Servicezeit", min_value=0.0, step=1.0),
    },
)
edited = edited.dropna(subset=["x", "y"]).reset_index(drop=True)
edited["bedarf"] = edited["bedarf"].fillna(1)
edited["fruehester_start"] = edited["fruehester_start"].fillna(0)
edited["spaetester_start"] = edited["spaetester_start"].fillna(999)
edited["servicezeit"] = edited["servicezeit"].fillna(0)
if edited["id"].isna().any():
    edited["id"] = range(1, len(edited) + 1)
st.session_state.stops = edited

if len(edited) == 0:
    st.warning("Bitte mindestens einen Lieferstopp anlegen.")
    st.stop()

depot = np.array([float(depot_x), float(depot_y)])
coords = edited[["x", "y"]].to_numpy(dtype=float)
demands = edited["bedarf"].to_numpy(dtype=float)
earliest = edited["fruehester_start"].to_numpy(dtype=float)
latest = edited["spaetester_start"].to_numpy(dtype=float)
service = edited["servicezeit"].to_numpy(dtype=float)
ids = edited["id"].to_numpy()
n_stops_eff = len(edited)

total_demand = demands.sum()
total_capacity = n_vehicles * capacity
if total_demand > total_capacity:
    st.warning(
        f"⚠️ Gesamtbedarf ({total_demand:.0f}) übersteigt die Gesamtkapazität der Flotte "
        f"({total_capacity:.0f}). Mindestens ein Fahrzeug wird überladen."
    )

# Straßennetz + Distanzmatrix
G, _, asymmetric_edges = build_road_network(tuple(depot), tuple(map(tuple, coords)), n_extra, 5, seed, asymmetric=asym_enabled)
cache_key = (tuple(map(tuple, coords)), tuple(depot), n_extra, seed, n_stops_eff, asym_enabled)
D, paths_lookup = compute_network_distances(G, n_stops_eff, cache_key)
node_positions = nx.get_node_attributes(G, "pos")
r_edges_xy = road_edges_xy(G, asymmetric_edges)

# Konstruktion für alle vier Heuristiken (die lokale Suche läuft je Tab)
sweep_routes, sweep_infeasible = sweep_construction(depot, coords, demands, n_vehicles, capacity)
savings_routes, savings_infeasible = savings_construction(n_stops_eff, D, demands, capacity, n_vehicles)
beam_routes, beam_infeasible = beam_savings(n_stops_eff, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled)
ga_routes, ga_infeasible = genetic_algorithm_construction(
    n_stops_eff, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled, seed=int(seed),
)

METHODS = [
    ("sweep", "Sweep", "🔀 Sweep", "Sortiert Stopps nach Polarwinkel um das Depot, weist sie reihum kapazitätskonform Fahrzeugen zu.", sweep_routes, sweep_infeasible),
    ("savings", "Savings", "💰 Savings", "Fusioniert anfängliche Einzeltouren in absteigender Ersparnis-Reihenfolge (Clarke & Wright, 1964).", savings_routes, savings_infeasible),
    ("beam", "Beam Search", "📡 Beam Search", f"Wendet dasselbe Ersparnis-Prinzip wie Savings an, verfolgt aber die {BEAM_WIDTH if tw_enabled else BEAM_WIDTH_NO_TW} besten Fusionsreihenfolgen parallel statt nur eine einzige - eine größere Beam-Breite kann das Ergebnis nachweislich nie verschlechtern.", beam_routes, beam_infeasible),
    ("ga", "Genetischer Algorithmus", "🧬 GA", f"Erkundet denselben Fusions-Entscheidungsraum wie Beam Search, aber evolutionär über {GA_SEEDED_GENERATIONS if tw_enabled else GA_NO_TW_GENERATIONS} Generationen mit {GA_SEEDED_POP_SIZE if tw_enabled else GA_NO_TW_POP_SIZE} Prioritätsreihenfolgen statt mit fester Beam-Breite - siehe README.", ga_routes, ga_infeasible),
]

# Historien einmal zentral berechnen - werden sowohl für die Primäransicht
# ("Ihre optimierte Route") als auch für die Detail-Tabs weiter unten
# gebraucht, nicht doppelt rechnen.
histories = {
    key: local_search_history(routes, D, demands, capacity, earliest, latest, service, tw_enabled)
    for key, _label, _tab_label, _caption, routes, _infeasible in METHODS
}

# Naive Ausgangslage OHNE jede Optimierung: Stopps werden in Eingabereihenfolge
# einfach nacheinander in Fahrzeuge gefüllt (kapazitätskonform), keine
# distanzbewusste Konstruktion, keine lokale Suche. Repräsentiert "was man
# ohne Tourenoptimierung tun würde" - Kontrastfolie für die Primäransicht.
naive_routes, _naive_infeasible = decode_giant_tour(list(range(n_stops_eff)), demands, capacity, n_vehicles)
naive_dist, naive_viol = solution_totals(naive_routes, D, earliest, latest, service, tw_enabled)

# Beste der vier eigenen Methoden bestimmen (OR-Tools bewusst außen vor - ist
# Button-gesteuert und nicht garantiert bereits gelöst; die Primäransicht
# soll ohne Zusatz-Interaktion immer ein vollständiges Ergebnis zeigen).
own_candidates = []
for key, label, _tab_label, _caption, _routes, _construction_infeasible in METHODS:
    final_routes, final_dist, final_viol, final_cap = histories[key][-1]
    own_candidates.append({
        "key": key, "label": label, "routes": final_routes,
        "dist": final_dist, "viol": final_viol, "cap_excess": final_cap,
        "infeasible": final_cap > 0,
    })
# Kapazität steht an erster Stelle (auf Nutzeranfrage ergänzt - vorher wurde
# nur nach Zeitfenster-Verletzungen/Distanz gewählt, eine Methode mit
# Kapazitätsverletzung konnte trotzdem als "beste" ausgewählt werden, wenn
# sie bei Distanz/Zeitfenstern vorne lag).
if tw_enabled:
    best_own = min(own_candidates, key=lambda c: (c["cap_excess"], c["viol"], c["dist"]))
else:
    best_own = min(own_candidates, key=lambda c: (c["cap_excess"], c["dist"]))

st.markdown("## 🎯 Ihre optimierte Route")

naive_hours, naive_cost, naive_co2 = distance_to_business(naive_dist, speed_kmh, cost_per_km, co2_per_km)
best_hours, best_cost, best_co2 = distance_to_business(best_own["dist"], speed_kmh, cost_per_km, co2_per_km)
cost_saved = naive_cost - best_cost
hours_saved = naive_hours - best_hours
co2_saved = naive_co2 - best_co2
violations_not_worse = not tw_enabled or best_own["viol"] <= naive_viol

if best_own["infeasible"]:
    st.warning(
        "⚠️ Mindestens ein Fahrzeug wird bei dieser Konfiguration kapazitätsmäßig überladen - "
        "Fahrzeuge oder Kapazität erhöhen für eine zulässige Lösung."
    )

m1, m2, m3, m4 = st.columns(4)
m1.metric("Distanz", f"{best_own['dist']:.1f} km")
m2.metric("Fahrzeit", f"{best_hours:.1f} h", delta=f"-{hours_saved:.1f} h ggü. unoptimiert", delta_color="inverse")
m3.metric("Kraftstoffkosten", f"{best_cost:.0f} €", delta=f"-{cost_saved:.0f} € ggü. unoptimiert", delta_color="inverse")
m4.metric("CO₂", f"{best_co2:.0f} kg", delta=f"-{co2_saved:.0f} kg ggü. unoptimiert", delta_color="inverse")

if tw_enabled:
    st.caption(f"Zeitfenster-Verletzungen: {best_own['viol']} (unoptimiert: {naive_viol})")

if cost_saved > 0.5 and violations_not_worse:
    st.success(
        f"💶 Gegenüber einer unoptimierten Abarbeitung Ihrer Stopps in Eingabereihenfolge sparen Sie "
        f"hier ca. **{cost_saved:.0f} € Kraftstoffkosten**, **{hours_saved:.1f} Stunden Fahrzeit** und "
        f"**{co2_saved:.0f} kg CO₂** – bei einer einzelnen Tourenplanung. Hochgerechnet auf regelmäßige "
        f"Touren summiert sich das schnell."
    )

fig_best = build_figure(
    depot, coords, ids, best_own["routes"], paths_lookup, node_positions, r_edges_xy,
    D, earliest, latest, service, tw_enabled,
)
st.plotly_chart(fig_best, use_container_width=True, key="primary_best_plot")

pdf_bytes_best = generate_tour_plan_pdf(
    "Optimierte Route", best_own["routes"], ids, demands, D, earliest, latest, service,
    tw_enabled, capacity, speed_kmh, cost_per_km, co2_per_km,
)
st.download_button(
    "📄 Tourenplan als PDF herunterladen", data=pdf_bytes_best,
    file_name="tourenplan_optimiert.pdf", mime="application/pdf", key="primary_pdf_download",
)

st.caption(
    "Ermittelt mit der besten von vier eigenen Optimierungsmethoden für dieses Szenario. "
    "Details zu allen Methoden und dem Vergleich mit Google OR-Tools unten."
)

st.markdown("---")

with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich", expanded=False):
    tab_labels = [m[2] for m in METHODS] + ["🧮 OR-Tools", "📊 Vergleich"]
    tabs = st.tabs(tab_labels)

    summaries = {}
    for (key, label, _tab_label, caption, routes, _construction_infeasible), tab in zip(METHODS, tabs[: len(METHODS)]):
        with tab:
            st.caption(caption)
            history = histories[key]  # bereits oben zentral berechnet
            summaries[key] = render_heuristic_panel(
                key, label, history, depot, coords, ids, demands, D, paths_lookup,
                node_positions, r_edges_xy, earliest, latest, service, tw_enabled, capacity, speed_kmh, cost_per_km, co2_per_km,
            )

    tab_ortools = tabs[len(METHODS)]
    tab_compare = tabs[len(METHODS) + 1]

    ortools_summary = None
    with tab_ortools:
        st.caption(
            "Löst dasselbe Problem (gleiche Straßennetz-Distanzen, gleiche Nebenbedingungen) mit "
            "Googles Open-Source-Solver OR-Tools (Apache 2.0) statt mit unseren eigenen Heuristiken. "
            "OR-Tools nutzt intern eine Guided-Local-Search-Metaheuristik und läuft bis zu einem Zeitlimit."
        )
        time_limit = st.slider(
            "Zeitlimit für den Solver (Sekunden)", 1, ORTOOLS_MAX_TIME_LIMIT, min(3, ORTOOLS_MAX_TIME_LIMIT), key="ortools_time_limit",
            help=f"Auf {ORTOOLS_MAX_TIME_LIMIT}s gedeckelt, um die App bei mehreren gleichzeitigen Besuchern auf dem kostenlosen Hosting-Tarif nicht zu überlasten.",
        )
        current_key = (
            tuple(coords.round(2).flatten()), tuple(depot), n_vehicles, capacity, tw_enabled,
            n_stops_eff, int(seed), n_extra, time_limit, tuple(demands.round(1)),
            tuple(earliest.round(1)) if tw_enabled else None,
            tuple(latest.round(1)) if tw_enabled else None,
            tuple(service.round(1)) if tw_enabled else None,
        )

        if "ortools_last_solve_time" not in st.session_state:
            st.session_state.ortools_last_solve_time = 0.0
        if "ortools_last_time_limit" not in st.session_state:
            st.session_state.ortools_last_time_limit = 0

        solve_clicked = st.button("🧮 Mit OR-Tools lösen", key="ortools_solve_btn")
        if solve_clicked:
            # Cooldown bezieht sich auf das Zeitlimit des TATSÄCHLICH gelaufenen
            # letzten Solves, nicht auf das aktuell eingestellte - sonst ließe sich
            # die Sperre umgehen, indem man nach einem langen Lauf einfach das
            # Zeitlimit herunterregelt und sofort erneut klickt.
            cooldown = st.session_state.ortools_last_time_limit + ORTOOLS_COOLDOWN_BUFFER
            since_last = time.time() - st.session_state.ortools_last_solve_time
            if since_last < cooldown:
                st.warning(
                    f"⏳ Bitte noch {cooldown - since_last:.0f}s warten, bevor Sie erneut lösen "
                    f"(Schutz vor Überlastung bei mehreren gleichzeitigen Besuchern)."
                )
            else:
                with st.spinner(f"OR-Tools sucht bis zu {time_limit}s nach einer Lösung..."):
                    t_start = time.time()
                    or_routes = solve_with_ortools(
                        n_stops_eff, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled, time_limit
                    )
                    elapsed = time.time() - t_start
                # Zeitstempel NACH dem Solve setzen: sonst läuft die Sperrfrist
                # bereits während der (bis zu 5s dauernden) Rechnung ab und die
                # effektive Pause nach Solve-Ende wäre deutlich kürzer als gedacht.
                st.session_state.ortools_last_solve_time = time.time()
                st.session_state.ortools_last_time_limit = time_limit
                st.session_state["ortools_result"] = {"routes": or_routes, "key": current_key, "elapsed": elapsed}

        result = st.session_state.get("ortools_result")
        if result is None:
            st.info("Noch keine Lösung berechnet – auf den Button oben klicken.")
        elif result["routes"] is None:
            st.error(
                "⚠️ OR-Tools hat keine zulässige Lösung gefunden (z. B. reicht die Kapazität "
                "strukturell nicht aus). Fahrzeuge/Kapazität erhöhen und erneut versuchen."
            )
        else:
            if result["key"] != current_key:
                st.warning(
                    "⚠️ Die Eingaben haben sich seit dieser Lösung geändert – das alte Ergebnis "
                    "passt nicht mehr zu den aktuellen Stopps und wird ausgeblendet. Bitte erneut lösen."
                )
            else:
                or_routes = result["routes"]
                or_dist, or_viol = solution_totals(or_routes, D, earliest, latest, service, tw_enabled)

                hours, cost, co2 = distance_to_business(or_dist, speed_kmh, cost_per_km, co2_per_km)
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Gesamtdistanz", f"{or_dist:.1f} km")
                m2.metric("Fahrzeit (geschätzt)", f"{hours:.1f} h")
                m3.metric("Kraftstoffkosten (geschätzt)", f"{cost:.0f} €")
                m4.metric("CO₂ (geschätzt)", f"{co2:.0f} kg")
                m5.metric("Rechenzeit", f"{result['elapsed']:.1f} s")
                if tw_enabled:
                    st.metric("Zeitfenster-Verletzungen", or_viol)

                animate_or = st.checkbox("🚚 Route animiert abspielen", key="ortools_animate")
                pdf_bytes_or = generate_tour_plan_pdf("OR-Tools", or_routes, ids, demands, D, earliest, latest, service, tw_enabled, capacity, speed_kmh, cost_per_km, co2_per_km)
                st.download_button(
                    "📄 Tourenplan als PDF herunterladen", data=pdf_bytes_or,
                    file_name="tourenplan_ortools.pdf", mime="application/pdf", key="ortools_pdf_download",
                )

                if animate_or:
                    fig_or = build_animated_figure(depot, coords, ids, or_routes, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled)
                else:
                    fig_or = build_figure(depot, coords, ids, or_routes, paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled)
                st.plotly_chart(fig_or, use_container_width=True, key=f"ortools_plot_{animate_or}")

                ortools_summary = {
                    "label": "OR-Tools", "initial_dist": or_dist, "final_dist": or_dist,
                    "initial_viol": or_viol, "final_viol": or_viol, "improvement_pct": None,
                    "final_routes": or_routes, "n_used": sum(1 for r in or_routes if r), "infeasible": False,
                }

    with tab_compare:
        st.markdown("### Heuristik-Vergleich")
        candidates = [summaries["sweep"], summaries["savings"], summaries["beam"], summaries["ga"]]
        candidates += [ortools_summary] if ortools_summary else []

        comp_rows = []
        for s in candidates:
            hours, cost, co2 = distance_to_business(s["final_dist"], speed_kmh, cost_per_km, co2_per_km)
            comp_rows.append(
                {
                    "Methode": s["label"],
                    "Startdistanz (km)": f"{s['initial_dist']:.1f}" if s["improvement_pct"] is not None else "–",
                    "Enddistanz (km)": f"{s['final_dist']:.1f}",
                    "Fahrzeit (h)": f"{hours:.1f}",
                    "Kosten (€)": f"{cost:.0f}",
                    "CO₂ (kg)": f"{co2:.0f}",
                    "Verbesserung": f"{s['improvement_pct']:.1f} %" if s["improvement_pct"] is not None else "–",
                    **({"Verletzungen (Start)": s["initial_viol"], "Verletzungen (Ende)": s["final_viol"]} if tw_enabled else {}),
                    "Genutzte Fahrzeuge": s["n_used"],
                    "Kapazität überschritten": "ja" if s["infeasible"] else "nein",
                }
            )
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Sweep, Savings, Beam Search und der genetische Algorithmus werden alle mit derselben "
            "eigenen lokalen Suche (2-opt + Or-opt) verbessert (daher Start-/Enddistanz). OR-Tools "
            "optimiert intern mit einer eigenen Metaheuristik – hier ist nur das Endergebnis ausgewiesen. "
            "Alle Distanzen werden zur fairen Vergleichbarkeit einheitlich mit derselben Bewertungsfunktion "
            f"auf demselben Straßennetz berechnet. Fahrzeit/Kosten/CO₂ basieren auf {speed_kmh} km/h, "
            f"{cost_per_km:.2f} €/km und {co2_per_km:.2f} kg CO₂/km (einstellbar in der Seitenleiste)."
        )

        if tw_enabled:
            best = min(candidates, key=lambda s: (s["final_viol"], s["final_dist"]))
            worst = max(candidates, key=lambda s: (s["final_viol"], s["final_dist"]))
            reason = "wenigste Zeitfenster-Verletzungen, dann kürzeste Distanz"
        else:
            best = min(candidates, key=lambda s: s["final_dist"])
            worst = max(candidates, key=lambda s: s["final_dist"])
            reason = "kürzeste Gesamtdistanz"
        st.markdown(f"➡️ **{best['label']}** schneidet hier am besten ab ({reason}).")

        if best["label"] != worst["label"]:
            best_hours, best_cost, best_co2 = distance_to_business(best["final_dist"], speed_kmh, cost_per_km, co2_per_km)
            worst_hours, worst_cost, worst_co2 = distance_to_business(worst["final_dist"], speed_kmh, cost_per_km, co2_per_km)
            cost_saved = worst_cost - best_cost
            hours_saved = worst_hours - best_hours
            co2_saved = worst_co2 - best_co2
            if cost_saved > 0.5:
                st.info(
                    f"💶 Im Vergleich zur schwächsten Methode hier ({worst['label']}) spart "
                    f"**{best['label']}** ca. **{cost_saved:.0f} € Kraftstoffkosten**, "
                    f"**{hours_saved:.1f} Stunden Fahrzeit** und **{co2_saved:.0f} kg CO₂** – bei einer "
                    f"einzelnen Tourenplanung. Hochgerechnet auf tägliche Touren summiert sich das schnell."
                )

        with st.expander("📈 Was der Vergleich über viele Testläufe hinweg zeigt"):
            st.markdown(
                """
    Die folgenden Zahlen stammen aus systematischen Tests über 15 (bzw. 9 mit Zeitfenstern)
    zufällige Probleminstanzen hinweg – nicht aus der oben aktuell angezeigten Instanz,
    sondern als generelles Muster. Alle vier eigenen Heuristiken durchlaufen dieselbe lokale
    Suche (2-opt + Or-opt), OR-Tools optimiert komplett eigenständig.

    **Ohne Zeitfenster (reine Distanzminimierung):**

    | Methode | Ø Abstand zu OR-Tools | Rechenzeit | Beste Lösung |
    |---|---|---|---|
    | Sweep | +9,5 % (−0,0 % bis +29,1 %) | ~2 ms | 5 / 15 |
    | Savings | +1,2 % (−0,2 % bis +5,0 %) | ~1 ms | 8 / 15 |
    | Beam Search | +0,2 % (−0,2 % bis +2,9 %) | ~340 ms | 13 / 15 |
    | Genet. Algorithmus | +0,3 % (−0,2 % bis +2,9 %) | ~450 ms | 12 / 15 |
    | OR-Tools | Referenz | ~3 s | 14 / 15 |

    *(Summe der "Beste Lösung"-Spalte übersteigt 15: nach identischer lokaler Suche
    (2-opt + Or-opt) konvergieren mehrere Konstruktionsmethoden bei manchen Instanzen auf
    exakt dieselbe Distanz - ein Gleichstand zählt für JEDE beteiligte Methode als "beste
    Lösung" dieser Instanz, nicht nur für eine.)*

    Der Sprung gegenüber einer sehr frühen Version dieser Demo (nur 2-opt, ohne Or-opt) war
    deutlich: Sweep lag damals im Schnitt 37 % hinter OR-Tools. Or-opt schließt einen
    Großteil dieser Lücke, weil schlechte Konstruktionsentscheidungen (Stopps beim falschen
    Fahrzeug) nachträglich korrigiert werden können - und Beam Search sowie der genetische
    Algorithmus liegen inzwischen (nach mehreren grundlegenden Überarbeitungen der
    Konstruktion selbst, siehe README für die vollständige Herleitung) im Schnitt nur noch
    ~0,2-0,3 % hinter OR-Tools, praktisch gleichauf.

    **Ein Bug in Or-opt selbst, in einer frühen Version nachträglich gefunden:** Or-opt
    beim Wiedereinfügen eines Segments in dieselbe Tour übersprang zu viele Positionen als
    "Ursprungsposition" (den gesamten Bereich `[start, start+seg_len]` statt nur die eine
    tatsächliche No-op-Position `start`) – nachrechenbar objektiv falsch. Genauer
    hingeschaut zeigt sich: Bei einer einzelnen Tour gibt es für die meisten dadurch
    blockierten Zielrouten einen redundanten alternativen Suchpfad (z. B. erreicht
    "verschiebe Stopp i" oft dieselbe Zielroute wie "verschiebe Stopp i+1") – der Bug
    änderte also nicht unbedingt, WELCHE Zielrouten grundsätzlich erreichbar sind, sondern
    die Reihenfolge, in der Kandidaten geprüft werden. Da die lokale Suche beim ersten
    verbessernden Zug abbricht (First-Improvement), kann eine andere Prüfreihenfolge trotzdem
    den gesamten weiteren Suchpfad ändern. Ein Beispiel dafür, dass bei Local-Search-Verfahren
    mit "erster Verbesserung" eine andere Prüfreihenfolge nicht automatisch überall zum
    besseren Endergebnis führt, weil die Suche dadurch einen anderen Pfad nimmt.

    **Mit Zeitfenstern (Summe Verletzungen über 9 von 9 Testfällen):**

    Sweep 30 · Savings 33 · Beam Search 31 · Genet. Algorithmus 27 · **OR-Tools 53**

    **Eine ehrliche Überraschung:** Wir haben zunächst erwartet, dass OR-Tools bei
    Zeitfenstern klar vorne liegt. Beim Nachrechnen fiel jedoch zunächst ein echter Bug in
    unserer OR-Tools-Anbindung auf: Das Modell kannte nur die späteste Ankunftszeit, nicht
    die früheste – dadurch konnte der Solver einen Stopp mit spätem Zeitfenster an den
    Tourbeginn legen, was in der Nachbewertung zu unnötigem Warten und Folgeverletzungen
    führte. Nach der Korrektur (früheste Ankunft als Untergrenze im Solver-Modell) sank die
    Verletzungszahl spürbar (von 79 auf 54) – blieb aber trotzdem höher als bei unseren
    eigenen Heuristiken. Weder eine höhere Strafgewichtung noch ein längeres Zeitlimit
    änderten das auf den schwierigsten Testinstanzen: Die Verletzungszahl blieb dort gleich,
    was auf eine echte Suchgrenze hindeutet und nicht auf ein simples Parameter-Problem.

    **Warum das plausibel ist:** Guided Local Search (OR-Tools' Metaheuristik) ist primär
    auf Distanzminimierung ausgelegt und bestraft dafür häufig genutzte Kanten – das hilft,
    aber zielt nicht spezifisch auf Zeitfenster-Verletzungen. Unsere eigene lokale Suche
    sortiert dagegen explizit lexikografisch: Verletzungen zuerst, Distanz erst danach. Bei
    eng terminierten Instanzen kann dieser einfachere, aber zielgerichtete Ansatz einem
    allgemeinen, distanzfokussierten Solver das Wasser reichen.

    **Fazit:** Es gibt kein universell bestes Verfahren. Beam Search und der genetische
    Algorithmus liegen bei reiner Distanzminimierung inzwischen am nächsten an OR-Tools
    (~0,2-0,3 % im Schnitt), aber mit spürbar mehr Rechenzeit als die deutlich günstigeren
    Sweep und Savings - Savings allein bleibt mit nur ~1 % Abstand und praktisch
    kostenloser Rechenzeit eine starke, einfache Wahl, wenn es schnell gehen muss. Bei
    Zeitfenstern hängt es stark von der konkreten Instanz ab. OR-Tools bleibt die richtige
    Wahl, wenn zusätzliche, komplexere Nebenbedingungen (mehrere Depots, Fahrerregeln,
    Pickup & Delivery) dazukommen, die sich in einer eigenen Heuristik nur mit deutlich
    mehr Aufwand sauber abbilden ließen. Welches Verfahren sich für ein reales Problem
    lohnt, hängt von Problemgröße, Zeitbudget und Anforderungen ab – genau diese Abwägung
    ist Teil einer fundierten Beratung.
    """
            )

        st.markdown("**Finale Touren im direkten Vergleich**")
        cols = st.columns(len(candidates))
        for col, s in zip(cols, candidates):
            with col:
                st.caption(f"{s['label']} (final)")
                fig_c = build_figure(depot, coords, ids, s["final_routes"], paths_lookup, node_positions, r_edges_xy, D, earliest, latest, service, tw_enabled)
                st.plotly_chart(fig_c, use_container_width=True, key=f"compare_{s['label']}")

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Straßennetz (statt Luftlinie):** Depot, Stopps und zusätzliche "Kreuzungen" bilden
gemeinsam einen gerichteten Graphen; jeder Knoten ist mit seinen nächsten Nachbarn
verbunden. Alle Distanzen und Routen basieren auf kürzesten Wegen in diesem Netz statt
auf der direkten Luftlinie. Es handelt sich um ein **synthetisches** Netz – für ein
reales Projekt würde man echte Straßennetz-/Routingdaten anbinden.

**Asymmetrisches Netz (optional):** Ist die Option aktiv, wird für rund ein Viertel der
Streckenabschnitte eine Richtung künstlich verlängert (Faktor 1,4–2,5×) – auf der Karte
orange gestrichelt markiert. Das simuliert Einbahnstraßen bzw. Umwege: der Hinweg kann
dann kürzer sein als der Rückweg. Alle Distanzberechnungen im Code sind bereits darauf
ausgelegt, richtungsabhängig nachzuschlagen (auch OR-Tools unterstützt das nativ).

**Vier eigene Konstruktionsheuristiken:**
- *Sweep:* Stopps werden nach Polarwinkel um das Depot sortiert und reihum den
  Fahrzeugen zugewiesen, solange die Kapazität reicht.
- *Savings-Algorithmus (Clarke & Wright):* Startet mit einer Einzeltour je Stopp und
  fusioniert Touren in der Reihenfolge der größten Ersparnis.
- *Beam Search:* Wendet dasselbe Prinzip wie Savings an (Touren nach Ersparnis
  fusionieren), verfolgt aber mehrere (16 ohne Zeitfenster, 8 mit Zeitfenstern - eine
  größere Breite hilft nachweislich, kostet aber Rechenzeit, siehe README)
  vielversprechende Fusionsreihenfolgen parallel statt nur eine einzige - bei jedem
  Fusionsschritt wird sowohl "fusionieren" als auch "überspringen, für später aufheben"
  als Kandidat geführt, als geordnete "Slots", die jeweils sofort das beste verbleibende
  Element aus einem gemeinsamen Kandidatenpool beanspruchen (monobeam-Verfahren, Lemons
  et al. 2022). Dadurch kann eine größere Beam-Breite das Ergebnis **nachweislich nie
  verschlechtern**, nur gleich gut oder besser machen - und ist im Schnitt nur noch
  0,2 % hinter OR-Tools (13 von 15 Testfällen mit der besten eigenen Lösung, siehe
  README).
- *Genetischer Algorithmus:* Erkundet denselben Entscheidungsraum wie Beam Search
  (Savings-Fusionsreihenfolgen), aber evolutionär statt mit fester Beam-Breite - das
  Chromosom ist eine Permutation der Fusions-Prioritäten, nicht der Stopp-Reihenfolge.
  Kreuzung (Order Crossover), Mutation und Elitismus über mehrere Generationen, mit
  Zeitfenster-Prüfung direkt in der Fusionsentscheidung selbst (eine Fusion wird
  abgelehnt, wenn sie die Zeitfenster-Verträglichkeit verschlechtern würde). Praktisch
  gleichwertig zu einer früher getesteten Impf-Variante, aber mehr als doppelt so
  schnell - siehe README für die vollständige Herleitung.

**Verbesserung – 2-opt + Or-opt Local Search:** 2-opt vertauscht Streckenabschnitte
*innerhalb* einer Tour. Or-opt geht weiter: es verschiebt kurze Segmente (1–2 Stopps)
auch *zwischen* Fahrzeugen, wenn das die Lösung verbessert – das kann eine ungünstige
Ausgangszuteilung nachträglich reparieren. Sind Zeitfenster aktiv, zählt zuerst die
Anzahl der Verletzungen (weniger ist besser), erst danach die Distanz.

**Zeitfenster:** Jeder Stopp kann einen frühesten und spätesten Start sowie eine
Servicezeit haben. Kommt ein Fahrzeug zu früh an, wartet es bis zum frühesten Start;
kommt es nach dem spätesten Start an, gilt der Stopp als verletzt (rot markiert).

**LKW-Animation:** Zeigt die fertige Route als bewegtes Symbol statt als statisches
Liniendiagramm – mit Play/Pause und Scrub-Regler. Alle Fahrzeuge starten und enden
synchron (Fortschritt in % der Strecke), auch wenn ihre Touren unterschiedlich lang sind.

**PDF-Tourenplan:** Exportiert die aktuell angezeigte Lösung als einsatzfertiges PDF –
mit Zusammenfassung und einer Stopp-Tabelle je Fahrzeug (inkl. Ankunftszeiten, wenn
Zeitfenster aktiv sind). Direkt aus dem Browser herunterladbar, kein Zwischenspeichern
nötig.

**OR-Tools:** Googles Open-Source-Routing-Solver löst dasselbe Problem komplett
eigenständig – mit einer eigenen Konstruktionsstrategie und einer Guided-Local-Search-
Metaheuristik, innerhalb eines einstellbaren Zeitlimits. Alle Methoden werden am Ende mit
derselben Bewertungsfunktion auf demselben Straßennetz verglichen, damit die Zahlen fair
vergleichbar sind – auch wenn die Suchstrategien intern sehr unterschiedlich arbeiten.

**In echten Projekten** kommen meist weitere Nebenbedingungen (mehrere Depots,
Fahrerarbeitszeiten, dynamische Aufträge) sowie größere, feiner abgestimmte Metaheuristiken
zum Einsatz – das Grundprinzip aus Konstruktion und Verbesserung bleibt aber dasselbe, ob
selbst implementiert oder mit einem Solver wie OR-Tools.
"""
    )

st.markdown("---")

st.markdown("#### War diese Demo hilfreich für Sie?")
if st.session_state.get("feedback_given"):
    vote_text = "👍 positiv" if st.session_state["feedback_given"] == "up" else "👎 negativ"
    st.success(f"Danke für Ihr Feedback ({vote_text})! 🙏")
else:
    fb_col1, fb_col2 = st.columns(2)
    with fb_col1:
        if st.button("👍 Ja", key="feedback_up_btn", use_container_width=True):
            log_feedback("up")
            st.session_state["feedback_given"] = "up"
            st.rerun()
    with fb_col2:
        if st.button("👎 Nein", key="feedback_down_btn", use_container_width=True):
            log_feedback("down")
            st.session_state["feedback_given"] = "down"
            st.rerun()

st.caption(
    "Diese Demo ist Teil des Portfolios von Sebastian Hanisch – Operations Research "
    "und Machine Learning. Interesse an einer maßgeschneiderten Lösung für Ihr "
    "Unternehmen? [Kontakt aufnehmen](#)"
)
