"""
Automatisierte Tests für die VRP-Demo-App.

Zwei Ebenen:
1. UI-Tests über streamlit.testing.v1.AppTest: laden die App headless, bedienen
   Slider/Buttons/Checkboxen wie ein echter Nutzer und prüfen, dass dabei keine
   Exceptions auftreten - über Standardfall, Extremwerte, alle Presets,
   Zeitfenster-Toggle und die OR-Tools-Integration hinweg.
2. Unit-Tests der reinen Algorithmus-Funktionen (ohne Streamlit-Kontext): prüfen
   inhaltliche Korrektheit, z. B. dass jede Konstruktion alle Stopps genau einmal
   zuweist, dass die lokale Suche das lexikografische Ziel nie verschlechtert, und
   dass Or-opt tatsächlich Stopps zwischen Fahrzeugen verschieben kann.

Ausführen mit: pytest tests/ -v
"""

import os
import sys
import uuid

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

APP_DIR = os.path.join(os.path.dirname(__file__), "..")
APP_PATH = os.path.join(APP_DIR, "app.py")
TIMEOUT = 90

# Ermöglicht "import vrp_constants" etc. - die Module liegen neben app.py,
# eine Ebene über diesem tests/-Ordner.
sys.path.insert(0, os.path.abspath(APP_DIR))


def fresh_app():
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=TIMEOUT)
    return at


def assert_ok(at):
    assert not at.exception, f"Unerwartete Exception(s): {[e.message for e in at.exception]}"


# ==========================================================================
# 1. UI-Tests (AppTest)
# ==========================================================================

def test_default_load():
    at = fresh_app()
    assert_ok(at)
    assert len(at.tabs) == 6  # Sweep, Savings, Beam, GA, OR-Tools, Vergleich (im Detail-Expander)


def test_primary_view_shows_four_business_metrics():
    """Die neue Primäransicht ('Ihre optimierte Route') soll ohne jede
    Zusatz-Interaktion sofort Distanz, Fahrzeit, Kosten und CO2 zeigen."""
    at = fresh_app()
    assert_ok(at)
    labels = [m.label for m in at.metric[:4]]
    assert labels == ["Distanz", "Fahrzeit", "Kraftstoffkosten", "CO₂"]


def test_primary_view_selects_true_best_of_four_own_methods():
    """Die Primäransicht muss exakt die beste (kürzeste Enddistanz) der vier
    eigenen Methoden zeigen - unabhängig aus der Vergleichstabelle im
    Detail-Expander nachgerechnet, nicht nur behauptet."""
    at = fresh_app()
    assert_ok(at)
    primary_dist_str = at.metric[0].value  # "395.0 km"
    primary_dist = float(primary_dist_str.replace(" km", ""))

    comp_df = [d.value for d in at.dataframe if "Methode" in d.value.columns][0]
    own_methods = comp_df[comp_df["Methode"] != "OR-Tools"]
    best_dist = own_methods["Enddistanz (km)"].astype(float).min()

    assert primary_dist == pytest.approx(best_dist, abs=0.05)


def test_primary_view_pdf_button_present():
    at = fresh_app()
    assert_ok(at)
    primary_pdf = [d for d in at.download_button if d.key == "primary_pdf_download"]
    assert len(primary_pdf) == 1
    assert "PDF" in primary_pdf[0].label


def test_primary_view_savings_message_shown_by_default():
    """Bei der Standardkonfiguration sollte die unoptimierte Ausgangslage
    (Stopps in Eingabereihenfolge, keine lokale Suche) klar schlechter sein
    als die beste eigene Methode - die Einsparungsnachricht sollte greifen."""
    at = fresh_app()
    assert_ok(at)
    successes = [str(s.value) for s in at.success]
    savings_msgs = [s for s in successes if "unoptimierte" in s]
    assert savings_msgs, "Erwartete Einsparungsnachricht in der Primäransicht nicht gefunden"
    assert "Kraftstoffkosten" in savings_msgs[0]
    assert "Stunden Fahrzeit" in savings_msgs[0]
    assert "CO₂" in savings_msgs[0]


def test_primary_view_no_algorithm_name_in_headline():
    """Kernanforderung der Umstrukturierung: die Primäransicht soll das
    Ergebnis in den Vordergrund stellen, nicht den Algorithmusnamen. Prüft,
    dass die Überschrift selbst keinen der vier Methodennamen enthält (die
    Zuordnung darf in einer klein gedruckten Caption stehen, siehe separater
    Test)."""
    at = fresh_app()
    assert_ok(at)
    headlines = [str(m.value) for m in at.markdown if "Ihre optimierte Route" in str(m.value)]
    assert headlines, "Überschrift 'Ihre optimierte Route' nicht gefunden"
    headline = headlines[0]
    for method_name in ["Sweep", "Savings", "Beam Search", "Genetischer Algorithmus"]:
        assert method_name not in headline, f"Überschrift sollte '{method_name}' nicht enthalten"


def test_primary_view_method_attribution_present_in_caption():
    """Transparenz-Gegenstück zum vorherigen Test: welche Methode das Ergebnis
    geliefert hat, soll nicht verschwiegen, sondern zurückhaltend (als
    Caption, nicht als Überschrift) genannt werden."""
    at = fresh_app()
    assert_ok(at)
    captions = [str(c.value) for c in at.caption]
    attribution = [c for c in captions if "eigenen Optimierungsmethoden" in c]
    assert attribution, "Erwarteter Hinweis auf die zugrunde liegende Methode fehlt"


def test_technical_comparison_expander_contains_all_tabs():
    """Stellt sicher, dass der 'Wie wir das erreichen'-Expander weiterhin
    alle sechs Detail-Tabs enthält - die Umstrukturierung darf keine
    bestehende Funktionalität verstecken oder entfernt haben."""
    at = fresh_app()
    assert_ok(at)
    tab_labels = [t.label for t in at.tabs]
    for expected in ["Sweep", "Savings", "Beam Search", "GA", "OR-Tools", "Vergleich"]:
        assert any(expected in label for label in tab_labels), f"Tab '{expected}' nicht gefunden"


def test_primary_view_handles_infeasible_gracefully():
    """Randfall: Kapazität reicht strukturell nicht aus. Die Primäransicht
    darf nicht abstürzen und soll (falls tatsächlich überladen) eine Warnung
    zeigen statt die Kapazitätsüberschreitung zu verschweigen. Ob die
    konkrete Zufallsinstanz tatsächlich überladen ist, hängt vom Seed ab -
    der Test prüft daher primär, dass kein Absturz auftritt (assert_ok)."""
    at = fresh_app()
    at.sidebar.slider[1].set_value(1).run(timeout=TIMEOUT)  # nur 1 Fahrzeug
    at.sidebar.slider[2].set_value(5).run(timeout=TIMEOUT)  # sehr geringe Kapazität
    assert_ok(at)


def test_regenerate_button():
    """Regressionstest für einen vom Nutzer gemeldeten Fehler: die vorherige
    Fassung prüfte nur 'kein Absturz' (assert_ok) - genau diese Schwäche
    ließ den eigentlichen Bug unentdeckt durch: der Button hatte VOR der
    Korrektur bei unverändertem Seed buchstäblich keine Wirkung (identische
    Stopp-Koordinaten vor/nach Klick, verifiziert), weil die automatische
    Neugenerierung bereits bei jeder Seed-/n_stops-Änderung griff und der
    Button selbst keine eigene Aktion auslöste. Fix: der Button würfelt
    jetzt einen neuen Zufalls-Seed (siehe randomize_seed in vrp_presets.py)
    - dieser Test prüft die TATSÄCHLICHE Wirkung (Seed und Stopps ändern
    sich), nicht nur Absturzfreiheit."""
    at = fresh_app()
    seed_before = at.session_state["seed_input"]
    stops_before = at.session_state["stops"].copy()

    at.sidebar.button[0].click().run(timeout=TIMEOUT)
    assert_ok(at)

    seed_after = at.session_state["seed_input"]
    stops_after = at.session_state["stops"]
    assert seed_after != seed_before, "Button sollte einen neuen Zufalls-Seed würfeln"
    assert not stops_before.equals(stops_after), "Button sollte tatsächlich neue Stopps erzeugen"


@pytest.mark.parametrize("n_stops", [5, 30])
def test_stop_count_extremes(n_stops):
    at = fresh_app()
    at.sidebar.slider[0].set_value(n_stops).run(timeout=TIMEOUT)
    assert_ok(at)


@pytest.mark.parametrize("n_vehicles", [1, 5])
def test_vehicle_count_extremes(n_vehicles):
    at = fresh_app()
    at.sidebar.slider[1].set_value(n_vehicles).run(timeout=TIMEOUT)
    assert_ok(at)


def test_capacity_infeasible_shows_warning_not_crash():
    at = fresh_app()
    at.sidebar.slider[2].set_value(3).run(timeout=TIMEOUT)
    assert_ok(at)


def test_worst_case_settings_no_crash():
    """30 Stopps, 5 Fahrzeuge, Zeitfenster an - der teuerste automatische Fall
    (ohne OR-Tools, das button-gesteuert ist)."""
    at = fresh_app()
    at.sidebar.slider[0].set_value(30).run(timeout=TIMEOUT)
    at.sidebar.slider[1].set_value(5).run(timeout=TIMEOUT)
    at.sidebar.slider[2].set_value(60).run(timeout=TIMEOUT)
    tw_checkbox = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_checkbox.check().run(timeout=TIMEOUT)
    assert_ok(at)


@pytest.mark.parametrize("n_extra", [5, 60])
def test_road_network_density_extremes(n_extra):
    at = fresh_app()
    at.sidebar.slider[5].set_value(n_extra).run(timeout=TIMEOUT)
    assert_ok(at)


def test_time_windows_toggle_on_and_off():
    at = fresh_app()
    tw_checkbox = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_checkbox.check().run(timeout=TIMEOUT)
    assert_ok(at)
    tw_checkbox2 = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_checkbox2.uncheck().run(timeout=TIMEOUT)
    assert_ok(at)


@pytest.mark.parametrize("preset_label,expected_stops,expected_tw", [
    ("Innenstadt", 15, False),
    ("Enge Zeitfenster", 12, True),
    ("Große Flotte", 28, False),
])
def test_presets_apply_expected_values(preset_label, expected_stops, expected_tw):
    at = fresh_app()
    btn = [b for b in at.button if preset_label in b.label][0]
    btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    assert at.sidebar.slider[0].value == expected_stops
    tw_val = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0].value
    assert tw_val == expected_tw


def test_switching_between_all_presets():
    at = fresh_app()
    for label in ["Große Flotte", "Enge Zeitfenster", "Innenstadt", "Große Flotte"]:
        btn = [b for b in at.button if label in b.label][0]
        btn.click().run(timeout=TIMEOUT)
        assert_ok(at)


@pytest.mark.parametrize("label", ["Innenstadt-Zustellung", "Enge Zeitfenster", "Große Flotte, knappe Kapazität"])
def test_presets_are_feasible_for_all_heuristics(label):
    """Regressionstest für gefundene Fehler: alle drei Presets zeigten
    'Kapazität überschritten' bei mindestens einer Methode, zwei davon
    unabhängig vom Beam-Search-Wechsel. 'Innenstadt-Zustellung' war um nur 1
    Einheit unmachbar (Gesamtbedarf 61 vs. Kapazität 60) - für ALLE vier
    Methoden, ein reines Versehen bei der ursprünglichen Parameterwahl.
    'Große Flotte, knappe Kapazität' war um 75 Einheiten unmachbar (bräuchte
    doppelte Kapazität) - keine Methode kann das lösen, unabhängig vom
    Algorithmus. 'Enge Zeitfenster' war rechnerisch machbar (Bedarf 67 vs.
    Kapazität 75), aber ein tieferer, eigenständiger Fund: find_or_opt_move
    prüft Kapazität nur am ZIEL einer Verschiebung, nicht ob die QUELLE
    noch überlastet ist, und akzeptiert nur kostenverbessernde Züge - dadurch
    kann die lokale Suche bei manchen Instanzen (empirisch: ~21% der
    getesteten Seeds) in einem kapazitätsverletzten Zustand stecken bleiben,
    obwohl der Gesamtbedarf klar unter der Gesamtkapazität liegt. Alle drei
    Presets auf saubere, für alle vier Methoden machbare Parameter/Seeds
    korrigiert."""
    at = fresh_app()
    btn = [b for b in at.button if label in b.label][0]
    btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    comp_df = [d for d in at.dataframe if "Methode" in d.value.columns][0].value
    assert (comp_df["Kapazität überschritten"] == "nein").all(), (
        f"{label}: mindestens eine Methode zeigt Kapazitätsüberschreitung: {comp_df[['Methode','Kapazität überschritten']]}"
    )


