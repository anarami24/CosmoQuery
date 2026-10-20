#GUI - interfaz de CosmoQuery con Gradio (python app.py -> http://127.0.0.1:7860)

import html
import os
import time

if __name__ == "__main__":
    print("Iniciando CosmoQuery… cargando bibliotecas (la primera vez puede tardar unos minutos)", flush=True)

import gradio as gr

import config
from approx_search import ALGORITHM_LABELS as APPROX_LABELS
from approximate import trie_fuzzy_search
from exact_search import ALGORITHMS as EXACT_ALGORITHMS
from preprocessing import STOPWORDS, highlight
from string_matching import ALGORITHM_LABELS as EXACT_LABELS

CSS_FILE = config.BASE_DIR / "assets" / "cosmoquery.css"
PORT = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
N_SUGGESTIONS = 6
METHOD_CHOICES = [("Aproximada", "approximate"), ("Exacta", "exact")]
ALG_CHOICES = {
    "approximate": [(APPROX_LABELS[a], a) for a in ("hybrid", "osa_trie", "ngram_jaccard", "lev_trie")],
    "exact": [(EXACT_LABELS[a], a) for a in EXACT_ALGORITHMS],
}
DEFAULT_ALG = {"approximate": "hybrid", "exact": "kmp"}
# del banco de Ana: 2 literales, 2 con errores, 1 paráfrasis y 1 sin respuesta
EXAMPLE_IDS = ["Q01", "Q11", "Q11-T", "Q31-T", "Q43", "Q51"]


class App:
    def __init__(self):
        from evaluation import load_questions
        from index_builder import load_index
        from rag_pipeline import CosmoQuery
        print("Cargando índice…", flush=True)
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
    # resalta las palabras de la pregunta (por raíz) con <mark>
    s = highlight(text, terms, "\x01", "\x02")
    return esc(s).replace("\x01", "<mark>").replace("\x02", "</mark>")


# Autocompletado con el Trie
def current_prefix(text):
    if not text or text[-1].isspace():
        return ""
    tokens = APP.pp.normalize(text.split()[-1]).split()
    return tokens[-1] if tokens else ""


def suggest(text):
    prefix = current_prefix(text)
    trie = APP.trie
    if len(prefix) < 2:
        return gr.Dataset(samples=[], visible=False)
    keep_stop = prefix in STOPWORDS
    words = [w for w in trie.autocomplete(prefix, k=N_SUGGESTIONS * 4)
             if (keep_stop or w not in STOPWORDS) and w != prefix][:N_SUGGESTIONS]
    if not words and len(prefix) >= 3:
        # si no hay nada, se buscan prefijos parecidos (OSA <= 1)
        prefixes, _ = trie_fuzzy_search(trie, prefix, 1, "osa", prefix_mode=True)
        cands = {}
        for p, d, _ in sorted(prefixes, key=lambda x: (x[1], -len(x[0]))):
            for w in trie.autocomplete(p, k=4):
                if w not in STOPWORDS and w not in cands:
                    cands[w] = (d, -trie.frequency(w))
        words = sorted(cands, key=lambda w: cands[w])[:N_SUGGESTIONS]
    return gr.Dataset(samples=[[w] for w in words], visible=bool(words))


def apply_suggestion(sample, text):
    if not sample:
        return gr.update()
    word = sample[0] if isinstance(sample, (list, tuple)) else str(sample)
    text = text or ""
    base = text if not text or text[-1].isspace() else text[:len(text) - len(text.split()[-1])]
    return base + word + " "


# Pregunta y respuesta
def run_question(question, method, algorithm):
    question = (question or "").strip()
    if not question:
        return '<div class="cq-hint">Escribe una pregunta en inglés sobre el Sistema Solar.</div>'
    try:
        r = APP.cq.ask(question, method, algorithm)
    except Exception as e:
        return f'<div class="cq-hint">No se pudo responder: {esc(e)}</div>'
    return answer_html(r)


