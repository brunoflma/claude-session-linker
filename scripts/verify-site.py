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
    page = Page()
    page.feed((ROOT / 'docs/index.html').read_text(encoding='utf-8'))
    assert len(page.ids) == len(set(page.ids)), 'Duplicate IDs'
    for url in page.links:
        if url.startswith('#'):
            assert url == '#' or url[1:] in page.ids, url
        elif not url.startswith(('https://', 'http://')):
            assert (ROOT / 'docs' / re.split(r'[?#]', url)[0]).is_file(), url
    assert all(target in page.ids for target in page.targets), 'Missing control target'
    assert len(page.github_links) >= 5
    assert all(url.startswith('https://github.com/brunoflma/claude-session-linker') for url in page.github_links)
    assert ''.join(page.prompt).strip() == (ROOT / 'docs/agent-setup-prompt.txt').read_text(encoding='utf-8').strip(), 'Prompt download differs'
    for entry in re.findall(r'url\([\'"]?([^\'"\)]+)', (ROOT / 'docs/assets/site.css').read_text(encoding='utf-8')):
        assert (ROOT / 'docs/assets' / entry).is_file(), entry
    image = (ROOT / 'docs/assets/social-preview.png').read_bytes()
    assert image[:8] == b'\x89PNG\r\n\x1a\n'
    assert (int.from_bytes(image[16:20]), int.from_bytes(image[20:24])) == (1280, 640)
    script = (ROOT / 'docs/assets/site.js').read_text(encoding='utf-8')
    assert not re.search(r'fetch\(|XMLHttpRequest|localStorage|document\.cookie|innerHTML', script), 'Keep the fictional demo local and text-only'
    print('Verified: links, controls, local assets, prompt parity, GitHub destinations and fictional demo boundaries.')


if __name__ == '__main__':
    main()
