
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    LogitsProcessor,
    LogitsProcessorList,
)


class NoIPhoneLogitsProcessor(LogitsProcessor):
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

        # Разные написания и контексты начала слова
        variants = [
            "iPhone",
            "iphone",
            "IPhone",
            "IPHONE",
            " Iphone",
            " iphone",
            " IPhone",
            " IPHONE",
            "\niPhone",
            "\niphone",
            "iPhone's",
            "iPhones",
            "айфон",
            "Айфон",
        ]

        # Уникальные последовательности токенов
        self.bad_sequences = set()
        for variant in variants:
            ids = tokenizer.encode(
                variant, add_special_tokens=False
            )
            if ids:
                self.bad_sequences.add(tuple(ids))

        # Для наглядности проверяем, как токенизатор
        # разбивает каждое написание
        print("Найденные последовательности:")
        for seq in sorted(self.bad_sequences):
            print(seq, "->", tokenizer.decode(list(seq)))

    def __call__(self, input_ids, scores):
        # input_ids: [batch_size, текущая длина]
        # scores:    [batch_size, размер словаря]

        for row in range(input_ids.shape[0]):
            generated = input_ids[row].tolist()

            for seq in self.bad_sequences:
                n = len(seq)

                # Однотокенные варианты запрещаем всегда
                if n == 1:
                    scores[row, seq[0]] = -float("inf")
                    continue

                # Проверяем, совпадает ли конец контекста
                # с началом запрещённой последовательности.
                # Если совпадает, блокируем следующий токен.
                max_prefix = min(n - 1, len(generated))

                for k in range(1, max_prefix + 1):
                    if tuple(generated[-k:]) == seq[:k]:
                        next_token = seq[k]
                        scores[row, next_token] = -float("inf")

        return scores


model_name = "sberbank-ai/rugpt3large_based_on_gpt2"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)
model.eval()

processor = NoIPhoneLogitsProcessor(tokenizer)
logits_processor = LogitsProcessorList([processor])

prompt = (
    "Explain the differences between popular "
    "smartphones and their operating systems."
)

inputs = tokenizer(prompt, return_tensors="pt").to(device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=120,
        do_sample=True,
        temperature=0.8,
        logits_processor=logits_processor,
        pad_token_id=tokenizer.eos_token_id,
    )

generated_text = tokenizer.decode(
    outputs[0],
    skip_special_tokens=True,
)

print("\nGenerated text:")
print(generated_text)



# Проверяем, какие токены блокируются,
# если контекст совпадает с началом запрещённого слова.

for seq in sorted(processor.bad_sequences):
    if len(seq) < 2:
        continue

    prefix = seq[:-1]
    expected_blocked_token = seq[-1]

    test_input = torch.tensor(
        [prefix], dtype=torch.long, device=device
    )

    with torch.no_grad():
        scores = model(test_input).logits[:, -1, :]

    processed_scores = processor(
        test_input,
        scores.clone()
    )

    blocked = torch.isneginf(
        processed_scores[0, expected_blocked_token]
    ).item()

    print(
        f"{tokenizer.decode(list(seq))!r}: "
        f"запрет сработал = {blocked}"
    )