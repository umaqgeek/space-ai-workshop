"""Pass GitHub's admin secret to Heroku at runtime, then deploy the checkout."""
import base64
import json
import os
import re
import subprocess
import urllib.request


def main():
    password = os.environ.get('ADMIN_PASSWORD', '')
    api_key = os.environ.get('HEROKU_API_KEY', '')
    app = os.environ.get('HEROKU_APP_NAME', '')
    if not password or not api_key or not re.fullmatch(r'[a-z][a-z0-9-]{2,29}', app):
        raise SystemExit('Set ADMIN_PASSWORD and HEROKU_API_KEY secrets and a valid HEROKU_APP_NAME variable.')
    request = urllib.request.Request(
        f'https://api.heroku.com/apps/{app}/config-vars',
        data=json.dumps({'ADMIN_PASSWORD': password}).encode(), method='PATCH',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
                 'Accept': 'application/vnd.heroku+json; version=3'},
    )
    # The response contains config secrets; never print or persist it.
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()
    environment = os.environ.copy()
    authorization = base64.b64encode(f'heroku:{api_key}'.encode()).decode()
    environment.update(GIT_CONFIG_COUNT='1',
                       GIT_CONFIG_KEY_0=f'http.https://git.heroku.com/{app}.git.extraheader',
                       GIT_CONFIG_VALUE_0=f'Authorization: Basic {authorization}',
                       GIT_TERMINAL_PROMPT='0')
    subprocess.run(['git', 'push', f'https://git.heroku.com/{app}.git', 'HEAD:main'],
                   env=environment, check=True)


if __name__ == '__main__':
    main()
