# Third-party notices

The baseline voice/drum names, a subset of effect parameter definitions and conversion
tables in `kp_mu_editor/data/catalog.json` are derived from QXGEdit's `src/XGParam.cpp`.

QXGEdit copyright (C) 2005-2023 Rui Nuno Capela (rncbc).
QXGEdit is licensed under the GNU General Public License version 2 or, at your option,
any later version. This project uses the version 3 option. The source extraction script
and the exact upstream source file are included with this project's corresponding source.

Upstream: https://github.com/rncbc/qxgedit
Source: https://github.com/rncbc/qxgedit/blob/master/src/XGParam.cpp

The remaining parameter addresses and product-specific lists were independently
transcribed or extracted from Yamaha's publicly available MIDI documentation.
Yamaha and its product names are trademarks of their respective owners. Yamaha
manuals are references and are not included in the redistributable application ZIP.

Runtime components include Python (PSF license), PySide6/Shiboken6/Qt (LGPL/GPL,
see their bundled license texts), and mido (MIT license). PyInstaller's bootloader
has a license exception permitting distribution of bundled applications.
The application distribution retains replaceable shared Qt libraries in `_internal`.

The runtime license texts are in `licenses/`. The versions used for this build are
recorded in `licenses/versions.json`. No runtime component is modified here.
Qt for Python source: https://code.qt.io/cgit/pyside/pyside-setup.git/
Qt source and component attribution: https://code.qt.io/cgit/qt/qtbase.git/
Qt source archives: https://download.qt.io/archive/qt/
Python source: https://www.python.org/downloads/source/
mido source: https://github.com/mido/mido
The application is provided with corresponding source in the adjacent source ZIP.
Builds load shared Qt DLLs dynamically and retain the ability to replace those DLLs.
