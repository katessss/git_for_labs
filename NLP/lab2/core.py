import argparse
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors, Word2Vec


def load_model(model_path: str):
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл модели не найден: {model_path}")

    if path.suffix == ".model":
        return Word2Vec.load(str(path)).wv

    return KeyedVectors.load_word2vec_format(
        str(path),
        binary=path.suffix.lower() in {".bin", ".gz"},
    )


class NounWord2Vec:
    def __init__(self, model):
        self.model = model
        self.nouns = [w for w in model.key_to_index if w.endswith("_NOUN")]
        self.noun_set = set(self.nouns)
        print(f"Модель загружена: {len(model.key_to_index)} слов")
        print(f"Существительных (NOUN): {len(self.nouns)}")

    def normalize_word(self, word: str) -> str:
        word = word.strip()
        if word in self.noun_set:
            return word
        noun = f"{word}_NOUN"
        if noun in self.noun_set:
            return noun
        raise KeyError(f"Существительное '{word}' отсутствует в модели.")

    def vector(self, word: str):
        return self.model.get_vector(self.normalize_word(word))

    def most_similar(self, positive=None, negative=None, topn=10):
        positive = [self.normalize_word(w) for w in (positive or [])]
        negative = [self.normalize_word(w) for w in (negative or [])]

        results = self.model.most_similar(
            positive=positive,
            negative=negative,
            topn=topn * 5,
        )
        return [(w, s) for w, s in results if w in self.noun_set][:topn]

    def most_similar_to_vector(self, vector, topn=10, exclude=None):
        exclude = {self.normalize_word(w) for w in (exclude or [])}
        results = self.model.similar_by_vector(vector, topn=topn * 5)
        return [(w, s) for w, s in results
                if w in self.noun_set and w not in exclude][:topn]

    def all_nouns(self):
        return sorted(self.nouns)


def find_combination(model, target1, target2, verbose=False):
    target1 = model.normalize_word(target1)
    target2 = model.normalize_word(target2)
    v1, v2 = model.vector(target1), model.vector(target2)

    best = None
    best_score = float("inf")

    def evaluate(vector, expression, exclude=None):
        nonlocal best, best_score
        results = model.most_similar_to_vector(vector, 10, exclude)
        words = [w for w, _ in results]
        if target1 in words and target2 in words:
            r1, r2 = words.index(target1) + 1, words.index(target2) + 1
            score = r1 + r2
            if score < best_score:
                best_score = score
                best = (expression, r1, r2, results)
                if verbose:
                    print(f"{expression}: {target1}->{r1}, {target2}->{r2}", file=sys.stderr)

    for alpha in [-3, -2, -1, 1, 2, 3]:
        for beta in [-3, -2, -1, 1, 2, 3]:
            evaluate(alpha * v1 + beta * v2,
                     f"{alpha:.1f}·{target1} + {beta:.1f}·{target2}")

    near1 = model.most_similar([target1], topn=30)
    near2 = model.most_similar([target2], topn=30)
    near_sum = model.most_similar([target1, target2], topn=30)
    candidates = {w for w, _ in near1 + near2 + near_sum}

    for w in candidates - {target1, target2}:
        vw = model.vector(w)
        evaluate(vw, w, {w})
        evaluate(vw + v1, f"{w} + {target1}", {w})
        evaluate(vw + v2, f"{w} + {target2}", {w})
        evaluate(vw + v1 - v2, f"{w} + {target1} - {target2}", {w})
        evaluate(vw - v1 + v2, f"{w} - {target1} + {target2}", {w})

    for w1, _ in near_sum[:15]:
        for w2, _ in near_sum[:15]:
            if w1 == w2 or w1 in {target1, target2} or w2 in {target1, target2}:
                continue
            evaluate(model.vector(w1) + model.vector(w2), f"{w1} + {w2}", {w1, w2})
            evaluate(model.vector(w1) - model.vector(w2), f"{w1} - {w2}", {w1, w2})

    return best


def parse_expression(expression, model):
    positive, negative = [], []
    tokens = expression.replace("+", " + ").replace("-", " - ").split()
    sign = "+"
    for token in tokens:
        if token in {"+", "-"}:
            sign = token
        else:
            word = model.normalize_word(token)
            (positive if sign == "+" else negative).append(word)
    return positive, negative


