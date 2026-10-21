import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updates import repository, version_tuple

path = Path(__file__).resolve().parents[1] / 'release.json'
release = json.loads(path.read_text())
version_tuple(release['version'])
if os.environ.get('RELEASE_REF_TYPE') == 'tag':
    assert os.environ['RELEASE_REF_NAME'] == 'v' + release['version'], 'Tag must match release.json version'
release['repository'] = repository(os.environ['RELEASE_REPOSITORY'])
path.write_text(json.dumps(release, ensure_ascii=False, indent=2) + '\n')
