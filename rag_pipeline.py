#ETAPA 5 - flujo completo: pregunta -> búsqueda -> fragmentos -> contexto -> modelo

import argparse
import textwrap
import time
from dataclasses import dataclass, field

import config
import qa_model
from approx_search import ApproximateSearcher, format_correction
from context_selection import STRATEGIES, ContextSelector
from exact_search import ExactSearcher
from index_builder import load_index
from search_types import SearchResult

METHODS = ["approximate", "exact"]
DEFAULT_ALGORITHM = {"approximate": "hybrid", "exact": "kmp"}


@dataclass
class RagAnswer:
    question: str
    method: str
    algorithm: str
    search: SearchResult
    selected: list
    discarded: list
    context: str
    tokens_used: int
    token_budget: int
    tokens_question: int
    tokens_context: int
    answer: str
    score_difference: float
    source_chunk_id: int = None
    answer_span: tuple = None
    truncated: bool = False
    selection: str = "greedy"
    redundancy: bool = True
    t_search_ms: float = 0.0
    t_select_ms: float = 0.0
    t_model_ms: float = 0.0
    t_total_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def is_no_answer(self):
        return self.answer == config.NO_ANSWER_TEXT


class CosmoQuery:

    def __init__(self, index=None, preload_model=True):
        self.index = index if index is not None else load_index()
        self.exact = ExactSearcher(self.index)
        self.approx = ApproximateSearcher(self.index)
        self.selector = ContextSelector(self.index)
        if preload_model:
            qa_model.load_model()

    def search(self, question, method="approximate", algorithm=None, top_k=None):
        algorithm = algorithm or DEFAULT_ALGORITHM[method]
        top_k = config.CONTEXT_CANDIDATES if top_k is None else top_k
        if method == "exact":
            return self.exact.search(question, algorithm, top_k)
        return self.approx.search(question, algorithm, top_k)

    @staticmethod
    def _answer_per_chunk(question, chunks, use_cache=True):
        """Una llamada al modelo por fragmento (k llamadas de O(L²) con L pequeño)
        y se elige la de mayor score_difference. Devuelve (out, chunk_id, span)."""
        best, best_cid = None, None
        total_ms, any_trunc, max_tokens, all_cached = 0.0, False, 0, True
        for c in chunks:
            o = qa_model.answer(question, c.text, use_cache)
            total_ms += o["time_ms"]
            any_trunc = any_trunc or o["truncated"]
            max_tokens = max(max_tokens, o["tokens_used"])
            all_cached = all_cached and o.get("cached", False)
            if best is None or o["score_difference"] > best["score_difference"]:
                best, best_cid = o, c.chunk_id
        out = dict(best, time_ms=total_ms, truncated=any_trunc, tokens_used=max_tokens, cached=all_cached)
        if best["start_char"] is None:      # el mejor también fue "I don't know"
            return out, None, None
        return out, best_cid, (best["start_char"], best["end_char"])

    def ask(self, question, method="approximate", algorithm=None, selection="greedy",
            redundancy=True, k=None, use_cache=True, redundancy_threshold=None):
        if method not in METHODS:
            raise ValueError(f"Método desconocido: {method}. Opciones: {METHODS}")
        algorithm = algorithm or DEFAULT_ALGORITHM[method]
        t0 = time.perf_counter()

        res = self.search(question, method, algorithm)
        t1 = time.perf_counter()
        sel = self.selector.select(question, res.results, selection, redundancy, k,
                                   redundancy_threshold=redundancy_threshold)
        t2 = time.perf_counter()

        if sel.context and getattr(config, "QA_PER_CHUNK", True):
            # Cada fragmento seleccionado se pasa POR SEPARADO al modelo y se queda la
            # respuesta con mayor score_difference. Si se pegan varios fragmentos en un
            # solo contexto, el modelo reparte su confianza entre fragmentos parecidos
            # y suele preferir "no hay respuesta" (score 0) aunque la respuesta esté ahí.
            out, source, span = self._answer_per_chunk(question, sel.selected, use_cache)
        elif sel.context:
            out = qa_model.answer(question, sel.context, use_cache)
            source = sel.chunk_at(out["start_char"])
            span = None
            if source is not None:
                offset = next(s for cid, s, _ in sel.spans if cid == source)
                span = (out["start_char"] - offset, out["end_char"] - offset)
        else:
            out = {"answer": config.NO_ANSWER_TEXT, "raw_answer": "", "score_difference": float("-inf"),
                   "start_char": None, "end_char": None, "truncated": False, "time_ms": 0.0,
                   "tokens_used": 0, "cached": False}
            source, span = None, None
        t3 = time.perf_counter()

        return RagAnswer(
            question=question, method=method, algorithm=algorithm, search=res,
            selected=sel.selected, discarded=sel.discarded, context=sel.context,
            tokens_used=out["tokens_used"], token_budget=sel.token_budget,
            tokens_question=sel.tokens_question, tokens_context=sel.tokens_context,
            answer=out["answer"], score_difference=out["score_difference"],
            source_chunk_id=source, answer_span=span, truncated=out["truncated"],
            selection=selection, redundancy=sel.redundancy,
            t_search_ms=(t1 - t0) * 1000, t_select_ms=(t2 - t1) * 1000,
            t_model_ms=out["time_ms"] if out.get("cached") else (t3 - t2) * 1000,
            t_total_ms=(t3 - t0) * 1000,
            extra={"values": sel.values, "weights": sel.weights, "total_value": sel.total_value,
                   "spans": sel.spans, "model_cached": out.get("cached", False),
                   "raw_answer": out.get("raw_answer", "")})


