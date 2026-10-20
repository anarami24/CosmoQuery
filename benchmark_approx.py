#ETAPA 6 - exacta contra aproximada, contexto y modelo

import argparse
import json
import math
import statistics
import textwrap
import time

import config
import qa_model
from approx_search import ALGORITHM_LABELS as APPROX_LABELS
from approx_search import ApproximateSearcher, format_correction
from approximate import brute_force_fuzzy, max_edit_distance, trie_fuzzy_search
from benchmark_exact import COLORS, INK, MUTED, _style, write_csv
from evaluation import answer_scores, evaluate_search, load_questions, relevant_chunks
from exact_search import ExactSearcher
from index_builder import load_index
from rag_pipeline import CosmoQuery
from string_matching import ALGORITHM_LABELS as EXACT_LABELS

APPROX_COLORS = {"lev_trie": "#64748b", "osa_trie": "#0f766e", "ngram_jaccard": "#a16207", "hybrid": "#7c3aed"}
COLOR = {**COLORS, **APPROX_COLORS}
LABEL = {**EXACT_LABELS, **APPROX_LABELS}
LABEL["kmp"] = "KMP + índice (exacta)"
LABEL["suffix_array"] = "Arreglo de sufijos (exacta)"
METHODS = [("kmp", "exact"), ("suffix_array", "exact"), ("lev_trie", "approximate"),
           ("osa_trie", "approximate"), ("ngram_jaccard", "approximate"), ("hybrid", "approximate")]
CATEGORIES = ["literal", "paraphrase", "typo", "no_answer"]
CAT_NAMES = {"literal": "Literales", "paraphrase": "Paráfrasis", "typo": "Con errores", "no_answer": "Sin respuesta"}
STRATEGIES = [("topk1", "top-k (k=1)", "topk", False, 1, None), ("topk3", "top-k (k=3)", "topk", False, 3, None),
              ("topk5", "top-k (k=5)", "topk", False, 5, None), ("greedy", "voraz", "greedy", True, None, None),
              ("greedy_nored", "voraz sin redundancia", "greedy", False, None, None),
              ("greedy_red03", "voraz, redundancia 0.3", "greedy", True, None, 0.3),
              ("dp", "PD (mochila)", "dp", True, None, None)]
RAG_METHODS = [("exact", "kmp", "Exacta (KMP)"), ("approximate", "hybrid", "Aproximada (híbrida)")]
# se incluye siempre el umbral configurado (por ejemplo 0.5) para poder compararlo
THRESHOLDS = sorted({0, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12} | {config.NO_ANSWER_THRESHOLD})
CACHE_FILE = config.BASE_DIR / ".cache" / "qa_answers.json"
F1_OK = 0.5


def clean(x):
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return None
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def searcher_fn(exact, approx, alg, **kw):
    if alg in ("kmp", "suffix_array"):
        return lambda q: exact.search(q, alg, config.TOP_K)
    return lambda q: approx.search(q, alg, config.TOP_K, **kw)


def experiment_methods(index, questions, exact, approx, repeats):
    summary, per_question, by_cat = [], [], {}
    for alg, method in METHODS:
        rows, summ, cats = evaluate_search(searcher_fn(exact, approx, alg), index, questions, repeats=repeats)
        summary.append({"algorithm": alg, "method": method, **summ})
        by_cat[alg] = cats
        per_question += [{"algorithm": alg, **r} for r in rows]
        print(f"  {alg:<14} {summ['time_ms_avg']:8.3f} ms | Hit@5 {summ.get('hit@5', 0):.3f} | MRR {summ.get('mrr', 0):.3f}")
    return summary, per_question, by_cat


def check_against_ana(by_cat):
    path = config.RESULTS_DIR / "etapa6_exacta.json"
    if not path.exists():
        return {"available": False}
    ana = json.loads(path.read_text(encoding="utf-8"))["by_category"]
    diffs = []
    for cat in ("literal", "paraphrase", "typo"):
        for m in ("hit@1", "hit@5", "mrr"):
            a, b = ana.get(cat, {}).get(m), by_cat["kmp"].get(cat, {}).get(m)
            if a is None or b is None or abs(a - b) > 1e-9:
                diffs.append({"category": cat, "metric": m, "ana": a, "persona2": b})
    return {"available": True, "match": not diffs, "differences": diffs}


def experiment_cases(index, questions, exact, approx, per_question):
    rows = {(r["algorithm"], r["id"]): r for r in per_question}
    same, approx_wins, exact_wins = [], [], []
    for q in questions:
        if q["category"] == "no_answer":
            continue
        e, a = rows[("kmp", q["id"])], rows[("hybrid", q["id"])]
        rel = relevant_chunks(index, q)
        if e["retrieved"][:1] and e["retrieved"][:1] == a["retrieved"][:1] and e["retrieved"][0] in rel:
            same.append(q)
        if a["hit@5"] and not e["hit@5"]:
            approx_wins.append(q)
        if e["hit@5"] and not a["hit@5"]:
            exact_wins.append(q)
        elif e["hit@1"] and not a["hit@1"]:
            exact_wins.append(q)

    def detail(q):
        rel = relevant_chunks(index, q)
        out = {"id": q["id"], "category": q["category"], "question": q["question"], "relevant": sorted(rel)}
        for name, res in (("exact", exact.search(q["question"], "kmp")), ("approx", approx.search(q["question"]))):
            out[name] = [{"id": r.chunk_id, "doc": r.doc, "section": r.section, "score": r.score,
                          "relevant": r.chunk_id in rel} for r in res.results[:3]]
            if name == "approx":
                out["corrections"] = [format_correction(c) for c in res.details["corrections"]]
        return out
    return {"same": [detail(q) for q in same[:3]], "approx_wins": [detail(q) for q in approx_wins[:3]],
            "exact_wins": [detail(q) for q in exact_wins],
            "counts": {"same_top1": len(same), "approx_only_hit5": len(approx_wins), "exact_better": len(exact_wins)}}


