#!/usr/bin/env python3
"""Tests for build_relations.py against a small simulated world (no network).

Run from the repository root:  python3 -m unittest tools/test_build_relations.py
"""
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_relations as br  # noqa: E402


def claim(qid):
    return {'mainsnak': {'datavalue': {'value': {'id': qid}}}}


def year(y):
    return {'mainsnak': {'datavalue': {'value': {'time': f'+{y:04d}-01-01T00:00:00Z'}}}}


def person(qid, label, occ, born, died=None, links=30, aliases=(), mbid=None, desc='composer', **rels):
    claims = {'P31': [claim('Q5')], 'P106': [claim(o) for o in occ], 'P569': [year(born)]}
    if died:
        claims['P570'] = [year(died)]
    if mbid:
        claims['P434'] = [{'mainsnak': {'datavalue': {'value': mbid}}}]
    for prop, targets in rels.items():
        claims[br.PROPS[prop]] = [claim(t) for t in targets]
    return {'id': qid, 'labels': {'en': {'value': label}}, 'aliases': {'en': [{'value': a} for a in aliases]},
            'descriptions': {'en': {'value': desc}},
            'claims': claims, 'sitelinks': {f'site{i}': {} for i in range(links)}}


COMPOSER, SINGER, OPERA_SINGER = 'Q36834', 'Q177220', 'Q2865819'
ENTITIES = {
    'Q1': person('Q1', 'Léonin', [COMPOSER], 1135, 1201, links=25, movement=['Q500']),
    'Q2': person('Q2', 'Pérotin', [COMPOSER], 1160, 1230, links=28, student_of=['Q1'], movement=['Q500']),
    'Q99': {'id': 'Q99', 'labels': {'en': {'value': 'Pérotin (crater)'}}, 'claims': {'P31': [claim('Q55')]}, 'sitelinks': {}},
    'Q3': person('Q3', 'Hildegard of Bingen', [COMPOSER], 1098, 1179, links=90, influenced_by=['Q8'], country=['Q600']),
    'Q4': person('Q4', 'Richard Wagner', [COMPOSER, 'Q158852'], 1813, 1883, links=150, mbid='mb-wagner',
                 genre=['Q1344'], country=['Q601'], sibling=['Q25']),
    'Q40': {'id': 'Q40', 'labels': {'en': {'value': 'Wagner (band)'}}, 'claims': {'P31': [claim('Q215380')]}, 'sitelinks': {}},
    'Q5': person('Q5', 'Maria Callas', [OPERA_SINGER, SINGER], 1923, 1977, links=100, mbid='mb-callas', voice=['Q700']),
    # new artists found by the expansion queries
    'Q6': person('Q6', 'Engelbert Humperdinck', [COMPOSER], 1854, 1921, links=55, mbid='mb-humperdinck',
                 genre=['Q1344', 'Q501'], country=['Q601']),
    'Q7': person('Q7', 'Renata Tebaldi', [OPERA_SINGER], 1922, 2004, links=45, voice=['Q700'], country=['Q602']),
    'Q8': person('Q8', 'Bernard of Clairvaux', [COMPOSER], 1090, 1153, links=20),
    'Q9': person('Q9', 'No Dates Person', [COMPOSER], 1900, links=60),
    'Q10': person('Q10', 'Johann Wolfgang von Goethe', [COMPOSER, 'Q36180'], 1749, 1832, links=200,
                  desc='German writer, artist, natural scientist and politician (1749–1832)'),
    'Q11': person('Q11', 'Louis Armstrong', [COMPOSER, SINGER], 1901, 1971, links=150, desc='American jazz trumpeter and singer'),
    'Q12': person('Q12', 'Young Prodigy', [COMPOSER], 1995, links=41, desc='British composer', genre=['Q506']),
    # classical evidence by genre/movement *names*; Max Richter only via the include list (31 editions)
    'Q20': person('Q20', 'Max Richter', [COMPOSER], 1966, links=31, desc='British composer (born 1966)', genre=['Q507', 'Q504']),
    'Q21': person('Q21', 'Pop Writer', [COMPOSER], 1960, links=90, desc='English composer', genre=['Q505']),
    'Q22': person('Q22', 'Genreless Composer', [COMPOSER], 1950, links=80, desc='Brazilian composer'),
    'Q23': person('Q23', 'Postminimal Composer', [COMPOSER], 1960, links=50, desc='Danish composer', genre=['Q504']),
    'Q24': person('Q24', 'Hans Richter', ['Q158852'], 1843, 1916, links=48,
                  desc='Austrian-Hungarian orchestral and operatic conductor (1843-1916)'),
    # family-only neighbour born after 1850 without a classical genre: needs evidence like anyone else
    'Q25': person('Q25', 'Wagner Relative', [COMPOSER], 1900, links=20, desc='German composer'),
    'Q13': person('Q13', 'Johann Pachelbel', [COMPOSER], 1653, 1706, links=70, desc='German Baroque composer', movement=['Q502']),
    'Q14': person('Q14', 'Album Performer', [COMPOSER], 1950, links=10),
    'Q16': person('Q16', 'Jean-Jacques Rousseau', [COMPOSER], 1712, 1778, links=180,
                  desc='Genevan philosopher, writer and composer (1712–1778)'),
    'Q17': person('Q17', 'Dual Role Musician', [COMPOSER], 1700, 1760, links=45, desc='Italian composer and philosopher'),
    'Q15': person('Q15', 'Rocky Pianist', ['Q486748'], 1950, links=50, desc='American pianist', genre=['Q503']),
}
del ENTITIES['Q9']['claims']['P569']
ENTITIES['Q5']['descriptions']['en']['value'] = 'American-born Greek soprano'
ENTITIES['Q7']['descriptions']['en']['value'] = 'Italian soprano'
LABELS = {'Q500': 'Notre-Dame school', 'Q501': 'Romantic music', 'Q1344': 'opera', 'Q600': 'Holy Roman Empire',
          'Q601': 'Germany', 'Q602': 'Italy', 'Q700': 'soprano', 'Q502': 'Baroque music', 'Q503': 'rock music',
          'Q504': 'postminimalism', 'Q505': 'pop music', 'Q506': 'contemporary classical music', 'Q507': 'ambient music'}
