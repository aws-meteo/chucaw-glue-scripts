import sys
with open('scripts/batch_process_gribs.sh', 'rb') as f:
    content = f.read().replace(b'\r\n', b'\n')
with open('scripts/batch_process_gribs.sh', 'wb') as f:
    f.write(content)
