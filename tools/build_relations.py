#!/usr/bin/env python3
"""Build MusicGalaxy's relatedness database from open sources.

What it does
  1. Matches every artist in knowledge_base.json to Wikidata (and, through Wikidata, MusicBrainz).
  2. Adds more artists: notable classical composers, conductors, opera singers and instrumentalists
     from Wikidata, plus teachers/students/influences of artists already in the database.
  3. Collects evidence of how artists are related:
       - Wikidata: teacher/student, "influenced by", family, works by one artist performed by another,
         and shared context (movement, genre, instrument, voice type, country, ensembles/employers)
       - MusicBrainz: artist relationships (teacher, family, collaboration, supporting musician)
       - ListenBrainz: "similar artists" from listening data
       - archive.org: how often two artists appear on the same recording
  4. Writes
       knowledge_base.json   artists, with qid/mbid/born/died/attrs added (backup: knowledge_base.json.bak)
       relations.json        direct relations between artists, each with its evidence ("why")
       tools/relations_report.md   what was matched, skipped or uncertain - worth a read

Every web response is cached in tools/.cache, so a second run is fast and an interrupted run resumes.
Only the Python standard library is used.

Usage (from the repository root)
  python3 tools/build_relations.py                 # full build
  python3 tools/build_relations.py --max-new 200   # add fewer new artists
  python3 tools/build_relations.py --no-expand     # only relate the artists already in the database
  python3 tools/build_relations.py --help          # all options

Wrong matches can be fixed in tools/wikidata_overrides.json:
  { "Arcangelo Corelli": "Q1234567", "Some Artist": null }
  (use the id from the artist's Wikidata page in place of Q1234567; null = never match)
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = 'MusicGalaxy/0.1 (https://github.com/ravbag/musicgalaxy; relations builder)'

WIKIDATA_API = 'https://www.wikidata.org/w/api.php'
WIKIDATA_SPARQL = 'https://query.wikidata.org/sparql'
MUSICBRAINZ_API = 'https://musicbrainz.org/ws/2'
LISTENBRAINZ_SIMILAR = 'https://labs.api.listenbrainz.org/similar-artists/json'
# ListenBrainz labs names its similarity datasets after the algorithm settings; if this one has been
# retired, the step is skipped with a warning (see the report) and the build carries on.
LISTENBRAINZ_ALGORITHM = 'session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30'
ARCHIVE_SEARCH = 'https://archive.org/advancedsearch.php'

# --- Wikidata identifiers -------------------------------------------------------------------------
Q_HUMAN = 'Q5'
OCCUPATIONS = {  # app type -> Wikidata occupations
    'Composer': ['Q36834'],                                   # composer
    'Conductor': ['Q158852'],                                 # conductor
    'Singer': ['Q2865819', 'Q177220'],                        # opera singer, singer
    'Instrumentalist': ['Q486748', 'Q1259917', 'Q765778', 'Q13219637'],  # pianist, violinist, organist, cellist
}
TYPE_PRIORITY = ['Composer', 'Conductor', 'Singer', 'Instrumentalist']
MUSIC_OCCUPATIONS = {q for qs in OCCUPATIONS.values() for q in qs} | {'Q639669'}  # + musician
# Occupations used to find new artists. Generic "singer" is left out: it is mostly pop.
EXPANSION_OCCUPATIONS = {
    'Composer': 'Q36834', 'Conductor': 'Q158852', 'Singer': 'Q2865819',
    'Pianist': 'Q486748', 'Violinist': 'Q1259917', 'Organist': 'Q765778', 'Cellist': 'Q13219637',
}
NEEDS_CLASSICAL_EVIDENCE = {'Composer', 'Pianist', 'Violinist', 'Cellist'}  # also common outside classical
CLASSICAL_GENRES = ['Q9730', 'Q1344']  # classical music, opera
PRE_POP_YEAR = 1850  # anyone born before this with these occupations counts as classical

PROPS = {
    'occupation': 'P106', 'instance': 'P31', 'born': 'P569', 'died': 'P570',
    'student_of': 'P1066', 'student': 'P802', 'influenced_by': 'P737',
    'movement': 'P135', 'genre': 'P136', 'instrument': 'P1303', 'voice': 'P412',
    'country': 'P27', 'member_of': 'P463', 'employer': 'P108',
    'father': 'P22', 'mother': 'P25', 'sibling': 'P3373', 'spouse': 'P26',
    'mbid': 'P434',
}

DEFAULT_COLLECTIONS = ['classic-archives', 'unlocked-recordings', 'community_audio']
CURRENT_YEAR = datetime.date.today().year

# New artists must be described on Wikidata as a musician ("German composer", "Italian soprano")
# and not as something else first ("German writer, artist, natural scientist..."), and must not be
# a jazz/pop/rock musician. Applies only to artists the script adds, not to the curated ones.
MUSIC_DESCRIPTION = re.compile(
    r'\b(composer|musician|conductor|singer|soprano|mezzo|contralto|alto|tenor|baritone|bass-baritone|bass|basso|'
    r'countertenor|castrato|pianist|violinist|violist|cellist|organist|harpsichordist|lutenist|guitarist|flautist|'
    r'flutist|oboist|clarinettist|clarinetist|bassoonist|trumpeter|horn player|harpist|kapellmeister|music theorist|'
    r'choirmaster|cantor|troubadour|trouv[eè]re|minnesinger|madrigalist|opera|music)', re.I)
NON_CLASSICAL = re.compile(
    r'\b(jazz|rock|pop|rapper|hip[- ]hop|singer-songwriter|songwriter|disc jockey|dj|heavy metal|punk|reggae|'
    r'blues|soul|r&b|rhythm and blues|country music|funk|disco|electronic dance|bandleader|big band|swing|'
    r'schlager|flamenco|bossa nova|k-pop|j-pop|eurovision)\b', re.I)


def is_placeholder(artist):
    """The original data has ~45 stub entries with a made-up era (1850) and tags ['Romantic', 'Secondary']."""
    return artist.get('source') != 'wikidata' and artist.get('era') == 1850 and \
        sorted(artist.get('tags') or []) == ['Romantic', 'Secondary']

# Country (Wikidata label) -> the nationality adjectives the knowledge base already uses
COUNTRY_ADJECTIVE = {
    'Germany': 'German', 'German Empire': 'German', 'Kingdom of Prussia': 'German', 'Holy Roman Empire': 'German',
    'East Germany': 'German', 'West Germany': 'German', 'Kingdom of Saxony': 'German', 'Kingdom of Bavaria': 'German',
    'France': 'French', 'Kingdom of France': 'French', 'Italy': 'Italian', 'Kingdom of Italy': 'Italian',
    'Republic of Venice': 'Italian', 'Kingdom of Naples': 'Italian', 'Papal States': 'Italian',
    'Austria': 'Austrian', 'Austria-Hungary': 'Austrian', 'Austrian Empire': 'Austrian', 'Archduchy of Austria': 'Austrian',
    'Russia': 'Russian', 'Russian Empire': 'Russian', 'Soviet Union': 'Russian', 'Tsardom of Russia': 'Russian',
    'United Kingdom': 'British', 'United Kingdom of Great Britain and Ireland': 'British', 'Kingdom of Great Britain': 'British',
    'Kingdom of England': 'English', 'England': 'English', 'Scotland': 'Scottish', 'Ireland': 'Irish',
    'United States': 'American', 'United States of America': 'American', 'Canada': 'Canadian',
    'Spain': 'Spanish', 'Portugal': 'Portuguese', 'Poland': 'Polish', 'Polish–Lithuanian Commonwealth': 'Polish',
    'Hungary': 'Hungarian', 'Kingdom of Hungary': 'Hungarian', 'Czech Republic': 'Czech', 'Czechoslovakia': 'Czech',
    'Kingdom of Bohemia': 'Czech', 'Finland': 'Finnish', 'Grand Duchy of Finland': 'Finnish', 'Norway': 'Norwegian',
    'Sweden': 'Swedish', 'Denmark': 'Danish', 'Netherlands': 'Dutch', 'Dutch Republic': 'Dutch', 'Belgium': 'Belgian',
    'Switzerland': 'Swiss', 'Japan': 'Japanese', 'China': 'Chinese', "People's Republic of China": 'Chinese',
    'South Korea': 'Korean', 'Argentina': 'Argentinian', 'Brazil': 'Brazilian', 'Mexico': 'Mexican',
    'Greece': 'Greek', 'Romania': 'Romanian', 'Latvia': 'Latvian', 'Estonia': 'Estonian', 'Lithuania': 'Lithuanian',
    'Ukraine': 'Ukrainian', 'Georgia': 'Georgian', 'Armenia': 'Armenian', 'Israel': 'Israeli', 'Australia': 'Australian',
    'New Zealand': 'New Zealand', 'Iceland': 'Icelandic', 'Venezuela': 'Venezuelan', 'Cuba': 'Cuban',
}

# Wikidata movement/genre/instrument/voice labels -> knowledge-base tags (first match per rule)
LABEL_TAGS = [
    (r'medieval|ars nova|ars antiqua|notre[- ]dame', 'Medieval'), (r'renaissance', 'Renaissance'),
    (r'baroque', 'Baroque'), (r'classical period|classicism|viennese classic', 'Classical'),
    (r'late romantic', 'Late Romantic'), (r'romantic', 'Romantic'), (r'impressionis', 'Impressionism'),
    (r'neoclassic', 'Neoclassical'), (r'expressionis', 'Modernist'), (r'modernis', 'Modernist'),
    (r'serial|twelve-tone|dodecaphon', 'Serialism'), (r'avant-garde', 'Avant-Garde'),
    (r'minimal', 'Minimalism'), (r'contemporary classical|new music|contemporary music', 'Contemporary'),
    (r'opera', 'Opera'), (r'operetta', 'Operetta'), (r'lied|art song', 'Lieder'),
    (r'sacred|church music|liturgical', 'Sacred'), (r'choral|choir', 'Choral'), (r'film score|film music', 'Film'),
    (r'ballet', 'Ballet'), (r'symphon', 'Symphony'), (r'chamber music', 'Chamber'), (r'jazz', 'Jazz'),
    (r'nationalis', 'Nationalist'), (r'electronic', 'Electronic'), (r'tango', 'Tango'),
    (r'^piano$', 'Piano'), (r'harpsichord', 'Harpsichord'), (r'organ', 'Organ'), (r'^violin$', 'Violin'),
    (r'^cello$', 'Cello'), (r'guitar', 'Guitar'), (r'^flute$', 'Flute'), (r'^lute$', 'Lute'),
    (r'^soprano', 'Soprano'), (r'mezzo', 'Mezzo'), (r'^tenor', 'Tenor'), (r'^baritone', 'Baritone'),
    (r'bass-baritone', 'Bass-Baritone'), (r'^bass$|^basso', 'Bass'), (r'countertenor', 'Countertenor'),
    (r'contralto', 'Contralto'),
]
PERIOD_TAGS = {'Medieval', 'Renaissance', 'Baroque', 'Classical', 'Romantic', 'Late Romantic', 'Modernist', 'Contemporary'}


def period_for_era(era):
    if era < 1400: return 'Medieval'
    if era < 1600: return 'Renaissance'
    if era < 1750: return 'Baroque'
    if era < 1820: return 'Classical'
    if era < 1910: return 'Romantic'
    if era < 1975: return 'Modernist'
    return 'Contemporary'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def slug(s):
    return norm(s).replace(' ', '_')


def log(msg):
    print(msg, flush=True)


# --- HTTP with cache, rate limits and retries ------------------------------------------------------
class Http:
    """GET JSON with an on-disk cache. Subclass/override fetch_raw() in tests."""

    def __init__(self, cache_dir, offline=False, verbose=False):
        self.cache_dir = cache_dir
        self.offline = offline
        self.verbose = verbose
        self.network_requests = 0
        self.last_request = {}
        # Seconds between requests per host. MusicBrainz asks for <= 1/s; Wikimedia rate-limits clients that
        # aren't logged in, and shared cloud addresses even more, so Wikidata is kept to one request a second.
        self.min_interval = {'musicbrainz.org': 1.1, 'query.wikidata.org': 2.0, 'www.wikidata.org': 1.0}
        self.default_interval = 0.25
        os.makedirs(cache_dir, exist_ok=True)

    def fetch_raw(self, url, headers):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=90) as res:
            return res.read().decode('utf-8')

    def cache_path(self, key):
        return os.path.join(self.cache_dir, hashlib.sha1(key.encode()).hexdigest() + '.json')

    def cache_get(self, key):
        path = self.cache_path(key)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        return None

    def cache_put(self, key, value):
        with open(self.cache_path(key), 'w', encoding='utf-8') as f:
            json.dump(value, f)

    def get_json(self, url, headers=None, cache=True):
        if cache:
            cached = self.cache_get(url)
            if cached is not None:
                return cached
        if self.offline:
            raise RuntimeError('offline and not cached: ' + url)
        host = urllib.parse.urlparse(url).hostname or ''
        wait = self.min_interval.get(host, self.default_interval) - (time.time() - self.last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.network_requests += 1
        if self.verbose:
            log(f'    GET {url[:160]}')
        elif self.network_requests % 20 == 0:
            log(f'    ... {self.network_requests} web requests so far (now: {host})')
        hdrs = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        hdrs.update(headers or {})
        delay = 5
        attempts = 10
        for attempt in range(attempts):
            self.last_request[host] = time.time()
            try:
                data = json.loads(self.fetch_raw(url, hdrs))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    retry_after = e.headers.get('Retry-After') if e.headers else None
                    wait = min(300, int(retry_after) if retry_after and retry_after.isdigit() else delay)
                    log(f'    {host} answered {e.code}{" (rate limit)" if e.code == 429 else ""}; waiting {wait}s')
                    time.sleep(wait)
                    delay = min(300, delay * 2)
                    if e.code == 429:  # slow down for the rest of the run too
                        self.min_interval[host] = min(5.0, self.min_interval.get(host, self.default_interval) * 1.5 + 0.5)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < attempts - 1:
                    log(f'    {host}: {e}; retrying in {delay}s')
                    time.sleep(delay)
                    delay = min(300, delay * 2)
                    continue
                raise
        if cache:
            self.cache_put(url, data)
        return data


# --- Wikidata -----------------------------------------------------------------------------------------
class Wikidata:
    def __init__(self, http):
        self.http = http
        self.entities = {}   # people (full records)
        self.label_cache = {}  # anything else we only need the name of (countries, movements, ...)

    def search(self, name):
        q = urllib.parse.urlencode({'action': 'wbsearchentities', 'search': name, 'language': 'en',
                                    'type': 'item', 'limit': 7, 'format': 'json'})
        data = self.http.get_json(f'{WIKIDATA_API}?{q}')
        return [r['id'] for r in data.get('search', []) if r.get('id')]

    # Everything except the fallback name search goes through the query service (SPARQL) in batches:
    # Wikimedia rate-limits the regular API heavily for clients that aren't logged in.
    ENTITY_BATCH = 80
    LABEL_BATCH = 200
    NAME_BATCH = 50

    def load(self, qids):
        """Fetch people's facts into self.entities; returns {qid: parsed}. Cached per entity."""
        todo = []
        for q in dict.fromkeys(qids):
            if not q or q in self.entities:
                continue
            cached = self.http.cache_get('wd-entity:v2:' + q)
            if cached is None:
                todo.append(q)
            elif cached:  # {} marks an entity that doesn't exist
                self.entities[q] = cached
        for i in range(0, len(todo), self.ENTITY_BATCH):
            chunk = todo[i:i + self.ENTITY_BATCH]
            if len(todo) > self.ENTITY_BATCH:
                log(f'    Wikidata facts: {i}/{len(todo)} people')
            items = ' '.join('wd:' + q for q in chunk)
            props = ' '.join('wdt:' + p for p in PROPS.values())
            facts = self.sparql(f'''SELECT ?item ?prop ?value WHERE {{
  VALUES ?item {{ {items} }}
  VALUES ?prop {{ {props} }}
  ?item ?prop ?value .
}}''')
            meta = self.sparql(f'''SELECT ?item ?label ?mul ?links ?alias ?desc WHERE {{
  VALUES ?item {{ {items} }}
  OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?mul . FILTER(LANG(?mul) = "mul") }}
  OPTIONAL {{ ?item wikibase:sitelinks ?links }}
  OPTIONAL {{ ?item schema:description ?desc . FILTER(LANG(?desc) = "en") }}
  OPTIONAL {{ ?item skos:altLabel ?alias . FILTER(LANG(?alias) = "en") }}
}}''')
            for qid, parsed in entities_from_sparql(chunk, facts, meta).items():
                self.http.cache_put('wd-entity:v2:' + qid, parsed)
                if parsed:
                    self.entities[qid] = parsed
        return {q: self.entities[q] for q in qids if q in self.entities}

    def labels(self, qids):
        """English names of anything (countries, movements, ensembles...). Cached per entity."""
        todo = []
        for q in dict.fromkeys(qids):
            if not q or q in self.label_cache:
                continue
            cached = self.http.cache_get('wd-label:' + q)
            if cached is None:
                todo.append(q)
            elif cached.get('label'):
                self.label_cache[q] = cached['label']
        for i in range(0, len(todo), self.LABEL_BATCH):
            chunk = todo[i:i + self.LABEL_BATCH]
            if len(todo) > self.LABEL_BATCH:
                log(f'    Wikidata names of places, movements...: {i}/{len(todo)}')
            rows = self.sparql(f'''SELECT ?item ?label WHERE {{
  VALUES ?item {{ {' '.join('wd:' + q for q in chunk)} }}
  ?item rdfs:label ?label . FILTER(LANG(?label) = "en" || LANG(?label) = "mul")
}}''')
            found = {}
            for r in rows:
                qid = uri_qid(r.get('item'))
                lab = r.get('label', {})
                if qid and (qid not in found or lab.get('xml:lang') == 'en'):
                    found[qid] = lab.get('value')
            for qid in chunk:
                self.http.cache_put('wd-label:' + qid, {'label': found.get(qid)})
                if found.get(qid):
                    self.label_cache[qid] = found[qid]
        return {q: self.label_cache[q] for q in qids if q in self.label_cache}

    def match_names(self, names):
        """People whose English (or language-neutral) name or alias is exactly one of names: {name: [qid]}."""
        out = {n: [] for n in names}
        for i in range(0, len(names), self.NAME_BATCH):
            chunk = names[i:i + self.NAME_BATCH]
            log(f'    exact name matching: {i}/{len(names)} names')
            lit = lambda n: json.dumps(n, ensure_ascii=False)
            values = ' '.join(f'{lit(n)}@en {lit(n)}@mul' for n in chunk)
            rows = self.sparql(f'''SELECT DISTINCT ?name ?item WHERE {{
  VALUES ?name {{ {values} }}
  ?item rdfs:label|skos:altLabel ?name .
  ?item wdt:P31 wd:Q5 .
}}''')
            for r in rows:
                name, qid = r.get('name', {}).get('value'), uri_qid(r.get('item'))
                if name in out and qid and qid not in out[name]:
                    out[name].append(qid)
        return out

    def sparql(self, query):
        q = urllib.parse.urlencode({'query': query, 'format': 'json'})
        data = self.http.get_json(f'{WIKIDATA_SPARQL}?{q}', headers={'Accept': 'application/sparql-results+json'})
        return data.get('results', {}).get('bindings', [])


