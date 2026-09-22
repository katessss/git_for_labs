

import argparse
import re
import sys

import nltk
import pymorphy3
from nltk.tokenize import sent_tokenize, word_tokenize

morph = pymorphy3.MorphAnalyzer()
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)


#  NOUN — существительное, ADJF - полное прилагательное
TARGET_POS = {"NOUN", "ADJF"}

# Токен считается словом, если состоит из кириллических букв (допускается дефис)
WORD_RE = re.compile(r"^[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*$")

# Приведение «вторых» падежей pymorphy3 к основным
CASE_NORMALIZATION = {
    "gen1": "gent", "gen2": "gent",   # чашка чаю -> родительный
    "acc2": "accs",                    # в солдаты -> винительный
    "loc1": "loct", "loc2": "loct",   # в лесу -> предложный
    "voct": "nomn",                    # звательный -> именительный
}


def noun_adj_parses(word):
    parses = morph.parse(word)
    if parses[0].tag.POS not in TARGET_POS:
        return []
    return [p for p in parses if p.tag.POS in TARGET_POS and "Abbr" not in p.tag]


def best_agreeing(word1, word2):
    best, best_score = None, -1.0
    for p1 in noun_adj_parses(word1):
        for p2 in noun_adj_parses(word2):
            score = p1.score * p2.score
            if score > best_score and agree(p1, p2):
                best, best_score = (p1, p2), score
    return best


def case_of(tag):
    return CASE_NORMALIZATION.get(tag.case, tag.case)


def genders_match(t1, t2):
    if t1.number == "plur":
        return True
    g1, g2 = t1.gender, t2.gender
    if "ms-f" in str(t1) or "ms-f" in str(t2): 
        return g1 in (None, "masc", "femn") and g2 in (None, "masc", "femn")
    return g1 is not None and g1 == g2


def agree(p1, p2):
    # Совпадают ли два разбора по роду, числу и падежу
    t1, t2 = p1.tag, p2.tag
    if t1.POS not in TARGET_POS or t2.POS not in TARGET_POS:
        return False
    if t1.number is None or t1.number != t2.number:
        return False
    if case_of(t1) is None or case_of(t1) != case_of(t2):
        return False
    return genders_match(t1, t2)


def find_pairs(text):
    """Сегментация -> токенизация -> поиск согласованных пар соседних слов."""
    pairs = []
    for sentence in sent_tokenize(text, language="russian"):
        tokens = word_tokenize(sentence, language="russian")
        for left, right in zip(tokens, tokens[1:]):
            if not (WORD_RE.match(left) and WORD_RE.match(right)):
                continue
            match = best_agreeing(left, right)
            if match:
                pairs.append((left, right, *match))
    return pairs


def main():
    file_path = "text.txt"
    with open(file_path, encoding="utf-8") as f:
        text = f.read()

    pairs = find_pairs(text)
    for left, right, p1, p2 in pairs:
        line = f"{p1.normal_form} {p2.normal_form}"
        line += f"\t<- {left} {right}\t[{p1.tag} | {p2.tag}]"
        print(line)
        print(f"\nВсего пар: {len(pairs)}")


if __name__ == "__main__":
    main()
