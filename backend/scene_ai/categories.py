"""Scene categories: label, strict rule for the AI, and a few speech keywords for the offline fallback."""


def _c(label, rule, kw=()):
    return {"label": label, "rule": rule, "kw": list(kw)}


CATEGORIES = {
    "fighting": _c("Fighting / Combat Scenes",
                   "Physical combat only: punching, kicking, martial arts, boxing, sword fights, wrestling, armed attacks, a chase that turns into combat. A loud argument or threats WITHOUT physical violence must score below 20.",
                   ["fight", "punch", "kick", "stab", "sword", "maar", "ladai", "لڑائی"]),
    "romantic": _c("Romantic Scenes",
                   "Romantic interaction between a couple: kissing, romantic hugging, love expressions, romantic gestures, intimate emotional couple moments. Friendship or family affection must score below 20.",
                   ["i love you", "love you", "kiss", "darling", "jaan", "mohabbat", "pyar", "محبت", "پیار"]),
    "comedy": _c("Comedy / Funny Scenes",
                 "Funny content: humorous dialogue, physical comedy, funny reactions, pranks, comedic expressions, funny misunderstandings, unexpected humorous events.",
                 ["haha", "lol", "joke", "funny", "mazak", "مذاق"]),
    "emotional": _c("Emotional / Sad Scenes",
                    "Sad or deeply emotional moments: grief, loss, painful goodbyes, heartbreak, emotional confessions.",
                    ["goodbye", "sorry", "alvida", "dukh", "afsos", "خدا حافظ"]),
    "action": _c("Action Scenes",
                 "High-energy action: chases, explosions, shootouts, stunts, vehicle action, fast physical sequences.",
                 ["chase", "explosion", "shoot", "gun", "bhago", "goli"]),
    "horror": _c("Horror / Scary Scenes",
                 "Frightening content: monsters, ghosts, gore, jump scares, terrifying atmosphere, characters in fear.",
                 ["ghost", "scream", "blood", "demon", "bhoot", "بھوت"]),
    "suspense": _c("Suspense / Thriller Scenes",
                   "Tense build-up: stalking, hiding, investigation, ticking clock, quiet danger, mystery reveal.",
                   ["who's there", "behind you", "secret", "careful", "khamosh"]),
    "adventure": _c("Adventure Scenes",
                    "Exploration and journeys: travel through wild places, treasure hunts, discovering new places, daring exploration.",
                    ["journey", "treasure", "explore", "cave", "safar"]),
    "dramatic": _c("Dramatic Scenes",
                   "Intense dramatic confrontations or revelations: betrayal, truth coming out, emotional turning points.",
                   ["betray", "the truth", "never forgive", "dhoka", "sach"]),
    "dialogue": _c("Dialogue / Conversation Scenes",
                   "Two or more people mainly talking to each other (calm conversation, interview, discussion) with little action.",
                   ["tell me", "listen", "kya", "بتاؤ"]),
    "motivational": _c("Motivational Scenes",
                       "Inspiring speeches or moments: encouragement, never giving up, overcoming challenges, success.",
                       ["never give up", "believe", "dream", "success", "himmat", "kamyabi", "ہمت"]),
    "educational": _c("Educational Scenes",
                      "Teaching or explaining: lessons, demonstrations, step-by-step explanations, facts, lectures.",
                      ["learn", "lesson", "explain", "for example", "sabaq", "سبق"]),
    "dancing": _c("Dancing Scenes",
                  "People dancing or performing choreography.",
                  ["dance", "naach", "ناچ"]),
    "singing": _c("Singing / Music Scenes",
                  "Singing, musical performances, instruments being played, music video style sequences.",
                  ["song", "sing", "gaana", "گانا"]),
    "crying": _c("Crying Scenes",
                 "A person visibly crying or sobbing, with tears.",
                 ["crying", "tears", "sob", "rona", "aansu", "آنسو"]),
    "angry": _c("Angry / Argument Scenes",
                "Verbal arguments, shouting, anger, heated confrontations WITHOUT physical fighting.",
                ["shut up", "how dare", "get out", "gussa", "غصہ", "bakwas"]),
    "surprise": _c("Surprise / Shocking Scenes",
                   "Sudden surprises or shocks: unexpected reveals, shocked reactions, plot twists.",
                   ["no way", "oh my god", "omg", "unbelievable", "shocking", "hairan", "حیران"]),
    "friendship": _c("Friendship Scenes",
                     "Friends spending time together, supporting each other, loyal friendship moments (NOT romantic).",
                     ["best friend", "my friend", "dost", "yaar", "دوست"]),
    "family": _c("Family / Emotional Bonding Scenes",
                 "Family bonding: parents, children, siblings sharing warm or emotional moments (NOT romantic).",
                 ["mother", "father", "family", "ammi", "abbu", "beta", "ماں", "باپ"]),
    "custom": _c("Custom Scene Category", "Defined by the user description.", []),
}


def short_label(key: str) -> str:
    label = CATEGORIES.get(key, {}).get("label", key)
    return label.split(" / ")[0].replace(" Scenes", "").replace(" Scene Category", "")