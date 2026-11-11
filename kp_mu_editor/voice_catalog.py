"""Voice families from the MU500 voice-list bank headings (manual pp.26, 50-51).

Only GM-ordered banks use program-number families. MU100-exclusive banks are
grouped by their printed timbre/phrase/SFX/rhythm headings, not guessed GM names.
"""
GM_CATEGORIES=('Piano','Chromatic Percussion','Organ','Guitar','Bass','Strings','Ensemble','Brass',
               'Reed','Pipe','Synth Lead','Synth Pad','Synth Effects','Ethnic','Percussive','Sound Effects')
CATEGORIES=GM_CATEGORIES+('MU100 Exclusive','Phrase / Loop','Rhythm / Loop','SFX')
EXCLUSIVE_BANKS={
    0:'Timbre',8:'Timbre, Poly',16:'Timbre, Looped',24:'Timbre, Looped, Poly',
    48:'Phrase, Looped',56:'Phrase, Looped, Poly',64:'SFX, Timbre',72:'SFX, Timbre, Poly',
    80:'SFX, Phrase',88:'SFX, Phrase, Poly',96:'Rhythm, Timbre',104:'Rhythm, Timbre, Poly',120:'Rhythm, Phrase, Poly',
}


def normalize_voice(row):
    row=dict(row)
    msb,lsb,program=row['msb'],row['lsb'],row['program']
    if msb in (120,126,127):
        row['kind']='sfx_kit' if msb==126 else 'drum_kit'
        row['category']='Drum / SFX Kit'
        row['voice_family']='SFX Kit' if msb==126 else 'Drum Kit'
        row['bank_description']=row['voice_family']
    elif msb==64:
        row.update(kind='normal',category='SFX',voice_family='SFX Voice',bank_description='SFX')
        # The last column on pp.51/65 has its own program-number guide.
        # Earlier extraction accidentally included that guide in the voice name.
        prefix=f'{program+1} '
        if row.get('source','').startswith('Yamaha') and row['name'].startswith(prefix):
            row['name']=row['name'][len(prefix):].strip()
    elif msb==48:
        category='SFX' if lsb in (64,72,80,88) else 'Phrase / Loop' if lsb in (48,56) else 'Rhythm / Loop' if lsb in (96,104,120) else 'MU100 Exclusive'
        row.update(kind='normal',category=category,voice_family='MU100 Exclusive',bank_description=EXCLUSIVE_BANKS.get(lsb,'Model Exclusive'))
    elif msb in (0,121):
        row.update(kind='normal',category=GM_CATEGORIES[min(15,program//8)],voice_family='GM2' if msb==121 else 'XG',bank_description='GM2' if msb==121 else 'XG')
    else:
        row.update(kind='normal',category=row.get('category','Other'),voice_family=row.get('voice_family','Other'),bank_description=row.get('bank_description',''))
    return row
def display_voice_name(name,program,msb,lsb):
    """Use one-based program numbers in every user-facing voice label."""
    return f'{program+1}-{msb}-{lsb} {name.replace(" #","#")}'