def experiment_pruning(index, questions, approx, repeats):
    trie, pp = approx.trie, index.preprocessor
    vocab = trie.words()
    words = []
    for q in questions:
        for w in pp.query_words(q["question"]):
            if w.isalpha() and len(w) >= config.FUZZY_MIN_LEN and not trie.contains(w) and w not in words:
                words.append(w)
    rows = []
    for w in words:
        k = max_edit_distance(len(w))
        found, stats = trie_fuzzy_search(trie, w, k, "osa")
        t_trie = statistics.median(trie_fuzzy_search(trie, w, k, "osa")[1]["time_ms"] for _ in range(repeats))
        brute, bstats = brute_force_fuzzy(vocab, w, k, "osa")
        t_brute = statistics.median([bstats["time_ms"]] + [brute_force_fuzzy(vocab, w, k, "osa")[1]["time_ms"]
                                                          for _ in range(repeats - 1)])
        rows.append({"word": w, "length": len(w), "max_dist": k, "nodes_visited": stats["nodes_visited"],
                     "nodes_total": stats["nodes_total"], "pct_nodes": 100 * stats["nodes_visited"] / stats["nodes_total"],
                     "found": len(found), "same_as_brute": found == brute, "trie_ms": t_trie, "brute_ms": t_brute,
                     "speedup": t_brute / max(t_trie, 1e-9)})
    summary = {}
    for label, sub in (("todas", rows), ("d = 1", [r for r in rows if r["max_dist"] == 1]),
                       ("d = 2", [r for r in rows if r["max_dist"] == 2])):
        if sub:
            summary[label] = {"n": len(sub), "nodes_avg": statistics.mean(r["nodes_visited"] for r in sub),
                              "pct_avg": statistics.mean(r["pct_nodes"] for r in sub),
                              "trie_ms_avg": statistics.mean(r["trie_ms"] for r in sub),
                              "brute_ms_avg": statistics.mean(r["brute_ms"] for r in sub),
                              "speedup_avg": statistics.mean(r["speedup"] for r in sub),
                              "all_same": all(r["same_as_brute"] for r in sub)}
    return rows, summary


def experiment_ablations(index, questions, approx, repeats):
    variants = [
        ("Regla de distancia", "fija en 1", "hybrid", {"max_dist_rules": {4: 1}}),
        ("Regla de distancia", "fija en 2", "hybrid", {"max_dist_rules": {4: 2}}),
        ("Regla de distancia", "por longitud (elegida)", "hybrid", {}),
        ("n de los n-gramas", "n = 2 (elegido)", "ngram_jaccard", {"ngram_n": 2}),
        ("n de los n-gramas", "n = 3", "ngram_jaccard", {"ngram_n": 3}),
        ("β (reordenamiento por Jaccard)", "β = 0", "hybrid", {"rerank_beta": 0.0}),
        ("β (reordenamiento por Jaccard)", "β = 0.1 (elegido)", "hybrid", {"rerank_beta": 0.1}),
        ("β (reordenamiento por Jaccard)", "β = 0.3", "hybrid", {"rerank_beta": 0.3}),
        ("Bono por frases", "con frases (elegido)", "hybrid", {"use_phrases": True}),
        ("Bono por frases", "sin frases", "hybrid", {"use_phrases": False}),
        ("LCS de términos (γ)", "γ = 0 (elegido)", "hybrid", {"lcs_weight": 0.0}),
        ("LCS de términos (γ)", "γ = 0.5", "hybrid", {"lcs_weight": 0.5}),
        ("LCS de términos (γ)", "γ = 1.0", "hybrid", {"lcs_weight": 1.0}),
    ]
    out = []
    for group, name, alg, kw in variants:
        _, summ, cats = evaluate_search(lambda q: approx.search(q, alg, config.TOP_K, **kw), index, questions,
                                        repeats=repeats)
        out.append({"group": group, "variant": name, "algorithm": alg, "time_ms_avg": summ["time_ms_avg"],
                    "hit@5": summ.get("hit@5", 0), "mrr": summ.get("mrr", 0),
                    "hit@5_literal": cats.get("literal", {}).get("hit@5"),
                    "hit@5_typo": cats.get("typo", {}).get("hit@5"), "mrr_typo": cats.get("typo", {}).get("mrr")})
        print(f"  {group:<32} {name:<24} Hit@5 {out[-1]['hit@5']:.3f} | MRR {out[-1]['mrr']:.3f}")
    return out


def experiment_scaling(index, questions, fractions, repeats):
    sample = [q for q in questions if q["category"] == "literal"][:10] + \
             [q for q in questions if q["category"] == "typo"][:10]
    total = len(index.chunks)
    rows = []
    for frac in fractions:
        n = max(1, int(total * frac))
        sub = index.subset(n)
        t0 = time.perf_counter()
        approx = ApproximateSearcher(sub)
        t_trie = time.perf_counter() - t0
        t0 = time.perf_counter()
        approx.ngram_index()
        t_ngram = time.perf_counter() - t0
        exact = ExactSearcher(sub)
        row = {"fraction": frac, "n_chunks": n, "vocab_words": len(approx.trie), "trie_nodes": approx.trie.n_nodes,
               "tokens": sum(len(t) for t in sub.stem_tokens), "build_trie_s": t_trie, "build_ngram_s": t_ngram}
        for alg in ("kmp", "suffix_array", "osa_trie", "ngram_jaccard", "hybrid"):
            fn = searcher_fn(exact, approx, alg)
            times = [statistics.median(fn(q["question"]).time_ms for _ in range(repeats)) for q in sample]
            row[f"{alg}_ms"] = statistics.mean(times)
        rows.append(row)
        print(f"  {frac:>5.0%} {n:>4} fragmentos, vocabulario {row['vocab_words']:>5,}: " +
              "  ".join(f"{a}={row[a + '_ms']:.2f}" for a in ("kmp", "suffix_array", "osa_trie", "ngram_jaccard", "hybrid")))
    return rows


