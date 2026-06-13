import importlib.metadata

for d in importlib.metadata.distributions():
    print(d.name, d.version)