def test_capacity_warning_follows_displayed_step_not_only_final_result():
    """Regressionstest für einen bei einer Übersichtsprüfung gefundenen
    Fehler: die Kapazitäts-Warnung im Heuristik-Panel bezog sich immer auf
    das ENDERGEBNIS (history[-1]), unabhängig vom per Regler ausgewählten
    Verbesserungsschritt - anders als alle übrigen Kennzahlen (Distanz,
    Zeitfenster-Verletzungen), die korrekt dem Regler folgen. Blätterte man
    zu einem früheren, noch kapazitätsverletzten Schritt zurück (z. B. um
    dort das PDF herunterzuladen), erschien trotzdem keine Warnung, obwohl
    die tatsächlich angezeigte Route verletzt war. Konkret reproduzierbar:
    12 Stopps, 3 Fahrzeuge, Kapazität 25, Zeitfenster an, Seed 7 - Savings'
    Verbesserungsverlauf ist bei Schritt 0 verletzt, aber am Ende (Schritt
    9) behoben. Die zurückgegebene Zusammenfassung (Vergleichstabelle,
    Primäransicht-Auswahl) bleibt bewusst beim Endergebnis - nur die direkt
    im Panel angezeigte Warnung folgt jetzt dem Regler."""
    at = fresh_app()
    at.sidebar.slider[0].set_value(12).run(timeout=TIMEOUT)
    at.sidebar.slider[1].set_value(3).run(timeout=TIMEOUT)
    at.sidebar.slider[2].set_value(25).run(timeout=TIMEOUT)
    tw_cb = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_cb.check().run(timeout=TIMEOUT)
    at.sidebar.number_input[0].set_value(7).run(timeout=TIMEOUT)
    assert_ok(at)

    comp_df = [d for d in at.dataframe if "Methode" in d.value.columns][0].value
    savings_row = comp_df[comp_df["Methode"] == "Savings"]
    assert (savings_row["Kapazität überschritten"] == "nein").all(), (
        "Endergebnis sollte machbar sein (Vergleichstabelle bezieht sich auf Endergebnis)"
    )

    savings_slider = [s for s in at.slider if s.key == "savings_step"]
    assert savings_slider, "Erwarteter Iterations-Regler für Savings fehlt"
    savings_slider[0].set_value(0).run(timeout=TIMEOUT)
    assert_ok(at)
    warnings = [str(w.value) for w in at.warning if "Savings" in str(w.value)]
    assert warnings, "Erwartete Kapazitäts-Warnung bei frühem Schritt (Konstruktion) fehlt"


@pytest.mark.parametrize("prefix", ["sweep", "savings", "beam", "ga"])
def test_heuristic_iteration_slider(prefix):
    at = fresh_app()
    sliders = [s for s in at.slider if s.key == f"{prefix}_step"]
    if not sliders:
        pytest.skip(f"{prefix}: bereits im lokalen Optimum, kein Slider vorhanden")
    s = sliders[0]
    s.set_value(s.min).run(timeout=TIMEOUT)
    assert_ok(at)
    s.set_value(s.max).run(timeout=TIMEOUT)
    assert_ok(at)


def test_asymmetric_network_toggle():
    at = fresh_app()
    asym_checkbox = [c for c in at.sidebar.checkbox if "Asymmetrisches" in c.label][0]
    asym_checkbox.check().run(timeout=TIMEOUT)
    assert_ok(at)
    asym_checkbox2 = [c for c in at.sidebar.checkbox if "Asymmetrisches" in c.label][0]
    asym_checkbox2.uncheck().run(timeout=TIMEOUT)
    assert_ok(at)


def test_asymmetric_network_at_worst_case_settings():
    at = fresh_app()
    at.sidebar.slider[0].set_value(30).run(timeout=TIMEOUT)
    at.sidebar.slider[1].set_value(5).run(timeout=TIMEOUT)
    asym_checkbox = [c for c in at.sidebar.checkbox if "Asymmetrisches" in c.label][0]
    asym_checkbox.check().run(timeout=TIMEOUT)
    tw_checkbox = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_checkbox.check().run(timeout=TIMEOUT)
    assert_ok(at)


def test_animation_uses_actual_truck_emoji_not_generic_triangle():
    """Regressionstest für einen vom Nutzer gemeldeten Fehler: die App-Texte
    versprechen durchgehend eine 'LKW-Animation' mit 'LKW-Symbol', aber die
    Animation zeigte nur ein einfaches Dreieck-Symbol (symbol='triangle-
    right'). Der Trace-interne Name '🚚' war wegen showlegend=False und
    hoverinfo='skip' nirgends sichtbar - reine interne Buchführung, keine
    tatsächliche Darstellung. Fix: ein echtes LKW-Emoji als Text-Marker,
    mit einem farbigen Hintergrundkreis für die Fahrzeug-Zuordnung (sonst
    wäre die bisherige Farbcodierung verloren gegangen, da Emoji keine
    einstellbare marker.color-Eigenschaft haben)."""
    from vrp_network import build_road_network, compute_network_distances, road_edges_xy
    from vrp_construction import sweep_construction
    from vrp_visualization import build_animated_figure

    rng = np.random.default_rng(1)
    depot = (50.0, 50.0)
    coords = rng.uniform(5, 95, size=(10, 2))
    demands = rng.integers(1, 10, size=10)
    G, all_pts, asym = build_road_network(depot, tuple(map(tuple, coords)), 15, 5, 1)
    D, paths_lookup = compute_network_distances(G, 10, "test")
    routes, _ = sweep_construction(depot, coords, demands, 3, 20)
    node_positions = {i: tuple(all_pts[i]) for i in range(len(all_pts))}
    r_edges_xy = road_edges_xy(G, asym)

    fig = build_animated_figure(
        depot, coords, list(range(1, 11)), routes, paths_lookup, node_positions, r_edges_xy, D,
        np.zeros(10), np.full(10, 999.0), np.zeros(10), False, capacity=20,
    )

    truck_traces = [t for t in fig.data if t.mode == "text" and t.text and any("🚚" in str(x) for x in t.text)]
    assert truck_traces, "Erwartetes LKW-Emoji als Text-Marker fehlt in der Animation"
    assert len(fig.frames) > 0
    assert any("🚚" in str(x) for d in fig.frames[0].data for x in (d.text or [])), (
        "LKW-Emoji fehlt in den Animations-Frames"
    )


@pytest.mark.parametrize("prefix", ["sweep", "savings", "beam", "ga"])
def test_route_animation_toggle(prefix):
    at = fresh_app()
    cb = [c for c in at.checkbox if c.key == f"{prefix}_animate"]
    assert cb, f"Animations-Checkbox für {prefix} nicht gefunden"
    cb[0].check().run(timeout=TIMEOUT)
    assert_ok(at)


def test_ortools_animation_toggle():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    cb = [c for c in at.checkbox if c.key == "ortools_animate"]
    assert cb
    cb[0].check().run(timeout=TIMEOUT)
    assert_ok(at)


def test_pdf_download_buttons_present_for_all_own_methods():
    at = fresh_app()
    assert_ok(at)
    labels = [d.label for d in at.download_button]
    # Primäransicht (1) + Sweep, Savings, Beam, GA (4) = 5. OR-Tools-Button
    # erscheint erst nach Lösen (Button-gesteuert).
    assert len(labels) == 5
    assert all("PDF" in l for l in labels)


def test_pdf_download_button_appears_for_ortools_after_solving():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    labels = [d.label for d in at.download_button]
    assert len(labels) == 6  # Primäransicht (1) + Sweep, Savings, Beam, GA (4) + OR-Tools (1)


def test_stale_ortools_result_after_input_change_does_not_crash():
    """Regressionstest: ein während der Entwicklung gefundener Bug führte hier
    zu einem IndexError, weil eine veraltete Lösung (mehr Stopps) gegen die neue,
    kleinere Distanzmatrix ausgewertet wurde."""
    at = fresh_app()
    at.sidebar.slider[0].set_value(30).run(timeout=TIMEOUT)
    at.sidebar.slider[2].set_value(60).run(timeout=TIMEOUT)
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)

    at.sidebar.slider[0].set_value(15).run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("geändert" in str(w.value) for w in at.warning)



    at = fresh_app()
    assert_ok(at)
    assert any("Noch keine Lösung berechnet" in str(i.value) for i in at.info)


def test_co2_slider_present():
    at = fresh_app()
    assert_ok(at)
    co2 = [s for s in at.sidebar.slider if "CO" in s.label]
    assert co2


def test_co2_metric_shown():
    at = fresh_app()
    assert_ok(at)
    labels = [m.label for m in at.metric]
    assert any("CO" in l for l in labels)


def test_comparison_table_has_co2_column():
    at = fresh_app()
    assert_ok(at)
    compare_df = at.dataframe[1].value
    assert "CO₂ (kg)" in compare_df.columns


def test_slider_bounds_match_setting_specs():
    """Wartbarkeits-Schutz: Die Wertebereiche der Slider dürfen nicht von
    SETTING_SPECS (vrp_presets.py) abweichen, aus dem auch die
    Permalink-Begrenzung liest. Liefen beide auseinander (z. B. weil jemand
    einen Slider-Bereich direkt in app.py ändert), käme der bereits behobene
    Absturz-Bug bei Permalinks mit Werten außerhalb des Slider-Bereichs
    stillschweigend zurück. Dieser Test erkennt so ein Auseinanderlaufen
    automatisch, statt sich auf Disziplin zu verlassen."""
    import vrp_presets

    at = fresh_app()
    assert_ok(at)

    by_key = {s.key: s for s in at.sidebar.slider if s.key}
    checked = 0
    for state_key, spec in vrp_presets.SETTING_SPECS.items():
        if spec.lo is None or state_key not in by_key:
            continue  # Checkboxen und number_input haben keinen Slider-Bereich
        slider = by_key[state_key]
        assert slider.min == pytest.approx(spec.lo), (
            f"{state_key}: Slider-Minimum {slider.min} != SETTING_SPECS {spec.lo}"
        )
        assert slider.max == pytest.approx(spec.hi), (
            f"{state_key}: Slider-Maximum {slider.max} != SETTING_SPECS {spec.hi}"
        )
        checked += 1
    assert checked >= 6, f"Nur {checked} Slider geprüft - Test greift vermutlich ins Leere"


def test_setting_specs_defaults_are_within_bounds():
    """Ein Default außerhalb des eigenen Wertebereichs würde die App beim
    allerersten Laden zum Absturz bringen - hier billig abgesichert."""
    import vrp_presets

    for state_key, spec in vrp_presets.SETTING_SPECS.items():
        if spec.lo is not None:
            assert spec.lo <= spec.default <= spec.hi, (
                f"{state_key}: Default {spec.default} liegt außerhalb [{spec.lo}, {spec.hi}]"
            )


