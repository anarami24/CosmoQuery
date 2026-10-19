#ETAPA 4 - Recuperación mediante búsqueda aproximada (Persona 2).

# Corrige cada palabra de la pregunta que no existe en el vocabulario con una técnica
# aproximada, convierte las correcciones en raíces con peso (su similitud) y vuelve a
# puntuar los fragmentos con el mismo criterio de la búsqueda exacta de Ana
# (BM25 + bono por frases + factor de cobertura), ponderando cada término por su peso.

# Algoritmos:
#   lev_trie       Levenshtein recorriendo el Trie con poda (línea base de la técnica A)
#   osa_trie       Damerau-Levenshtein (OSA) recorriendo el Trie con poda (técnica A)
#   ngram_jaccard  n-gramas de caracteres + Jaccard con tabla hash (técnica B)
#   hybrid         unión de OSA y n-gramas; cada candidato se queda con su mayor similitud

# Uso:  python approx_search.py "What is the largset volcanno on Mars?" --compare

import argparse
import math
import textwrap
import time
from collections import Counter

import config
from approximate import (NgramIndex, char_ngrams, jaccard, lcs_length, max_edit_distance,
                         trie_fuzzy_search)
from preprocessing import STOPWORDS, highlight
from search_types import ScoredChunk, SearchResult
from structures import Trie, quickselect_top_k

ALGORITHMS = ["lev_trie", "osa_trie", "ngram_jaccard", "hybrid"]
ALGORITHM_LABELS = {
    "lev_trie": "Levenshtein + Trie con poda",
    "osa_trie": "OSA (Damerau) + Trie con poda",
    "ngram_jaccard": "n-gramas + Jaccard",
    "hybrid": "Híbrido (OSA + n-gramas)",
}
TECHNIQUES = {"lev_trie": ("lev",), "osa_trie": ("osa",), "ngram_jaccard": ("ngram",),
              "hybrid": ("osa", "ngram")}
LCS_WEIGHT = 0.0        # γ del bono por orden (RF-4.4); apagado salvo que la ablación lo justifique
RERANK_NGRAM = 3        # el reordenamiento compara trigramas de caracteres


