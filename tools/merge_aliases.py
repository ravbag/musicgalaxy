#!/usr/bin/env python3
"""Merge duplicate entries in knowledge_base.json that name the same person.

Each canonical entry absorbs its aliases:
  - id/key come from the canonical (full) name; merged names go into `aliases`
  - era/temp come from the master entry when there is one (its values were curated;
    several non-master duplicates carry a placeholder era of 1850)
  - is_master is true if any merged entry was a master
  - tags, collections and meta lists are unioned
  - related lists are unioned, renamed to canonical ids, deduplicated (max weight wins)
    and capped at RELATED_CAP
Every `related` reference in the whole file is rewritten to the canonical id.

Usage: python3 tools/merge_aliases.py [knowledge_base.json]
The file is rewritten in place. Running it again is a no-op.
"""
import json
import sys

RELATED_CAP = 12

# canonical id -> names that refer to the same person
ALIASES = {
    "Guillaume de Machaut": ["Machaut"],
    "Giovanni Pierluigi da Palestrina": ["Palestrina"],
    "Carlo Gesualdo": ["Gesualdo"],
    "Claudio Monteverdi": ["Monteverdi"],
    "Johann Sebastian Bach": ["J.S. Bach"],
    "George Frideric Handel": ["Handel"],
    "Antonio Vivaldi": ["Vivaldi"],
    "Henry Purcell": ["Purcell"],
    "Domenico Scarlatti": ["D. Scarlatti"],
    "Arcangelo Corelli": ["Corelli"],
    "Jean-Philippe Rameau": ["Rameau"],
    "Georg Philipp Telemann": ["Telemann"],
    "Dieterich Buxtehude": ["Buxtehude"],
    "Franz Joseph Haydn": ["Haydn"],
    "Wolfgang Amadeus Mozart": ["Mozart"],
    "Ludwig van Beethoven": ["Beethoven"],
    "Christoph Willibald Gluck": ["Gluck"],
    "Muzio Clementi": ["Clementi"],
    "Luigi Boccherini": ["Boccherini"],
    "Franz Schubert": ["Schubert"],
    "Frédéric Chopin": ["Chopin", "Frederick Chopin"],
    "Robert Schumann": ["Schumann"],
    "Johannes Brahms": ["Brahms"],
    "Richard Wagner": ["Wagner"],
    "Giuseppe Verdi": ["Verdi"],
    "Hector Berlioz": ["Berlioz"],
    "Franz Liszt": ["Liszt"],
    "Pyotr Ilyich Tchaikovsky": ["Tchaikovsky"],
    "Felix Mendelssohn": ["Mendelssohn"],
    "Giacomo Puccini": ["Puccini"],
    "Gioachino Rossini": ["Rossini", "Gioacchino Rossini"],
    "Gaetano Donizetti": ["Donizetti"],
    "Vincenzo Bellini": ["Bellini"],
    "Modest Mussorgsky": ["Mussorgsky"],
    "Antonín Dvořák": ["Dvořák"],
    "Edvard Grieg": ["Grieg"],
    "Georges Bizet": ["Bizet"],
    "Anton Bruckner": ["Bruckner"],
    "Gustav Mahler": ["Mahler"],
    "Jean Sibelius": ["Sibelius"],
    "Camille Saint-Saëns": ["Saint-Saëns"],
    "Sergei Rachmaninoff": ["Rachmaninoff"],
    "Gabriel Fauré": ["Fauré"],
    "Claude Debussy": ["Debussy"],
    "Maurice Ravel": ["Ravel"],
    "Igor Stravinsky": ["Stravinsky"],
    "Arnold Schoenberg": ["Schoenberg"],
    "Béla Bartók": ["Bartók"],
    "Dmitri Shostakovich": ["Shostakovich"],
    "Sergei Prokofiev": ["Prokofiev"],
    "George Gershwin": ["Gershwin"],
    "Benjamin Britten": ["Britten"],
    "Aaron Copland": ["Copland"],
    "Olivier Messiaen": ["Messiaen"],
    "György Ligeti": ["Ligeti"],
    "Krzysztof Penderecki": ["Penderecki"],
    "Ralph Vaughan Williams": ["Vaughan Williams"],
    "Alexander Scriabin": ["Scriabin"],
    "Charles Ives": ["Ives"],
    "Erik Satie": ["Satie"],
    "Dietrich Fischer-Dieskau": ["Fischer-Dieskau"],
    "Luciano Pavarotti": ["Pavarotti"],
    "Feodor Chaliapin": ["Fjodor Chaliapin"],
    "Janet Baker": ["Dame Janet Baker"],
    "Wilhelm Furtwängler": ["Furtwängler"],
    "Giovanni Battista Pergolesi": ["Giovanni Pergolesi"],
    "Leoš Janáček": ["Léoš Janáček"],
    "Alexander von Zemlinsky": ["Alexander Zemlinsky"],
}


def union(*lists):
    out = []
    for lst in lists:
        for x in lst or []:
            if x not in out:
                out.append(x)
    return out


def merge(group):
    """group[0] is the canonical entry, the rest are aliases."""
    canon = group[0]
    master = next((n for n in group if n.get("is_master")), canon)
    merged = dict(canon)
    merged["is_master"] = any(n.get("is_master") for n in group)
    merged["era"] = master["era"]
    merged["temp"] = master["temp"]
    merged["tags"] = union(*(n.get("tags") for n in group))
    merged["collections"] = union(*(n.get("collections") for n in group))
    merged["meta"] = {
        k: union(*((n.get("meta") or {}).get(k) for n in group))
        for k in union(*((n.get("meta") or {}).keys() for n in group))
    }
    merged["aliases"] = union(canon.get("aliases"), *([n["id"]] + (n.get("aliases") or []) for n in group[1:]))
    merged["related"] = [r for n in group for r in n.get("related") or []]
    return merged


def main(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    by_id = {n["id"]: n for n in data}

    rename = {}
    for canon, aliases in ALIASES.items():
        for a in aliases:
            rename[a] = canon

    out = []
    for n in data:
        if n["id"] in rename:
            continue  # absorbed into its canonical entry
        if n["id"] in ALIASES:
            group = [n] + [by_id[a] for a in ALIASES[n["id"]] if a in by_id]
            n = merge(group)
        out.append(n)

    for n in out:
        best = {}
        for r in n.get("related") or []:
            rid = rename.get(r["id"], r["id"])
            if rid == n["id"]:
                continue
            if rid not in best or r.get("w", 0) > best[rid].get("w", 0):
                best[rid] = dict(r, id=rid)
        n["related"] = sorted(best.values(), key=lambda r: -r.get("w", 0))[:RELATED_CAP]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"{len(data)} -> {len(out)} entries")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "knowledge_base.json")
