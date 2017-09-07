# git-slack-post-receive
Git post-receive hook for Slack in Python 3. Configurable in .git/config AND a config file inside the repo.

## Usage
### Installation & Configuration

Install `git-slack-hook.py` to your repository's `.git/hooks` directory and
rename it `post-receive` (or symlink `post-receive` ->
`<repodir>/git-slack-hook.py`). Make sure it's executable (`chmod 755`).

Your Python 3 setup will need to have the _python-dateutil_ library installed.

Configuration is handled through `git config` and/or `.git_slack_hook.conf` from the repository's master branch (config file name and branch can be customized). Most of the configuration options can be defined in either way:

These may be set *only in `.git/config`*:

    'hooks.slack.webhook-url'   [REQUIRED]
        Secret URL for Slack web hook. Used for posting JSON messages to Slack.

    'hooks.slack.in-repo-hook-config-file'
        Argument for 'git show' to read configuration file from repository itself.
        Default: 'master:.git_slack_hook.conf'

These can be either in `.git/config` or repository (repository config overrides `.git/config`):

    'hooks.slack.channel'   [REQUIRED]
        Channel string to post to. Can be '#channelname', '@user_name' etc.

    'hooks.slack.commit-url'
        Should contain {commit} as placeholder for commit hash, and may contain {reponame}

    'hooks.slack.branch-regex'
        Regular expression to filter pushed references. If this doesn't match,
        no message is posted. NOTE: This matches raw ref string, not branch name --
        master, for example, is: 'refs/heads/master'
        Default: '.*'

    'hooks.slack.repository-title'
        Human readable name for the repository.
        Default: use directory name.

    'hooks.slack.bot-name'
        Display name for the Slack message pusher.
        Default: 'GIT push'

    'hooks.slack.bot-icon'
        Slack icon for the message.
        Default: ':cherries:'

    'hooks.slack.hide-merges'
        If '1', don't show merges.
        Default: '0'

    'hooks.slack.strip-bare-git-extension'
        If '1', remove ".git" when determining repository name (for use with commit-url).
        Default: '1'

Note that only two of the options are required: `hooks.slack.webhook-url` and `hooks.slack.channel`.

The format of `.git_slack_hook.conf` looks like this:

    hooks.slack.channel = #my_commit_channel
    hooks.slack.icon-emoji = :cherries:
    hooks.slack.hide-merges = 1

This is parsed by splitting at first '='. Don't quote values.

Alternatively, using .git/config:

    $ git config hooks.slack.channel "#my_commit_channel"
    $ git config hooks.slack.icon-emoji ":cherries:"
    $ git config hooks.slack.hide-merges "1"

## License

This code is copyright (c) 2017 by Jarno Elonen,
based on [notify-webhook](https://github.com/metajack/notify-webhook) (c) 2008-2015 by Jack Moffitt <jack@metajack.im> and
others; and is available under the [GPLv3](http://www.gnu.org/licenses/gpl.html).
See `LICENSE` for details.
