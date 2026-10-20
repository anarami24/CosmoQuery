#ETAPA 5 - Selección del contexto para el modelo (Persona 2).

# El modelo acepta a lo más 512 tokens (pregunta + contexto + tokens especiales), así que no
# caben todos los fragmentos recuperados. Elegir cuáles entran es el problema de la mochila 0/1
# (presentación "El problema de la mochila"):
#   objetos = fragmentos candidatos (los CONTEXT_CANDIDATES mejores de la búsqueda),
#   peso w_i = tokens BPE reales del fragmento (con su separador),
#   valor v_i = puntaje normalizado al mayor × (0.5 + cobertura),
#   capacidad W = 512 - tokens de la pregunta - tokens especiales - margen.

# Estrategias:
#   topk    los k primeros de la búsqueda, sin presupuesto ni redundancia (línea base)
#   greedy  algoritmo avaro: ordena por densidad r_i = v_i / w_i y toma mientras quepa
#   dp      programación dinámica: tabla V[i][j] con la solución óptima
# Antes de greedy y dp se descartan fragmentos redundantes (Jaccard de raíces > umbral), que
# aparecen por el traslape de 30 palabras entre fragmentos consecutivos del mismo documento.

from dataclasses import dataclass, field

import config
from approximate import jaccard_words
from structures import merge_sort

STRATEGIES = ["topk", "greedy", "dp"]
SEPARATOR = "\n\n"
MARGIN = 8


# MOCHILA 0/1
def knapsack_greedy(values, weights, capacity):
    """Mochila 0/1 con el criterio avaro de densidad r_i = v_i / w_i.

    Se ordenan los objetos por densidad descendente con el merge_sort de Ana (divide y
    vencerás) y se recorre la lista tomando cada objeto que todavía quepa (si uno no cabe se
    salta y se sigue con el siguiente). No garantiza el óptimo en la mochila 0/1.
    Técnica: algoritmo avaro. Complejidad: O(n log n) tiempo (el ordenamiento), O(n) espacio.
    Devuelve (índices elegidos en orden de densidad, valor total, peso total).
    """
    order = merge_sort(list(range(len(values))),
                       key=lambda i: (-values[i] / max(weights[i], 1e-9), -values[i], i))
    chosen, total_v, total_w = [], 0.0, 0
    for i in order:
        if total_w + weights[i] <= capacity:
            chosen.append(i)
            total_v += values[i]
            total_w += weights[i]
    return chosen, total_v, total_w


