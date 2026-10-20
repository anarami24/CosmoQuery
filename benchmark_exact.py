import argparse
import csv
import json
import statistics
import time

import config
from evaluation import evaluate_search, load_questions, validate_questions
from exact_search import ALGORITHMS, ExactSearcher
from index_builder import load_index
from string_matching import ALGORITHM_LABELS, MATCHERS


COLORS = {"naive": "#2a78d6", "kmp": "#eb6834", "z": "#1baf7a",
          "rabin_karp": "#eda100", "suffix_array": "#e87ba4"}
MARKERS = {"naive": "o", "kmp": "s", "z": "^", "rabin_karp": "D", "suffix_array": "v"}
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e6e5e0"


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def fmt(x, d=3):
    return f"{x:.{d}f}" if isinstance(x, float) else str(x)

def experiment_algorithms(index, questions, repeats):
    searcher = ExactSearcher(index)
    summary_rows, per_question, by_category = [], [], {}
    for alg in ALGORITHMS:
        for use_index in ([True] if alg == "suffix_array" else [True, False]):
            reps = repeats if use_index else 1
            rows, summ, cats = evaluate_search(
                lambda q: searcher.search(q, alg, config.TOP_K, use_index), index, questions, repeats=reps)
            label = f"{alg}{'' if use_index else ' (sin índice)'}"
            summary_rows.append({"algorithm": alg, "use_index": use_index, **summ})
            for r in rows:
                per_question.append({"algorithm": alg, "use_index": use_index, **r})
            if alg == "kmp" and use_index:
                by_category = cats
            print(f"  {label:<28} prom {summ['time_ms_avg']:9.3f} ms | examinados {summ['examined_avg']:8.1f}"
                  f" | Hit@5 {summ.get('hit@5', 0):.3f} | MRR {summ.get('mrr', 0):.3f}")
    return summary_rows, per_question, by_category


def experiment_stemming(index, questions, repeats):
    searcher = ExactSearcher(index)
    out = {}
    for field in ("words", "stems"):
        _, summ, cats = evaluate_search(lambda q: searcher.search(q, "kmp", config.TOP_K, True, field),
                                        index, questions, repeats=repeats)
        out[field] = {"overall": summ, "by_category": cats}
    return out


def experiment_scaling(index, questions, fractions):
    sample_qs = [q for q in questions if q["category"] == "literal"][:10]
    total = len(index.chunks)
    rows = []
    for frac in fractions:
        n = max(1, int(total * frac))
        t0 = time.perf_counter()
        sub = index.subset(n)
        build_s = time.perf_counter() - t0
        chars = sum(len(t) for t in sub.stem_text)
        searcher = ExactSearcher(sub)
        row = {"fraction": frac, "n_chunks": n, "chars": chars, "build_inv_sa_s": build_s}
        configs = [(a, False) for a in MATCHERS] + [("kmp", True), ("suffix_array", True)]
        for alg, use_index in configs:
            times = [searcher.search(q["question"], alg, config.TOP_K, use_index).time_ms for q in sample_qs]
            row[f"{alg}{'_index' if use_index else '_scan'}_ms"] = statistics.mean(times)
        rows.append(row)
        print(f"  {frac:>5.0%}  {n:>6,} fragmentos  " +
              "  ".join(f"{k.replace('_ms', '')}={v:.1f}" for k, v in row.items() if k.endswith("_ms")))
    return rows


def experiment_worst_case(sizes, m=40):
    pattern = "a" * (m - 1) + "b"
    rows = []
    for n in sizes:
        text = "a" * n
        row = {"n": n, "m": m}
        for alg, Matcher in MATCHERS.items():
            matcher = Matcher(pattern)
            t0 = time.perf_counter()
            matcher.search(text)
            row[f"{alg}_ms"] = (time.perf_counter() - t0) * 1000
        rows.append(row)
        print(f"  n={n:>7,}  " + "  ".join(f"{a}={row[a + '_ms']:.1f}ms" for a in MATCHERS))
    return rows


#graficas
def _style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED)


