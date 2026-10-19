from pathlib import Path

# Rutas
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"             
CHUNKS_FILE = DATA_DIR / "chunks.json"
INDEX_FILE = DATA_DIR / "index.pkl"
QUESTIONS_FILE = DATA_DIR / "questions.json"
RESULTS_DIR = BASE_DIR / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


# Etapa 1 - Fragmentación
# Tamaño objetivo de cada fragmento (en palabras) y traslape entre fragmentos
# consecutivos. 150 palabras =~ 200 tokens de RoBERTa, así que caben 2 fragmentos
# completos en la ventana de 512 tokens del modelo junto con la pregunta.
CHUNK_SIZE_WORDS = 150
CHUNK_OVERLAP_WORDS = 30
MIN_CHUNK_WORDS = 25        # fragmentos cortos se fusionan con el anterior

# Secciones que no aportan contenido para responder preguntas.
SKIP_SECTIONS = {
    "see also", "references", "external links", "notes", "further reading",
    "bibliography", "footnotes", "citations", "sources", "explanatory notes",
    "general and cited references", "works cited", "general bibliography",
    "keep exploring", "discover more topics from nasa", "discover more topics", "explore more",
    "related terms", "related resources", "related articles", "related news", "latest news",
    "news", "featured story", "featured stories", "suggested searches", "highlights",
    "share", "details", "stay connected", "more resources", "resources", "multimedia",
    "explore", "related", "learn more", "top stories", "you might also like",
}

# Colección: páginas oficiales de NASA (dominio público en su mayoría).
SOURCES = [
    ("solar-system", "Solar System Facts", "https://science.nasa.gov/solar-system/solar-system-facts/"),
    ("planets", "About the Planets", "https://science.nasa.gov/solar-system/planets/"),
    ("mercury", "Mercury Facts", ("https://science.nasa.gov/mercury/facts/", "https://science.nasa.gov/solar-system/planets/mercury/mercury-facts/")),
    ("venus", "Venus Facts", ("https://science.nasa.gov/venus/venus-facts/", "https://science.nasa.gov/solar-system/planets/venus/venus-facts/")),
    ("earth", "Earth Facts", "https://science.nasa.gov/earth/facts/"),
    ("mars", "Mars Facts", ("https://science.nasa.gov/mars/facts/", "https://science.nasa.gov/solar-system/planets/mars/mars-facts/")),
    ("jupiter", "Jupiter Facts", ("https://science.nasa.gov/jupiter/jupiter-facts/", "https://science.nasa.gov/solar-system/planets/jupiter/jupiter-facts/")),
    ("saturn", "Saturn Facts", ("https://science.nasa.gov/saturn/facts/", "https://science.nasa.gov/solar-system/planets/saturn/saturn-facts/")),
    ("uranus", "Uranus Facts", ("https://science.nasa.gov/uranus/facts/", "https://science.nasa.gov/solar-system/planets/uranus/uranus-facts/")),
    ("neptune", "Neptune Facts", ("https://science.nasa.gov/neptune/neptune-facts/", "https://science.nasa.gov/solar-system/planets/neptune/neptune-facts/")),
    ("pluto", "Pluto Facts", "https://science.nasa.gov/dwarf-planets/pluto/facts/"),
    ("moon", "Moon Facts", "https://science.nasa.gov/moon/facts/"),
    ("europa", "Europa Facts", "https://science.nasa.gov/jupiter/moons/europa/"),
    ("titan", "Titan Facts", "https://science.nasa.gov/saturn/moons/titan/"),
    ("sun", "Sun Facts", "https://science.nasa.gov/sun/facts/"),
    ("asteroids", "Asteroid Facts", "https://science.nasa.gov/solar-system/asteroids/facts/"),
    ("comets", "Comet Facts", "https://science.nasa.gov/solar-system/comets/facts/"),
    ("missions", "Planetary Missions", "https://www.nasa.gov/planetarymissions/planetary-mission-program-overview/"),
    ("jpl", "JPL Solar System", "https://www.jpl.nasa.gov/topics/solar-system/"),
    ("exploration", "Solar System Exploration", "https://science.nasa.gov/solar-system/exploration/"),
    ("mars-rovers", "Mars Exploration", "https://science.nasa.gov/mars/"),
    ("voyager", "Voyager Mission", "https://science.nasa.gov/mission/voyager/"),
    ("cassini", "Cassini Mission", "https://science.nasa.gov/mission/cassini/"),
    ("juno", "Juno Mission", "https://science.nasa.gov/mission/juno/"),
    ("perseverance", "Perseverance Mission", "https://science.nasa.gov/mission/mars-2020-perseverance/"),
    ("europa-clipper", "Europa Clipper", "https://science.nasa.gov/mission/europa-clipper/"),
]

