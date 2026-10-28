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
    input = tokenizer(text, return_tensors="pt") # разбиваем текст на токены и создаем тензор, pt 
    mask_index = torch.where(
        input["input_ids"][0] == tokenizer.mask_token_id 
    )
    # input_ids — это двумерный тензор: [количество предложений, количество токенов], 
    # поэтому мы берем первый элемент (первое предложение) и ищем индекс токена [MASK]

    output = model(**input) # запускаем модель на входных данных, получаем выходные данные
    # ** - специальный синтаксис Python для распаковки словаря. по сути там: 
    # "input_ids": ids, "attention_mask": mask

    logits = output.logits # логиты - сырые оценки модели для всех токенов словаря на каждой позиции предложения.
    softmax = F.softmax(logits, dim=-1) # превращаем logits в вероятности
    # для каждой позиции в предложении отдельно распределить вероятности между всеми словами словаря.
    # У logits примерно такая структура: [количество предложений, количество токенов, размер словаря]
    mask_word = softmax[0, mask_index[0], :] #Берём вероятности только для [MASK]
    # : - означает, что мы хотим взять все элементы по этому измерению (в данном случае все токены словаря)
    # то есть Для первого предложения взять позицию [MASK] и получить вероятности всех слов словаря.

    top = torch.topk(mask_word, 10) 

    words = [
        tokenizer.decode([token]).strip()
        for token in top.indices[0] 
    ]

    print("\n", text)
    print(words)

    if "перед" in words and "является" in words:
        print(">>> НАШЛИ!")