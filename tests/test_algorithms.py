"""
Pruebas de correctitud.  
"""
import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preprocessing import PorterStemmer, Preprocessor          # noqa: E402
from string_matching import MATCHERS, prefix_function, z_function  # noqa: E402
from structures import (InvertedIndex, SuffixArray, Trie, merge_sort,  # noqa: E402
                        quickselect_top_k)


def reference_find_all(pattern, text):
    return [m.start() for m in re.finditer(f"(?={re.escape(pattern)})", text)]


class TestStringMatching(unittest.TestCase):
    def test_random_against_reference(self):
        rng = random.Random(7)
        for _ in range(400):
            alphabet = rng.choice(["ab", "abc", "acgt", "ab "])
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
            pattern = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 5)))
            expected = reference_find_all(pattern, text)
            for name, Matcher in MATCHERS.items():
                self.assertEqual(Matcher(pattern).search(text), expected, f"{name}: {pattern!r} en {text!r}")

    def test_worst_case_inputs(self):
        text, pattern = "a" * 300, "a" * 10
        for name, Matcher in MATCHERS.items():
            self.assertEqual(len(Matcher(pattern).search(text)), 291, name)

    def test_prefix_and_z(self):
        self.assertEqual(prefix_function("aabaaab"), [0, 1, 0, 1, 2, 2, 3])
        self.assertEqual(z_function("aaabaab"), [7, 2, 1, 0, 2, 1, 0])

    def test_whole_word_patterns(self):
        text = " moon moons honeymoon moon "
        for name, Matcher in MATCHERS.items():
            self.assertEqual(len(Matcher(" moon ").search(text)), 2, name)


class TestStructures(unittest.TestCase):
    def test_trie(self):
        t = Trie()
        for w, f in [("jupiter", 10), ("juno", 4), ("july", 6), ("jump", 1), ("mars", 3)]:
            t.insert(w, f)
        self.assertEqual(t.autocomplete("ju", 3), ["jupiter", "july", "juno"])
        self.assertTrue(t.contains("mars"))
        self.assertFalse(t.contains("mar"))
        self.assertTrue(t.starts_with("mar"))
        self.assertEqual(t.autocomplete("x"), [])
        self.assertEqual(len(t), 5)

    def test_suffix_array_against_scan(self):
        rng = random.Random(3)
        docs = [[rng.choice("abcd") for _ in range(rng.randint(1, 30))] for _ in range(25)]
        sa = SuffixArray().build(docs)
        sa_merge = SuffixArray(sort_fn=merge_sort).build(docs)
        self.assertEqual(list(sa.sa), list(sa_merge.sa))
        for phrase in (["a"], ["a", "b"], ["c", "c", "d"], ["z"]):
            expected = {}
            for cid, d in enumerate(docs):
                c = sum(1 for i in range(len(d) - len(phrase) + 1) if d[i:i + len(phrase)] == phrase)
                if c:
                    expected[cid] = c
            self.assertEqual(sa.count_by_chunk(phrase), expected, phrase)

    def test_merge_sort_and_quickselect(self):
        rng = random.Random(1)
        data = [rng.randint(0, 50) for _ in range(500)]
        self.assertEqual(merge_sort(data), sorted(data))
        for k in (0, 1, 5, 50, 500, 600):
            self.assertEqual(quickselect_top_k(data, k), sorted(data, reverse=True)[:k])

    def test_inverted_index(self):
        inv = InvertedIndex().build([["a", "b", "a"], ["b"], ["c"]])
        self.assertEqual(inv.get("a"), {0: 2})
        self.assertEqual(inv.df("b"), 2)
        self.assertEqual(inv.candidates(["a", "c"]), {0, 2})
        self.assertGreater(inv.idf("c"), inv.idf("b"))


