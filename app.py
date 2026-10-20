#GUI - interfaz de CosmoQuery con Gradio (python app.py -> http://127.0.0.1:7860)

import html
import os
import time

if __name__ == "__main__":
    print("Iniciando CosmoQuery… cargando bibliotecas (la primera vez puede tardar unos minutos)", flush=True)

import gradio as gr

import config
from approx_search import ALGORITHM_LABELS as APPROX_LABELS
from approximate import char_ngrams, edit_distance_table, jaccard, max_edit_distance, trie_fuzzy_search
from exact_search import ALGORITHMS as EXACT_ALGORITHMS
from preprocessing import STOPWORDS, highlight
from string_matching import ALGORITHM_LABELS as EXACT_LABELS

CSS_FILE = config.BASE_DIR / "assets" / "cosmoquery.css"
N_SUGGESTIONS = 6
SD_SCALE = 15.0      # tope de la barra de confianza
PORT = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
METHOD_CHOICES = [("Aproximada", "approximate"), ("Exacta", "exact")]
ALG_CHOICES = {
    "approximate": [(APPROX_LABELS[a], a) for a in ("hybrid", "osa_trie", "ngram_jaccard", "lev_trie")],
    "exact": [(EXACT_LABELS[a], a) for a in EXACT_ALGORITHMS],
}
DEFAULT_ALG = {"approximate": "hybrid", "exact": "kmp"}
STRATEGY_CHOICES = [("Voraz (densidad valor/peso)", "greedy"), ("PD (mochila óptima)", "dp"),
                    ("Top-k (k = 3, sin presupuesto)", "topk")]
# del banco de Ana: 2 literales, 2 con errores, 1 paráfrasis y 1 sin respuesta
EXAMPLE_IDS = ["Q01", "Q11", "Q11-T", "Q31-T", "Q43", "Q51"]
FIGURE_TITLES = {
    "comp_hit5_categorias": "Hit@5 por tipo de pregunta: exacta contra aproximada",
    "comp_tiempo": "Tiempo de búsqueda por método",
    "comp_poda": "Poda en el Trie: nodos visitados por palabra",
    "comp_escalabilidad": "Tiempo contra tamaño de la colección y del vocabulario",
    "comp_contexto_f1": "F1 según la estrategia de contexto",
    "comp_umbral": "Umbral de \"I don't know\"",
    "exacta_tiempo_algoritmos": "Búsqueda exacta: tiempo por algoritmo (Ana)",
    "exacta_escalabilidad": "Búsqueda exacta: escalabilidad (Ana)",
    "exacta_peor_caso": "Búsqueda exacta: peor caso (Ana)",
    "exacta_calidad_categorias": "Búsqueda exacta: calidad por categoría (Ana)",
}


class App:
    """Estado compartido: índice, buscadores, selector y modelo cargados una sola vez."""

    def __init__(self):
        from evaluation import load_questions
        from rag_pipeline import CosmoQuery
        print("Cargando índice…", flush=True)
        from index_builder import load_index
        index = load_index()
        print("Cargando modelo de lenguaje (la primera vez se descarga, ~500 MB)…", flush=True)
        self.cq = CosmoQuery(index)
        self.index = index
        self.pp = index.preprocessor
        self.trie = index.trie
        self.cq.approx.ngram_index()
        qs = {q["id"]: q for q in load_questions()}
        self.examples = [qs[i]["question"] for i in EXAMPLE_IDS if i in qs]
        print(f"Listo. Abre http://127.0.0.1:{PORT} en el navegador.", flush=True)


APP = None


def esc(x):
    return html.escape(str(x))


def marked(text, terms):
    """Resalta los términos (por raíz, con `highlight` de Ana) con <mark>, escapando el resto."""
    s = highlight(text, terms, "\x01", "\x02")
    return esc(s).replace("\x01", "<mark>").replace("\x02", "</mark>")


def card(title, body):
    return f'<div class="cq-card"><h3>{esc(title)}</h3>{body}</div>'


