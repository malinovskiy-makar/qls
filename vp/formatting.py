"""Source emphasis only: underline, emphasis and strong text, without HTML attributes."""
import re

from django.utils.html import escape, format_html, format_html_join

from problems.rendering import _math_span_end

_TAG = re.compile(r'</?(?:u|em|strong)>')
_WRAP = {'u': '<u>{}</u>', 'em': '<em>{}</em>', 'strong': '<strong>{}</strong>'}


def _tokens(text):
    start = pos = 0
    while pos < len(text):
        if text[pos:pos + 2] == r'\$':
            pos += 2
            continue
        end = _math_span_end(text, pos)
        if end > pos:
            # Even literal <u> inside TeX is text, never an HTML element.
            pos = end
            continue
        tag = _TAG.match(text, pos)
        if tag:
            yield False, text[start:pos]
            yield True, tag.group()
            start = pos = tag.end()
        else:
            pos += 1
    yield False, text[start:]


def inline_text(value):
    """Escape everything except balanced exact <u>, <em> and <strong> tags."""
    tokens = list(_tokens(str(value or '')))
    stack = []
    balanced = True
    for is_tag, token in tokens:
        if not is_tag:
            continue
        if token.startswith('</'):
            if not stack or stack.pop() != token[2:-1]:
                balanced = False
                break
        else:
            stack.append(token[1:-1])
    balanced = balanced and not stack
    if not balanced:
        return escape(str(value or ''))
    fragments = [[]]
    for is_tag, token in tokens:
        if not is_tag:
            # Escape unconditionally, including SafeString input.
            fragments[-1].append(escape(token))
        elif not token.startswith('</'):
            fragments.append([])
        else:
            inner = format_html_join('', '{}', ((x,) for x in fragments.pop()))
            fragments[-1].append(format_html(_WRAP[token[2:-1]], inner))
    return format_html_join('', '{}', ((x,) for x in fragments[0]))


def plain_inline(value):
    """Plain preview label; do not cut an opening tag into a headline."""
    return ''.join(token for is_tag, token in _tokens(str(value or '')) if not is_tag)
