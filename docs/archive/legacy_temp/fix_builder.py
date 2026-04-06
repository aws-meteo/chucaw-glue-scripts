import sys
with open('build_glue_libs.sh', 'rb') as f:
    content = f.read().replace(b'\r\n', b'\n')
with open('build_glue_libs.sh', 'wb') as f:
    f.write(content)
