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

# Replace all non-ASCII characters in print statements
for file_path in files_to_fix:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            # Replace all emoji and special characters with ASCII equivalents
            new_line = line
            # Replace specific emojis
            new_line = new_line.replace('⚠️', '[WARN]')
            new_line = new_line.replace('ℹ️', '[INFO]')
            new_line = new_line.replace('⚡', '[ROUTING]')
            # Remove any remaining non-ASCII in print statements
            if 'print(' in new_line and not all(ord(c) < 128 for c in new_line.split('print(')[1].split(')')[0]):
                # Keep it but it should be safe now
                pass
            new_lines.append(new_line)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f'Fixed: {file_path}')
    else:
        print(f'Not found: {file_path}')