def chunk_card(c, terms, meta, badge="", cls="", why="", limit=None):
    text = c["text"] if limit is None or len(c["text"]) <= limit else c["text"][:limit] + "…"
    return (f'<div class="cq-chunk {cls}"><div class="cq-chunk-head"><span class="cq-doc">'
            f'{esc(c["doc"])} › {esc(c["section"])}{badge}</span><span class="cq-meta">{meta}</span></div>'
            f'<div class="cq-chunk-text">{marked(text, terms)}</div>'
            + (f'<div class="cq-why">{esc(why)}</div>' if why else "") + "</div>")


def correction_text(c):
    if "distance" in c:
        return f'{c["technique"].upper()} d={c["distance"]}'
    return f'Jaccard {c["jaccard"]:.2f}'


# Autocompletado
def current_prefix(text):
    """Palabra incompleta al final del texto, normalizada como la colección."""
    if not text or text[-1].isspace():
        return ""
    tokens = APP.pp.normalize(text.split()[-1]).split()
    return tokens[-1] if tokens else ""


def suggest(text):
    """Sugerencias del Trie para la palabra que se está escribiendo (evento de entrada)."""
    prefix = current_prefix(text)
    trie = APP.trie
    info = f"Autocompletado con Trie · {len(trie):,} palabras · {trie.n_nodes:,} nodos"
    if len(prefix) < 2:
        return gr.Dataset(samples=[], visible=False), f'<div class="cq-trie-info">{info}</div>'
    t0 = time.perf_counter()
    keep_stop = prefix in STOPWORDS
    words = [w for w in trie.autocomplete(prefix, k=N_SUGGESTIONS * 4)
             if (keep_stop or w not in STOPWORDS) and w != prefix][:N_SUGGESTIONS]
    labels = [f"{w} · {trie.frequency(w)}" for w in words]
    fuzzy = False
    if not words and len(prefix) >= 3:
        # si no hay nada, se buscan prefijos parecidos (OSA <= 1)
        prefixes, _ = trie_fuzzy_search(trie, prefix, 1, "osa", prefix_mode=True)
        cands = {}
        for p, d, _ in sorted(prefixes, key=lambda x: (x[1], -len(x[0]))):
            for w in trie.autocomplete(p, k=4):
                if w not in STOPWORDS and w not in cands:
                    cands[w] = (d, -trie.frequency(w))
        words = sorted(cands, key=lambda w: cands[w])[:N_SUGGESTIONS]
        labels = [f"¿{w}? · {trie.frequency(w)}" for w in words]
        fuzzy = bool(words)
    ms = (time.perf_counter() - t0) * 1000
    extra = " · ¿quisiste decir…? (prefijo a distancia OSA 1)" if fuzzy else ""
    return (gr.Dataset(samples=[[l] for l in labels], visible=bool(labels)),
            f'<div class="cq-trie-info">{info} · prefijo «{esc(prefix)}» · {ms:.2f} ms{extra}</div>')


def apply_suggestion(sample, text):
    """Reemplaza la palabra incompleta por la sugerencia elegida y agrega un espacio."""
    if not sample:
        return gr.update()
    label = sample[0] if isinstance(sample, (list, tuple)) else str(sample)
    word = label.split(" · ")[0].strip("¿?")
    text = text or ""
    base = text if not text or text[-1].isspace() else text[:len(text) - len(text.split()[-1])]
    return base + word + " "


# Pestaña Pregunta
def run_question(question, method, algorithm, strategy, redundancy):
    question = (question or "").strip()
    if not question:
        msg = card("Respuesta", '<div class="cq-empty">Escribe una pregunta en inglés sobre el Sistema Solar.</div>')
        return msg, "", "", "", "", ""
    try:
        k = 3 if strategy == "topk" else None
        r = APP.cq.ask(question, method, algorithm, strategy, redundancy, k)
    except Exception as e:                                   # la GUI nunca debe tronar
        err = card("Error", f'<div class="cq-empty">No se pudo responder: {esc(e)}</div>')
        return err, "", "", "", "", ""
    return (answer_html(r), corrections_html(r), terms_html(r), budget_html(r), times_html(r), chunks_html(r))


