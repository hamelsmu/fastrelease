# AUTOGENERATED! DO NOT EDIT! File to edit: 00_core.ipynb (unless otherwise specified).

__all__ = ['GH_HOST', 'run_proc', 'do_request', 'FastRelease', 'fastrelease_changelog', 'fastrelease_release']

# Cell
from datetime import datetime
from textwrap import fill
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from configparser import ConfigParser
import os,shutil,json,subprocess
from .fastscript import *

# Cell
GH_HOST = "https://api.github.com"

# Cell
def _issue_txt(issue):
    res = '- {} ([#{}]({}))\n'.format(issue["title"].strip(), issue["number"], issue["url"])
    body = issue['body']
    if not body: return res
    return res + fill(body.strip(), initial_indent="  - ", subsequent_indent="    ") + "\n"

def _issues_txt(iss, label):
    if not iss: return ''
    res = f"### {label}\n\n"
    return res + '\n'.join(map(_issue_txt, iss))

def _config(cfg_name="settings.ini"):
    cfg_path = Path().absolute()
    while cfg_path != cfg_path.parent and not (cfg_path/cfg_name).exists(): cfg_path = cfg_path.parent
    config_file = cfg_path/cfg_name
    assert config_file.exists(), f"Couldn't find {cfg_name}"
    config = ConfigParser()
    config.read(config_file)
    return config['DEFAULT'],cfg_path

def _load_json(cfg, k):
    try: return json.loads(cfg[k])
    except json.JSONDecodeError as e: raise Exception(f"Key: `{k}` in .ini file is not a valid JSON string: {e}")

# Cell
def run_proc(*args):
    res = subprocess.run(args, capture_output=True)
    if res.returncode: raise IOError("{} ;; {}").format(res.stdout, res.stderr)
    return res.stdout

# Cell
def do_request(url, post=False, headers=None, **data):
    "Call GET or json-encoded POST on `url`, depending on `post`"
    if data:
        if post: data = json.dumps(data).encode('ascii')
        else:
            url += "?" + urlencode(data)
            data = None
    with urlopen(Request(url, headers=headers, data=data or None)) as res: return json.loads(res.read())

# Cell
class FastRelease:
    def __init__(self, owner=None, repo=None, token=None, **groups):
        "Create CHANGELOG.md from GitHub issues"
        self.cfg,cfg_path = _config()
        if not groups:
            default_groups=dict(breaking="Breaking Changes", enhancement="New Features", bug="Bugs Squashed")
            groups=_load_json(self.cfg, 'label_groups') if 'label_groups' in self.cfg else default_groups
        os.chdir(cfg_path)
        if not owner: owner = self.cfg['user']
        if not repo:  repo  = self.cfg['lib_name']
        if not token:
            assert Path('token').exists, "Failed to find token"
            token = Path('token').read_text().strip()
        self.owner,self.repo,self.token,self.groups = owner,repo,token,groups
        self.headers = { 'Authorization' : 'token ' + token }
        self.repo_url = f"{GH_HOST}/repos/{owner}/{repo}"

    def gh(self, path, complete=False, post=False, **data):
        "Call GitHub API `path`"
        if not complete: path = f"{self.repo_url}/{path}"
        return do_request(path, headers=self.headers, post=post, **data)

    def _tag_date(self, tag):
        try: tag_d = self.gh(f"git/ref/tags/{tag}")
        except HTTPError: raise Exception(f"Failed to find tag {tag}")
        commit_d = self.gh(tag_d["object"]["url"], complete=True)
        self.commit_date = commit_d["committer"]["date"]
        return self.commit_date

    def _issues(self, label):
        return self.gh("issues", state='closed', sort='created', filter='all',
                       since=self.commit_date, labels=label)

    def _issue_groups(self):
        with ProcessPoolExecutor() as ex: return ex.map(self._issues, self.groups.keys())

    def latest_release(self):
        "Tag for the latest release"
        return self.gh("releases/latest")["tag_name"]

    def changelog(self, debug=False):
        "Create the CHANGELOG.md file, or return the proposed text if `debug` is `True`"
        fn = Path('CHANGELOG.md')
        if not fn.exists(): fn.write_text("# Release notes\n\n<!-- do not remove -->\n")
        txt = fn.read_text()
        marker = '<!-- do not remove -->\n'
        try:
            latest = self.latest_release()
            self._tag_date(latest)
        except HTTPError: # no prior releases
            self.commit_date = '2000-01-01T00:00:004Z'
        res = f"\n## {self.cfg['version']}\n"
        issues = self._issue_groups()
        res += '\n'.join(_issues_txt(*o) for o in zip(issues, self.groups.values()))
        res = txt.replace(marker, marker+res+"\n")
        if debug: return res
        shutil.copy(fn, fn.with_suffix(".bak"))
        Path(fn).write_text(res)

    def release(self):
        "Tag and create a release in GitHub for the current version"
        ver = self.cfg['version']
        run_proc('git', 'tag', ver)
        run_proc('git', 'push', '--tags')
        run_proc('git', 'pull', '--tags')
        self.gh("releases", post=True, tag_name=ver, name=ver, body=ver)

# Cell
@call_parse
def fastrelease_changelog():
    "Create a CHANGELOG.md file from closed and labeled GitHub issues"
    FastRelease().changelog()

# Cell
@call_parse
def fastrelease_release():
    "Tag and create a release in GitHub for the current version"
    FastRelease().release()