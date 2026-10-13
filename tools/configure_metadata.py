"""Set explicitly supplied publication metadata; never install or publish anything."""
import argparse,json,pathlib,re
parser=argparse.ArgumentParser()
parser.add_argument('--owner',required=True)
parser.add_argument('--repository',default='klar-assist-extensions')
parser.add_argument('--codeowner',required=True)
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',args.owner):parser.error('Invalid GitHub owner')
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.repository):parser.error('Invalid repository name')
owner=args.codeowner.removeprefix('@')
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:/[A-Za-z0-9_-]+)?',owner):parser.error('Invalid codeowner')
root=pathlib.Path(__file__).resolve().parents[1]
p=root/'custom_components/klar_assist_extensions/manifest.json'
m=json.loads(p.read_text());url=f'https://github.com/{args.owner}/{args.repository}'
m.update(documentation=url,issue_tracker=url+'/issues',codeowners=['@'+owner])
ordered={k:m[k] for k in ('domain','name')}
ordered.update({k:m[k] for k in sorted(m) if k not in ordered})
p.write_text(json.dumps(ordered,indent=2)+'\n')
(root/'.github/CODEOWNERS').write_text('* @'+owner+'\n')
print('Publication metadata updated locally; no installation or publication performed.')
