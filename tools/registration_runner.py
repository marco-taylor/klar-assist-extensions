"""Actual HA loading/auth/platform tests with a disposable config, never /config."""
import sys,io,tarfile,tempfile,pathlib,unittest,json,os
sys.dont_write_bytecode=True
with tempfile.TemporaryDirectory(prefix='klar-assist-extensions-registration-',dir='/tmp') as directory:
    root=pathlib.Path(directory)
    assert not str(root).startswith('/config')
    with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz') as archive:
        archive.extractall(root,filter='data')
    (root/'custom_components/__init__.py').write_text('"""Isolated integration namespace."""\n')
    sys.path.insert(0,str(root))
    os.environ['KAE_REGISTRATION_CONFIG']=str(root)
    import tests.registration_suite as suite
    print('Isolated config: '+str(root),flush=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(suite))
    print('REGISTRATION_JSON='+json.dumps(suite.OUTCOMES,ensure_ascii=False))
    exit_code=0 if result.wasSuccessful() else 1
sys.exit(exit_code)
