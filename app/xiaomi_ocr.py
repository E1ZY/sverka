"""Local Xiaomi-OCR-0 inference. No document or image is sent to a remote API."""
import logging
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)
_lock = threading.RLock()
PROMPT = 'Extract the text in the image.'


@lru_cache(maxsize=1)
def _load(model_path, device):
    if not (Path(model_path) / 'model.safetensors').is_file():
        raise RuntimeError('Xiaomi-OCR-0 не подготовлена. Выполните: python scripts/setup_xiaomi_ocr.py')
    try:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
    except ImportError as error:
        raise RuntimeError('Установите зависимости Xiaomi OCR: python -m pip install -r requirements-xiaomi-ocr.txt -c constraints.txt') from error
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA недоступна. Установите CUDA-сборку PyTorch по README или выберите XIAOMI_OCR_DEVICE=cpu.')
    dtype = torch.float32 if device == 'cpu' else torch.float16
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForImageTextToText.from_pretrained(model_path, dtype=dtype, local_files_only=True,
                                                      trust_remote_code=False, attn_implementation='sdpa').to(device).eval()
    log.info('Xiaomi-OCR-0 loaded on %s', device)
    return torch, processor, model, device


def _character_scores(tokenizer, ids, scores, text):
    """Map generation log probabilities to characters without inventing OCR certainty."""
    useful = [(token, score) for token, score in zip(ids, scores) if token not in tokenizer.all_special_ids]
    try:
        encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        if encoded['input_ids'] == [token for token, _ in useful]:
            output = [min(scores, default=-math.inf)] * len(text)
            for (_, score), (start, end) in zip(useful, encoded['offset_mapping']):
                output[start:end] = [score] * (end-start)
            return output
    except (NotImplementedError, TypeError, ValueError):
        pass
    # Byte-level tokens can complete a Cyrillic character in a later step.
    output, cursor, pending = [-math.inf] * len(text), 0, []
    for index, score in enumerate(scores):
        pending.append(score)
        prefix = tokenizer.decode(ids[:index+1], skip_special_tokens=True, clean_up_tokenization_spaces=False)
        end = 0
        for actual, expected in zip(prefix, text):
            if actual != expected:
                break
            end += 1
        if end > cursor:
            output[cursor:end] = [min(pending)] * (end-cursor)
            cursor, pending = end, []
    return output


def generation_words(tokenizer, ids, scores, size):
    text = tokenizer.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    confidence = _character_scores(tokenizer, ids, scores, text)
    tokens, offset = [], 0
    for line, content in enumerate(text.splitlines(keepends=True), 1):
        for match in re.finditer(r'\S+', content):
            probabilities = confidence[offset+match.start():offset+match.end()]
            score = 100 * math.exp(sum(probabilities) / len(probabilities)) if probabilities else 0
            # The bounding box is the actual supplied region, not a fabricated word location.
            tokens.append({'text': match[0], 'bbox': [0, 0, size[0], size[1]], 'line': line,
                           'confidence': round(min(score, 99.9), 1), 'provider': 'xiaomi',
                           'confidence_basis': 'generation_probability', 'bbox_precision': 'region'})
        offset += len(content)
    return tokens


def words(image, settings, psm=6, numeric=False):
    with _lock:
        torch, processor, model, device = _load(settings.model, settings.device)
        # Retain only one scalar per generated token, rather than vocab-sized scores.
        scores = []
        from transformers import LogitsProcessor

        class Confidence(LogitsProcessor):
            def __call__(self, input_ids, logits):
                probabilities = logits[0].float()
                # Keep scalar tensors on the GPU; .item() here would synchronize
                # the CPU and GPU after every generated token.
                scores.append((probabilities.max() - torch.logsumexp(probabilities, dim=-1)).detach())
                return logits

        messages = [{'role': 'user', 'content': [{'type': 'image', 'image': image.convert('RGB')},
                                               {'type': 'text', 'text': PROMPT}]}]
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                enable_thinking=False, return_dict=True, return_tensors='pt').to(device)
        limit = min(settings.max_new_tokens, 128 if numeric else 512 if psm == 7 else settings.max_new_tokens)
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=limit, max_time=settings.timeout,
                                    do_sample=False, logits_processor=[Confidence()])
        ids = output[0, inputs['input_ids'].shape[1]:].tolist()
        eos = model.generation_config.eos_token_id
        eos = {eos} if isinstance(eos, int) else set(eos or [])
        if not ids or ids[-1] not in eos:
            raise RuntimeError('Xiaomi OCR не закончила распознавание: достигнут лимит времени или текста. Частичный результат не принят.')
        if len(ids) != len(scores):
            raise RuntimeError('Xiaomi OCR: не удалось сопоставить текст с оценками уверенности.')
        scores = [min(0., value) if math.isfinite(value) else -math.inf
                  for value in torch.stack(scores).cpu().tolist()]
        return generation_words(processor.tokenizer, ids, scores, image.size)