def answer_html(r):
    chunks = APP.index.chunks
    if not r.search.results:
        body = ('<div class="cq-answer cq-idk">No encontré fragmentos con esas palabras.</div>'
                '<div class="cq-muted">Revisa la ortografía o prueba con la búsqueda aproximada.</div>')
        return card("Respuesta", body)
    sd = r.score_difference if r.score_difference not in (float("inf"), float("-inf")) else 0.0
    pct = max(0.0, min(1.0, sd / SD_SCALE)) * 100
    tick = config.NO_ANSWER_THRESHOLD / SD_SCALE * 100
    bar = (f'<div class="cq-bar"><div class="cq-bar-fill {"cq-low" if r.is_no_answer else ""}" '
           f'style="width:{pct:.1f}%"></div><div class="cq-bar-tick" style="left:{tick:.1f}%"></div></div>'
           f'<div class="cq-bar-legend"><span>confianza (score_difference) = {sd:.2f}</span>'
           f'<span>umbral del PokeChat = {config.NO_ANSWER_THRESHOLD:g}</span></div>')
    if r.is_no_answer:
        raw = r.extra.get("raw_answer", "")
        hint = (f' El modelo consideró «{esc(raw)}», pero con una confianza menor al umbral.' if raw else "")
        body = ('<div class="cq-answer cq-idk">I don\'t know</div>'
                f'<div class="cq-muted">No encontré evidencia suficiente en los fragmentos recuperados.{hint}</div>'
                + bar)
        return card("Respuesta", body)
    body = f'<div class="cq-answer">{esc(r.answer)}</div>' + bar
    if r.source_chunk_id is not None and r.answer_span:
        c = chunks[r.source_chunk_id]
        text, (a, b) = c["text"], r.answer_span
        start = max(text.rfind(". ", 0, a) + 2, 0) if text.rfind(". ", 0, a) >= 0 else 0
        end = text.find(". ", b)
        end = len(text) if end < 0 else end + 1
        sentence = (esc(text[start:a]) + f'<span class="cq-answer-hl">{esc(text[a:b])}</span>' + esc(text[b:end]))
        body += (f'<div class="cq-source" style="margin-top:12px">Fuente: <b>{esc(c["doc"])} › {esc(c["section"])}</b>'
                 f' · fragmento {r.source_chunk_id}</div><div class="cq-sentence">{sentence}</div>')
    return card("Respuesta", body)


def corrections_html(r):
    fixes = r.search.details.get("corrections", [])
    if r.method == "exact":
        return card("¿Quisiste decir…?", '<div class="cq-empty">La búsqueda exacta no corrige palabras.</div>')
    if not fixes:
        unmatched = r.search.details.get("unmatched_words", [])
        msg = "Todas las palabras existen en el vocabulario." if not unmatched else \
            f"Sin correcciones. Palabras sin coincidencias: {', '.join(unmatched)}."
        return card("¿Quisiste decir…?", f'<div class="cq-empty">{esc(msg)}</div>')
    rows = "".join(f'<div class="cq-fix"><span class="cq-from">{esc(c["query_word"])}</span> → '
                   f'<span class="cq-to">{esc(c["candidate"])}</span> <span class="cq-muted">· {esc(correction_text(c))}'
                   f' · peso {c["weight"]:.2f}</span></div>' for c in fixes)
    d = r.search.details
    rows += (f'<div class="cq-muted" style="font-size:12px;margin-top:6px">Recorrido del Trie con poda: '
             f'{d.get("nodes_visited", 0):,} nodos visitados de {d.get("nodes_total", 0):,}.</div>')
    return card("¿Quisiste decir…?", rows)


def terms_html(r):
    terms = "".join(f'<span class="cq-chip">{esc(t)}</span>' for t in r.search.terms)
    phrases = "".join(f'<span class="cq-chip cq-phrase">{esc(p)}</span>' for p in r.search.patterns if " " in p)
    body = f'<div class="cq-chips">{terms}{phrases}</div>' if terms else '<div class="cq-empty">Sin términos.</div>'
    return card("Términos y patrones buscados (raíces y frases)", body)


