#ETAPA 2 

import argparse
import json
import pickle
import statistics
import time
from collections import Counter

import config
from preprocessing import (Preprocessor, STOPWORDS, remove_punctuation, strip_accents,
                           to_lowercase, remove_stopwords, PorterStemmer)
from structures import InvertedIndex, SuffixArray, Trie, deep_sizeof


class CorpusIndex:
    def __init__(self, chunks):
        self.chunks = chunks
        self.preprocessor = Preprocessor()
        self.stem_tokens = []      
        self.word_tokens = []      # palabras normalizadas sin stopwords sin stemming
        self.stem_text = []       
        self.word_text = []
        self.inv_stems = InvertedIndex()
        self.inv_words = InvertedIndex()
        self.trie = Trie()
        self.suffix_array = SuffixArray()
        self.vocab_words = Counter()  
        self.vocab_stems = Counter()
        self.stem_to_words = {}        
        self.build_stats = {}

    def build(self, verbose=True):
        pp = self.preprocessor
        stats = {}

        t0 = time.perf_counter()
        for c in self.chunks:
            surface = pp.surface_tokens(c["text"])
            self.vocab_words.update(surface)
            words = remove_stopwords(surface)
            stems = [pp.stem(w) for w in words]
            for w, s in zip(words, stems):
                self.stem_to_words.setdefault(s, Counter())[w] += 1
            self.vocab_stems.update(stems)
            self.word_tokens.append(words)
            self.stem_tokens.append(stems)
            self.word_text.append(" " + " ".join(words) + " ")
            self.stem_text.append(" " + " ".join(stems) + " ")
        stats["preprocess_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.inv_stems.build(self.stem_tokens)
        self.inv_words.build(self.word_tokens)
        stats["inverted_index_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        for word, freq in self.vocab_words.items():
            if word.isalpha() and len(word) >= 2:
                self.trie.insert(word, freq)
        stats["trie_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.suffix_array.build(self.stem_tokens)
        stats["suffix_array_s"] = time.perf_counter() - t0

        stats.update({
            "n_chunks": len(self.chunks),
            "total_stem_tokens": sum(len(t) for t in self.stem_tokens),
            "vocab_words": len(self.vocab_words),
            "vocab_stems": len(self.vocab_stems),
            "trie_words": len(self.trie),
            "trie_nodes": self.trie.n_nodes,
            "trie_chars_inserted": sum(len(w) for w, _ in self.trie.words()),
            "inv_stems_terms": len(self.inv_stems.postings),
            "inv_stems_pairs": self.inv_stems.n_pairs(),
            "suffix_array_len": len(self.suffix_array),
            "suffix_array_rounds": self.suffix_array.rounds,
        })
        self.build_stats = stats
        if verbose:
            print(f"  preprocesamiento {stats['preprocess_s']:.2f}s | índice invertido "
                  f"{stats['inverted_index_s']:.2f}s | trie {stats['trie_s']:.2f}s | "
                  f"arreglo de sufijos {stats['suffix_array_s']:.2f}s")
        return self

    def memory_report(self):
        #Memoria aproximada de cada estructura
        return {
            "trie_MB": deep_sizeof(self.trie) / 1e6,
            "inverted_index_MB": deep_sizeof(self.inv_stems.postings) / 1e6,
            "suffix_array_MB": (deep_sizeof(self.suffix_array.seq)
                                + self.suffix_array.sa.itemsize * len(self.suffix_array.sa) * 2) / 1e6,
            "chunks_text_MB": sum(len(c["text"]) for c in self.chunks) / 1e6,
        }

    def subset(self, n_chunks):
    #Índice construido solo con los primeros n fragmentos 
        sub = CorpusIndex(self.chunks[:n_chunks])
        sub.preprocessor = self.preprocessor
        sub.stem_tokens = self.stem_tokens[:n_chunks]
        sub.word_tokens = self.word_tokens[:n_chunks]
        sub.stem_text = self.stem_text[:n_chunks]
        sub.word_text = self.word_text[:n_chunks]
        sub.inv_stems = InvertedIndex().build(sub.stem_tokens)
        sub.inv_words = InvertedIndex().build(sub.word_tokens)
        sub.suffix_array = SuffixArray().build(sub.stem_tokens)
        return sub

    def save(self, path=config.INDEX_FILE):
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_index(path=config.INDEX_FILE):
    #Punto de entrada para los demás módulos 
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Ejecuta primero: python index_builder.py")
    with open(path, "rb") as f:
        return pickle.load(f)


def load_chunks(path=config.CHUNKS_FILE):
    return json.loads(path.read_text(encoding="utf-8"))


#Reporte de la Etapa 2: 
def preprocessing_ablation(chunks):
    texts = [c["text"] for c in chunks]
    stemmer = PorterStemmer()
    steps = [
        ("0. Texto crudo (split por espacios)", lambda t: t),
        ("1. + Minúsculas", to_lowercase),
        ("2. + Normalizar acentos (NFD)", strip_accents),
        ("3. + Quitar puntuación y especiales", remove_punctuation),
    ]
    rows, current = [], texts
    for name, fn in steps:
        t0 = time.perf_counter()
        current = [fn(t) for t in current]
        elapsed = time.perf_counter() - t0
        tokens = [t.split() for t in current]
        rows.append(_row(name, tokens, elapsed))
    token_lists = [t.split() for t in current]
    t0 = time.perf_counter()
    token_lists = [remove_stopwords(t) for t in token_lists]
    rows.append(_row("4. + Quitar stopwords", token_lists, time.perf_counter() - t0))
    t0 = time.perf_counter()
    token_lists = [[stemmer.stem(w) for w in t] for t in token_lists]
    rows.append(_row("5. + Stemming de Porter (estado del arte)", token_lists, time.perf_counter() - t0))
    return rows


def _row(name, token_lists, elapsed):
    vocab = set()
    total = 0
    for t in token_lists:
        vocab.update(t)
        total += len(t)
    return {"step": name, "tokens": total, "vocab": len(vocab), "time_ms": elapsed * 1000}


def bpe_comparison(chunks, model_name="deepset/roberta-base-squad2"):
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(model_name)
    except Exception as e: 
        return {"available": False, "error": str(e)[:200]}
    counts = [len(tok(c["text"], add_special_tokens=False)["input_ids"]) for c in chunks]
    words = [c["n_words"] for c in chunks]
    sample_word = "magnetosphere"
    return {
        "available": True,
        "model": model_name,
        "bpe_vocab_size": tok.vocab_size,
        "tokens_per_chunk_avg": statistics.mean(counts),
        "tokens_per_chunk_max": max(counts),
        "tokens_per_word": sum(counts) / max(1, sum(words)),
        "chunks_over_384_tokens": sum(c > 384 for c in counts),
        "example": {sample_word: tok.tokenize(" " + sample_word)},
    }


def stemming_examples(index, n=12):
    groups = sorted(index.stem_to_words.items(), key=lambda kv: -len(kv[1]))
    return [(stem, list(words.keys())[:6]) for stem, words in groups[:n]]


def write_stage2_report(index, ablation, bpe, memory, path):
    s = index.build_stats
    L = ["# Etapa 2 - Preprocesamiento e indexación\n",
         "## Efecto acumulado de cada técnica de preprocesamiento\n",
         "| Paso | Tokens | Vocabulario | Tiempo (ms) |", "|---|---:|---:|---:|"]
    base_vocab = ablation[0]["vocab"]
    for r in ablation:
        L.append(f"| {r['step']} | {r['tokens']:,} | {r['vocab']:,} ({100 * r['vocab'] / base_vocab:.0f}%) | {r['time_ms']:.1f} |")
    L += ["\n## Ejemplos de stemming (raíz -> variantes agrupadas)\n", "| Raíz | Variantes |", "|---|---|"]
    for stem, words in stemming_examples(index):
        L.append(f"| {stem} | {', '.join(words)} |")
    L += ["\n## Tokenización por subpalabras (BPE) del modelo RoBERTa\n"]
    if bpe.get("available"):
        L += [f"- Vocabulario BPE: {bpe['bpe_vocab_size']:,} subpalabras",
              f"- Tokens BPE por fragmento: promedio {bpe['tokens_per_chunk_avg']:.0f}, máximo {bpe['tokens_per_chunk_max']}",
              f"- Tokens BPE por palabra: {bpe['tokens_per_word']:.2f}",
              f"- Fragmentos con más de 384 tokens: {bpe['chunks_over_384_tokens']}",
              f"- Ejemplo: {bpe['example']}"]
    else:
        L.append(f"- No disponible en esta ejecución ({bpe.get('error', '')}). Ejecutar con internet y `transformers` instalado.")
    L += ["\n## Estructuras construidas\n",
          "| Estructura | Tamaño | Construcción (s) | Memoria aprox. (MB) | Complejidad construcción | Complejidad espacio |",
          "|---|---|---:|---:|---|---|",
          f"| Trie (vocabulario) | {s['trie_words']:,} palabras, {s['trie_nodes']:,} nodos (de {s['trie_chars_inserted']:,} caracteres) | {s['trie_s']:.3f} | {memory['trie_MB']:.1f} | O(L) | O(L) nodos |",
          f"| Índice invertido (hash) | {s['inv_stems_terms']:,} términos, {s['inv_stems_pairs']:,} pares | {s['inverted_index_s']:.3f} | {memory['inverted_index_MB']:.1f} | O(T) | O(P) ≤ O(T) |",
          f"| Arreglo de sufijos | {s['suffix_array_len']:,} posiciones, {s['suffix_array_rounds']} rondas | {s['suffix_array_s']:.3f} | {memory['suffix_array_MB']:.1f} | O(n log² n) | O(n) |",
          "\nL = caracteres del vocabulario, T = tokens de la colección, P = pares (término, fragmento), n = términos de la colección.",
          f"\nCompresión del Trie: {s['trie_nodes']:,} nodos para {s['trie_chars_inserted']:,} caracteres "
          f"({100 * s['trie_nodes'] / max(1, s['trie_chars_inserted']):.0f}%), gracias a los prefijos compartidos."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Etapa 2: preprocesamiento e indexación")
    ap.add_argument("--no-bpe", action="store_true")
    args = ap.parse_args()

    chunks = load_chunks()
    print(f"Construyendo índice para {len(chunks):,} fragmentos...")
    import index_builder
    index = index_builder.CorpusIndex(chunks).build()
    index.save()
    print(f"Índice guardado en {config.INDEX_FILE}")

    print("Generando reporte de la Etapa 2...")
    ablation = preprocessing_ablation(chunks)
    bpe = {"available": False, "error": "omitido con --no-bpe"} if args.no_bpe else bpe_comparison(chunks)
    memory = index.memory_report()
    config.RESULTS_DIR.mkdir(exist_ok=True)
    write_stage2_report(index, ablation, bpe, memory, config.RESULTS_DIR / "etapa2_preprocesamiento.md")
    (config.RESULTS_DIR / "etapa2_stats.json").write_text(json.dumps(
        {"build": index.build_stats, "ablation": ablation, "bpe": bpe, "memory": memory},
        indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for r in ablation:
        print(f"  {r['step']:<45} tokens={r['tokens']:>9,}  vocab={r['vocab']:>7,}")
    print(f"Reporte: {config.RESULTS_DIR / 'etapa2_preprocesamiento.md'}")


if __name__ == "__main__":
    main()
