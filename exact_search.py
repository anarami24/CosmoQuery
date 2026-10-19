#ETAPA 3
import math
import time

import config
from search_types import ScoredChunk, SearchResult
from string_matching import MATCHERS
from structures import quickselect_top_k

ALGORITHMS = list(MATCHERS) + ["suffix_array"]


class ExactSearcher:
    def __init__(self, index):
        self.index = index
        self.pp = index.preprocessor

    def extract_terms(self, query, field="stems"):
        """Términos únicos (en orden) y frases (bigramas) de la pregunta."""
        if field == "stems":
            tokens = self.pp.process_query(query)
        else:
            tokens = self.pp.query_words(query)
        terms = list(dict.fromkeys(tokens))
        phrases = list(dict.fromkeys(
            (a, b) for a, b in zip(tokens, tokens[1:]) if a != b))
        return terms, phrases

    def search(self, query, algorithm="kmp", top_k=config.TOP_K, use_index=True,
               field="stems", use_phrases=True):
        if algorithm not in ALGORITHMS:
            raise ValueError(f"Algoritmo desconocido: {algorithm}. Opciones: {ALGORITHMS}")
        if algorithm == "suffix_array" and field != "stems":
            raise ValueError("El arreglo de sufijos está construido sobre raíces (field='stems')")

        idx = self.index
        inv = idx.inv_stems if field == "stems" else idx.inv_words
        texts = idx.stem_text if field == "stems" else idx.word_text

        t0 = time.perf_counter()
        terms, phrases = self.extract_terms(query, field)
        if not use_phrases:
            phrases = []

        counts = {}       
        if not terms:
            examined = 0
        elif algorithm == "suffix_array":
            #busqueda binaria de cada patrón en el arreglo de sufijos: O(m log n)
            for t in terms:
                for cid, c in idx.suffix_array.count_by_chunk([t]).items():
                    counts.setdefault(cid, {})[t] = c
            for a, b in phrases:
                for cid, c in idx.suffix_array.count_by_chunk([a, b]).items():
                    counts.setdefault(cid, {})[f"{a} {b}"] = c
            examined = len(counts)
        else:
            Matcher = MATCHERS[algorithm]
            #wl preprocesamiento de cada patrón se hace una sola vez
            term_matchers = [(t, Matcher(f" {t} ")) for t in terms]
            phrase_matchers = [((a, b), Matcher(f" {a} {b} ")) for a, b in phrases]
            candidates = sorted(inv.candidates(terms)) if use_index else range(len(texts))
            examined = len(candidates)
            for cid in candidates:
                text = texts[cid]
                found = {}
                for t, matcher in term_matchers:
                    c = len(matcher.search(text))
                    if c:
                        found[t] = c
                # Poda: una frase solo puede aparecer si aparecen sus dos términos
                for (a, b), matcher in phrase_matchers:
                    if a in found and b in found:
                        c = len(matcher.search(text))
                        if c:
                            found[f"{a} {b}"] = c
                if found:
                    counts[cid] = found

        scored = [(self._score(cid, found, terms, phrases, inv), cid) for cid, found in counts.items()]
        top = quickselect_top_k(scored, top_k, key=lambda x: (x[0], -x[1]))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        results = []
        for score, cid in top:
            chunk = idx.chunks[cid]
            found = counts[cid]
            cov = sum(1 for t in terms if t in found) / len(terms)
            results.append(ScoredChunk(cid, round(score, 4), chunk["doc"], chunk["section"],
                                       chunk["text"], dict(found), round(cov, 3)))
        return SearchResult(
            query=query, method="exact", algorithm=algorithm, terms=terms,
            patterns=terms + [f"{a} {b}" for a, b in phrases], results=results,
            time_ms=elapsed_ms, n_examined=examined, n_matched=len(counts),
            n_total=len(idx.chunks),
            details={"use_index": use_index, "field": field})

    def _score(self, cid, found, terms, phrases, inv):
        k1, b = config.BM25_K1, config.BM25_B
        length_norm = 1 - b + b * inv.doc_len.get(cid, 0) / max(inv.avg_len, 1e-9)
        base = 0.0
        for t in terms:
            tf = found.get(t, 0)
            if tf:
                base += inv.idf(t) * tf * (k1 + 1) / (tf + k1 * length_norm)
        bonus = 0.0
        for a, bb in phrases:
            c = found.get(f"{a} {bb}", 0)
            if c:
                bonus += config.PHRASE_WEIGHT * (inv.idf(a) + inv.idf(bb)) / 2 * math.log(1 + c)
        coverage = sum(1 for t in terms if t in found) / len(terms)
        return (base + bonus) * (0.5 + coverage)
