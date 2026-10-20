#ETAPA 4 - algoritmos de búsqueda aproximada

import time

import config
from preprocessing import STOPWORDS
from structures import quickselect_top_k


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def osa_distance(a, b):
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
    if metric not in METRICS:
        raise ValueError(f"Métrica desconocida: {metric}. Opciones: {list(METRICS)}")
    t0 = time.perf_counter()
    osa = metric == "osa"
    exclude = exclude or ()
    m = len(word)
    root_row = list(range(m + 1))
    found = []
    visited = 1
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
            continue
        for c, child in node.children.items():
            stack.append((child, c, ch, row, parent, depth + 1, prefix + c))
    found.sort(key=lambda x: (x[1], -x[2], x[0]))
    stats = {"nodes_visited": visited, "nodes_total": trie.n_nodes,
             "time_ms": (time.perf_counter() - t0) * 1000}
    return found, stats


def brute_force_fuzzy(vocab, word, max_dist, metric="osa", exclude=None):
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
    padded = f"${word}$"
    if len(padded) < n:
        return {padded}
    return {padded[i:i + n] for i in range(len(padded) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def jaccard_words(a_tokens, b_tokens):
    return jaccard(set(a_tokens), set(b_tokens))


class NgramIndex:

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
        top = quickselect_top_k(scored, k, key=lambda x: (x[1], x[2], [-ord(ch) for ch in x[0]]))
        stats = {"candidates": len(shared), "time_ms": (time.perf_counter() - t0) * 1000}
        return top, stats


def lcs_length(a, b):
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]
