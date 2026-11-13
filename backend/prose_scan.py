"""
prose_scan.py — instant prose checks, no model calls
====================================================

scan(text) / scan_chunks(chunks) report:
  cliches          stock "AI-sounding" phrases (list in config/ai_cliches.txt, one per line, editable)
  overused         content words used far more often than normal for the length
  filler           filler words (just, really, suddenly, ...)
  adverbs          -ly adverbs per 1,000 words, most used
  tags             dialogue tags: plain said/asked vs. fancier ones (whispered, hissed, ...)
  repeated_starts  three or more sentences in a row starting with the same word
  patterns         habits models fall into:
                   not_but     "not X, but Y" / "It wasn't X. It was Y." (emphasis by negating something)
                   negations   narration of what doesn't happen ("she doesn't move", "he didn't answer")
                   echoes      a reply that repeats the other speaker's words as a question ("Gooner?")
                   dashes      em-dashes per 1,000 words
                   para_starts most paragraphs opening with the same word
Everything is a hint to look at, never an automatic edit.
"""

import re
from collections import Counter
from pathlib import Path

CLICHE_FILE = Path(__file__).resolve().parent / "config" / "ai_cliches.txt"

DEFAULT_CLICHES = """
# One phrase per line. Matching ignores case. A trailing * matches any word ending (shiver* = shiver, shivers, shivered).
shiver* down * spine
shiver* * down * spine
sent shiver*
barely above a whisper
voice barely a whisper
a mix of
a mixture of
eyes sparkl* with mischief
glint in * eye*
mischievous glint
ministrations
couldn't help but
can't help but
let out a breath * didn't know
breath * didn't know * holding
a testament to
tapestry of
the air thick with
air was thick with
palpable tension
the weight of * words
hung heavy in the air
hung in the air
smirk* playing on * lips
a smile tugging at
tugging at the corners of
padded over
padded across
orbs
with a newfound
newfound determination
steeled * resolve
a wave of
waves of pleasure
jolts of electricity
electricity shot through
sent a jolt
her heart skipped a beat
his heart skipped a beat
time seemed to stand still
world seemed to fade away
the world around them faded
in that moment
little did * know
it's not like that
maybe, just maybe
for what felt like an eternity
something shifted
something primal
a dance of
dance as old as time
bite your lip
bit * lip
eyes darkened with
swallowed hard
released a breath
let out a shaky breath
heart pounding in * chest
pulse quickened
a delicate dance
nestled
in the grand scheme of things
it's worth noting
navigate the complexities
delve into
embark on a journey
journey of self-discovery
unspoken understanding
an unspoken bond
the scent of * filled
smelled of sandalwood
husky voice
low growl
voice dripping with
words dripping with
oh, how the tables have turned
the game has just begun
you're playing with fire
mine, all mine
whispered in * ear
eyes wide with
# more stock lines (2.6)
smell* of ozone
scent of ozone
tang of ozone
a beat passed
after a beat
beat of silence
for a long moment
the silence stretched
silence stretched between
a comfortable silence
the tension in the room
slow and deliberate
the words hung
the words landed
landed like a
a flicker of
flicker* of something
jaw tightened
knuckles whiten*
gaze lingered
a moment too long
the ghost of a smile
ghost of a smile
not unkind
breath hitched
chest tightened
something in * chest
mouth quirked
lips quirked
a slow smile spread
smile spread across
the corner of * mouth
as if on cue
somewhere in the distance
it wasn't a question
it was not a question
half-lidded
for the first time in a long time
despite herself
despite himself
""".strip()

FILLER = ["just", "really", "very", "suddenly", "quite", "somehow", "actually", "literally", "basically",
          "simply", "totally", "completely", "absolutely", "definitely", "certainly", "rather", "somewhat",
          "began to", "started to", "seemed to", "managed to", "decided to"]