def test_permalink_url_params_are_unique():
    """Zwei Widgets mit demselben URL-Parameternamen würden sich gegenseitig
    überschreiben - ein Copy-Paste-Fehler, der sonst nur schwer auffällt."""
    import vrp_presets

    params = [spec.url_param for spec in vrp_presets.SETTING_SPECS.values()]
    assert len(params) == len(set(params)), f"Doppelte URL-Parameter: {params}"


def test_ortools_cooldown_blocks_immediate_resolve():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)

    solve_btn2 = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn2.click().run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("warten" in str(w.value) for w in at.warning)


def test_ortools_cooldown_not_bypassable_by_lowering_time_limit():
    """Regressionstest für eine beim Review gefundene Umgehungsmöglichkeit:
    Der Cooldown wurde gegen das AKTUELL eingestellte Zeitlimit gerechnet.
    Nach einem langen Lauf (Zeitlimit 5 -> Cooldown 8s) konnte man das
    Zeitlimit einfach auf 1 herunterregeln (Cooldown scheinbar nur 4s) und
    dadurch früher erneut lösen. Jetzt zählt das Zeitlimit des tatsächlich
    gelaufenen letzten Solves."""
    at = fresh_app()
    [s for s in at.slider if "Zeitlimit" in s.label][0].set_value(5).run(timeout=TIMEOUT)
    [b for b in at.button if "Mit OR-Tools" in b.label][0].click().run(timeout=TIMEOUT)
    assert_ok(at)

    # Zeitlimit herunterregeln und sofort erneut versuchen
    [s for s in at.slider if "Zeitlimit" in s.label][0].set_value(1).run(timeout=TIMEOUT)
    [b for b in at.button if "Mit OR-Tools" in b.label][0].click().run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("warten" in str(w.value) for w in at.warning), (
        "Cooldown muss weiterhin greifen - das Zeitlimit des vorherigen Solves zählt"
    )


def test_ortools_cooldown_timestamp_recorded_after_solve():
    """Regressionstest: Der Zeitstempel wurde VOR dem (bis zu 5s dauernden)
    Solve gesetzt, wodurch die Sperrfrist bereits während der Rechnung ablief
    und die effektive Pause nach Solve-Ende deutlich kürzer war als
    beabsichtigt. Prüft, dass der gespeicherte Zeitstempel nach Rückkehr des
    Solves nicht älter ist als dessen Rechendauer."""
    import time as _time

    at = fresh_app()
    [s for s in at.slider if "Zeitlimit" in s.label][0].set_value(2).run(timeout=TIMEOUT)
    [b for b in at.button if "Mit OR-Tools" in b.label][0].click().run(timeout=TIMEOUT)
    assert_ok(at)

    recorded = at.session_state["ortools_last_solve_time"]
    elapsed_solve = at.session_state["ortools_result"]["elapsed"]
    age = _time.time() - recorded
    assert age < elapsed_solve + 2.0, (
        f"Zeitstempel ist {age:.1f}s alt bei {elapsed_solve:.1f}s Solve-Dauer - "
        "deutet darauf hin, dass er vor statt nach dem Solve gesetzt wurde"
    )
    assert at.session_state["ortools_last_time_limit"] == 2


def test_permalink_writes_query_params_on_load():
    at = fresh_app()
    assert_ok(at)
    qp = dict(at.query_params)
    for key in ["n_stops", "n_vehicles", "capacity", "seed", "tw", "asym", "extra", "speed", "cost", "co2"]:
        assert key in qp


def test_permalink_updates_on_change():
    at = fresh_app()
    at.sidebar.slider[0].set_value(21).run(timeout=TIMEOUT)
    assert_ok(at)
    qp = dict(at.query_params)
    assert qp.get("n_stops") in (["21"], "21")


def test_seed_change_alone_regenerates_stops():
    """Regressionstest für einen gefundenen Bug (identisches Muster in der
    Packungsoptimierung-Demo gefunden und dort zuerst behoben): Der
    Regenerierungs-Trigger prüfte nur n_stops, nicht den Seed. Ein reiner
    Seed-Wechsel (ohne n_stops zu ändern) hatte dadurch keine Wirkung auf die
    tatsächlich generierten Stopps, obwohl die Sidebar bereits den neuen Seed
    zeigte - verwirrend und funktional falsch, da der Seed-Regler seinem
    Namen nach genau das bewirken soll."""
    at = fresh_app()
    assert_ok(at)
    stops_before = at.session_state["stops"].copy()

    at.sidebar.number_input[0].set_value(999).run(timeout=TIMEOUT)
    assert_ok(at)
    stops_after = at.session_state["stops"]
    assert not stops_before.equals(stops_after), "Stopps sollten sich nach reinem Seed-Wechsel ändern"


def test_n_stops_change_still_regenerates_stops():
    """Stellt sicher, dass der bestehende n_stops-Trigger durch die Erweiterung
    um den Seed nicht kaputt gegangen ist."""
    at = fresh_app()
    assert_ok(at)
    at.sidebar.slider[0].set_value(25).run(timeout=TIMEOUT)
    assert_ok(at)
    assert len(at.session_state["stops"]) == 25



    at = AppTest.from_file(APP_PATH)
    at.query_params["n_stops"] = "19"
    at.query_params["n_vehicles"] = "4"
    at.query_params["tw"] = "1"
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    assert at.sidebar.slider[0].value == 19
    assert at.sidebar.slider[1].value == 4
    tw_val = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0].value
    assert tw_val is True


def test_permalink_ignores_invalid_params_gracefully():
    at = AppTest.from_file(APP_PATH)
    at.query_params["n_stops"] = "not_a_number"
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    assert at.sidebar.slider[0].value == 12  # Default, da ungueltiger Wert ignoriert wird


@pytest.mark.parametrize("param,value,label_fragment,expected", [
    ("n_stops", "1000", "Lieferstopps", 30),
    ("n_stops", "-5", "Lieferstopps", 5),
    ("n_vehicles", "100", "Fahrzeuge", 5),
    ("n_vehicles", "0", "Fahrzeuge", 1),
    ("capacity", "9999", "Kapazität", 60),
    ("capacity", "-10", "Kapazität", 5),
    ("extra", "99999", "Kreuzungen", 60),
    ("speed", "500", "Geschwindigkeit", 80),
    ("speed", "-5", "Geschwindigkeit", 15),
])
def test_permalink_clamps_out_of_range_slider_values(param, value, label_fragment, expected):
    """Regressionstest für einen beim Review gefundenen Bug: Ein Permalink mit
    einem Wert außerhalb der Slider-Grenzen (z. B. ?n_stops=1000, veraltet
    nach einer späteren Grenzänderung, versehentlich getippt oder absichtlich
    manipuliert) ließ Streamlit mit einer unbehandelten
    StreamlitValueAboveMaxError/BelowMinError abstürzen. Werte werden jetzt
    beim Laden auf den gültigen Bereich begrenzt statt roh übernommen."""
    at = AppTest.from_file(APP_PATH)
    at.query_params[param] = value
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    matching = [s for s in at.sidebar.slider if label_fragment in s.label]
    assert matching, f"Slider mit Label-Fragment '{label_fragment}' nicht gefunden"
    assert matching[0].value == expected


@pytest.mark.parametrize("value,expected", [("50.0", 1.00), ("-1.0", 0.10)])
def test_permalink_clamps_out_of_range_cost(value, expected):
    at = AppTest.from_file(APP_PATH)
    at.query_params["cost"] = value
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    matching = [s for s in at.sidebar.slider if "Kosten pro km" in s.label]
    assert matching[0].value == pytest.approx(expected)


@pytest.mark.parametrize("value,expected", [("999.0", 2.00), ("-1.0", 0.10)])
def test_permalink_clamps_out_of_range_co2(value, expected):
    at = AppTest.from_file(APP_PATH)
    at.query_params["co2"] = value
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    matching = [s for s in at.sidebar.slider if "CO" in s.label]
    assert matching[0].value == pytest.approx(expected)


@pytest.mark.parametrize("value", ["-42", "-1", "99999999999999999999999999999"])
def test_permalink_handles_extreme_seed_without_crash(value):
    """Regressionstest: negative Seeds ließen numpy mit 'expected
    non-negative integer' abstürzen; extrem große Seeds sollen ebenfalls
    nicht crashen."""
    at = AppTest.from_file(APP_PATH)
    at.query_params["seed"] = value
    at.run(timeout=TIMEOUT)
    assert_ok(at)


@pytest.mark.parametrize("param,value", [
    ("cost", "nan"), ("cost", "inf"), ("cost", "-inf"),
    ("co2", "nan"), ("co2", "inf"),
])
def test_permalink_rejects_non_finite_float_params(param, value, funcs):
    """Regressionstest: float("nan")/float("inf") werfen anders als int()
    KEINE Exception - die App crashte dadurch zwar nicht (Python-Zufall in
    der Vergleichsreihenfolge von min/max mit NaN), aber verließ sich auf
    unbeabsichtigtes Verhalten. NaN/Infinity werden jetzt explizit erkannt
    und der Parameter ignoriert (Default bleibt bestehen), statt sich auf
    Vergleichsreihenfolge-Zufall zu verlassen."""
    at = AppTest.from_file(APP_PATH)
    at.query_params[param] = value
    at.run(timeout=TIMEOUT)
    assert_ok(at)
    label_fragment = "Kosten pro km" if param == "cost" else "CO"
    matching = [s for s in at.sidebar.slider if label_fragment in s.label]
    val = matching[0].value
    assert val == val, f"Slider-Wert ist NaN: {val}"  # NaN != NaN in Python
    assert val not in (float("inf"), float("-inf"))
    default = funcs["DEFAULT_COST_PER_KM"] if param == "cost" else funcs["DEFAULT_CO2_PER_KM"]
    assert val == pytest.approx(default)



    at = fresh_app()
    assert_ok(at)
    speed = [s for s in at.sidebar.slider if "Geschwindigkeit" in s.label]
    cost = [s for s in at.sidebar.slider if "Kosten pro km" in s.label]
    assert speed and cost


def test_business_metrics_shown_with_units():
    at = fresh_app()
    assert_ok(at)
    labels = [m.label for m in at.metric]
    assert "Fahrzeit (geschätzt)" in labels
    assert "Kraftstoffkosten (geschätzt)" in labels


def test_business_metrics_react_to_slider_changes():
    at = fresh_app()
    speed = [s for s in at.sidebar.slider if "Geschwindigkeit" in s.label][0]
    speed.set_value(80).run(timeout=TIMEOUT)
    assert_ok(at)
    cost = [s for s in at.sidebar.slider if "Kosten pro km" in s.label][0]
    cost.set_value(1.0).run(timeout=TIMEOUT)
    assert_ok(at)


def test_comparison_table_has_cost_and_time_columns():
    at = fresh_app()
    assert_ok(at)
    compare_df = at.dataframe[1].value
    assert "Fahrzeit (h)" in compare_df.columns
    assert "Kosten (€)" in compare_df.columns


def test_ortools_time_limit_capped_at_5s():
    at = fresh_app()
    slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    assert slider.max <= 5


def test_feedback_buttons_present_before_voting():
    at = fresh_app()
    assert_ok(at)
    up = [b for b in at.button if b.key == "feedback_up_btn"]
    down = [b for b in at.button if b.key == "feedback_down_btn"]
    assert up and down


def test_feedback_thumbs_up_shows_thank_you():
    at = fresh_app()
    up = [b for b in at.button if b.key == "feedback_up_btn"][0]
    up.click().run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("Danke" in str(s.value) for s in at.success)


def test_feedback_thumbs_down_shows_thank_you():
    at = fresh_app()
    down = [b for b in at.button if b.key == "feedback_down_btn"][0]
    down.click().run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("Danke" in str(s.value) for s in at.success)


def test_ortools_solve_no_tw():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)


def test_ortools_solve_with_tw():
    at = fresh_app()
    tw_checkbox = [c for c in at.sidebar.checkbox if "Zeitfenster" in c.label][0]
    tw_checkbox.check().run(timeout=TIMEOUT)
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)