def budget_html(r):
    total = config.MODEL_MAX_TOKENS
    q = r.tokens_question + APP.cq.selector.special_tokens
    c = r.tokens_context
    used = q + c
    free = max(0, total - used)
    over = max(0, used - total)
    scale = max(total, used)
    seg = lambda cls, n: f'<div class="{cls}" style="width:{100 * n / scale:.2f}%"></div>' if n > 0 else ""
    note = (f'<div class="cq-why">La entrada excede {total} tokens: el modelo la trunca '
            f'({over} tokens se pierden). Las estrategias con presupuesto evitan esto.</div>' if over else "")
    body = (f'<div class="cq-budget">{seg("cq-seg-q", q)}{seg("cq-seg-c", c - over)}{seg("cq-seg-x", over)}{seg("cq-seg-f", free)}</div>'
            f'<div class="cq-legend"><span><i class="cq-seg-q"></i>pregunta + especiales {q}</span>'
            f'<span><i class="cq-seg-c"></i>contexto {c}</span><span><i class="cq-seg-f"></i>libre {free}</span>'
            f'<span>presupuesto del contexto W = {r.token_budget}</span><span>total {used} / {total}</span></div>{note}')
    return card("Presupuesto de tokens del modelo", body)


def times_html(r):
    s = r.search
    stats = [("búsqueda", f"{r.t_search_ms:.1f} ms"), ("selección", f"{r.t_select_ms:.1f} ms"),
             ("modelo", f"{r.t_model_ms:.0f} ms"), ("total", f"{r.t_total_ms:.0f} ms"),
             ("examinados", f"{s.n_examined:,} / {s.n_total:,}"), ("con coincidencias", f"{s.n_matched:,}")]
    body = '<div class="cq-stats">' + "".join(
        f'<div class="cq-stat"><div class="cq-v">{v}</div><div class="cq-l">{esc(l)}</div></div>' for l, v in stats) + "</div>"
    return card("Tiempos", body)


def chunks_html(r):
    chunks = APP.index.chunks
    weights = r.extra.get("weights", {})
    out = []
    for i, s in enumerate(r.selected, 1):
        src = s.chunk_id == r.source_chunk_id
        meta = (f"#{i} · score {s.score:.2f} · cobertura {s.coverage:.0%} · {weights.get(s.chunk_id, '?')} tokens")
        out.append(chunk_card(chunks[s.chunk_id], r.search.terms, meta,
                              badge='<span class="cq-badge">respuesta</span>' if src else "",
                              cls="cq-src" if src else ""))
    for cid, why in r.discarded:
        out.append(chunk_card(chunks[cid], r.search.terms, f"fragmento {cid}", cls="cq-off", why=f"Descartado: {why}",
                              limit=260))
    if not out:
        return card("Fragmentos seleccionados como contexto", '<div class="cq-empty">Ninguno.</div>')
    return card(f"Fragmentos seleccionados como contexto ({len(r.selected)}) y descartados ({len(r.discarded)})",
                "".join(out))


