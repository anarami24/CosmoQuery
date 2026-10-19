"""
Pruebas de correctitud de Persona 2 (Etapas 4 y 5).
"""
import random
import sys
import unittest
from functools import lru_cache
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approximate import (NgramIndex, brute_force_fuzzy, char_ngrams, edit_distance_table,  # noqa: E402
                         jaccard, jaccard_words, lcs_length, levenshtein, max_edit_distance,
                         osa_distance, trie_fuzzy_search)
from preprocessing import STOPWORDS                                                         # noqa: E402
from structures import Trie                                                                 # noqa: E402


# Implementaciones de referencia: la definición recursiva, memoizada, sin optimizar.
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
    """Fuerza bruta: la subsecuencia más larga de `a` que también es subsecuencia de `b`."""
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
        self.assertEqual(osa_distance("ca", "abc"), 3)      # OSA no edita dos veces la misma subcadena
        self.assertEqual(levenshtein("kitten", "sitting"), 3)

    def test_table_marks_transposition(self):
        D, swaps = edit_distance_table("largset", "largest", "osa")
        self.assertEqual(D[-1][-1], 1)
        self.assertIn((6, 6), swaps)                        # "se" -> "es" en las posiciones 5-6
        D_lev, swaps_lev = edit_distance_table("largset", "largest", "lev")
        self.assertEqual((D_lev[-1][-1], swaps_lev), (2, []))

    def test_max_edit_distance(self):
        rules = {4: 1, 8: 2}
        self.assertEqual([max_edit_distance(n, rules, 4) for n in (2, 3, 4, 7, 8, 12)], [0, 0, 1, 1, 2, 2])


class TestTrieFuzzySearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Trie real de la colección (se construye desde data/chunks.json, que está en el repo).
        from index_builder import CorpusIndex, load_chunks
        cls.idx = CorpusIndex(load_chunks()).build(verbose=False)
        cls.vocab = cls.idx.trie.words()

    def brute(self, word, k, metric, exclude=None):
        # Fuerza bruta acotada por |len(a) - len(b)| <= k (cota inferior válida de la distancia).
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
        # "ju" ya está a distancia 1 de "jpu" (una inserción): se acepta y no se baja más.
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
        self.assertNotIn("the", index.freq)                 # sin stopwords
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


if __name__ == "__main__":
    unittest.main()
