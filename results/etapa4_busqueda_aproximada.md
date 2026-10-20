# Etapa 4 - Recuperación mediante búsqueda aproximada

Colección: 523 fragmentos. Vocabulario del Trie: 4,693 palabras, 14,191 nodos. Banco: preguntas de Ana + variantes con errores (`load_questions()`, semilla 42).

## Algoritmos implementados

| Algoritmo | Cómo se calcula la similitud | Técnica de diseño | Complejidad |
|---|---|---|---|
| Levenshtein + Trie (`lev_trie`) | d = mínimo de inserciones, borrados y sustituciones; peso = 1 − d / max(|w|, |c|) | PD fila por fila + ramificación y poda | O(V·m); peor caso O(N·m) |
| OSA / Damerau + Trie (`osa_trie`) | como Levenshtein, más transposición de letras adyacentes con costo 1 | PD fila por fila + ramificación y poda | O(V·m); peor caso O(N·m) |
| n-gramas + Jaccard (`ngram_jaccard`) | J = |A ∩ B| / |A ∪ B| entre los n-gramas de `$palabra$`; peso = J | hashing (tabla n-grama → palabras) | O(Σ|posting|) por palabra; construcción O(Σ|w|) |
| Híbrido (`hybrid`) | unión de candidatos de OSA y bigramas; cada uno con su mayor similitud | combinación de las anteriores | suma de ambas |

m = longitud de la palabra, N = nodos del Trie, V = nodos visitados (V ≪ N por la poda), |w| = longitud de cada palabra del vocabulario.

**Poda:** al bajar un nivel en el Trie, cada celda de la fila nueva se calcula a partir de la fila anterior más un costo ≥ 0, así que el mínimo de la fila nunca baja. Ese mínimo es una cota inferior de la distancia de cualquier palabra del subárbol: si ya supera el umbral, la rama se descarta.

**Nuevo ordenamiento:** las palabras corregidas se convierten en raíces con peso igual a su similitud. Cada fragmento se puntúa con la fórmula de la búsqueda exacta (BM25 + bono por frases con el arreglo de sufijos + factor 0.5 + cobertura), multiplicando la frecuencia de cada término por su peso y contando la cobertura por palabra de la pregunta. Después: score × (1 + β · Jaccard de trigramas pregunta–fragmento).

### Parámetros

| Parámetro | Valor | Significado |
|---|---|---|
| FUZZY_MIN_LEN | 4 | palabras más cortas no se corrigen |
| FUZZY_MAX_DIST | {4: 1, 8: 2} | longitud mínima → distancia máxima |
| FUZZY_MAX_CANDIDATES | 3 | correcciones por palabra (solo las de mejor distancia/Jaccard) |
| NGRAM_N | 2 | tamaño de los n-gramas |
| NGRAM_MIN_JACCARD | 0.45 | Jaccard mínimo para aceptar un candidato |
| JACCARD_RERANK_WEIGHT (β) | 0.1 | peso del reordenamiento por trigramas |
| BM25_K1 / BM25_B / PHRASE_WEIGHT | 1.5 / 0.75 / 1.0 | los mismos de la exacta (Ana) |

## Correcciones por palabra (12 de 67 palabras con error del banco)

Primero aparecen las palabras donde las técnicas no coinciden. ✓ = el primer candidato tiene la misma raíz que la palabra original (recupera lo mismo). Tiempo de OSA = mediana de 5 corridas; fuerza bruta = OSA contra todo el vocabulario (mediana de 3).

