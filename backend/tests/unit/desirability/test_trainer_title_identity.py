from backend.desirability.trainer_title_identity import classify_supporter_title

def test_explicit_title_rules_are_conservative():
    assert classify_supporter_title('Iono').subjects == ('Iono',)
    assert classify_supporter_title("Cynthia's Ambition").subjects == ('Cynthia',)
    assert classify_supporter_title('Cynthia & Caitlin').subjects == ('Cynthia','Caitlin')
    assert classify_supporter_title("Boss's Orders").classification == 'generic_card_with_variable_character'
    assert classify_supporter_title("Boss's Orders (Ghetsis)").subjects == ('Ghetsis',)
    assert classify_supporter_title('Pokémon Center Lady').classification == 'generic_role_or_class'
    assert classify_supporter_title('Team Yell Grunt').classification == 'team_or_organization'