# Pestaña Exacta vs aproximada
def run_compare(question, strategy, redundancy):
    question = (question or "").strip()
    if not question:
        return '<div class="cq-empty">Escribe una pregunta arriba y presiona Preguntar.</div>'
    try:
        k = 3 if strategy == "topk" else None
        ex = APP.cq.ask(question, "exact", "kmp", strategy, redundancy, k)
        ap = APP.cq.ask(question, "approximate", "hybrid", strategy, redundancy, k)
    except Exception as e:
        return f'<div class="cq-empty">No se pudo comparar: {esc(e)}</div>'
    ids_e = set(ex.search.ids()[:config.TOP_K])
    ids_a = set(ap.search.ids()[:config.TOP_K])
    cols = []
    for r, title, other in ((ex, "Exacta · KMP + índice invertido", ids_a), (ap, "Aproximada · híbrida (OSA + n-gramas)", ids_e)):
        head = (f'<div class="cq-stats" style="margin-bottom:10px">'
                f'<div class="cq-stat"><div class="cq-v">{r.search.time_ms:.2f} ms</div><div class="cq-l">búsqueda</div></div>'
                f'<div class="cq-stat"><div class="cq-v">{r.search.n_examined}</div><div class="cq-l">examinados</div></div>'
                f'<div class="cq-stat"><div class="cq-v">{r.search.n_matched}</div><div class="cq-l">con coincidencias</div></div></div>')
        ans = esc(r.answer) if not r.is_no_answer else "I don't know"
        head += (f'<div class="cq-muted" style="font-size:13px">Respuesta del modelo</div>'
                 f'<div class="cq-answer{" cq-idk" if r.is_no_answer else ""}" style="font-size:20px">{ans}</div>'
                 f'<div class="cq-muted" style="font-size:12px;margin-bottom:8px">score_difference {r.score_difference:.2f}'
                 f' · términos: {esc(", ".join(r.search.terms))}</div>')
        fixes = r.search.details.get("corrections", [])
        if fixes:
            head += '<div class="cq-chips" style="margin-bottom:8px">' + "".join(
                f'<span class="cq-chip">{esc(c["query_word"])} → <b>{esc(c["candidate"])}</b></span>' for c in fixes) + "</div>"
        items = []
        for rank, s in enumerate(r.search.results[:config.TOP_K], 1):
            both = '<span class="cq-badge cq-both">en ambos</span>' if s.chunk_id in other else ""
            items.append(chunk_card(APP.index.chunks[s.chunk_id], r.search.terms,
                                    f"#{rank} · score {s.score:.2f} · cobertura {s.coverage:.0%}", badge=both, limit=320))
        body = head + ("".join(items) or '<div class="cq-empty">Sin resultados.</div>')
        cols.append(card(title, body))
    return f'<div class="cq-compare">{"".join(cols)}</div>'


# Pestaña Laboratorio
def run_lab_word(word):
    word = APP.pp.normalize(word or "").replace(" ", "")
    if not word:
        return '<div class="cq-empty">Escribe una palabra (por ejemplo, largset o jupitr).</div>'
    k = max(1, max_edit_distance(len(word)))
    found, stats = trie_fuzzy_search(APP.trie, word, k, "osa", STOPWORDS)
    rows = "".join(f"<tr><td>{esc(w)}</td><td>{d}</td><td>{f:,}</td></tr>" for w, d, f in found[:10])
    pct = 100 * stats["nodes_visited"] / stats["nodes_total"]
    out = [card(f"OSA sobre el Trie con poda (distancia ≤ {k})",
                f'<div class="cq-muted" style="margin-bottom:8px">{stats["nodes_visited"]:,} nodos visitados de '
                f'{stats["nodes_total"]:,} ({pct:.1f}%) · {stats["time_ms"]:.2f} ms</div>'
                + (f'<table class="cq-table"><tr><th>Palabra</th><th>Distancia</th><th>Frecuencia</th></tr>{rows}</table>'
                   if rows else '<div class="cq-empty">Ninguna palabra del vocabulario dentro del umbral.</div>'))]
    if found:
        best = found[0][0]
        D, swaps = edit_distance_table(word, best, "osa")
        swaps = set(swaps)
        head = "<tr><th></th><th>ε</th>" + "".join(f"<th>{esc(ch)}</th>" for ch in best) + "</tr>"
        body = ""
        for i in range(len(word) + 1):
            body += f"<tr><th>{'ε' if i == 0 else esc(word[i - 1])}</th>"
            for j in range(len(best) + 1):
                cls = "cq-swap" if (i, j) in swaps else ("cq-final" if (i, j) == (len(word), len(best)) else "")
                body += f'<td class="{cls}">{D[i][j]}</td>'
            body += "</tr>"
        out.append(card(f"Tabla de PD: «{word}» contra «{best}»",
                        f'<table class="cq-dp">{head}{body}</table><div class="cq-legend" style="margin-top:8px">'
                        f'<span><i style="background:#fff176"></i>se usó la transposición</span>'
                        f'<span>distancia final = {D[-1][-1]}</span></div>'))
        ga, gb = char_ngrams(word, 2), char_ngrams(best, 2)
        chips = lambda gs, other: "".join(f'<span class="cq-chip cq-gram {"cq-shared" if g in other else ""}">{esc(g)}</span>'
                                          for g in sorted(gs))
        out.append(card(f"Bigramas y Jaccard: J = |A ∩ B| / |A ∪ B| = {len(ga & gb)} / {len(ga | gb)} = {jaccard(ga, gb):.2f}",
                        f'<div class="cq-muted">«{esc(word)}»</div><div class="cq-chips" style="margin:4px 0 10px">{chips(ga, gb)}</div>'
                        f'<div class="cq-muted">«{esc(best)}»</div><div class="cq-chips" style="margin-top:4px">{chips(gb, ga)}</div>'))
    return "".join(out)