NOT_ADVERBS = {"only", "family", "early", "reply", "apply", "supply", "belly", "bully", "lily", "holy", "ugly",
               "silly", "jelly", "fly", "july", "italy", "ally", "rally", "tally", "billy", "molly", "sally",
               "emily", "kelly", "lonely", "lovely", "friendly", "elderly", "likely", "daily", "weekly", "monthly",
               "yearly", "costly", "deadly", "lively", "chilly", "hilly", "curly", "burly", "surly", "oily",
               "wily", "comply", "imply", "multiply", "rely", "ply", "sly", "fully", "dolly", "gully", "jolly",
               "folly", "holly", "wooly", "woolly", "anomaly", "assembly", "butterfly", "dragonfly", "homily",
               "melancholy", "monopoly", "rely", "smelly", "wobbly", "bubbly", "cuddly", "prickly", "sickly",
               "unlikely", "ungodly", "worldly", "orderly", "manly", "womanly", "beastly", "ghastly", "ghostly",
               "heavenly", "kindly", "leisurely", "masterly", "measly", "motherly", "fatherly", "brotherly",
               "sisterly", "neighborly", "scholarly", "shapely", "stately", "timely", "unruly", "wiggly"}

PLAIN_TAGS = {"said", "says", "say", "asked", "asks", "ask", "replied", "replies", "answered"}
FANCY_TAGS = {"whispered", "murmured", "muttered", "hissed", "growled", "purred", "breathed", "exclaimed",
              "gasped", "snapped", "barked", "chuckled", "laughed", "giggled", "sighed", "groaned", "moaned",
              "shouted", "yelled", "screamed", "cried", "sneered", "scoffed", "smirked", "grinned", "smiled",
              "teased", "drawled", "rasped", "croaked", "stammered", "stuttered", "huffed", "grumbled",
              "mumbled", "retorted", "quipped", "intoned", "declared", "demanded", "pleaded", "begged",
              "whimpered", "squealed", "chirped", "cooed", "crooned", "spat", "seethed", "bellowed", "roared"}

