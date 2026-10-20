"""
Evalúa las RESPUESTAS del sistema completo (búsqueda + contexto + modelo) sobre
todas las preguntas de data/questions.json y dice, para cada falla, si el
problema fue de la búsqueda o del modelo.

Uso:
    python evaluar_respuestas.py                    # búsqueda exacta (KMP)
    python evaluar_respuestas.py --method approximate
    python evaluar_respuestas.py --sin-typos        # solo las 56 preguntas escritas a mano

Diagnóstico por pregunta:
  OK           el modelo respondió bien (o dijo "I don't know" en una sin respuesta)
  BUSQUEDA     ningún fragmento con la respuesta llegó al contexto del modelo
  MODELO       el fragmento correcto SÍ estaba en el contexto, pero el modelo falló
               (dijo "I don't know" por el umbral, o subrayó otra cosa)
  INVENTÓ      pregunta sin respuesta, pero el modelo contestó algo
"""
import argparse
import csv
from collections import Counter, defaultdict

import config
from evaluation import answer_scores, load_questions, relevant_chunks
from index_builder import load_index
from rag_pipeline import CosmoQuery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="exact", choices=["exact", "approximate"])
    ap.add_argument("--alg", default=None)
    ap.add_argument("--sin-typos", action="store_true")
    args = ap.parse_args()

    index = load_index()
    cq = CosmoQuery(index)
    questions = load_questions(include_typos=not args.sin_typos)
    no_answer = getattr(config, "NO_ANSWER_TEXT", "I don't know")
    threshold = getattr(config, "NO_ANSWER_THRESHOLD", "?")

    rows = []
    for q in questions:
        r = cq.ask(q["question"], args.method, args.alg)
        sc = answer_scores(r.answer, q["answers"], no_answer)
        relevant = relevant_chunks(index, q)
        in_context = any(s.chunk_id in relevant for s in r.selected)
        if q["category"] == "no_answer":
            verdict = "OK" if sc["em"] == 1 else "INVENTÓ"
        elif sc["f1"] >= 0.5:
            verdict = "OK"
        elif not in_context:
            verdict = "BUSQUEDA"
        else:
            verdict = "MODELO"
        rows.append({"id": q["id"], "category": q["category"], "verdict": verdict,
                     "question": q["question"], "answer": r.answer, "expected": " | ".join(q["answers"]),
                     "score_difference": round(r.score_difference, 2), "truncated": r.truncated,
                     "n_selected": len(r.selected), "relevant_in_context": in_context,
                     "em": sc["em"], "f1": round(sc["f1"], 3)})

    print(f"\nMétodo: {args.method} | umbral de 'I don't know': {threshold}\n")
    print(f"{'id':<7}{'tipo':<11}{'resultado':<10}{'score':>7}  pregunta -> respuesta (esperada)")
    for x in rows:
        if x["verdict"] != "OK":
            print(f"{x['id']:<7}{x['category']:<11}{x['verdict']:<10}{x['score_difference']:>7}  "
                  f"{x['question'][:55]} -> {x['answer'][:30]!r} ({x['expected'][:25]})"
                  f"{'  [TRUNCADO]' if x['truncated'] else ''}")

    print("\nResumen por tipo de pregunta:")
    by_cat = defaultdict(Counter)
    for x in rows:
        by_cat[x["category"]][x["verdict"]] += 1
    for cat, cnt in by_cat.items():
        total = sum(cnt.values())
        print(f"  {cat:<11} {cnt['OK']:>3}/{total:<3} correctas  |  " +
              ", ".join(f"{k}: {v}" for k, v in cnt.items() if k != "OK"))
    ok = sum(x["verdict"] == "OK" for x in rows)
    print(f"\nTotal: {ok}/{len(rows)} correctas ({100 * ok / len(rows):.0f}%)")

    config.RESULTS_DIR.mkdir(exist_ok=True)
    out = config.RESULTS_DIR / f"respuestas_{args.method}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Detalle guardado en {out}")


if __name__ == "__main__":
    main()