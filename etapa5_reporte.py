#ETAPA 5 - Reporte de respuestas del modelo con contexto seleccionado (Persona 2).

# Corre 24 preguntas del banco de Ana (10 literales, 4 de paráfrasis, 6 con errores de escritura
# y 4 sin respuesta en la colección) por el flujo completo de CosmoQuery, con la búsqueda
# aproximada híbrida como método principal y la exacta (KMP) en paralelo. Para cada una guarda
# los fragmentos elegidos, la respuesta, score_difference, el fragmento de origen, los tiempos y
# un diagnóstico automático. Salidas: results/etapa5_respuestas.md, .csv y .json.

# Uso:  python etapa5_reporte.py [--selection greedy|dp]

import argparse
import csv
import json
from collections import Counter

import config
from approx_search import format_correction
from evaluation import answer_scores, load_questions, relevant_chunks
from preprocessing import highlight
from rag_pipeline import CosmoQuery

PLAN = [("literal", 10), ("paraphrase", 4), ("typo", 6), ("no_answer", 4)]
F1_OK = 0.5             # una respuesta cuenta como correcta si F1 >= 0.5 (estilo SQuAD)
SNIPPET = 350
METHODS = [("approximate", "hybrid"), ("exact", "kmp")]
DIAGNOSES = ["correcta y respaldada", "correcta (evidencia fuera de los fragmentos anotados)",
             "recuperación incompleta", "falla del modelo", "no-respuesta correcta", "respuesta sin respaldo"]


def pick_questions(questions):
    """Preguntas repartidas uniformemente dentro de cada categoría (en el orden del banco), para no
    concentrarse en los primeros documentos. Regla fija: índices round(i·n/k) para i = 0..k-1."""
    chosen = []
    for cat, k in PLAN:
        pool = [q for q in questions if q["category"] == cat]
        chosen += [pool[round(i * len(pool) / k)] for i in range(k)]
    return chosen


def diagnose(q, rag, relevant):
    """Diagnóstico automático de una respuesta (ver la sección de criterios del reporte)."""
    selected = {s.chunk_id for s in rag.selected}
    evidence_in_context = bool(relevant & selected)
    scores = answer_scores(rag.answer, q["answers"], config.NO_ANSWER_TEXT)
    if q["category"] == "no_answer":
        label = "no-respuesta correcta" if rag.is_no_answer else "respuesta sin respaldo"
    elif scores["f1"] >= F1_OK:
        label = "correcta y respaldada" if evidence_in_context else DIAGNOSES[1]
    elif not evidence_in_context:
        label = "recuperación incompleta"
    else:
        label = "falla del modelo"
    # Detalle de los "I don't know": ¿el tramo que eligió el modelo era correcto antes del umbral?
    detail = ""
    raw = rag.extra.get("raw_answer", "")
    if rag.is_no_answer and q["answers"]:
        if raw and answer_scores(raw, q["answers"])["f1"] >= F1_OK:
            detail = f"tramo correcto ({raw}) rechazado por el umbral"
        else:
            detail = f"tramo incorrecto ({raw or 'vacío'})"
    return label, evidence_in_context, scores, detail


def run(cq, questions, selection, redundancy=True):
    index = cq.index
    rows = []
    for q in questions:
        relevant = relevant_chunks(index, q)
        entry = {"id": q["id"], "category": q["category"], "question": q["question"],
                 "original": q.get("original"), "answers": q["answers"], "relevant": sorted(relevant)}
        for method, alg in METHODS:
            rag = cq.ask(q["question"], method, alg, selection, redundancy, use_cache=False)
            label, ev, sc, detail = diagnose(q, rag, relevant)
            entry[method] = {
                "algorithm": alg, "answer": rag.answer, "score_difference": round(rag.score_difference, 3),
                "source_chunk": rag.source_chunk_id, "answer_span": rag.answer_span,
                "em": sc["em"], "f1": round(sc["f1"], 3), "diagnosis": label, "evidence_in_context": ev,
                "raw_answer": rag.extra.get("raw_answer", ""), "model_detail": detail,
                "selected": [{"id": s.chunk_id, "doc": s.doc, "section": s.section, "score": s.score,
                              "coverage": s.coverage, "tokens": rag.extra["weights"][s.chunk_id],
                              "relevant": s.chunk_id in relevant, "text": s.text} for s in rag.selected],
                "discarded": rag.discarded, "terms": rag.search.terms,
                "corrections": [format_correction(c) for c in rag.search.details.get("corrections", [])],
                "retrieved": rag.search.ids(), "n_examined": rag.search.n_examined,
                "tokens_used": rag.tokens_used, "tokens_context": rag.tokens_context,
                "token_budget": rag.token_budget, "truncated": rag.truncated,
                "t_search_ms": rag.t_search_ms, "t_select_ms": rag.t_select_ms,
                "t_model_ms": rag.t_model_ms, "t_total_ms": rag.t_total_ms,
            }
        rows.append(entry)
        a, e = entry["approximate"], entry["exact"]
        print(f"  {q['id']:<6} aprox: {a['answer'][:28]:<28} [{a['diagnosis']}] | exacta: {e['answer'][:28]:<28} [{e['diagnosis']}]")
    return rows


