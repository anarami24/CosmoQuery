
#Demo en consola de la búsqueda exacta (Etapa 3).

import argparse
import textwrap

from exact_search import ALGORITHMS, ExactSearcher
from index_builder import load_index
from preprocessing import highlight
from string_matching import ALGORITHM_LABELS


def print_result(res, show_text=True, width=100):
    print(f"\nPregunta : {res.query}")
    print(f"Algoritmo: {ALGORITHM_LABELS.get(res.algorithm, res.algorithm)}"
          f"   | índice invertido: {'sí' if res.details.get('use_index') else 'no'}")
    print(f"Términos : {res.terms}")
    print(f"Patrones : {res.patterns}")
    print(f"Tiempo   : {res.time_ms:.3f} ms   | fragmentos examinados: {res.n_examined:,} de "
          f"{res.n_total:,}   | con coincidencias: {res.n_matched:,}")
    if not res.results:
        print("  (sin resultados)")
    for rank, r in enumerate(res.results, 1):
        print(f"\n  #{rank}  score={r.score:.3f}  cobertura={r.coverage:.0%}  "
              f"[{r.doc} > {r.section}]  (fragmento {r.chunk_id})")
        print(f"      coincidencias: {r.matches}")
        if show_text:
            body = highlight(r.text, res.terms, pre="[", post="]")
            print(textwrap.indent(textwrap.fill(body, width), "      "))


def main():
    ap = argparse.ArgumentParser(description="Búsqueda exacta sobre la colección")
    ap.add_argument("query")
    ap.add_argument("--alg", default="kmp", choices=ALGORITHMS)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--no-index", action="store_true", help="examinar todos los fragmentos")
    ap.add_argument("--words", action="store_true", help="buscar palabras sin stemming")
    ap.add_argument("--compare", action="store_true", help="comparar todos los algoritmos")
    args = ap.parse_args()

    searcher = ExactSearcher(load_index())
    field = "words" if args.words else "stems"
    if args.compare:
        print(f"\n{'Algoritmo':<28}{'Tiempo (ms)':>12}{'Examinados':>12}  Top-{args.k} (ids)")
        reference = None
        for alg in ALGORITHMS:
            if alg == "suffix_array" and field != "stems":
                continue
            res = searcher.search(args.query, alg, args.k, not args.no_index, field)
            ids = res.ids()
            reference = reference or ids
            same = "" if ids == reference else "  <-- distinto!"
            print(f"{ALGORITHM_LABELS[alg]:<28}{res.time_ms:>12.3f}{res.n_examined:>12,}  {ids}{same}")
        print_result(searcher.search(args.query, "kmp", args.k, not args.no_index, field))
    else:
        print_result(searcher.search(args.query, args.alg, args.k, not args.no_index, field))


if __name__ == "__main__":
    main()