# Only used for names without an exact match (the fallback search)
SEARCH = {'Léonin': ['Q1'], 'Pérotin': ['Q99', 'Q2'], 'Hildegard von Bingen': ['Q3'],
          'Richard Wagner': ['Q40', 'Q4'], 'Maria Callas': ['Q5']}


ENTITY_URI = 'http://www.wikidata.org/entity/'


def sparql_value(v):
    if isinstance(v, dict) and v.get('id'):
        return {'type': 'uri', 'value': ENTITY_URI + v['id']}
    if isinstance(v, dict) and v.get('time'):
        return {'type': 'literal', 'value': v['time'].lstrip('+')}
    return {'type': 'literal', 'value': v}


def fake_sparql(query):
    """Answer the builder's query shapes from ENTITIES, like the Wikidata query service would."""
    items = re.findall(r'wd:(Q\d+)', query.split('VALUES ?item', 1)[1].split('}', 1)[0]) if 'VALUES ?item' in query else []
    rows = []
    if 'VALUES ?name' in query:  # exact name matching
        names = {json.loads('"' + n + '"') for n in re.findall(r'"((?:[^"\\]|\\.)*)"@en', query)}
        for q, e in ENTITIES.items():
            if 'Q5' not in [c['mainsnak']['datavalue']['value']['id'] for c in e['claims'].get('P31', [])]:
                continue
            for n in [e['labels']['en']['value']] + [a['value'] for a in e.get('aliases', {}).get('en', [])]:
                if n in names:
                    rows.append({'name': {'value': n}, 'item': {'value': ENTITY_URI + q}})
    elif 'VALUES ?prop' in query:  # facts about people
        props = re.findall(r'wdt:(P\d+)', query.split('VALUES ?prop', 1)[1].split('}', 1)[0])
        for q in items:
            for prop, claims in ENTITIES.get(q, {}).get('claims', {}).items():
                if prop in props:
                    for c in claims:
                        rows.append({'item': {'value': ENTITY_URI + q}, 'prop': {'value': 'http://www.wikidata.org/prop/direct/' + prop},
                                     'value': sparql_value(c['mainsnak']['datavalue']['value'])})
    elif '?mul' in query:  # names, aliases, number of Wikipedia editions
        for q in items:
            e = ENTITIES.get(q)
            if not e:
                continue
            base = {'item': {'value': ENTITY_URI + q}, 'label': {'value': e['labels']['en']['value'], 'xml:lang': 'en'},
                    'links': {'value': str(len(e.get('sitelinks', {})))}}
            if e.get('descriptions'):
                base['desc'] = {'value': e['descriptions']['en']['value']}
            aliases = [a['value'] for a in e.get('aliases', {}).get('en', [])]
            rows += [dict(base, alias={'value': a}) for a in aliases] or [base]
    elif 'SELECT ?item ?label WHERE' in query:  # names of countries, movements...
        for q in items:
            lab = LABELS.get(q) or ENTITIES.get(q, {}).get('labels', {}).get('en', {}).get('value')
            if lab:
                rows.append({'item': {'value': ENTITY_URI + q}, 'label': {'value': lab, 'xml:lang': 'en'}})
    elif 'wd:Q36834 ; wikibase:sitelinks' in query:
        rows = [{'item': {'value': ENTITY_URI + i}, 'links': {'value': str(n)}}
                for i, n in [('Q10', 200), ('Q16', 180), ('Q11', 150), ('Q21', 90), ('Q22', 80), ('Q13', 70), ('Q6', 55),
                             ('Q9', 60), ('Q3', 90), ('Q23', 50), ('Q17', 45), ('Q12', 41)]]
    elif 'wd:Q158852 ; wikibase:sitelinks' in query:
        rows = [{'item': {'value': ENTITY_URI + 'Q24'}, 'links': {'value': '48'}}]
    elif 'wd:Q2865819 ; wikibase:sitelinks' in query:
        rows = [{'item': {'value': ENTITY_URI + 'Q7'}, 'links': {'value': '45'}}]
    elif 'wd:Q486748 ; wikibase:sitelinks' in query:
        rows = [{'item': {'value': ENTITY_URI + 'Q15'}, 'links': {'value': '50'}}]
    elif 'wdt:P86 ?composer' in query:
        rows = [{'composer': {'value': ENTITY_URI + 'Q4'}, 'performer': {'value': ENTITY_URI + 'Q5'}, 'workLabel': {'value': 'Tristan und Isolde'}},
                {'composer': {'value': ENTITY_URI + 'Q4'}, 'performer': {'value': ENTITY_URI + 'Q12345'}, 'workLabel': {'value': 'Parsifal'}},
                # a composer credited as "performer" (as on album entries): ignored
                {'composer': {'value': ENTITY_URI + 'Q4'}, 'performer': {'value': ENTITY_URI + 'Q2'}, 'workLabel': {'value': 'Wagner Album'}}]
    return json.dumps({'results': {'bindings': rows}})