def experiment_context(cq, questions):
    index = cq.index
    records = []
    t_start = time.perf_counter()
    for qi, q in enumerate(questions, 1):
        rel = relevant_chunks(index, q)
        for method, alg, _ in RAG_METHODS:
            for key, _, selection, redundancy, k, red_t in STRATEGIES:
                r = cq.ask(q["question"], method, alg, selection, redundancy, k, use_cache=True,
                           redundancy_threshold=red_t)
                sc = answer_scores(r.answer, q["answers"], config.NO_ANSWER_TEXT)
                raw = r.extra.get("raw_answer", "")
                selected = [s.chunk_id for s in r.selected]
                records.append({
                    "id": q["id"], "category": q["category"], "method": method, "strategy": key,
                    "answer": r.answer, "raw_answer": raw, "score_difference": r.score_difference,
                    "em": sc["em"], "f1": sc["f1"],
                    "raw_f1": answer_scores(raw, q["answers"])["f1"] if q["answers"] and raw else 0.0,
                    "idk": r.is_no_answer, "answerable": bool(q["answers"]),
                    "evidence_in_context": bool(rel & set(selected)), "selected": selected,
                    "tokens_context": r.tokens_context, "tokens_used": r.tokens_used, "token_budget": r.token_budget,
                    "truncated": r.truncated, "t_model_ms": r.t_model_ms, "t_select_ms": r.t_select_ms,
                    "redundant_dropped": sum("redundante" in why for _, why in r.discarded),
                    "total_value": r.extra["total_value"]})
        if qi % 10 == 0:
            qa_model.save_cache(CACHE_FILE)
            print(f"  {qi}/{len(questions)} preguntas ({time.perf_counter() - t_start:.0f} s)")
    qa_model.save_cache(CACHE_FILE)
    summary = []
    for method, _, mlabel in RAG_METHODS:
        for key, slabel, *_ in STRATEGIES:
            rs = [r for r in records if r["method"] == method and r["strategy"] == key]
            ans = [r for r in rs if r["answerable"]]
            noans = [r for r in rs if not r["answerable"]]
            summary.append({
                "method": method, "method_label": mlabel, "strategy": key, "strategy_label": slabel,
                "n": len(rs), "em": statistics.mean(r["em"] for r in rs), "f1": statistics.mean(r["f1"] for r in rs),
                "f1_answerable": statistics.mean(r["f1"] for r in ans) if ans else None,
                "raw_f1_answerable": statistics.mean(r["raw_f1"] for r in ans) if ans else None,
                "idk_rate": statistics.mean(r["idk"] for r in rs),
                "no_answer_acc": statistics.mean(r["idk"] for r in noans) if noans else None,
                "evidence_recall": statistics.mean(r["evidence_in_context"] for r in ans) if ans else None,
                "tokens_context_avg": statistics.mean(r["tokens_context"] for r in rs),
                "tokens_used_avg": statistics.mean(r["tokens_used"] for r in rs),
                "budget_avg": statistics.mean(r["token_budget"] for r in rs),
                "truncated": sum(r["truncated"] for r in rs),
                "chunks_avg": statistics.mean(len(r["selected"]) for r in rs),
                "redundant_dropped_avg": statistics.mean(r["redundant_dropped"] for r in rs),
                "t_model_ms_avg": statistics.mean(r["t_model_ms"] for r in rs)})
            s = summary[-1]
            print(f"  {mlabel:<22} {slabel:<22} F1 {s['f1']:.3f} | IDK {s['idk_rate']:.2f} | evidencia "
                  f"{s['evidence_recall'] or 0:.2f} | truncadas {s['truncated']}")
    return records, summary


def redundancy_stats(index, seed=42):
    import random
    from approximate import jaccard_words
    st, ch = index.stem_tokens, index.chunks
    cons = sorted(jaccard_words(st[i], st[i + 1]) for i in range(len(ch) - 1) if ch[i]["doc"] == ch[i + 1]["doc"])
    rng = random.Random(seed)
    rnd = sorted(jaccard_words(st[a], st[b]) for a, b in (rng.sample(range(len(ch)), 2) for _ in range(2000)))
    pct = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
    return {"consecutive": {"n": len(cons), "median": statistics.median(cons), "p90": pct(cons, 0.9), "max": cons[-1],
                            "above": {t: sum(c > t for c in cons) for t in (0.2, 0.3, 0.4, 0.5)}},
            "random": {"n": len(rnd), "median": statistics.median(rnd), "p99": pct(rnd, 0.99), "max": rnd[-1],
                       "above": {t: sum(c > t for c in rnd) for t in (0.2, 0.3, 0.4, 0.5)}}}


def experiment_threshold(records):
    sweeps = []
    for method, strategy in (("approximate", "greedy"), ("approximate", "topk1"), ("exact", "greedy")):
        rs = [r for r in records if r["method"] == method and r["strategy"] == strategy]
        for t in THRESHOLDS:
            f1s, f1_ans, noans = [], [], []
            for r in rs:
                sd = r["score_difference"]
                answered = r["raw_answer"] and sd is not None and not math.isinf(sd) and sd >= t
                if r["answerable"]:
                    f = r["raw_f1"] if answered else 0.0
                    f1_ans.append(f)
                else:
                    f = 0.0 if answered else 1.0
                    noans.append(f)
                f1s.append(f)
            sweeps.append({"method": method, "strategy": strategy, "threshold": t, "f1": statistics.mean(f1s),
                           "f1_answerable": statistics.mean(f1_ans) if f1_ans else None,
                           "no_answer_acc": statistics.mean(noans) if noans else None})
    by_strategy = []
    for key, label, *_ in STRATEGIES:
        rs = [r for r in records if r["method"] == "approximate" and r["strategy"] == key
              and r["answerable"] and r["raw_f1"] >= F1_OK]
        sds = [r["score_difference"] for r in rs]
        by_strategy.append({"strategy": key, "strategy_label": label, "n_correct_spans": len(rs),
                            "tokens_context_avg": statistics.mean(r["tokens_context"] for r in rs) if rs else None,
                            "sd_avg": statistics.mean(sds) if sds else None,
                            "sd_median": statistics.median(sds) if sds else None,
                            "pct_above_threshold": 100 * statistics.mean(s >= config.NO_ANSWER_THRESHOLD for s in sds) if sds else None})
    return sweeps, by_strategy