def uri_qid(binding):
    v = (binding or {}).get('value', '')
    m = re.search(r'/entity/(Q\d+)$', v)
    return m.group(1) if m else None


def sparql_year(value):
    m = re.match(r'(-?)0*(\d+)-\d\d-\d\d', value or '')
    if not m:
        return None
    y = int(m.group(2))
    return -y if m.group(1) else y


def entities_from_sparql(qids, facts, meta):
    """One record per person: label, aliases, sitelinks count, born/died years, mbid and the related
    entity ids per PROPS key. Items Wikidata doesn't know map to {}."""
    by_prop = {v: k for k, v in PROPS.items()}
    ents = {q: {'claims': defaultdict(list), 'label': None, 'mul': None, 'desc': None, 'links': 0, 'aliases': []} for q in qids}
    for r in facts:
        q = uri_qid(r.get('item'))
        prop = r.get('prop', {}).get('value', '').rsplit('/', 1)[-1]
        if q in ents and prop in by_prop:
            ents[q]['claims'][by_prop[prop]].append(r.get('value', {}))
    for r in meta:
        q = uri_qid(r.get('item'))
        if q not in ents:
            continue
        e = ents[q]
        e['label'] = e['label'] or r.get('label', {}).get('value')
        e['mul'] = e['mul'] or r.get('mul', {}).get('value')
        e['desc'] = e['desc'] or r.get('desc', {}).get('value')
        if r.get('links'):
            e['links'] = max(e['links'], int(float(r['links']['value'])))
        alias = r.get('alias', {}).get('value')
        if alias and alias not in e['aliases']:
            e['aliases'].append(alias)
    out = {}
    for q, e in ents.items():
        c = e['claims']
        if not c and not e['label'] and not e['mul']:
            out[q] = {}
            continue
        ids = lambda key: [x for x in (uri_qid(v) for v in c.get(key, [])) if x]
        first = lambda key: next((v.get('value') for v in c.get(key, [])), None)
        p = {
            'qid': q, 'label': e['label'] or e['mul'] or q, 'aliases': e['aliases'], 'sitelinks': e['links'],
            'born': next((y for y in (sparql_year(v.get('value')) for v in c.get('born', [])) if y is not None), None),
            'died': next((y for y in (sparql_year(v.get('value')) for v in c.get('died', [])) if y is not None), None),
            'mbid': first('mbid'), 'description': e['desc'] or '',
        }
        for key in ('instance', 'occupation', 'student_of', 'student', 'influenced_by', 'movement', 'genre',
                    'instrument', 'voice', 'country', 'member_of', 'employer', 'father', 'mother', 'sibling', 'spouse'):
            p[key] = list(dict.fromkeys(ids(key)))
        out[q] = p
    return out