class FakeHttp(br.Http):
    """Answers like the real services would; counts requests so caching can be checked."""

    def __init__(self, cache_dir, **kw):
        super().__init__(cache_dir, **kw)
        self.default_interval = 0
        self.min_interval = {}
        self.requests = []

    def fetch_raw(self, url, headers):
        self.requests.append(url)
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        if u.hostname == 'www.wikidata.org' and q.get('action') == ['wbsearchentities']:
            return json.dumps({'search': [{'id': i} for i in SEARCH.get(q['search'][0], [])]})
        if u.hostname == 'query.wikidata.org':
            return fake_sparql(q['query'][0])
        if u.hostname == 'musicbrainz.org':
            if '/artist/mb-humperdinck' in u.path:
                return json.dumps({'relations': [{'type': 'teacher', 'direction': 'backward', 'artist': {'id': 'mb-wagner'}},
                                                 {'type': 'parent', 'direction': 'backward', 'artist': {'id': 'mb-callas'}},
                                                 {'type': 'is person', 'artist': {'id': 'mb-callas'}}]})
            return json.dumps({'relations': []})
        if u.hostname == 'labs.api.listenbrainz.org':
            if q['artist_mbids'] == ['mb-wagner']:
                return json.dumps([{'artist_mbid': '125ec42a-7229-4250-afc5-e057484327fe', 'name': '[unknown]', 'type': 'Other', 'score': 784},
                                   {'artist_mbid': 'mb-unknown', 'type': 'Person', 'score': 100},
                                   {'artist_mbid': 'mb-callas', 'type': 'Person', 'score': 50}])
            return json.dumps([])
        if u.hostname == 'archive.org':
            if 'Léonin' in q['q'][0]:
                return json.dumps({'response': {'docs': [
                    {'creator': 'Léonin; Pérotin', 'title': 'Magnus liber organi'},
                    {'creator': ['Perotin', 'Leonin'], 'title': 'Viderunt omnes'},
                    {'creator': 'Léonin', 'title': 'Organum'}]}})
            return json.dumps({'response': {'docs': []}})
        raise AssertionError('unexpected request ' + url)


class BuildRelationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        kb = [
            {'id': 'Léonin', 'key': 'leonin', 'type': 'Composer', 'era': 1170, 'tags': ['Medieval'], 'is_master': True},
            {'id': 'Pérotin', 'key': 'perotin', 'type': 'Composer', 'era': 1200, 'tags': ['Medieval'], 'is_master': True},
            {'id': 'Hildegard von Bingen', 'key': 'hildegard', 'type': 'Composer', 'era': 1150, 'tags': ['Medieval', 'Sacred']},
            {'id': 'Richard Wagner', 'key': 'wagner', 'type': 'Composer', 'era': 1870, 'tags': ['Opera'], 'aliases': ['Wagner']},
            {'id': 'Maria Callas', 'key': 'callas', 'type': 'Singer', 'era': 1955, 'tags': ['Opera']},
            {'id': 'Johann Pachelbel', 'key': 'pachelbel', 'type': 'Composer', 'era': 1850, 'tags': ['Romantic', 'Secondary']},
        ]
        with open(os.path.join(self.root, 'knowledge_base.json'), 'w', encoding='utf-8') as f:
            json.dump(kb, f)

    def tearDown(self):
        self.tmp.cleanup()

    def run_build(self, *extra, offline=False):
        args = br.parse_args(['--root', self.root, *extra])
        http = FakeHttp(args.cache, offline=offline)
        kb, rel, report = br.build(args, http)
        return kb, rel, report, http

    def edge(self, rel, a, b):
        key = tuple(sorted((a, b)))
        return next((e for e in rel['edges'] if (e['a'], e['b']) == key), None)

    def test_full_build(self):
        kb, rel, report, _ = self.run_build()
        by_id = {a['id']: a for a in kb}
        # matching picks the person, not the crater or the band
        self.assertEqual(by_id['Pérotin']['qid'], 'Q2')
        self.assertEqual(by_id['Richard Wagner']['qid'], 'Q4')
        # no exact name match ("Hildegard of Bingen" on Wikidata): found by the fallback search
        self.assertEqual(by_id['Hildegard von Bingen']['qid'], 'Q3')
        # expansion: new composer/singer/neighbour added, known and undated ones not
        self.assertIn('Engelbert Humperdinck', by_id)
        self.assertIn('Renata Tebaldi', by_id)
        self.assertIn('Bernard of Clairvaux', by_id)  # Hildegard's influence
        self.assertNotIn('No Dates Person', by_id)
        # not classical musicians: a writer, a jazz musician, a rock pianist
        self.assertNotIn('Johann Wolfgang von Goethe', by_id)
        self.assertNotIn('Louis Armstrong', by_id)
        self.assertNotIn('Rocky Pianist', by_id)
        self.assertNotIn('Jean-Jacques Rousseau', by_id)  # composer only as a later role
        self.assertIn('Dual Role Musician', by_id)  # composer first: kept
        # genre names: postminimalism counts as classical; pop or no genre at all doesn't (born after 1850)
        self.assertIn('Postminimal Composer', by_id)
        self.assertNotIn('Pop Writer', by_id)
        self.assertNotIn('Genreless Composer', by_id)
        # family alone doesn't exempt from the evidence check (teachers, students and influences do)
        self.assertNotIn('Wagner Relative', by_id)
        # "orchestral and operatic conductor" is a musical role
        self.assertIn('Hans Richter', by_id)
        # under 40 Wikipedia editions and not in any query: not added without the include list
        self.assertNotIn('Max Richter', by_id)
        self.assertEqual(by_id['Young Prodigy']['era'], br.CURRENT_YEAR)  # born 1995: era capped, not 2035
        # placeholder entry: matched despite its made-up era, then corrected; not duplicated
        p = by_id['Johann Pachelbel']
        self.assertEqual((p['qid'], p['era']), ('Q13', 1693))
        self.assertEqual(p['tags'], ['Baroque', 'Secondary'])
        self.assertFalse(any(a['id'].startswith('Johann Pachelbel (') for a in kb))
        self.assertEqual(sum(1 for a in kb if a['id'] == 'Hildegard von Bingen'), 1)
        h = by_id['Engelbert Humperdinck']
        self.assertEqual((h['type'], h['era'], h['source']), ('Composer', 1894, 'wikidata'))
        self.assertEqual(h['tags'], ['Opera', 'Romantic', 'German'])
        self.assertEqual(by_id['Renata Tebaldi']['tags'], ['Opera', 'Soprano', 'Italian'])  # Opera first: drives Within Tag/Radio
        self.assertEqual(by_id['Bernard of Clairvaux']['tags'], ['Medieval'])  # period from era
        # attributes for shared-context similarity
        self.assertEqual(by_id['Pérotin']['attrs']['movement'], ['Notre-Dame school'])
        self.assertEqual(by_id['Hildegard von Bingen']['attrs']['country'], ['German'])
        self.assertEqual((by_id['Richard Wagner']['born'], by_id['Richard Wagner']['mbid']), (1813, 'mb-wagner'))
        # relations with evidence
        e = self.edge(rel, 'Léonin', 'Pérotin')
        self.assertEqual(e['s']['teacher'], 1.0)
        self.assertIn('Pérotin studied with Léonin', e['why'])
        self.assertEqual(e['s']['cooccur'], 0.2)  # named together on 2 recordings
        self.assertIn('Léonin and Pérotin appear together on 2 archive.org recordings', e['why'])
        self.assertIn('Hildegard von Bingen was influenced by Bernard of Clairvaux',
                      self.edge(rel, 'Hildegard von Bingen', 'Bernard of Clairvaux')['why'])
        wc = self.edge(rel, 'Richard Wagner', 'Maria Callas')
        self.assertIn("Maria Callas performed Richard Wagner's Tristan und Isolde", wc['why'])
        self.assertNotIn('performed', (self.edge(rel, 'Richard Wagner', 'Pérotin') or {'s': {}})['s'])  # composer, not performer
        self.assertEqual(wc['s']['listen'], 0.5)  # 50 of a top score of 100
        self.assertIn('Engelbert Humperdinck studied with Richard Wagner',
                      self.edge(rel, 'Engelbert Humperdinck', 'Richard Wagner')['why'])  # MusicBrainz
        self.assertEqual(self.edge(rel, 'Engelbert Humperdinck', 'Maria Callas')['why'],
                         ['Maria Callas was the parent of Engelbert Humperdinck'])  # 'is person' ignored, parent direction kept
        # files
        self.assertTrue(os.path.exists(os.path.join(self.root, 'knowledge_base.json.bak')))
        with open(os.path.join(self.root, 'relations.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['edges'], rel['edges'])
        with open(os.path.join(self.root, 'tools', 'relations_report.md'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('No Dates Person', text)
        self.assertIn('Johann Wolfgang von Goethe (Q10): not a classical musician: described as "German writer', text)
        self.assertIn('Louis Armstrong (Q11): not a classical musician: jazz', text)
        self.assertIn('Johann Pachelbel: era 1850 -> 1693, tags Romantic -> Baroque', text)
        self.assertIn('Genreless Composer (Q22): not a classical musician: no classical genre or movement (genres: none)', text)
        self.assertIn('Engelbert Humperdinck (Composer, 1854–1921, 55 Wikipedia editions)', text)

    def test_second_run_uses_cache_and_is_stable(self):
        kb1, rel1, _, _ = self.run_build()
        kb2, rel2, _, http = self.run_build(offline=True)  # would raise on any uncached request
        self.assertEqual(rel1['edges'], rel2['edges'])
        self.assertEqual([a['id'] for a in kb2], [a['id'] for a in kb1])  # same artists, no duplicates on a re-run
        self.assertEqual(len(kb2), 13)  # 6 curated + 7 added
        self.assertEqual(http.requests, [])

    def test_include_list(self):
        os.makedirs(os.path.join(self.root, 'tools'), exist_ok=True)
        with open(os.path.join(self.root, 'tools', 'wikidata_overrides.json'), 'w', encoding='utf-8') as f:
            json.dump({'include': ['Max Richter', 'Nobody Of This Name']}, f)
        kb, rel, report, _ = self.run_build('--max-new', '1')
        by_id = {a['id']: a for a in kb}
        r = by_id.get('Max Richter')
        self.assertIsNotNone(r)  # added although under the notability cut-off and over --max-new
        self.assertEqual((r['qid'], r['type'], r['source']), ('Q20', 'Composer', 'wikidata'))
        self.assertTrue(any('Nobody Of This Name' in w for w in report['warnings']))

    def test_overrides_and_no_expand(self):
        os.makedirs(os.path.join(self.root, 'tools'), exist_ok=True)
        with open(os.path.join(self.root, 'tools', 'wikidata_overrides.json'), 'w', encoding='utf-8') as f:
            json.dump({'Maria Callas': None}, f)
        kb, rel, report, _ = self.run_build('--no-expand', '--no-musicbrainz', '--no-listenbrainz', '--no-cooccurrence')
        self.assertEqual(len(kb), 6)
        self.assertNotIn('qid', next(a for a in kb if a['id'] == 'Maria Callas'))
        self.assertIn('Maria Callas (override: never match)', report['unmatched'])
        self.assertIsNone(self.edge(rel, 'Richard Wagner', 'Maria Callas'))

    def test_rate_limited_api_does_not_stop_the_build(self):
        class RateLimited(FakeHttp):
            def fetch_raw(self, url, headers):
                if 'www.wikidata.org/w/api.php' in url:
                    raise br.urllib.error.HTTPError(url, 429, 'Too Many Requests', {'Retry-After': '1'}, None)
                return super().fetch_raw(url, headers)
        args = br.parse_args(['--root', self.root, '--no-expand'])
        real_sleep = br.time.sleep
        br.time.sleep = lambda s: None
        try:
            kb, rel, report = br.build(args, RateLimited(args.cache))
        finally:
            br.time.sleep = real_sleep
        by_id = {a['id']: a for a in kb}
        self.assertEqual(by_id['Pérotin']['qid'], 'Q2')  # batch matching needs no API
        self.assertNotIn('qid', by_id['Hildegard von Bingen'])  # only the API search could find her
        self.assertTrue(any('Hildegard von Bingen' in w and 'run again' in w for w in report['warnings']))
        self.assertIsNotNone(self.edge(rel, 'Léonin', 'Pérotin'))

    def test_batch_matching_outage_falls_back_to_search(self):
        class NoBatch(FakeHttp):
            def fetch_raw(self, url, headers):
                if 'query.wikidata.org' in url and 'VALUES+%3Fname' in url:
                    raise br.urllib.error.HTTPError(url, 503, 'Service Unavailable', {'Retry-After': '1'}, None)
                return super().fetch_raw(url, headers)
        args = br.parse_args(['--root', self.root, '--no-expand'])
        real_sleep = br.time.sleep
        br.time.sleep = lambda s: None
        try:
            kb, rel, report = br.build(args, NoBatch(args.cache))
        finally:
            br.time.sleep = real_sleep
        by_id = {a['id']: a for a in kb}
        self.assertTrue(any('batch name matching failed' in w for w in report['warnings']))
        self.assertEqual(by_id['Pérotin']['qid'], 'Q2')  # found by the per-artist search instead
        self.assertEqual(by_id['Hildegard von Bingen']['qid'], 'Q3')

    def test_listenbrainz_outage_is_skipped(self):
        class Broken(FakeHttp):
            def fetch_raw(self, url, headers):
                if 'listenbrainz' in url:
                    raise br.urllib.error.HTTPError(url, 404, 'gone', None, None)
                return super().fetch_raw(url, headers)
        args = br.parse_args(['--root', self.root])
        kb, rel, report = br.build(args, Broken(args.cache))
        self.assertTrue(any('ListenBrainz' in w for w in report['warnings']))
        self.assertIsNotNone(self.edge(rel, 'Léonin', 'Pérotin'))


    def test_classical_filter(self):
        labels = {'G1': 'symphonic metal', 'G2': 'Indian classical music', 'G3': 'postminimalism'}

        def check(desc, genres=(), occupations=('Q36834',)):
            e = {'description': desc, 'genre': list(genres), 'movement': [], 'occupation': list(occupations)}
            return br.classical_musician(e, labels, needs_evidence=True)[0]

        self.assertTrue(check('British composer', ['G3']))
        self.assertFalse(check('Dutch singer', ['G1']))                       # symphonic metal
        self.assertFalse(check('Indian playback singer (1924–1980)', ['G2']))
        self.assertFalse(check('American composer and conductor'))            # no evidence at all
        self.assertTrue(check('American composer and conductor', occupations=['Q36834', 'Q1415090']))
        # a noun with an adjective ending is still the first role
        self.assertEqual(br.first_role('American politician and composer'), 'American politician')
        self.assertEqual(br.first_role('German historian and composer'), 'German historian')
        self.assertEqual(br.first_role('Austrian-Hungarian orchestral and operatic conductor (1843-1916)'),
                         'Austrian-Hungarian orchestral and operatic conductor')
        self.assertEqual(br.first_role('Italian and French composer'), 'Italian and French composer')

    def test_include_lookup_outage_does_not_stop_the_build(self):
        os.makedirs(os.path.join(self.root, 'tools'), exist_ok=True)
        with open(os.path.join(self.root, 'tools', 'wikidata_overrides.json'), 'w', encoding='utf-8') as f:
            json.dump({'include': ['Max Richter']}, f)

        class NoIncludeLookup(FakeHttp):
            def fetch_raw(self, url, headers):
                if 'query.wikidata.org' in url and 'VALUES+%3Fname' in url and 'Max+Richter' in url:
                    raise br.urllib.error.HTTPError(url, 503, 'Service Unavailable', {'Retry-After': '1'}, None)
                return super().fetch_raw(url, headers)
        args = br.parse_args(['--root', self.root])
        real_sleep = br.time.sleep
        br.time.sleep = lambda s: None
        try:
            kb, rel, report = br.build(args, NoIncludeLookup(args.cache))
        finally:
            br.time.sleep = real_sleep
        by_id = {a['id']: a for a in kb}
        self.assertNotIn('Max Richter', by_id)
        self.assertIn('Engelbert Humperdinck', by_id)  # the rest of the build went ahead
        self.assertTrue(any('include list: name lookup failed' in w for w in report['warnings']))

if __name__ == '__main__':
    unittest.main()
