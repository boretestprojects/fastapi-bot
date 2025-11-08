from dateutil import parser

def parse_human_date(text):
    try:
        return parser.parse(text, fuzzy=True)
    except Exception:
        return None
