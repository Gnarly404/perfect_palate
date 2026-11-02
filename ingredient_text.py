"""Perfect Palate - turn scraped ingredient text into clean, readable lines.

Some recipes list ingredients as "▢1 1/2 – 2 1/2pounds (453.60 g)beef brisket, ▢salt and pepperfor seasoning":
checkbox glyphs instead of commas, and words glued together.  This module splits such text into lines
("1 1/2–2 1/2 pounds (453.60 g) beef brisket") and pulls out a quantity and a name for shopping lists.
"""
import re

_UNITS = (r'pounds?|lbs?|ounces?|oz|grams?|g|kg|kilograms?|ml|millilit(?:er|re)s?|lit(?:er|re)s?|l|cups?|tablespoons?|tbsps?|tbsp|'
          r'teaspoons?|tsps?|tsp|cloves?|slices?|stalks?|sprigs?|packets?|cans?|tins?|bunch(?:es)?|heads?|pieces?|pinch(?:es)?|'
          r'dash(?:es)?|handfuls?|sticks?|bulbs?|leaves|leaf|fillets?|rings?|pods?')
_LONG_UNITS = r'pounds?|ounces?|grams?|kilograms?|millilit(?:er|re)s?|lit(?:er|re)s?|cups?|tablespoons?|teaspoons?|cloves?|slices?|stalks?|sprigs?|packets?|cans?|tins?|bunch(?:es)?|heads?|pieces?|pinch(?:es)?|dash(?:es)?|handfuls?|sticks?|bulbs?|leaves|fillets?'
_SIZES = r'(?:extra[- ])?(?:large|medium|small|big|whole|ripe|fresh|thick|thin)'
_NUM = r'(?:\d+\s+\d+/\d+|\d+\s*[¼½¾⅓⅔⅛⅜⅝⅞]|[¼½¾⅓⅔⅛⅜⅝⅞]|\d+/\d+|\d+(?:\.\d+)?)'
_QTY = re.compile(r'^(?P<q>' + _NUM + r'(?:\s*(?:-|–|—|to)\s*' + _NUM + r')?)\s*'
                  r'(?P<size>' + _SIZES + r'\s+)?'
                  r'(?P<unit>(?:' + _UNITS + r')\b)?\s*(?P<paren>\([^)]*\))?\s*(?P<name>.*)$', re.I)
_HEADER = re.compile(r'^(?:[A-Za-z][A-Za-z &/\'-]{0,40}):\s*$')
_GLUED_TAILS = re.compile(r'([a-z])(to taste|for (?:seasoning|rubbing|serving|garnish|garnishing|frying|dusting|greasing|topping|'
                          r'dipping|brushing|cooking|the)|optional|see notes|divided|or more|or to taste)', re.I)


def _tidy(text):
    text = text.replace(' ', ' ').strip(' \t\r\n,;•-–—*')
    text = re.sub(r'^[▢☐□▪•\-–—\s]+', '', text)
    text = re.sub(r'(\d)\s*([¼½¾⅓⅔⅛⅜⅝⅞])', r'\1\2', text)
    text = re.sub(r'(\d)\s*[-–—]\s*(\d)', r'\1–\2', text)
    text = re.sub(r'(\d|[¼½¾⅓⅔⅛⅜⅝⅞])\s*[-–—]\s*(\d|[¼½¾⅓⅔⅛⅜⅝⅞])', r'\1–\2', text)
    text = re.sub(r'([a-z]{3,}(?:[eg]|[^s\W]s))or(?= [a-z])', r'\1 or', text)
    text = re.sub(r'(?<=\d)(large|medium|small|big)(?=[a-z])', r' \1 ', text, flags=re.I)
    text = re.sub(r'(?i)(\d(?:/\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])(\s*(?:' + _SIZES + r'\s+)?(?:' + _LONG_UNITS + r'))(?=[a-z]{3,})', r'\1\2 ', text)
    text = re.sub(r'(?i)immaculatebites', 'Immaculate Bites', text)
    text = re.sub(r',(?=\S)', ', ', text)
    text = re.sub(r'(\d|[¼½¾⅓⅔⅛⅜⅝⅞])([A-Za-z]{2,})', r'\1 \2', text)
    text = re.sub(r'\)([A-Za-z])', r') \1', text)
    text = re.sub(r'([a-z])\(', r'\1 (', text)
    text = re.sub(r'(\d)\s*(g|kg|ml|oz)\b', r'\1 \2', text)
    text = _GLUED_TAILS.sub(r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' ,;')


def split_lines(raw):
    """Return clean ingredient lines, dropping section headers like 'Proteins:'."""
    raw = (raw or '').replace('▢', '\n▢').replace('☐', '\n☐')
    pieces = []
    for block in raw.split('\n'):
        block = block.strip()
        if not block:
            continue
        # commas inside brackets, or in a prep note such as "bacon,diced", stay with their ingredient
        parts = re.split(r',\s*(?![^()]*\))(?=[▢☐]|\d|[¼½¾⅓⅔⅛⅜⅝⅞]|[A-Z][a-z]+ \(|[A-Z][a-z]+:)', block) if '▢' not in block else [block]
        pieces.extend(parts)
    lines = []
    for piece in pieces:
        text = _tidy(piece)
        if not text or not re.search(r'[A-Za-z]', text) or _HEADER.match(text):
            continue
        lines.append(text)
    return lines


def parse_line(line):
    """Split one clean line into (quantity text, name).  Quantity is '' when there is none."""
    m = _QTY.match(line)
    if not m or not m.group('name').strip():
        # "Garlic (3 cloves, minced)" style
        p = re.match(r'^(.*?)\s*\(([^()]*)\)\s*$', line)
        if p and re.search(r'\d', p.group(2)):
            return p.group(2).strip(), p.group(1).strip()
        return '', line
    qty = ' '.join(x for x in (m.group('q'), (m.group('size') or '').strip(), m.group('unit') or '', m.group('paren') or '') if x)
    return re.sub(r'\s+', ' ', qty).strip(), m.group('name').strip(' ,;')


def shopping_name(name):
    """The thing to buy, without prep notes: 'bacon, diced' -> 'bacon'; 'salt and pepper for seasoning' -> 'salt and pepper'."""
    core = re.split(r',|\s\(|\bfor (?:seasoning|rubbing|serving|garnish|frying|dusting|greasing|topping)\b|\bto taste\b', name)[0]
    return core.strip(' ,;:-') or name.strip()
