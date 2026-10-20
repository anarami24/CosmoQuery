#ETAPA 4 - algoritmos de búsqueda aproximada

# A) distancia de edición (Levenshtein y OSA) recorriendo el Trie con poda
# B) n-gramas de caracteres + Jaccard con una tabla hash
# m = largo de la palabra buscada, L = largo de la otra, N = nodos del Trie, V = nodos visitados

import time

import config
from preprocessing import STOPWORDS
from structures import quickselect_top_k


def levenshtein(a, b):
    """Distancia de Levenshtein (insertar, borrar y sustituir cuestan 1).
    PD con dos filas. Tiempo O(|a|·|b|), espacio O(|b|)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def osa_distance(a, b):
    """Damerau-Levenshtein restringida (OSA): además permite intercambiar dos letras
    vecinas con costo 1, así "largset" -> "largest" vale 1 y no 2.
    PD con tres filas. Tiempo O(|a|·|b|), espacio O(|b|)."""
    n = len(b)
    grand = None
    prev = list(range(n + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * n
        ca = a[i - 1]
        for j in range(1, n + 1):
            cb = b[j - 1]
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                v = min(v, grand[j - 2] + 1)
            cur[j] = v
        grand, prev = prev, cur
    return prev[-1]


METRICS = {"lev": levenshtein, "osa": osa_distance}


def edit_distance_table(a, b, metric="osa"):
    """Tabla completa de la PD y las celdas donde se usó transposición (para mostrarla).
    Tiempo y espacio O(|a|·|b|)."""
    D = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    swaps = []
    for i in range(len(a) + 1):
        D[i][0] = i
    for j in range(len(b) + 1):
        D[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if (metric == "osa" and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]
                    and D[i - 2][j - 2] + 1 < D[i][j]):
                D[i][j] = D[i - 2][j - 2] + 1
                swaps.append((i, j))
    return D, swaps


def max_edit_distance(length, rules=None, min_len=None):
    # con la config por defecto: 1-3 letras -> 0 (no se corrige), 4-7 -> 1, 8 o más -> 2
    rules = config.FUZZY_MAX_DIST if rules is None else rules
    min_len = config.FUZZY_MIN_LEN if min_len is None else min_len
    if length < min_len:
        return 0
    best = 0
    for min_length, dist in rules.items():
        if length >= min_length:
            best = max(best, dist)
    return best


def trie_fuzzy_search(trie, word, max_dist, metric="osa", exclude=None, prefix_mode=False):
    """Palabras del Trie a distancia <= max_dist de `word`.

    Cada nodo es un prefijo; al bajar se calcula su fila de la tabla de PD a partir de la
    fila del padre, así los prefijos compartidos se calculan una sola vez. Poda: el mínimo
    de la fila nunca baja al seguir bajando, entonces si ya pasa max_dist se descarta el
    subárbol completo. Con prefix_mode=True se regresan prefijos parecidos (autocompletado).

    Técnica: ramificación y poda + PD. Tiempo O(V·m), peor caso O(N·m); espacio O(prof·m).
    """
    if metric not in METRICS:
        raise ValueError(f"Métrica desconocida: {metric}. Opciones: {list(METRICS)}")
    t0 = time.perf_counter()
    osa = metric == "osa"
    exclude = exclude or ()
    m = len(word)
    root_row = list(range(m + 1))
    found = []
    visited = 1
    # pila de (nodo, letra, letra del padre, fila del padre, fila del abuelo, profundidad, prefijo)
    stack = [(child, ch, None, root_row, None, 1, ch) for ch, child in trie.root.children.items()]
    while stack:
        node, ch, prev_ch, parent, grand, depth, prefix = stack.pop()
        visited += 1
        row = [depth] + [0] * m
        for j in range(1, m + 1):
            wj = word[j - 1]
            v = min(parent[j] + 1, row[j - 1] + 1, parent[j - 1] + (ch != wj))
            if osa and grand is not None and j > 1 and ch == word[j - 2] and prev_ch == wj:
                v = min(v, grand[j - 2] + 1)
            row[j] = v
        if prefix_mode:
            if row[m] <= max_dist:
                found.append((prefix, row[m], node.freq))
                continue
        elif node.is_end and row[m] <= max_dist and node.word not in exclude:
            found.append((node.word, row[m], node.freq))
        if min(row) > max_dist:
            continue                         # poda
        for c, child in node.children.items():
            stack.append((child, c, ch, row, parent, depth + 1, prefix + c))
    found.sort(key=lambda x: (x[1], -x[2], x[0]))
    stats = {"nodes_visited": visited, "nodes_total": trie.n_nodes,
             "time_ms": (time.perf_counter() - t0) * 1000}
    return found, stats


def brute_force_fuzzy(vocab, word, max_dist, metric="osa", exclude=None):
    """Sin poda: compara contra todo el vocabulario. Sirve para medir y para las pruebas.
    Tiempo O(|Vocab|·L·m)."""
    t0 = time.perf_counter()
    dist_fn = METRICS[metric]
    exclude = exclude or ()
    found = []
    for w, freq in vocab:
        if w in exclude:
            continue
        d = dist_fn(word, w)
        if d <= max_dist:
            found.append((w, d, freq))
    found.sort(key=lambda x: (x[1], -x[2], x[0]))
    return found, {"comparisons": len(vocab), "time_ms": (time.perf_counter() - t0) * 1000}


def char_ngrams(word, n=2):
    """n-gramas de "$word$", p. ej. "moon" -> {"$m", "mo", "oo", "on", "n$"}. O(|w|)."""
    padded = f"${word}$"
    if len(padded) < n:
        return {padded}
    return {padded[i:i + n] for i in range(len(padded) - n + 1)}


def jaccard(a, b):
    """|A ∩ B| / |A ∪ B| (0 si los dos están vacíos). Hashing con sets, O(|A| + |B|)."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def jaccard_words(a_tokens, b_tokens):
    return jaccard(set(a_tokens), set(b_tokens))