def artist_type(ent):
    occ = set(ent['occupation'])
    for t in TYPE_PRIORITY:
        if occ & set(OCCUPATIONS[t]):
            return t
    return None


def floruit(ent):
    """The 'era' convention of the knowledge base: roughly when the person was most active."""
    b, d = ent.get('born'), ent.get('died')
    if b is not None:
        era = b + 40
        era = min(era, d - 5) if d is not None and d - 5 > b else era
    elif d is not None:
        era = d - 20
    else:
        return None
    return min(era, CURRENT_YEAR)


# --- Step 1: match existing artists ---------------------------------------------------------------
def match_score(artist, ent):
    if Q_HUMAN not in ent['instance']:
        return -99
    score = 0
    occ = set(ent['occupation'])
    if occ & set(OCCUPATIONS.get(artist.get('type'), [])):
        score += 3
    elif occ & MUSIC_OCCUPATIONS:
        score += 1
    else:
        score -= 2
    era = None if is_placeholder(artist) else artist.get('era')
    if ent['born'] is not None and isinstance(era, (int, float)):
        score += 2 if 10 <= era - ent['born'] <= 90 else -3
    names = {norm(artist['id'])} | {norm(a) for a in artist.get('aliases', [])}
    if norm(ent['label']) in names or names & {norm(a) for a in ent['aliases']}:
        score += 1
    score += min(2.0, ent['sitelinks'] / 50)
    return score


