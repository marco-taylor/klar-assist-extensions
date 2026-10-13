"""Run all isolated tests with the current Python/HA installation, no live HA API."""
import io,pathlib,subprocess,sys,tarfile
root=pathlib.Path(__file__).resolve().parents[1]
archive=io.BytesIO()
with tarfile.open(fileobj=archive,mode='w:gz') as package:
 for name in ('custom_components','tests','hacs.json'):
  package.add(root/name,arcname=name,filter=lambda item:None if '__pycache__' in item.name or item.name.endswith('.pyc') else item)
for runner in ('isolated_runner.py','registration_runner.py'):
 result=subprocess.run([sys.executable,'-B','-c',(root/'tools'/runner).read_text()],
                       input=archive.getvalue(),cwd=root)
 if result.returncode:sys.exit(result.returncode)
