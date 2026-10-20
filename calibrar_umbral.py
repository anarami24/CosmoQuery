"""
Calibra el umbral de "I don't know" (config.NO_ANSWER_THRESHOLD) con el banco de preguntas.

El umbral 7 del PokeChat se eligió con un contexto de 4 líneas sobre Pikachu.
Con 3-5 fragmentos de NASA (~450 tokens) el modelo reparte su confianza y el
score_difference baja, así que respuestas correctas quedan debajo de 7.

Este script hace UNA corrida del sistema por pregunta, guarda el score_difference
y la respuesta "cruda" (antes del umbral), y después simula cada umbral posible:
  - pregunta con respuesta: acierto si score >= umbral y la respuesta cruda es correcta
  - pregunta sin respuesta: acierto si score <  umbral (dice "I don't know")

Uso:
    python calibrar_umbral.py                 # búsqueda exacta
    python calibrar_umbral.py --method approximate
"""
import argparse

import config
from evaluation import answer_scores, load_questions
from index_builder import load_index
from rag_pipeline import CosmoQuery


def accuracy(rows, t):
    hits = {"con_respuesta": [0, 0], "sin_respuesta": [0, 0]}
    for x in rows:
        if x["no_answer"]:
            ok = x["score"] < t
            hits["sin_respuesta"][0] += ok
            hits["sin_respuesta"][1] += 1
        else:
            ok = x["score"] >= t and x["raw_ok"]
            hits["con_respuesta"][0] += ok
            hits["con_respuesta"][1] += 1
    total = sum(h[0] for h in hits.values()) / max(1, sum(h[1] for h in hits.values()))
    return total, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="exact", choices=["exact", "approximate"])
    ap.add_argument("--con-typos", action="store_true")
    args = ap.parse_args()

    index = load_index()
    cq = CosmoQuery(index)
    rows = []
    for q in load_questions(include_typos=args.con_typos):
        r = cq.ask(q["question"], args.method)
        raw = r.extra.get("raw_answer", "") or ""
        raw_ok = bool(q["answers"]) and bool(raw) and answer_scores(raw, q["answers"])["f1"] >= 0.5
        rows.append({"id": q["id"], "question": q["question"], "score": r.score_difference,
                     "raw": raw, "raw_ok": raw_ok, "no_answer": q["category"] == "no_answer"})

    print(f"\nscore_difference por pregunta ({args.method}):")
    for x in sorted(rows, key=lambda x: x["score"]):
        tag = "SIN RESPUESTA" if x["no_answer"] else ("correcta" if x["raw_ok"] else "incorrecta")
        print(f"  {x['score']:7.2f}  {tag:<14} {x['id']:<5} {x['question'][:50]:<50} -> {x['raw'][:30]!r}")

    print(f"\n{'umbral':>7} {'aciertos':>9}  con respuesta   sin respuesta")
    best_t, best_acc = None, -1
    t = 0.0
    while t <= 12.0001:
        acc, h = accuracy(rows, t)
        c, s = h["con_respuesta"], h["sin_respuesta"]
        mark = "  <- actual" if abs(t - config.NO_ANSWER_THRESHOLD) < 1e-9 else ""
        print(f"{t:7.1f} {acc:8.0%}   {c[0]:>3}/{c[1]:<3}         {s[0]:>3}/{s[1]:<3}{mark}")
        if acc > best_acc:
            best_t, best_acc = t, acc
        t += 0.5
    print(f"\nMejor umbral: {best_t:.1f} ({best_acc:.0%} de aciertos). "
          f"Actual: {config.NO_ANSWER_THRESHOLD} ({accuracy(rows, config.NO_ANSWER_THRESHOLD)[0]:.0%}).")
    print("Cámbialo en config.py -> NO_ANSWER_THRESHOLD")


if __name__ == "__main__":
    main()