def match_existing(kb, wd, overrides, report, rematch=False):
    todo = [a for a in kb if a['id'] not in overrides and (rematch or not a.get('qid'))]
    # 1) exact name matches, many artists per query
    names = list(dict.fromkeys(n for a in todo for n in [a['id']] + [x for x in a.get('aliases', []) if ' ' in x]))
    try:
        exact = wd.match_names(names) if names else {}
        wd.load([q for qs in exact.values() for q in qs])
    except Exception as ex:  # noqa: BLE001 - fall back to one search per artist rather than stopping
        report['warnings'].append(f'Wikidata batch name matching failed ({ex}); searched artists one by one instead')
        exact = {}
    matched = 0
    for artist in kb:
        name = artist['id']
        if name in overrides:
            artist['qid'] = overrides[name]
            if artist['qid'] is None:
                artist.pop('qid')
                report['unmatched'].append(f'{name} (override: never match)')
            else:
                matched += 1
            continue
        if artist.get('qid') and not rematch:
            matched += 1
            continue
        best = None
        failed = False
        queries = [name] + [a for a in artist.get('aliases', []) if ' ' in a]
        cand_ids = list(dict.fromkeys(q for n in queries for q in exact.get(n, [])))
        scored = sorted(((match_score(artist, e), q) for q, e in wd.load(cand_ids).items()), reverse=True)
        if scored and scored[0][0] >= 3:
            best = scored
        # 2) fall back to Wikidata's search for names without a good exact match (one request each)
        for query in ([] if best else queries):
            log(f'    no exact match for {query!r}; searching Wikidata')
            try:
                cands = wd.load(wd.search(query))
            except Exception as ex:  # noqa: BLE001 - one failed lookup shouldn't stop the build
                report['warnings'].append(f'Wikidata search failed for {name} ({ex}); run again to retry')
                failed = True
                break
            scored = sorted(((match_score(artist, e), q) for q, e in cands.items()), reverse=True)
            if scored and scored[0][0] >= 3:
                best = scored
                break
        if failed:
            continue
        if not best:
            report['unmatched'].append(name)
            continue
        artist['qid'] = best[0][1]
        matched += 1
        if len(best) > 1 and best[1][0] >= best[0][0] - 1 and best[1][0] >= 3:
            e1, e2 = wd.entities[best[0][1]], wd.entities[best[1][1]]
            report['uncertain'].append(f"{name}: chose {best[0][1]} ({e1['label']}, born {e1['born']}) over "
                                       f"{best[1][1]} ({e2['label']}, born {e2['born']})")
    log(f'  matched {matched} of {len(kb)} artists '
        f'({sum(1 for v in exact.values() if v)} names matched exactly in batches)')
    return matched


