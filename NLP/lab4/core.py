
import re
import random
import time
import torch
from tqdm.auto import tqdm
from transformers import GPT2LMHeadModel, GPT2Tokenizer
from concurrent.futures import ThreadPoolExecutor
from tqdm.auto import tqdm

from .utils import find_progress, find_progress, find_progress_with_pos, print_stats
from .prompts import prompts, sys_prompt, words

model_name = "sberbank-ai/rugpt3large_based_on_gpt2"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tok = GPT2Tokenizer.from_pretrained(model_name)
# model = GPT2LMHeadModel.from_pretrained(model_name).to(device)
# model.eval()

MAX_NEW_TOKENS = 1_000
TOP_P = 0.95
REPETITION_PENALTY = 2.0
NUM_BEAMS = 1
DO_SAMPLE = True
TOTAL_ATTEMPTS = 15_000
STATS_EVERY = 10
TOTAL_CUDAS = 4

assert torch.cuda.device_count() >= TOTAL_CUDAS, f"Нужно минимум {TOTAL_CUDAS} GPU"

models = []
for i in range(TOTAL_CUDAS):
    device = f"cuda:{i}"

    model_i = GPT2LMHeadModel.from_pretrained(
        model_name,
        torch_dtype=torch.float16
    ).to(device)

    model_i.eval()
    models.append(model_i)

    print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
gpu_count = len(models)
print("gpu_count:", gpu_count)




def generate(
    model, tok, text,
    do_sample=True, max_length=100, repetition_penalty=5.0,
    top_k=5, top_p=0.95, temperature=1,
    num_beams=None, no_repeat_ngram_size=3
):
    input_ids = tok.encode(text, return_tensors="pt")

    with torch.no_grad():
        out = model.generate(
            input_ids,
            max_length=max_length,
            repetition_penalty=repetition_penalty,
            do_sample=do_sample,
            top_k=top_k,
            top_p=top_p,
            temperature=temperature,
            num_beams=num_beams,
            no_repeat_ngram_size=no_repeat_ngram_size,
            pad_token_id=tok.eos_token_id
        )

    return [tok.decode(ids, skip_special_tokens=True) for ids in out]

def run_attempt(attempt, gpu_id):
    model_i = models[gpu_id]
    prompt_id = random.randrange(len(prompts))
    prompt = sys_prompt.strip() + "\n\n" + prompts[prompt_id].strip()

    temperature = random.choice([0.7, 0.8, 1.0, 1.2])
    top_k = random.choice([20, 50, 100])
    no_repeat_ngram_size = random.choice([0, 2])

    input_ids = tok.encode(prompt, return_tensors="pt").to(f"cuda:{gpu_id}")

    start = time.time()

    with torch.no_grad():
        output = model_i.generate(
            input_ids,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=DO_SAMPLE,
            temperature=temperature,
            top_k=top_k,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            num_beams=NUM_BEAMS,
            no_repeat_ngram_size=no_repeat_ngram_size,
            pad_token_id=tok.eos_token_id
        )

    torch.cuda.synchronize(gpu_id)
    elapsed = time.time() - start

    generated = tok.decode(
        output[0, input_ids.shape[1]:],
        skip_special_tokens=True
    )

    found, missing = find_progress(generated)
    count = len(found)

    result = {
        "attempt": attempt,
        "gpu": gpu_id,
        "prompt_id": prompt_id,
        "prompt": prompt,
        "text": generated,
        "found": found,
        "missing": missing,
        "count": count,
        "temperature": temperature,
        "top_k": top_k,
        'no_repeat_ngram_size': no_repeat_ngram_size,
        "elapsed": elapsed,
        "success": count == len(words)
    }

    # Краткая информация о каждой попытке с найденными словами
    if found:
        print(
            f"\nПопытка {attempt} | GPU {gpu_id} | "
            f"{elapsed:.1f} сек | "
            f"Промпт №{prompt_id + 1} | "
            f"temperature={temperature}, top_k={top_k}",
            flush=True
        )
        
        # print("\nИсходный промпт:\n", prompt, flush=True)
        print(f"\nНайдено: {count}/10 — {' → '.join(found)}", flush=True)
        print(f"Ещё не найдены: {', '.join(missing) if missing else 'все найдены'}", flush=True)
        # print(f"Следующее ожидаемое слово: {missing or 'все найдены'}", flush=True)
        # print("\nСгенерированный текст:\n", generated, flush=True)
        
        

    # Полный текст при успехе
    if result["success"]:
        print("\nВСЕ 10 СЛОВ НАЙДЕНЫ!", flush=True)
        print(f"Попытка: {attempt} | GPU: {gpu_id}", flush=True)
        print(f"Параметры: temperature={temperature}, top_k={top_k}")
        print("\nПромпт:\n", prompt, flush=True)
        print("\nСгенерированный текст:\n", generated, flush=True)

    return result


attempts_stats = []
best_count = 0
best_text = ""
best_prompt = ""
best_params = {}
success = False
start_all = time.time()

with ThreadPoolExecutor(max_workers=gpu_count) as executor:
    for batch_start in tqdm(
        range(1, TOTAL_ATTEMPTS + 1, gpu_count),
        desc="Перебор"
    ):
        batch = [
            (attempt,executor.submit(run_attempt, attempt, gpu_id))
            for gpu_id in range(gpu_count)
            if (attempt := batch_start + gpu_id) <= TOTAL_ATTEMPTS
        ]

        for attempt, future in batch:
            result = future.result()

            attempts_stats.append({
                "attempt": result["attempt"],
                "gpu": result["gpu"],
                "prompt_id": result["prompt_id"] + 1,
                "temperature": result["temperature"],
                "top_k": result["top_k"],
                'no_repeat_ngram_size': result["no_repeat_ngram_size"],
                "found_count": result["count"],                
                "found": result["found"].copy(),
                "missing": result["missing"].copy(),
                "elapsed": result["elapsed"],
                "success": result["success"],
            })

            if len(attempts_stats) % STATS_EVERY == 0:
                print_stats(attempts_stats)

            if result["count"] > best_count:
                best_count = result["count"]
                best_text = result["text"]
                best_prompt = result["prompt"]
                best_params = {
                    "temperature": result["temperature"],
                    "top_k": result["top_k"]
                }

                print("\nНОВЫЙ РЕКОРД!", flush=True)
                print(f"Попытка: {attempt}")
                print(f"Результат: {best_count}/10")
                print("Промпт:\n", best_prompt, flush=True)
                print("Текст:\n", best_text, flush=True)

            if result["success"]:
                success = True

        if success:
            break

if attempts_stats and len(attempts_stats) % STATS_EVERY != 0:
    print_stats(attempts_stats)
print("\n" + "=" * 50)
print("ПЕРЕБОР ЗАВЕРШЁН")
print(f"Успех: {success}")
print(f"Лучший результат: {best_count}/10")
print(f"Время: {(time.time() - start_all) / 60:.1f} мин")
print("Лучший промпт:\n", best_prompt)
print("Лучший текст:\n", best_text)
print("Лучшие параметры:", best_params)
