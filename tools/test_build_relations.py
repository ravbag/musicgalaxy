#!/usr/bin/env python3
"""Tests for build_relations.py against a small simulated world (no network).

Run from the repository root:  python3 -m unittest tools/test_build_relations.py
"""
import json
import os
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


def person(qid, label, occ, born, died=None, links=30, aliases=(), mbid=None, **rels):
    claims = {'P31': [claim('Q5')], 'P106': [claim(o) for o in occ], 'P569': [year(born)]}
    if died:
        claims['P570'] = [year(died)]
    if mbid:
        claims['P434'] = [{'mainsnak': {'datavalue': {'value': mbid}}}]
    for prop, targets in rels.items():
        claims[br.PROPS[prop]] = [claim(t) for t in targets]
    return {'id': qid, 'labels': {'en': {'value': label}}, 'aliases': {'en': [{'value': a} for a in aliases]},
            'claims': claims, 'sitelinks': {f'site{i}': {} for i in range(links)}}


COMPOSER, SINGER, OPERA_SINGER = 'Q36834', 'Q177220', 'Q2865819'
ENTITIES = {
    'Q1': person('Q1', 'Léonin', [COMPOSER], 1135, 1201, links=25, movement=['Q500']),
    'Q2': person('Q2', 'Pérotin', [COMPOSER], 1160, 1230, links=28, student_of=['Q1'], movement=['Q500']),
    'Q99': {'id': 'Q99', 'labels': {'en': {'value': 'Pérotin (crater)'}}, 'claims': {'P31': [claim('Q55')]}, 'sitelinks': {}},
    'Q3': person('Q3', 'Hildegard von Bingen', [COMPOSER], 1098, 1179, links=90, influenced_by=['Q8'], country=['Q600']),
    'Q4': person('Q4', 'Richard Wagner', [COMPOSER, 'Q158852'], 1813, 1883, links=150, mbid='mb-wagner',
                 genre=['Q1344'], country=['Q601']),
    'Q40': {'id': 'Q40', 'labels': {'en': {'value': 'Wagner (band)'}}, 'claims': {'P31': [claim('Q215380')]}, 'sitelinks': {}},
    'Q5': person('Q5', 'Maria Callas', [OPERA_SINGER, SINGER], 1923, 1977, links=100, mbid='mb-callas', voice=['Q700']),
    # new artists found by the expansion queries
    'Q6': person('Q6', 'Engelbert Humperdinck', [COMPOSER], 1854, 1921, links=55, mbid='mb-humperdinck',
                 genre=['Q1344', 'Q501'], country=['Q601']),
    'Q7': person('Q7', 'Renata Tebaldi', [OPERA_SINGER], 1922, 2004, links=45, voice=['Q700'], country=['Q602']),
    'Q8': person('Q8', 'Bernard of Clairvaux', [COMPOSER], 1090, 1153, links=20),
    'Q9': person('Q9', 'No Dates Person', [COMPOSER], 1900, links=60),
}
del ENTITIES['Q9']['claims']['P569']
LABELS = {'Q500': 'Notre-Dame school', 'Q501': 'Romantic music', 'Q1344': 'opera', 'Q600': 'Holy Roman Empire',
          'Q601': 'Germany', 'Q602': 'Italy', 'Q700': 'soprano'}
SEARCH = {'Léonin': ['Q1'], 'Pérotin': ['Q99', 'Q2'], 'Hildegard von Bingen': ['Q3'],
          'Richard Wagner': ['Q40', 'Q4'], 'Maria Callas': ['Q5']}


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
        if u.hostname == 'www.wikidata.org' and q.get('action') == ['wbgetentities']:
            ids = q['ids'][0].split('|')
            if q['props'] == ['labels']:
                return json.dumps({'entities': {i: {'id': i, 'labels': {'en': {'value': LABELS[i]}}} for i in ids if i in LABELS}})
            return json.dumps({'entities': {i: ENTITIES.get(i, {'id': i, 'missing': ''}) for i in ids}})
        if u.hostname == 'query.wikidata.org':
            query = q['query'][0]
            if 'wd:Q36834 ; wikibase:sitelinks' in query:
                rows = [('Q6', 55), ('Q9', 60), ('Q3', 90)]  # Q3 is already known, Q9 has no dates
            elif 'wd:Q2865819 ; wikibase:sitelinks' in query:
                rows = [('Q7', 45)]
            elif 'wdt:P86 ?composer' in query:
                return json.dumps({'results': {'bindings': [
                    {'composer': {'value': 'http://www.wikidata.org/entity/Q4'},
                     'performer': {'value': 'http://www.wikidata.org/entity/Q5'}, 'workLabel': {'value': 'Tristan und Isolde'}},
                    {'composer': {'value': 'http://www.wikidata.org/entity/Q4'},
                     'performer': {'value': 'http://www.wikidata.org/entity/Q12345'}, 'workLabel': {'value': 'Parsifal'}}]}})
            else:
                rows = []
            return json.dumps({'results': {'bindings': [
                {'item': {'value': f'http://www.wikidata.org/entity/{i}'}, 'links': {'value': str(n)}} for i, n in rows]}})
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
        # expansion: new composer/singer/neighbour added, known and undated ones not
        self.assertIn('Engelbert Humperdinck', by_id)
        self.assertIn('Renata Tebaldi', by_id)
        self.assertIn('Bernard of Clairvaux', by_id)  # Hildegard's influence
        self.assertNotIn('No Dates Person', by_id)
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
        self.assertIn('Engelbert Humperdinck (Composer, 1854–1921, 55 Wikipedia editions)', text)

    def test_second_run_uses_cache_and_is_stable(self):
        _, rel1, _, _ = self.run_build()
        kb2, rel2, _, http = self.run_build(offline=True)  # would raise on any uncached request
        self.assertEqual(rel1['edges'], rel2['edges'])
        self.assertEqual(len(kb2), 8)  # no duplicates added on the second run
        self.assertEqual(http.requests, [])

    def test_overrides_and_no_expand(self):
        os.makedirs(os.path.join(self.root, 'tools'), exist_ok=True)
        with open(os.path.join(self.root, 'tools', 'wikidata_overrides.json'), 'w', encoding='utf-8') as f:
            json.dump({'Maria Callas': None}, f)
        kb, rel, report, _ = self.run_build('--no-expand', '--no-musicbrainz', '--no-listenbrainz', '--no-cooccurrence')
        self.assertEqual(len(kb), 5)
        self.assertNotIn('qid', next(a for a in kb if a['id'] == 'Maria Callas'))
        self.assertIn('Maria Callas (override: never match)', report['unmatched'])
        self.assertIsNone(self.edge(rel, 'Richard Wagner', 'Maria Callas'))

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


if __name__ == '__main__':
    unittest.main()