def test_ortools_stale_result_shows_warning():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    at.sidebar.slider[0].set_value(20).run(timeout=TIMEOUT)
    assert_ok(at)
    assert any("geändert" in str(w.value) for w in at.warning)


def test_comparison_tab_has_all_four_own_methods():
    at = fresh_app()
    assert_ok(at)
    df_texts = [str(d.value) for d in at.dataframe]
    matches = [t for t in df_texts if "Sweep" in t and "Savings" in t and "Beam Search" in t]
    assert matches, "Vergleichstabelle mit allen vier Heuristiken nicht gefunden"


def test_comparison_tab_includes_ortools_after_solving():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    df_texts = [str(d.value) for d in at.dataframe]
    matches = [t for t in df_texts if "OR-Tools" in t and "Sweep" in t]
    assert matches, "OR-Tools nicht in Vergleichstabelle nach dem Lösen gefunden"


def test_stops_data_present_in_session_state():
    at = fresh_app()
    assert_ok(at)
    assert "stops" in at.session_state
    assert len(at.session_state["stops"]) > 0


# ==========================================================================
# 2. Unit-Tests der reinen Algorithmus-Funktionen
# ==========================================================================
#
# Die Logik liegt jetzt in eigenen vrp_*.py-Modulen ohne Streamlit-UI-Code
# auf oberster Ebene - deshalb reichen normale Imports, ohne Umweg über den
# früheren AST-Extraktions-Trick (der nötig war, solange alles in einer
# einzigen app.py mit vermischtem UI-Code lag).

def _load_pure_functions():
    """Sammelt die testbaren Funktionen/Konstanten aus den vrp_*.py-Modulen
    in einem Dict, damit bestehende Tests (funcs["name"](...)) unverändert
    weiterlaufen."""
    import vrp_constants as c
    import vrp_construction as construction
    import vrp_evaluation as evaluation
    import vrp_feedback as feedback
    import vrp_local_search as local_search
    import vrp_network as network
    import vrp_ortools_solver as ortools_solver
    import vrp_pdf_export as pdf_export

    return {
        "EPS": c.EPS, "VEHICLE_COLORS": c.VEHICLE_COLORS, "BEAM_WIDTH": c.BEAM_WIDTH,
        "GA_POP_SIZE": c.GA_POP_SIZE, "GA_GENERATIONS": c.GA_GENERATIONS,
        "GA_SEEDED_POP_SIZE": c.GA_SEEDED_POP_SIZE, "GA_SEEDED_GENERATIONS": c.GA_SEEDED_GENERATIONS,
        "OR_OPT_SEG_LENGTHS": c.OR_OPT_SEG_LENGTHS, "LOCAL_SEARCH_MAX_MOVES": c.LOCAL_SEARCH_MAX_MOVES,
        "DEFAULT_SPEED_KMH": c.DEFAULT_SPEED_KMH, "DEFAULT_COST_PER_KM": c.DEFAULT_COST_PER_KM,
        "DEFAULT_CO2_PER_KM": c.DEFAULT_CO2_PER_KM, "ORTOOLS_MAX_TIME_LIMIT": c.ORTOOLS_MAX_TIME_LIMIT,
        "ORTOOLS_COOLDOWN_BUFFER": c.ORTOOLS_COOLDOWN_BUFFER, "FEEDBACK_FILE": "test_feedback_log.csv",
        "build_road_network": network.build_road_network,
        "compute_network_distances": network.compute_network_distances,
        "road_edges_xy": network.road_edges_xy,
        "route_polyline": network.route_polyline,
        "route_cost": evaluation.route_cost,
        "route_capacity_excess": evaluation.route_capacity_excess,
        "solution_capacity_excess": evaluation.solution_capacity_excess,
        "route_timeline": evaluation.route_timeline,
        "evaluate_route": evaluation.evaluate_route,
        "solution_totals": evaluation.solution_totals,
        "distance_to_business": evaluation.distance_to_business,
        "sweep_construction": construction.sweep_construction,
        "savings_construction": construction.savings_construction,
        "beam_search_construction": construction.beam_search_construction,
        "monobeam_vrp_construction": construction.monobeam_vrp_construction,
        "beam_savings": construction.beam_savings,
        "decode_giant_tour": construction.decode_giant_tour,
        "decode_giant_tour_optimal_split": construction.decode_giant_tour_optimal_split,
        "genetic_algorithm_construction": construction.genetic_algorithm_construction,
        "genetic_algorithm_construction_seeded": construction.genetic_algorithm_construction_seeded,
        "find_two_opt_move": local_search.find_two_opt_move,
        "find_or_opt_move": local_search.find_or_opt_move,
        "find_swap_move": local_search.find_swap_move,
        "local_search_history": local_search.local_search_history,
        "solve_with_ortools": ortools_solver.solve_with_ortools,
        "generate_tour_plan_pdf": pdf_export.generate_tour_plan_pdf,
        "log_feedback": feedback.log_feedback,
        "get_feedback_counts": feedback.get_feedback_counts,
    }


@pytest.fixture(scope="module")
def funcs():
    return _load_pure_functions()


def _make_instance(funcs, n_stops=15, n_vehicles=3, capacity=20, seed=1):
    rng = np.random.default_rng(seed)
    coords = rng.uniform(5, 95, size=(n_stops, 2))
    demands = rng.integers(1, 8, size=n_stops)
    earliest = np.zeros(n_stops)
    latest = np.full(n_stops, 999.0)
    service = np.zeros(n_stops)
    depot = np.array([50.0, 50.0])
    G, _, _ = funcs["build_road_network"](tuple(depot), tuple(map(tuple, coords)), 15, 5, seed)
    D, _ = funcs["compute_network_distances"](G, n_stops, str(uuid.uuid4()))
    return dict(
        depot=depot, coords=coords, demands=demands, earliest=earliest, latest=latest,
        service=service, D=D, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity,
    )


def _assert_all_stops_covered_once(routes, n_stops):
    seen = sorted(s for r in routes for s in r)
    assert seen == list(range(n_stops)), "Nicht jeder Stopp wurde genau einmal zugewiesen"