class ApproximateSearcher:
    def __init__(self, index):
        self.index = index
        self.pp = index.preprocessor
        self.trie = index.trie
        if len(self.trie) == 0:
            # CorpusIndex.subset(n) deja el Trie vacío: se reconstruye aquí con el vocabulario
            # del subconjunto (sin modificar el código de Ana). Se usan las mismas reglas que
            # index_builder: solo palabras alfabéticas de 2 o más letras.
            self.trie = build_trie(index.word_tokens)
        self._ngram_indexes = {}
        self._chunk_grams = {}

    def ngram_index(self, n=None):
        """Índice de n-gramas del vocabulario; se construye la primera vez que se pide."""
        n = config.NGRAM_N if n is None else n
        if n not in self._ngram_indexes:
            self._ngram_indexes[n] = NgramIndex(self.trie.words(), n)
        return self._ngram_indexes[n]

    # Paso 2: expansión de cada palabra de la pregunta
    def expand_word(self, word, algorithm, max_dist_rules=None, ngram_n=None, min_len=None):
        """Candidatos (palabra, similitud, corrección) para una palabra de la pregunta.

        - Palabra que existe en el vocabulario (o número): término exacto, peso 1.
        - Palabra corta (< FUZZY_MIN_LEN): se deja exacta aunque no exista.
        - Si no, se buscan correcciones y se conservan solo las de mejor distancia
          (o mejor Jaccard), hasta FUZZY_MAX_CANDIDATES.
        Devuelve (lista de candidatos, nodos visitados del Trie, motivo).
        """
        min_len = config.FUZZY_MIN_LEN if min_len is None else min_len
        if self.trie.contains(word) or not word.isalpha():
            return [(word, 1.0, None)], 0, "exact"
        max_dist = max_edit_distance(len(word), max_dist_rules, min_len)
        if len(word) < min_len or max_dist == 0:
            return [(word, 1.0, None)], 0, "short"
        best = {}                              # candidato -> (similitud, datos de la corrección)
        nodes = 0
        for tech in TECHNIQUES[algorithm]:
            if tech in ("lev", "osa"):
                found, stats = trie_fuzzy_search(self.trie, word, max_dist, tech, STOPWORDS)
                nodes += stats["nodes_visited"]
                if not found:
                    continue
                d_best = found[0][1]
                for cand, d, freq in found[:config.FUZZY_MAX_CANDIDATES]:
                    if d != d_best:
                        break
                    sim = 1 - d / max(len(word), len(cand))
                    info = {"technique": tech, "distance": d}
                    if sim > best.get(cand, (-1,))[0]:
                        best[cand] = (sim, info)
            else:
                found, _ = self.ngram_index(ngram_n).lookup(word)
                if not found:
                    continue
                j_best = found[0][1]
                for cand, j, freq in found:
                    if j != j_best:
                        break
                    info = {"technique": f"ngram{self.ngram_index(ngram_n).n}", "jaccard": round(j, 3)}
                    if j > best.get(cand, (-1,))[0]:
                        best[cand] = (j, info)
        if not best:
            return [(word, 1.0, None)], nodes, "no_candidates"
        ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], -self.trie.frequency(kv[0]), kv[0]))
        return [(c, sim, info) for c, (sim, info) in ranked[:config.FUZZY_MAX_CANDIDATES]], nodes, "corrected"

    def search(self, query, algorithm="hybrid", top_k=config.TOP_K, max_dist_rules=None,
               ngram_n=None, rerank_beta=None, use_phrases=True, lcs_weight=None, min_len=None):
        if algorithm not in ALGORITHMS:
            raise ValueError(f"Algoritmo desconocido: {algorithm}. Opciones: {ALGORITHMS}")
        rerank_beta = config.JACCARD_RERANK_WEIGHT if rerank_beta is None else rerank_beta
        lcs_weight = LCS_WEIGHT if lcs_weight is None else lcs_weight
        idx, inv = self.index, self.index.inv_stems
        t0 = time.perf_counter()

        # 1. Palabras de la pregunta (sin stopwords ni relleno, sin stemming)
        words = self.pp.query_words(query)

        # 2. Expansión: cada palabra -> grupo de raíces con peso
        weights = {}              # raíz -> peso (similitud de su mejor corrección)
        groups = []               # una entrada por palabra: conjunto de raíces que la representan
        corrections, exact_words, short_words = [], [], []
        nodes_visited = 0
        expansion_cache = {}
        for w in words:
            if w not in expansion_cache:
                expansion_cache[w] = self.expand_word(w, algorithm, max_dist_rules, ngram_n, min_len)
            cands, nodes, reason = expansion_cache[w]
            nodes_visited += nodes
            group = []
            for cand, sim, info in cands:
                stem = self.pp.stem(cand)
                if sim > weights.get(stem, -1):
                    weights[stem] = sim
                if stem not in group:
                    group.append(stem)
                if info is not None and not any(c["query_word"] == w and c["candidate"] == cand
                                                for c in corrections):
                    corrections.append({"query_word": w, "candidate": cand, "stem": stem,
                                        "weight": round(sim, 3), **info})
            if reason == "exact":
                exact_words.append(w)
            elif reason == "short":
                short_words.append(w)
            groups.append(group)
        terms = list(dict.fromkeys(s for g in groups for s in g))
        # Grupos únicos (igual que Ana deduplica términos: "moon" y "moons" cuentan una vez)
        unique_groups = list(dict.fromkeys(tuple(g) for g in groups))
        phrases = []
        if use_phrases:
            phrases = list(dict.fromkeys(
                (a, b) for g1, g2 in zip(groups, groups[1:]) for a in g1 for b in g2 if a != b))
        unmatched = [w for w, g in zip(words, groups) if not any(inv.df(s) for s in g)]

        # 3. Recuperación con el índice invertido de raíces (n_examined igual que en la exacta)
        candidates = inv.candidates(terms)
        counts = {}
        for t in terms:
            for cid, tf in inv.get(t).items():
                counts.setdefault(cid, {})[t] = tf
        # Frases: bigramas de términos consecutivos contados con el arreglo de sufijos de Ana
        for a, b in phrases:
            if inv.df(a) and inv.df(b):
                for cid, c in idx.suffix_array.count_by_chunk([a, b]).items():
                    counts.setdefault(cid, {})[f"{a} {b}"] = c

        # 4-5. Puntuación ponderada + reordenamiento opcional por Jaccard de trigramas
        q_grams = char_ngrams(" ".join(terms), RERANK_NGRAM) if rerank_beta else None
        scored = []
        for cid, found in counts.items():
            score = self._score(cid, found, terms, unique_groups, phrases, weights, inv)
            if rerank_beta:
                score *= 1 + rerank_beta * jaccard(q_grams, self._grams_of(cid))
            if lcs_weight and terms:
                score += lcs_weight * lcs_length(terms, idx.stem_tokens[cid]) / len(terms)
            scored.append((score, cid))

        # 6. Top-k con el quickselect de Ana, desempate por id (igual que la exacta)
        top = quickselect_top_k(scored, top_k, key=lambda x: (x[0], -x[1]))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        results = []
        for score, cid in top:
            chunk = idx.chunks[cid]
            found = counts[cid]
            cov = self._coverage(found, unique_groups)
            used = [c for c in corrections if c["stem"] in found]
            results.append(ScoredChunk(cid, round(score, 4), chunk["doc"], chunk["section"],
                                       chunk["text"], dict(found), round(cov, 3),
                                       {"corrections": used}))
        return SearchResult(
            query=query, method="approximate", algorithm=algorithm, terms=terms,
            patterns=terms + [f"{a} {b}" for a, b in phrases], results=results,
            time_ms=elapsed_ms, n_examined=len(candidates), n_matched=len(counts),
            n_total=len(idx.chunks),
            details={"corrections": corrections, "weights": {t: round(w, 3) for t, w in weights.items()},
                     "nodes_visited": nodes_visited, "nodes_total": self.trie.n_nodes,
                     "exact_words": exact_words, "short_words": short_words,
                     "unmatched_words": unmatched, "query_words": words,
                     "rerank_beta": rerank_beta, "use_phrases": use_phrases})

    @staticmethod
    def _coverage(found, groups):
        """Fracción de palabras de la pregunta presentes: una palabra cuenta si alguno de sus
        candidatos aparece en el fragmento."""
        if not groups:
            return 0.0
        return sum(1 for g in groups if any(s in found for s in g)) / len(groups)

    def _score(self, cid, found, terms, groups, phrases, weights, inv):
        """Misma fórmula que ExactSearcher._score de Ana (exact_search.py), con dos cambios:
        la frecuencia de cada término se multiplica por su peso (similitud de la corrección)
        y la cobertura se cuenta por palabra de la pregunta. No se llama directamente a
        _score porque ahí la cobertura se cuenta por término y contaría cada candidato
        como si fuera una palabra distinta. Si no hubo correcciones, ambas coinciden."""
        k1, b = config.BM25_K1, config.BM25_B
        length_norm = 1 - b + b * inv.doc_len.get(cid, 0) / max(inv.avg_len, 1e-9)
        base = 0.0
        for t in terms:
            tf = found.get(t, 0) * weights.get(t, 1.0)
            if tf:
                base += inv.idf(t) * tf * (k1 + 1) / (tf + k1 * length_norm)
        bonus = 0.0
        for a, bb in phrases:
            c = found.get(f"{a} {bb}", 0) * min(weights.get(a, 1.0), weights.get(bb, 1.0))
            if c:
                bonus += config.PHRASE_WEIGHT * (inv.idf(a) + inv.idf(bb)) / 2 * math.log(1 + c)
        return (base + bonus) * (0.5 + self._coverage(found, groups))

    def _grams_of(self, cid):
        grams = self._chunk_grams.get(cid)
        if grams is None:
            grams = self._chunk_grams[cid] = char_ngrams(" ".join(self.index.stem_tokens[cid]), RERANK_NGRAM)
        return grams


