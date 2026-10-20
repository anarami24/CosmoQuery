import random
import sys
import unittest
from functools import lru_cache
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approximate import (NgramIndex, brute_force_fuzzy, char_ngrams, edit_distance_table,
                         jaccard, jaccard_words, lcs_length, levenshtein, max_edit_distance,
                         osa_distance, trie_fuzzy_search)
from preprocessing import STOPWORDS
from structures import Trie


def ref_distance(a, b, transpositions):
    @lru_cache(maxsize=None)
    def d(i, j):
        if i == 0:
            return j
        if j == 0:
            return i
        best = min(d(i - 1, j) + 1, d(i, j - 1) + 1, d(i - 1, j - 1) + (a[i - 1] != b[j - 1]))
        if transpositions and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
            best = min(best, d(i - 2, j - 2) + 1)
        return best
    return d(len(a), len(b))


def ref_lcs(a, b):
    def is_subseq(s, t):
        it = iter(t)
        return all(ch in it for ch in s)
    for size in range(len(a), 0, -1):
        if any(is_subseq(c, b) for c in combinations(a, size)):
            return size
    return 0


def mutate(word, rng):
    ops = rng.choice(["swap", "delete", "substitute", "insert"])
    j = rng.randint(0, max(0, len(word) - 2))
    if ops == "swap" and len(word) >= 2:
        return word[:j] + word[j + 1] + word[j] + word[j + 2:]
    if ops == "delete" and len(word) >= 2:
        return word[:j] + word[j + 1:]
    if ops == "substitute":
        return word[:j] + rng.choice("aeioursnlt") + word[j + 1:]
    return word[:j] + rng.choice("aeioursnlt") + word[j:]


class TestEditDistances(unittest.TestCase):
    def test_random_against_reference(self):
        rng = random.Random(42)
        for _ in range(400):
            alphabet = rng.choice(["ab", "abc", "abcd"])
            a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
            b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))
            self.assertEqual(levenshtein(a, b), ref_distance(a, b, False), (a, b))
            self.assertEqual(osa_distance(a, b), ref_distance(a, b, True), (a, b))
            D, _ = edit_distance_table(a, b, "osa")
            self.assertEqual(D[-1][-1], osa_distance(a, b), (a, b))

    def test_edge_cases(self):
        for fn in (levenshtein, osa_distance):
            self.assertEqual(fn("", ""), 0)
            self.assertEqual(fn("", "abc"), 3)
            self.assertEqual(fn("abc", ""), 3)
            self.assertEqual(fn("jupiter", "jupiter"), 0)
        self.assertEqual(levenshtein("ab", "ba"), 2)
        self.assertEqual(osa_distance("ab", "ba"), 1)
        self.assertEqual(levenshtein("largset", "largest"), 2)
        self.assertEqual(osa_distance("largset", "largest"), 1)
        self.assertEqual(osa_distance("ca", "abc"), 3)
        self.assertEqual(levenshtein("kitten", "sitting"), 3)

    def test_table_marks_transposition(self):
        D, swaps = edit_distance_table("largset", "largest", "osa")
        self.assertEqual(D[-1][-1], 1)
        self.assertIn((6, 6), swaps)
        D_lev, swaps_lev = edit_distance_table("largset", "largest", "lev")
        self.assertEqual((D_lev[-1][-1], swaps_lev), (2, []))

    def test_max_edit_distance(self):
        rules = {4: 1, 8: 2}
        self.assertEqual([max_edit_distance(n, rules, 4) for n in (2, 3, 4, 7, 8, 12)], [0, 0, 1, 1, 2, 2])


_INDEX = None


def real_index():
    global _INDEX
    if _INDEX is None:
        from index_builder import CorpusIndex, load_chunks
        _INDEX = CorpusIndex(load_chunks()).build(verbose=False)
    return _INDEX


class TestTrieFuzzySearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = real_index()
        cls.vocab = cls.idx.trie.words()

    def brute(self, word, k, metric, exclude=None):
        near = [(w, f) for w, f in self.vocab if abs(len(w) - len(word)) <= k]
        return brute_force_fuzzy(near, word, k, metric, exclude)[0]

    def test_pruning_never_loses_solutions(self):
        rng = random.Random(42)
        words = [w for w, _ in self.vocab if len(w) >= 4]
        sample = [mutate(w, rng) for w in rng.sample(words, 50)]
        for word in sample:
            for k in (1, 2):
                got, stats = trie_fuzzy_search(self.idx.trie, word, k, "osa")
                self.assertEqual(got, self.brute(word, k, "osa"), (word, k))
                self.assertLessEqual(stats["nodes_visited"], stats["nodes_total"])
            got, _ = trie_fuzzy_search(self.idx.trie, word, 1, "lev")
            self.assertEqual(got, self.brute(word, 1, "lev"), (word, "lev"))

    def test_known_corrections_and_pruning(self):
        got, stats = trie_fuzzy_search(self.idx.trie, "largset", 1, "osa", exclude=STOPWORDS)
        self.assertEqual(got[0][:2], ("largest", 1))
        self.assertLess(stats["nodes_visited"], stats["nodes_total"] * 0.5)
        lev, _ = trie_fuzzy_search(self.idx.trie, "largset", 1, "lev")
        self.assertNotIn("largest", [w for w, _, _ in lev])
        stop, _ = trie_fuzzy_search(self.idx.trie, "iz", 1, "osa", exclude=STOPWORDS)
        self.assertFalse({w for w, _, _ in stop} & STOPWORDS)

    def test_prefix_mode(self):
        t = Trie()
        for w, f in [("jupiter", 9), ("juno", 4), ("mars", 3), ("perseverance", 2)]:
            t.insert(w, f)
        got, _ = trie_fuzzy_search(t, "jpu", 1, "osa", prefix_mode=True)
        self.assertEqual([p for p, _, _ in got], ["ju"])
        got, _ = trie_fuzzy_search(t, "jupt", 1, "osa", prefix_mode=True)
        self.assertIn("jup", [p for p, _, _ in got])
        for p, d, _ in got:
            self.assertLessEqual(osa_distance(p, "jpu"), 1)
            self.assertTrue(t.starts_with(p))
        self.assertEqual(trie_fuzzy_search(t, "xyz", 1, "osa", prefix_mode=True)[0], [])


