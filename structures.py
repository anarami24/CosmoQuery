#ETAPA 2 

import heapq
import random
import sys
from array import array

# TRIE
class TrieNode:
    __slots__ = ("children", "is_end", "freq", "word")

    def __init__(self):
        self.children = {}   
        self.is_end = False
        self.freq = 0          
        self.word = None       

class Trie:
    def __init__(self):
        self.root = TrieNode()
        self.n_words = 0
        self.n_nodes = 1

    def insert(self, word, freq=1):
        node = self.root
        for ch in word:
            nxt = node.children.get(ch)
            if nxt is None:
                nxt = TrieNode()
                node.children[ch] = nxt
                self.n_nodes += 1
            node = nxt
        if not node.is_end:
            node.is_end = True
            node.word = word
            self.n_words += 1
        node.freq += freq

    def _find_node(self, prefix):
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def contains(self, word):
        node = self._find_node(word)
        return node is not None and node.is_end

    def frequency(self, word):
        node = self._find_node(word)
        return node.freq if node is not None and node.is_end else 0

    def starts_with(self, prefix):
        return self._find_node(prefix) is not None

    def autocomplete(self, prefix, k=5):
        prefix = prefix.lower()
        node = self._find_node(prefix)
        if node is None:
            return []
        heap = []                     
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur.is_end:
                item = (cur.freq, cur.word)
                if len(heap) < k:
                    heapq.heappush(heap, item)
                elif item > heap[0]:
                    heapq.heapreplace(heap, item)
            stack.extend(cur.children.values())
        return [w for f, w in sorted(heap, key=lambda x: (-x[0], x[1]))]

    def words(self):
        stack, out = [self.root], []
        while stack:
            cur = stack.pop()
            if cur.is_end:
                out.append((cur.word, cur.freq))
            stack.extend(cur.children.values())
        return out

    def __len__(self):
        return self.n_words

    def __contains__(self, word):
        return self.contains(word)


#INDICE INVERTIDO
class InvertedIndex:

    def __init__(self):
        self.postings = {}
        self.doc_len = {}
        self.n_docs = 0
        self.avg_len = 0.0

    def build(self, token_lists):
        for chunk_id, tokens in enumerate(token_lists):
            self.doc_len[chunk_id] = len(tokens)
            for t in tokens:
                plist = self.postings.get(t)
                if plist is None:
                    plist = self.postings[t] = {}
                plist[chunk_id] = plist.get(chunk_id, 0) + 1
        self.n_docs = len(token_lists)
        self.avg_len = sum(self.doc_len.values()) / max(1, self.n_docs)
        return self

    def get(self, term):
        return self.postings.get(term, {})

    def df(self, term):
        return len(self.postings.get(term, ()))

    def idf(self, term):
        import math
        n, df = self.n_docs, self.df(term)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def candidates(self, terms):
        out = set()
        for t in terms:
            out.update(self.postings.get(t, ()))
        return out

    def n_pairs(self):
        return sum(len(p) for p in self.postings.values())

# MERGE SORT 
def merge_sort(items, key=lambda x: x):
    if len(items) <= 1:
        return list(items)
    mid = len(items) // 2
    left = merge_sort(items[:mid], key)
    right = merge_sort(items[mid:], key)
    merged, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if key(right[j]) < key(left[i]):
            merged.append(right[j]); j += 1
        else:
            merged.append(left[i]); i += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged

# ARREGLO DE SUFIJOS 
class SuffixArray:

    def __init__(self, sort_fn=None):
        self.sort_fn = sort_fn
        self.seq = []
        self.sa = array("i")
        self.pos2chunk = array("i")
        self.term_id = {}
        self.rounds = 0

    def build(self, token_lists):
        seq, pos2chunk = [], []
        for chunk_id, tokens in enumerate(token_lists):
            for t in tokens:
                tid = self.term_id.get(t)
                if tid is None:
                    tid = self.term_id[t] = len(self.term_id)
                seq.append(tid)
                pos2chunk.append(chunk_id)
            seq.append(-(chunk_id + 1))     
            pos2chunk.append(chunk_id)
        self.seq = seq
        n = len(seq)

        distinct = sorted(set(seq))
        rank_of = {v: r for r, v in enumerate(distinct)}
        rank = [rank_of[v] for v in seq]
        sa = list(range(n))
        k, rounds = 1, 0
        while True:
            rounds += 1
            key = (lambda i: (rank[i], rank[i + k] if i + k < n else -1))
            sa = self.sort_fn(sa, key=key) if self.sort_fn else sorted(sa, key=key)
            new_rank = [0] * n
            for j in range(1, n):
                new_rank[sa[j]] = new_rank[sa[j - 1]] + (key(sa[j]) != key(sa[j - 1]))
            rank = new_rank
            if rank[sa[-1]] == n - 1 or k >= n:
                break
            k *= 2
        self.sa = array("i", sa)
        self.pos2chunk = array("i", pos2chunk)
        self.rounds = rounds
        return self

    def _prefix(self, pos, m):
        return self.seq[pos:pos + m]

    def find(self, phrase_terms):
        ids = []
        for t in phrase_terms:
            tid = self.term_id.get(t)
            if tid is None:
                return []
            ids.append(tid)
        m, n = len(ids), len(self.sa)
        lo, hi = 0, n
        while lo < hi:                             # cota inferior
            mid = (lo + hi) // 2
            if self._prefix(self.sa[mid], m) < ids:
                lo = mid + 1
            else:
                hi = mid
        start = lo
        hi = n
        while lo < hi:                             # cota superior
            mid = (lo + hi) // 2
            if self._prefix(self.sa[mid], m) <= ids:
                lo = mid + 1
            else:
                hi = mid
        return [self.sa[i] for i in range(start, lo)]

    def count_by_chunk(self, phrase_terms):
        counts = {}
        for pos in self.find(phrase_terms):
            c = self.pos2chunk[pos]
            counts[c] = counts.get(c, 0) + 1
        return counts

    def __len__(self):
        return len(self.sa)

# QUICKSELECT
def quickselect_top_k(items, k, key=lambda x: x, rng=random):
    #Devuelve los k elementos con mayor `key` ordenados de mayor a menor.
   
    items = list(items)
    if k <= 0 or not items:
        return []
    if k >= len(items):
        return sorted(items, key=key, reverse=True)
    selected = []
    need = k
    while need > 0:
        pivot = key(rng.choice(items))
        greater = [x for x in items if key(x) > pivot]
        equal = [x for x in items if key(x) == pivot]
        if len(greater) >= need:
            items = greater                         # los k están todos entre los mayores
        elif len(greater) + len(equal) >= need:
            selected.extend(greater)
            selected.extend(equal[:need - len(greater)])
            need = 0
        else:
            selected.extend(greater)
            selected.extend(equal)
            need -= len(greater) + len(equal)
            items = [x for x in items if key(x) < pivot]
    return sorted(selected, key=key, reverse=True)


def deep_sizeof(obj, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum(deep_sizeof(k, seen) + deep_sizeof(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(deep_sizeof(x, seen) for x in obj)
    elif hasattr(obj, "__slots__"):
        size += sum(deep_sizeof(getattr(obj, s), seen) for s in obj.__slots__ if hasattr(obj, s))
    elif hasattr(obj, "__dict__"):
        size += deep_sizeof(vars(obj), seen)
    return size
