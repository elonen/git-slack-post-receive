#!/usr/bin/env python3

import sys, re, os, subprocess, io, requests,json
import urllib.request, urllib.parse, urllib.error
from datetime import datetime
from collections import OrderedDict
from time import ctime
import dateutil.parser

'''
=====================
Configuration options
=====================

Only in .git/config:

    'hooks.slack.webhook-url'   [REQUIRED]
        Secret URL for Slack web hook. Used for posting JSON messages to Slack.

    'hooks.slack.in-repo-hook-config-file'
        Argument for 'git show' to read configuration file from repository itself.
        Default: 'master:.git_slack_hook.conf'

Either in .git/config or repository (repository config overrides .git/config):

    'hooks.slack.channel'   [REQUIRED]
        Channel string to post to. Can be '#channelname', '@user_name' etc.

    'hooks.slack.commit-url'
        Should contain {commit} as placeholder for commit hash, and may contain {reponame}

    'hooks.slack.branch-regex'
        Regular expression to filter pushed references. If this doesn't match,
        no message is posted. NOTE: This matches raw ref string, not branch name --
        master, for example, is: 'refs/heads/master'
        Default: '.*'

    'hooks.slack.bot-name'
        Display name for the Slack message pusher.
        Default: 'GIT push'

    'hooks.slack.repository-title'
        Human readable name for the repository.
        Default: use directory name.

    'hooks.slack.bot-icon'
        Slack icon for the message.
        Default: ':cherries:'

    'hooks.slack.hide-merges'
        If '1', don't show merges.
        Default: '0'

    'hooks.slack.strip-bare-git-extension'
        If '1', remove ".git" when determining repository name (for use with commit-url).
        Default: '1'

'''

EMAIL_RE = re.compile("^\"?(.*)\"? <(.*)>$")
DIFF_TREE_RE = re.compile("^:(?P<src_mode>[0-9]{6}) (?P<dst_mode>[0-9]{6}) (?P<src_hash>[0-9a-f]{7,40}) (?P<dst_hash>[0-9a-f]{7,40}) (?P<status>[ADMTUX]|[CR][0-9]{1,3})\s+(?P<file1>\S+)(?:\s+(?P<file2>\S+))?$", re.MULTILINE)

def git(args, silent_stderr=False):
    args = ['git'] + args
    if silent_stderr:
        git = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        git = subprocess.Popen(args, stdout=subprocess.PIPE)        
    details = git.stdout.read()
    details = details.decode("utf-8").strip()
    return details

def _git_config():
    raw_config = git(['config', '-l', '-z'])
    items = raw_config.split("\0")
    # remove empty items
    items = filter(lambda i: len(i) > 0, items)
    # split into key/value based on FIRST \n; allow embedded \n in values
    items = [item.partition("\n")[0:3:2] for item in items]
    return OrderedDict(items)

GIT_CONFIG = _git_config()


CONFIG_FILE_IN_REPOSITORY = GIT_CONFIG.get('hooks.slack.in-repo-hook-config-file', 'master:.git_slack_hook.conf')

def _git_repo_config():
    raw_config = git(['show', CONFIG_FILE_IN_REPOSITORY ], silent_stderr=True)
    items = raw_config.split("\n")
    # remove empty items and comments
    items = filter(lambda i: len(i.strip())>0 and i.strip()[0]!='#', items)
    items = [[x.strip() for x in item.partition("=")[0:3:2]] for item in items]  # split by '=''
    return OrderedDict(items)

REPO_CONFIG = _git_repo_config()

def get_git_config(key, default=None):
    return GIT_CONFIG.get(key, default)

def get_in_repo_config(key, default=None):
    return REPO_CONFIG.get(key, default)

def get_any_config(key, default=None):
    return get_in_repo_config(key) or get_git_config(key) or default

def get_repo_name():
    if get_git_config('core.bare', 'false') == 'true':
        name = os.path.basename(os.getcwd())
        if name.endswith('.git') and get_any_config('hooks.slack.strip-bare-git-extension', '1') != '0':
            name = name[:-4]
        return name
    else:
        return os.path.basename(os.path.dirname(os.getcwd()))


COMMIT_URL = get_any_config('hooks.slack.commit-url')