def run_lab_prefix(prefix):
    prefix = APP.pp.normalize(prefix or "").replace(" ", "")
    if not prefix:
        return '<div class="cq-empty">Escribe un prefijo (por ejemplo, jup o perse).</div>'
    node = APP.trie.root
    for ch in prefix:
        node = node.children.get(ch)
        if node is None:
            return card("Autocompletado", f'<div class="cq-empty">Ninguna palabra empieza con «{esc(prefix)}».</div>')
    n_nodes = n_words = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        n_nodes += 1
        n_words += cur.is_end
        stack.extend(cur.children.values())
    t0 = time.perf_counter()
    words = APP.trie.autocomplete(prefix, k=10)
    ms = (time.perf_counter() - t0) * 1000
    rows = "".join(f"<tr><td>{esc(w)}</td><td>{APP.trie.frequency(w):,}</td></tr>" for w in words)
    return card(f"Autocompletado de «{prefix}»",
                f'<div class="cq-muted" style="margin-bottom:8px">Subárbol: {n_nodes:,} nodos y {n_words:,} palabras · '
                f'top-10 por frecuencia con un heap en {ms:.2f} ms</div>'
                f'<table class="cq-table"><tr><th>Palabra</th><th>Frecuencia</th></tr>{rows}</table>')


def figure_items():
    items = []
    for stem, title in FIGURE_TITLES.items():
        path = config.FIGURES_DIR / f"{stem}.png"
        if path.exists():
            items.append((str(path), title))
    return items