def build_trie(token_lists):
    """Trie con el vocabulario de una lista de fragmentos tokenizados. O(Σ|w|)."""
    counter = Counter()
    for tokens in token_lists:
        counter.update(tokens)
    trie = Trie()
    for word, freq in counter.items():
        if word.isalpha() and len(word) >= 2:
            trie.insert(word, freq)
    return trie


# Demo en consola
def format_correction(c):
    if "distance" in c:
        return f"{c['query_word']} -> {c['candidate']} ({c['technique'].upper()} d={c['distance']}, peso {c['weight']:.2f})"
    return f"{c['query_word']} -> {c['candidate']} (Jaccard {c['jaccard']:.2f} con {c['technique']})"


def print_ranking(title, res, width=100, show_text=False):
    print(f"\n{title}  |  {res.time_ms:.3f} ms  |  examinados {res.n_examined:,} de {res.n_total:,}"
          f"  |  con coincidencias {res.n_matched:,}")
    if not res.results:
        print("  (sin resultados)")
    for rank, r in enumerate(res.results, 1):
        print(f"  #{rank} score={r.score:8.3f}  cobertura={r.coverage:4.0%}  [{r.doc} > {r.section}]  (fragmento {r.chunk_id})")
        if show_text:
            body = highlight(r.text, res.terms, pre="[", post="]")
            print(textwrap.indent(textwrap.fill(body, width), "      "))


