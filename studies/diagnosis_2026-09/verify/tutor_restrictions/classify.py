"""Independent legality check of tutor_cast events.
Restrictions hand-coded from Forge 2.0.13 card scripts (ChangeType$ of the
Library-origin ChangeZone), target facts from engine/card_cache.json."""
import json, os, glob, collections, re, sys
S = os.path.dirname(os.path.abspath(__file__))
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
cache = json.load(open(ROOT + '/engine/card_cache.json', encoding='utf-8'))


def fact(n):
    f = cache.get(n.lower())
    if f is None:
        f = cache.get(n.split(' // ')[0].lower())
    return f


def T(f): return (f.get('type_line') or '')
def front_type(f): return T(f).split(' // ')[0]
def has(f, *types): return any(t in front_type(f) for t in types)
def mv(f): return f.get('cmc') or 0
def green(f): return 'G' in (f.get('colors') if f.get('colors') is not None else [])
def legendary(f): return 'Legendary' in front_type(f)
def perm(f): return any(t in front_type(f) for t in ('Creature', 'Artifact', 'Enchantment', 'Planeswalker', 'Land', 'Battle'))


def power(f):
    try:
        return int(f.get('power'))
    except Exception:
        return 99


ANY = lambda f: True
# name: (predicate on target, how the search happens, conditional-on-X/board flag)
# how: spell = casting the spell searches; etb = ETB trigger searches on cast;
#      ab = only a later activated ability searches; pw = loyalty ability after cast;
#      nosearch = casting the SPELL never searches (transmute / typecycling are
#      not spells, and castableSpell() only returns sa.isSpell()).
R = {
    'Beseech the Mirror': (ANY, 'spell', 0),
    'Demonic Tutor': (ANY, 'spell', 0), 'Grim Tutor': (ANY, 'spell', 0),
    'Diabolic Intent': (ANY, 'spell', 0), 'Gamble': (ANY, 'spell', 0),
    'Imperial Seal': (ANY, 'spell', 0), 'Vampiric Tutor': (ANY, 'spell', 0),
    'Long-Term Plans': (ANY, 'spell', 0), 'Intuition': (ANY, 'spell', 0),
    'Gifts Ungiven': (ANY, 'spell', 0), 'Lively Dirge': (ANY, 'spell', 0),
    'Demonic Counsel': (ANY, 'spell', 1),
    'Wishclaw Talisman': (ANY, 'ab', 0),
    'Razaketh, the Foulblooded': (ANY, 'ab', 0),
    'Bilbo, Birthday Celebrant': (lambda f: has(f, 'Creature'), 'ab', 1),
    'Birthing Pod': (lambda f: has(f, 'Creature'), 'ab', 1),
    'Captain Sisay': (legendary, 'ab', 0),
    'Sisay, Weatherlight Captain': (lambda f: legendary(f) and perm(f), 'ab', 1),
    'Yisan, the Wanderer Bard': (lambda f: has(f, 'Creature'), 'ab', 1),
    'Kuldotha Forgemaster': (lambda f: has(f, 'Artifact'), 'ab', 0),
    'Moggcatcher': (lambda f: perm(f) and 'Goblin' in T(f), 'ab', 0),
    'Transmutation Font': (lambda f: has(f, 'Artifact'), 'ab', 1),
    'Chord of Calling': (lambda f: has(f, 'Creature'), 'spell', 1),
    "Eladamri's Call": (lambda f: has(f, 'Creature'), 'spell', 0),
    'Shared Summons': (lambda f: has(f, 'Creature'), 'spell', 0),
    'Sylvan Tutor': (lambda f: has(f, 'Creature'), 'spell', 0),
    'Worldly Tutor': (lambda f: has(f, 'Creature'), 'spell', 0),
    'Tooth and Nail': (lambda f: has(f, 'Creature'), 'spell', 0),
    'Eldritch Evolution': (lambda f: has(f, 'Creature'), 'spell', 1),
    'Neoform': (lambda f: has(f, 'Creature'), 'spell', 1),
    "Nature's Rhythm": (lambda f: has(f, 'Creature'), 'spell', 1),
    "Green Sun's Zenith": (lambda f: has(f, 'Creature') and green(f), 'spell', 1),
    'Natural Order': (lambda f: has(f, 'Creature') and green(f), 'spell', 0),
    "Summoner's Pact": (lambda f: has(f, 'Creature') and green(f), 'spell', 0),
    'Time of Need': (lambda f: has(f, 'Creature') and legendary(f), 'spell', 0),
    'Enlightened Tutor': (lambda f: has(f, 'Artifact', 'Enchantment'), 'spell', 0),
    'Idyllic Tutor': (lambda f: has(f, 'Enchantment'), 'spell', 0),
    'Mystical Tutor': (lambda f: has(f, 'Instant', 'Sorcery'), 'spell', 0),
    'Solve the Equation': (lambda f: has(f, 'Instant', 'Sorcery'), 'spell', 0),
    'Reckless Handling': (lambda f: has(f, 'Artifact'), 'spell', 0),
    'Transmute Artifact': (lambda f: has(f, 'Artifact'), 'spell', 1),
    'Wargate': (perm, 'spell', 1),
    'Fierce Empath': (lambda f: has(f, 'Creature') and mv(f) >= 6, 'etb', 0),
    'Formidable Speaker': (lambda f: has(f, 'Creature'), 'etb', 0),
    'Goblin Engineer': (lambda f: has(f, 'Artifact'), 'etb', 0),
    'Goblin Matron': (lambda f: 'Goblin' in T(f), 'etb', 0),
    'Imperial Recruiter': (lambda f: has(f, 'Creature') and power(f) <= 2, 'etb', 0),
    'Moon-Blessed Cleric': (lambda f: has(f, 'Enchantment'), 'etb', 0),
    'Ranger-Captain of Eos': (lambda f: has(f, 'Creature') and mv(f) <= 1, 'etb', 0),
    'Sand Scout': (lambda f: 'Desert' in T(f), 'etb', 1),
    'Spellseeker': (lambda f: has(f, 'Instant', 'Sorcery') and mv(f) <= 2, 'etb', 0),
    "Thalia's Lancers": (legendary, 'etb', 0),
    'Trinket Mage': (lambda f: has(f, 'Artifact') and mv(f) <= 1, 'etb', 0),
    'Trophy Mage': (lambda f: has(f, 'Artifact') and mv(f) == 3, 'etb', 0),
    'Woodland Bellower': (lambda f: has(f, 'Creature') and green(f) and not legendary(f) and mv(f) <= 3, 'etb', 0),
    'Nahiri, the Harbinger': (lambda f: has(f, 'Artifact', 'Creature'), 'pw', 1),
    'Tezzeret the Seeker': (lambda f: has(f, 'Artifact'), 'pw', 1),
    'Tezzeret, Cruel Captain': (lambda f: has(f, 'Artifact') and mv(f) <= 1, 'pw', 0),
    "Vivien, Monsters' Advocate": (lambda f: has(f, 'Creature'), 'pw', 1),
    'Dizzy Spell': (lambda f: mv(f) == 1, 'nosearch', 0),
    'Muddle the Mixture': (lambda f: mv(f) == 2, 'nosearch', 0),
    'Drift of Phantasms': (lambda f: mv(f) == 3, 'nosearch', 0),
    'Step Through': (lambda f: 'Wizard' in T(f), 'nosearch', 0),
}

