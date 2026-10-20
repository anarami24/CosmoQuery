#GUI - interfaz de CosmoQuery con Gradio (python app.py -> http://127.0.0.1:7860)

import html
import os
import random
import time
from urllib.parse import quote

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
# titulares en Bricolage Grotesque (Google Fonts); sin internet se usa la fuente del sistema
HEAD = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&display=swap">')
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


def hide_suggestions():
    return gr.Dataset(samples=[], visible=False)


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
    foot = (f'<div class="cq-foot">Respondido en {seconds:.2f} s. Revisé {r.search.n_examined} '
            f'de {r.search.n_total} fragmentos.</div>')

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
                 f'<div class="cq-source">{esc(c["doc"])}, {esc(c["section"])}</div>')
    return f'<div class="cq-card">{body}{foot}</div>'


def build_ui():
    with gr.Blocks(title="CosmoQuery") as demo:
        gr.HTML('<div class="cq-brand">CosmoQuery</div>'
                '<div class="cq-hero"><h1>Pregúntale al universo.</h1>'
                '<p>Respuestas sacadas de páginas de la NASA. Escribe tu pregunta en inglés.</p></div>')
        with gr.Row(elem_id="cq-ask-row", equal_height=True):
            question = gr.Textbox(show_label=False, placeholder="What is the largest volcano on Mars?",
                                  lines=1, max_lines=2, elem_id="cq-question", autofocus=True, scale=5,
                                  container=False)
            ask = gr.Button("Preguntar", variant="primary", elem_id="cq-ask", scale=0, min_width=150)
        suggestions = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[], label="Sugerencias",
                                 show_label=False, elem_id="cq-suggestions", type="values",
                                 layout="gallery", visible=False, samples_per_page=N_SUGGESTIONS)
        with gr.Row(elem_id="cq-options", equal_height=True):
            method = gr.Radio(METHOD_CHOICES, value="approximate", label="Búsqueda", elem_id="cq-method",
                              scale=0, min_width=260)
            algorithm = gr.Dropdown(ALG_CHOICES["approximate"], value="hybrid", label="Algoritmo",
                                    elem_id="cq-alg", scale=0, min_width=290)
        answer = gr.HTML(elem_id="cq-answer")
        examples = gr.Dataset(components=[gr.Textbox(visible=False)], samples=[[q] for q in APP.examples],
                              label="Prueba con", elem_id="cq-examples", type="values", layout="gallery")
        gr.HTML('<div class="cq-credits">Hecho por Ana Griselda Ramírez Arámburo y Camila Gómez Godínez '
                'para TC2038</div>')

        # el autocompletado corre en cada tecla; always_last evita que se encolen llamadas
        question.input(suggest, question, suggestions, show_progress="hidden",
                       trigger_mode="always_last", queue=False)
        suggestions.click(apply_suggestion, [suggestions, question], question, show_progress="hidden", queue=False) \
            .then(suggest, question, suggestions, show_progress="hidden", queue=False) \
            .then(None, js="() => { const t = document.querySelector('#cq-question textarea'); if (t) t.focus(); }")
        # al elegir un ejemplo se escribe en el cuadro y se pregunta de una vez
        examples.click(lambda s: (s[0] if s else "", hide_suggestions()), examples, [question, suggestions],
                       show_progress="hidden", queue=False) \
            .then(run_question, [question, method, algorithm], answer)
        method.change(lambda m: gr.Dropdown(choices=ALG_CHOICES[m], value=DEFAULT_ALG[m]), method, algorithm,
                      queue=False)
        for trigger in (ask.click, question.submit):
            trigger(hide_suggestions, None, suggestions, show_progress="hidden", queue=False)
            trigger(run_question, [question, method, algorithm], answer)
    return demo


def theme():
    # colores del diseño "anochecer en Marte"; iguales aunque el navegador esté en modo claro u oscuro
    glass, line = "rgba(255,255,255,0.10)", "rgba(255,255,255,0.28)"
    colors = dict(body_background_fill="#0D1230", body_text_color="#F4F1FF", body_text_color_subdued="#BDB6E6",
                  background_fill_primary="transparent", background_fill_secondary=glass,
                  block_background_fill="transparent", block_border_color="transparent",
                  block_label_text_color="#BDB6E6", block_title_text_color="#BDB6E6",
                  block_label_background_fill="transparent", panel_background_fill="transparent",
                  border_color_primary=line, input_background_fill=glass, input_border_color=line,
                  input_placeholder_color="#9C95C9", color_accent="#9B8BFA",
                  button_primary_background_fill="#9B8BFA", button_primary_background_fill_hover="#ADA0FB",
                  button_primary_text_color="#14112F",
                  checkbox_label_background_fill="transparent", checkbox_label_background_fill_selected="#F4F1FF",
                  checkbox_label_text_color="#F4F1FF", checkbox_label_text_color_selected="#1C1840",
                  checkbox_label_border_color="transparent", checkbox_label_border_color_selected="transparent")
    base = gr.themes.Default(primary_hue="violet", neutral_hue="slate",
                             font=[gr.themes.GoogleFont("Figtree"), "Segoe UI", "Arial", "sans-serif"])
    dark = {f"{k}_dark": v for k, v in colors.items() if hasattr(base, f"{k}_dark")}
    return base.set(**colors, **dark)


def sky_css():
    # estrellas (posiciones fijas) y colinas de Marte como SVG dentro del CSS, sin archivos extra
    rnd = random.Random(7)
    stars = "".join(f'<circle cx="{rnd.uniform(0, 1366):.0f}" cy="{rnd.uniform(0, 900):.0f}" '
                    f'r="{rnd.choice([0.6, 0.7, 0.8, 1.0, 1.2, 1.6]):.1f}" fill="#fff" '
                    f'opacity="{rnd.uniform(0.35, 1):.2f}"/>' for _ in range(110))
    stars_svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1366" height="900">{stars}</svg>'
    hills_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1366" height="260" viewBox="0 0 1366 260" '
                 'preserveAspectRatio="none">'
                 '<path d="M0 110 C 170 60 320 130 480 96 S 780 36 950 92 S 1210 140 1366 70 L 1366 260 L 0 260 Z" '
                 'fill="#5A2539"/>'
                 '<circle cx="1050" cy="79" r="5" fill="#FFF0CF"/>'
                 '<path d="M0 160 C 230 120 400 186 640 152 S 1040 110 1366 174 L 1366 260 L 0 260 Z" '
                 'fill="#2E1424"/></svg>')
    uri = lambda svg: "url(\"data:image/svg+xml;utf8," + quote(svg) + "\")"
    return (f".gradio-container {{ background-image: {uri(hills_svg)}, {uri(stars_svg)}, "
            "linear-gradient(180deg, #0D1230 0%, #251F5E 42%, #5B3471 72%, #A24E5E 88%, #2B1322 100%) !important; }\n")


def main():
    global APP
    css = (CSS_FILE.read_text(encoding="utf-8") if CSS_FILE.exists() else "") + sky_css()
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
    demo.launch(server_name="127.0.0.1", server_port=PORT, theme=theme(), css=css, head=HEAD)


if __name__ == "__main__":
    main()