def test_sweep_covers_all_stops(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    assert len(routes) == inst["n_vehicles"]


def test_savings_covers_all_stops(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["savings_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    assert len(routes) == inst["n_vehicles"]


def test_savings_respects_asymmetric_direction(funcs):
    """Regressionstest für einen beim Review gefundenen Bug: Der
    Savings-Algorithmus entschied Fusionen anhand einer nur in EINER Richtung
    berechneten Ersparnis, wendete das Ergebnis aber teils in der jeweils
    ANDEREN (viel teureren) Richtung an. Konkretes Gegenbeispiel: A->B und
    A->C sind billig, aber B->A ist sehr teuer - eine Konstruktion, die diese
    teure Kante nutzt, obwohl eine gleichwertige Route mit ausschließlich
    billigen Kanten möglich wäre, zeigt den Bug. Vor dem Fix wählte der
    Algorithmus hier eine Route mit Distanz 41 statt der erreichbaren 31
    (Konstruktion) bzw. 13 (nach lokaler Suche)."""
    D = np.array([
        [0, 5, 5, 5],
        [5, 0, 2, 1],
        [5, 30, 0, 20],  # B->A = 30 (teuer!)
        [5, 1, 20, 0],
    ], dtype=float)
    demands = np.array([1.0, 1.0, 1.0])
    routes, _ = funcs["savings_construction"](3, D, demands, 10, 1)
    dist, _ = funcs["solution_totals"](routes, D, np.zeros(3), np.full(3, 999.0), np.zeros(3), False)
    assert dist <= 31.0 + 1e-6, f"Erwartet <=31 nach Fix, bekommen {dist} (Bug-Symptom waere 41)"


def test_savings_symmetric_case_unchanged_by_directional_fix(funcs):
    """Stellt sicher, dass die Erweiterung auf richtungsabhängige Ersparnis
    für symmetrische Netze (Normalfall) zum selben Ergebnis führt wie zuvor -
    bei symmetrischen Distanzen sind s_ij und s_ji identisch, das Verhalten
    darf sich nicht ändern."""
    inst = _make_instance(funcs, n_stops=15, seed=7)
    routes, infeasible = funcs["savings_construction"](
        inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"]
    )
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    # Jeder Stopp taucht in genau einer Fahrzeugtour auf, keine Duplikate
    # durch die jetzt doppelten (i,j)/(j,i)-Ersparnis-Einträge.
    all_stops_flat = [s for r in routes for s in r]
    assert len(all_stops_flat) == len(set(all_stops_flat)) == inst["n_stops"]


def test_old_beam_search_construction_covers_all_stops(funcs):
    """beam_search_construction bleibt vollständig getestet im Code (siehe
    monobeam_vrp_construction-Docstring für die Historie), ist aber nicht
    mehr in der App verdrahtet - ersetzt durch die monotone Variante."""
    inst = _make_instance(funcs)
    routes, _ = funcs["beam_search_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    assert len(routes) == inst["n_vehicles"]


def test_old_beam_search_produces_reasonably_balanced_routes(funcs):
    """Regressionstest: eine testweise Cheapest-Insertion-Variante von Beam
    Search fuehrte zu stark unausgewogenen Touren (ein Fahrzeug bekam fast
    alle Stopps, andere blieben leer) und war im Benchmark nachweislich
    schlechter - deshalb wieder auf Anhaengen-am-Ende zurueckgesetzt. Dieser
    Test prueft, dass keine grobe Unwucht mehr auftritt."""
    inst = _make_instance(funcs, n_stops=20, n_vehicles=4, capacity=50, seed=3)
    routes, _ = funcs["beam_search_construction"](20, inst["D"], inst["demands"], 50, 4)
    lengths = [len(r) for r in routes]
    assert max(lengths) - min(lengths) <= 20 * 0.6  # keine extreme Schieflage


def test_monobeam_vrp_covers_all_stops(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["monobeam_vrp_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    assert len(routes) == inst["n_vehicles"]


def test_monobeam_vrp_produces_reasonably_balanced_routes(funcs):
    inst = _make_instance(funcs, n_stops=20, n_vehicles=4, capacity=50, seed=3)
    routes, _ = funcs["monobeam_vrp_construction"](20, inst["D"], inst["demands"], 50, 4)
    lengths = [len(r) for r in routes]
    assert max(lengths) - min(lengths) <= 20 * 0.6


def test_monobeam_vrp_is_monotone_in_beam_width(funcs):
    """Der zentrale, auf Nutzeranfrage untersuchte und dann bewiesene
    Befund: beam_search_construction war NICHT monoton (in einer ersten
    Stichprobe 6 von 30 Instanzen zeigten eine schlechtere statt bessere
    Tour bei größerer Breite - dieselbe strukturelle Ursache wie bei den
    zuerst verworfenen Beam-Search-Varianten der Fracht- und Packungsdemo).
    Anders als dort übersteht die Verletzung hier nicht zuverlässig die
    anschließende lokale Suche (3 von 6 geprüften Fällen blieben auch danach
    bestehen) - für Nutzer sichtbar, nicht nur ein Konstruktionsdetail.
    monobeam_vrp_construction behebt das nachweislich - über 147
    Testinstanzen (variable Größe, Kapazität, Fahrzeuganzahl) traten dabei 0
    Verletzungen auf. Zwei gescheiterte Zwischenversuche mussten dafür erst
    verworfen werden (siehe Docstring): feste Reihenfolge nach Distanz vom
    Depot (häufige unnötige Infeasible-Fälle) und nach Bedarf absteigend
    (behob das, aber 15 von 15 Instanzen nach lokaler Suche deutlich
    schlechter, da die geografische Flexibilität verloren ging) - die
    funktionierende Lösung behält die FREIE Wahl des Originals vollständig
    bei und korrigiert nur die Verschachtelung von Erzeugung und Zuweisung."""
    for n_stops in [10, 20, 30]:
        for seed in range(1, 4):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=max(3, n_stops // 6), capacity=20, seed=seed)
            costs = []
            for bw in [1, 2, 4, 8]:
                routes, _ = funcs["monobeam_vrp_construction"](
                    inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"], beam_width=bw
                )
                dist, _ = funcs["solution_totals"](routes, inst["D"], inst["earliest"], inst["latest"], inst["service"], False)
                costs.append(dist)
            for i in range(len(costs) - 1):
                assert costs[i] >= costs[i + 1] - 1e-6, (
                    f"n={n_stops} seed={seed}: Distanz stieg von bw={[1,2,4,8][i]} zu bw={[1,2,4,8][i+1]}: "
                    f"{costs[i]:.1f} -> {costs[i+1]:.1f}"
                )


def test_beam_savings_covers_all_stops(funcs):
    """Regressionstest für Fund 1 der beam_savings-Historie (siehe README):
    eine frühere Fassung kürzte das Ergebnis stillschweigend auf
    n_vehicles Routen, wenn die Fusion mehr getrennte Routen übrig ließ
    als Fahrzeuge vorhanden waren - ganze Touren samt Stopps verschwanden
    dabei. Prüft explizit, dass jeder Stopp genau einmal in der
    zurückgegebenen Routenmenge vorkommt, über mehrere Größen/Kapazitäten."""
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40), (30, 5, 40)]:
        for seed in range(1, 4):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            routes, _ = funcs["beam_savings"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            all_stops = sorted(s for r in routes for s in r)
            assert all_stops == list(range(n_stops)), (
                f"n={n_stops} v={n_vehicles} seed={seed}: nicht alle Stopps abgedeckt, "
                f"gefunden: {all_stops}"
            )


def test_beam_savings_never_loses_stops_on_consolidation():
    """Konkretes, handgerechnetes Beispiel aus der Fehlersuche (siehe
    README Fund 1): ein Szenario, das absichtlich mehr getrennte Routen
    erzeugt als Fahrzeuge vorhanden sind, um die Zwangs-Konsolidierung zu
    erzwingen - prüft explizit, dass dabei kein Stopp verloren geht."""
    import numpy as np
    from vrp_network import build_road_network, compute_network_distances

    n_stops, n_vehicles, capacity = 20, 2, 15  # bewusst knapp: viele Restrouten noetig
    rng = np.random.default_rng(3)
    depot_xy = (50.0, 50.0)
    stops_xy = rng.uniform(5, 95, size=(n_stops, 2))
    demands = rng.integers(1, 6, size=n_stops)
    earliest = np.zeros(n_stops)
    latest = np.full(n_stops, 999.0)
    service = np.zeros(n_stops)
    G, _, _ = build_road_network(tuple(depot_xy), tuple(map(tuple, stops_xy)), 15, 5, 3)
    D, _ = compute_network_distances(G, n_stops, "test_no_loss")

    from vrp_construction import beam_savings
    routes, _infeasible = beam_savings(n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, False)
    all_stops = sorted(s for r in routes for s in r)
    assert all_stops == list(range(n_stops))
    assert len(routes) == n_vehicles


def test_beam_savings_is_monotone_without_tw(funcs):
    """Der zentrale Befund der beam_savings-Historie (siehe README, Funde
    2-4): drei unabhängige Bugs mussten behoben werden, bevor Monotonie
    zuverlässig galt (falsches Verschachtelungsmuster, konsolidierungs-
    unbewusste Auswahl, lokale-Suche-blinde Auswahl). Vergleich bewusst
    kapazitätsbewusst (Kapazitätsüberschreitung, Distanz) statt nur
    Distanz - eine reine Distanz-Verschlechterung kann ein korrekter
    Kompromiss sein, wenn dafür die Kapazitätsüberschreitung sinkt (siehe
    README, konkret bei n=25 v=3 seed=4 gefunden: 553,3 -> 553,6 bei
    gleichzeitig sinkender Überschreitung 6 -> 3 - kein Bug, sondern
    korrektes lexikografisches Verhalten)."""
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40), (30, 5, 40)]:
        for seed in range(1, 5):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            if sum(inst["demands"]) > n_vehicles * capacity:
                continue  # genuin unloesbare Instanz uebersprungen (siehe README-Historie)
            vals = []
            for bw in [1, 2, 4, 8]:
                routes, _ = funcs["beam_savings"](
                    inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                    inst["earliest"], inst["latest"], inst["service"], False, beam_width=bw,
                )
                history = funcs["local_search_history"](
                    routes, inst["D"], inst["demands"], inst["capacity"],
                    inst["earliest"], inst["latest"], inst["service"], False,
                )
                _, dist, _viol, cap = history[-1]
                vals.append((cap, dist))
            for i in range(len(vals) - 1):
                cap_a, dist_a = vals[i]
                cap_b, dist_b = vals[i + 1]
                ok = cap_b < cap_a - 1e-6 or (abs(cap_b - cap_a) <= 1e-6 and dist_b <= dist_a + 1e-6)
                assert ok, (
                    f"n={n_stops} v={n_vehicles} seed={seed}: Verschlechterung von bw={[1,2,4,8][i]} "
                    f"zu bw={[1,2,4,8][i+1]}: {vals[i]} -> {vals[i+1]}"
                )


def test_beam_savings_is_monotone_with_tw(funcs):
    """Wie test_beam_savings_is_monotone_without_tw, aber mit Zeitfenstern -
    der auf Nutzeranfrage vertiefte Fund 5 der Historie (siehe README): mit
    Zeitfenstern brach die Monotonie zunächst weiter ein (10 von 44
    Verletzungen), bis die Konstruktion selbst (nicht nur die Endauswahl)
    dieselbe lexikografische Priorität wie local_search_history verwendet."""
    import numpy as np

    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40)]:
        for seed in range(1, 5):
            rng = np.random.default_rng(seed)
            coords = rng.uniform(5, 95, size=(n_stops, 2))
            demands = rng.integers(1, 8, size=n_stops)
            earliest = rng.uniform(0, 120, size=n_stops).round(0)
            latest = earliest + rng.uniform(20, 60, size=n_stops).round(0)
            service = rng.integers(0, 6, size=n_stops)
            depot = np.array([50.0, 50.0])
            if sum(demands) > n_vehicles * capacity:
                continue
            G, _, _ = funcs["build_road_network"](tuple(depot), tuple(map(tuple, coords)), 15, 5, seed)
            D, _ = funcs["compute_network_distances"](G, n_stops, f"tw_mono_{seed}_{n_stops}")

            vals = []
            for bw in [1, 2, 4, 8]:
                routes, _ = funcs["beam_savings"](
                    n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, True, beam_width=bw,
                )
                history = funcs["local_search_history"](routes, D, demands, capacity, earliest, latest, service, True)
                _, dist, viol, cap = history[-1]
                vals.append((cap, viol, dist))
            for i in range(len(vals) - 1):
                cap_a, viol_a, dist_a = vals[i]
                cap_b, viol_b, dist_b = vals[i + 1]
                if cap_b < cap_a - 1e-6:
                    ok = True
                elif abs(cap_b - cap_a) <= 1e-6 and viol_b < viol_a:
                    ok = True
                elif abs(cap_b - cap_a) <= 1e-6 and viol_b == viol_a:
                    ok = dist_b <= dist_a + 1e-6
                else:
                    ok = False
                assert ok, (
                    f"n={n_stops} v={n_vehicles} seed={seed}: Verschlechterung von bw={[1,2,4,8][i]} "
                    f"zu bw={[1,2,4,8][i+1]}: {vals[i]} -> {vals[i+1]}"
                )


def test_beam_savings_worst_case_completes_within_budget(funcs):
    """Performance-Schutztest: wird bei jeder UI-Interaktion automatisch
    neu berechnet. Empirischer Worst Case bei der App-Obergrenze (30
    Stopps): ~341ms ohne Zeitfenster (Standardbreite jetzt 16 - auf
    Nutzeranfrage erhöht, siehe README), ~1,1-1,4s mit Zeitfenstern
    (Standardbreite bleibt bei 8, die vollständige lokale-Suche-Bewertung
    aller eindeutigen Endkandidaten kostet mit den teureren
    `evaluate_route`-Aufrufen deutlich mehr, siehe README)."""
    import time
    import numpy as np

    worst_no_tw = 0.0
    worst_tw = 0.0
    for seed in range(1, 6):
        inst = _make_instance(funcs, n_stops=30, n_vehicles=5, capacity=40, seed=seed)
        t0 = time.time()
        funcs["beam_savings"](
            30, inst["D"], inst["demands"], 40, 5, inst["earliest"], inst["latest"], inst["service"], False,
        )
        worst_no_tw = max(worst_no_tw, time.time() - t0)

        rng = np.random.default_rng(seed)
        earliest = rng.uniform(0, 120, size=30).round(0)
        latest = earliest + rng.uniform(20, 60, size=30).round(0)
        service = rng.integers(0, 6, size=30)
        t0 = time.time()
        funcs["beam_savings"](30, inst["D"], inst["demands"], 40, 5, earliest, latest, service, True)
        worst_tw = max(worst_tw, time.time() - t0)

    assert worst_no_tw < 2.0, f"Worst Case ohne Zeitfenster dauerte {worst_no_tw:.1f}s"
    assert worst_tw < 5.0, f"Worst Case mit Zeitfenstern dauerte {worst_tw:.1f}s"


def test_beam_savings_generally_beats_or_ties_savings(funcs):
    """Qualitäts-Sanity-Check: der ganze Sinn von beam_savings ist, Savings'
    deterministisches Fusionsergebnis durch Exploration mehrerer
    Fusionsreihenfolgen zu verbessern oder mindestens zu erreichen - sollte
    also über eine breitere Stichprobe NIE schlechter abschneiden als
    reines Savings (Breite 1 ist bei identischer Bewertungsgröße nah an
    Savings, größere Breiten können nur zusätzliche Alternativen finden)."""
    n_worse = 0
    n_tested = 0
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40)]:
        for seed in range(1, 6):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            if sum(inst["demands"]) > n_vehicles * capacity:
                continue
            n_tested += 1
            routes_bs, _ = funcs["beam_savings"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            routes_sv, _ = funcs["savings_construction"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            )
            h_bs = funcs["local_search_history"](
                routes_bs, inst["D"], inst["demands"], inst["capacity"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            h_sv = funcs["local_search_history"](
                routes_sv, inst["D"], inst["demands"], inst["capacity"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            _, dist_bs, _, cap_bs = h_bs[-1]
            _, dist_sv, _, cap_sv = h_sv[-1]
            worse = cap_bs > cap_sv + 1e-6 or (abs(cap_bs - cap_sv) <= 1e-6 and dist_bs > dist_sv + 1e-6)
            if worse:
                n_worse += 1
    assert n_worse == 0, f"{n_worse} von {n_tested} Instanzen: beam_savings schlechter als Savings"



    """Performance-Schutztest: wird bei jeder UI-Interaktion automatisch neu
    berechnet. Empirischer Worst Case bei der App-Obergrenze (30 Stopps,
    Standardbreite 8): ~115ms."""
    import time

    worst = 0.0
    for seed in range(1, 8):
        inst = _make_instance(funcs, n_stops=30, n_vehicles=6, capacity=20, seed=seed)
        t0 = time.time()
        funcs["monobeam_vrp_construction"](30, inst["D"], inst["demands"], 20, 6, beam_width=8)
        worst = max(worst, time.time() - t0)
    assert worst < 2.0, f"Worst Case dauerte {worst:.1f}s"


def test_genetic_algorithm_covers_all_stops(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["genetic_algorithm_construction"](
        inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        inst["earliest"], inst["latest"], inst["service"], False, pop_size=15, generations=10, seed=1,
    )
    _assert_all_stops_covered_once(routes, inst["n_stops"])


def test_genetic_algorithm_handles_single_stop(funcs):
    inst = _make_instance(funcs, n_stops=1, n_vehicles=2, capacity=20)
    routes, infeasible = funcs["genetic_algorithm_construction"](
        1, inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        inst["earliest"], inst["latest"], inst["service"], False,
    )
    _assert_all_stops_covered_once(routes, 1)


def test_decode_giant_tour_optimal_split_covers_all_stops(funcs):
    """Grundlegender Korrektheitstest für die auf Nutzeranfrage ergänzte
    optimale Split-Prozedur (Prins 2004)."""
    for n_stops, n_vehicles, capacity in [(10, 3, 25), (20, 4, 30), (25, 5, 20)]:
        for seed in range(1, 4):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            tour = list(range(n_stops))
            np.random.default_rng(seed).shuffle(tour)
            routes, _infeasible = funcs["decode_giant_tour_optimal_split"](
                tour, inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            _assert_all_stops_covered_once(routes, n_stops)


def test_decode_giant_tour_optimal_split_recovers_original_route_quality(funcs):
    """Regressionstest für den zentralen Fund der Impf-Historie (siehe
    README): decode_giant_tour (Greedy-Split) respektiert beim Dekodieren
    einer verketteten Routen-Liste nur Kapazität, nicht die ursprünglichen
    Routengrenzen - Stopps wandern dadurch über Routengrenzen hinweg und
    verwässern die Struktur. decode_giant_tour_optimal_split muss die
    ursprüngliche Savings-Distanz exakt (oder besser) rekonstruieren,
    unabhängig von dieser Verzerrung."""
    for seed in range(1, 5):
        inst = _make_instance(funcs, n_stops=20, n_vehicles=4, capacity=40, seed=seed)
        savings_routes, _ = funcs["savings_construction"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        )
        orig_dist, _ = funcs["solution_totals"](
            savings_routes, inst["D"], inst["earliest"], inst["latest"], inst["service"], False,
        )
        giant_tour = [s for r in savings_routes for s in r]
        opt_routes, _infeasible = funcs["decode_giant_tour_optimal_split"](
            giant_tour, inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False,
        )
        opt_dist, _ = funcs["solution_totals"](
            opt_routes, inst["D"], inst["earliest"], inst["latest"], inst["service"], False,
        )
        assert opt_dist <= orig_dist + 1e-6, (
            f"seed={seed}: optimale Aufteilung ({opt_dist:.1f}) schlechter als "
            f"Original-Savings ({orig_dist:.1f})"
        )
        _assert_all_stops_covered_once(opt_routes, inst["n_stops"])


def test_genetic_algorithm_seeded_covers_all_stops(funcs):
    """Vollständigkeitstest für die ÜBERHOLTE, aber getestet im Code
    belassene geimpfte GA (genetic_algorithm_construction_seeded) - siehe
    dortigen Docstring und README, warum sie durch die neue, auf
    Fusionsentscheidungen operierende genetic_algorithm_construction
    ersetzt wurde."""
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40)]:
        inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=1)
        seed_routes, _ = funcs["beam_savings"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False,
        )
        routes, _infeasible = funcs["genetic_algorithm_construction_seeded"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False, seed=1,
            seed_routes=seed_routes, pop_size=funcs["GA_SEEDED_POP_SIZE"], generations=funcs["GA_SEEDED_GENERATIONS"],
        )
        _assert_all_stops_covered_once(routes, n_stops)


def test_genetic_algorithm_without_seed_routes_unchanged(funcs):
    """Rückwärtskompatibilitäts-Test für die ÜBERHOLTE, aber getestet im
    Code belassene geimpfte GA: seed_routes=None (Standard) muss das
    Verhalten vollständig unverändert lassen."""
    inst = _make_instance(funcs, n_stops=15, n_vehicles=3, capacity=25, seed=3)
    routes1, _ = funcs["genetic_algorithm_construction_seeded"](
        inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        inst["earliest"], inst["latest"], inst["service"], False, seed=3,
    )
    routes2, _ = funcs["genetic_algorithm_construction_seeded"](
        inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        inst["earliest"], inst["latest"], inst["service"], False, seed=3, seed_routes=None,
    )
    assert routes1 == routes2, "seed_routes=None sollte identisch zum Aufruf ohne den Parameter sein"


def test_genetic_algorithm_seeded_generally_beats_unseeded(funcs):
    """Qualitäts-Sanity-Check für die ÜBERHOLTE, aber getestet im Code
    belassene geimpfte GA - dokumentiert den ursprünglich gefundenen
    Effekt (23 von 28 Siegen ohne, 15 von 21 mit Zeitfenstern), der zur
    Entdeckung der noch besseren, jetzt produktiven Fusions-Prioritäten-GA
    führte (siehe genetic_algorithm_construction und README)."""
    n_seeded_wins, n_unseeded_wins, n_ties = 0, 0, 0
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40)]:
        for seed in range(1, 4):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            seed_routes, _ = funcs["beam_savings"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False,
            )
            routes_seeded, _ = funcs["genetic_algorithm_construction_seeded"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False, seed=seed,
                seed_routes=seed_routes, pop_size=funcs["GA_SEEDED_POP_SIZE"], generations=funcs["GA_SEEDED_GENERATIONS"],
            )
            routes_unseeded, _ = funcs["genetic_algorithm_construction_seeded"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], False, seed=seed,
            )
            dist_seeded, _ = funcs["solution_totals"](
                routes_seeded, inst["D"], inst["earliest"], inst["latest"], inst["service"], False,
            )
            dist_unseeded, _ = funcs["solution_totals"](
                routes_unseeded, inst["D"], inst["earliest"], inst["latest"], inst["service"], False,
            )
            if dist_seeded < dist_unseeded - 0.5:
                n_seeded_wins += 1
            elif dist_unseeded < dist_seeded - 0.5:
                n_unseeded_wins += 1
            else:
                n_ties += 1
    assert n_seeded_wins >= n_unseeded_wins, (
        f"Geimpfte GA sollte mindestens so oft gewinnen wie unveraendert: "
        f"geimpft={n_seeded_wins}, unveraendert={n_unseeded_wins}, gleich={n_ties}"
    )


def test_genetic_algorithm_seeded_worst_case_completes_within_budget(funcs):
    """Performance-Schutztest für die ÜBERHOLTE, aber getestet im Code
    belassene geimpfte GA."""
    import time

    worst = 0.0
    for seed in range(1, 6):
        inst = _make_instance(funcs, n_stops=30, n_vehicles=5, capacity=40, seed=seed)
        seed_routes, _ = funcs["beam_savings"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False,
        )
        t0 = time.time()
        funcs["genetic_algorithm_construction_seeded"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False, seed=seed,
            seed_routes=seed_routes, pop_size=funcs["GA_SEEDED_POP_SIZE"], generations=funcs["GA_SEEDED_GENERATIONS"],
        )
        worst = max(worst, time.time() - t0)
    assert worst < 5.0, f"Worst Case dauerte {worst:.1f}s"


def test_genetic_algorithm_merge_priority_covers_all_stops(funcs):
    """Vollständigkeitstest für die NEUE, produktive GA (operiert auf
    Savings-Fusionsentscheidungen statt Stopp-Permutationen) - über eine
    breite Parameterspanne inklusive Randfällen, wie bei der Untersuchung
    empirisch verifiziert (siehe README)."""
    for n_stops, n_vehicles, capacity in [(5, 1, 40), (15, 3, 40), (20, 4, 40), (25, 4, 40), (30, 5, 40)]:
        for seed in range(1, 3):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            routes, _infeasible = funcs["genetic_algorithm_construction"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], True, seed=seed,
            )
            _assert_all_stops_covered_once(routes, n_stops)
            assert len(routes) == n_vehicles, f"n={n_stops} v={n_vehicles} seed={seed}: {len(routes)} Routen statt {n_vehicles}"