STOP = set("""a an the and or but if then than so to of in on at by for with from into onto over under about
as is are was were be been being am i you he she it we they me him her us them my your his its our their this that
these those there here what which who whom whose when where why how not no nor all any some each every both few
more most other such own same too can could will would shall should may might must do does did done have has had
having up down out off again further once just also very really only even still back now then like well get got
said say says asked one two said'd t s d ll re ve m don didn doesn isn wasn weren couldn wouldn shouldn won can't
it's i'm i'd i'll you're he's she's they're we're that's there's let's""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z'’]*")
QUOTE = re.compile(r"[\"“]([^\"“”\n]{1,600})[\"”]")
NEG = r"(?:isn't|wasn't|aren't|weren't|is not|was not|are not|were not|isn’t|wasn’t|aren’t|weren’t)"
NOT_BUT = [
    re.compile(r"\bnot (?:just |only |simply |merely |because )?[^.,;:!?\"“”\n]{1,40}?,? but (?:rather |because )?\w", re.I),
    re.compile(r"\b(?:it|this|that|he|she|they) " + NEG + r" [^.!?\"“”\n]{1,45}[.;]\s+(?:it|this|that|he|she|they) (?:is|was|are|were)\b", re.I),
    re.compile(r"\b(?:it|this|that) " + NEG + r" [^.!?\"“”\n—–]{1,45}\s*[—–]\s*(?:it|this|that)(?:'s| is| was)\b", re.I),
]
NEG_VERBS = ("move|moved|moving|speak|spoke|say anything|said anything|said nothing|answer|answered|respond|responded|reply|replied|"
             "look away|looked away|flinch|flinched|react|reacted|blink|blinked|breathe|breathed|turn around|turned around|"
             "pull away|pulled away|let go|look up|looked up|smile|smiled|laugh|laughed|step back|stepped back")
NEGATION = re.compile(r"\b(?:doesn't|didn't|don't|does not|did not|do not|doesn’t|didn’t|don’t|never)\s+(?:even\s+|quite\s+|immediately\s+)?(?:"
                      + NEG_VERBS + r")\b", re.I)
DASH = re.compile(r"—|\s--\s")
SENT = re.compile(r"(?<=[.!?])[\"'”’)]*\s+")


def load_cliches():
    try:
        raw = CLICHE_FILE.read_text(encoding="utf-8")
    except OSError:
        raw = DEFAULT_CLICHES
        try:
            CLICHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CLICHE_FILE.write_text(DEFAULT_CLICHES + "\n", encoding="utf-8")
        except OSError:
            pass
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append((line, _phrase_re(line)))
    return out


def _phrase_re(phrase):
    parts = []
    for tok in phrase.split():
        if tok == "*":
            parts.append(r"[\w'’]+(?:\s+[\w'’]+)?")          # one or two words
        elif tok.endswith("*"):
            parts.append(re.escape(tok[:-1]) + r"[\w'’]*")
        else:
            parts.append(re.escape(tok).replace("'", "['’]"))
    return re.compile(r"(?<![\w])" + r"\s+".join(parts) + r"(?![\w])", re.I)


def _excerpt(text, start, end, width=70):
    a = max(0, start - width // 2)
    b = min(len(text), end + width // 2)
    s = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a else "") + s + ("…" if b < len(text) else "")


def _names(text):
    """Words that are almost always capitalised (names): excluded from 'overused'."""
    caps, low = Counter(), Counter()
    for m in WORD.finditer(text):
        w = m.group(0)
        (caps if w[0].isupper() else low)[w.lower()] += 1
    return {w for w, c in caps.items() if c >= 2 and c > 3 * low.get(w, 0)}


def scan(text, label="", cliches=None):
    cliches = cliches if cliches is not None else load_cliches()
    text = text or ""
    words = [w.lower().replace("’", "'") for w in WORD.findall(text)]
    n = len(words) or 1
    found = []
    for phrase, rx in cliches:
        hits = list(rx.finditer(text))
        if hits:
            found.append({"phrase": phrase, "count": len(hits),
                          "examples": [{"label": label, "excerpt": _excerpt(text, h.start(), h.end())} for h in hits[:3]]})
    names = _names(text)
    counts = Counter(w for w in words if w not in STOP and w not in names and len(w) > 3)
    limit = max(6, n / 450)
    overused = [{"word": w, "count": c, "per10k": round(c * 10000 / n, 1)} for w, c in counts.most_common(40) if c >= limit][:15]
    low = " ".join(words)
    filler = {}
    for f in FILLER:
        c = len(re.findall(r"(?<![\w'])" + re.escape(f) + r"(?![\w'])", low))
        if c:
            filler[f] = c
    adv = Counter(w for w in words if w.endswith("ly") and len(w) > 4 and w not in NOT_ADVERBS)
    tags_plain, tags_fancy = Counter(), Counter()
    # a tag is one of the first three words after a closing quote: '..." she whispered' / '..." whispered Mara'
    for m in re.finditer(r"[,!?.…-][\"”]\s+(\w+)(?:\s+(\w+))?(?:\s+(\w+))?", text):
        for w in (g.lower() for g in m.groups() if g):
            if w in PLAIN_TAGS:
                tags_plain[w] += 1
                break
            if w in FANCY_TAGS:
                tags_fancy[w] += 1
                break
    starts, runs = [], []
    for sent in SENT.split(text):
        m = WORD.search(sent)
        starts.append((m.group(0).lower() if m else "", sent))
    i = 0
    while i < len(starts):
        j = i
        while j + 1 < len(starts) and starts[j + 1][0] == starts[i][0] and starts[i][0]:
            j += 1
        if j - i + 1 >= 3:
            runs.append({"word": starts[i][0], "run": j - i + 1, "label": label,
                         "excerpt": re.sub(r"\s+", " ", " ".join(s for _, s in starts[i:j + 1]))[:160] + "…"})
        i = j + 1
    total_tags = sum(tags_plain.values()) + sum(tags_fancy.values())
    return {
        "words": len(words), "cliches": sorted(found, key=lambda x: -x["count"]),
        "cliche_count": sum(x["count"] for x in found), "overused": overused,
        "filler": dict(sorted(filler.items(), key=lambda x: -x[1])),
        "filler_per1k": round(sum(filler.values()) * 1000 / n, 1),
        "adverbs": {"count": sum(adv.values()), "per1k": round(sum(adv.values()) * 1000 / n, 1),
                    "top": [{"word": w, "count": c} for w, c in adv.most_common(10)]},
        "tags": {"plain": sum(tags_plain.values()), "fancy": sum(tags_fancy.values()),
                 "fancy_share": round(sum(tags_fancy.values()) / total_tags, 2) if total_tags else 0,
                 "top_fancy": [{"word": w, "count": c} for w, c in tags_fancy.most_common(8)]},
        "repeated_starts": runs[:20],
        "patterns": patterns(text, label, len(words)),
    }


def _blank_quotes(text):
    """Dialogue replaced by spaces (same length, so positions still match): narration-only checks."""
    return QUOTE.sub(lambda m: " " * len(m.group(0)), text)


def _content(words):
    return [w for w in words if w not in STOP]


def patterns(text, label="", words=None):
    text = text or ""
    n = max(1, words if words is not None else len(WORD.findall(text)))
    ex = lambda m: {"label": label, "excerpt": _excerpt(text, m.start(), m.end())}
    nb, seen = [], set()
    for rx in NOT_BUT:
        for m in rx.finditer(text):
            if m.start() // 40 not in seen:
                seen.add(m.start() // 40)
                nb.append(ex(m))
    narr = _blank_quotes(text)
    neg = [ex(m) for m in NEGATION.finditer(narr)]
    # echo: a short question that repeats words of the quote right before it
    echoes, quotes = [], list(QUOTE.finditer(text))
    for prev, cur in zip(quotes, quotes[1:]):
        q = cur.group(1).strip()
        if not q.endswith("?") or len(q.split()) > 4:
            continue
        mine = _content([w.lower() for w in WORD.findall(q)])
        theirs = {w.lower() for w in WORD.findall(prev.group(1))}
        if mine and all(w in theirs for w in mine) and len(prev.group(1).split()) > len(q.split()):
            echoes.append({"label": label, "excerpt": _excerpt(text, prev.start(), cur.end(), width=20)})
    dashes = len(DASH.findall(text))
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    firsts = Counter()
    for p in paras:
        m = WORD.search(_blank_quotes(p)) if not p.lstrip().startswith(("\"", "“")) else None
        firsts[m.group(0).lower() if m else "“dialogue”"] += 1
    para_starts = [{"word": w, "count": c, "of": len(paras), "label": label}
                   for w, c in firsts.most_common(3) if len(paras) >= 5 and c / len(paras) >= 0.4]
    return {
        "not_but": {"count": len(nb), "examples": nb[:6]},
        "negations": {"count": len(neg), "per1k": round(len(neg) * 1000 / n, 1), "examples": neg[:6]},
        "echoes": {"count": len(echoes), "examples": echoes[:6]},
        "dashes": {"count": dashes, "per1k": round(dashes * 1000 / n, 1)},
        "para_starts": para_starts,
    }


def _merge_patterns(total, part):
    for k in ("not_but", "negations", "echoes"):
        total[k]["count"] += part[k]["count"]
        total[k]["examples"] = (total[k]["examples"] + part[k]["examples"])[:6]
    total["dashes"]["count"] += part["dashes"]["count"]
    total["para_starts"] = (total["para_starts"] + part["para_starts"])[:10]


def scan_chunks(chunks):
    """Whole-text report plus one line per chunk (so the worst chapters stand out)."""
    cl = load_cliches()
    full = "\n\n".join(c["text"] for c in chunks)
    report = scan(full, cliches=cl)
    # cliché examples should say which chunk they are from
    for c_entry in report["cliches"]:
        c_entry["examples"] = []
    per = []
    report["repeated_starts"] = []
    pat = {"not_but": {"count": 0, "examples": []}, "negations": {"count": 0, "examples": []},
           "echoes": {"count": 0, "examples": []}, "dashes": {"count": 0}, "para_starts": []}
    for c in chunks:
        r = scan(c["text"], c["label"], cl)
        for x in r["cliches"]:
            tgt = next(y for y in report["cliches"] if y["phrase"] == x["phrase"])
            if len(tgt["examples"]) < 3:
                tgt["examples"].extend(x["examples"][:3 - len(tgt["examples"])])
        per.append({"idx": c["idx"], "label": c["label"], "words": r["words"], "cliches": r["cliche_count"],
                    "cliches_per1k": round(r["cliche_count"] * 1000 / max(1, r["words"]), 2),
                    "adverbs_per1k": r["adverbs"]["per1k"], "filler_per1k": r["filler_per1k"],
                    "fancy_tag_share": r["tags"]["fancy_share"], "repeated_starts": len(r["repeated_starts"]),
                    "not_but": r["patterns"]["not_but"]["count"], "negations": r["patterns"]["negations"]["count"],
                    "echoes": r["patterns"]["echoes"]["count"], "dashes_per1k": r["patterns"]["dashes"]["per1k"]})
        report["repeated_starts"].extend(r["repeated_starts"])
        _merge_patterns(pat, r["patterns"])
    report["repeated_starts"] = report["repeated_starts"][:20]
    w = max(1, report["words"])
    pat["negations"]["per1k"] = round(pat["negations"]["count"] * 1000 / w, 1)
    pat["dashes"]["per1k"] = round(pat["dashes"]["count"] * 1000 / w, 1)
    report["patterns"] = pat
    report["per_chunk"] = per
    return report


REFUSAL = re.compile(r"\b(?:as an ai\b|as a language model|i can(?:no|')t (?:help|assist|create|write|fulfil|comply|provide|continue)|"
                     r"i(?:'m| am) (?:sorry|unable),? but|i(?:'m| am) not able to (?:help|create|write)|against (?:my|the) (?:guidelines|policy))", re.I)


def card_text_warnings(card, limit=6):
    """Cliché hits in the fields of a generated card: ['First message: "barely above a whisper" ×2', ...]."""
    cl = load_cliches()
    out = []
    for key, name in (("description", "Description"), ("personality", "Personality"), ("scenario", "Scenario"),
                      ("first_mes", "First message"), ("mes_example", "Example messages")):
        text = str(card.get(key) or "")
        if REFUSAL.search(text):
            out.insert(0, f"{name}: looks like the model refused or broke character (“{REFUSAL.search(text).group(0)}”)")
        r = scan(text, cliches=cl)
        for x in r["cliches"]:
            out.append(f"{name}: “{x['phrase'].replace('*', '…')}”" + (f" ×{x['count']}" if x["count"] > 1 else ""))
        p = r["patterns"]
        if key in ("first_mes", "mes_example", "description"):
            if p["not_but"]["count"]:
                out.append(f"{name}: “not X, but Y” emphasis ×{p['not_but']['count']}")
            if p["negations"]["count"] >= 2:
                out.append(f"{name}: describes what doesn't happen ×{p['negations']['count']} (say what does)")
            if p["echoes"]["count"]:
                out.append(f"{name}: a reply repeats the other speaker's words as a question")
            if r["words"] >= 80 and p["dashes"]["per1k"] > 12:
                out.append(f"{name}: many em-dashes ({p['dashes']['count']})")
    return out[:limit]
