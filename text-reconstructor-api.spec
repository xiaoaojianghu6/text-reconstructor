# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/api_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('src/text_reconstructor', 'text_reconstructor')],
    hiddenimports=['text_reconstructor', 'text_reconstructor.api', 'text_reconstructor.llm', 'text_reconstructor.output', 'text_reconstructor.output.vpga_refiner', 'text_reconstructor.output.llm_review_extractor', 'text_reconstructor.output.interactive_questions', 'text_reconstructor.output.refinement_refiner', 'text_reconstructor.output.llm_refiner', 'text_reconstructor.output.detail_anchor', 'text_reconstructor.output.fcr', 'text_reconstructor.output.suggestions', 'text_reconstructor.processor', 'text_reconstructor.processor.tagger', 'text_reconstructor.processor.chunker', 'text_reconstructor.processor.buffer', 'text_reconstructor.processor.prefix_pruner', 'text_reconstructor.processor.prompts', 'text_reconstructor.graph', 'text_reconstructor.graph.models', 'text_reconstructor.graph.updater', 'text_reconstructor.graph.decay', 'text_reconstructor.graph.cross_file_scanner', 'text_reconstructor.adversary', 'text_reconstructor.adversary.semantic_router', 'text_reconstructor.adversary.entity_hedge', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'httpx', 'networkx', 'click'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='text-reconstructor-api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='text-reconstructor-api',
)