def experiment_greedy_vs_dp(records):
    out = {}
    for method, _, mlabel in RAG_METHODS:
        g = {r["id"]: r for r in records if r["method"] == method and r["strategy"] == "greedy"}
        d = {r["id"]: r for r in records if r["method"] == method and r["strategy"] == "dp"}
        diff = [i for i in g if set(g[i]["selected"]) != set(d[i]["selected"])]
        gaps = [d[i]["total_value"] - g[i]["total_value"] for i in g]
        out[method] = {
            "label": mlabel, "n": len(g), "different_sets": len(diff),
            "value_gap_avg": statistics.mean(gaps), "value_gap_max": max(gaps),
            "value_gap_pct_avg": statistics.mean(100 * (d[i]["total_value"] - g[i]["total_value"]) / d[i]["total_value"]
                                                 for i in g if d[i]["total_value"] > 0),
            "answer_changed": sum(g[i]["answer"] != d[i]["answer"] for i in g),
            "f1_greedy": statistics.mean(g[i]["f1"] for i in g), "f1_dp": statistics.mean(d[i]["f1"] for i in g),
            "t_select_greedy_ms": statistics.mean(g[i]["t_select_ms"] for i in g),
            "t_select_dp_ms": statistics.mean(d[i]["t_select_ms"] for i in g),
            "examples": [{"id": i, "method": mlabel, "greedy": g[i]["selected"], "dp": d[i]["selected"],
                          "greedy_value": round(g[i]["total_value"], 3), "dp_value": round(d[i]["total_value"], 3),
                          "greedy_answer": g[i]["answer"], "dp_answer": d[i]["answer"]} for i in diff[:5]]}
    return out


