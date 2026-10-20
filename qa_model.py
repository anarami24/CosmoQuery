#ETAPA 5 - modelo de lenguaje (deepset/roberta-base-squad2, extractivo)

# answer() sigue el ask_question final del cuaderno PokeChat: argmax de inicio y de fin,
# score_difference = (inicio + fin) - (<s> + <s>) y si es < 7 la respuesta es "I don't know".
# Lo único que se agregó: los offsets para ubicar la respuesta, truncar si se pasa de 512
# tokens (se marca como error) y "I don't know" si el tramo sale vacío.
# La atención del modelo cuesta O(L²) con L tokens de entrada; por eso importa el presupuesto.

import hashlib
import time

import config

_TOKENIZER = None
_MODEL = None
_DEVICE = None
_ANSWER_CACHE = {}


def load_model():
    # se carga una sola vez
    global _TOKENIZER, _MODEL, _DEVICE
    if _MODEL is None:
        import torch
        from transformers import AutoModelForQuestionAnswering, AutoTokenizer
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        _TOKENIZER = AutoTokenizer.from_pretrained(config.QA_MODEL)
        _MODEL = AutoModelForQuestionAnswering.from_pretrained(config.QA_MODEL).to(_DEVICE).eval()
    return _TOKENIZER, _MODEL


def get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import AutoTokenizer
        _TOKENIZER = AutoTokenizer.from_pretrained(config.QA_MODEL)
    return _TOKENIZER


def count_tokens(text):
    return len(get_tokenizer()(text, add_special_tokens=False)["input_ids"])


def special_tokens_pair():
    # <s> pregunta </s></s> contexto </s>
    return get_tokenizer().num_special_tokens_to_add(pair=True)


def answer(question, context, use_cache=True):
    # raw_answer es el tramo antes del umbral; start_char/end_char son posiciones en el contexto
    key = (question, hashlib.sha1(context.encode("utf-8")).hexdigest())
    if use_cache and key in _ANSWER_CACHE:
        return dict(_ANSWER_CACHE[key], cached=True)
    import torch
    tokenizer, model = load_model()
    t0 = time.perf_counter()

    inputs = tokenizer(question, context, return_tensors="pt", return_offsets_mapping=True)
    tokens_used = inputs["input_ids"].shape[1]
    truncated = tokens_used > config.MODEL_MAX_TOKENS
    if truncated:
        inputs = tokenizer(question, context, return_tensors="pt", return_offsets_mapping=True,
                           truncation="only_second", max_length=config.MODEL_MAX_TOKENS)
    offsets = inputs.pop("offset_mapping")[0].tolist()
    sequence_ids = inputs.sequence_ids(0)
    inputs = {k: v.to(_DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    start_logits = outputs.start_logits[0]
    end_logits = outputs.end_logits[0]

    start_index = start_logits.argmax().item()
    end_index = end_logits.argmax().item()

    answer_score = start_logits[start_index].item() + end_logits[end_index].item()
    no_answer_score = start_logits[0].item() + end_logits[0].item()
    score_difference = answer_score - no_answer_score

    text = tokenizer.decode(inputs["input_ids"][0, start_index:end_index + 1],
                            skip_special_tokens=True).strip()
    raw_text = text
    start_char = end_char = None
    if score_difference < config.NO_ANSWER_THRESHOLD or not text:
        text = config.NO_ANSWER_TEXT
    elif sequence_ids[start_index] == 1 and sequence_ids[end_index] == 1:
        start_char, end_char = offsets[start_index][0], offsets[end_index][1]

    result = {"answer": text, "raw_answer": raw_text, "score_difference": score_difference, "start_char": start_char,
              "end_char": end_char, "tokens_used": int(tokens_used), "truncated": truncated,
              "time_ms": (time.perf_counter() - t0) * 1000, "cached": False}
    if use_cache:
        _ANSWER_CACHE[key] = result
    return result


def load_cache(path):
    # caché en disco por (pregunta, hash del contexto) para el benchmark
    import json
    if path.exists():
        for k, v in json.loads(path.read_text(encoding="utf-8")).items():
            q, h = k.rsplit("\x1f", 1)
            _ANSWER_CACHE[(q, h)] = v
    return len(_ANSWER_CACHE)


def save_cache(path):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({f"{q}\x1f{h}": v for (q, h), v in _ANSWER_CACHE.items()},
                               ensure_ascii=False), encoding="utf-8")


def ask_question(context, question):
    # misma firma que en el cuaderno
    return answer(question, context)["answer"]