class TestNgramsJaccard(unittest.TestCase):
    def test_char_ngrams(self):
        self.assertEqual(char_ngrams("moon", 2), {"$m", "mo", "oo", "on", "n$"})
        self.assertEqual(char_ngrams("io", 3), {"$io", "io$"})
        self.assertEqual(char_ngrams("a", 2), {"$a", "a$"})

    def test_jaccard(self):
        self.assertAlmostEqual(jaccard({1, 2}, {2, 3}), 1 / 3)
        self.assertEqual(jaccard({1}, {1}), 1.0)
        self.assertEqual(jaccard({1}, {2}), 0.0)
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertAlmostEqual(jaccard(char_ngrams("volcanno"), char_ngrams("volcano")), 8 / 9)
        self.assertAlmostEqual(jaccard_words(["a", "b", "b"], ["b", "c"]), 1 / 3)

    def test_ngram_index_matches_direct_jaccard(self):
        vocab = [("volcano", 5), ("volcanoes", 3), ("volume", 2), ("the", 99), ("satellites", 4)]
        index = NgramIndex(vocab, n=2)
        self.assertNotIn("the", index.freq)
        top, stats = index.lookup("volcanno", min_j=0.0, k=10)
        self.assertEqual(top[0][0], "volcano")
        for w, j, _ in top:
            self.assertAlmostEqual(j, jaccard(char_ngrams("volcanno"), char_ngrams(w)))
        self.assertEqual([w for w, _, _ in index.lookup("satelites", 0.45, 3)[0]], ["satellites"])
        self.assertEqual(index.lookup("zzzz", 0.1, 3)[0], [])

    def test_ngram_tie_breaks_by_frequency_then_word(self):
        index = NgramIndex([("abcd", 1), ("abce", 7), ("abcf", 7)], n=2)
        self.assertEqual([w for w, _, _ in index.lookup("abcx", 0.0, 3)[0]], ["abce", "abcf", "abcd"])


class TestLCS(unittest.TestCase):
    def test_slide_example(self):
        self.assertEqual(lcs_length("ABCXYZAY", "BXYZABC"), 5)

    def test_random_against_brute_force(self):
        rng = random.Random(42)
        for _ in range(150):
            a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 7)))
            b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 7)))
            self.assertEqual(lcs_length(a, b), ref_lcs(a, b), (a, b))
        self.assertEqual(lcs_length(["mar", "volcano", "larg"], ["larg", "volcano", "mar"]), 1)


class TestApproximateSearcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from approx_search import ApproximateSearcher
        from exact_search import ExactSearcher
        cls.idx = real_index()
        cls.approx = ApproximateSearcher(cls.idx)
        cls.exact = ExactSearcher(cls.idx)

    def test_no_typos_same_as_exact(self):
        from approx_search import ALGORITHMS
        for q in ["When was Pluto discovered?", "What is the Great Red Spot on Jupiter?",
                  "How many moons does Mars have?"]:
            ref = self.exact.search(q, "kmp")
            for alg in ALGORITHMS:
                res = self.approx.search(q, alg, rerank_beta=0.0)
                self.assertEqual(res.details["corrections"], [], (q, alg))
                self.assertEqual([(r.chunk_id, r.score) for r in res.results],
                                 [(r.chunk_id, r.score) for r in ref.results], (q, alg))
                self.assertEqual(res.n_examined, ref.n_examined)

    def test_typo_finds_jupiter(self):
        res = self.approx.search("How big is Jupitr?", "osa_trie")
        self.assertEqual(res.details["corrections"][0]["candidate"], "jupiter")
        self.assertIn("Jupiter Facts", [r.doc for r in res.results])
        self.assertEqual(res.method, "approximate")
        self.assertGreater(res.details["nodes_visited"], 0)
        self.assertLess(res.details["nodes_visited"], res.details["nodes_total"])

    def test_robust_queries(self):
        for q in ["", "   ", "what is the", "¿¡!?", "zzzzqx", "io"]:
            res = self.approx.search(q)
            self.assertIsInstance(res.results, list, q)
        self.assertEqual(self.approx.search("what is the").results, [])

    def test_subset_rebuilds_trie(self):
        from approx_search import ApproximateSearcher
        sub = self.idx.subset(50)
        self.assertEqual(len(sub.trie), 0)
        searcher = ApproximateSearcher(sub)
        self.assertGreater(len(searcher.trie), 0)
        for r in searcher.search("What is the sun made of?").results:
            self.assertLess(r.chunk_id, 50)


