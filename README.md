# CosmoQuery

Sistema de recuperación de información sobre el Sistema Solar (38 páginas de NASA, 523 fragmentos) con algoritmos clásicos de cadenas, que le da contexto a un modelo de lenguaje de Hugging Face (`deepset/roberta-base-squad2`).

Proyecto de TC2038 Análisis y diseño de algoritmos avanzados · Tecnológico de Monterrey.
Equipo: Ana Griselda Ramírez Arámburo (Persona 1, Etapas 1–3) · Camila Gómez Godínez (Persona 2, Etapas 4–6 y GUI).

## Preparación (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python index_builder.py          # genera data/index.pkl (agrega --no-bpe si no hay internet)
python -m unittest discover tests
```

La primera vez que se usa el modelo se descargan unos 500 MB; después funciona sin internet.

## Persona 2 — Búsqueda aproximada, contexto, modelo y GUI

### Aplicación (GUI con autocompletado por Trie)

```powershell
python app.py                    # abre http://127.0.0.1:7860
```

Mientras escribes la pregunta, el Trie sugiere palabras del vocabulario. Se puede elegir búsqueda exacta o aproximada y el algoritmo. La respuesta muestra las correcciones ("¿quisiste decir…?"), la oración de donde salió con las palabras de la pregunta resaltadas y el tiempo.

### Consola

```powershell
# Etapa 4: búsqueda aproximada (lev_trie, osa_trie, ngram_jaccard, hybrid) comparada con la exacta
python approx_search.py "What is the largset volcanno in the solar systme?" --compare

# Etapa 5: flujo completo pregunta -> búsqueda -> contexto -> modelo -> respuesta
python rag_pipeline.py "When was Pluto discovered?"
python rag_pipeline.py "When did Eurpoa Clipper launah?" --method exact --selection dp
```

Opciones de `rag_pipeline.py`: `--method approximate|exact`, `--alg`, `--selection greedy|dp|topk`, `--no-redundancy`, `--k`.

### Reportes y benchmark

```powershell
python etapa4_reporte.py         # results/etapa4_busqueda_aproximada.md y .json
python etapa5_reporte.py         # results/etapa5_respuestas.md, .csv y .json (24 preguntas)
python benchmark_approx.py --quick   # Etapa 6 rápida (~2 min)
python benchmark_approx.py           # Etapa 6 completa: results/etapa6_comparacion.md, etapa6_aprox_*.csv, figures/comp_*.png
```

Las respuestas del modelo del benchmark se guardan en `.cache/qa_answers.json` (ignorada por git) para no recalcularlas.

### Archivos

| Archivo | Contenido |
|---|---|
| `approximate.py` | Levenshtein, OSA (Damerau), recorrido del Trie con ramificación y poda, n-gramas, Jaccard, índice de n-gramas, LCS |
| `approx_search.py` | `ApproximateSearcher`: corrige palabras y vuelve a puntuar con BM25 + frases + cobertura |
| `context_selection.py` | Redundancia por Jaccard, mochila 0/1 voraz y con programación dinámica, armado del contexto |
| `qa_model.py` | RoBERTa con la lógica de `ask_question` del cuaderno PokeChat ("I don't know" si `score_difference` < `NO_ANSWER_THRESHOLD`) |
| `rag_pipeline.py` | `CosmoQuery.ask`: flujo completo con tiempos por etapa; el modelo lee cada fragmento elegido por separado |
| `calibrar_umbral.py`, `evaluar_respuestas.py` | Calibración del umbral de "I don't know" y evaluación de las respuestas por pregunta |
| `etapa4_reporte.py`, `etapa5_reporte.py`, `benchmark_approx.py` | Reportes de las Etapas 4, 5 y 6 |
| `app.py`, `assets/cosmoquery.css` | GUI en Gradio |
| `tests/test_approximate.py` | Pruebas contra implementaciones de referencia y fuerza bruta |

Los parámetros de Persona 2 están al final de `config.py` (búsqueda aproximada, contexto y modelo).