def make_plots(summary_rows, scaling_rows, worst_rows, by_category, stemming):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib no está instalado: se omiten las gráficas)")
        return []
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    files = []

    # 1. Tiempo promedio por algoritmo
    fig, ax = plt.subplots(figsize=(8, 4.2))
    labels, values, colors, hatches = [], [], [], []
    for r in summary_rows:
        labels.append(ALGORITHM_LABELS[r["algorithm"]].split(" (")[0] + ("\n+ índice" if r["use_index"] else "\nsin índice"))
        values.append(r["time_ms_avg"])
        colors.append(COLORS[r["algorithm"]])
        hatches.append("" if r["use_index"] else "///")
    bars = ax.bar(range(len(values)), values, color=colors, edgecolor="white", linewidth=2)
    for b, h in zip(bars, hatches):
        b.set_hatch(h)
    for i, v in enumerate(values):
        ax.text(i, v * 1.15, f"{v:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_yscale("log")
    ax.set_xticks(range(len(values)), labels, fontsize=7.5)
    _style(ax, "Tiempo promedio por consulta (escala log)", "", "ms por consulta")
    fig.tight_layout()
    path = config.FIGURES_DIR / "exacta_tiempo_algoritmos.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    files.append(path)

    # 2. Escalabilidad
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = [r["n_chunks"] for r in scaling_rows]
    series = [(f"{a}_scan_ms", a, f"{ALGORITHM_LABELS[a]} (sin índice)", "-") for a in MATCHERS]
    series += [("kmp_index_ms", "kmp", "KMP + índice invertido", "--"),
               ("suffix_array_index_ms", "suffix_array", "Arreglo de sufijos", "--")]
    for key, alg, label, ls in series:
        y = [r[key] for r in scaling_rows]
        ax.plot(x, y, ls, color=COLORS[alg], marker=MARKERS[alg], markersize=6, linewidth=2, label=label)
    ax.set_yscale("log")
    _style(ax, "Tiempo de búsqueda vs. tamaño de la colección", "fragmentos en la colección", "ms por consulta (log)")
    ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    path = config.FIGURES_DIR / "exacta_escalabilidad.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    files.append(path)

    # 3. Peor caso
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = [r["n"] for r in worst_rows]
    for alg in MATCHERS:
        ax.plot(x, [r[f"{alg}_ms"] for r in worst_rows], color=COLORS[alg], marker=MARKERS[alg],
                markersize=6, linewidth=2, label=ALGORITHM_LABELS[alg])
    _style(ax, f"Peor caso: texto 'aaa…a', patrón 'a…ab' (m = {worst_rows[0]['m']})", "longitud del texto n", "ms")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    path = config.FIGURES_DIR / "exacta_peor_caso.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    files.append(path)

    # 4. Calidad por categoría: con y sin stemming
    cats = [c for c in ("literal", "paraphrase", "typo") if c in by_category]
    if cats:
        fig, ax = plt.subplots(figsize=(8, 4.2))
        width = 0.38
        for j, (field, color, name) in enumerate([("words", "#2a78d6", "Sin stemming"),
                                                  ("stems", "#eb6834", "Con stemming de Porter")]):
            vals = [stemming[field]["by_category"].get(c, {}).get("hit@5", 0) for c in cats]
            pos = [i + (j - 0.5) * width for i in range(len(cats))]
            ax.bar(pos, vals, width - 0.02, color=color, edgecolor="white", linewidth=2, label=name)
            for p, v in zip(pos, vals):
                ax.text(p, v + 0.02, f"{v:.2f}", ha="center", fontsize=8, color=INK)
        names = {"literal": "Literales", "paraphrase": "Paráfrasis", "typo": "Con errores de escritura"}
        ax.set_xticks(range(len(cats)), [names[c] for c in cats])
        ax.set_ylim(0, 1.1)
        _style(ax, "Búsqueda exacta: Hit@5 por tipo de pregunta", "", "Hit@5")
        ax.legend(fontsize=8, frameon=False)
        fig.tight_layout()
        path = config.FIGURES_DIR / "exacta_calidad_categorias.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        files.append(path)
    return files


#reporte
def write_markdown(path, n_questions, problems, summary_rows, by_category, stemming, scaling_rows, worst_rows, figures):
    L = ["# Etapa 6 - Análisis de la búsqueda exacta\n",
         f"Banco de pruebas: **{n_questions} preguntas** (escritas a mano + variantes con errores de escritura).\n"]
    if problems:
        L += [f"> **Atención:** {len(problems)} preguntas no tienen fragmento relevante en la colección "
              "(revisar evidencia/documentos):", ""]
        L += [f"> - {p['id']}: {p['question']} -> {p['reason']}" for p in problems]
        L.append("")
    L += ["## A. Comparación de algoritmos\n",
          "| Algoritmo | Índice invertido | Tiempo prom. (ms) | Mediana (ms) | Fragmentos examinados | Recuperados (score>0) | Hit@1 | Hit@5 | MRR | P@5 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary_rows:
        L.append(f"| {ALGORITHM_LABELS[r['algorithm']]} | {'sí' if r['use_index'] else 'no'} | {r['time_ms_avg']:.3f} | "
                 f"{r['time_ms_median']:.3f} | {r['examined_avg']:.1f} | {r['matched_avg']:.1f} | "
                 f"{r.get('hit@1', 0):.3f} | {r.get('hit@5', 0):.3f} | {r.get('mrr', 0):.3f} | {r.get('p@5', 0):.3f} |")
    L += ["\nTodos los algoritmos devuelven exactamente el mismo ranking (son búsquedas exactas); "
          "solo cambia el tiempo. La calidad depende del criterio de puntuación, no del algoritmo.\n",
          "## B. Calidad por tipo de pregunta (KMP + índice)\n",
          "| Categoría | Preguntas | Hit@1 | Hit@3 | Hit@5 | MRR | Recuperados prom. |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cat, s in by_category.items():
        L.append(f"| {cat} | {s['n']} | {s.get('hit@1', float('nan')):.3f} | {s.get('hit@3', float('nan')):.3f} | "
                 f"{s.get('hit@5', float('nan')):.3f} | {s.get('mrr', float('nan')):.3f} | {s['matched_avg']:.1f} |")
    L += ["\n## C. Efecto del stemming (KMP + índice)\n",
          "| Variante | Hit@1 | Hit@5 | MRR | Recuperados prom. |", "|---|---:|---:|---:|---:|"]
    for field, name in (("words", "Sin stemming"), ("stems", "Con stemming de Porter")):
        s = stemming[field]["overall"]
        L.append(f"| {name} | {s.get('hit@1', 0):.3f} | {s.get('hit@5', 0):.3f} | {s.get('mrr', 0):.3f} | {s['matched_avg']:.1f} |")
    L += ["\n## D. Escalabilidad (10 preguntas literales, ms promedio por consulta)\n"]
    keys = [k for k in scaling_rows[0] if k.endswith("_ms")]
    L.append("| Fragmentos | Caracteres | Construcción índice+SA (s) | " + " | ".join(k.replace("_ms", "") for k in keys) + " |")
    L.append("|---:|---:|---:|" + "---:|" * len(keys))
    for r in scaling_rows:
        L.append(f"| {r['n_chunks']:,} | {r['chars']:,} | {r['build_inv_sa_s']:.2f} | " + " | ".join(f"{r[k]:.2f}" for k in keys) + " |")
    L += ["\n## E. Peor caso teórico (ms)\n", "| n | " + " | ".join(ALGORITHM_LABELS[a] for a in MATCHERS) + " |",
          "|---:|" + "---:|" * len(MATCHERS)]
    for r in worst_rows:
        L.append(f"| {r['n']:,} | " + " | ".join(f"{r[a + '_ms']:.1f}" for a in MATCHERS) + " |")
    if figures:
        L += ["\n## Gráficas\n"] + [f"![{f.stem}](figures/{f.name})" for f in figures]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Etapa 6: benchmarks de la búsqueda exacta")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    index = load_index()
    questions = load_questions()
    if args.quick:
        questions = questions[::3]
    repeats = 1 if args.quick else 3
    config.RESULTS_DIR.mkdir(exist_ok=True)

    problems = validate_questions(index, questions)
    if problems:
        print(f"AVISO: {len(problems)} preguntas sin fragmento relevante en la colección (ver reporte).")

    print(f"\nA/B. Algoritmos sobre {len(questions)} preguntas...")
    summary_rows, per_question, by_category = experiment_algorithms(index, questions, repeats)
    print("\nC. Stemming vs. sin stemming...")
    stemming = experiment_stemming(index, questions, repeats)
    print("\nD. Escalabilidad...")
    fractions = [0.25, 0.5, 1.0] if args.quick else [0.1, 0.25, 0.5, 0.75, 1.0]
    scaling_rows = experiment_scaling(index, questions, fractions)
    print("\nE. Peor caso teórico...")
    sizes = [2000, 4000, 8000] if args.quick else [2000, 4000, 8000, 16000, 32000]
    worst_rows = experiment_worst_case(sizes)

    figures = make_plots(summary_rows, scaling_rows, worst_rows, by_category, stemming)
    write_csv(config.RESULTS_DIR / "etapa6_exacta_resumen.csv", summary_rows)
    write_csv(config.RESULTS_DIR / "etapa6_exacta_por_pregunta.csv", per_question)
    write_csv(config.RESULTS_DIR / "etapa6_exacta_escalabilidad.csv", scaling_rows)
    write_csv(config.RESULTS_DIR / "etapa6_exacta_peor_caso.csv", worst_rows)
    (config.RESULTS_DIR / "etapa6_exacta.json").write_text(json.dumps(
        {"summary": summary_rows, "by_category": by_category, "stemming": stemming,
         "scaling": scaling_rows, "worst_case": worst_rows, "problems": problems},
        indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(config.RESULTS_DIR / "etapa6_exacta.md", len(questions), problems, summary_rows,
                   by_category, stemming, scaling_rows, worst_rows, figures)
    print(f"\nListo. Reporte: {config.RESULTS_DIR / 'etapa6_exacta.md'}")


if __name__ == "__main__":
    main()
