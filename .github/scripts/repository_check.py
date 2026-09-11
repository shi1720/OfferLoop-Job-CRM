"""Offline repository checks. Does not import applications or call providers.

Checks tracked and new non-ignored files, never prints credential values.
This is a focused regression guard, not a substitute for full secret scanning.
"""
import ast
import pathlib
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

KEYS = re.compile(r'(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}|AIza[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9_]{25,})')
PRIVATE_KEY = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
LITERAL_SECRET = re.compile(r'''(?im)^\s*(?:const |let |var )?[\w]*(?:API_KEY|API_TOKEN|SECRET_KEY|ACCESS_TOKEN)\s*=\s*["']([^"'\n]{24,})["']''')
FORBIDDEN = {'.env', 'credentials-2.json', 'qc-incept-firebase-credentials.json'}

def credential_findings(source):
    found = [(m.start(), 'provider credential') for m in KEYS.finditer(source)]
    found += [(m.start(), 'private key') for m in PRIVATE_KEY.finditer(source)]
    for m in LITERAL_SECRET.finditer(source):
        value = m.group(1)
        if not any(word in value.lower() for word in ['example', 'placeholder', 'your-', 'your_', 'test-', 'replace', 'https://']):
            found.append((m.start(), 'literal credential assignment'))
    return found

def self_test():
    assert credential_findings('x = "' + 'sk-proj-' + 'a' * 40 + '"')
    assert credential_findings('-----BEGIN ' + 'PRIVATE KEY-----')
    assert credential_findings('const PROVIDER_API_KEY = "' + 'z' * 40 + '";')
    assert not credential_findings('API_KEY = os.environ["OPENAI_API_KEY"]')
    assert not credential_findings('EXAMPLE_API_KEY = "your-provider-key-placeholder"')
    print('Credential guard self-tests passed.')

def main():
    if '--self-test' in sys.argv:
        self_test()
        return
    root = pathlib.Path.cwd()
    files = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).decode().split('\0')
    errors = []
    checked = 0
    for name in sorted(set(filter(None, files))):
        p = root / name
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        if p.name in FORBIDDEN:
            errors.append(f'{name}: credentials/configuration file must not be tracked')
        try:
            source = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        checked += 1
        for offset, kind in credential_findings(source):
            line = source.count('\n', 0, offset) + 1
            errors.append(f'{name}:{line}: possible {kind}; value withheld')
        if p.suffix == '.py':
            try:
                ast.parse(source, filename=name)
            except SyntaxError as error:
                errors.append(f'{name}:{error.lineno}: Python syntax error: {error.msg}')
        if p.suffix.lower() == '.md':
            # Fenced snippets may intentionally show example URLs or paths.
            prose = re.sub(r'```.*?```', '', source, flags=re.S)
            for match in re.finditer(r'\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', prose):
                target = match.group(1).strip('<>')
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path or target.startswith('/'):
                    continue
                if not (p.parent / unquote(url.path)).exists():
                    errors.append(f'{name}: missing local link target {url.path}')
    readme = root / 'README.md'
    if not readme.exists() or len(readme.read_text().strip()) < 80:
        errors.append('README.md: describe the project and its actual status')
    if errors:
        print('\n'.join(errors))
        raise SystemExit(1)
    print(f'Checked {checked} text files: Python syntax, local documentation links and credential patterns passed.')

if __name__ == '__main__':
    main()
