"""Offline publication checks; remote HACS/GitHub validation remains separate."""
import json,pathlib,re,sys,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
m=json.loads((root/'custom_components/klar_assist_extensions/manifest.json').read_text())
h=json.loads((root/'hacs.json').read_text());results=[]
def check(name,condition):results.append({'check':name,'result':'PASS' if condition else 'FAIL'})
check('single_integration',len(list((root/'custom_components').iterdir()))==1)
check('hacs_metadata',h.get('name')==m.get('name') and h.get('render_readme') is True and h.get('homeassistant')=='2026.10.1')
check('manifest_keys',all(k in m for k in ['domain','name','version','documentation','issue_tracker','codeowners']))
check('project_documentation',bool(re.fullmatch(r'https://github.com/[^/]+/klar-assist-extensions/?',m.get('documentation',''))))
check('project_issue_tracker',m.get('issue_tracker')==m.get('documentation','').rstrip('/')+'/issues')
check('confirmed_codeowner',bool(m.get('codeowners')) and all(re.fullmatch(r'@[A-Za-z0-9-]+(?:/[A-Za-z0-9_-]+)?',s) for s in m['codeowners']))
check('brand_icon',(root/'custom_components/klar_assist_extensions/brand/icon.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
check('license_readme',all((root/n).is_file() for n in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md']))
check('no_private_artifact_directories',not any((root/n).exists() for n in ['installation-tests','integration-tests','.storage','.git','backups']))
check('no_artifact_files',not any(p.suffix in {'.log','.pyc','.patch','.bak','.db'} for p in root.rglob('*') if p.is_file()))
check('runtime_fingerprints',all(hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for digest,p in [line.split('  ',1) for line in (root/'RUNTIME_SHA256SUMS').read_text().splitlines()]))
print(json.dumps({'checks':results,'remote_hacs_validation_executed':False},indent=2))
sys.exit(0 if all(c['result']=='PASS' for c in results) else 1)
