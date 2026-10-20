#ETAPA 4 - reporte de la búsqueda aproximada

import json
import statistics

import config
from approx_search import ALGORITHM_LABELS, ALGORITHMS, ApproximateSearcher, format_correction
from approximate import brute_force_fuzzy, max_edit_distance, trie_fuzzy_search
from evaluation import evaluate_search, load_questions, relevant_chunks
from exact_search import ExactSearcher
from index_builder import load_index
from preprocessing import STOPWORDS, highlight

N_CORRECTION_ROWS = 12
RUNS = 5


def median_ms(fn, runs=RUNS):
    return statistics.median(fn() for _ in range(runs))


def typo_words(questions, index, searcher):
    pp = index.preprocessor
    out, seen = [], set()
    for q in questions:
        if q["category"] != "typo":
            continue
        for orig, typo in zip(pp.query_words(q["original"]), pp.query_words(q["question"])):
            if orig != typo and typo not in seen and not searcher.trie.contains(typo) \
                    and len(typo) >= config.FUZZY_MIN_LEN:
                seen.add(typo)
                out.append((q["id"], typo, orig))
    return out


def correction_row(searcher, word, original):
    trie = searcher.trie
    stem = searcher.pp.stem
    k = max_edit_distance(len(word))
    osa, stats = trie_fuzzy_search(trie, word, k, "osa", STOPWORDS)
    lev, _ = trie_fuzzy_search(trie, word, k, "lev", STOPWORDS)
    t_osa = median_ms(lambda: trie_fuzzy_search(trie, word, k, "osa", STOPWORDS)[1]["time_ms"])
    t_brute = median_ms(lambda: brute_force_fuzzy(trie.words(), word, k, "osa", STOPWORDS)[1]["time_ms"], 3)
    bi, _ = searcher.ngram_index(2).lookup(word, min_j=0.0, k=1)
    tri, _ = searcher.ngram_index(3).lookup(word, min_j=0.0, k=1)
    return {
        "word": word, "original": original, "max_dist": k,
        "osa": osa[0][0] if osa else None, "osa_d": osa[0][1] if osa else None,
        "lev": lev[0][0] if lev else None, "lev_d": lev[0][1] if lev else None,
        "bigram": bi[0][0] if bi else None, "bigram_j": round(bi[0][1], 3) if bi else None,
        "trigram": tri[0][0] if tri else None, "trigram_j": round(tri[0][1], 3) if tri else None,
        "bigram_passes_min_j": bool(bi and bi[0][1] >= config.NGRAM_MIN_JACCARD),
        "nodes_visited": stats["nodes_visited"], "nodes_total": stats["nodes_total"],
        "ok": {t: bool(c) and stem(c[0][0]) == stem(original) for t, c in
               (("osa", osa), ("lev", lev), ("bigram", bi), ("trigram", tri))},
        "osa_ms": t_osa, "brute_ms": t_brute,
    }


def pick_rows(rows, n):
    def disagree(r):
        hits = {r["ok"]["osa"], r["ok"]["bigram"], r["ok"]["trigram"]}
        return len(hits) > 1 or not any(hits)
    first = [r for r in rows if disagree(r)]
    rest = [r for r in rows if not disagree(r)]
    return (first + rest)[:n]


def pick_examples(questions, index, exact, approx):
    chosen = []
    for q in questions:
        if q["category"] != "typo" or len(chosen) == 3:
            continue
        rel = relevant_chunks(index, q)
        e, a = exact.search(q["question"], "kmp").ids(), approx.search(q["question"]).ids()
        if a[:1] and a[0] in rel and not (e[:1] and e[0] in rel):
            chosen.append(q)
    for cat in ("literal", "paraphrase", "no_answer"):
        chosen.append(next(q for q in questions if q["category"] == cat))
    return chosen


