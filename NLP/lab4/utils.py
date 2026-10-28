
import re
from IPython.display import display
from collections import Counter
import pandas as pd

from .promts import words

def find_progress_with_pos(text):
    pos = 0
    found = []

    for word in words:
        match = re.search(
            r'(?<!\w)' + re.escape(word) + r'(?!\w)',
            text[pos:],
            re.IGNORECASE
        )

        if match is None:
            return found, word

        pos += match.end()
        found.append(word)

    return found, None


def find_progress(text):
    normalized_text = text.casefold().replace("ё", "е")

    found = []
    missing = []

    for word in words:
        normalized_word = word.casefold().replace("ё", "е")

        pattern = r'(?<!\w)' + re.escape(normalized_word) + r'(?!\w)'

        if re.search(pattern, normalized_text):
            found.append(word)
        else:
            missing.append(word)

    return found, missing


def print_stats(stats):
    if not stats:
        return

    df = pd.DataFrame(stats)
    total = len(df)

    print(f"\n{'=' * 60}")
    print(f"СТАТИСТИКА: завершено {total} операций")
    print(f"{'=' * 60}")

    print(f"Среднее число найденных слов: "
          f"{df['found_count'].mean():.2f} / {len(words)}")

    print(f"Медиана: {df['found_count'].median():.0f} / {len(words)}")
    print(f"Лучший результат: {df['found_count'].max()} / {len(words)}")

    print("\nДоля генераций по количеству найденных слов:")
    distribution = (
        df["found_count"]
        .value_counts()
        .sort_index()
        .rename_axis("Найдено слов")
        .to_frame("Количество")
    )
    distribution["Доля, %"] = (
        distribution["Количество"] / total * 100
    ).round(1)
    display(distribution)

    print("\nЧастота каждого слова:")
    word_counts = Counter(
        word
        for found_list in df["found"]
        for word in found_list
    )

    word_stats = pd.DataFrame([
        {
            "Слово": word,
            "Найдено раз": word_counts[word],
            "Доля генераций, %": round(
                word_counts[word] / total * 100, 1
            ),
        }
        for word in words
    ]).sort_values("Доля генераций, %")

    display(word_stats)

    print("\nРезультаты по промптам:")
    prompt_stats = (
        df.groupby("prompt_id")
        .agg(
            Операций=("found_count", "size"),
            Среднее=("found_count", "mean"),
            Максимум=("found_count", "max"),
        )
        .round(2)
        .sort_values("Среднее", ascending=False)
    )
    display(prompt_stats)

    print("\nРезультаты по параметрам генерации:")
    
    params_stats = (
        df.groupby([
            "temperature",
            "top_k",
            "no_repeat_ngram_size"
        ])
        .agg(
            Операций=("found_count", "size"),
            Среднее=("found_count", "mean"),
            Медиана=("found_count", "median"),
            Максимум=("found_count", "max"),
            Успехов=("success", "sum"),
        )
        .round(2)
        .sort_values(
            ["Среднее", "Максимум"],
            ascending=False
        )
    )
    
    display(params_stats)
