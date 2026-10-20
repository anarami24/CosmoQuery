#ETAPA 3 

class NaiveMatcher:
    #Compara el patrón contra cada posición del texto
    name = "naive"

    def __init__(self, pattern):
        self.p = pattern

    def search(self, text):
        p, m, n = self.p, len(self.p), len(text)
        out = []
        for i in range(n - m + 1):
            j = 0
            while j < m and text[i + j] == p[j]:
                j += 1
            if j == m:
                out.append(i)
        return out


def prefix_function(s):
    pi = [0] * len(s)
    j = 0
    for i in range(1, len(s)):
        while j > 0 and s[i] != s[j]:
            j = pi[j - 1]
        if s[i] == s[j]:
            j += 1
        pi[i] = j
    return pi


class KMPMatcher:
    name = "kmp"

    def __init__(self, pattern):
        self.p = pattern
        self.pi = prefix_function(pattern)   # se calcula una sola vez

    def search(self, text):
        p, pi, m = self.p, self.pi, len(self.p)
        out, j = [], 0
        for i, ch in enumerate(text):
            while j > 0 and ch != p[j]:
                j = pi[j - 1]                # salto: reutiliza lo ya comparado
            if ch == p[j]:
                j += 1
                if j == m:
                    out.append(i - m + 1)
                    j = pi[j - 1]
        return out


def z_function(s):
    n = len(s)
    z = [0] * n
    if n:
        z[0] = n
    l = r = 0
    for i in range(1, n):
        if i < r:
            z[i] = min(r - i, z[i - l])
        while i + z[i] < n and s[z[i]] == s[i + z[i]]:
            z[i] += 1
        if i + z[i] > r:
            l, r = i, i + z[i]
    return z


class ZMatcher:
   #Búsqueda con la función Z sobre  patrón + separador + texto. O(n + m)
    name = "z"
    SEP = "\x00"   # caracter que no aparece en el texto preprocesado

    def __init__(self, pattern):
        self.p = pattern

    def search(self, text):
        m = len(self.p)
        z = z_function(self.p + self.SEP + text)
        offset = m + 1
        return [i - offset for i in range(offset, len(z)) if z[i] >= m]


class RabinKarpMatcher:
    #Polynomial rolling hash:  h(s) = s0·B^(m-1) + s1·B^(m-2) + ... + s(m-1)  (mod M)

    name = "rabin_karp"
    BASE = 131
    MOD = (1 << 61) - 1       # primo de Mersenne: colisiones muy improbables

    def __init__(self, pattern):
        self.p = pattern
        self.m = len(pattern)
        h = 0
        for ch in pattern:
            h = (h * self.BASE + ord(ch)) % self.MOD
        self.hp = h
        self.high = pow(self.BASE, self.m - 1, self.MOD) if self.m else 0

    def search(self, text):
        m, n, B, M = self.m, len(text), self.BASE, self.MOD
        if m == 0 or n < m:
            return []
        h = 0
        for ch in text[:m]:
            h = (h * B + ord(ch)) % M
        out, p, hp, high = [], self.p, self.hp, self.high
        for i in range(n - m + 1):
            if h == hp and text[i:i + m] == p:      # verificación (evita falsos positivos)
                out.append(i)
            if i + m < n:
                h = ((h - ord(text[i]) * high) * B + ord(text[i + m])) % M
        return out


MATCHERS = {
    "naive": NaiveMatcher,
    "kmp": KMPMatcher,
    "z": ZMatcher,
    "rabin_karp": RabinKarpMatcher,
}

ALGORITHM_LABELS = {
    "naive": "Ingenuo (fuerza bruta)",
    "kmp": "KMP",
    "z": "Función Z",
    "rabin_karp": "Rabin-Karp (rolling hash)",
    "suffix_array": "Arreglo de sufijos",
}
