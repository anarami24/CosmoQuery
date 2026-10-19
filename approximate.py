#ETAPA 4 - Búsqueda aproximada: algoritmos de comparación de cadenas (Persona 2).

# Técnica A: distancia de edición (Levenshtein y Damerau-Levenshtein en su variante OSA) con
#   programación dinámica, y su versión recorriendo el Trie de Ana con ramificación y poda.
# Técnica B: n-gramas de caracteres + similitud de Jaccard, con una tabla hash n-grama -> palabras.
# Extra: subsecuencia común más larga (LCS) con la PD vista en clase.

# Variables usadas en las complejidades:
#   m = longitud de la palabra buscada, L = longitud de la otra palabra,
#   N = nodos del Trie, V = nodos visitados (V << N gracias a la poda),
#   |Vocab| = palabras del vocabulario, |A|, |B| = tamaño de los conjuntos de n-gramas.

import time

import config
from preprocessing import STOPWORDS
from structures import quickselect_top_k


# DISTANCIAS DE EDICIÓN (PD)
def levenshtein(a, b):
    """Distancia de Levenshtein: inserción, borrado y sustitución cuestan 1.

    Técnica: programación dinámica. D[i][j] = distancia entre a[:i] y b[:j];
    D[i][j] = min(D[i-1][j] + 1, D[i][j-1] + 1, D[i-1][j-1] + (a[i-1] != b[j-1])).
    Solo se guardan dos filas porque cada fila depende únicamente de la anterior.
    Complejidad: tiempo O(|a|·|b|), espacio O(|b|).
    """
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def osa_distance(a, b):
    """Distancia de Damerau-Levenshtein restringida (OSA, optimal string alignment).

    Igual que Levenshtein, más la transposición de dos letras adyacentes con costo 1:
    si a[i-1] == b[j-2] y a[i-2] == b[j-1], D[i][j] = min(D[i][j], D[i-2][j-2] + 1).
    Así "largset" -> "largest" cuesta 1 (Levenshtein da 2). Es "restringida" porque
    una subcadena no se edita dos veces (por eso OSA("ca", "abc") = 3 y no 2).
    Técnica: programación dinámica con tres filas (la transposición mira dos filas atrás).
    Complejidad: tiempo O(|a|·|b|), espacio O(|b|).
    """
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
    """Tabla completa de la PD (|a|+1) x (|b|+1) y las celdas donde se usó transposición.

    Sirve para mostrar la tabla en el reporte y en la GUI. Mismas recurrencias que arriba.
    Complejidad: tiempo y espacio O(|a|·|b|).
    """
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
    """Distancia máxima permitida según la longitud de la palabra (0 = no se corrige).

    Con la configuración por defecto: 1-3 letras -> 0, 4-7 -> 1, 8 o más -> 2.
    """
    rules = config.FUZZY_MAX_DIST if rules is None else rules
    min_len = config.FUZZY_MIN_LEN if min_len is None else min_len
    if length < min_len:
        return 0
    best = 0
    for min_length, dist in rules.items():
        if length >= min_length:
            best = max(best, dist)
    return best


# RECORRIDO DEL TRIE CON RAMIFICACIÓN Y PODA
def trie_fuzzy_search(trie, word, max_dist, metric="osa", exclude=None, prefix_mode=False):
    """Palabras del Trie a distancia <= max_dist de `word` (Levenshtein u OSA).

    Idea: cada nodo del Trie es un prefijo p. Al bajar por el carácter c se calcula la fila
    D[|p|][*] de la tabla de PD de p contra `word` usando solo la fila del padre (y la del
    abuelo para la transposición de OSA). Todas las palabras que comparten el prefijo p
    reutilizan esa fila: el prefijo compartido es un subproblema que se resuelve una sola vez.

    Poda (ramificación y poda): el mínimo de la fila es una cota inferior de la distancia de
    cualquier palabra del subárbol, porque bajar un nivel nunca reduce el mínimo de la fila
    (cada celda nueva viene de una celda de la fila anterior + costo >= 0, y la transposición
    D[i-2][j-2] + 1 nunca es menor que la celda D[i-1][j-1] de la fila intermedia). Si ese
    mínimo ya supera max_dist, no se expanden los hijos.

    prefix_mode=True (autocompletado tolerante a errores): se acepta un nodo cuando el último
    valor de la fila es <= max_dist, sin exigir que sea fin de palabra, y no se baja más;
    el resultado es la lista de prefijos del Trie parecidos a `word`.

    Técnica: ramificación y poda sobre el árbol de búsqueda (el Trie) + programación dinámica.
    Complejidad: peor caso O(N·m) tiempo; en la práctica O(V·m) con V nodos visitados.
    Espacio O(d·m) para la pila, con d la profundidad del Trie (longitud máxima de palabra).
    Devuelve (lista de (palabra, distancia, frecuencia) ordenada por distancia, frecuencia
    descendente y palabra; stats con nodes_visited, nodes_total y time_ms).
    """
    if metric not in METRICS:
        raise ValueError(f"Métrica desconocida: {metric}. Opciones: {list(METRICS)}")
    t0 = time.perf_counter()
    osa = metric == "osa"
    exclude = exclude or ()
    m = len(word)
    root_row = list(range(m + 1))
    found = []
    visited = 1                              # la raíz
    # Cada elemento: (nodo, carácter que llevó a él, carácter del padre, fila del padre,
    #                 fila del abuelo, profundidad, prefijo)
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
                continue                     # el resto del subárbol lo cubre el autocompletado
        elif node.is_end and row[m] <= max_dist and node.word not in exclude:
            found.append((node.word, row[m], node.freq))
        if min(row) > max_dist:
            continue                         # poda: ninguna palabra del subárbol cabe en el umbral
        for c, child in node.children.items():
            stack.append((child, c, ch, row, parent, depth + 1, prefix + c))
    found.sort(key=lambda x: (x[1], -x[2], x[0]))
    stats = {"nodes_visited": visited, "nodes_total": trie.n_nodes,
             "time_ms": (time.perf_counter() - t0) * 1000}
    return found, stats