def bank_noise(questions, index, exact, approx):
    pp = index.preprocessor
    out, extra = [], {"corrected_words": 0, "with_extra_candidates": 0, "examples": []}
    for q in questions:
        if q["category"] != "typo":
            continue
        originals = dict(zip(pp.query_words(q["question"]), pp.query_words(q["original"])))
        res = approx.search(q["question"])
        rel = relevant_chunks(index, q)
        hit_a = any(c in rel for c in res.ids())
        hit_e = any(c in rel for c in exact.search(q["question"], "kmp").ids())
        by_word = {}
        for c in res.details["corrections"]:
            by_word.setdefault(c["query_word"], []).append(c)
        for word, cands in by_word.items():
            orig = originals.get(word, word)
            stems = {c["stem"] for c in cands}
            extra["corrected_words"] += 1
            if pp.stem(orig) in stems and len(stems) > 1:
                extra["with_extra_candidates"] += 1
                if len(extra["examples"]) < 6:
                    extra["examples"].append(f"{word} -> " + ", ".join(c["candidate"] for c in cands))
            if pp.stem(orig) not in stems:
                out.append({"id": q["id"], "word": word, "original": orig,
                            "candidates": [format_correction(c) for c in cands],
                            "kind": "palabra correcta fuera del vocabulario" if word == orig else "corrección equivocada",
                            "hit5_exact": hit_e, "hit5_approx": hit_a})
    return out, extra


def neighbors_without_rules(trie, words):
    rows = []
    for w in words:
        found, _ = trie_fuzzy_search(trie, w, 1, "osa")
        near = [x for x, d, _ in found if x != w]
        rows.append({"word": w, "in_vocab": trie.contains(w), "neighbors_d1": near[:10],
                     "n_neighbors": len(near), "stopword_neighbors": [x for x in near if x in STOPWORDS][:8]})
    return rows


def md_table(header, rows):
    L = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    L += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return L


def cell(text):
    return str(text).replace("|", "/").replace("\n", " ")


def main():
    index = load_index()
    questions = load_questions()
    exact = ExactSearcher(index)
    approx = ApproximateSearcher(index)
    trie = approx.trie
    report = {"params": {k: getattr(config, k) for k in (
        "FUZZY_MIN_LEN", "FUZZY_MAX_DIST", "FUZZY_MAX_CANDIDATES", "NGRAM_N", "NGRAM_MIN_JACCARD",
        "JACCARD_RERANK_WEIGHT", "BM25_K1", "BM25_B", "PHRASE_WEIGHT", "TOP_K")},
        "trie": {"words": len(trie), "nodes": trie.n_nodes},
        "ngram_index": {n: {"words": len(approx.ngram_index(n)), "grams": len(approx.ngram_index(n).table)} for n in (2, 3)}}

    print("Correcciones por palabra…")
    words = typo_words(questions, index, approx)
    rows = [correction_row(approx, w, o) | {"id": qid} for qid, w, o in words]
    report["corrections"] = rows
    n = len(rows)
    acc = {t: sum(r["ok"][t] for r in rows) for t in ("osa", "lev", "bigram", "trigram")}
    report["corrections_summary"] = {
        "n_words": n, "top1_correct": acc,
        "avg_nodes_visited": statistics.mean(r["nodes_visited"] for r in rows),
        "avg_pct_nodes": 100 * statistics.mean(r["nodes_visited"] / r["nodes_total"] for r in rows),
        "avg_osa_ms": statistics.mean(r["osa_ms"] for r in rows),
        "avg_brute_ms": statistics.mean(r["brute_ms"] for r in rows)}

    print("Consultas de ejemplo…")
    examples = []
    for q in pick_examples(questions, index, exact, approx):
        rel = relevant_chunks(index, q)
        e = exact.search(q["question"], "kmp")
        a = approx.search(q["question"])
        examples.append({"question": q, "relevant": sorted(rel), "exact": e, "approx": a})

    print(f"Tiempos y calidad por técnica (mediana de {RUNS} corridas)…")
    timing = {}
    runs = [("kmp", lambda q: exact.search(q, "kmp"))] + \
           [(alg, (lambda alg: lambda q: approx.search(q, alg))(alg)) for alg in ALGORITHMS]
    for name, fn in runs:
        _, summ, cats = evaluate_search(fn, index, questions, repeats=RUNS)
        timing[name] = {"overall": summ, "by_category": cats}
        print(f"  {name:<14} {summ['time_ms_avg']:7.3f} ms | Hit@5 {summ['hit@5']:.3f} | MRR {summ['mrr']:.3f}")
    report["timing_quality"] = timing

    print("Falsos amigos…")
    noise, extra = bank_noise(questions, index, exact, approx)
    report["extra_candidates"] = extra
    short = sorted({w for q in questions for w in index.preprocessor.query_words(q["question"])
                    if w.isalpha() and len(w) < config.FUZZY_MIN_LEN})
    nb = neighbors_without_rules(trie, short + ["moon", "mars", "rings"])
    report["noise_bank"] = noise
    report["noise_without_rules"] = nb

    write_markdown(report, examples, config.RESULTS_DIR / "etapa4_busqueda_aproximada.md")
    report["examples"] = [{"id": x["question"]["id"], "category": x["question"]["category"],
                           "question": x["question"]["question"], "relevant": x["relevant"],
                           "exact": x["exact"].to_dict(), "approx": x["approx"].to_dict()} for x in examples]
    for x in report["examples"]:
        for side in ("exact", "approx"):
            for r in x[side]["results"]:
                r.pop("text", None)
    (config.RESULTS_DIR / "etapa4_busqueda_aproximada.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Reporte: {config.RESULTS_DIR / 'etapa4_busqueda_aproximada.md'}")