def answer_html(r):
    fixes = r.search.details.get("corrections", [])
    fix_html = ""
    if fixes:
        items = ", ".join(f'<s>{esc(c["query_word"])}</s> → <b>{esc(c["candidate"])}</b>' for c in fixes)
        fix_html = f'<div class="cq-fixes">¿Quisiste decir? {items}</div>'
    seconds = r.t_total_ms / 1000
    foot = (f'<div class="cq-foot">Respondido en {seconds:.2f} s · revisé {r.search.n_examined} '
            f'de {r.search.n_total} fragmentos</div>')

    if not r.search.results:
        return ('<div class="cq-card cq-idk"><div class="cq-answer">Sin resultados</div>'
                '<p>No encontré ningún fragmento con esas palabras. Revisa la ortografía o prueba la '
                f'búsqueda aproximada.</p>{fix_html}{foot}</div>')
    if r.is_no_answer:
        return ('<div class="cq-card cq-idk"><div class="cq-answer">I don\'t know</div>'
                '<p>No encontré la respuesta en los textos de NASA que tengo.</p>'
                f'{fix_html}{foot}</div>')

    body = f'<div class="cq-answer">{esc(r.answer)}</div>{fix_html}'
    if r.source_chunk_id is not None and r.answer_span:
        c = APP.index.chunks[r.source_chunk_id]
        text, (a, b) = c["text"], r.answer_span
        start = text.rfind(". ", 0, a)
        start = 0 if start < 0 else start + 2
        end = text.find(". ", b)
        end = len(text) if end < 0 else end + 1
        terms = r.search.terms
        sentence = (marked(text[start:a], terms) + f'<span class="cq-ans">{esc(text[a:b])}</span>'
                    + marked(text[b:end], terms))
        body += (f'<div class="cq-quote">{sentence}</div>'
                 f'<div class="cq-source">{esc(c["doc"])} › {esc(c["section"])}</div>')
    return f'<div class="cq-card">{body}{foot}</div>'


def build_ui():
    with gr.Blocks(title="CosmoQuery") as demo:
        gr.HTML('<div class="cq-header"><h1>CosmoQuery</h1>'
                '<p>Pregúntale algo sobre el Sistema Solar (en inglés)</p></div>')
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                question = gr.Textbox(label="Pregunta", placeholder="What is the largest volcano on Mars?",
                                      lines=1, max_lines=2, elem_id="cq-question", autofocus=True)
                suggestions = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[], label="Sugerencias",
                                         show_label=False, elem_id="cq-suggestions", type="values",
                                         layout="gallery", visible=False, samples_per_page=N_SUGGESTIONS)
                ask = gr.Button("Preguntar", variant="primary")
                answer = gr.HTML()
            with gr.Column(scale=1, min_width=240):
                method = gr.Radio(METHOD_CHOICES, value="approximate", label="Búsqueda")
                algorithm = gr.Dropdown(ALG_CHOICES["approximate"], value="hybrid", label="Algoritmo")
                examples = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[[q] for q in APP.examples],
                                      label="Prueba con", elem_id="cq-examples", type="values", layout="table")
        gr.HTML('<div class="cq-credits">Ana Griselda Ramírez Arámburo · Camila Gómez Godínez · TC2038</div>')

        # el autocompletado corre en cada tecla; always_last evita que se encolen llamadas
        question.input(suggest, question, suggestions, show_progress="hidden",
                       trigger_mode="always_last", queue=False)
        suggestions.click(apply_suggestion, [suggestions, question], question, show_progress="hidden", queue=False) \
            .then(suggest, question, suggestions, show_progress="hidden", queue=False) \
            .then(None, js="() => { const t = document.querySelector('#cq-question textarea'); if (t) t.focus(); }")
        examples.click(lambda s: s[0] if s else "", examples, question, show_progress="hidden", queue=False)
        method.change(lambda m: gr.Dropdown(choices=ALG_CHOICES[m], value=DEFAULT_ALG[m]), method, algorithm,
                      queue=False)
        for trigger in (ask.click, question.submit):
            trigger(run_question, [question, method, algorithm], answer)
    return demo


def theme():
    # tema claro de Gradio con fuentes del sistema; igual aunque el navegador esté en modo oscuro
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
            gr.HTML('<div class="cq-hint">Falta el índice. Ejecuta primero <code>python index_builder.py</code> '
                    'y vuelve a abrir la aplicación.</div>')
        demo.launch(server_name="127.0.0.1", server_port=PORT, css=css, theme=theme())
        return
    APP = App()
    demo = build_ui()
    demo.queue(default_concurrency_limit=2)
    demo.launch(server_name="127.0.0.1", server_port=PORT, theme=theme(), css=css)


if __name__ == "__main__":
    main()
