import argparse
import json
import re
import time
from pathlib import Path

import config
from html_extractor import blocks_to_raw_text, content_words, extract_blocks, remove_boilerplate

SECTION_RE = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")
SENTENCE_RE = re.compile(r"(?<!\b[A-Z]\.)(?<!\bSt\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bvs\.)(?<!\bc\.)(?<!\bSept\.)(?<!\bOct\.)(?<!\bNov\.)(?<!\bDec\.)(?<!\bJan\.)(?<!\bFeb\.)(?<!\bAug\.)(?<!\bApr\.)(?<!\bMar\.)(?<!\bJr\.)(?<!\bNo\.)(?<=[.!?])\s+(?=[\"'(A-Z0-9])")


#Descarga
def download_pages(sources, html_dir=config.HTML_DIR, pause=1.0, retries=3):
   #Descarga cada URL a data/html/<id>.html. Si ya existe no la vuelve a bajar
    import requests 

    html_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT,
                            "Accept-Language": "en-US,en;q=0.9"})
    failed = []
    for doc_id, title, urls in sources:
        path = html_dir / f"{doc_id}.html"
        if path.exists() and path.stat().st_size > 2000:
            print(f"  [en caché]    {title}")
            continue
        urls = urls if isinstance(urls, (tuple, list)) else (urls,)
        ok, last_error = False, ""
        for url in urls:                        # URL principal y alternativas
            for attempt in range(1, retries + 1):
                try:
                    resp = session.get(url, timeout=30, allow_redirects=True)
                    if resp.status_code == 404:
                        last_error = f"404 en {url}"
                        break                       # no reintentar: probar la siguiente URL
                    resp.raise_for_status()
                    resp.encoding = resp.apparent_encoding or "utf-8"
                    path.write_text(resp.text, encoding="utf-8")
                    moved = f"  (desde {resp.url})" if resp.url.rstrip("/") != urls[0].rstrip("/") else ""
                    print(f"  [descargada]  {title}{moved}")
                    ok = True
                    break
                except Exception as e: 
                    last_error = str(e)[:90]
                    if attempt < retries:
                        time.sleep(2 * attempt)   
            if ok:
                break
        if not ok:
            print(f"  [FALLÓ]       {title}: {last_error}")
            failed.append((doc_id, title, urls[0]))
        time.sleep(pause)                     
    return failed


def html_to_raw(sources, html_dir=config.HTML_DIR, raw_dir=config.RAW_DIR):
    #Extrae el texto de cada HTML guardado, quita la plantilla repetida y escribe data/raw/
    raw_dir.mkdir(parents=True, exist_ok=True)
    for old in raw_dir.glob("*.txt"):
        old.unlink()
    titles, docs, relaxed_ids = {}, {}, []
    for doc_id, title, url in sources:
        path = html_dir / f"{doc_id}.html"
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        _, blocks = extract_blocks(html)
        if content_words(blocks) < 150:
            _, relaxed_blocks = extract_blocks(html, relaxed=True)
            if content_words(relaxed_blocks) > content_words(blocks):
                blocks = relaxed_blocks
                relaxed_ids.append(title)
        titles[doc_id] = title
        docs[doc_id] = blocks
    docs, removed = remove_boilerplate(docs)
    words = {}
    for doc_id, blocks in docs.items():
        text = blocks_to_raw_text(titles[doc_id], blocks)
        (raw_dir / f"{doc_id}.txt").write_text(text, encoding="utf-8")
        words[doc_id] = len(text.split())
    print(f"  Texto extraído de {len(docs)} páginas; {removed} bloques de plantilla eliminados.")
    if relaxed_ids:
        print(f"  Extraídas en modo amplio (estructura HTML distinta): {', '.join(relaxed_ids)}")
    for doc_id, n in sorted(words.items(), key=lambda kv: kv[1]):
        flag = "  <- muy corta, revisar" if n < 150 else ""
        print(f"    {titles[doc_id]:<32} {n:>6,} palabras{flag}")
    return words


def safe_name(title):
    return re.sub(r"[^\w\-]+", "_", title).strip("_")


