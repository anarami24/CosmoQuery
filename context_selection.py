#ETAPA 5 - selección del contexto

from dataclasses import dataclass, field

import config
from approximate import jaccard_words
from structures import merge_sort

STRATEGIES = ["topk", "greedy", "dp"]
SEPARATOR = "\n\n"
MARGIN = 8


def knapsack_greedy(values, weights, capacity):
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


@dataclass
class ContextSelection:
    strategy: str
    redundancy: bool
    selected: list
    discarded: list
    context: str
    spans: list
    token_budget: int
    tokens_question: int
    tokens_context: int
    total_value: float
    values: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)

    def chunk_at(self, char_pos):
        if char_pos is None:
            return None
        for cid, start, end in self.spans:
            if start <= char_pos < end:
                return cid
        return None


class ContextSelector:
    def __init__(self, index, count_tokens=None, special_tokens=None):
        if count_tokens is None or special_tokens is None:
            import qa_model
            count_tokens = count_tokens or qa_model.count_tokens
            special_tokens = special_tokens if special_tokens is not None else qa_model.special_tokens_pair()
        self.index = index
        self.count_tokens = count_tokens
        self.special_tokens = special_tokens
        self._weights = {}

    def weight(self, chunk_id):
        w = self._weights.get(chunk_id)
        if w is None:
            w = self._weights[chunk_id] = self.count_tokens(SEPARATOR + self.index.chunks[chunk_id]["text"])
        return w

    def budget(self, question):
        if config.CONTEXT_TOKEN_BUDGET is not None:
            return config.CONTEXT_TOKEN_BUDGET
        return config.MODEL_MAX_TOKENS - self.count_tokens(question) - self.special_tokens - MARGIN

    def select(self, question, results, strategy="greedy", redundancy=True, k=None,
               n_candidates=None, redundancy_threshold=None):
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

        chosen = sorted(chosen, key=lambda r: (-values[r.chunk_id], r.chunk_id))
        context, spans = self._assemble(chosen)
        tokens_ctx = self.count_tokens(context) if context else 0
        if strategy != "topk":
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
