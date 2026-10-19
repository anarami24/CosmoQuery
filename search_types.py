
from dataclasses import dataclass, field, asdict


@dataclass
class ScoredChunk:
    chunk_id: int
    score: float
    doc: str
    section: str
    text: str
    matches: dict = field(default_factory=dict)   # término/patrón: nº de coincidencias
    coverage: float = 0.0                         # fracción de términos de la consulta presentes
    extra: dict = field(default_factory=dict)     # datos propios de cada método


@dataclass
class SearchResult:
    query: str
    method: str                 # "exact" | "approximate"
    algorithm: str              # "kmp", "z", "levenshtein_trie", ...
    terms: list                 # términos extraídos de la pregunta
    patterns: list              # patrones buscados (términos y frases)
    results: list               # list[ScoredChunk], ordenados por score desc
    time_ms: float              # tiempo total de la búsqueda
    n_examined: int             # fragmentos examinados por el algoritmo
    n_matched: int              # fragmentos con puntaje > 0
    n_total: int                # fragmentos en la colección
    details: dict = field(default_factory=dict)

    def ids(self):
        return [r.chunk_id for r in self.results]

    def to_dict(self):
        return asdict(self)