# --- Step 2: find more artists ------------------------------------------------------------------------
def expansion_candidates(wd, kb, args, report):
    known = {a['qid'] for a in kb if a.get('qid')}
    found = {}
    genre_values = ' '.join('wd:' + g for g in CLASSICAL_GENRES)
    for label, occ in EXPANSION_OCCUPATIONS.items():
        classical = (f'FILTER(EXISTS {{ ?item wdt:P136 ?g . VALUES ?g {{ {genre_values} }} }} '
                     f'|| (BOUND(?born) && YEAR(?born) < {PRE_POP_YEAR}))') if label in NEEDS_CLASSICAL_EVIDENCE else ''
        query = f'''SELECT ?item ?links WHERE {{
  ?item wdt:P106 wd:{occ} ; wikibase:sitelinks ?links .
  FILTER(?links >= {args.min_sitelinks})
  ?item wdt:P31 wd:Q5 .
  OPTIONAL {{ ?item wdt:P569 ?born }}
  {classical}
}}'''
        try:
            rows = wd.sparql(query)
        except Exception as e:  # noqa: BLE001 - keep building with what we have
            report['warnings'].append(f'Wikidata query for {label}s failed ({e}); skipped')
            continue
        n = 0
        for r in rows:
            qid = r.get('item', {}).get('value', '').rsplit('/', 1)[-1]
            if qid and qid not in known:
                found[qid] = max(found.get(qid, 0), int(float(r.get('links', {}).get('value', 0))))
                n += 1
        log(f'  {label}s with >= {args.min_sitelinks} Wikipedia editions: {n} not yet in the database')
    # People directly connected to known artists (teachers, students, influences, family)
    if args.expand_neighbours:
        neighbour = Counter()
        for a in kb:
            ent = wd.entities.get(a.get('qid') or '')
            if not ent:
                continue
            for key in ('student_of', 'student', 'influenced_by', 'father', 'mother', 'sibling', 'spouse'):
                for q in ent[key]:
                    if q not in known:
                        neighbour[q] += 1
        ents = wd.load(list(neighbour))
        n = 0
        for q, e in ents.items():
            if Q_HUMAN in e['instance'] and artist_type(e) and e['sitelinks'] >= args.min_sitelinks_neighbour:
                found[q] = max(found.get(q, 0), e['sitelinks'])
                n += 1
        log(f'  connected to known artists (teachers, students, influences, family): {n}')
    return sorted(found, key=lambda q: -found[q])


def derive_tags(ent, typ, era, labels):
    tags = []
    for key in ('movement', 'genre', 'voice', 'instrument'):
        for q in ent[key]:
            lab = (labels.get(q) or '').lower()
            for pattern, tag in LABEL_TAGS:
                if re.search(pattern, lab):
                    if tag not in tags:
                        tags.append(tag)
                    break
    if typ in ('Composer', 'Instrumentalist') and era is not None and not (set(tags) & PERIOD_TAGS):
        tags.insert(0, period_for_era(era))
    if typ == 'Singer' and 'Opera' not in tags and 'Q2865819' in ent['occupation']:  # opera singer
        tags.insert(0, 'Opera')
    for adj in country_adjectives(ent, labels):
        if adj not in tags:
            tags.append(adj)
    return tags[:6]


def country_adjectives(ent, labels):
    out = []
    for q in ent['country']:
        adj = COUNTRY_ADJECTIVE.get(labels.get(q) or '')
        if adj and adj not in out:
            out.append(adj)
    return out


def classical_musician(e, labels):
    """(True, '') or (False, reason) for a candidate artist."""
    desc = e.get('description') or ''
    # The first role named must be musical: "German composer and pianist" yes, "Genevan philosopher,
    # writer and composer" (Rousseau) or "British astronomer and composer" (Herschel) no
    first_role = re.split(r',|;|\(|\band\b|\bwho\b', desc, maxsplit=1)[0]
    if not MUSIC_DESCRIPTION.search(first_role):
        return False, f'described as "{desc}"' if desc else 'no description'
    genres = ' / '.join(labels.get(g, '') for g in e['genre'])
    for text in (desc, genres):
        m = NON_CLASSICAL.search(text)
        if m:
            return False, f'{m.group(0)} ({text})'
    return True, ''