def make_plots(summary, by_cat, pruning, scaling, ctx_summary, sweeps):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib no está instalado: se omiten las gráficas)")
        return []
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    files = []

    def save(fig, name):
        fig.tight_layout()
        path = config.FIGURES_DIR / name
        fig.savefig(path, dpi=160)
        plt.close(fig)
        files.append(path)

    cats = ["literal", "paraphrase", "typo"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    width = 0.8 / len(METHODS)
    for j, (alg, _) in enumerate(METHODS):
        vals = [by_cat[alg].get(c, {}).get("hit@5", 0) for c in cats]
        pos = [i + (j - (len(METHODS) - 1) / 2) * width for i in range(len(cats))]
        ax.bar(pos, vals, width - 0.02, color=COLOR[alg], edgecolor="white", linewidth=1.5, label=LABEL[alg])
        for p, v in zip(pos, vals):
            ax.text(p, v + 0.02, f"{v:.2f}", ha="center", fontsize=6.5, color=INK)
    ax.set_xticks(range(len(cats)), [CAT_NAMES[c] for c in cats])
    ax.set_ylim(0, 1.12)
    _style(ax, "Hit@5 por tipo de pregunta: exacta contra aproximada", "", "Hit@5")
    ax.legend(fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    save(fig, "comp_hit5_categorias.png")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    vals = [s["time_ms_avg"] for s in summary]
    ax.bar(range(len(vals)), vals, color=[COLOR[s["algorithm"]] for s in summary], edgecolor="white", linewidth=2)
    for i, v in enumerate(vals):
        ax.text(i, v * 1.12, f"{v:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_yscale("log")
    ax.set_xticks(range(len(vals)), [LABEL[s["algorithm"]].replace(" (", "\n(").replace(" + ", "\n+ ") for s in summary],
                  fontsize=7)
    _style(ax, "Tiempo promedio de búsqueda por consulta (escala log)", "", "ms por consulta")
    save(fig, "comp_tiempo.png")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    for k, color in ((1, APPROX_COLORS["osa_trie"]), (2, APPROX_COLORS["hybrid"])):
        pts = [r for r in pruning if r["max_dist"] == k]
        ax.scatter([r["length"] for r in pts], [r["pct_nodes"] for r in pts], color=color, s=28, alpha=0.8,
                   label=f"distancia máxima {k} ({len(pts)} palabras)")
    _style(ax, "Poda en el Trie: nodos visitados por palabra corregida", "longitud de la palabra",
           "% de los nodos del Trie")
    ax.legend(fontsize=8, frameon=False)
    save(fig, "comp_poda.png")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, xkey, xlabel in ((axes[0], "n_chunks", "fragmentos en la colección"),
                             (axes[1], "vocab_words", "palabras en el vocabulario (Trie)")):
        for alg in ("kmp", "suffix_array", "osa_trie", "ngram_jaccard", "hybrid"):
            ax.plot([r[xkey] for r in scaling], [r[f"{alg}_ms"] for r in scaling], marker="o", markersize=5,
                    linewidth=2, color=COLOR[alg], label=LABEL[alg])
        ax.set_yscale("log")
        _style(ax, "Tiempo por consulta vs. " + ("fragmentos" if xkey == "n_chunks" else "vocabulario"),
               xlabel, "ms por consulta (log)")
    axes[1].legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    save(fig, "comp_escalabilidad.png")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    width = 0.38
    colors = {"exact": COLORS["kmp"], "approximate": APPROX_COLORS["hybrid"]}
    for j, (method, _, mlabel) in enumerate(RAG_METHODS):
        rows = [s for s in ctx_summary if s["method"] == method]
        pos = [i + (j - 0.5) * width for i in range(len(rows))]
        ax.bar(pos, [s["f1"] for s in rows], width - 0.02, color=colors[method], edgecolor="white",
               linewidth=1.5, label=mlabel)
        for p, s in zip(pos, rows):
            ax.text(p, s["f1"] + 0.015, f"{s['f1']:.2f}", ha="center", fontsize=7, color=INK)
    ax.set_xticks(range(len(STRATEGIES)), [textwrap.fill(s[1], 12) for s in STRATEGIES], fontsize=8)
    ax.set_ylim(0, max(s["f1"] for s in ctx_summary) + 0.12)
    _style(ax, "F1 de la respuesta según la estrategia de contexto", "", "F1 promedio")
    ax.legend(fontsize=8, frameon=False)
    save(fig, "comp_contexto_f1.png")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    rows = [s for s in sweeps if s["method"] == "approximate" and s["strategy"] == "greedy"]
    t = [s["threshold"] for s in rows]
    ax.plot(t, [s["f1_answerable"] for s in rows], marker="o", linewidth=2, color=APPROX_COLORS["hybrid"],
            label="F1 en preguntas con respuesta")
    if rows[0]["no_answer_acc"] is not None:
        ax.plot(t, [s["no_answer_acc"] for s in rows], marker="s", linewidth=2, color=COLORS["kmp"],
                label="aciertos en preguntas sin respuesta")
    ax.plot(t, [s["f1"] for s in rows], marker="^", linewidth=2, color=MUTED, label="F1 global")
    ax.axvline(config.NO_ANSWER_THRESHOLD, color=INK, linestyle="--", linewidth=1)
    ax.text(config.NO_ANSWER_THRESHOLD + 0.15, 0.03, f"umbral elegido ({config.NO_ANSWER_THRESHOLD:g})", fontsize=8, color=INK)
    ax.axvline(7, color=MUTED, linestyle=":", linewidth=1)
    ax.text(7.15, 0.10, "PokeChat (7)", fontsize=8, color=MUTED)
    ax.set_ylim(0, 1.05)
    _style(ax, "Umbral de \"I don't know\" (aproximada, contexto voraz)", "umbral de score_difference", "")
    ax.legend(fontsize=8, frameon=False)
    save(fig, "comp_umbral.png")
    return files


def f3(x):
    return "—" if x is None else f"{x:.3f}"


def write_markdown(path, ctx):
    L = ["# Etapa 6 - Comparación de la búsqueda exacta contra la aproximada\n",
         f"Banco: **{ctx['n_questions']} preguntas** de Ana (`load_questions()`, semilla 42)"
         f"{' — modo rápido (subconjunto, 1 repetición)' if ctx['quick'] else ''}. "
         f"Tiempos de búsqueda: mediana de {ctx['repeats']} repeticiones por pregunta. Top-{config.TOP_K}.\n"]
    chk = ctx["check_ana"]
    if not ctx["quick"] and chk.get("available"):
        L.append("> Verificación: los números de la exacta (KMP) "
                 + ("**coinciden** con `results/etapa6_exacta.json` de Ana.\n" if chk["match"]
                    else f"**NO coinciden** con los de Ana: {chk['differences']}\n"))

    L += ["## A. Exacta contra aproximada (recuperación)\n",
          "| Método | Tiempo prom. (ms) | Mediana (ms) | Examinados | Recuperados (score>0) | Hit@1 | Hit@3 | Hit@5 | MRR | P@5 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in ctx["summary"]:
        L.append(f"| {LABEL[s['algorithm']]} | {s['time_ms_avg']:.3f} | {s['time_ms_median']:.3f} | {s['examined_avg']:.1f} | "
                 f"{s['matched_avg']:.1f} | {f3(s.get('hit@1'))} | {f3(s.get('hit@3'))} | {f3(s.get('hit@5'))} | "
                 f"{f3(s.get('mrr'))} | {f3(s.get('p@5'))} |")
    L.append("\n### Por categoría\n")
    L += ["| Método | Categoría | n | ms prom. | Examinados | Recuperados | Hit@1 | Hit@3 | Hit@5 | MRR | P@5 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for alg, _ in METHODS:
        for c in CATEGORIES:
            s = ctx["by_cat"][alg].get(c)
            if s:
                L.append(f"| {LABEL[alg]} | {c} | {s['n']} | {s['time_ms_avg']:.3f} | {s['examined_avg']:.1f} | "
                         f"{s['matched_avg']:.1f} | {f3(s.get('hit@1'))} | {f3(s.get('hit@3'))} | {f3(s.get('hit@5'))} | "
                         f"{f3(s.get('mrr'))} | {f3(s.get('p@5'))} |")
    L.append("\nEn `no_answer` no hay métricas de ranking (no existe fragmento relevante); solo tiempo y recuperados.\n")

    cases = ctx["cases"]
    L += ["## B. Casos parecidos y casos distintos (exacta KMP contra aproximada híbrida)\n",
          f"Conteos sobre las preguntas con respuesta: mismo top-1 relevante en {cases['counts']['same_top1']}; "
          f"solo la aproximada tiene un relevante en el top-5 en {cases['counts']['approx_only_hit5']}; "
          f"la exacta es mejor (Hit@5, o Hit@1 si ambas tienen Hit@5) en {cases['counts']['exact_better']}.\n"]
    for key, title in (("same", "Ambos métodos coinciden en el top-1 relevante"),
                       ("approx_wins", "La aproximada acierta y la exacta falla"),
                       ("exact_wins", "La exacta acierta y la aproximada falla o baja (ruido de la corrección)")):
        L.append(f"### {title}\n")
        if not cases[key]:
            L.append("Ningún caso en este banco.\n")
        for c in cases[key]:
            L += [f"**{c['id']}** [{c['category']}] {c['question']} · relevantes: {c['relevant']} · "
                  f"correcciones: {'; '.join(c['corrections']) or 'ninguna'}\n",
                  "| # | Exacta | Aproximada |", "|---|---|---|"]
            for i in range(3):
                def fmt(lst):
                    if i >= len(lst):
                        return ""
                    r = lst[i]
                    return f"{r['id']}{' ✓' if r['relevant'] else ''} · {r['doc']} > {r['section'][:45]} · {r['score']:.2f}"
                L.append(f"| {i + 1} | {fmt(c['exact'])} | {fmt(c['approx'])} |")
            L.append("")

    L += ["## C. Evidencia de la poda (OSA sobre el Trie contra fuerza bruta)\n",
          f"Todas las palabras de las preguntas que no están en el vocabulario y se corrigen ({len(ctx['pruning'])}). "
          f"Fuerza bruta = OSA contra las {ctx['vocab_size']:,} palabras del vocabulario.\n",
          "| Grupo | Palabras | Nodos visitados prom. | % del Trie | OSA + Trie (ms) | Fuerza bruta (ms) | Aceleración | Mismo resultado |",
          "|---|---:|---:|---:|---:|---:|---:|---|"]
    for k, s in ctx["pruning_summary"].items():
        L.append(f"| {k} | {s['n']} | {s['nodes_avg']:,.0f} | {s['pct_avg']:.1f}% | {s['trie_ms_avg']:.2f} | "
                 f"{s['brute_ms_avg']:.1f} | {s['speedup_avg']:.0f}× | {'sí' if s['all_same'] else 'NO'} |")
    L.append("\nDetalle por palabra en `results/etapa6_aprox_poda.csv`.\n")

    L += ["## D. Ablaciones (calidad y tiempo)\n",
          "| Factor | Variante | Algoritmo | Hit@5 | MRR | Hit@5 literal | Hit@5 typo | MRR typo | ms prom. |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for a in ctx["ablations"]:
        L.append(f"| {a['group']} | {a['variant']} | {a['algorithm']} | {a['hit@5']:.3f} | {a['mrr']:.3f} | "
                 f"{f3(a['hit@5_literal'])} | {f3(a['hit@5_typo'])} | {f3(a['mrr_typo'])} | {a['time_ms_avg']:.3f} |")
    L.append("")

    L += ["## E. Tamaño de la colección\n",
          "Consultas: 10 literales + 10 con errores. ms promedio por consulta. El Trie y el índice de n-gramas se "
          "reconstruyen con el vocabulario de cada subconjunto (sin stopwords).\n",
          "| % | Fragmentos | Tokens | Vocabulario | Nodos Trie | Construir Trie (s) | Construir n-gramas (s) | KMP | Arreglo de sufijos | OSA + Trie | n-gramas | Híbrido |",
          "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in ctx["scaling"]:
        L.append(f"| {r['fraction']:.0%} | {r['n_chunks']:,} | {r['tokens']:,} | {r['vocab_words']:,} | {r['trie_nodes']:,} | "
                 f"{r['build_trie_s']:.3f} | {r['build_ngram_s']:.3f} | {r['kmp_ms']:.2f} | {r['suffix_array_ms']:.2f} | "
                 f"{r['osa_trie_ms']:.2f} | {r['ngram_jaccard_ms']:.2f} | {r['hybrid_ms']:.2f} |")
    L.append("")

    L += ["## F. Efecto del contexto en el modelo\n",
          f"Modelo `{config.QA_MODEL}` con la lógica del PokeChat (umbral {config.NO_ANSWER_THRESHOLD:g}). "
          f"Recuperación de {config.CONTEXT_CANDIDATES} candidatos; top-k no usa presupuesto ni redundancia. "
          "El modelo lee cada fragmento elegido por separado y se queda con la respuesta de mayor score_difference, "
          "así que leer más fragmentos cuesta tiempo (una llamada al modelo por fragmento), no tokens. "
          "\"Evidencia\" = algún fragmento relevante quedó en el contexto (solo preguntas con respuesta). "
          "\"F1 sin umbral\" = F1 del tramo que eligió el modelo antes de aplicar el umbral.\n",
          "| Búsqueda | Estrategia | EM | F1 | F1 (con respuesta) | F1 sin umbral | \"I don't know\" | Aciertos sin respuesta | "
          "Evidencia | Fragmentos | Redundantes descartados | Tokens contexto / presupuesto | Truncadas | Modelo ms |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in ctx["context_summary"]:
        L.append(f"| {s['method_label']} | {s['strategy_label']} | {s['em']:.3f} | {s['f1']:.3f} | {f3(s['f1_answerable'])} | "
                 f"{f3(s['raw_f1_answerable'])} | {s['idk_rate']:.2f} | {f3(s['no_answer_acc'])} | {f3(s['evidence_recall'])} | "
                 f"{s['chunks_avg']:.1f} | {s['redundant_dropped_avg']:.2f} | {s['tokens_context_avg']:.0f} / {s['budget_avg']:.0f} | "
                 f"{s['truncated']} | {s['t_model_ms_avg']:.0f} |")
    rs = ctx["redundancy_stats"]
    c, r = rs["consecutive"], rs["random"]
    L += [f"\n**Umbral de redundancia (REDUNDANCY_JACCARD = {config.REDUNDANCY_JACCARD:g}).** Jaccard de raíces entre "
          f"fragmentos consecutivos del mismo documento ({c['n']} pares): mediana {c['median']:.3f}, p90 {c['p90']:.3f}, "
          f"máximo {c['max']:.3f}. Entre pares al azar ({r['n']}): mediana {r['median']:.3f}, p99 {r['p99']:.3f}, "
          f"máximo {r['max']:.3f}.\n",
          "| Umbral | Pares consecutivos que lo superan | Pares al azar que lo superan |", "|---:|---:|---:|"]
    L += [f"| {t} | {c['above'][t]} | {r['above'][t]} |" for t in c["above"]]
    L.append("")

    L += ["## G. Umbral de \"I don't know\"\n",
          "Barrido sobre las respuestas ya calculadas (no se vuelve a correr el modelo): con umbral t, la respuesta es el "
          f"tramo del modelo si score_difference ≥ t. El sistema usa t = {config.NO_ANSWER_THRESHOLD:g}, calibrado "
          "con calibrar_umbral.py (el PokeChat usaba 7).\n",
          "| Búsqueda / estrategia | " + " | ".join(f"t={t}" for t in THRESHOLDS) + " |",
          "|---|" + "---:|" * len(THRESHOLDS)]
    for method, strategy in (("approximate", "greedy"), ("approximate", "topk1"), ("exact", "greedy")):
        rows = [s for s in ctx["threshold"] if s["method"] == method and s["strategy"] == strategy]
        for metric, mname in (("f1_answerable", "F1 con respuesta"), ("no_answer_acc", "aciertos sin respuesta")):
            L.append(f"| {method} / {strategy} · {mname} | " + " | ".join(f3(r[metric]) for r in rows) + " |")
    noans = [r for r in ctx["records"] if not r["answerable"]]
    empty = sum(1 for r in noans if not r["raw_answer"])
    L.append(f"\nEn las preguntas sin respuesta, el modelo eligió el token `<s>` (sin tramo) en {empty} de {len(noans)} "
             "corridas; por eso aciertan con cualquier umbral.")
    L += ["\n### score_difference de los tramos correctos según el contexto (aproximada)\n",
          "| Estrategia | Tramos correctos | Tokens de contexto prom. | score_difference prom. | Mediana | % ≥ umbral |",
          "|---|---:|---:|---:|---:|---:|"]
    for r in ctx["threshold_by_strategy"]:
        tokens = "—" if r["tokens_context_avg"] is None else f"{r['tokens_context_avg']:.0f}"
        pct = "—" if r["pct_above_threshold"] is None else f"{r['pct_above_threshold']:.0f}%"
        L.append(f"| {r['strategy_label']} | {r['n_correct_spans']} | {tokens} | {f3(r['sd_avg'])} | "
                 f"{f3(r['sd_median'])} | {pct} |")
    L.append("")

    L += ["## H. Mochila voraz contra programación dinámica\n",
          "| Búsqueda | Preguntas | Conjuntos distintos | Diferencia de valor prom. (PD − voraz) | Máxima | % prom. | "
          "Respuesta cambió | F1 voraz | F1 PD | Selección voraz (ms) | Selección PD (ms) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, g in ctx["greedy_vs_dp"].items():
        L.append(f"| {g['label']} | {g['n']} | {g['different_sets']} | {g['value_gap_avg']:.4f} | {g['value_gap_max']:.4f} | "
                 f"{g['value_gap_pct_avg']:.2f}% | {g['answer_changed']} | {g['f1_greedy']:.3f} | {g['f1_dp']:.3f} | "
                 f"{g['t_select_greedy_ms']:.1f} | {g['t_select_dp_ms']:.1f} |")
    ex = [e for g in ctx["greedy_vs_dp"].values() for e in g["examples"]]
    if ex:
        L.append("\nEjemplos donde eligen conjuntos distintos:\n")
        L += [f"- {e['id']} ({e['method']}): voraz {e['greedy']} (valor {e['greedy_value']}) → \"{e['greedy_answer']}\"; "
              f"PD {e['dp']} (valor {e['dp_value']}) → \"{e['dp_answer']}\"" for e in ex[:6]]
    L.append("\nEl tiempo de selección incluye contar tokens (con caché) y eliminar redundancia; la tabla de la PD tiene "
             "unas N·W ≈ 10 × 490 celdas.\n")

    L += ["## I. Datos para el análisis\n"] + [f"- {b}" for b in ctx["analysis"]]
    if ctx["figures"]:
        L += ["\n## Gráficas\n"] + [f"![{f.stem}](figures/{f.name})" for f in ctx["figures"]]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def analysis_bullets(ctx):
    S = {s["algorithm"]: s for s in ctx["summary"]}
    C = ctx["by_cat"]
    fastest = min(ctx["summary"], key=lambda s: s["time_ms_avg"])
    approx_fastest = min((s for s in ctx["summary"] if s["method"] == "approximate"), key=lambda s: s["time_ms_avg"])
    best = max(ctx["summary"], key=lambda s: (s.get("hit@5", 0), s.get("mrr", 0)))
    sc = ctx["scaling"]
    first, last = sc[0], sc[-1]
    ctx_s = {(s["method"], s["strategy"]): s for s in ctx["context_summary"]}
    best_ctx = max(ctx["context_summary"], key=lambda s: s["f1"])
    pr = ctx["pruning_summary"].get("todas", {})
    gd = ctx["greedy_vs_dp"]["approximate"]
    thr = [s for s in ctx["threshold"] if s["method"] == "approximate" and s["strategy"] == "greedy"]
    best_t = max(thr, key=lambda s: s["f1"])
    t7 = min(thr, key=lambda s: abs(s["threshold"] - config.NO_ANSWER_THRESHOLD))
    t_poke = min(thr, key=lambda s: abs(s["threshold"] - 7))
    typo = lambda a, m: C[a].get("typo", {}).get(m, 0)
    b = [
        f"**¿Qué algoritmo es más rápido?** {LABEL[fastest['algorithm']]} ({fastest['time_ms_avg']:.3f} ms promedio). "
        f"KMP + índice: {S['kmp']['time_ms_avg']:.3f} ms. De las aproximadas, {LABEL[approx_fastest['algorithm']]} "
        f"({approx_fastest['time_ms_avg']:.3f} ms); híbrido {S['hybrid']['time_ms_avg']:.3f} ms.",
        f"**¿Qué método recupera información más útil?** {LABEL[best['algorithm']]}: Hit@5 {best['hit@5']:.3f}, "
        f"MRR {best['mrr']:.3f} (KMP: Hit@5 {S['kmp']['hit@5']:.3f}, MRR {S['kmp']['mrr']:.3f}). "
        f"En preguntas con errores: Hit@5 {typo('kmp', 'hit@5'):.3f} → {typo('hybrid', 'hit@5'):.3f}, "
        f"MRR {typo('kmp', 'mrr'):.3f} → {typo('hybrid', 'mrr'):.3f}. Literales: "
        f"{C['kmp']['literal']['hit@5']:.3f} (exacta) contra {C['hybrid']['literal']['hit@5']:.3f} (híbrida). "
        f"Paráfrasis: {C['kmp']['paraphrase']['hit@5']:.3f} contra {C['hybrid']['paraphrase']['hit@5']:.3f}.",
        f"**Errores de escritura, OSA contra Levenshtein:** Hit@5 typo {typo('osa_trie', 'hit@5'):.3f} contra "
        f"{typo('lev_trie', 'hit@5'):.3f} (el generador de errores intercambia letras).",
        f"**Poda:** OSA sobre el Trie visita en promedio {pr.get('pct_avg', 0):.1f}% de los nodos y es "
        f"{pr.get('speedup_avg', 0):.0f}× más rápido que la fuerza bruta, con el mismo resultado"
        f"{'' if pr.get('all_same') else ' (¡NO en todos los casos!)'}.",
        f"**¿Cómo afecta el tamaño de la colección?** De {first['n_chunks']} a {last['n_chunks']} fragmentos "
        f"(×{last['n_chunks'] / first['n_chunks']:.1f}) el vocabulario crece ×{last['vocab_words'] / first['vocab_words']:.1f} "
        f"({first['vocab_words']:,} → {last['vocab_words']:,}). Tiempo por consulta: KMP "
        f"{first['kmp_ms']:.2f} → {last['kmp_ms']:.2f} ms; OSA + Trie {first['osa_trie_ms']:.2f} → {last['osa_trie_ms']:.2f} ms; "
        f"n-gramas {first['ngram_jaccard_ms']:.2f} → {last['ngram_jaccard_ms']:.2f} ms; arreglo de sufijos "
        f"{first['suffix_array_ms']:.2f} → {last['suffix_array_ms']:.2f} ms.",
        f"**¿Cómo afecta la selección del contexto?** Mejor F1: {best_ctx['method_label']} con {best_ctx['strategy_label']} "
        f"({best_ctx['f1']:.3f}). Aproximada: top-1 {ctx_s[('approximate', 'topk1')]['f1']:.3f}, top-3 "
        f"{ctx_s[('approximate', 'topk3')]['f1']:.3f}, top-5 {ctx_s[('approximate', 'topk5')]['f1']:.3f} "
        f"({ctx_s[('approximate', 'topk5')]['truncated']} truncadas), voraz {ctx_s[('approximate', 'greedy')]['f1']:.3f}, "
        f"PD {ctx_s[('approximate', 'dp')]['f1']:.3f}. Evidencia en el contexto: top-1 "
        f"{ctx_s[('approximate', 'topk1')]['evidence_recall']:.2f} contra voraz {ctx_s[('approximate', 'greedy')]['evidence_recall']:.2f}.",
        f"**Voraz contra PD:** eligen conjuntos distintos en {gd['different_sets']} de {gd['n']} preguntas; diferencia "
        f"de valor promedio {gd['value_gap_pct_avg']:.2f}%; la respuesta cambió en {gd['answer_changed']}.",
        f"**Umbral:** con t = {config.NO_ANSWER_THRESHOLD:g} (el elegido) el F1 global de la aproximada con contexto voraz es "
        f"{t7['f1']:.3f}, contra {t_poke['f1']:.3f} con t = 7 del PokeChat; el mejor del barrido es t = {best_t['threshold']:g} con {best_t['f1']:.3f} "
        f"(F1 con respuesta {f3(best_t['f1_answerable'])}, aciertos sin respuesta {f3(best_t['no_answer_acc'])}).",
        f"**Ventajas y limitaciones:** la aproximada corrige errores de escritura con poco costo extra y no empeora las "
        f"literales; no resuelve sinónimos (paráfrasis sin cambio) ni errores que forman otra palabra real; "
        f"la corrección empeoró el ranking en {ctx['cases']['counts']['exact_better']} pregunta(s) (sección B).",
    ]
    return b


def main():
    ap = argparse.ArgumentParser(description="Etapa 6: exacta contra aproximada, contexto y modelo")
    ap.add_argument("--quick", action="store_true", help="subconjunto de preguntas y 1 repetición")
    args = ap.parse_args()

    index = load_index()
    all_questions = load_questions()
    questions = all_questions[::4] if args.quick else all_questions
    repeats = 1 if args.quick else 3
    exact, approx = ExactSearcher(index), ApproximateSearcher(index)
    approx.ngram_index(2), approx.ngram_index(3)
    ctx = {"quick": args.quick, "n_questions": len(questions), "repeats": repeats, "vocab_size": len(approx.trie)}
    t0 = time.perf_counter()

    print(f"A. Exacta contra aproximada ({len(questions)} preguntas)…")
    ctx["summary"], per_question, ctx["by_cat"] = experiment_methods(index, questions, exact, approx, repeats)
    ctx["check_ana"] = check_against_ana(ctx["by_cat"]) if not args.quick else {"available": False}
    if ctx["check_ana"].get("available") and not ctx["check_ana"]["match"]:
        print(f"  AVISO: la exacta no coincide con results/etapa6_exacta.json: {ctx['check_ana']['differences']}")
    print("B. Casos parecidos y distintos…")
    ctx["cases"] = experiment_cases(index, questions, exact, approx, per_question)
    print("C. Poda…")
    pruning, ctx["pruning_summary"] = experiment_pruning(index, all_questions, approx, repeats)
    ctx["pruning"] = pruning
    print("D. Ablaciones…")
    ctx["ablations"] = experiment_ablations(index, questions, approx, repeats)
    print("E. Tamaño de la colección…")
    fractions = [0.25, 0.5, 1.0] if args.quick else [0.1, 0.25, 0.5, 0.75, 1.0]
    ctx["scaling"] = experiment_scaling(index, all_questions, fractions, repeats)
    print("F. Contexto y modelo…")
    qa_model.load_cache(CACHE_FILE)
    cq = CosmoQuery(index)
    records, ctx["context_summary"] = experiment_context(cq, questions)
    ctx["redundancy_stats"] = redundancy_stats(index)
    ctx["records"] = records
    print("G. Umbral…")
    ctx["threshold"], ctx["threshold_by_strategy"] = experiment_threshold(records)
    print("H. Voraz contra PD…")
    ctx["greedy_vs_dp"] = experiment_greedy_vs_dp(records)
    ctx["analysis"] = analysis_bullets(ctx)

    ctx["figures"] = make_plots(ctx["summary"], ctx["by_cat"], pruning, ctx["scaling"],
                                ctx["context_summary"], ctx["threshold"])
    R = config.RESULTS_DIR
    write_csv(R / "etapa6_aprox_resumen.csv", ctx["summary"])
    write_csv(R / "etapa6_aprox_por_pregunta.csv", per_question)
    write_csv(R / "etapa6_aprox_poda.csv", pruning)
    write_csv(R / "etapa6_aprox_ablaciones.csv", ctx["ablations"])
    write_csv(R / "etapa6_aprox_escalabilidad.csv", ctx["scaling"])
    write_csv(R / "etapa6_aprox_contexto.csv", ctx["context_summary"])
    write_csv(R / "etapa6_aprox_contexto_por_pregunta.csv", clean(records))
    write_csv(R / "etapa6_aprox_umbral.csv", ctx["threshold"])
    write_markdown(R / "etapa6_comparacion.md", ctx)
    ctx["elapsed_s"] = time.perf_counter() - t0
    (R / "etapa6_comparacion.json").write_text(json.dumps(
        clean({k: v for k, v in ctx.items() if k not in ("figures", "records")}
              | {"figures": [f.name for f in ctx["figures"]]}),
        indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nListo en {ctx['elapsed_s']:.0f} s. Reporte: {R / 'etapa6_comparacion.md'}")


if __name__ == "__main__":
    main()