"""Check the static presentation without opening the application or account data."""
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.targets = [], [], []
        self.prompt, self.in_prompt = [], False
        self.github_links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.append(values['id'])
        for key in ('href', 'src'):
            if key in values:
                self.links.append(values[key])
        if 'aria-controls' in values:
            self.targets.append(values['aria-controls'])
        if 'data-copy' in values:
            self.targets.append(values['data-copy'])
        if tag == 'a' and 'data-github' in values:
            self.github_links.append(values['href'])
        if tag == 'pre' and values.get('id') == 'agent-prompt':
            self.in_prompt = True

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.in_prompt = False

    def handle_data(self, data):
        if self.in_prompt:
            self.prompt.append(data)


def main():
    pages = {}
    for name in ['index.html', 'install-windows.html', 'install-macos.html']:
        item = Page()
        item.feed((ROOT / 'docs' / name).read_text(encoding='utf-8'))
        pages[name] = item
    for name, item in pages.items():
        if len(item.ids) != len(set(item.ids)):
            raise AssertionError(f'Duplicate IDs in {name}')
        if not all(target in item.ids for target in item.targets):
            raise AssertionError(f'Missing control in {name}')
        for url in item.links:
            if url.startswith(('https://', 'http://')):
                continue
            path, _, anchor = url.partition('#')
            path = path.split('?')[0]
            if path:
                if not (ROOT / 'docs' / path).is_file():
                    raise AssertionError(f'Missing local file: {ROOT / "docs" / path} in ({name}, {url})')
            if anchor:
                if anchor not in pages[path or name].ids:
                    raise AssertionError(f'Missing anchor: {anchor} in ({name}, {url})')
    page = Page()
    page.feed((ROOT / 'docs/index.html').read_text(encoding='utf-8'))
    if len(page.ids) != len(set(page.ids)):
        raise AssertionError('Duplicate IDs')
    for url in page.links:
        if url.startswith('#'):
            if not (url == '#' or url[1:] in page.ids):
                raise AssertionError(f'Invalid fragment link: {url}')
        elif not url.startswith(('https://', 'http://')):
            if not (ROOT / 'docs' / re.split(r'[?#]', url)[0]).is_file():
                raise AssertionError(f'Missing local file: {url}')
    if not all(target in page.ids for target in page.targets):
        raise AssertionError('Missing control target')
    if len(page.github_links) < 5:
        raise AssertionError('Expected at least 5 GitHub links')
    if not all(url.startswith('https://github.com/brunoflma/claude-session-linker') for url in page.github_links):
        raise AssertionError('Found unexpected GitHub link')
    if ''.join(page.prompt).strip() != (ROOT / 'docs/agent-setup-prompt.txt').read_text(encoding='utf-8').strip():
        raise AssertionError('Prompt download differs')
    for entry in re.findall(r'url\([\'"]?([^\'"\)]+)', (ROOT / 'docs/assets/site.css').read_text(encoding='utf-8')):
        if not (ROOT / 'docs/assets' / entry).is_file():
            raise AssertionError(f'Asset file not found: {entry}')
    image = (ROOT / 'docs/assets/social-preview.png').read_bytes()
    if image[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError('Invalid PNG signature')
    if (int.from_bytes(image[16:20]), int.from_bytes(image[20:24])) != (1280, 640):
        raise AssertionError('Invalid PNG dimensions')
    script = (ROOT / 'docs/assets/site.js').read_text(encoding='utf-8')
    if re.search(r'fetch\(|XMLHttpRequest|localStorage|document\.cookie|innerHTML', script):
        raise AssertionError('Keep the fictional demo local and text-only')
    print('Verified: links, controls, local assets, prompt parity, GitHub destinations and fictional demo boundaries.')


if __name__ == '__main__':
    main()
