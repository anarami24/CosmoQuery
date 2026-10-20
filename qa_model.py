#ETAPA 5 - Modelo de lenguaje para responder preguntas (Persona 2).

# Modelo: deepset/roberta-base-squad2 (Hugging Face), sin entrenamiento adicional. Es un modelo
# extractivo: no redacta, elige un tramo (inicio, fin) del contexto que recibe.

# La lógica de ask_question replica la versión final del cuaderno PokeChat del profesor
# (celda "Define the final version of ask_question with no-answer handling"):
#   1. tokenizer(question, context) sin truncar;
#   2. inicio = argmax(start_logits) y fin = argmax(end_logits), elegidos por separado;
#   3. answer_score = start_logits[inicio] + end_logits[fin];
#      no_answer_score = start_logits[0] + end_logits[0]   (token <s>, "sin respuesta");
#      score_difference = answer_score - no_answer_score;
#   4. si score_difference < 7 -> "I don't know"; si no, se decodifica el tramo.
# Únicos agregados (no cambian la respuesta del cuaderno salvo el caso 3):
#   1. Se pide return_offsets_mapping para saber en qué carácter del contexto empieza la
#      respuesta (y así de qué fragmento salió).
#   2. Si la entrada pasa de 512 tokens se trunca el contexto (el cuaderno fallaría); se marca
#      truncated=True y se cuenta como error de la selección de contexto.
#   3. Si el tramo decodificado queda vacío (fin < inicio, o el tramo es un token especial),
#      la respuesta es "I don't know" (decisión aprobada por Camila).

# Complejidad: el modelo es un transformer; la atención cuesta O(L²·d) con L tokens de entrada
# (L <= 512) y d el tamaño oculto. Por eso el presupuesto de tokens importa.

import hashlib
import time

import config

_TOKENIZER = None
_MODEL = None
_DEVICE = None
_ANSWER_CACHE = {}


def load_model():
    """Carga el tokenizador y el modelo una sola vez (caché a nivel de módulo)."""
    global _TOKENIZER, _MODEL, _DEVICE
    if _MODEL is None:
        import torch
        from transformers import AutoModelForQuestionAnswering, AutoTokenizer
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        _TOKENIZER = AutoTokenizer.from_pretrained(config.QA_MODEL)
        _MODEL = AutoModelForQuestionAnswering.from_pretrained(config.QA_MODEL).to(_DEVICE).eval()
    return _TOKENIZER, _MODEL


def get_tokenizer():
    """Solo el tokenizador (no carga los pesos del modelo); sirve para contar tokens."""
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import AutoTokenizer
        _TOKENIZER = AutoTokenizer.from_pretrained(config.QA_MODEL)
    return _TOKENIZER


def count_tokens(text):
    """Tokens BPE reales del texto, sin tokens especiales."""
    return len(get_tokenizer()(text, add_special_tokens=False)["input_ids"])


def special_tokens_pair():
    """Tokens especiales que agrega el modelo a una pareja (pregunta, contexto): <s> q </s></s> c </s>."""
    return get_tokenizer().num_special_tokens_to_add(pair=True)


def answer(question, context, use_cache=True):
    """Respuesta del modelo para una pregunta y un contexto, con la lógica del PokeChat.

    Devuelve {answer, raw_answer, score_difference, start_char, end_char, tokens_used, truncated, time_ms}.
    raw_answer es el tramo elegido antes del umbral (solo para diagnosticar "I don't know").
    start_char/end_char son posiciones dentro de `context` (None si no hay respuesta).
    """
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
    raw_text = text                         # tramo elegido antes de aplicar el umbral (diagnóstico)
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
    """Carga respuestas guardadas por (pregunta, hash del contexto) desde un JSON."""
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
    """Misma firma y salida que ask_question del cuaderno PokeChat (solo el texto)."""
    return answer(question, context)["answer"]
