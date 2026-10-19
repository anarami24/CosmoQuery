import statistics

import config
from exact_search import ALGORITHMS, ExactSearcher
from index_builder import load_index
from preprocessing import highlight
from string_matching import ALGORITHM_LABELS

EXAMPLE_QUERIES = [
    "What is mentioned about the Great Red Spot and storms on Jupiter?",
    "When was Pluto discovered and when was it reclassified as a dwarf planet?",
    "What do we know about the moons of Mars, Phobos and Deimos?",
    "What lies beneath the ice of Europa and when did Europa Clipper launch?",
    "What is the atmosphere of Venus made of?",
    "When did Voyager 1 reach interstellar space?",
]
LIMITATION_PAIRS = [
    ("Who discovered Uranus?", "Who first spotted the seventh planet?", "paráfrasis"),
    ("What is the largest volcano in the solar system?", "What is the largset volcanno in the solar systme?", "errores de escritura"),
    ("What is the smallest planet in our solar system?", "Which world is the tiniest in our planetary system?", "sinónimos"),
]

COMPLEXITY = {
    "naive": "O(m) por patrón y O(n·m) peor caso por texto",
    "kmp": "O(m) preproceso (una vez) + O(n) por texto",
    "z": "O(n + m) por texto",
    "rabin_karp": "O(m) preproceso + O(n) esperado por texto (O(n·m) peor caso)",
    "suffix_array": "O(m log N + occ) por patrón, sin recorrer los fragmentos",
}


def median_time(searcher, q, alg, runs=5):
    return statistics.median(searcher.search(q, alg).time_ms for _ in range(runs))


def main():
    index = load_index()
    searcher = ExactSearcher(index)
    L = ["# Etapa 3 - Recuperación mediante búsqueda exacta\n",
         f"Colección: {len(index.chunks):,} fragmentos. Top-{config.TOP_K} por consulta. "
         "Tiempos = mediana de 5 ejecuciones.\n",
         "## Complejidad por algoritmo\n", "| Algoritmo | Complejidad |", "|---|---|"]
    L += [f"| {ALGORITHM_LABELS[a]} | {COMPLEXITY[a]} |" for a in ALGORITHMS]
    L.append("\nn = longitud del fragmento preprocesado, m = longitud del patrón, N = términos de toda la colección, "
             "occ = número de apariciones. Con k patrones y C candidatos, una consulta cuesta O(k·Σ n_i) con "
             "los algoritmos de recorrido y O(k·m log N) con el arreglo de sufijos.\n")

    for qi, q in enumerate(EXAMPLE_QUERIES, 1):
        res = searcher.search(q, "kmp")
        L += [f"## Consulta {qi}: \"{q}\"\n",
              f"- **Términos:** {', '.join(res.terms)}",
              f"- **Patrones (términos + frases):** {', '.join(res.patterns)}",
              f"- **Fragmentos examinados:** {res.n_examined:,} de {res.n_total:,} (filtrados con el índice invertido); "
              f"con coincidencias: {res.n_matched:,}\n",
              "| Algoritmo | Tiempo (ms) | Top-5 (ids) |", "|---|---:|---|"]
        for alg in ALGORITHMS:
            r = searcher.search(q, alg)
            L.append(f"| {ALGORITHM_LABELS[alg]} | {median_time(searcher, q, alg):.3f} | {r.ids()} |")
        scan = searcher.search(q, "kmp", use_index=False)
        L.append(f"| KMP sin índice (recorre todo) | {median_time_noindex(searcher, q):.3f} | {scan.ids()} |")
        L += ["", "| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |", "|---|---:|---:|---|---|---|"]
        for rank, r in enumerate(res.results, 1):
            snippet = highlight(r.text, res.terms)[:320].replace("|", "/").replace("\n", " ")
            L.append(f"| {rank} | {r.score:.3f} | {r.coverage:.0%} | {r.doc} > {r.section} | "
                     f"{', '.join(f'{k}:{v}' for k, v in r.matches.items())} | {snippet}… |")
        L.append("")

    L += ["## Limitaciones de la búsqueda exacta\n",
          "| Tipo | Pregunta | Términos | Recuperados | Top-1 | Puntuación top-1 |", "|---|---|---|---:|---|---:|"]
    for literal, variant, kind in LIMITATION_PAIRS:
        for label, q in (("literal", literal), (kind, variant)):
            r = searcher.search(q, "kmp")
            top = f"{r.results[0].doc} > {r.results[0].section}" if r.results else "(ninguno)"
            score = f"{r.results[0].score:.3f}" if r.results else "-"
            L.append(f"| {label} | {q} | {', '.join(r.terms)} | {r.n_matched} | {top} | {score} |")
    path = config.RESULTS_DIR / "etapa3_busqueda_exacta.md"
    config.RESULTS_DIR.mkdir(exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Reporte de la Etapa 3: {path}")


def median_time_noindex(searcher, q, runs=3):
    return statistics.median(searcher.search(q, "kmp", use_index=False).time_ms for _ in range(runs))


if __name__ == "__main__":
    main()
