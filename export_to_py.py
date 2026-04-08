import json

with open('swat_ensemble_anomaly_detection.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

lines = []
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'markdown':
        src = ''.join(cell.get('source', []))
        lines.append('\n# ' + '=' * 78)
        for ln in src.split('\n'):
            lines.append('# ' + ln)
        lines.append('# ' + '=' * 78 + '\n')
    elif cell['cell_type'] == 'code':
        src = ''.join(cell.get('source', []))
        lines.append('\n# --- Cell ' + str(i) + ' ---')
        lines.append(src)
        lines.append('')

with open('swat_full_pipeline.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('Done. Cells exported:', sum(1 for c in nb['cells'] if c['cell_type'] == 'code'))
