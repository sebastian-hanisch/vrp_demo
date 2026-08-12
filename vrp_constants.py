"""
Zentrale Konstanten für die VRP-Demo. Ausgelagert, damit sowohl app.py als
auch alle Logik-Module (vrp_*.py) und die Testsuite dieselben Werte nutzen,
ohne Streamlit importieren zu müssen.
"""

VEHICLE_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]
EPS = 1e-9

BEAM_WIDTH = 8
GA_POP_SIZE = 30
GA_GENERATIONS = 40
OR_OPT_SEG_LENGTHS = (1, 2)
LOCAL_SEARCH_MAX_MOVES = 200

DEFAULT_SPEED_KMH = 40
DEFAULT_COST_PER_KM = 0.35
DEFAULT_CO2_PER_KM = 0.8  # kg CO2/km - Richtwert für einen kleinen/mittleren Diesel-Lieferwagen

ORTOOLS_MAX_TIME_LIMIT = 5  # gedeckelt (statt 10s) - Schutz vor Ressourcenlast bei mehreren gleichzeitigen Besuchern auf kostenlosem Hosting
ORTOOLS_COOLDOWN_BUFFER = 3  # Sekunden Wartezeit zusätzlich zum Zeitlimit, bevor erneut gelöst werden kann

FEEDBACK_FILE = "feedback_log.csv"
