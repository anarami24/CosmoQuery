import json
import random
import re
import statistics
import string
from collections import Counter, defaultdict

import config
from preprocessing import STOPWORDS, Preprocessor

_pp = Preprocessor()
_norm_cache = {}


#banco de preguntas
def make_typo(question, rng, n_words=None):
    words = question.split()
    candidates = [i for i, w in enumerate(words)
                  if len(w.strip(string.punctuation)) >= 5 and w.lower().strip(string.punctuation) not in STOPWORDS]
    if not candidates:
        return question
    n_words = n_words or (2 if len(candidates) >= 3 else 1)
    for i in rng.sample(candidates, min(n_words, len(candidates))):
        w = words[i]
        core = w.rstrip(string.punctuation)
        tail = w[len(core):]
        for _ in range(10):
            op = rng.choice(["swap", "delete", "substitute", "insert"])
            j = rng.randint(1, len(core) - 2)            # no tocar la primera letra
            if op == "swap":
                new = core[:j] + core[j + 1] + core[j] + core[j + 2:]
            elif op == "delete":
                new = core[:j] + core[j + 1:]
            elif op == "substitute":
                new = core[:j] + rng.choice("aeioursnlt") + core[j + 1:]
            else:
                new = core[:j] + rng.choice("aeioursnlt") + core[j:]
            if new.lower() != core.lower():
                break
        words[i] = new + tail
    return " ".join(words)


def load_questions(path=config.QUESTIONS_FILE, include_typos=True, seed=42):
    questions = json.loads(path.read_text(encoding="utf-8"))
    if include_typos:
        rng = random.Random(seed)
        typos = []
        for q in questions:
            if q["category"] in ("literal", "paraphrase"):
                t = dict(q)
                t["id"] = q["id"] + "-T"
                t["question"] = make_typo(q["question"], rng)
                t["category"] = "typo"
                t["original"] = q["question"]
                typos.append(t)
        questions = questions + typos
    return questions


#Relevancia
def _normalized_chunks(index):
    key = id(index)
    if key not in _norm_cache:
        _norm_cache[key] = [" " + _pp.normalize(c["text"]) + " " for c in index.chunks]
    return _norm_cache[key]


def relevant_chunks(index, question):
    if not question.get("evidence"):
        return set()
    texts = _normalized_chunks(index)
    evid = [" " + _pp.normalize(e) + " " for e in question["evidence"]]
    docs = set(question.get("docs") or [])
    out = set()
    for cid, chunk in enumerate(index.chunks):
        if docs and chunk["doc"] not in docs:
            continue
        if any(e in texts[cid] for e in evid):
            out.add(cid)
    return out


def validate_questions(index, questions):
    corpus_docs = {c["doc"] for c in index.chunks}
    problems = []
    for q in questions:
        if q["category"] == "no_answer" or q["category"] == "typo":
            continue
        if not relevant_chunks(index, q):
            missing = [d for d in q["docs"] if d not in corpus_docs]
            problems.append({"id": q["id"], "question": q["question"],
                             "reason": f"documentos ausentes: {missing}" if missing else "evidencia no encontrada"})
    return problems


#metricas
def ranking_metrics(retrieved, relevant, ks=(1, 3, 5)):
    m = {}
    for k in ks:
        top = retrieved[:k]
        hits = sum(1 for c in top if c in relevant)
        m[f"hit@{k}"] = 1.0 if hits else 0.0
        m[f"p@{k}"] = hits / k
        m[f"r@{k}"] = hits / min(k, len(relevant)) if relevant else 0.0
    rr = 0.0
    for pos, c in enumerate(retrieved, 1):
        if c in relevant:
            rr = 1.0 / pos
            break
    m["mrr"] = rr
    return m


def normalize_answer(s):
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def answer_scores(prediction, answers, no_answer_text="I don't know"):
    if not answers:
        ok = float(prediction.strip().lower() == no_answer_text.lower())
        return {"em": ok, "f1": ok}
    pred_toks = normalize_answer(prediction).split()
    best_em = best_f1 = 0.0
    for ans in answers:
        gold = normalize_answer(ans).split()
        best_em = max(best_em, float(pred_toks == gold))
        common = Counter(pred_toks) & Counter(gold)
        same = sum(common.values())
        if same:
            p, r = same / len(pred_toks), same / len(gold)
            best_f1 = max(best_f1, 2 * p * r / (p + r))
    return {"em": best_em, "f1": best_f1}


#Evaluación de una estrategia de búsqueda
def evaluate_search(search_fn, index, questions, ks=(1, 3, 5), repeats=1):
    rows = []
    for q in questions:
        times, res = [], None
        for _ in range(repeats):
            res = search_fn(q["question"])
            times.append(res.time_ms)
        relevant = relevant_chunks(index, q)
        row = {
            "id": q["id"], "category": q["category"], "question": q["question"],
            "time_ms": statistics.median(times), "examined": res.n_examined,
            "matched": res.n_matched, "retrieved": res.ids(), "n_relevant": len(relevant),
            "top_score": res.results[0].score if res.results else 0.0,
        }
        if q["category"] != "no_answer":
            row.update(ranking_metrics(res.ids(), relevant, ks))
        rows.append(row)
    return rows, summarize(rows), summarize_by(rows, "category")


def summarize(rows):
    if not rows:
        return {}
    out = {"n": len(rows),
           "time_ms_avg": statistics.mean(r["time_ms"] for r in rows),
           "time_ms_median": statistics.median(r["time_ms"] for r in rows),
           "examined_avg": statistics.mean(r["examined"] for r in rows),
           "matched_avg": statistics.mean(r["matched"] for r in rows)}
    rated = [r for r in rows if "mrr" in r]
    if rated:
        for key in [k for k in rated[0] if k.startswith(("hit@", "p@", "r@")) or k == "mrr"]:
            out[key] = statistics.mean(r[key] for r in rated)
    return out


def summarize_by(rows, field):
    groups = defaultdict(list)
    for r in rows:
        groups[r[field]].append(r)
    return {k: summarize(v) for k, v in groups.items()}