#Lectura y limpieza
def read_article(path):
    #Devuelve (titulo, [(seccion, texto_de_la_seccion), ...]) sin secciones inutiles
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    title = lines[0].replace("TITLE:", "").strip() if lines and lines[0].startswith("TITLE:") else Path(path).stem
    sections, current, buffer = [], "Introduction", []
    skipping = False
    level_skip = None
    for line in lines[1:]:
        m = SECTION_RE.match(line.strip())
        if m:
            level, name = len(m.group(1)), m.group(2).strip()
            if buffer and not skipping:
                sections.append((current, "\n".join(buffer)))
            buffer = []
            if name.lower() in config.SKIP_SECTIONS:
                skipping, level_skip = True, level
            elif skipping and level > level_skip:
                pass 
            else:
                skipping = False
            current = name
            continue
        if not skipping:
            buffer.append(line)
    if buffer and not skipping:
        sections.append((current, "\n".join(buffer)))
    cleaned = [(sec, clean_text(txt)) for sec, txt in sections]
    return title, [(sec, txt) for sec, txt in cleaned if txt]


def clean_text(text):
    text = re.sub(r"\{\\displaystyle[^}]*\}", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = [p.strip() for p in text.split("\n") if len(p.split()) >= 4]
    return "\n".join(paragraphs)


def split_sentences(paragraph):
    return [s.strip() for s in SENTENCE_RE.split(paragraph) if s.strip()]


#Fragmentación (algoritmo voraz)
def chunk_section(sentences, size=config.CHUNK_SIZE_WORDS, overlap=config.CHUNK_OVERLAP_WORDS):
    #Empaquetado VORAZ de oraciones en fragmentos:

    units = []
    for s in sentences:
        words = s.split()
        for i in range(0, len(words), size):
            units.append(" ".join(words[i:i + size]))

    chunks, current, current_len = [], [], 0
    for unit in units:
        n = len(unit.split())
        if current and current_len + n > size:
            chunks.append(" ".join(current))
            carry, carry_len = [], 0
            for prev in reversed(current):
                if carry_len >= overlap:
                    break
                carry.insert(0, prev)
                carry_len += len(prev.split())
            if carry_len + n > size:       
                carry, carry_len = [], 0
            current, current_len = carry, carry_len
        current.append(unit)
        current_len += n
    if current:
        chunks.append(" ".join(current))
    return chunks


def build_chunks(article_paths):
    chunks = []
    for path in sorted(article_paths):
        title, sections = read_article(path)
        for section, text in sections:
            sentences = [s for p in text.split("\n") for s in split_sentences(p)]
            for piece in chunk_section(sentences):
                n_words = len(piece.split())
                # fragmento muy corto: se une al anterior si es del mismo artículo
                if n_words < config.MIN_CHUNK_WORDS and chunks and chunks[-1]["doc"] == title:
                    chunks[-1]["text"] += " " + piece
                    if section not in chunks[-1]["section"]:
                        chunks[-1]["section"] += " / " + section
                    chunks[-1]["n_words"] = len(chunks[-1]["text"].split())
                    chunks[-1]["n_chars"] = len(chunks[-1]["text"])
                    continue
                chunks.append({
                    "id": len(chunks), "doc": title, "section": section,
                    "text": piece, "n_words": n_words, "n_chars": len(piece),
                })
    return chunks


#Estadisticas para el reporte
def corpus_stats(article_paths, chunks):
    docs = {}
    for c in chunks:
        docs.setdefault(c["doc"], {"chunks": 0, "words": 0})
        docs[c["doc"]]["chunks"] += 1
    raw_words = raw_chars = 0
    for p in article_paths:
        t = Path(p).read_text(encoding="utf-8")
        raw_words += len(t.split())
        raw_chars += len(t)
    sizes = [c["n_words"] for c in chunks]
    return {
        "n_documents": len(article_paths),
        "raw_words": raw_words,
        "raw_chars": raw_chars,
        "clean_words_in_chunks": sum(sizes),
        "n_chunks": len(chunks),
        "chunk_words_avg": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "chunk_words_min": min(sizes) if sizes else 0,
        "chunk_words_max": max(sizes) if sizes else 0,
        "chunk_size_target": config.CHUNK_SIZE_WORDS,
        "chunk_overlap": config.CHUNK_OVERLAP_WORDS,
        "chunks_per_document": {d: v["chunks"] for d, v in sorted(docs.items())},
    }


def write_stats_markdown(stats, path):
    lines = [
        "# Etapa 1 - Estadísticas de la colección\n",
        "| Métrica | Valor |", "|---|---|",
        f"| Documentos | {stats['n_documents']} |",
        f"| Palabras (texto descargado) | {stats['raw_words']:,} |",
        f"| Caracteres (texto descargado) | {stats['raw_chars']:,} |",
        f"| Palabras tras limpieza (en fragmentos) | {stats['clean_words_in_chunks']:,} |",
        f"| Fragmentos | {stats['n_chunks']:,} |",
        f"| Palabras por fragmento (prom / mín / máx) | {stats['chunk_words_avg']} / {stats['chunk_words_min']} / {stats['chunk_words_max']} |",
        f"| Criterio | ventana voraz de {stats['chunk_size_target']} palabras por oraciones completas, traslape de {stats['chunk_overlap']} |",
        "\n## Fragmentos por documento\n", "| Documento | Fragmentos |", "|---|---|",
    ]
    lines += [f"| {d} | {n} |" for d, n in stats["chunks_per_document"].items()]
    if stats.get("urls"):
        lines += ["\n## Fuentes\n", "| Documento | URL |", "|---|---|"]
        lines += [f"| {t} | {u} |" for t, u in stats["urls"].items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def diagnose(doc_id):
    #muestra cuantas palabras se extraen de una página en cada modo y los primeros bloques.
    path = config.HTML_DIR / f"{doc_id}.html"
    if not path.exists():
        raise SystemExit(f"No existe {path}")
    html = path.read_text(encoding="utf-8", errors="ignore")
    print(f"{path.name}: {len(html):,} caracteres de HTML, "
          f"<p>: {html.count('<p')}, <li>: {html.count('<li')}, <main>: {html.count('<main')}")
    for relaxed in (False, True):
        _, blocks = extract_blocks(html, relaxed=relaxed)
        print(f"\n--- modo {'amplio' if relaxed else 'estricto'}: {content_words(blocks)} palabras útiles ---")
        for tag, text in blocks[:12]:
            print(f"  <{tag}> {text[:110]}")


def main():
    ap = argparse.ArgumentParser(description="Etapa 1: construir la colección de fragmentos")
    ap.add_argument("--sample", action="store_true", help="usar el corpus offline de data/sample")
    ap.add_argument("--no-download", action="store_true", help="reutilizar el HTML de data/html")
    ap.add_argument("--solo-base", action="store_true", help="usar solo las fuentes base (sin las adicionales)")
    ap.add_argument("--diagnostico", metavar="ID", help="mostrar qué texto se extrae de data/html/<ID>.html")
    args = ap.parse_args()

    if args.diagnostico:
        diagnose(args.diagnostico)
        return

    if args.sample:
        source_dir = config.SAMPLE_DIR
        sources = []
    else:
        sources = config.SOURCES + ([] if args.solo_base else config.EXTRA_SOURCES)
        if not args.no_download:
            print(f"Descargando {len(sources)} páginas de NASA...")
            failed = download_pages(sources)
            if failed:
                print(f"  AVISO: {len(failed)} páginas no se descargaron (ver arriba). Se continúa con las demás.")
        print("Extrayendo el texto de las páginas...")
        html_to_raw(sources)
        source_dir = config.RAW_DIR
    paths = sorted(source_dir.glob("*.txt"))
    if not paths:
        raise SystemExit(f"No hay textos en {source_dir}. Revisa la conexión o guarda los HTML en {config.HTML_DIR}")

    t0 = time.perf_counter()
    chunks = build_chunks(paths)
    elapsed = time.perf_counter() - t0

    config.DATA_DIR.mkdir(exist_ok=True)
    config.CHUNKS_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")

    stats = corpus_stats(paths, chunks)
    stats["chunking_time_s"] = round(elapsed, 3)
    stats["source"] = "sample (offline)" if args.sample else "NASA (science.nasa.gov, nasa.gov, jpl.nasa.gov)"
    stats["urls"] = {t: (u[0] if isinstance(u, (tuple, list)) else u) for _, t, u in sources}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "etapa1_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    write_stats_markdown(stats, config.RESULTS_DIR / "etapa1_stats.md")

    print(f"\nDocumentos: {stats['n_documents']}  |  Palabras: {stats['raw_words']:,}  |  "
          f"Fragmentos: {stats['n_chunks']:,}  (prom {stats['chunk_words_avg']} palabras)")
    print(f"Fragmentos guardados en {config.CHUNKS_FILE}")


if __name__ == "__main__":
    main()