def cell(text):
    return str(text).replace("|", "/").replace("\n", " ")


def write_csv(path, rows):
    fields = ["id", "category", "question", "answers", "relevant"]
    per = ["answer", "raw_answer", "model_detail", "score_difference", "source_chunk", "em", "f1", "diagnosis", "evidence_in_context",
           "selected_ids", "tokens_used", "token_budget", "truncated", "t_search_ms", "t_select_ms",
           "t_model_ms", "t_total_ms"]
    header = fields + [f"{m}_{p}" for m, _ in METHODS for p in per]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            line = [r["id"], r["category"], r["question"], json.dumps(r["answers"]), json.dumps(r["relevant"])]
            for m, _ in METHODS:
                d = dict(r[m], selected_ids=json.dumps([s["id"] for s in r[m]["selected"]]))
                line += [round(d[p], 2) if isinstance(d[p], float) else d[p] for p in per]
            w.writerow(line)


def write_markdown(path, rows, selection):
    L = ["# Etapa 5 - Respuestas del modelo con el contexto seleccionado\n",
         f"Modelo: `{config.QA_MODEL}` (extractivo, sin entrenamiento adicional), con la lógica de `ask_question` del "
         f"cuaderno PokeChat: si `score_difference` < {config.NO_ANSWER_THRESHOLD:g}, la respuesta es "
         f"\"{config.NO_ANSWER_TEXT}\". Flujo: pregunta → búsqueda → recuperación de los {config.CONTEXT_CANDIDATES} "
         f"mejores fragmentos → selección del contexto (`{selection}`, con eliminación de redundancia) → modelo → respuesta.\n",
         f"Método principal: búsqueda aproximada híbrida. En paralelo: búsqueda exacta (KMP con índice). "
         f"{len(rows)} preguntas del banco de Ana: " + ", ".join(f"{k} {c}" for c, k in PLAN) +
         ", repartidas uniformemente dentro de cada categoría. Tiempos medidos sin caché del modelo, en CPU.\n",
         "## Criterios del diagnóstico automático\n",
         f"- **Evidencia en el contexto**: algún fragmento relevante de Ana (`relevant_chunks`) quedó entre los seleccionados.",
         f"- **Correcta**: F1 ≥ {F1_OK} contra las respuestas aceptadas del banco (EM/F1 de `answer_scores`).",
         "- **correcta y respaldada**: correcta y con evidencia en el contexto.",
         "- **correcta (evidencia fuera de los fragmentos anotados)**: correcta, pero salió de un fragmento que no está "
         "entre los relevantes de Ana (otro documento dice lo mismo).",
         "- **recuperación incompleta**: incorrecta y la evidencia no llegó al contexto.",
         "- **falla del modelo**: incorrecta aunque la evidencia sí estaba en el contexto.",
         "- **no-respuesta correcta / respuesta sin respaldo**: pregunta sin respuesta en la colección; el modelo "
         "dice o no dice \"I don't know\".\n",
         "## Resumen por diagnóstico\n",
         "| Diagnóstico | Aproximada (híbrida) | Exacta (KMP) |", "|---|---:|---:|"]
    counts = {m: Counter(r[m]["diagnosis"] for r in rows) for m, _ in METHODS}
    for d in DIAGNOSES:
        L.append(f"| {d} | {counts['approximate'][d]} | {counts['exact'][d]} |")
    L.append("")
    summary = []
    for m, label in (("approximate", "Aproximada (híbrida)"), ("exact", "Exacta (KMP)")):
        rs = [r[m] for r in rows]
        answered = [r for r in rows if r["category"] != "no_answer"]
        summary.append([label,
                        f"{sum(x['em'] for x in rs) / len(rs):.3f}", f"{sum(x['f1'] for x in rs) / len(rs):.3f}",
                        f"{sum(r[m]['evidence_in_context'] for r in answered)}/{len(answered)}",
                        f"{sum(x['answer'] == config.NO_ANSWER_TEXT for x in rs)}/{len(rs)}",
                        f"{sum(x['truncated'] for x in rs)}",
                        f"{sum(x['tokens_used'] for x in rs) / len(rs):.0f}",
                        f"{sum(x['t_search_ms'] for x in rs) / len(rs):.1f}",
                        f"{sum(x['t_select_ms'] for x in rs) / len(rs):.1f}",
                        f"{sum(x['t_model_ms'] for x in rs) / len(rs):.0f}",
                        f"{sum(x['t_total_ms'] for x in rs) / len(rs):.0f}"])
    L += ["| Método | EM | F1 | Evidencia en contexto | \"I don't know\" | Truncadas | Tokens de entrada prom. | "
          "Búsqueda ms | Selección ms | Modelo ms | Total ms |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    L += ["| " + " | ".join(r) + " |" for r in summary]
    below = {m: sum("rechazado por el umbral" in r[m]["model_detail"] for r in rows) for m, _ in METHODS}
    diffs = sorted(r["approximate"]["score_difference"] for r in rows
                   if "rechazado" in r["approximate"]["model_detail"])
    L.append(f"\n**\"I don't know\" con el tramo correcto:** en {below['approximate']} preguntas (aproximada) y "
             f"{below['exact']} (exacta) el modelo eligió el tramo correcto, pero su score_difference quedó debajo "
             f"del umbral {config.NO_ANSWER_THRESHOLD:g} del PokeChat"
             + (f" (valores: {', '.join(f'{d:.2f}' for d in diffs)})" if diffs else "") + ". "
             "La columna `raw_answer` del `.csv` guarda ese tramo. El efecto del tamaño del contexto sobre "
             "score_difference se mide en la Etapa 6.")
    L.append("\nEM y F1 son promedios sobre las 24 preguntas (las sin respuesta valen 1 si el modelo dice "
             "\"I don't know\"). La evidencia en contexto se cuenta solo en las 20 preguntas con respuesta.\n")

    L += ["## Tabla de respuestas\n",
          "| Id | Categoría | Pregunta | Esperada | Aproximada: respuesta (score_diff) | Diagnóstico | Exacta: respuesta (score_diff) | Diagnóstico |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        a, e = r["approximate"], r["exact"]
        L.append(f"| {r['id']} | {r['category']} | {cell(r['question'])} | {cell(', '.join(r['answers']) or '—')} | "
                 f"{cell(a['answer'])} ({a['score_difference']:.2f}) | {a['diagnosis']} | "
                 f"{cell(e['answer'])} ({e['score_difference']:.2f}) | {e['diagnosis']} |")

    L.append("\n## Detalle por pregunta (búsqueda aproximada híbrida)\n")
    for r in rows:
        a, e = r["approximate"], r["exact"]
        L += [f"### {r['id']} [{r['category']}] {r['question']}\n"]
        if r.get("original"):
            L.append(f"- Pregunta original (sin errores): {r['original']}")
        L += [f"- Respuestas aceptadas: {', '.join(r['answers']) or '(ninguna: no está en la colección)'}; "
              f"fragmentos relevantes: {r['relevant'] or '—'}",
              f"- Correcciones: {'; '.join(a['corrections']) or 'ninguna'}",
              f"- **Respuesta: {a['answer']}** · score_difference = {a['score_difference']:.2f} · "
              f"fragmento de origen: {a['source_chunk'] if a['source_chunk'] is not None else '—'} · "
              f"EM {a['em']:.0f}, F1 {a['f1']:.2f} · **{a['diagnosis']}**"
              + (f" · {a['model_detail']}" if a["model_detail"] else ""),
              f"- Contexto: {len(a['selected'])} fragmentos, {a['tokens_context']} tokens de {a['token_budget']} "
              f"disponibles; entrada al modelo {a['tokens_used']}/{config.MODEL_MAX_TOKENS}"
              f"{' (TRUNCADA)' if a['truncated'] else ''}",
              f"- Tiempos: búsqueda {a['t_search_ms']:.1f} ms · selección {a['t_select_ms']:.1f} ms · "
              f"modelo {a['t_model_ms']:.0f} ms · total {a['t_total_ms']:.0f} ms",
              f"- Exacta (KMP): {e['answer']} ({e['score_difference']:.2f}) · {e['diagnosis']} · "
              f"fragmentos {[s['id'] for s in e['selected']]}\n",
              "| # | Fragmento | Documento > sección | Tokens | Relevante | Texto (inicio, términos en negritas) |",
              "|---|---|---|---:|---|---|"]
        for i, s in enumerate(a["selected"], 1):
            src = " ← respuesta" if s["id"] == a["source_chunk"] else ""
            snippet = highlight(s["text"], a["terms"])[:SNIPPET]
            L.append(f"| {i} | {s['id']}{src} | {cell(s['doc'] + ' > ' + s['section'])[:70]} | {s['tokens']} | "
                     f"{'sí' if s['relevant'] else 'no'} | {cell(snippet)}… |")
        if a["discarded"]:
            L.append(f"\nDescartados: " + "; ".join(f"{cid} ({why})" for cid, why in a["discarded"]))
        L.append("")

    L.append("## Casos comentados (datos)\n")
    wanted = [("correcta y respaldada", "approximate"), ("recuperación incompleta", None),
              ("falla del modelo", None), ("no-respuesta correcta", "approximate"),
              ("respuesta sin respaldo", None)]
    shown = 0
    for label, only in wanted:
        hit = next(((r, m) for r in rows for m, _ in METHODS
                    if (only is None or m == only) and r[m]["diagnosis"] == label), None)
        if hit is None or shown == 4:
            continue
        r, m = hit
        d = r[m]
        where = [s["id"] for s in d["selected"] if s["relevant"]]
        L += [f"**{label}** · {r['id']} ({'aproximada' if m == 'approximate' else 'exacta'})",
              f"- Pregunta: {r['question']} · esperada: {', '.join(r['answers']) or '—'} · respuesta: {d['answer']} "
              f"(score_difference {d['score_difference']:.2f})",
              f"- Relevantes: {r['relevant'] or '—'} · recuperados (top-10): {d['retrieved']} · "
              f"en el contexto: {[s['id'] for s in d['selected']]} · relevantes en el contexto: {where or 'ninguno'}",
              f"- Fragmento de origen de la respuesta: {d['source_chunk'] if d['source_chunk'] is not None else '—'}\n"]
        shown += 1
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Etapa 5: respuestas del modelo con contexto seleccionado")
    ap.add_argument("--selection", default="greedy", choices=["greedy", "dp", "topk"])
    args = ap.parse_args()

    print("Cargando índice y modelo…")
    cq = CosmoQuery()
    cq.ask("When was Pluto discovered?", use_cache=False)          # calentamiento (no se reporta)
    questions = pick_questions(load_questions())
    print(f"Respondiendo {len(questions)} preguntas…")
    rows = run(cq, questions, args.selection)

    config.RESULTS_DIR.mkdir(exist_ok=True)
    base = config.RESULTS_DIR / "etapa5_respuestas"
    write_markdown(base.with_suffix(".md"), rows, args.selection)
    write_csv(base.with_suffix(".csv"), rows)
    base.with_suffix(".json").write_text(json.dumps(
        {"selection": args.selection, "model": config.QA_MODEL, "threshold": config.NO_ANSWER_THRESHOLD,
         "f1_ok": F1_OK, "questions": rows}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Reporte: {base.with_suffix('.md')}")


if __name__ == "__main__":
    main()