def knapsack_dp(values, weights, capacity):
    """Mochila 0/1 óptima con programación dinámica (notación de la presentación del curso).

    V[i][j] = mejor valor usando los primeros i objetos con capacidad j:
      V[i][j] = V[i-1][j]                                   si w_i > j
      V[i][j] = max(V[i-1][j], v_i + V[i-1][j - w_i])       en otro caso
    La solución (qué objetos entran) se reconstruye recorriendo la tabla desde V[n][W]:
    si V[i][j] != V[i-1][j], el objeto i se incluyó y se resta su peso.
    Técnica: programación dinámica. Complejidad: O(n·W) tiempo y espacio (pseudopolinomial;
    con n = 10 y W ≈ 480 son unas 4,800 celdas).
    Devuelve (índices elegidos en orden de índice, valor total, peso total).
    """
    n, W = len(values), max(0, int(capacity))
    V = [[0.0] * (W + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w, v = weights[i - 1], values[i - 1]
        prev, cur = V[i - 1], V[i]
        for j in range(W + 1):
            if w > j:
                cur[j] = prev[j]
            else:
                cur[j] = max(prev[j], v + prev[j - w])
    chosen, j = [], W
    for i in range(n, 0, -1):
        if V[i][j] != V[i - 1][j]:
            chosen.append(i - 1)
            j -= weights[i - 1]
    chosen.reverse()
    return chosen, V[n][W], sum(weights[i] for i in chosen)


# SELECCIÓN DEL CONTEXTO
@dataclass
class ContextSelection:
    strategy: str
    redundancy: bool
    selected: list                      # list[ScoredChunk] en el orden del contexto
    discarded: list                     # list[(chunk_id, motivo)]
    context: str
    spans: list                         # list[(chunk_id, inicio, fin)] dentro de `context`
    token_budget: int
    tokens_question: int
    tokens_context: int                 # tokens reales del contexto ensamblado
    total_value: float
    values: dict = field(default_factory=dict)    # chunk_id -> valor
    weights: dict = field(default_factory=dict)   # chunk_id -> tokens (con separador)

    def chunk_at(self, char_pos):
        """Fragmento del contexto que contiene la posición `char_pos` (de dónde salió la respuesta)."""
        if char_pos is None:
            return None
        for cid, start, end in self.spans:
            if start <= char_pos < end:
                return cid
        return None


class ContextSelector:
    def __init__(self, index, count_tokens=None, special_tokens=None):
        """`count_tokens(texto) -> int` y `special_tokens` vienen del tokenizador del modelo;
        se pueden inyectar para probar sin descargarlo."""
        if count_tokens is None or special_tokens is None:
            import qa_model
            count_tokens = count_tokens or qa_model.count_tokens
            special_tokens = special_tokens if special_tokens is not None else qa_model.special_tokens_pair()
        self.index = index
        self.count_tokens = count_tokens
        self.special_tokens = special_tokens
        self._weights = {}                 # caché por chunk_id

    def weight(self, chunk_id):
        """Tokens BPE del fragmento con su separador delante (el BPE cambia en la unión)."""
        w = self._weights.get(chunk_id)
        if w is None:
            w = self._weights[chunk_id] = self.count_tokens(SEPARATOR + self.index.chunks[chunk_id]["text"])
        return w

    def budget(self, question):
        """W = MODEL_MAX_TOKENS - tokens de la pregunta - especiales - margen."""
        if config.CONTEXT_TOKEN_BUDGET is not None:
            return config.CONTEXT_TOKEN_BUDGET
        return config.MODEL_MAX_TOKENS - self.count_tokens(question) - self.special_tokens - MARGIN

    def select(self, question, results, strategy="greedy", redundancy=True, k=None,
               n_candidates=None, redundancy_threshold=None):
        """Elige fragmentos de `results` (list[ScoredChunk] ordenados por puntaje) y arma el contexto.
        `redundancy_threshold` sustituye a REDUNDANCY_JACCARD (para el experimento de la Etapa 6)."""
        if strategy not in STRATEGIES:
            raise ValueError(f"Estrategia desconocida: {strategy}. Opciones: {STRATEGIES}")
        n_candidates = config.CONTEXT_CANDIDATES if n_candidates is None else n_candidates
        cands = list(results[:n_candidates])
        W = self.budget(question)
        q_tokens = self.count_tokens(question)
        top = max((r.score for r in cands), default=0.0) or 1.0
        values = {r.chunk_id: (r.score / top) * (0.5 + r.coverage) for r in cands}
        weights = {r.chunk_id: self.weight(r.chunk_id) for r in cands}
        discarded = []

        if strategy == "topk":
            k = config.TOP_K if k is None else k
            chosen = cands[:k]
            discarded += [(r.chunk_id, f"fuera del top-{k}") for r in cands[k:]]
        else:
            pool = sorted(cands, key=lambda r: (-values[r.chunk_id], r.chunk_id))
            if redundancy:
                pool, dropped = self._remove_redundant(pool, redundancy_threshold)
                discarded += dropped
            vals = [values[r.chunk_id] for r in pool]
            wts = [weights[r.chunk_id] for r in pool]
            if strategy == "greedy":
                idxs, _, _ = knapsack_greedy(vals, wts, W)
            else:
                idxs, _, _ = knapsack_dp(vals, wts, W)
            picked = set(idxs)
            chosen = [r for i, r in enumerate(pool) if i in picked]
            discarded += [(r.chunk_id, f"no cabe en el presupuesto ({weights[r.chunk_id]} tokens)")
                          for i, r in enumerate(pool) if i not in picked]

        # Ensamblado: orden por valor (desc) y separadores "\n\n"; se guardan los rangos.
        chosen = sorted(chosen, key=lambda r: (-values[r.chunk_id], r.chunk_id))
        context, spans = self._assemble(chosen)
        tokens_ctx = self.count_tokens(context) if context else 0
        if strategy != "topk":
            # Verificación con el tokenizador real: si el ensamblado excede el presupuesto (no
            # debería, porque el peso ya incluye el separador), se quita el de menor valor.
            while chosen and tokens_ctx > W:
                removed = chosen.pop()
                discarded.append((removed.chunk_id, "excede el presupuesto real al ensamblar"))
                context, spans = self._assemble(chosen)
                tokens_ctx = self.count_tokens(context) if context else 0
        return ContextSelection(
            strategy=strategy, redundancy=redundancy and strategy != "topk", selected=chosen,
            discarded=discarded, context=context, spans=spans, token_budget=W,
            tokens_question=q_tokens, tokens_context=tokens_ctx,
            total_value=sum(values[r.chunk_id] for r in chosen), values=values, weights=weights)

    def _remove_redundant(self, pool, threshold=None):
        """Descarta un fragmento si su Jaccard de raíces con uno ya conservado (de mayor valor)
        supera REDUNDANCY_JACCARD. Complejidad O(N²·T) con T tokens por fragmento."""
        threshold = config.REDUNDANCY_JACCARD if threshold is None else threshold
        kept, dropped = [], []
        stems = self.index.stem_tokens
        for r in pool:
            dup = next((k for k in kept
                        if jaccard_words(stems[r.chunk_id], stems[k.chunk_id]) > threshold), None)
            if dup is None:
                kept.append(r)
            else:
                j = jaccard_words(stems[r.chunk_id], stems[dup.chunk_id])
                dropped.append((r.chunk_id, f"redundante con el fragmento {dup.chunk_id} (Jaccard {j:.2f})"))
        return kept, dropped

    @staticmethod
    def _assemble(chosen):
        parts, spans, pos = [], [], 0
        for i, r in enumerate(chosen):
            if i:
                parts.append(SEPARATOR)
                pos += len(SEPARATOR)
            spans.append((r.chunk_id, pos, pos + len(r.text)))
            parts.append(r.text)
            pos += len(r.text)
        return "".join(parts), spans
