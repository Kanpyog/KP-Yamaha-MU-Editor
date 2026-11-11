"""Actionable errors when a source checkout lacks MIDI file dependencies."""
def midi_library():
    try:
        import mido
    except ModuleNotFoundError as exc:
        if exc.name not in ('mido','packaging'):raise
        raise RuntimeError('MIDIファイル用ライブラリが不足しています。Start_Python.cmdから起動し直してください。専用環境がない場合はrequirements.txtのライブラリを導入してください。') from exc
    return mido