files = glob.glob(ROOT + '/studies/**/*.jsonl', recursive=True)
rows = []
for fp in files:
    with open(fp, encoding='utf-8') as fh:
        for line in fh:
            if '"tutor_cast"' not in line:
                continue
            r = json.loads(line)
            if r.get('event') != 'tutor_cast':
                continue
            t, _, m = r['detail'].partition(' seeking ')
            rows.append((os.path.relpath(fp, ROOT).replace('\\', '/'), t, m, r))
print('events', len(rows), 'files scanned', len(files))
missing_t = collections.Counter(); missing_f = collections.Counter()
cls = collections.Counter(); pairs = collections.defaultdict(collections.Counter)
bydir = collections.defaultdict(collections.Counter)
byhow = collections.Counter()
for fp, t, m, r in rows:
    if t not in R:
        missing_t[t] += 1; cls['unk_tutor'] += 1; continue
    f = fact(m)
    if f is None:
        missing_f[m] += 1; cls['unk_target'] += 1; continue
    pred, how, cond = R[t]
    legal = bool(pred(f))
    k = 'ILLEGAL' if not legal else ('legal_cond' if cond else 'legal')
    cls[k] += 1
    byhow[(k, how)] += 1
    pairs[k][(t, m)] += 1
    d = '/'.join(fp.split('/')[1:3])
    bydir[d][k] += 1
    bydir[d]['total'] += 1
print('missing tutors', missing_t)
print('missing target facts', missing_f)
tot = sum(cls.values())
for k, v in sorted(cls.items()):
    print(f'{v:5d} {k} {v/tot:.1%}')
print('--- by (class, how)')
for k, v in sorted(byhow.items()):
    print(v, k)
print('--- top illegal pairs')
for (t, m), v in pairs['ILLEGAL'].most_common(45):
    print(v, t, '->', m, '|', front_type(fact(m)), '| mv', mv(fact(m)))
print('--- by dir')
for d, c in sorted(bydir.items()):
    print(d, dict(c))
json.dump({'illegal': [[t, m, v] for (t, m), v in pairs['ILLEGAL'].most_common()],
           'legal_cond': [[t, m, v] for (t, m), v in pairs['legal_cond'].most_common()]},
          open(os.path.join(S, 'illegal_pairs.json'), 'w'), indent=0)