class TestKnapsack(unittest.TestCase):
    @staticmethod
    def brute_force(values, weights, capacity):
        best = 0.0
        n = len(values)
        for mask in range(1 << n):
            w = sum(weights[i] for i in range(n) if mask >> i & 1)
            if w <= capacity:
                best = max(best, sum(values[i] for i in range(n) if mask >> i & 1))
        return best

    def test_slide_example(self):
        from context_selection import knapsack_dp, knapsack_greedy
        chosen, value, weight = knapsack_dp([140, 60, 50], [20, 10, 25], 30)
        self.assertEqual((chosen, value, weight), ([0, 1], 200, 30))
        self.assertEqual(knapsack_greedy([140, 60, 50], [20, 10, 25], 30)[1], 200)

    def test_dp_optimal_and_greedy_feasible(self):
        from context_selection import knapsack_dp, knapsack_greedy
        rng = random.Random(42)
        for _ in range(200):
            n = rng.randint(0, 12)
            values = [round(rng.uniform(0, 1.5), 3) for _ in range(n)]
            weights = [rng.randint(1, 60) for _ in range(n)]
            capacity = rng.randint(0, 200)
            chosen, value, weight = knapsack_dp(values, weights, capacity)
            self.assertAlmostEqual(value, self.brute_force(values, weights, capacity))
            self.assertAlmostEqual(value, sum(values[i] for i in chosen))
            self.assertLessEqual(weight, capacity)
            g_chosen, g_value, g_weight = knapsack_greedy(values, weights, capacity)
            self.assertLessEqual(g_weight, capacity)
            self.assertLessEqual(g_value, value + 1e-9)
            self.assertEqual(len(set(g_chosen)), len(g_chosen))


class TestContextSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from approx_search import ApproximateSearcher
        cls.idx = real_index()
        cls.approx = ApproximateSearcher(cls.idx)

    def fake_selector(self):
        from context_selection import ContextSelector
        return ContextSelector(self.idx, count_tokens=lambda t: len(t.split()), special_tokens=4)

    def test_strategies_and_spans(self):
        res = self.approx.search("When was Pluto discovered?", top_k=10)
        sel = self.fake_selector()
        for strategy in ("greedy", "dp"):
            out = sel.select("When was Pluto discovered?", res.results, strategy)
            self.assertLessEqual(out.tokens_context, out.token_budget, strategy)
            self.assertTrue(out.selected)
            for cid, start, end in out.spans:
                self.assertEqual(out.context[start:end], self.idx.chunks[cid]["text"])
                self.assertEqual(out.chunk_at(start), cid)
            ids = [r.chunk_id for r in out.selected] + [c for c, _ in out.discarded]
            self.assertEqual(sorted(ids), sorted(r.chunk_id for r in res.results))
        top3 = sel.select("q", res.results, "topk", k=3)
        self.assertEqual([r.chunk_id for r in top3.selected],
                         sorted([r.chunk_id for r in res.results[:3]],
                                key=lambda c: -top3.values[c]))

    def test_redundancy_drops_overlapping_chunks(self):
        from search_types import ScoredChunk
        c = self.idx.chunks[10]
        dup = [ScoredChunk(10, 2.0, c["doc"], c["section"], c["text"], coverage=1.0),
               ScoredChunk(10, 1.0, c["doc"], c["section"], c["text"], coverage=1.0)]
        out = self.fake_selector().select("q", dup, "greedy", redundancy=True)
        self.assertEqual(len(out.selected), 1)
        self.assertIn("redundante", out.discarded[0][1])

    def test_real_tokenizer_never_exceeds_budget(self):
        try:
            import qa_model
            qa_model.get_tokenizer()
        except Exception as e:
            self.skipTest(f"tokenizador no disponible: {e}")
        from context_selection import ContextSelector
        from evaluation import load_questions
        sel = ContextSelector(self.idx)
        for q in load_questions()[::7]:
            res = self.approx.search(q["question"], top_k=10)
            for strategy in ("greedy", "dp"):
                out = sel.select(q["question"], res.results, strategy)
                total = out.tokens_question + out.tokens_context + sel.special_tokens
                self.assertLessEqual(total, 512, (q["id"], strategy))
                if out.context:
                    real = len(qa_model.get_tokenizer()(q["question"], out.context)["input_ids"])
                    self.assertLessEqual(real, 512, (q["id"], strategy))


if __name__ == "__main__":
    unittest.main()
