# Etapa 2 - Preprocesamiento e indexación

## Efecto acumulado de cada técnica de preprocesamiento

| Paso | Tokens | Vocabulario | Tiempo (ms) |
|---|---:|---:|---:|
| 0. Texto crudo (split por espacios) | 52,333 | 8,101 (100%) | 0.0 |
| 1. + Minúsculas | 52,333 | 7,509 (93%) | 0.5 |
| 2. + Normalizar acentos (NFD) | 52,333 | 7,508 (93%) | 16.5 |
| 3. + Quitar puntuación y especiales | 52,734 | 5,225 (64%) | 10.8 |
| 4. + Quitar stopwords | 31,637 | 5,080 (63%) | 2.1 |
| 5. + Stemming de Porter (estado del arte) | 31,637 | 3,786 (47%) | 18.5 |

## Ejemplos de stemming (raíz -> variantes agrupadas)

| Raíz | Variantes |
|---|---|
| explor | exploration, explored, exploring, explore, explores, explorations |
| interact | interact, interactives, interacted, interactions, interactive, interacts |
| orbit | orbit, orbits, orbital, orbiting, orbiter, orbiters |
| continu | continued, continue, continuously, continues, continuous, continuing |
| gener | generally, generating, generated, generates, generate, generation |
| origin | originally, origin, original, origins, originating, originate |
| investig | investigation, investigations, investigating, investigate, investigator, investigators |
| complet | complete, completion, completes, completed, completing, completely |
| observ | observing, observations, observe, observation, observed, observers |
| protect | protects, protective, protection, protecting, protected, protect |
| land | landing, landed, land, lands, landings |
| fire | firing, fired, fire, firings, fires |

## Tokenización por subpalabras (BPE) del modelo RoBERTa

- Vocabulario BPE: 50,265 subpalabras
- Tokens BPE por fragmento: promedio 129, máximo 282
- Tokens BPE por palabra: 1.29
- Fragmentos con más de 384 tokens: 0
- Ejemplo: {'magnetosphere': ['Ġmagnet', 'osphere']}

## Estructuras construidas

| Estructura | Tamaño | Construcción (s) | Memoria aprox. (MB) | Complejidad construcción | Complejidad espacio |
|---|---|---:|---:|---|---|
| Trie (vocabulario) | 4,693 palabras, 14,191 nodos (de 32,687 caracteres) | 0.003 | 3.4 | O(L) | O(L) nodos |
| Índice invertido (hash) | 3,786 términos, 24,962 pares | 0.005 | 1.8 | O(T) | O(P) ≤ O(T) |
| Arreglo de sufijos | 32,160 posiciones, 6 rondas | 0.052 | 0.7 | O(n log² n) | O(n) |

L = caracteres del vocabulario, T = tokens de la colección, P = pares (término, fragmento), n = términos de la colección.

Compresión del Trie: 14,191 nodos para 32,687 caracteres (43%), gracias a los prefijos compartidos.