| Palabra | Original | OSA (d) | Levenshtein (d) | Bigramas (J) | Trigramas (J) | Nodos visitados | OSA ms | Fuerza bruta ms |
|---|---|---|---|---|---|---|---|---|
| pluot | pluto | pluto (1) ✓ | — ✗ | plummet (0.4) ✗ | pluto (0.25) ✓ | 461 / 14,191 (3.2%) | 0.56 | 30.7 |
| darf | dwarf | dwarf (1) ✓ | dwarf (1) ✓ | dwarf (0.571) ✓ | dark (0.333) ✗ | 607 / 14,191 (4.3%) | 0.71 | 24.6 |
| solr | solar | solar (1) ✓ | solar (1) ✓ | solar (0.571) ✓ | sol (0.4) ✗ | 651 / 14,191 (4.6%) | 0.69 | 25.2 |
| gaes | gases | gas (1) ✗ | gas (1) ✗ | gases (0.571) ✓ | gases (0.286) ✓ | 535 / 14,191 (3.8%) | 0.56 | 24.9 |
| graet | great | great (1) ✓ | grant (1) ✗ | grant (0.5) ✗ | gray (0.286) ✗ | 467 / 14,191 (3.3%) | 0.56 | 31.2 |
| firut | first | first (1) ✓ | first (1) ✓ | first (0.5) ✓ | fire (0.286) ✗ | 523 / 14,191 (3.7%) | 0.64 | 30.6 |
| largset | largest | largest (1) ✓ | — ✗ | largest (0.455) ✓ | large (0.333) ✗ | 665 / 14,191 (4.7%) | 1.00 | 42.7 |
| largert | largest | largest (1) ✓ | largest (1) ✓ | larger (0.667) ✗ | larger (0.625) ✗ | 667 / 14,191 (4.7%) | 1.02 | 42.7 |
| diocovered | discovered | discovered (1) ✓ | discovered (1) ✓ | discovered (0.692) ✓ | covered (0.545) ✗ | 2,343 / 14,191 (16.5%) | 4.75 | 60.5 |
| gires | gives | gives (1) ✓ | gives (1) ✓ | gives (0.5) ✓ | fires (0.429) ✗ | 509 / 14,191 (3.6%) | 0.61 | 30.7 |
| widniest | windiest | windiest (1) ✓ | windiest (2) ✓ | widest (0.6) ✗ | widest (0.4) ✗ | 2,098 / 14,191 (14.8%) | 3.62 | 48.9 |
| smallet | smallest | smaller (1) ✗ | smaller (1) ✗ | smallest (0.7) ✓ | smaller (0.556) ✗ | 498 / 14,191 (3.5%) | 0.76 | 42.4 |

**Resumen sobre las 67 palabras:** primer candidato correcto con OSA 65, Levenshtein 50, bigramas 59, trigramas 46. Nodos visitados en promedio: 1,092 (7.7% del Trie). Tiempo promedio: OSA con poda 1.84 ms contra 40.2 ms de la fuerza bruta (22× más rápido). La tabla completa está en el `.json`.

## Consultas de ejemplo (exacta KMP contra aproximada híbrida)

### 1. [typo] Q07-T: "What is the larugest volcano in the solr system?"

- Fragmentos relevantes (evidencia de Ana): [278]
- Exacta: términos ['larugest', 'volcano', 'solr', 'system']; 211 examinados; 18.99 ms
- Aproximada: términos ['largest', 'volcano', 'solar', 'sol', 'system']; 255 examinados; 9.24 ms; nodos del Trie visitados 3,239
- Correcciones: larugest -> largest (OSA d=1, peso 0.88); solr -> solar (OSA d=1, peso 0.80); solr -> sols (OSA d=1, peso 0.75); solr -> sol (OSA d=1, peso 0.75)

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 127 | 5.548 (50%) | Io Facts > Facts About Io | 278 ✓ | 18.527 (100%) | Mars Facts > The Largest Volcano |
| 2 | 278 ✓ | 4.957 (50%) | Mars Facts > The Largest Volcano | 135 | 13.038 (100%) | Juno Mission > Contents |
| 3 | 135 | 4.629 (50%) | Juno Mission > Contents | 383 | 11.713 (75%) | About the Planets > Saturn's Hexagon / Mercury Facts / Venus |
| 4 | 276 | 4.058 (50%) | Mars Facts > Surface | 118 | 9.662 (75%) | Ganymede Facts > Ganymede News / Jupiter |
| 5 | 480 | 3.916 (50%) | Venus Facts > Introduction | 402 | 9.373 (75%) | Saturn Facts > Our Solar System |

