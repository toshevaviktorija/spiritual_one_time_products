"""Domain constants shared by the natal chart generator."""

SIGN_NAMES = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces",
}

ROMAN_HOUSES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")

SIGN_RULERS = {
    "Ari": "Mars", "Tau": "Venus", "Gem": "Mercury", "Can": "Moon",
    "Leo": "Sun", "Vir": "Mercury", "Lib": "Venus", "Sco": "Pluto",
    "Sag": "Jupiter", "Cap": "Saturn", "Aqu": "Uranus", "Pis": "Neptune",
}

SIGN_COLORS = {
    "Ari": "#C95D52", "Tau": "#6F8F63", "Gem": "#D6A94A", "Can": "#708DB2",
    "Leo": "#D98643", "Vir": "#879568", "Lib": "#B77C98", "Sco": "#744F72",
    "Sag": "#A05D73", "Cap": "#65756D", "Aqu": "#557E9C", "Pis": "#648C88",
}

HOUSE_SHORT_INFO = {
    1: "House of Self", 2: "House of Values", 3: "House of Communication",
    4: "House of Home", 5: "House of Creativity", 6: "House of Health",
    7: "House of Partnership", 8: "House of Transformation", 9: "House of Philosophy",
    10: "House of Career", 11: "House of Community", 12: "House of Unconscious",
}

PLANET_SYMBOLS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆", "Pluto": "♇",
}