def build_ui():
    with gr.Blocks(title="CosmoQuery") as demo:
        gr.HTML('<div class="cq-header"><h1>CosmoQuery</h1>'
                '<p>Asistente del Sistema Solar con recuperación por algoritmos de cadenas · TC2038</p>'
                '<p class="cq-credits">Ana Griselda Ramírez Arámburo · Camila Gómez Godínez</p></div>')
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                question = gr.Textbox(label="Pregunta (en inglés)", placeholder="What is the largest volcano on Mars?",
                                      lines=1, max_lines=2, elem_id="cq-question", autofocus=True)
                suggestions = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[], label="Sugerencias",
                                         show_label=False, elem_id="cq-suggestions", type="values", layout="gallery",
                                         visible=False, samples_per_page=N_SUGGESTIONS)
                trie_info = gr.HTML(f'<div class="cq-trie-info">Autocompletado con Trie · {len(APP.trie):,} palabras · '
                                    f'{APP.trie.n_nodes:,} nodos</div>')
                examples = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[[q] for q in APP.examples],
                                      label="Preguntas de ejemplo", elem_id="cq-examples", type="values",
                                      layout="gallery")
            with gr.Column(scale=2):
                with gr.Row():
                    method = gr.Radio(METHOD_CHOICES, value="approximate", label="Método de búsqueda")
                    algorithm = gr.Dropdown(ALG_CHOICES["approximate"], value="hybrid", label="Algoritmo")
                with gr.Row():
                    strategy = gr.Radio(STRATEGY_CHOICES, value="greedy", label="Selección del contexto")
                    redundancy = gr.Checkbox(value=True, label="Eliminar redundancia")
                ask = gr.Button("Preguntar", variant="primary")

        with gr.Tabs():
            with gr.Tab("Pregunta"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=5):
                        out_answer = gr.HTML()
                        out_fixes = gr.HTML()
                        out_terms = gr.HTML()
                        out_budget = gr.HTML()
                        out_times = gr.HTML()
                    with gr.Column(scale=6):
                        out_chunks = gr.HTML()
            with gr.Tab("Exacta vs aproximada"):
                out_compare = gr.HTML('<div class="cq-empty">Haz una pregunta para comparar los dos métodos.</div>')
            with gr.Tab("Laboratorio de cadenas"):
                with gr.Row(equal_height=False):
                    with gr.Column():
                        lab_word = gr.Textbox(label="Palabra (búsqueda aproximada)", value="largset")
                        lab_word_out = gr.HTML()
                    with gr.Column():
                        lab_prefix = gr.Textbox(label="Prefijo (autocompletado)", value="perse")
                        lab_prefix_out = gr.HTML()
            with gr.Tab("Resultados"):
                items = figure_items()
                if items:
                    gr.Gallery(value=items, columns=2, height="auto", object_fit="contain", show_label=False)
                else:
                    gr.HTML('<div class="cq-empty">Aún no hay figuras. Ejecuta benchmark_approx.py y benchmark_exact.py.</div>')

        # el autocompletado corre en cada tecla; always_last evita que se encolen llamadas
        question.input(suggest, question, [suggestions, trie_info], show_progress="hidden",
                       trigger_mode="always_last", queue=False)
        suggestions.click(apply_suggestion, [suggestions, question], question, show_progress="hidden", queue=False) \
            .then(suggest, question, [suggestions, trie_info], show_progress="hidden", queue=False) \
            .then(None, js="() => { const t = document.querySelector('#cq-question textarea'); if (t) t.focus(); }")
        examples.click(lambda s: s[0] if s else "", examples, question, show_progress="hidden", queue=False)
        method.change(lambda m: gr.Dropdown(choices=ALG_CHOICES[m], value=DEFAULT_ALG[m]), method, algorithm,
                      queue=False)

        outputs = [out_answer, out_fixes, out_terms, out_budget, out_times, out_chunks]
        for trigger in (ask.click, question.submit):
            trigger(run_question, [question, method, algorithm, strategy, redundancy], outputs) \
                .then(run_compare, [question, strategy, redundancy], out_compare)
        lab_word.submit(run_lab_word, lab_word, lab_word_out)
        lab_word.change(run_lab_word, lab_word, lab_word_out, show_progress="hidden", trigger_mode="always_last")
        lab_prefix.change(run_lab_prefix, lab_prefix, lab_prefix_out, show_progress="hidden", trigger_mode="always_last")
        demo.load(run_lab_word, lab_word, lab_word_out).then(run_lab_prefix, lab_prefix, lab_prefix_out)
    return demo


def theme():
    # Tema claro de Gradio con fuentes del sistema; se usa igual aunque el navegador esté en modo oscuro
    colors = dict(body_background_fill="#ffffff", body_text_color="#222222", block_background_fill="#ffffff",
                  background_fill_primary="#ffffff", background_fill_secondary="#f5f5f5",
                  block_border_color="#dddddd", border_color_primary="#dddddd", input_background_fill="#ffffff",
                  block_label_text_color="#444444", block_title_text_color="#444444",
                  body_text_color_subdued="#666666")
    base = gr.themes.Default(primary_hue="blue", neutral_hue="gray",
                             font=["Segoe UI", "Arial", "sans-serif"], font_mono=["Consolas", "monospace"])
    dark = {f"{k}_dark": v for k, v in colors.items() if hasattr(base, f"{k}_dark")}
    return base.set(**colors, **dark)


def main():
    global APP
    css = CSS_FILE.read_text(encoding="utf-8") if CSS_FILE.exists() else ""
    if not config.INDEX_FILE.exists():
        print(f"No existe {config.INDEX_FILE}. Ejecuta primero: python index_builder.py")
        with gr.Blocks(title="CosmoQuery") as demo:
            gr.HTML('<div class="cq-card"><h3>Falta el índice</h3><div class="cq-empty">Ejecuta primero '
                    '<code>python index_builder.py</code> y vuelve a abrir la aplicación.</div></div>')
        demo.launch(server_name="127.0.0.1", server_port=PORT, css=css, theme=theme())
        return
    APP = App()
    demo = build_ui()
    demo.queue(default_concurrency_limit=2)
    demo.launch(server_name="127.0.0.1", server_port=PORT, theme=theme(), css=css,
                allowed_paths=[str(config.FIGURES_DIR)])


if __name__ == "__main__":
    main()