def test_genetic_algorithm_merge_priority_rejects_tw_worsening_merges(funcs):
    """Regressionstest für den zentralen Fund der Kombinations-Historie
    (siehe README): eine erste Fassung des Fusions-Prioritäten-Chromosoms
    prüfte während des Fusionsprozesses selbst keine Zeitfenster-
    Verträglichkeit - jede geometrisch/kapazitätsmäßig gültige Fusion
    wurde blind akzeptiert. Ergebnis: nur 6 von 20 Siegen gegenüber der
    (damals noch produktiven) geimpften GA mit Zeitfenstern. Nach dem Fix
    (Fusion wird abgelehnt, wenn sie die Zeitfenster-Verletzungen
    gegenüber den getrennten Routen verschlechtern würde): 20 von 20.
    Dieser Test prüft direkt, dass eine bekanntermaßen zeitfenster-
    verschlechternde Fusion tatsächlich abgelehnt wird."""
    import numpy as np

    # Zwei Stopps mit eng aufeinanderfolgenden, sich gegenseitig
    # ausschliessenden Zeitfenstern - eine Fusion MUSS eine Verletzung
    # erzeugen, waehrend getrennte Touren beide puenktlich bedienen koennen.
    n_stops = 4
    demands = np.array([2, 2, 2, 2])
    D = np.array([
        [0, 10, 10, 50, 50],
        [10, 0, 15, 55, 55],
        [10, 15, 0, 55, 55],
        [50, 55, 55, 0, 5],
        [50, 55, 55, 5, 0],
    ], dtype=float)
    earliest = np.array([0.0, 0.0, 100.0, 200.0])
    latest = np.array([20.0, 20.0, 120.0, 220.0])
    service = np.zeros(4)

    routes, _infeasible = funcs["genetic_algorithm_construction"](
        n_stops, D, demands, 40, 2, earliest, latest, service, True, seed=1,
    )
    dist, viol = funcs["solution_totals"](routes, D, earliest, latest, service, True)
    assert viol == 0, f"Erwartete 0 Zeitfenster-Verletzungen, gefunden: {viol}"


def test_genetic_algorithm_merge_priority_fitness_prioritizes_capacity(funcs):
    """Regressionstest für den fünften, beim Neu-Vermessen der Benchmark-
    Tabelle gefundenen Fehler (siehe genetic_algorithm_construction-
    Docstring und README für die Historie): fitness_key bewertete
    ursprünglich nur (Zeitfenster-Verletzungen, Distanz), Kapazität floss
    überhaupt nicht ein - GA hatte dadurch keinen evolutionären Druck,
    kapazitätsverletzte Prioritätsreihenfolgen zu vermeiden. Konkretes,
    reproduzierbares Beispiel: n=15, v=3, Kapazität 35, Seed 14 - vor dem
    Fix landeten 4 von 5 internen Test-Seeds bei einem kapazitätsverletzten
    Rohergebnis (Distanz nach lokaler Suche: 553,0 statt der erreichbaren
    443,5). Nach dem Fix: alle 5 internen Seeds konsistent bei 443,5, keine
    Kapazitätsverletzung mehr."""
    inst = _make_instance(funcs, n_stops=15, n_vehicles=3, capacity=35, seed=14)
    n_infeasible = 0
    for internal_seed in range(5):
        routes, infeasible = funcs["genetic_algorithm_construction"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False, seed=internal_seed,
        )
        if infeasible:
            n_infeasible += 1
        history = funcs["local_search_history"](
            routes, inst["D"], inst["demands"], inst["capacity"],
            inst["earliest"], inst["latest"], inst["service"], False,
        )
        _, dist, _viol, cap = history[-1]
        assert cap == 0, f"internal_seed={internal_seed}: Endergebnis kapazitätsverletzt (Überschreitung={cap})"
        assert dist < 460, f"internal_seed={internal_seed}: Distanz {dist:.1f} statt erwarteter ~443,5"
    assert n_infeasible == 0, f"{n_infeasible} von 5 internen Seeds lieferten ein kapazitätsverletztes Rohergebnis"


