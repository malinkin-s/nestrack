# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build of the probe client.

    pyinstaller probe.spec

Build with the same Python as the real client: 3.8.10, 32-bit. PyInstaller
packs the interpreter it runs under, so the build environment decides what
ends up on the shop-floor PC.

A console program on purpose: the operator running the probe should see the
results as they happen.
"""

a = Analysis(
    ['probe_client.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # The real client needs these network modules, so the probe keeps them.
    excludes=['tkinter', 'unittest', 'pydoc', 'doctest', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='nestrack-probe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX makes antivirus false positives worse
    runtime_tmpdir=None,
    console=True,
)