def main():
    from exact_search import ExactSearcher
    from index_builder import load_index

    ap = argparse.ArgumentParser(description="Búsqueda aproximada sobre la colección")
    ap.add_argument("query")
    ap.add_argument("--alg", default="hybrid", choices=ALGORITHMS)
    ap.add_argument("--k", type=int, default=config.TOP_K)
    ap.add_argument("--compare", action="store_true", help="comparar contra la exacta y entre técnicas")
    ap.add_argument("--text", action="store_true", help="mostrar el texto de los fragmentos")
    args = ap.parse_args()

    index = load_index()
    approx = ApproximateSearcher(index)
    res = approx.search(args.query, args.alg, args.k)
    d = res.details
    print(f"\nPregunta : {args.query}")
    print(f"Palabras : {d['query_words']}")
    print(f"Exactas  : {d['exact_words']}   | sin corregir (cortas): {d['short_words']}"
          f"   | sin coincidencias: {d['unmatched_words']}")
    print(f"Términos : {res.terms}")
    print("Correcciones:")
    for c in d["corrections"] or []:
        print(f"  {format_correction(c)}")
    if not d["corrections"]:
        print("  (ninguna)")
    n_fuzzy = len({c["query_word"] for c in d["corrections"]})
    print(f"Poda del Trie: {d['nodes_visited']:,} nodos visitados en total al corregir {n_fuzzy} palabra(s);"
          f" el Trie tiene {d['nodes_total']:,} nodos")

    if args.compare:
        exact = ExactSearcher(index).search(args.query, "kmp", args.k)
        print_ranking(f"EXACTA - KMP (términos {exact.terms})", exact, show_text=args.text)
        for alg in ALGORITHMS:
            r = approx.search(args.query, alg, args.k)
            corr = "; ".join(format_correction(c) for c in r.details["corrections"]) or "sin correcciones"
            print_ranking(f"APROXIMADA - {ALGORITHM_LABELS[alg]}\n  {corr}", r, show_text=args.text)
        print(f"\n{'Método':<34}{'Tiempo (ms)':>12}{'Examinados':>12}{'Nodos Trie':>12}  Top-{args.k} (ids)")
        print(f"{'KMP (exacta)':<34}{exact.time_ms:>12.3f}{exact.n_examined:>12,}{'-':>12}  {exact.ids()}")
        for alg in ALGORITHMS:
            r = approx.search(args.query, alg, args.k)
            print(f"{ALGORITHM_LABELS[alg]:<34}{r.time_ms:>12.3f}{r.n_examined:>12,}"
                  f"{r.details['nodes_visited']:>12,}  {r.ids()}")
    else:
        print_ranking(f"APROXIMADA - {ALGORITHM_LABELS[args.alg]}", res, show_text=True)


if __name__ == "__main__":
    main()
