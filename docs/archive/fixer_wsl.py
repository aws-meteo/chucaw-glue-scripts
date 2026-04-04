import sys
with open('scripts/batch_process_gribs.sh', 'rb') as f:
    content = f.read()

# I need to change /workspace back to Windows mount directory since this runs in WSL, not docker!
content = content.replace(b'/workspace', b'/mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts')

with open('scripts/batch_process_gribs.sh', 'wb') as f:
    f.write(content)
