from transformers import BertTokenizer, BertForMaskedLM
from torch.nn import functional as F
import torch

name = 'bert-base-multilingual-uncased'

tokenizer = BertTokenizer.from_pretrained(name)
model = BertForMaskedLM.from_pretrained(name, return_dict=True)

sentences = [
    "Это [MASK] важной частью проекта.",
    "Он находился [MASK] выбором.",
    "Этот объект [MASK] зданием."
]

for text in sentences:
    input = tokenizer(text, return_tensors="pt")
    mask_index = torch.where(
        input["input_ids"][0] == tokenizer.mask_token_id
    )

    output = model(**input)

    logits = output.logits
    softmax = F.softmax(logits, dim=-1)
    mask_word = softmax[0, mask_index[0], :]

    top = torch.topk(mask_word, 10)

    words = [
        tokenizer.decode([token]).strip()
        for token in top.indices[0]
    ]

    print("\n", text)
    print(words)

    if "перед" in words and "является" in words:
        print(">>> НАШЛИ!")