def interactive(model):
    print("\nИнтерактивный режим")
    print("  слово1 + слово2 - слово3")
    print("  find слово1 слово2")
    print("  list")
    print("  exit\n")

    while True:
        try:
            line = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in {"exit", "quit", "q"}:
            break
        if line == "list":
            for i, w in enumerate(model.all_nouns(), 1):
                print(f"{w:30}", end="\n" if i % 4 == 0 else "")
            print()
            continue
        if line.startswith("find "):
            parts = line.split()
            if len(parts) != 3:
                print("Использование: find слово1 слово2")
                continue
            try:
                result = find_combination(model, parts[1], parts[2], True)
            except KeyError as e:
                print(e)
                continue
            if result:
                expression, r1, r2, results = result
                print(f"\nФормула: {expression}")
                print(f"Позиции: {parts[1]} -> {r1}, {parts[2]} -> {r2}\n")
                for i, (w, s) in enumerate(results, 1):
                    mark = " <- цель" if w in {model.normalize_word(parts[1]), model.normalize_word(parts[2])} else ""
                    print(f"{i:2d}. {w:30s} {s:.4f}{mark}")
            else:
                print("Не удалось найти комбинацию, где оба слова в top-10.")
            continue
        try:
            positive, negative = parse_expression(line, model)
            results = model.most_similar(positive, negative, 10)
            expression = " + ".join(positive)
            if negative:
                expression += (" - " if expression else "") + " - ".join(negative)
            print(f"\n10 ближайших к ({expression}):")
            for i, (w, s) in enumerate(results, 1):
                print(f"{i:2d}. {w:30s} {s:.4f}")
        except KeyError as e:
            print(e)


def main():
    parser = argparse.ArgumentParser(description="Линейные операции над Word2Vec-векторами существительных через Gensim.")
    parser.add_argument("model", help="Путь к Word2Vec-модели (.model, .bin, .txt)")
    parser.add_argument("--sim", help="10 ближайших существительных к слову")
    parser.add_argument("--pos", nargs="+", help="Слова со знаком +")
    parser.add_argument("--neg", nargs="+", help="Слова со знаком -")
    parser.add_argument("--find", nargs=2, metavar=("W1", "W2"), help="Подобрать комбинацию для пары")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    try:
        model = NounWord2Vec(load_model(args.model))
    except Exception as e:
        print(f"Ошибка загрузки модели: {e}", file=sys.stderr)
        sys.exit(1)

    if args.sim:
        try:
            word = model.normalize_word(args.sim)
            results = model.most_similar([word], topn=10)
        except KeyError as e:
            print(e, file=sys.stderr); sys.exit(1)
        print(f"\n10 ближайших существительных к '{word}':")
        for i, (w, s) in enumerate(results, 1):
            print(f"{i:2d}. {w:30s} {s:.4f}")
        return

    if args.pos or args.neg:
        try:
            results = model.most_similar(args.pos or [], args.neg or [], 10)
        except KeyError as e:
            print(e, file=sys.stderr); sys.exit(1)
        expr = " + ".join(args.pos or [])
        if args.neg:
            expr += (" - " if expr else "") + " - ".join(args.neg)
        print(f"\n10 ближайших существительных к ({expr}):")
        for i, (w, s) in enumerate(results, 1):
            print(f"{i:2d}. {w:30s} {s:.4f}")
        return

    if args.find:
        try:
            result = find_combination(model, args.find[0], args.find[1], args.verbose)
        except KeyError as e:
            print(e, file=sys.stderr); sys.exit(1)
        if result:
            expression, r1, r2, results = result
            print(f"\nФормула: {expression}")
            print(f"Позиции: {args.find[0]} -> {r1}, {args.find[1]} -> {r2}\n")
            for i, (w, s) in enumerate(results, 1):
                mark = " <- цель" if w in {model.normalize_word(args.find[0]), model.normalize_word(args.find[1])} else ""
                print(f"{i:2d}. {w:30s} {s:.4f}{mark}")
        else:
            print("Не удалось найти комбинацию.")
        return

    interactive(model)


if __name__ == "__main__":
    main()
