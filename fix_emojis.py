import os
import re

files_to_fix = [
    'db/services/ingest_service.py',
    'db/services/orchestrators/pokemon_tcg_orchestrator.py',
    'db/services/orchestrators/tcg_orchestrator.py',
    'db/services/sets_service.py',
    'db/services/cards_service.py',
    'db/services/sealed_products_service.py',
    'db/controllers/ingest_controller.py',
]

emoji_map = {
    '🔄': '[ROUTING]',
    '📦': '[PKG]',
    '🎴': '[TCG]',
    '❌': '[ERROR]',
    '🎯': '[TARGET]',
    '✅': '[OK]',
}

for file_path in files_to_fix:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for emoji, replacement in emoji_map.items():
            content = content.replace(emoji, replacement)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed: {file_path}')
    else:
        print(f'Not found: {file_path}')