def print_answer(r, width=100):
    print(f"\nPregunta : {r.question}")
    print(f"Búsqueda : {r.method} ({r.algorithm}) | {r.search.n_examined} examinados, "
          f"{r.search.n_matched} con coincidencias")
    for c in r.search.details.get("corrections", []):
        print(f"  ¿Quisiste decir? {format_correction(c)}")
    print(f"Contexto : estrategia {r.selection}, redundancia {'sí' if r.redundancy else 'no'} | "
          f"{r.tokens_context} tokens de {r.token_budget} disponibles | "
          f"entrada total al modelo {r.tokens_used}/{config.MODEL_MAX_TOKENS}"
          f"{'  ¡TRUNCADO!' if r.truncated else ''}")
    for i, s in enumerate(r.selected, 1):
        mark = "  <- respuesta" if s.chunk_id == r.source_chunk_id else ""
        print(f"  [{i}] fragmento {s.chunk_id} [{s.doc} > {s.section}] score={s.score:.3f} "
              f"cobertura={s.coverage:.0%} tokens={r.extra['weights'][s.chunk_id]}{mark}")
    for cid, why in r.discarded:
        print(f"  (descartado {cid}: {why})")
    print(f"\nRespuesta: {r.answer}   (score_difference = {r.score_difference:.2f}, umbral {config.NO_ANSWER_THRESHOLD})")
    if r.source_chunk_id is not None:
        text = next(s.text for s in r.selected if s.chunk_id == r.source_chunk_id)
        a, b = r.answer_span
        snippet = text[max(0, a - 120):a] + "[" + text[a:b] + "]" + text[b:b + 120]
        print(textwrap.indent(textwrap.fill("…" + snippet.replace("\n", " ") + "…", width), "  "))
    print(f"Tiempos  : búsqueda {r.t_search_ms:.1f} ms | selección {r.t_select_ms:.1f} ms | "
          f"modelo {r.t_model_ms:.1f} ms | total {r.t_total_ms:.1f} ms")


def main():
    ap = argparse.ArgumentParser(description="CosmoQuery: pregunta -> búsqueda -> contexto -> modelo")
    ap.add_argument("question")
    ap.add_argument("--method", default="approximate", choices=METHODS)
    ap.add_argument("--alg", default=None, help="algoritmo de búsqueda (por defecto hybrid / kmp)")
    ap.add_argument("--selection", default="greedy", choices=STRATEGIES)
    ap.add_argument("--no-redundancy", action="store_true", help="no eliminar fragmentos redundantes")
    ap.add_argument("--k", type=int, default=None, help="k para la estrategia topk")
    args = ap.parse_args()

    print("Cargando índice y modelo…")
    cq = CosmoQuery()
    print_answer(cq.ask(args.question, args.method, args.alg, args.selection,
                        not args.no_redundancy, args.k))


if __name__ == "__main__":
    main()