def add_new_artists(kb, wd, qids, args, report):
    ents = wd.load(qids)
    attr_labels = wd.labels([q for e in ents.values() for k in ('movement', 'genre', 'voice', 'instrument', 'country') for q in e[k]])
    taken_ids = {norm(a['id']) for a in kb} | {norm(x) for a in kb for x in a.get('aliases', [])}
    unmatched = {norm(a['id']): a for a in kb if not a.get('qid')}
    added = []
    for q in qids:
        if len(added) >= args.max_new:
            break
        e = ents.get(q)
        if not e or Q_HUMAN not in e['instance']:
            continue
        typ = artist_type(e)
        era = floruit(e)
        if not typ or era is None:
            report['skipped'].append(f"{e['label']} ({q}): no {'music occupation' if not typ else 'dates'}")
            continue
        ok, why_not = classical_musician(e, attr_labels)
        if not ok:
            report['skipped'].append(f"{e['label']} ({q}): not a classical musician: {why_not}")
            continue
        name = e['label']
        if norm(name) in unmatched:  # an existing artist the matching step missed: link it instead of duplicating
            existing = unmatched.pop(norm(name))
            existing['qid'] = q
            report['attached'].append(f"{existing['id']} -> {q} ({e.get('description') or e['label']})")
            continue
        if norm(name) in taken_ids:
            name = f"{name} ({e['born'] if e['born'] is not None else q})"
            if norm(name) in taken_ids:
                continue
        taken_ids.add(norm(name))
        aliases = [a for a in e['aliases'] if 4 <= len(a) <= 60 and ',' not in a and norm(a) not in taken_ids][:5]
        kb.append({
            'id': name, 'key': slug(name) or q.lower(), 'is_master': False, 'type': typ, 'era': era,
            'tags': derive_tags(e, typ, era, attr_labels), 'collections': list(DEFAULT_COLLECTIONS),
            'meta': {'schools': [], 'regions': country_adjectives(e, attr_labels), 'forms': [], 'styles': []},
            'related': [], 'aliases': aliases, 'qid': q, 'source': 'wikidata',
        })
        added.append(f"{name} ({typ}, {e['born'] if e['born'] is not None else '?'}–{e['died'] if e['died'] is not None else ''}, "
                     f"{e['sitelinks']} Wikipedia editions)")
    report['added'] = added
    log(f'  added {len(added)} artists')


# --- Step 3: attributes and relations ---------------------------------------------------------------
class Edges:
    def __init__(self):
        self.edges = {}

    def add(self, a, b, signal, value, why):
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        e = self.edges.setdefault(key, {'a': key[0], 'b': key[1], 's': {}, 'why': []})
        e['s'][signal] = round(max(e['s'].get(signal, 0), value), 3)
        if why and why not in e['why'] and len(e['why']) < 6:
            e['why'].append(why)

    def to_list(self):
        return sorted(self.edges.values(), key=lambda e: (e['a'], e['b']))


def fill_attributes(kb, wd, report):
    """Adds qid-derived facts to each artist: born/died/mbid and attrs used for shared-context similarity."""
    ents = wd.load([a['qid'] for a in kb if a.get('qid')])
    labels = wd.labels([q for e in ents.values()
                        for k in ('movement', 'genre', 'voice', 'instrument', 'country', 'member_of', 'employer')
                        for q in e[k]])
    for a in kb:
        e = ents.get(a.get('qid') or '')
        if not e:
            continue
        a['born'], a['died'] = e['born'], e['died']
        if e['mbid']:
            a['mbid'] = e['mbid']
        lab = lambda qs: sorted({labels[q] for q in qs if labels.get(q) and not re.fullmatch(r'Q\d+', labels[q])})
        a['attrs'] = {
            'movement': lab(e['movement']), 'genre': lab(e['genre']), 'instrument': lab(e['instrument']),
            'voice': lab(e['voice']), 'member': lab(e['member_of'] + e['employer']),
            'country': sorted(set(country_adjectives(e, labels))),
        }
        a['sitelinks'] = e['sitelinks']
        if is_placeholder(a):
            era = floruit(e)
            tags = derive_tags(e, a.get('type') or artist_type(e) or 'Composer', era, labels) if era is not None else []
            if era is not None and tags:
                report['corrected'].append(f"{a['id']}: era 1850 -> {era}, tags Romantic -> {', '.join(tags)}")
                a['era'] = era
                a['tags'] = tags + ['Secondary']
                a.setdefault('meta', {})['styles'] = [t for t in tags if t in PERIOD_TAGS]
                a['meta']['regions'] = country_adjectives(e, labels)


def wikidata_relations(kb, wd, edges, report):
    by_qid = {a['qid']: a['id'] for a in kb if a.get('qid')}
    n0 = len(edges.edges)
    for a in kb:
        e = wd.entities.get(a.get('qid') or '')
        if not e:
            continue
        me = a['id']
        for q in e['student_of']:
            if q in by_qid:
                edges.add(me, by_qid[q], 'teacher', 1.0, f'{me} studied with {by_qid[q]}')
        for q in e['student']:
            if q in by_qid:
                edges.add(me, by_qid[q], 'teacher', 1.0, f'{by_qid[q]} studied with {me}')
        for q in e['influenced_by']:
            if q in by_qid:
                edges.add(me, by_qid[q], 'influence', 1.0, f'{me} was influenced by {by_qid[q]}')
        for key, text in (('father', '{o} was the father of {me}'), ('mother', '{o} was the mother of {me}'),
                          ('sibling', '{me} and {o} were siblings'), ('spouse', '{me} and {o} were married')):
            for q in e[key]:
                if q in by_qid:
                    edges.add(me, by_qid[q], 'family', 1.0, text.format(me=me, o=by_qid[q]))
    log(f'  Wikidata people links: {len(edges.edges) - n0} pairs')

    # Works by one artist with another artist credited as performer
    composers = [a['qid'] for a in kb if a.get('qid') and a.get('type') == 'Composer']
    # Album entries credit composers as "performers" of compilations, so only singers, conductors
    # and instrumentalists count as performers here
    performers = {a['id'] for a in kb if a.get('type') in ('Singer', 'Conductor', 'Instrumentalist')}
    n1 = len(edges.edges)
    for i in range(0, len(composers), 80):
        values = ' '.join('wd:' + q for q in composers[i:i + 80])
        query = f'''SELECT ?composer ?performer ?workLabel WHERE {{
  VALUES ?composer {{ {values} }}
  ?work wdt:P86 ?composer ; wdt:P175 ?performer .
  ?performer wdt:P31 wd:Q5 .
  FILTER NOT EXISTS {{ ?work wdt:P31 wd:Q482994 }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 20000'''
        try:
            rows = wd.sparql(query)
        except Exception as ex:  # noqa: BLE001
            report['warnings'].append(f'Wikidata works query failed ({ex}); some "performed" links missing')
            continue
        for r in rows:
            c = by_qid.get(r.get('composer', {}).get('value', '').rsplit('/', 1)[-1])
            p = by_qid.get(r.get('performer', {}).get('value', '').rsplit('/', 1)[-1])
            work = r.get('workLabel', {}).get('value', '')
            if c and p and c != p and p in performers:
                why = f"{p} performed {c}'s {work}" if work and not re.fullmatch(r'Q\d+', work) else f'{p} performed works by {c}'
                edges.add(c, p, 'performed', 1.0, why)
    log(f'  Wikidata performed-works links: {len(edges.edges) - n1} new pairs')


