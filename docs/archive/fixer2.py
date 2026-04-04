with open('batch_runner.sh', 'rb') as f:
    content = f.read().replace(b'\r\n', b'\n')
with open('batch_runner.sh', 'wb') as f:
    f.write(content)
