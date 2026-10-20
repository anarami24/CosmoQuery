#ETAPA 2

#Técnicas implementadas :
# 1. Conversión a minúsculas.
#  2. Normalización de acentos / diacríticos (Unicode NFD).
#  3. Eliminación de signos de puntuación y caracteres especiales.
#  4. Tokenización en palabras.
 # 5. Eliminación de stopwords.
#6. Construcción del vocabulario (palabras únicas con frecuencia).
  #  7. [Estado del arte] Stemming con el algoritmo de Porter, implementado desde cero.
  # 8. [Estado del arte, comparación] Tokenización por subpalabras (BPE) del propio modelo RoBERTa, para medir cuántos tokens ocupa cada fragmento en el LLM.

#Todas las funciones son O(n) en la longitud del texto, salvo el stemming, que es O(L) por palabra (L = longitud de la palabra, acotada por una constante pequeña).

import re
import unicodedata
from collections import Counter


#lista de stopwords en inglés (basada en la lista clásica de NLTK/Snowball).

STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren as at be because been
before being below between both but by can cannot could couldn did didn do does doesn doing
don down during each few for from further had hadn has hasn have haven having he her here
hers herself him himself his how i if in into is isn it its itself just let me more most
mustn my myself no nor not now of off on once only or other ought our ours ourselves out over
own same shan she should shouldn so some such than that the their theirs them themselves then
there these they this those through to too under until up very was wasn we were weren what
when where which while who whom why will with won would wouldn you your yours yourself
yourselves s t d ll m o re ve y ain ma
tell many much called name named known
""".split())

#palabras de "relleno" típicas de una PREGUNTA
QUERY_FILLER = frozenset("""
mention mentioned mentions describe described explain explained information info say says
said please thing things something anything give list kind type
""".split())

_POSSESSIVE_RE = re.compile(r"['’]s\b")
_NUM_SEP_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")    
_TOKEN_RE = re.compile(r"\d+(?:\.\d+)+|[^\W_]+")


def to_lowercase(text):
    return text.lower()


def strip_accents(text):
    #descompone cada caracter (NFD) y elimina las marcas diacriticas
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def remove_punctuation(text):
   #elimina signos y caracteres especiales
    text = _POSSESSIVE_RE.sub("", text)
    text = _NUM_SEP_RE.sub("", text)
    return " ".join(_TOKEN_RE.findall(text))


def tokenize(text):
    return text.split()


def remove_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS]


def build_vocabulary(token_lists):
    counter = Counter()
    for tokens in token_lists:
        counter.update(tokens)
    return counter



# Algoritmo de Porter

class PorterStemmer:
    _STEP2 = {
        "ational": "ate", "tional": "tion", "enci": "ence", "anci": "ance", "izer": "ize",
        "bli": "ble", "alli": "al", "entli": "ent", "eli": "e", "ousli": "ous",
        "ization": "ize", "ation": "ate", "ator": "ate", "alism": "al", "iveness": "ive",
        "fulness": "ful", "ousness": "ous", "aliti": "al", "iviti": "ive", "biliti": "ble",
        "logi": "log",
    }
    _STEP3 = {
        "icate": "ic", "ative": "", "alize": "al", "iciti": "ic", "ical": "ic",
        "ful": "", "ness": "",
    }
    _STEP4 = ("al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment",
              "ent", "ion", "ou", "ism", "ate", "iti", "ous", "ive", "ize")

    def __init__(self):
        self._cache = {}
        self._step2 = sorted(self._STEP2.items(), key=lambda kv: -len(kv[0]))
        self._step3 = sorted(self._STEP3.items(), key=lambda kv: -len(kv[0]))
        self._step4 = sorted(self._STEP4, key=len, reverse=True)

    @staticmethod
    def _is_cons(w, i):
        c = w[i]
        if c in "aeiou":
            return False
        if c == "y":
            return i == 0 or not PorterStemmer._is_cons(w, i - 1)
        return True

    def _measure(self, stem):
        """m = número de secuencias VC en la forma [C](VC)^m[V]."""
        n, i, length = 0, 0, len(stem)
        while i < length and self._is_cons(stem, i):
            i += 1
        while i < length:
            while i < length and not self._is_cons(stem, i):
                i += 1
            if i >= length:
                break
            while i < length and self._is_cons(stem, i):
                i += 1
            n += 1
        return n

    def _has_vowel(self, stem):
        return any(not self._is_cons(stem, i) for i in range(len(stem)))

    def _double_cons(self, w):
        return len(w) >= 2 and w[-1] == w[-2] and self._is_cons(w, len(w) - 1)

    def _cvc(self, w):
        return (len(w) >= 3 and self._is_cons(w, len(w) - 3) and not self._is_cons(w, len(w) - 2)
                and self._is_cons(w, len(w) - 1) and w[-1] not in "wxy")

    def _step1a(self, w):
        if w.endswith("sses"):
            return w[:-2]
        if w.endswith("ies"):
            return w[:-2]
        if w.endswith("ss"):
            return w
        if w.endswith("s"):
            return w[:-1]
        return w

    def _step1b(self, w):
        if w.endswith("eed"):
            return w[:-1] if self._measure(w[:-3]) > 0 else w
        flag = False
        if w.endswith("ed") and self._has_vowel(w[:-2]):
            w, flag = w[:-2], True
        elif w.endswith("ing") and self._has_vowel(w[:-3]):
            w, flag = w[:-3], True
        if flag:
            if w.endswith(("at", "bl", "iz")):
                return w + "e"
            if self._double_cons(w) and w[-1] not in "lsz":
                return w[:-1]
            if self._measure(w) == 1 and self._cvc(w):
                return w + "e"
        return w

    def _step1c(self, w):
        if w.endswith("y") and self._has_vowel(w[:-1]):
            return w[:-1] + "i"
        return w

    def _apply_rules(self, w, rules, min_m):
        for suffix, repl in rules:
            if w.endswith(suffix):
                stem = w[:-len(suffix)]
                return stem + repl if self._measure(stem) > min_m else w
        return w

    def _step4_fn(self, w):
        for suffix in self._step4:
            if w.endswith(suffix):
                stem = w[:-len(suffix)]
                if self._measure(stem) > 1:
                    if suffix == "ion" and not stem.endswith(("s", "t")):
                        return w
                    return stem
                return w
        return w

    def _step5(self, w):
        if w.endswith("e"):
            stem = w[:-1]
            m = self._measure(stem)
            if m > 1 or (m == 1 and not self._cvc(stem)):
                w = stem
        if self._measure(w) > 1 and self._double_cons(w) and w.endswith("l"):
            w = w[:-1]
        return w

    def stem(self, word):
        if len(word) <= 2 or not word.isalpha():
            return word
        cached = self._cache.get(word)
        if cached is not None:
            return cached
        w = self._step1a(word)
        w = self._step1b(w)
        w = self._step1c(w)
        w = self._apply_rules(w, self._step2, 0)
        w = self._apply_rules(w, self._step3, 0)
        w = self._step4_fn(w)
        w = self._step5(w)
        self._cache[word] = w
        return w


class Preprocessor:
    def __init__(self, lowercase=True, accents=True, punctuation=True,
                 stopwords=True, stemming=True):
        self.lowercase = lowercase
        self.accents = accents
        self.punctuation = punctuation
        self.stopwords = stopwords
        self.stemming = stemming
        self.stemmer = PorterStemmer()

    def normalize(self, text):
        if self.lowercase:
            text = to_lowercase(text)
        if self.accents:
            text = strip_accents(text)
        if self.punctuation:
            text = remove_punctuation(text)
        return text

    def surface_tokens(self, text):
        return tokenize(self.normalize(text))

    def process(self, text):
        tokens = self.surface_tokens(text)
        if self.stopwords:
            tokens = remove_stopwords(tokens)
        if self.stemming:
            tokens = [self.stemmer.stem(t) for t in tokens]
        return tokens

    def process_query(self, query):
        tokens = remove_stopwords(self.surface_tokens(query)) if self.stopwords else self.surface_tokens(query)
        tokens = [t for t in tokens if t not in QUERY_FILLER]
        return [self.stem(t) for t in tokens]

    def query_words(self, query):
        return [t for t in remove_stopwords(self.surface_tokens(query)) if t not in QUERY_FILLER]

    def stem(self, word):
        return self.stemmer.stem(word) if self.stemming else word

    def word_spans(self, original_text):
        spans = []
        for m in re.finditer(r"[A-Za-zÀ-ÿ0-9]+(?:[.'’][A-Za-z0-9]+)*", original_text):
            norm = self.normalize(m.group())
            for tok in norm.split():
                if self.stopwords and tok in STOPWORDS:
                    continue
                spans.append((m.start(), m.end(), self.stem(tok)))
        return spans


def highlight(original_text, terms, pre="**", post="**"):
    pre_proc = Preprocessor()
    terms = set(terms)
    out, last = [], 0
    for start, end, stem in pre_proc.word_spans(original_text):
        if stem in terms and start >= last:
            out.append(original_text[last:start])
            out.append(pre + original_text[start:end] + post)
            last = end
    out.append(original_text[last:])
    return "".join(out)