class TestPreprocessing(unittest.TestCase):
    def test_porter_known_pairs(self):
        pairs = {"caresses": "caress", "ponies": "poni", "motoring": "motor", "hopping": "hop",
                 "relational": "relat", "generalizations": "gener", "oscillators": "oscil",
                 "orbiting": "orbit", "moons": "moon", "happy": "happi", "agreed": "agre"}
        ps = PorterStemmer()
        for w, s in pairs.items():
            self.assertEqual(ps.stem(w), s, w)

    def test_pipeline(self):
        p = Preprocessor()
        self.assertEqual(p.process("What are the MOONS of Jupiter's?"), ["moon", "jupit"])
        self.assertEqual(p.normalize("Négone, 4.6 billion; 1,300 km!"), "negone 4.6 billion 1300 km")


class TestExactSearchConsistency(unittest.TestCase):

    def test_same_ranking(self):
        from index_builder import CorpusIndex
        from exact_search import ALGORITHMS, ExactSearcher
        chunks = [{"id": i, "doc": "d", "section": "s", "text": t, "n_words": len(t.split())}
                  for i, t in enumerate([
                      "Jupiter has a Great Red Spot, a giant storm.",
                      "The red planet Mars has two moons.",
                      "A great storm on Saturn; the spot is white.",
                      "Pluto was discovered in 1930 by Clyde Tombaugh.",
                  ])]
        searcher = ExactSearcher(CorpusIndex(chunks).build(verbose=False))
        for q in ["great red spot storm", "moons of Mars", "Who discovered Pluto?", "nothing here"]:
            ref = searcher.search(q, "naive", 4)
            for alg in ALGORITHMS:
                for use_index in (True, False):
                    res = searcher.search(q, alg, 4, use_index)
                    self.assertEqual([(r.chunk_id, r.score) for r in res.results],
                                     [(r.chunk_id, r.score) for r in ref.results], (q, alg, use_index))
        self.assertEqual(searcher.search("great red spot", "kmp").results[0].chunk_id, 0)


if __name__ == "__main__":
    unittest.main()


class TestHtmlExtractor(unittest.TestCase):
    def test_extracts_article_and_drops_boilerplate(self):
        from html_extractor import blocks_to_raw_text, extract_blocks, remove_boilerplate
        menu = '<nav class="main-menu"><p>Menu text that should never appear in the corpus at all</p></nav>'
        legal = "<p>This legal notice appears on every single page of the website footer area.</p>"
        pages = {}
        for i, body in enumerate(["<h2>Moons</h2><p>Mars has two small moons, Phobos and Deimos, that may be captured asteroids.</p>",
                                  "<p>Venus is the hottest planet in our solar system with a thick atmosphere.</p>",
                                  "<p>Pluto was reclassified as a dwarf planet in 2006 by the astronomers.</p>",
                                  "<p>Saturn is the only planet with an average density less than water.</p>"]):
            html = f"<html><body>{menu}<main><h1>T{i}</h1>{body}{legal}<script>var a='<p>x</p>';</script></main></body></html>"
            pages[i] = extract_blocks(html)[1]
        cleaned, removed = remove_boilerplate(pages)
        self.assertEqual(removed, 4)
        raw = blocks_to_raw_text("Mars Facts", cleaned[0])
        self.assertIn("== Moons ==", raw)
        self.assertIn("Phobos and Deimos", raw)
        self.assertNotIn("Menu text", raw)
        self.assertNotIn("legal notice", raw)
        self.assertNotIn("var a", raw)

    def test_relaxed_mode_for_div_pages(self):
        from html_extractor import content_words, extract_blocks
        html = ("<html><body><main><h1>Moon Facts</h1></main><div class='page-header'>"
                "<div>Earth's Moon is the only place beyond Earth where humans have set foot so far.</div>"
                "</div></body></html>")
        self.assertEqual(content_words(extract_blocks(html)[1]), 0)
        self.assertGreater(content_words(extract_blocks(html, relaxed=True)[1]), 10)