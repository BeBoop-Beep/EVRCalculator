import difflib
from constants.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP

# Rating to pull rate mapping (1/X)
def get_config_for_set(user_input):
    key = user_input.lower().strip()

    # Try alias map first
    if key in SET_ALIAS_MAP:
        mapped_key = SET_ALIAS_MAP[key]
        return SET_CONFIG_MAP[mapped_key]

    # Try exact key in config map
    if key in SET_CONFIG_MAP:
        return SET_CONFIG_MAP[key]

    # Try fuzzy matching against aliases and set names
    possible_inputs = list(SET_ALIAS_MAP.keys()) + list(SET_CONFIG_MAP.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    print("We think you mean :", matches[0])
    return SET_CONFIG_MAP[matches[0]]