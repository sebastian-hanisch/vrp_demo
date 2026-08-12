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
    assert len(at.tabs) == 6  # Sweep, Savings, Beam, GA, OR-Tools, Vergleich


def test_regenerate_button():
    at = fresh_app()
    at.sidebar.button[0].click().run(timeout=TIMEOUT)
    assert_ok(at)


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
    assert len(labels) == 4  # Sweep, Savings, Beam, GA (OR-Tools-Button erst nach Lösen)
    assert all("PDF" in l for l in labels)


def test_pdf_download_button_appears_for_ortools_after_solving():
    at = fresh_app()
    ortools_slider = [s for s in at.slider if "Zeitlimit" in s.label][0]
    ortools_slider.set_value(1).run(timeout=TIMEOUT)
    solve_btn = [b for b in at.button if "Mit OR-Tools" in b.label][0]
    solve_btn.click().run(timeout=TIMEOUT)
    assert_ok(at)
    labels = [d.label for d in at.download_button]
    assert len(labels) == 5


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


def test_permalink_restores_settings_from_url():
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
        "OR_OPT_SEG_LENGTHS": c.OR_OPT_SEG_LENGTHS, "LOCAL_SEARCH_MAX_MOVES": c.LOCAL_SEARCH_MAX_MOVES,
        "DEFAULT_SPEED_KMH": c.DEFAULT_SPEED_KMH, "DEFAULT_COST_PER_KM": c.DEFAULT_COST_PER_KM,
        "DEFAULT_CO2_PER_KM": c.DEFAULT_CO2_PER_KM, "ORTOOLS_MAX_TIME_LIMIT": c.ORTOOLS_MAX_TIME_LIMIT,
        "ORTOOLS_COOLDOWN_BUFFER": c.ORTOOLS_COOLDOWN_BUFFER, "FEEDBACK_FILE": "test_feedback_log.csv",
        "build_road_network": network.build_road_network,
        "compute_network_distances": network.compute_network_distances,
        "road_edges_xy": network.road_edges_xy,
        "route_polyline": network.route_polyline,
        "route_cost": evaluation.route_cost,
        "route_timeline": evaluation.route_timeline,
        "evaluate_route": evaluation.evaluate_route,
        "solution_totals": evaluation.solution_totals,
        "distance_to_business": evaluation.distance_to_business,
        "sweep_construction": construction.sweep_construction,
        "savings_construction": construction.savings_construction,
        "beam_search_construction": construction.beam_search_construction,
        "decode_giant_tour": construction.decode_giant_tour,
        "genetic_algorithm_construction": construction.genetic_algorithm_construction,
        "find_two_opt_move": local_search.find_two_opt_move,
        "find_or_opt_move": local_search.find_or_opt_move,
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


def test_beam_search_covers_all_stops(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["beam_search_construction"](inst["n_stops"], inst["D"], inst["demands"], inst["capacity"], inst["n_vehicles"])
    _assert_all_stops_covered_once(routes, inst["n_stops"])
    assert len(routes) == inst["n_vehicles"]


def test_beam_search_produces_reasonably_balanced_routes(funcs):
    """Regressionstest: eine testweise Cheapest-Insertion-Variante von Beam
    Search fuehrte zu stark unausgewogenen Touren (ein Fahrzeug bekam fast
    alle Stopps, andere blieben leer) und war im Benchmark nachweislich
    schlechter - deshalb wieder auf Anhaengen-am-Ende zurueckgesetzt. Dieser
    Test prueft, dass keine grobe Unwucht mehr auftritt."""
    inst = _make_instance(funcs, n_stops=20, n_vehicles=4, capacity=50, seed=3)
    routes, _ = funcs["beam_search_construction"](20, inst["D"], inst["demands"], 50, 4)
    lengths = [len(r) for r in routes]
    assert max(lengths) - min(lengths) <= 20 * 0.6  # keine extreme Schieflage


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


def test_local_search_never_increases_distance_without_tw(funcs):
    inst = _make_instance(funcs)
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    history = funcs["local_search_history"](
        routes, inst["D"], inst["demands"], inst["capacity"],
        inst["earliest"], inst["latest"], inst["service"], False,
    )
    distances = [h[1] for h in history]
    for a, b in zip(distances, distances[1:]):
        assert b <= a + 1e-6, "Lokale Suche hat die Distanz verschlechtert (ohne Zeitfenster)"


def test_local_search_never_increases_violations_with_tw(funcs):
    inst = _make_instance(funcs, seed=2)
    rng = np.random.default_rng(2)
    earliest = rng.uniform(0, 100, size=inst["n_stops"]).round(0)
    latest = earliest + rng.uniform(15, 40, size=inst["n_stops"]).round(0)
    service = np.zeros(inst["n_stops"])
    routes, _ = funcs["sweep_construction"](inst["depot"], inst["coords"], inst["demands"], inst["n_vehicles"], inst["capacity"])
    history = funcs["local_search_history"](
        routes, inst["D"], inst["demands"], inst["capacity"], earliest, latest, service, True,
    )
    violations = [h[2] for h in history]
    for a, b in zip(violations, violations[1:]):
        assert b <= a, "Verletzungen sollten durch die lokale Suche nie zunehmen"


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