MB_SIGNAL = {
    'teacher': 'teacher', 'parent': 'family', 'sibling': 'family', 'married': 'family',
    'collaboration': 'collab', 'member of band': 'collab', 'supporting musician': 'performed',
    'vocal supporting musician': 'performed', 'instrumental supporting musician': 'performed',
}


def musicbrainz_relations(kb, http, edges, report):
    by_mbid = {a['mbid']: a['id'] for a in kb if a.get('mbid')}
    n0, done = len(edges.edges), 0
    for a in kb:
        if not a.get('mbid'):
            continue
        try:
            data = http.get_json(f"{MUSICBRAINZ_API}/artist/{a['mbid']}?inc=artist-rels&fmt=json")
        except Exception as ex:  # noqa: BLE001
            report['warnings'].append(f"MusicBrainz lookup failed for {a['id']} ({ex})")
            continue
        done += 1
        for rel in data.get('relations', []) or []:
            other = by_mbid.get((rel.get('artist') or {}).get('id'))
            signal = MB_SIGNAL.get(rel.get('type'))
            if not other or not signal:
                continue
            me = a['id']
            if rel['type'] == 'teacher':
                why = f'{me} studied with {other}' if rel.get('direction') == 'backward' else f'{other} studied with {me}'
            elif rel['type'] == 'parent':  # forward: this artist is the parent
                why = f'{me} was the parent of {other}' if rel.get('direction') == 'forward' else f'{other} was the parent of {me}'
            elif signal == 'family':
                why = f'{me} and {other} were married' if rel['type'] == 'married' else f'{me} and {other} were siblings'
            elif signal == 'performed':
                why = f'{me} and {other} performed together'
            else:
                why = f'{me} and {other} collaborated'
            edges.add(me, other, signal, 1.0, why)
        if done % 50 == 0:
            log(f'    MusicBrainz: {done} artists looked up')
    log(f'  MusicBrainz links: {len(edges.edges) - n0} new pairs ({done} artists looked up)')


SPECIAL_PURPOSE_MBIDS = {'125ec42a-7229-4250-afc5-e057484327fe',  # [unknown]
                         '89ad4ac3-39f7-470e-963a-56509c546377',  # Various Artists
                         'f731ccc4-e22a-43af-a747-64213329e088',  # [anonymous]
                         '33cf029c-63b0-41a0-9855-be2a3665fb3b',  # [data]
                         '314e1c25-dde7-4e4d-b2f4-0a7b9f7c56dc',  # [dialogue]
                         'eec63d3c-3b81-4ad4-b1e4-7c147d4d2b61',  # [no artist]
                         '9be7f096-97ec-4615-8957-8d40b5dcbc41',  # [traditional]
                         '66ea0139-149f-4a0c-8fbf-5ea9ec4a6e49'}  # [Disney]


def listenbrainz_similar(kb, http, edges, report):
    by_mbid = {a['mbid']: a['id'] for a in kb if a.get('mbid')}
    n0 = len(edges.edges)
    for a in kb:
        if not a.get('mbid'):
            continue
        q = urllib.parse.urlencode({'artist_mbids': a['mbid'], 'algorithm': LISTENBRAINZ_ALGORITHM})
        try:
            data = http.get_json(f'{LISTENBRAINZ_SIMILAR}?{q}')
        except Exception as ex:  # noqa: BLE001
            report['warnings'].append(f'ListenBrainz similar-artists not available ({ex}); step skipped')
            return
        # Drop MusicBrainz's special-purpose entries ("[unknown]", "Various Artists"): they top the
        # scores and would shrink everyone else's when scores are scaled to the best match
        rows = [r for r in iter_dicts(data) if r.get('artist_mbid') and isinstance(r.get('score'), (int, float))
                and r['artist_mbid'] not in SPECIAL_PURPOSE_MBIDS and r.get('type') != 'Other'
                and r['artist_mbid'] != a['mbid']]
        top = max((r['score'] for r in rows), default=0)
        for r in rows:
            other = by_mbid.get(r['artist_mbid'])
            if other and top > 0:
                # one sentence per pair, whichever artist's list it was found in first
                pair = edges.edges.get(tuple(sorted((a['id'], other))))
                said = pair and any(w.startswith('listeners of ') for w in pair['why'])
                edges.add(a['id'], other, 'listen', r['score'] / top,
                          None if said else f"listeners of {a['id']} also play {other}")
    log(f'  ListenBrainz links: {len(edges.edges) - n0} new pairs')


def iter_dicts(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from iter_dicts(v)
    elif isinstance(x, list):
        for v in x:
            yield from iter_dicts(v)


def archive_cooccurrence(kb, http, edges, report):
    """Count how often other artists are named on the archive.org items found for each artist."""
    names = {}
    for a in kb:
        for n in [a['id']] + [x for x in a.get('aliases', []) if ' ' in x]:
            if len(norm(n)) >= 6:
                names[norm(n)] = a['id']
    pattern = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, names), key=len, reverse=True)) + r')\b')
    counts = Counter()
    for i, a in enumerate(kb):
        nm = a['id'].replace('"', '')
        q = urllib.parse.urlencode([('q', f'(creator:"{nm}" OR title:"{nm}") AND mediatype:audio'),
                                    ('fl[]', 'creator'), ('fl[]', 'title'), ('fl[]', 'subject'),
                                    ('rows', '100'), ('output', 'json')])
        try:
            data = http.get_json(f'{ARCHIVE_SEARCH}?{q}')
        except Exception as ex:  # noqa: BLE001
            report['warnings'].append(f"archive.org search failed for {a['id']} ({ex})")
            continue
        for doc in data.get('response', {}).get('docs', []):
            text = norm(' '.join(str(v) for k in ('creator', 'title', 'subject')
                                 for v in (doc.get(k) if isinstance(doc.get(k), list) else [doc.get(k) or ''])))
            for other in {names[m] for m in pattern.findall(text)}:
                if other != a['id']:
                    counts[tuple(sorted((a['id'], other)))] += 1
        if (i + 1) % 100 == 0:
            log(f'    archive.org: {i + 1} artists searched')
    for (x, y), c in counts.items():
        if c >= 2:
            edges.add(x, y, 'cooccur', min(1.0, c / 10), f'{x} and {y} appear together on {c} archive.org recordings')
    log(f'  archive.org co-occurrence links: {sum(1 for c in counts.values() if c >= 2)} pairs')