def write_markdown(rep, examples, path):
    p = rep["params"]
    cs = rep["corrections_summary"]
    L = ["# Etapa 4 - Recuperación mediante búsqueda aproximada\n",
         f"Colección: {examples[0]['exact'].n_total:,} fragmentos. Vocabulario del Trie: {rep['trie']['words']:,} palabras, "
         f"{rep['trie']['nodes']:,} nodos. Banco: preguntas de Ana + variantes con errores (`load_questions()`, semilla 42).\n",
         "## Algoritmos implementados\n"]
    L += md_table(["Algoritmo", "Cómo se calcula la similitud", "Técnica de diseño", "Complejidad"], [
        ["Levenshtein + Trie (`lev_trie`)", "d = mínimo de inserciones, borrados y sustituciones; peso = 1 − d / max(|w|, |c|)",
         "PD fila por fila + ramificación y poda", "O(V·m); peor caso O(N·m)"],
        ["OSA / Damerau + Trie (`osa_trie`)", "como Levenshtein, más transposición de letras adyacentes con costo 1",
         "PD fila por fila + ramificación y poda", "O(V·m); peor caso O(N·m)"],
        ["n-gramas + Jaccard (`ngram_jaccard`)", "J = |A ∩ B| / |A ∪ B| entre los n-gramas de `$palabra$`; peso = J",
         "hashing (tabla n-grama → palabras)", "O(Σ|posting|) por palabra; construcción O(Σ|w|)"],
        ["Híbrido (`hybrid`)", "unión de candidatos de OSA y bigramas; cada uno con su mayor similitud",
         "combinación de las anteriores", "suma de ambas"],
    ])
    L += ["\nm = longitud de la palabra, N = nodos del Trie, V = nodos visitados (V ≪ N por la poda), "
          "|w| = longitud de cada palabra del vocabulario.\n",
          "**Poda:** al bajar un nivel en el Trie, cada celda de la fila nueva se calcula a partir de la fila anterior "
          "más un costo ≥ 0, así que el mínimo de la fila nunca baja. Ese mínimo es una cota inferior de la distancia de "
          "cualquier palabra del subárbol: si ya supera el umbral, la rama se descarta.\n",
          "**Nuevo ordenamiento:** las palabras corregidas se convierten en raíces con peso igual a su similitud. Cada "
          "fragmento se puntúa con la fórmula de la búsqueda exacta (BM25 + bono por frases con el arreglo de sufijos "
          "+ factor 0.5 + cobertura), multiplicando la frecuencia de cada término por su peso y contando la cobertura "
          "por palabra de la pregunta. Después: score × (1 + β · Jaccard de trigramas pregunta–fragmento).\n",
          "### Parámetros\n"]
    L += md_table(["Parámetro", "Valor", "Significado"], [
        ["FUZZY_MIN_LEN", p["FUZZY_MIN_LEN"], "palabras más cortas no se corrigen"],
        ["FUZZY_MAX_DIST", p["FUZZY_MAX_DIST"], "longitud mínima → distancia máxima"],
        ["FUZZY_MAX_CANDIDATES", p["FUZZY_MAX_CANDIDATES"], "correcciones por palabra (solo las de mejor distancia/Jaccard)"],
        ["NGRAM_N", p["NGRAM_N"], "tamaño de los n-gramas"],
        ["NGRAM_MIN_JACCARD", p["NGRAM_MIN_JACCARD"], "Jaccard mínimo para aceptar un candidato"],
        ["JACCARD_RERANK_WEIGHT (β)", p["JACCARD_RERANK_WEIGHT"], "peso del reordenamiento por trigramas"],
        ["BM25_K1 / BM25_B / PHRASE_WEIGHT", f"{p['BM25_K1']} / {p['BM25_B']} / {p['PHRASE_WEIGHT']}", "los mismos de la exacta (Ana)"],
    ])

    L += [f"\n## Correcciones por palabra ({N_CORRECTION_ROWS} de {cs['n_words']} palabras con error del banco)\n",
          "Primero aparecen las palabras donde las técnicas no coinciden. ✓ = el primer candidato tiene la misma raíz que la palabra original (recupera lo mismo). "
          f"Tiempo de OSA = mediana de {RUNS} corridas; fuerza bruta = OSA contra todo el vocabulario (mediana de 3).\n"]
    ok = lambda t, r: "✓" if r["ok"][t] else "✗"

    L += md_table(["Palabra", "Original", "OSA (d)", "Levenshtein (d)", "Bigramas (J)", "Trigramas (J)",
                   "Nodos visitados", "OSA ms", "Fuerza bruta ms"],
                  [[r["word"], r["original"], f"{r['osa']} ({r['osa_d']}) {ok('osa', r)}",
                    f"{r['lev']} ({r['lev_d']}) {ok('lev', r)}" if r["lev"] else "— ✗",
                    f"{r['bigram']} ({r['bigram_j']}) {ok('bigram', r)}",
                    f"{r['trigram']} ({r['trigram_j']}) {ok('trigram', r)}",
                    f"{r['nodes_visited']:,} / {r['nodes_total']:,} ({100 * r['nodes_visited'] / r['nodes_total']:.1f}%)",
                    f"{r['osa_ms']:.2f}", f"{r['brute_ms']:.1f}"]
                   for r in pick_rows(rep["corrections"], N_CORRECTION_ROWS)])
    acc = cs["top1_correct"]
    L += [f"\n**Resumen sobre las {cs['n_words']} palabras:** primer candidato correcto con OSA {acc['osa']}, "
          f"Levenshtein {acc['lev']}, bigramas {acc['bigram']}, trigramas {acc['trigram']}. "
          f"Nodos visitados en promedio: {cs['avg_nodes_visited']:,.0f} ({cs['avg_pct_nodes']:.1f}% del Trie). "
          f"Tiempo promedio: OSA con poda {cs['avg_osa_ms']:.2f} ms contra {cs['avg_brute_ms']:.1f} ms de la fuerza bruta "
          f"({cs['avg_brute_ms'] / cs['avg_osa_ms']:.0f}× más rápido). La tabla completa está en el `.json`.\n"]

    L.append("## Consultas de ejemplo (exacta KMP contra aproximada híbrida)\n")
    for i, x in enumerate(examples, 1):
        q, e, a = x["question"], x["exact"], x["approx"]
        L += [f"### {i}. [{q['category']}] {q['id']}: \"{q['question']}\"\n",
              f"- Fragmentos relevantes (evidencia de Ana): {x['relevant'] or 'ninguno (sin respuesta en la colección)'}",
              f"- Exacta: términos {e.terms}; {e.n_examined} examinados; {e.time_ms:.2f} ms",
              f"- Aproximada: términos {a.terms}; {a.n_examined} examinados; {a.time_ms:.2f} ms; "
              f"nodos del Trie visitados {a.details['nodes_visited']:,}",
              f"- Correcciones: {'; '.join(format_correction(c) for c in a.details['corrections']) or 'ninguna'}\n"]
        rows = []
        for rank in range(max(len(e.results), len(a.results))):
            def fmt(res):
                if rank >= len(res.results):
                    return "", "", ""
                r = res.results[rank]
                rel = " ✓" if r.chunk_id in x["relevant"] else ""
                return f"{r.chunk_id}{rel}", f"{r.score:.3f} ({r.coverage:.0%})", cell(f"{r.doc} > {r.section}")[:60]
            rows.append([rank + 1, *fmt(e), *fmt(a)])
        L += md_table(["#", "Exacta: id", "puntaje (cobertura)", "documento > sección",
                       "Aproximada: id", "puntaje (cobertura)", "documento > sección"], rows)
        if a.results:
            snippet = highlight(a.results[0].text, a.terms)[:350]
            L.append(f"\nTop-1 aproximada: {cell(snippet)}…\n")
        L.append("✓ = fragmento relevante.\n")

    L += [f"## Tiempo y calidad por técnica (106 preguntas, mediana de {RUNS} corridas por pregunta)\n"]
    rows = []
    for name, t in rep["timing_quality"].items():
        o, c = t["overall"], t["by_category"]
        label = "KMP (exacta, línea base)" if name == "kmp" else ALGORITHM_LABELS[name]
        rows.append([label, f"{o['time_ms_avg']:.3f}", f"{o['time_ms_median']:.3f}", f"{o['examined_avg']:.1f}",
                     *(f"{c[k]['hit@5']:.3f}" for k in ("literal", "paraphrase", "typo")),
                     f"{o['hit@5']:.3f}", f"{o['mrr']:.3f}"])
    L += md_table(["Técnica", "ms prom.", "ms mediana", "Examinados", "Hit@5 literal", "Hit@5 paráfrasis",
                   "Hit@5 typo", "Hit@5 global", "MRR global"], rows)
    L.append("\nLa comparación completa (Hit@1/3, P@5, por categoría, escalabilidad y ablaciones) está en "
             "`results/etapa6_comparacion.md`.\n")

    L += ["## Cuándo la búsqueda aproximada introduce coincidencias poco útiles\n",
          "### Ruido real en el banco de preguntas\n",
          "Correcciones de la búsqueda híbrida que no recuperan la palabra original. \"Hit@5\" indica si algún fragmento "
          "relevante quedó en el top-5 de cada método para esa pregunta.\n"]
    L += md_table(["Pregunta", "Palabra", "Original", "Tipo", "Candidatos usados", "Hit@5 exacta", "Hit@5 aproximada"],
                  [[n["id"], n["word"], n["original"], n["kind"], cell("; ".join(n["candidates"])),
                    "sí" if n["hit5_exact"] else "no", "sí" if n["hit5_approx"] else "no"] for n in rep["noise_bank"]])
    ex = rep["extra_candidates"]
    L.append(f"\nAdemás, de {ex['corrected_words']} palabras corregidas en las variantes con errores, "
             f"{ex['with_extra_candidates']} incluyen la corrección buena **y** otros candidatos con la misma distancia, "
             f"que también suman puntaje (con peso menor). Ejemplos: {'; '.join(ex['examples'])}.")
    L += ["\n### Si se apagan las reglas (corregir palabras cortas o que ya existen)\n",
          "Vecinos a distancia OSA 1 de palabras de la pregunta que hoy no se corrigen (son cortas o ya están en el "
          "vocabulario). Con las reglas activas ninguno de estos candidatos entra a la búsqueda.\n"]
    L += md_table(["Palabra", "¿En el vocabulario?", "Vecinos a d = 1", "Cuántos", "De ellos, stopwords"],
                  [[r["word"], "sí" if r["in_vocab"] else "no", cell(", ".join(r["neighbors_d1"])) or "—",
                    r["n_neighbors"], ", ".join(r["stopword_neighbors"]) or "—"] for r in rep["noise_without_rules"]])
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