def get_revisions(old, new, head_commit=False):
    if re.match("^0+$", old):
        if not head_commit:
            return []

        commit_range = '%s~1..%s' % (new, new)
    else:
        commit_range = '%s..%s' % (old, new)

    revs = git(['rev-list', '--pretty=medium', '--reverse', commit_range])
    sections = revs.split('\n\n')

    revisions = []
    s = 0
    while s < len(sections):
        lines = sections[s].split('\n')

        # first line is 'commit HASH\n'
        props = {'id': lines[0].strip().split(' ')[1], 'added': [], 'removed': [], 'modified': []}

        # call git diff-tree and get the file changes
        output = git(['diff-tree', '-r', '-C', '%s' % props['id']])

        # sort the changes into the added/modified/removed lists
        for i in DIFF_TREE_RE.finditer(output):
            item = i.groupdict()
            if item['status'] == 'A':      # addition of a file
                props['added'].append(item['file1'])
            elif item['status'][0] == 'C': # copy of a file into a new one
                props['added'].append(item['file2'])
            elif item['status'] == 'D':    # deletion of a file
                props['removed'].append(item['file1'])
            elif item['status'] == 'M':    # modification of the contents or mode of a file
                props['modified'].append(item['file1'])
            elif item['status'][0] == 'R': # renaming of a file
                props['removed'].append(item['file1'])
                props['added'].append(item['file2'])
            elif item['status'] == 'T':    # change in the type of the file
                 props['modified'].append(item['file1'])
            else:   # Covers U (file is unmerged)
                    # and X ("unknown" change type, usually an error)
                pass    # When we get X, we do not know what actually happened so
                        # it's safest just to ignore it. We shouldn't be seeing U
                        # anyway, so we can ignore that too.

        # read the header
        for l in lines[1:]:
            key, val = l.split(' ', 1)
            props[key[:-1].lower()] = val.strip()

        # read the commit message
        # Strip leading tabs/4-spaces on the message
        props['message'] = re.sub(r'^(\t| {4})', '', sections[s+1], 0, re.MULTILINE)

        # use github time format
        basetime = datetime.strptime(props['date'][:-6], "%a %b %d %H:%M:%S %Y")
        tzstr = props['date'][-5:]
        props['date'] = basetime.strftime('%Y-%m-%dT%H:%M:%S') + tzstr

        # split up author
        m = EMAIL_RE.match(props['author'])
        if m:
            props['name'] = m.group(1)
            props['email'] = m.group(2)
        else:
            props['name'] = 'unknown'
            props['email'] = 'unknown'
        del props['author']

        if head_commit:
            return props

        revisions.append(props)
        s += 2

    return revisions


def post_slack(old, new, ref):

    # sys.stderr.write('%s post receive hook: %s %s %s\n' % (datetime.now(), str(old), str(new), str(ref)))

    webhook_url = get_git_config('hooks.slack.webhook-url')
    if webhook_url is None:
        sys.stderr.write('Slack hook: No webhook_url set.\n')
        sys.exit(0)

    branch_regex = get_any_config('hooks.slack.branch-regex') or '.*'
    if not re.match( branch_regex, str(ref)):
        # sys.stderr.write('NOTE: Reference "%s" does not match branch_regex. Not uploading message.\n')
        sys.exit(0)

    slack_botname = get_any_config('hooks.slack.bot-name') or "GIT push"
    slack_icon = get_any_config('hooks.slack.bot-icon') or ":cherries:"

    slack_channel = get_any_config('hooks.slack.channel')
    if slack_channel is None:
        sys.stderr.write('Slack hook: No slack_channel set.\n')
        sys.exit(0)

    repo_name = get_repo_name()

    revisions = get_revisions(old, new)
    commits = []
    for r in revisions:
          
        parents = git(['show', '--no-patch', '--format="%P"', str(r['id']) ]).split(' ')
        is_merge = len(parents) >= 2
        if is_merge and get_any_config('hooks.slack.hide-merges', '0') != '0':
            continue

        c = {
            "fallback": 'Commit #{commit} by {author} on {timestamp}:\n{message}'.format(
                commit = r['id'][:7],
                author = '%s <%s>' % (r['name'], r['email']),
                timestamp = r['date'],
                message = r['message']),
            "author_name": r['name'],
            "author_link": 'mailto:' + r['email'],
            "title": str(r['id'])[:7],
            "text": str(r['message']),
            "ts": dateutil.parser.parse(r['date']).timestamp()
        }
        if len(parents) == 2:
            c['color'] = 'good'
            c['title'] += "   ( merge %s )" % ' + '.join([ x[:7] for x in parents])

        if COMMIT_URL is not None:
            c['title_link'] = COMMIT_URL.format(
                commit=r['id'],
                reponame=repo_name )
        commits.append(c)

    repo_title = get_any_config('hooks.slack.repository-title') or repo_name

    content = {
        "channel": slack_channel,
        "username": slack_botname,
        "icon_emoji": slack_icon,
        "text": "[%s / *%s*] %d commits" % (str(repo_title), str(ref).replace('refs/heads/',''), len(commits)),
        "attachments": commits }
    
    r = requests.post(webhook_url, json=content)
    if r.status_code != 200:
        sys.stderr.write('Slack hook: HTTP error status %s: %s' %(str(r.status_code), str(r.text)))
        sys.exit(2)


if __name__ == '__main__':
    for line in sys.stdin:
        old, new, ref = line.strip().split(' ')
        post_slack(old, new, ref)
