"""25 gaming categories + optional custom category.
audio: 'high' = loud/energetic scenes, 'mid' = medium, 'any' = audio says nothing."""

def _c(id_, label, keywords, audio="any", hint=""):
    return {"id": id_, "label": label, "keywords": keywords, "audio": audio, "hint": hint}

GAMING_CATEGORIES = [
    _c("fighting", "Fist Fight / Melee", ["fight", "punch", "kick", "brawl", "hit him", "beat", "knock"], "high", "hand-to-hand combat, no firearms"),
    _c("shooting", "Shooting / Gunfight", ["gun", "shoot", "shot", "fire", "reload", "bullet", "cover", "ammo"], "high", "firearms being used"),
    _c("police_chase", "Police Chase", ["police", "cops", "siren", "wanted", "officer", "patrol", "swat", "escape"], "high", "vehicle chase WITH police cars/wanted level"),
    _c("car_chase", "Car Chase", ["chase", "follow", "catch him", "behind us", "speed"], "high", "vehicle chase WITHOUT police"),
    _c("crash", "Crash / Collision", ["crash", "collision", "smash", "wreck", "flip", "hit the"], "high", "vehicle impact"),
    _c("explosions", "Explosions", ["explosion", "explode", "boom", "blow up", "bomb", "grenade", "rocket"], "high", "visible blasts, fire"),
    _c("mission", "Mission / Objective", ["mission", "objective", "go to", "meet", "deliver", "target", "plan"], "any", "story mission moments"),
    _c("funny", "Funny Moments", ["lol", "haha", "funny", "what the", "laugh", "stupid", "joke"], "any", "comedic or absurd events"),
    _c("cinematic", "Cinematic / Cutscene", ["cutscene", "story", "cinematic", "scene", "trailer"], "any", "film-like camera, story scene"),
    _c("stealth", "Stealth", ["quiet", "sneak", "stealth", "silent", "hide", "careful"], "mid", "sneaking, low noise"),
    _c("stunts", "Stunts / Jumps", ["stunt", "jump", "ramp", "flip", "launch", "air"], "high", "jumps, ramps, tricks"),
    _c("heist", "Heist / Robbery", ["heist", "rob", "robbery", "vault", "bank", "loot", "score", "hostage"], "mid", "robbery or heist"),
    _c("helicopter_air", "Helicopter / Air", ["helicopter", "chopper", "plane", "jet", "fly", "pilot"], "mid", "air vehicles"),
    _c("water_boat", "Boat / Water", ["boat", "jet ski", "yacht", "ocean", "dive", "swim"], "mid", "water scenes"),
    _c("motorcycle", "Motorcycle", ["bike", "motorcycle", "wheelie", "biker"], "high", "motorcycle riding"),
    _c("skydiving", "Skydiving / Falling", ["skydive", "parachute", "fall", "falling", "drop"], "high", "falling from height"),
    _c("street_race", "Street Race", ["race", "racing", "lap", "finish", "overtake", "nitro"], "high", "racing against others"),
    _c("drifting", "Drifting", ["drift", "slide", "burnout", "tire", "corner"], "high", "controlled sliding"),
    _c("wasted_death", "Wasted / Death", ["wasted", "dead", "died", "dies", "busted", "rip"], "any", "player or NPC death"),
    _c("npc_reactions", "NPC Reactions", ["npc", "pedestrian", "people", "react", "scream", "run away"], "mid", "funny or realistic NPC behaviour"),
    _c("glitch_bug", "Glitch / Bug", ["glitch", "bug", "broken", "physics", "ragdoll", "clip through"], "any", "game bugs and physics fails"),
    _c("dialogue_story", "Dialogue / Story", ["said", "tell me", "listen", "family", "trust", "promise"], "mid", "characters talking"),
    _c("customization", "Shopping / Customization", ["buy", "shop", "outfit", "clothes", "upgrade", "tattoo", "paint"], "any", "stores, outfits, car mods"),
    _c("scenery", "Exploration / Scenery", ["view", "beautiful", "sunset", "city", "beach", "explore", "drive around"], "mid", "calm open-world views"),
    _c("weapons_showcase", "Weapons Showcase", ["weapon", "rifle", "pistol", "shotgun", "sniper", "smg", "knife"], "any", "showing weapons and loadouts"),
]

def category_ids():
    return [c["id"] for c in GAMING_CATEGORIES]

def get_categories(custom_label=None):
    cats = list(GAMING_CATEGORIES)
    if custom_label and custom_label.strip():
        words = [w.lower() for w in custom_label.replace(",", " ").split() if len(w) > 2]
        cats.append(_c("custom", custom_label.strip(), words or [custom_label.strip().lower()], "any", custom_label.strip()))
    return cats