class NgramIndex:
    """Tabla hash n-grama -> palabras del vocabulario (sin stopwords).
    Construir: O(Σ|w|). Consultar: O(suma de las listas de los n-gramas de la palabra)."""

    def __init__(self, vocab, n=None, exclude=STOPWORDS):
        self.n = config.NGRAM_N if n is None else n
        self.table = {}
        self.freq = {}
        self.size = {}
        for word, freq in vocab:
            if word in exclude:
                continue
            grams = char_ngrams(word, self.n)
            self.freq[word] = freq
            self.size[word] = len(grams)
            for g in grams:
                bucket = self.table.get(g)
                if bucket is None:
                    bucket = self.table[g] = set()
                bucket.add(word)

    def __len__(self):
        return len(self.freq)

    def lookup(self, word, min_j=None, k=None):
        # se cuenta cuántos n-gramas comparte cada palabra y J = c / (|A| + |B| - c)
        t0 = time.perf_counter()
        min_j = config.NGRAM_MIN_JACCARD if min_j is None else min_j
        k = config.FUZZY_MAX_CANDIDATES if k is None else k
        grams = char_ngrams(word, self.n)
        shared = {}
        for g in grams:
            for w in self.table.get(g, ()):
                shared[w] = shared.get(w, 0) + 1
        scored = []
        for w, c in shared.items():
            j = c / (len(grams) + self.size[w] - c)
            if j >= min_j:
                scored.append((w, j, self.freq[w]))
        # empates: mayor frecuencia y luego orden alfabético
        top = quickselect_top_k(scored, k, key=lambda x: (x[1], x[2], [-ord(ch) for ch in x[0]]))
        stats = {"candidates": len(shared), "time_ms": (time.perf_counter() - t0) * 1000}
        return top, stats


def lcs_length(a, b):
    """Subsecuencia común más larga (la de clase): LCS("ABCXYZAY", "BXYZABC") = 5.
    PD con dos filas. Tiempo O(|a|·|b|), espacio O(|b|)."""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]
