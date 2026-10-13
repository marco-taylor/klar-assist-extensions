"""Read a tar on stdin; import project/test code entirely in memory. No HA server."""
import sys, io, tarfile, importlib.abc, importlib.util, unittest, types, json, asyncio
sys.dont_write_bytecode = True
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode='r:gz') as archive:
    files = {entry.name.removeprefix('./'): archive.extractfile(entry).read()
             for entry in archive.getmembers() if entry.isfile()}
fixture_module = types.ModuleType('isolated_files')
fixture_module.files = files
sys.modules['isolated_files'] = fixture_module
files['custom_components/__init__.py'] = b''
files['tests/__init__.py'] = b''


class MemoryImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        stem = fullname.replace('.', '/')
        for candidate, is_package in ((stem+'/__init__.py', True), (stem+'.py', False)):
            if candidate in files:
                return importlib.util.spec_from_loader(fullname, self, origin=candidate, is_package=is_package)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = module.__spec__.origin
        exec(compile(files[module.__file__], module.__file__, 'exec'), module.__dict__)

sys.meta_path.insert(0, MemoryImporter())
for path, source in files.items():
    if path.endswith('.py'):
        compile(source, path, 'exec')
for path in ['custom_components/klar_assist_extensions/manifest.json',
             'custom_components/klar_assist_extensions/strings.json',
             'custom_components/klar_assist_extensions/translations/de.json', 'hacs.json']:
    json.loads(files[path])
import custom_components.klar_assist_extensions.config_flow
suite = unittest.TestSuite()
for path in sorted(files):
    if path.startswith('tests/test_') and path.endswith('.py'):
        module = __import__(path[:-3].replace('/', '.'), fromlist=['*'])
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    sys.exit(1)
import tests.benchmark
asyncio.run(tests.benchmark.run())
import tests.samples
asyncio.run(tests.samples.run())
