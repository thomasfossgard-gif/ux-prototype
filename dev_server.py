#!/usr/bin/env python3
"""Dev server for UXPrototype.

Extends SimpleHTTPRequestHandler with POST /save-visual-styles, which
rewrites the VISUAL_STYLES_DEFAULT block in index.html. Used by the
Visuals tab's "Save to Code" button so visual tweaks become defaults
without leaving the browser.
"""
import http.server
import json
import re
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ROOT = Path(__file__).parent.resolve()
INDEX = ROOT / 'index.html'

VS_BLOCK_PATTERN = re.compile(r'const VISUAL_STYLES_DEFAULT = \{[\s\S]*?\n\};')

JS_IDENT = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*$')


def js_string(s):
    """Serialize a Python string as a single-quoted JS string literal."""
    out = ["'"]
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == "'":
            out.append("\\'")
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 0x20:
            out.append('\\u%04x' % ord(ch))
        else:
            out.append(ch)
    out.append("'")
    return ''.join(out)


def js_serialize(value, indent=2, level=1):
    """Serialize a Python value as a JS literal matching the project's style:
    unquoted keys when they're valid identifiers, single-quoted strings, trailing
    commas after every item.
    """
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return js_string(value)
    if isinstance(value, list):
        if not value:
            return '[]'
        prefix = ' ' * (indent * level)
        outer = ' ' * (indent * (level - 1))
        items = ',\n'.join(prefix + js_serialize(v, indent, level + 1) for v in value)
        return '[\n' + items + ',\n' + outer + ']'
    if isinstance(value, dict):
        if not value:
            return '{}'
        prefix = ' ' * (indent * level)
        outer = ' ' * (indent * (level - 1))
        lines = []
        for k, v in value.items():
            key = k if (isinstance(k, str) and JS_IDENT.match(k)) else json.dumps(k)
            lines.append(prefix + key + ': ' + js_serialize(v, indent, level + 1))
        return '{\n' + ',\n'.join(lines) + ',\n' + outer + '}'
    raise ValueError(f'Unsupported type: {type(value).__name__}')


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != '/save-visual-styles':
            self.send_error(404, 'Unknown endpoint')
            return
        length = int(self.headers.get('Content-Length', '0'))
        try:
            data = json.loads(self.rfile.read(length))
        except Exception as e:
            self._json_response(400, {'ok': False, 'error': f'Invalid JSON: {e}'})
            return
        try:
            self._patch_index(data)
        except Exception as e:
            self._json_response(500, {'ok': False, 'error': str(e)})
            return
        self._json_response(200, {'ok': True})

    def _patch_index(self, data):
        text = INDEX.read_text(encoding='utf-8')
        if not VS_BLOCK_PATTERN.search(text):
            raise RuntimeError('VISUAL_STYLES_DEFAULT block not found in index.html')
        body = js_serialize(data)
        new_block = 'const VISUAL_STYLES_DEFAULT = ' + body + ';'
        # lambda replacement so backslashes in JSON aren't interpreted as backreferences.
        new_text = VS_BLOCK_PATTERN.sub(lambda m: new_block, text, count=1)
        tmp = INDEX.with_suffix('.html.tmp')
        tmp.write_text(new_text, encoding='utf-8')
        tmp.replace(INDEX)

    def _json_response(self, code, body):
        payload = json.dumps(body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        sys.stderr.write('[%s] %s\n' % (self.log_date_time_string(), fmt % args))


def main():
    server = http.server.ThreadingHTTPServer(('', PORT), Handler)
    print(f'Serving {ROOT} on http://localhost:{PORT}')
    print('  POST /save-visual-styles  -> writes index.html')
    print('Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
