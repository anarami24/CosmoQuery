
from dataclasses import dataclass, field, asdict


@dataclass
class ScoredChunk:
    chunk_id: int
    score: float
    doc: str
    section: str
    text: str
    matches: dict = field(default_factory=dict)   
    coverage: float = 0.0                        
    extra: dict = field(default_factory=dict)     


@dataclass
class SearchResult:
    query: str
    method: str                 
    algorithm: str             
    terms: list                 
    patterns: list             
    results: list              
    time_ms: float              
    n_examined: int             
    n_matched: int              
    n_total: int                
    details: dict = field(default_factory=dict)

    def ids(self):
        return [r.chunk_id for r in self.results]

    def to_dict(self):
        return asdict(self)