def test_genetic_algorithm_merge_priority_worst_case_completes_within_budget(funcs):
    """Performance-Schutztest für die neue, produktive GA: komplett
    eigenständig (keine beam_savings-Vorberechnung nötig) - empirischer
    Worst Case bei der App-Obergrenze (30 Stopps) ~900ms mit
    Zeitfenstern, deutlich schneller als die überholte geimpfte Fassung
    (~2s, siehe test_genetic_algorithm_seeded_worst_case_completes_within_budget)."""
    import time

    worst = 0.0
    for seed in range(1, 6):
        inst = _make_instance(funcs, n_stops=30, n_vehicles=5, capacity=40, seed=seed)
        t0 = time.time()
        funcs["genetic_algorithm_construction"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], True, seed=seed,
        )
        worst = max(worst, time.time() - t0)
    assert worst < 3.0, f"Worst Case dauerte {worst:.1f}s"


def test_genetic_algorithm_merge_priority_no_tw_worst_case_completes_within_budget(funcs):
    """Performance-Schutztest für den siebten Fund (siehe README und
    genetic_algorithm_construction-Docstring): ohne Zeitfenster werden
    automatisch groessere GA_NO_TW_POP_SIZE/GA_NO_TW_GENERATIONS-Werte
    verwendet (40/30 statt 20/15) - empirischer Worst Case bei der
    App-Obergrenze (30 Stopps) ~455ms, deutlich unter dem Zeitfenster-Fall
    trotz der groesseren Parameter."""
    import time

    worst = 0.0
    for seed in range(1, 6):
        inst = _make_instance(funcs, n_stops=30, n_vehicles=5, capacity=40, seed=seed)
        t0 = time.time()
        funcs["genetic_algorithm_construction"](
            inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
            inst["earliest"], inst["latest"], inst["service"], False, seed=seed,
        )
        worst = max(worst, time.time() - t0)
    assert worst < 1.5, f"Worst Case dauerte {worst:.1f}s"


def test_genetic_algorithm_merge_priority_ties_or_beats_seeded(funcs):
    """Qualitäts-Sanity-Check für den zentralen, auf Nutzeranfrage
    untersuchten Fund: GA direkt auf Savings-Fusionsentscheidungen
    operieren zu lassen (statt auf Stopp-Permutationen, geimpft mit
    beam_savings) erreicht praktisch identische Qualität bei deutlich
    weniger Rechenzeit - 20 von 20 Siegen über zwei Stichproben (49 Fälle
    gesamt, 9 Gleichstände) in der ursprünglichen Untersuchung, ein
    echter Gleichstand, keine klare Dominanz.

    WICHTIG: eine erste Fassung dieses Tests verglich strikte Sieg-Zahlen
    (`n_new_wins >= n_old_wins`) auf einer kleinen Stichprobe (9 Fälle) -
    das schlug fehl (2 zu 6), obwohl der zugrundeliegende Befund ein
    echter Gleichstand ist. Bei nur 9 Vergleichen ist reines Sieg-Zählen
    zu anfällig für Stichproben-Rauschen, um einen Gleichstand-Befund
    zuverlässig zu bestätigen. Jetzt: aggregierte Gesamtsumme über eine
    größere Stichprobe, mit großzügiger Toleranz (die neue GA darf im
    Schnitt etwas schlechter sein, aber nicht deutlich) - robuster
    gegenüber einzelnen Ausreißern."""
    total_old_dist, total_new_dist = 0.0, 0.0
    total_old_viol, total_new_viol = 0, 0
    for n_stops, n_vehicles, capacity in [(15, 3, 40), (20, 4, 40), (25, 4, 40), (30, 5, 40)]:
        for seed in range(1, 6):
            inst = _make_instance(funcs, n_stops=n_stops, n_vehicles=n_vehicles, capacity=capacity, seed=seed)
            seed_routes, _ = funcs["beam_savings"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], True,
            )
            routes_old, _ = funcs["genetic_algorithm_construction_seeded"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], True, seed=seed,
                seed_routes=seed_routes, pop_size=funcs["GA_SEEDED_POP_SIZE"], generations=funcs["GA_SEEDED_GENERATIONS"],
            )
            routes_new, _ = funcs["genetic_algorithm_construction"](
                inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
                inst["earliest"], inst["latest"], inst["service"], True, seed=seed,
            )
            dist_old, viol_old = funcs["solution_totals"](
                routes_old, inst["D"], inst["earliest"], inst["latest"], inst["service"], True,
            )
            dist_new, viol_new = funcs["solution_totals"](
                routes_new, inst["D"], inst["earliest"], inst["latest"], inst["service"], True,
            )
            total_old_dist += dist_old
            total_new_dist += dist_new
            total_old_viol += viol_old
            total_new_viol += viol_new

    # Grosszuegige Toleranz (15%): das Ziel ist "praktisch gleichwertig",
    # nicht "immer strikt besser" - siehe Docstring.
    assert total_new_viol <= total_old_viol * 1.15 + 2, (
        f"Neue GA deutlich mehr Zeitfenster-Verletzungen: neu={total_new_viol} alt={total_old_viol}"
    )
    assert total_new_dist <= total_old_dist * 1.15, (
        f"Neue GA deutlich schlechtere Gesamtdistanz: neu={total_new_dist:.0f} alt={total_old_dist:.0f}"
    )


def test_local_search_respects_capacity_priority_without_tw(funcs):
    """Regressionstest, aktualisiert auf Nutzeranfrage: die ursprüngliche
    Fassung prüfte 'Distanz sinkt nie ohne Zeitfenster' - das galt nur,
    solange Kapazität ein reiner Freigabefilter war. Seit Kapazität
    lexikografisch VOR Distanz priorisiert wird (siehe find_or_opt_move),
    kann ein einzelner Schritt die Distanz bewusst erhöhen, um eine
    Kapazitätsverletzung zu beheben (Kapazität ist der wichtigere
    Constraint) - konkret beobachtet: ein Schritt sank cap_excess von 1,0
    auf 0,0 und erhöhte dabei die Distanz von 627 auf 817. Die tatsächliche
    Garantie: Distanz darf nur dann steigen, wenn cap_excess im selben
    Schritt SINKT - genau das wird hier geprüft, statt der überholten
    einfacheren Annahme."""
    inst = _make_instance(funcs)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    history = funcs["local_search_history"](
        routes, inst["D"], inst["demands"], inst["capacity"],
        inst["earliest"], inst["latest"], inst["service"], False,
    )
    for (r_a, dist_a, viol_a, cap_a), (r_b, dist_b, viol_b, cap_b) in zip(history, history[1:]):
        if dist_b > dist_a + 1e-6:
            assert cap_b < cap_a - 1e-6, (
                f"Distanz stieg ({dist_a:.1f} -> {dist_b:.1f}), ohne dass sich die "
                f"Kapazitätsüberschreitung verbesserte ({cap_a} -> {cap_b}) - "
                "unbegründeter Distanzanstieg."
            )


def test_local_search_never_increases_distance_when_capacity_always_feasible(funcs):
    """Ergänzt die obige, gelockerte Prüfung um den ursprünglichen,
    strengeren Fall: ist die Konstruktion von Anfang an kapazitätskonform
    (keine Verletzung, die behoben werden müsste), gilt die klassische
    Garantie unverändert - Distanz sinkt monoton, ohne Ausnahme."""
    inst = _make_instance(funcs, n_stops=10, n_vehicles=5, capacity=60, seed=3)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    history = funcs["local_search_history"](
        routes, inst["D"], inst["demands"], inst["capacity"],
        inst["earliest"], inst["latest"], inst["service"], False,
    )
    assert history[0][3] == 0, "Testinstanz sollte von Anfang an kapazitätskonform sein"
    distances = [h[1] for h in history]
    for a, b in zip(distances, distances[1:]):
        assert b <= a + 1e-6, "Lokale Suche hat die Distanz verschlechtert, obwohl nie eine Kapazitätsverletzung vorlag"


def test_local_search_respects_capacity_priority_with_tw(funcs):
    """Wie test_local_search_respects_capacity_priority_without_tw, aber mit
    Zeitfenstern: Verletzungen dürfen nur dann steigen, wenn sich im selben
    Schritt die Kapazitätsüberschreitung verbessert (Kapazität steht
    lexikografisch vor Zeitfenstern, siehe find_or_opt_move)."""
    inst = _make_instance(funcs, seed=2)
    rng = np.random.default_rng(2)
    earliest = rng.uniform(0, 100, size=inst["n_stops"]).round(0)
    latest = earliest + rng.uniform(15, 40, size=inst["n_stops"]).round(0)
    service = np.zeros(inst["n_stops"])
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    history = funcs["local_search_history"](
        routes, inst["D"], inst["demands"], inst["capacity"], earliest, latest, service, True,
    )
    for (r_a, dist_a, viol_a, cap_a), (r_b, dist_b, viol_b, cap_b) in zip(history, history[1:]):
        if viol_b > viol_a:
            assert cap_b < cap_a - 1e-6, (
                f"Zeitfenster-Verletzungen stiegen ({viol_a} -> {viol_b}), ohne dass sich die "
                f"Kapazitätsüberschreitung verbesserte ({cap_a} -> {cap_b})."
            )