def brute_force_fuzzy(vocab, word, max_dist, metric="osa", exclude=None):
    """Línea base sin poda: calcula la distancia contra cada palabra del vocabulario.

    `vocab` es una lista de (palabra, frecuencia), como la que devuelve Trie.words().
    Técnica: fuerza bruta + PD. Complejidad: O(|Vocab|·L·m) tiempo, O(L) espacio extra.
    """
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


# N-GRAMAS DE CARACTERES + JACCARD (HASHING)
def char_ngrams(word, n=2):
    """Conjunto de n-gramas de caracteres de `$word$` (el `$` marca inicio y fin).

    Ejemplo: char_ngrams("moon", 2) = {"$m", "mo", "oo", "on", "n$"}.
    Los marcadores hacen que la primera y la última letra cuenten (casi nunca tienen errores).
    Complejidad: O(|w|) tiempo y espacio.
    """
    padded = f"${word}$"
    if len(padded) < n:
        return {padded}
    return {padded[i:i + n] for i in range(len(padded) - n + 1)}


def jaccard(a, b):
    """Similitud de Jaccard |A ∩ B| / |A ∪ B| entre dos conjuntos (0 si ambos están vacíos).

    Técnica: hashing (los conjuntos de Python son tablas hash, la pertenencia cuesta O(1)).
    Complejidad: O(|A| + |B|) tiempo esperado.
    """
    if not a and not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def jaccard_words(a_tokens, b_tokens):
    """Jaccard entre los conjuntos de tokens de dos textos (redundancia y reordenamiento).

    Complejidad: O(|a| + |b|) tiempo esperado.
    """
    return jaccard(set(a_tokens), set(b_tokens))


class NgramIndex:
    """Tabla hash n-grama -> conjunto de palabras del vocabulario (sin stopwords).

    Construcción: O(Σ|w|) tiempo y espacio (cada palabra aporta |w| + 3 - n n-gramas).
    Consulta: O(Σ|posting|) tiempo, sumando las listas de los n-gramas de la palabra buscada.
    """

    def __init__(self, vocab, n=None, exclude=STOPWORDS):
        """`vocab`: iterable de (palabra, frecuencia), por ejemplo Trie.words()."""
        self.n = config.NGRAM_N if n is None else n
        self.table = {}
        self.freq = {}
        self.size = {}                      # número de n-gramas distintos de cada palabra
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
        """Las k palabras con mayor Jaccard (>= min_j); empate -> mayor frecuencia.

        Para no comparar conjuntos completos, se cuenta cuántos n-gramas comparte cada
        candidata recorriendo las listas de la tabla hash; con ese conteo c:
        J = c / (|A| + |B| - c). Solo se consideran palabras que comparten al menos un n-grama.
        Devuelve (lista de (palabra, jaccard, frecuencia), stats con candidates y time_ms).
        """
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
        # Top-k con el quickselect aleatorizado de Ana; desempate por frecuencia y luego por
        # orden alfabético (se invierte el orden de los caracteres para que "a" gane a "b").
        top = quickselect_top_k(scored, k, key=lambda x: (x[1], x[2], [-ord(ch) for ch in x[0]]))
        stats = {"candidates": len(shared), "time_ms": (time.perf_counter() - t0) * 1000}
        return top, stats


# SUBSECUENCIA COMÚN MÁS LARGA (LCS)
def lcs_length(a, b):
    """Longitud de la subsecuencia común más larga entre dos secuencias (cadenas o listas).

    Técnica: programación dinámica (presentación "El substring común más largo", sección de
    subsecuencia): L[i][j] = L[i-1][j-1] + 1 si a[i-1] == b[j-1], si no max(L[i-1][j], L[i][j-1]).
    Ejemplo de la diapositiva: LCS("ABCXYZAY", "BXYZABC") = 5 ("BXYZA").
    Complejidad: tiempo O(|a|·|b|), espacio O(|b|) con dos filas.
    """
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]