# Fuentes NASA adicionales
EXTRA_SOURCES = [
    ("new-horizons", "New Horizons Mission", "https://science.nasa.gov/mission/new-horizons/"),
    ("apollo-11", "Apollo 11 Mission Overview", "https://www.nasa.gov/missions/apollo/apollo-11-mission-overview/"),
    ("kuiper-belt", "Kuiper Belt Facts", "https://science.nasa.gov/solar-system/kuiper-belt/facts/"),
    ("oort-cloud", "Oort Cloud Facts", "https://science.nasa.gov/solar-system/oort-cloud/facts/"),
    ("ceres", "Ceres Facts", "https://science.nasa.gov/dwarf-planets/ceres/facts/"),
    ("ganymede", "Ganymede Facts", "https://science.nasa.gov/jupiter/moons/ganymede/"),
    ("io", "Io Facts", "https://science.nasa.gov/jupiter/moons/io/"),
    ("enceladus", "Enceladus Facts", "https://science.nasa.gov/saturn/moons/enceladus/"),
    ("triton", "Triton Facts", "https://science.nasa.gov/neptune/moons/triton/"),
    ("curiosity", "Curiosity Mission", "https://science.nasa.gov/mission/msl-curiosity/"),
    ("webb", "James Webb Space Telescope", "https://science.nasa.gov/mission/webb/"),
    ("hubble", "Hubble Space Telescope", "https://science.nasa.gov/mission/hubble/"),
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 ComoQuery-StudentProject/1.0")
HTML_DIR = DATA_DIR / "html"   

#------CAMIIII
# --------------------------------------------------------------------------
# Etapa 3 - Puntuación (Okapi BM25 + bonos)
# --------------------------------------------------------------------------
BM25_K1 = 1.5          # saturación de la frecuencia del término
BM25_B = 0.75          # normalización por longitud del fragmento
PHRASE_WEIGHT = 1.0    # peso del bono por frases (bigramas) encontradas
TOP_K = 5

# --------------------------------------------------------------------------
# Persona 2 - Etapa 4: Búsqueda aproximada
# --------------------------------------------------------------------------
FUZZY_MIN_LEN = 4                # palabras de 3 letras o menos no se corrigen
FUZZY_MAX_DIST = {4: 1, 8: 2}    # longitud mínima -> distancia máxima (4-7: 1, >=8: 2)
FUZZY_MAX_CANDIDATES = 3         # correcciones por palabra
NGRAM_N = 2                      # bigramas (se compara con 3 en la Etapa 6)
NGRAM_MIN_JACCARD = 0.45
JACCARD_RERANK_WEIGHT = 0.1      # β del reordenamiento por Jaccard de trigramas
# --------------------------------------------------------------------------
# Persona 2 - Etapa 5: Contexto y modelo
# --------------------------------------------------------------------------
QA_MODEL = "deepset/roberta-base-squad2"
MODEL_MAX_TOKENS = 512
CONTEXT_CANDIDATES = 10          # top-N recuperados que entran a la selección
CONTEXT_TOKEN_BUDGET = None      # None = 512 - tokens(pregunta) - especiales - margen
REDUNDANCY_JACCARD = 0.5
NO_ANSWER_THRESHOLD = 7.0        # umbral del PokeChat (score_difference < 7)
NO_ANSWER_TEXT = "I don't know"  # coincide con evaluation.answer_scores