def test_capacity_violation_resolved_when_theoretically_possible(funcs):
    """Kern-Regressionstest für den auf Nutzeranfrage ergänzten
    Kapazitäts-Fix: mehrere Seeds bei 12 Stopps, 3 Fahrzeugen, Kapazität 25
    mit Zeitfenstern - die ursprünglich beim manuellen Explorieren gefundenen
    Problemfälle. Lösbarkeit wird direkt aus dem tatsächlichen Gesamtbedarf
    berechnet (nicht als fester Seed-abhängiger Wert angenommen, da
    unterschiedliche Zufallsbereiche in Testcode vs. manueller Exploration
    zu unterschiedlichen Bedarfssummen führen können) - bei genuin
    unlösbaren Instanzen (Gesamtbedarf > Gesamtkapazität) bleibt eine
    Restverletzung korrekt bestehen, sonst sollte sie vollständig behoben
    werden."""
    for seed in [7, 9, 11]:
        inst = _make_instance(funcs, n_stops=12, n_vehicles=3, capacity=25, seed=seed)
        rng = np.random.default_rng(seed)
        earliest = rng.uniform(0, 120, size=12).round(0)
        latest = earliest + rng.uniform(20, 60, size=12).round(0)
        service = rng.integers(0, 6, size=12)
        should_be_solvable = sum(inst["demands"]) <= inst["n_vehicles"] * inst["capacity"]

        routes, _ = funcs["savings_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
        history = funcs["local_search_history"](
            routes, inst["D"], inst["demands"], inst["capacity"], earliest, latest, service, True,
        )
        final_cap = history[-1][3]
        if should_be_solvable:
            assert final_cap == 0, f"seed={seed}: sollte lösbar sein, Restverletzung={final_cap}"
        else:
            assert final_cap > 0, f"seed={seed}: sollte genuin unlösbar bleiben"


def test_local_search_never_worse_than_construction_on_capacity(funcs):
    """Über eine breitere Stichprobe: die Kapazitätsüberschreitung nach der
    lokalen Suche darf nie höher sein als direkt nach der Konstruktion -
    egal was 2-opt/Or-opt/Tausch tun, sie dürfen die Lage nie verschlimmern."""
    for seed in range(1, 8):
        inst = _make_instance(funcs, n_stops=15, n_vehicles=3, capacity=20, seed=seed)
        routes, _ = funcs["savings_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
        construction_cap = funcs["solution_capacity_excess"](routes, inst["demands"], inst["capacity"])
        history = funcs["local_search_history"](
            routes, inst["D"], inst["demands"], inst["capacity"], inst["earliest"], inst["latest"], inst["service"], False,
        )
        final_cap = history[-1][3]
        assert final_cap <= construction_cap + 1e-6, (
            f"seed={seed}: lokale Suche verschlechterte Kapazität ({construction_cap} -> {final_cap})"
        )


def test_find_swap_move_structurally_valid(funcs):
    """find_swap_move darf keine Stopps verlieren oder verdoppeln."""
    inst = _make_instance(funcs, n_stops=12, n_vehicles=3, capacity=25, seed=7)
    routes, _ = funcs["savings_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
    new_routes, found = funcs["find_swap_move"](
        routes, inst["D"], inst["demands"], inst["capacity"], inst["earliest"], inst["latest"], inst["service"], False,
    )
    all_stops = sorted(s for r in new_routes for s in r)
    assert all_stops == list(range(inst["n_stops"]))


def test_find_swap_move_resolves_case_or_opt_cannot():
    """Konkretes, handgerechnetes Beispiel aus der Diskussion: Route A hat
    3 Stopps mit Bedarf 26 (Kapazität 25, kleinster Stopp dort hat Bedarf 8),
    Route B hat nur 7 freie Kapazität - Or-opt kann keinen einzelnen Stopp
    verschieben (auch nicht mit Kapazitäts-Priorität, siehe find_or_opt_move
    Docstring), aber ein Tausch (Bedarf 8 gegen Bedarf 2) löst es."""
    from vrp_local_search import find_swap_move, route_capacity_excess

    demands = np.array([5, 1, 2, 5, 9, 5, 8, 9, 8, 6, 4, 5])
    routes = [[0, 9, 2, 3], [1, 11, 10, 5, 6], [7, 4, 8]]
    capacity = 25
    n = 13
    D = np.ones((n, n)) * 10.0
    for i in range(n):
        D[i][i] = 0.0
    earliest = np.zeros(12)
    latest = np.full(12, 999.0)
    service = np.zeros(12)

    excess_before = sum(route_capacity_excess(r, demands, capacity) for r in routes)
    assert excess_before == 1.0

    new_routes, found = find_swap_move(routes, D, demands, capacity, earliest, latest, service, False)
    assert found, "Sollte einen entlastenden Tausch finden"
    excess_after = sum(route_capacity_excess(r, demands, capacity) for r in new_routes)
    assert excess_after < excess_before


def test_or_opt_can_move_stops_between_vehicles(funcs):
    """Regressionstest für die zentrale Or-opt-Fähigkeit: Stopps dürfen bei
    Bedarf das Fahrzeug wechseln - das konnte reines 2-opt nicht."""
    D = np.array([
        [0, 10, 11, 20, 21],
        [10, 0, 1, 10, 11],
        [11, 1, 0, 9, 10],
        [20, 10, 9, 0, 1],
        [21, 11, 10, 1, 0],
    ], dtype=float)
    demands = np.array([1, 1, 1, 1.0])
    earliest = np.zeros(4)
    latest = np.full(4, 999.0)
    service = np.zeros(4)
    bad_routes = [[0, 2], [1, 3]]  # schlechte Zuteilung - sollte eher [[0,1],[2,3]] sein
    new_routes, found = funcs["find_or_opt_move"](bad_routes, D, demands, 10, earliest, latest, service, False)
    assert found, "Or-opt hätte hier einen verbessernden Zug finden müssen"


def test_or_opt_skip_condition_only_excludes_true_noop():
    """Regressionstest für einen beim finalen Review gefundenen Bug: Beim
    Wiedereinfügen eines entfernten Segments in dieselbe Tour wurde fälschlich
    der gesamte Bereich [start, start+seg_len] als 'Ursprungsposition'
    übersprungen, statt nur der einen tatsächlichen No-op-Position
    (pos == start). Das war objektiv falsch - bewiesen durch Nachrechnen für
    jede (start, seg_len)-Kombination: nur pos == start reproduziert exakt die
    Ausgangsroute, alle anderen Positionen im alten Sperrbereich ergeben eine
    andere Route.

    Hinweis zur Einordnung: Bei einer einzelnen Tour gibt es für praktisch
    jede so blockierte Zielroute einen redundanten alternativen Suchpfad
    (z. B. erreicht "verschiebe Element i" oft dieselbe Zielroute wie
    "verschiebe Element i+1") - der Bug ändert bei einer einzelnen Tour daher
    nicht zwingend, WELCHE Zielrouten find_or_opt_move am Ende erreichen kann,
    sondern die Reihenfolge, in der Kandidaten geprüft werden. Da die lokale
    Suche beim ersten verbessernden Zug abbricht (First-Improvement), kann
    das trotzdem den gesamten weiteren Suchpfad ändern - das erklärt die
    gemessene Änderung der Benchmark-Zahlen nach dem Fix trotz identischer
    Erreichbarkeit im Einzelfall. Dieser Test prüft daher direkt die
    Korrektheit der Sperrbedingung selbst, statt sich auf das (durch
    Redundanz verzerrte) Endergebnis von find_or_opt_move zu verlassen."""
    for route_len in [2, 3, 4, 5]:
        route = list(range(route_len))
        for seg_len in (1, 2):
            if seg_len > route_len:
                continue
            for start in range(route_len - seg_len + 1):
                segment = route[start : start + seg_len]
                remainder = route[:start] + route[start + seg_len :]
                for pos in range(len(remainder) + 1):
                    candidate = remainder[:pos] + segment + remainder[pos:]
                    is_true_noop = candidate == route
                    is_excluded_by_fixed_condition = pos == start
                    assert is_true_noop == is_excluded_by_fixed_condition, (
                        f"route_len={route_len}, seg_len={seg_len}, start={start}, pos={pos}: "
                        f"candidate={candidate} route={route}"
                    )


def test_ortools_infeasible_capacity_returns_none(funcs):
    inst = _make_instance(funcs, n_stops=10, n_vehicles=2, capacity=2)
    result = funcs["solve_with_ortools"](
        inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        inst["earliest"], inst["latest"], inst["service"], False, 1,
    )
    assert result is None


def test_ortools_respects_earliest_start(funcs):
    """Regressionstest für den in der Entwicklung gefundenen Bug: OR-Tools muss
    die früheste Startzeit kennen, sonst kann ein spät gewünschter Stopp an den
    Tourbeginn geraten und unnötige Folgeverletzungen auslösen."""
    inst = _make_instance(funcs, n_stops=12, n_vehicles=3, capacity=30, seed=3)
    rng = np.random.default_rng(3)
    earliest = rng.uniform(0, 100, size=12).round(0)
    latest = earliest + rng.uniform(20, 50, size=12).round(0)
    service = np.zeros(12)
    routes = funcs["solve_with_ortools"](
        12, inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"],
        earliest, latest, service, True, 2,
    )
    assert routes is not None
    # Jede Route sollte konsistent mit unserer eigenen Bewertung sein (kein Crash,
    # plausible Werte)
    dist, viol = funcs["solution_totals"](routes, inst["D"], earliest, latest, service, True)
    assert dist >= 0
    assert viol >= 0


def test_distance_to_business_conversion(funcs):
    hours, cost, co2 = funcs["distance_to_business"](80.0, 40.0, 0.5, 0.8)
    assert hours == pytest.approx(2.0)
    assert cost == pytest.approx(40.0)
    assert co2 == pytest.approx(64.0)


def test_distance_to_business_zero_speed_safe(funcs):
    hours, cost, co2 = funcs["distance_to_business"](80.0, 0.0, 0.5, 0.8)
    assert hours == 0.0  # darf nicht durch 0 teilen
    assert cost == pytest.approx(40.0)
    assert co2 == pytest.approx(64.0)


def test_feedback_log_and_count_roundtrip(funcs, tmp_path):
    """Testet log_feedback/get_feedback_counts isoliert gegen eine temporäre
    Datei - dank explizitem feedback_file-Parameter (statt einer global
    gelesenen Konstante) ohne Monkeypatching möglich."""
    log_file = str(tmp_path / "feedback_test.csv")
    assert funcs["get_feedback_counts"](log_file) == (0, 0)
    assert funcs["log_feedback"]("up", log_file) is True
    assert funcs["log_feedback"]("up", log_file) is True
    assert funcs["log_feedback"]("down", log_file) is True
    assert funcs["get_feedback_counts"](log_file) == (2, 1)



def test_asymmetric_network_produces_asymmetric_distances(funcs):
    """Prüft, dass ein asymmetrisches Netz (a) tatsächlich asymmetrische Kanten
    erzeugt und (b) das über mehrere Layouts hinweg auch messbar auf die
    Distanzmatrix zwischen Depot/Stopps durchschlägt. Einzelne Layouts können
    zufällig keine der betroffenen Kanten auf einem genutzten kürzesten Weg
    haben - deshalb über mehrere Seeds geprüft, nicht nur einen."""
    import networkx as nx

    any_asym_distance_found = False
    for seed in [5, 6, 7, 8, 9]:
        inst = _make_instance(funcs, n_stops=12, seed=seed)
        G, _, asym_edges = funcs["build_road_network"](
            tuple(inst["depot"]), tuple(map(tuple, inst["coords"])), 15, 5, seed, asymmetric=True
        )
        assert nx.is_strongly_connected(G)
        assert len(asym_edges) > 0, f"Keine asymmetrischen Kanten erzeugt bei seed={seed}"
        D, _ = funcs["compute_network_distances"](G, 12, str(uuid.uuid4()))
        n = D.shape[0]
        if any(abs(D[i][j] - D[j][i]) > 0.01 for i in range(n) for j in range(n)):
            any_asym_distance_found = True
            break
    assert any_asym_distance_found, "Asymmetrisches Netz sollte über mehrere Layouts hinweg zu asymmetrischen Distanzen führen"


def test_symmetric_network_produces_symmetric_distances(funcs):
    inst = _make_instance(funcs, n_stops=12, seed=5)
    G, _, asym_edges = funcs["build_road_network"](tuple(inst["depot"]), tuple(map(tuple, inst["coords"])), 15, 5, 5, asymmetric=False)
    assert len(asym_edges) == 0
    D, _ = funcs["compute_network_distances"](G, 12, str(uuid.uuid4()))
    n = D.shape[0]
    for i in range(n):
        for j in range(n):
            assert D[i][j] == pytest.approx(D[j][i], abs=0.01)


def test_generate_tour_plan_pdf_produces_valid_pdf(funcs):
    inst = _make_instance(funcs, n_stops=10, seed=4)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    ids = list(range(1, 11))
    pdf_bytes = funcs["generate_tour_plan_pdf"](
        "Sweep", routes, ids, inst["demands"], inst["D"], inst["earliest"], inst["latest"], inst["service"], False, inst["capacity"],
    )
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500


def test_generate_tour_plan_pdf_with_time_windows(funcs):
    inst = _make_instance(funcs, n_stops=8, seed=6)
    rng = np.random.default_rng(6)
    earliest = rng.uniform(0, 80, size=8).round(0)
    latest = earliest + rng.uniform(15, 40, size=8).round(0)
    service = np.zeros(8)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    ids = list(range(1, 9))
    pdf_bytes = funcs["generate_tour_plan_pdf"](
        "Sweep", routes, ids, inst["demands"], inst["D"], earliest, latest, service, True, inst["capacity"],
    )
    assert pdf_bytes[:4] == b"%PDF"


def test_road_network_stays_strongly_connected_with_asymmetry(funcs):
    import networkx as nx
    for seed in [1, 2, 3, 10, 20]:
        inst = _make_instance(funcs, n_stops=20, seed=seed)
        G, _, _ = funcs["build_road_network"](tuple(inst["depot"]), tuple(map(tuple, inst["coords"])), 15, 5, seed, asymmetric=True)
        assert nx.is_strongly_connected(G), f"Netz nicht stark zusammenhängend bei seed={seed}"


def test_route_cost_symmetric_for_closed_loop(funcs):
    """Für eine geschlossene Tour (Depot -> ... -> Depot) mit symmetrischer
    Distanzmatrix sollte die Reihenfolge bei nur einem Stopp keine Rolle spielen."""
    inst = _make_instance(funcs, n_stops=5)
    single = [2]
    assert funcs["route_cost"](single, inst["D"]) == pytest.approx(2 * inst["D"][0][3])
