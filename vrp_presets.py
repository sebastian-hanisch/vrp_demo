"""
Ein-Klick-Beispielszenarien und Permalink-Logik (aktuelle Konfiguration wird
in der URL gespiegelt und lässt sich beim Laden daraus wiederherstellen).

WICHTIG - eine Wahrheitsquelle für Wertebereiche: SETTING_SPECS unten definiert
Minimum/Maximum/Default für jedes konfigurierbare Widget. Sowohl die
Slider-Definitionen in app.py (über bounds()) als auch die Permalink-Begrenzung
lesen daraus. Vor dieser Zusammenführung standen die Grenzen doppelt (einmal
hier, einmal im st.slider-Aufruf); ein Auseinanderlaufen hätte den bereits
behobenen Absturz-Bug bei Permalinks mit Werten außerhalb des Slider-Bereichs
stillschweigend zurückgebracht. Ein Test (test_slider_bounds_match_setting_specs)
prüft zusätzlich automatisch, dass die tatsächlich gerenderten Slider mit dieser
Spezifikation übereinstimmen.
"""

import math
from dataclasses import dataclass
from typing import Callable, Optional

import streamlit as st

from vrp_constants import DEFAULT_CO2_PER_KM, DEFAULT_COST_PER_KM, DEFAULT_SPEED_KMH


@dataclass(frozen=True)
class SettingSpec:
    """Spezifikation eines konfigurierbaren Widgets: URL-Parametername,
    Typkonvertierung für Werte aus der URL, gültiger Wertebereich und
    Standardwert. lo/hi = None bedeutet "kein Wertebereich" (z. B. Checkbox)."""

    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None


SETTING_SPECS = {
    "n_stops_slider": SettingSpec("n_stops", int, 12, 5, 30),
    "n_vehicles_slider": SettingSpec("n_vehicles", int, 3, 1, 5),
    "capacity_slider": SettingSpec("capacity", int, 25, 5, 60),
    # numpy verlangt nicht-negative Seeds
    "seed_input": SettingSpec("seed", int, 42, 0, 2_000_000_000),
    "tw_checkbox": SettingSpec("tw", lambda v: v == "1", False),
    "asym_checkbox": SettingSpec("asym", lambda v: v == "1", False),
    "n_extra_slider": SettingSpec("extra", int, 20, 5, 60),
    "speed_slider": SettingSpec("speed", int, DEFAULT_SPEED_KMH, 15, 80),
    "cost_slider": SettingSpec("cost", float, DEFAULT_COST_PER_KM, 0.10, 1.00),
    "co2_slider": SettingSpec("co2", float, DEFAULT_CO2_PER_KM, 0.10, 2.00),
}


def bounds(state_key):
    """Gibt (min, max) für ein Widget zurück - zum direkten Entpacken in einen
    st.slider-Aufruf: st.slider(label, *bounds("n_stops_slider"), key=...)."""
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def apply_preset(n_stops_val, n_vehicles_val, capacity_val, tw_val, seed_val):
    """on_click-Callback für die Beispielszenario-Buttons."""
    st.session_state["n_stops_slider"] = n_stops_val
    st.session_state["n_vehicles_slider"] = n_vehicles_val
    st.session_state["capacity_slider"] = capacity_val
    st.session_state["tw_checkbox"] = tw_val
    st.session_state["seed_input"] = seed_val
    st.session_state["force_regen"] = True


def load_permalink_settings():
    """Übernimmt Einstellungen aus der URL in den Session State - einmalig
    beim ersten Laden einer Session. Ungültige Parameter (falscher Typ) werden
    stillschweigend ignoriert (Default bleibt bestehen); Werte außerhalb des
    gültigen Wertebereichs werden auf die nächstliegende gültige Grenze
    begrenzt (nicht ignoriert) - ein zu großer oder negativer Wert in der URL
    (versehentlich, veraltet nach späterer Grenzänderung, oder absichtlich
    manipuliert) darf die App nie zum Absturz bringen."""
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    applied_any = False
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            try:
                value = spec.caster(qp[spec.url_param])
                if isinstance(value, float) and not math.isfinite(value):
                    continue  # NaN/Infinity explizit ablehnen statt vom Zufall der
                    # min/max-Vergleichsreihenfolge abhängig zu sein (float("nan")
                    # und float("inf") werfen bei caster=float keine Exception,
                    # anders als beim int-Caster)
                if spec.lo is not None:
                    value = max(spec.lo, value)
                if spec.hi is not None:
                    value = min(spec.hi, value)
                st.session_state[state_key] = value
                applied_any = True
            except (ValueError, TypeError):
                pass  # z. B. nicht-numerischer Text -> ignorieren, Default bleibt bestehen
    if applied_any:
        st.session_state["force_regen"] = True
    st.session_state["permalink_loaded"] = True


def init_session_state_defaults():
    """Setzt Default-Werte für alle permalink-/preset-gesteuerten Widgets,
    sofern noch nicht (z. B. durch Permalink oder Preset) gesetzt. Wird vor der
    Widget-Erzeugung aufgerufen - vermeidet den Streamlit-Warnhinweis, der
    auftritt, wenn ein Widget gleichzeitig einen festen `value` UND einen
    bereits belegten Session-State-Key hat."""
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def sync_query_params(n_stops, n_vehicles, capacity, seed, tw_enabled, asym_enabled, n_extra, speed_kmh, cost_per_km, co2_per_km):
    """Schreibt die aktuelle Konfiguration in die URL zurück, damit die
    Adresszeile jederzeit den aktuellen Stand widerspiegelt und direkt zum
    Teilen kopiert werden kann. Fehler werden verschluckt - Query-Params sind
    ein Komfortfeature, kein kritischer Pfad."""
    try:
        st.query_params["n_stops"] = str(n_stops)
        st.query_params["n_vehicles"] = str(n_vehicles)
        st.query_params["capacity"] = str(capacity)
        st.query_params["seed"] = str(int(seed))
        st.query_params["tw"] = "1" if tw_enabled else "0"
        st.query_params["asym"] = "1" if asym_enabled else "0"
        st.query_params["extra"] = str(n_extra)
        st.query_params["speed"] = str(speed_kmh)
        st.query_params["cost"] = str(cost_per_km)
        st.query_params["co2"] = str(co2_per_km)
    except Exception:
        pass