Top-1 aproximada: Mars is home to the **largest** **volcano** in the **solar** **system**, Olympus Mons. It dwarfs Earth's highest peak, Mount Everest, which rises 29,029 feet, or 8,848 meters, above the Earth's surface. Olympus Mons stands more than 25 miles (that's more than 132,000 feet, or 40 kilometers) tall from base to summit, with the base covering an area a…

✓ = fragmento relevante.

### 2. [typo] Q08-T: "What gaes make up the atmosphere of Mars?"

- Fragmentos relevantes (evidencia de Ana): [280]
- Exacta: términos ['gae', 'make', 'atmospher', 'mar']; 186 examinados; 17.23 ms
- Aproximada: términos ['gase', 'ga', 'goe', 'make', 'atmospher', 'mar']; 222 examinados; 3.63 ms; nodos del Trie visitados 535
- Correcciones: gaes -> gases (OSA d=1, peso 0.80); gaes -> gas (OSA d=1, peso 0.75); gaes -> goes (OSA d=1, peso 0.75)

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 276 | 10.239 (75%) | Mars Facts > Surface | 280 ✓ | 10.882 (75%) | Mars Facts > Atmosphere |
| 2 | 373 | 8.107 (75%) | Perseverance Mission > Mars Rock Samples: The Stories They C | 276 | 10.295 (75%) | Mars Facts > Surface |
| 3 | 272 | 6.219 (50%) | Mars Facts > Moons | 170 | 9.296 (75%) | Juno Mission > Scientific Discoveries and Results |
| 4 | 257 | 6.203 (50%) | Mars Exploration > MARS ODYSSEY / Active Mission / NASA’s Cu | 447 | 8.430 (75%) | Sun Facts > Surface |
| 5 | 280 ✓ | 6.151 (50%) | Mars Facts > Atmosphere | 373 | 8.133 (75%) | Perseverance Mission > Mars Rock Samples: The Stories They C |

Top-1 aproximada: **Mars** has a thin **atmosphere** made up mostly of carbon dioxide, nitrogen, and argon **gases**. To our eyes, the sky would be hazy and red because of suspended dust instead of the familiar blue tint we see on Earth. **Mars**' sparse **atmosphere** doesn't offer much protection from impacts by such objects as meteorites, asteroids, and comets. T…

✓ = fragmento relevante.

### 3. [typo] Q12-T: "What is the largert moon in the solar slystem?"

- Fragmentos relevantes (evidencia de Ana): [116, 117, 118, 204]
- Exacta: términos ['largert', 'moon', 'solar', 'slystem']; 308 examinados; 31.97 ms
- Aproximada: términos ['largest', 'larger', 'moon', 'solar', 'system']; 339 examinados; 9.43 ms; nodos del Trie visitados 1,164
- Correcciones: largert -> largest (OSA d=1, peso 0.86); largert -> larger (OSA d=1, peso 0.86); slystem -> system (OSA d=1, peso 0.86)

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 424 | 5.369 (50%) | Solar System Facts > Moons | 204 ✓ | 18.081 (100%) | Jupiter Facts > Moons |
| 2 | 116 ✓ | 4.723 (50%) | Ganymede Facts > Introduction | 116 ✓ | 17.754 (100%) | Ganymede Facts > Introduction |
| 3 | 204 ✓ | 4.485 (50%) | Jupiter Facts > Moons | 383 | 14.171 (75%) | About the Planets > Saturn's Hexagon / Mercury Facts / Venus |
| 4 | 79 | 4.059 (50%) | Earth Facts > Moons | 457 | 13.754 (100%) | Titan Facts > Facts About Titan |
| 5 | 457 | 3.717 (50%) | Titan Facts > Facts About Titan | 167 | 13.720 (100%) | Juno Mission > The Science Mission |

Top-1 aproximada: With four large **moons** and many smaller **moons**, Jupiter forms a kind of miniature **solar** **system**. Jupiter has 115 **moons** that are officially recognized by the International Astronomical Union. The four **largest** **moons** – Io, Europa, Ganymede, and Callisto – were first observed by the astronomer Galileo Galilei in 1610 using an e…

✓ = fragmento relevante.

### 4. [literal] Q01: "When was Pluto discovered?"

- Fragmentos relevantes (evidencia de Ana): [386, 389]
- Exacta: términos ['pluto', 'discov']; 98 examinados; 8.06 ms
- Aproximada: términos ['pluto', 'discov']; 98 examinados; 1.01 ms; nodos del Trie visitados 0
- Correcciones: ninguna

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 240 | 9.559 (100%) | Kuiper Belt Facts > Pluto's Place in the Kuiper Belt | 240 | 9.586 (100%) | Kuiper Belt Facts > Pluto's Place in the Kuiper Belt |
| 2 | 386 ✓ | 9.524 (100%) | Pluto Facts > Introduction | 386 ✓ | 9.552 (100%) | Pluto Facts > Introduction |
| 3 | 389 ✓ | 8.915 (100%) | Pluto Facts > Namesake | 389 ✓ | 8.938 (100%) | Pluto Facts > Namesake |
| 4 | 47 | 6.505 (100%) | Ceres Facts > Introduction / Namesake | 47 | 6.524 (100%) | Ceres Facts > Introduction / Namesake |
| 5 | 395 | 4.718 (50%) | Pluto Facts > Moons | 395 | 4.730 (50%) | Pluto Facts > Moons |

Top-1 aproximada: In 1930, **Pluto** became the first Kuiper Belt object to be **discovered**. It was found at a time before astronomers had reason to expect a large population of icy worlds beyond Neptune. Today it's known as the "King of the Kuiper Belt" – and it's the largest object in the region, even though another object similar in size, called Eris, has a sli…

✓ = fragmento relevante.

### 5. [paraphrase] Q43: "Which world circles closest to our star?"

- Fragmentos relevantes (evidencia de Ana): [284, 383, 427]
- Exacta: términos ['world', 'circl', 'closest', 'star']; 113 examinados; 17.99 ms
- Aproximada: términos ['world', 'circl', 'closest', 'star']; 113 examinados; 1.63 ms; nodos del Trie visitados 0
- Correcciones: ninguna

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 195 | 9.943 (75%) | Juno Mission > Juno's Io Encounters | 195 | 9.991 (75%) | Juno Mission > Juno's Io Encounters |
| 2 | 196 | 6.482 (50%) | Juno Mission > Juno's Io Encounters | 196 | 6.517 (50%) | Juno Mission > Juno's Io Encounters |
| 3 | 420 | 6.412 (50%) | Solar System Facts > Namesake / Potential for Life | 420 | 6.453 (50%) | Solar System Facts > Namesake / Potential for Life |
| 4 | 167 | 5.861 (50%) | Juno Mission > The Science Mission | 167 | 5.884 (50%) | Juno Mission > The Science Mission |
| 5 | 116 | 5.801 (50%) | Ganymede Facts > Introduction | 116 | 5.832 (50%) | Ganymede Facts > Introduction |

Top-1 aproximada: Io is caught in a tug-of-war between Jupiter's powerful gravity and the smaller pull from two neighboring moons, churning its insides and creating eruptions and lakes of lava that cover its surface. Meanwhile, the gravitational pull Io exerted on Juno during the Feb. 3 flyby has reduced the spacecraft’s orbit around Jupiter to 33 days. It originall…

✓ = fragmento relevante.

### 6. [no_answer] Q51: "How many people live on Mars today?"

- Fragmentos relevantes (evidencia de Ana): ninguno (sin respuesta en la colección)
- Exacta: términos ['peopl', 'live', 'mar', 'todai']; 116 examinados; 12.58 ms
- Aproximada: términos ['peopl', 'live', 'mar', 'todai']; 116 examinados; 0.85 ms; nodos del Trie visitados 0
- Correcciones: ninguna

| # | Exacta: id | puntaje (cobertura) | documento > sección | Aproximada: id | puntaje (cobertura) | documento > sección |
|---|---|---|---|---|---|---|
| 1 | 26 | 11.254 (75%) | Asteroid Facts > Large Asteroids Have Hit Earth in the Past | 26 | 11.288 (75%) | Asteroid Facts > Large Asteroids Have Hit Earth in the Past |
| 2 | 279 | 9.598 (50%) | Mars Facts > Water on Mars | 279 | 9.637 (50%) | Mars Facts > Water on Mars |
| 3 | 48 | 8.622 (50%) | Ceres Facts > Potential for Life | 48 | 8.664 (50%) | Ceres Facts > Potential for Life |
| 4 | 268 | 8.316 (50%) | Mars Facts > Potential for Life | 268 | 8.378 (50%) | Mars Facts > Potential for Life |
| 5 | 248 | 7.118 (50%) | Mars Exploration > Perseverance, On a Roll | 248 | 7.172 (50%) | Mars Exploration > Perseverance, On a Roll |

Top-1 aproximada: A house-sized asteroid exploded over Chelyabinsk, Russia, on Feb.15, 2013. The explosion released the energy equivalent to about 440,000 tons of TNT, generating a shock wave that damaged some buildings and blew out windows across 200 square miles. Hundreds of **people** were injured in the blast, mostly due to the broken glass. Another impact site,…

✓ = fragmento relevante.

## Tiempo y calidad por técnica (106 preguntas, mediana de 5 corridas por pregunta)

| Técnica | ms prom. | ms mediana | Examinados | Hit@5 literal | Hit@5 paráfrasis | Hit@5 typo | Hit@5 global | MRR global |
|---|---|---|---|---|---|---|---|---|
| KMP (exacta, línea base) | 13.892 | 11.060 | 166.9 | 0.952 | 0.375 | 0.640 | 0.750 | 0.627 |
| Levenshtein + Trie con poda | 2.220 | 1.389 | 185.5 | 0.952 | 0.375 | 0.780 | 0.820 | 0.735 |
| OSA (Damerau) + Trie con poda | 2.485 | 1.488 | 191.6 | 0.952 | 0.375 | 0.860 | 0.860 | 0.773 |
| n-gramas + Jaccard | 1.234 | 1.047 | 185.0 | 0.952 | 0.375 | 0.780 | 0.820 | 0.721 |
| Híbrido (OSA + n-gramas) | 2.692 | 1.662 | 191.7 | 0.952 | 0.375 | 0.860 | 0.860 | 0.773 |

La comparación completa (Hit@1/3, P@5, por categoría, escalabilidad y ablaciones) está en `results/etapa6_comparacion.md`.

## Cuándo la búsqueda aproximada introduce coincidencias poco útiles

### Ruido real en el banco de preguntas

Correcciones de la búsqueda híbrida que no recuperan la palabra original. "Hit@5" indica si algún fragmento relevante quedó en el top-5 de cada método para esa pregunta.

| Pregunta | Palabra | Original | Tipo | Candidatos usados | Hit@5 exacta | Hit@5 aproximada |
|---|---|---|---|---|---|---|
| Q47-T | rages | rages | palabra correcta fuera del vocabulario | rages -> ranges (OSA d=1, peso 0.83); rages -> ages (OSA d=1, peso 0.80); rages -> rates (OSA d=1, peso 0.80) | sí | sí |
| Q49-T | ringed | ringed | palabra correcta fuera del vocabulario | ringed -> ranged (OSA d=1, peso 0.83); ringed -> hinged (OSA d=1, peso 0.83) | sí | sí |

Además, de 72 palabras corregidas en las variantes con errores, 17 incluyen la corrección buena **y** otros candidatos con la misma distancia, que también suman puntaje (con peso menor). Ejemplos: darf -> dwarf, dark, dart; lagest -> largest, latest; moos -> moons, moon, mons; solr -> solar, sols, sol; gaes -> gases, gas, goes; graet -> great, grant.

### Si se apagan las reglas (corregir palabras cortas o que ya existen)

Vecinos a distancia OSA 1 de palabras de la pregunta que hoy no se corrigen (son cortas o ya están en el vocabulario). Con las reglas activas ninguno de estos candidatos entra a la búsqueda.

| Palabra | ¿En el vocabulario? | Vecinos a d = 1 | Cuántos | De ellos, stopwords |
|---|---|---|---|---|
| age | sí | are, ago, page, ages | 4 | are |
| day | sí | may, days, way, dry, ray, bay, say | 7 | — |
| far | sí | for, war, afar, car, fan, mar | 6 | for |
| fly | sí | — | 0 | — |
| icy | sí | ice, ic | 2 | — |
| led | sí | red, lead, le, let | 4 | let |
| new | sí | now, few, neo, news, knew | 5 | now, few |
| old | sí | cold, hold, gold, fold, odd | 5 | — |
| one | sí | on, once, zone, none, ones, done, gone, tone | 8 | on, once |
| red | sí | re, led, read, fred, rex | 5 | re |
| sun | sí | run, gun, san, son, suv, spun | 6 | — |
| two | sí | to, too | 2 | to, too |
| moon | sí | moons, soon, noon | 3 | — |
| mars | sí | mass, maps, mark, ears, mar, marks | 6 | — |
| rings | sí | ring, brings | 2 | — |
