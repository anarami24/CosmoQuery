#ETAPA 1

import hashlib
import re
from html import unescape
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "noscript", "svg", "header", "nav", "footer", "aside",
             "form", "button", "iframe", "select", "template", "figure"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr", "param"}
BLOCK_TAGS = {"p", "li", "td", "dd", "dt", "blockquote", "h1", "h2", "h3", "h4"}
SKIP_ATTR_RE = re.compile(
    r"(^|[\s_-])(menu|nav|navbar|footer|breadcrumb|share|social|cookie|search|sidebar|"
    r"related|newsletter|skip|modal|subscribe|header|banner|pagination|tags?)($|[\s_-])", re.I)


class _ArticleParser(HTMLParser):
    #relaxed=False: modo estricto (solo <main>, ignora elementos marcados como menú).
    # relaxed=True : modo amplio para páginas con otra estructura: no se limita a <main>, no filtra por class/id y también toma texto de <div>/<section>.
    # La plantilla repetida se quita después con remove_boilerplate().

    def __init__(self, relaxed=False):
        super().__init__(convert_charrefs=True)
        self.relaxed = relaxed
        self.block_tags = BLOCK_TAGS | ({"div", "section", "article"} if relaxed else set())
        self.stack = []          
        self.skip_depth = 0      
        self.main_depth = 0      
        self.saw_main = False
        self.block = None        # etiqueta del bloque que se esta capturando
        self.buffer = []
        self.blocks = []       
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in VOID_TAGS:
            if tag == "br" and self.block:
                self.buffer.append(" ")
            return
        attrs = dict(attrs)
        marker = " ".join(filter(None, [attrs.get("class"), attrs.get("id"), attrs.get("role")]))
        is_main = tag == "main" or attrs.get("role") == "main"
        if self.relaxed:
            opens_skip = tag in SKIP_TAGS
        else:
            opens_skip = tag in SKIP_TAGS or (not is_main and bool(SKIP_ATTR_RE.search(marker))) \
                or attrs.get("aria-hidden") == "true"
        self.stack.append((tag, opens_skip, is_main))
        if opens_skip:
            self.skip_depth += 1
        if is_main:
            self.main_depth += 1
            self.saw_main = True
        if tag in self.block_tags and not self.skip_depth:
            self._flush()
            self.block = tag

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in VOID_TAGS or not any(t == tag for t, _, _ in self.stack):
            return
        while self.stack:
            t, opened_skip, was_main = self.stack.pop()
            if opened_skip:
                self.skip_depth -= 1
            if was_main:
                self.main_depth -= 1
            if t == self.block:
                self._flush()
            if t == tag:
                break

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self.block and not self.skip_depth:
            self.buffer.append(data)

    def _flush(self):
        if self.block:
            text = re.sub(r"\s+", " ", unescape("".join(self.buffer))).strip()
            if text:
                self.blocks.append((self.block, text, self.main_depth > 0))
        self.block, self.buffer = None, []

    def close(self):
        super().close()
        self._flush()


def extract_blocks(html, relaxed=False):
    #Devuelve (título_html, [(etiqueta, texto)]) con el contenido del artículo
    parser = _ArticleParser(relaxed)
    parser.feed(html)
    parser.close()
    blocks = [(("p" if t in ("div", "section", "article") else t), x, m) for t, x, m in parser.blocks]
    if not relaxed and parser.saw_main and any(in_main for _, _, in_main in blocks):
        blocks = [b for b in blocks if b[2]]
    return parser.title.strip(), [(tag, text) for tag, text, _ in blocks]


def content_words(blocks, min_words=8):
    return sum(len(t.split()) for tag, t in blocks if not tag.startswith("h") and _keep(tag, t, min_words))


def _keep(tag, text, min_words):
    #Filtra bloques: encabezados cortos sí; párrafos/listas solo si tienen contenido
    n = len(text.split())
    if tag in ("h1", "h2", "h3", "h4"):
        return 1 <= n <= 12
    if tag in ("li", "td", "dd", "dt"):
        return n >= max(6, min_words)
    return n >= min_words


def fingerprint(text):
    return hashlib.md5(re.sub(r"\W+", " ", text.lower()).strip().encode()).hexdigest()


def remove_boilerplate(docs, max_doc_fraction=0.3, min_docs=3):
    df = {}
    for blocks in docs.values():
        for fp in {fingerprint(t) for tag, t in blocks if not tag.startswith("h")}:
            df[fp] = df.get(fp, 0) + 1
    limit = max(min_docs, int(max_doc_fraction * len(docs)))
    removed = 0
    out = {}
    for doc_id, blocks in docs.items():
        kept = []
        for tag, text in blocks:
            if not tag.startswith("h") and df.get(fingerprint(text), 0) > limit:
                removed += 1
                continue
            kept.append((tag, text))
        out[doc_id] = kept
    return out, removed


def blocks_to_raw_text(title, blocks, min_words=8):
    #Convierte los bloques al formato de texto del pipeline
    lines = [f"TITLE: {title}"]
    seen = set()
    for tag, text in blocks:
        if not _keep(tag, text, min_words):
            continue
        if tag == "h1":
            continue                       # el título ya está en la primera línea
        if tag in ("h2", "h3", "h4"):
            level = {"h2": "==", "h3": "===", "h4": "===="}[tag]
            lines.append(f"{level} {text} {level}")
            continue
        fp = fingerprint(text)
        if fp in seen:                     # párrafo repetido dentro de la misma página
            continue
        seen.add(fp)
        lines.append(text)
    return "\n".join(lines) + "\n"