# --- Main ---------------------------------------------------------------------------------------------
def write_report(path, report, stats):
    lines = ['# Relations build report', '', f"Built {stats['built']}", '']
    lines += [f'- {k}: {v}' for k, v in stats['counts'].items()]
    for title, key in (('Warnings', 'warnings'), ('Not matched to Wikidata', 'unmatched'),
                       ('Uncertain matches (check, fix in tools/wikidata_overrides.json)', 'uncertain'),
                       ('Placeholder entries corrected from Wikidata', 'corrected'),
                       ('Existing artists linked during expansion', 'attached'),
                       ('Artists added', 'added'), ('Candidates skipped', 'skipped')):
        items = report.get(key) or []
        lines += ['', f'## {title} ({len(items)})', '']
        lines += [f'- {x}' for x in items] or ['(none)']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def build(args, http):
    kb_path = os.path.join(args.root, 'knowledge_base.json')
    with open(kb_path, encoding='utf-8') as f:
        kb = json.load(f)
    # Artists added by an earlier run are rebuilt from scratch, so changed filters take effect
    kb = [a for a in kb if a.get('source') != 'wikidata']
    overrides = {}
    if os.path.exists(args.overrides):
        with open(args.overrides, encoding='utf-8') as f:
            overrides = json.load(f)
    report = defaultdict(list)
    wd = Wikidata(http)

    t0 = time.time()
    step = lambda text: log(f'{text}   [{int(time.time() - t0) // 60}m{int(time.time() - t0) % 60:02d}s, '
                            f'{http.network_requests} web requests so far]')
    step('1/4 Matching artists to Wikidata...')
    match_existing(kb, wd, overrides, report, rematch=args.rematch)
    wd.load([a['qid'] for a in kb if a.get('qid')])

    n_before = len(kb)
    if args.expand:
        step('2/4 Finding more artists...')
        add_new_artists(kb, wd, expansion_candidates(wd, kb, args, report), args, report)
    else:
        step('2/4 Finding more artists: skipped (--no-expand)')

    step('3/4 Collecting relations...')
    fill_attributes(kb, wd, report)
    edges = Edges()
    wikidata_relations(kb, wd, edges, report)
    if args.musicbrainz:
        musicbrainz_relations(kb, http, edges, report)
    if args.listenbrainz:
        listenbrainz_similar(kb, http, edges, report)
    if args.cooccurrence:
        archive_cooccurrence(kb, http, edges, report)

    step('4/4 Writing files...')
    built = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    signal_counts = Counter(s for e in edges.edges.values() for s in e['s'])
    stats = {'built': built, 'counts': {
        'artists': len(kb), 'artists added': len(kb) - n_before,
        'matched to Wikidata': sum(1 for a in kb if a.get('qid')),
        'with MusicBrainz id': sum(1 for a in kb if a.get('mbid')),
        'related pairs': len(edges.edges), **{f'pairs with {k}': v for k, v in sorted(signal_counts.items())}}}
    relations = {
        'version': 1, 'built': built,
        'sources': ['Wikidata (CC0)', 'MusicBrainz (CC0)', 'ListenBrainz', 'archive.org search'],
        'signals': {
            'teacher': 'teacher and student', 'influence': 'one influenced the other', 'family': 'family',
            'performed': "one performed the other's works, or they performed together", 'collab': 'collaborated',
            'listen': 'listened to by the same people (ListenBrainz), 0-1', 'cooccur': 'named on the same archive.org recordings, 0-1',
        },
        'edges': edges.to_list(),
    }
    if not args.dry_run:
        shutil.copyfile(kb_path, kb_path + '.bak')
        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        with open(os.path.join(args.root, 'relations.json'), 'w', encoding='utf-8') as f:
            json.dump(relations, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(args.root, 'tools'), exist_ok=True)
    write_report(os.path.join(args.root, 'tools', 'relations_report.md'), report, stats)
    for k, v in stats['counts'].items():
        log(f'  {k}: {v}')
    log('Done. Read tools/relations_report.md for unmatched and uncertain artists.')
    return kb, relations, report


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=ROOT, help='repository root (default: this script\'s repo)')
    ap.add_argument('--max-new', type=int, default=500, help='most new artists to add (default 500)')
    ap.add_argument('--min-sitelinks', type=int, default=40,
                    help='how many Wikipedia language editions a new artist needs (notability; default 40)')
    ap.add_argument('--min-sitelinks-neighbour', type=int, default=15,
                    help='same, for teachers/students/influences of known artists (default 15)')
    ap.add_argument('--no-expand', dest='expand', action='store_false', help='do not add new artists')
    ap.add_argument('--no-neighbours', dest='expand_neighbours', action='store_false',
                    help='do not add teachers/students/influences of known artists')
    ap.add_argument('--no-musicbrainz', dest='musicbrainz', action='store_false')
    ap.add_argument('--no-listenbrainz', dest='listenbrainz', action='store_false')
    ap.add_argument('--no-cooccurrence', dest='cooccurrence', action='store_false', help='skip archive.org co-occurrence')
    ap.add_argument('--rematch', action='store_true', help='match artists again even if they already have a qid')
    ap.add_argument('--overrides', default=None, help='default: tools/wikidata_overrides.json')
    ap.add_argument('--cache', default=None, help='default: tools/.cache')
    ap.add_argument('--offline', action='store_true', help='use cached responses only')
    ap.add_argument('--dry-run', action='store_true', help='write only the report, not the data files')
    ap.add_argument('--verbose', action='store_true', help='print every web request')
    args = ap.parse_args(argv)
    args.overrides = args.overrides or os.path.join(args.root, 'tools', 'wikidata_overrides.json')
    args.cache = args.cache or os.path.join(args.root, 'tools', '.cache')
    return args


if __name__ == '__main__':
    a = parse_args()
    try:
        build(a, Http(a.cache, offline=a.offline, verbose=a.verbose))
    except KeyboardInterrupt:
        sys.exit('\nInterrupted. Run again to resume; finished downloads are cached in tools/.cache.')
