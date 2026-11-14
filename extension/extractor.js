/* Rendered ChatGPT text -> plain UTF-8 transport text with fenced code blocks. */
(function (root) {
  'use strict';
  const SELECTOR = '[data-markdown-text-style="assistant-message"],.markdown,[data-message-text],pre';
  const SKIP = new Set(['BUTTON','SVG','STYLE','SCRIPT','NOSCRIPT','TEXTAREA','INPUT']);
  const BLOCK = new Set(['P','H1','H2','H3','H4','H5','H6','BLOCKQUOTE','LI','UL','OL','TABLE','TR']);
  const nodes = element => Array.from(element.childNodes || []);
  function render(element) {
    if (element.nodeType === 3) return (element.textContent || '').replace(/\s+/g, ' ');
    if (element.nodeType !== 1) return '';
    const tag = element.tagName?.toUpperCase() || '';
    if (SKIP.has(tag) || element.getAttribute?.('aria-hidden') === 'true') return '';
    if (tag === 'BR') return '\n';
    if (tag === 'PRE') {
      const code = element.querySelector?.('code') || element;
      const raw = (code.textContent || '').replace(/\r\n?/g, '\n').replace(/\n$/, '');
      const className = code.getAttribute?.('class') || '';
      const language = /(?:^|\s)language-([\w+#.-]+)/.exec(className)?.[1] || '';
      const runs = raw.match(/`+/g) || [];
      const fence = '`'.repeat(Math.max(3, ...runs.map(x => x.length + 1)));
      return `${fence}${language}\n${raw}\n${fence}\n\n`;
    }
    let body = nodes(element).map(render).join('');
    if (!nodes(element).length) body = element.innerText ?? element.textContent ?? '';
    if (tag === 'CODE') return `\`${body}\``;
    if (tag === 'LI') return `- ${body.trim()}\n`;
    if (BLOCK.has(tag)) return `${body.trim()}\n\n`;
    return body;
  }
  function extract(message) {
    if (!message) return '';
    const candidates = [...(message.querySelectorAll?.(SELECTOR) || [])];
    // Selected subtrees must not be serialized twice (e.g. <pre> inside markdown).
    const top = candidates.filter((candidate, i) => !candidates.some((prior, j) => j < i && prior.contains?.(candidate)));
    if (!top.length) return (message.innerText ?? message.textContent ?? '').replace(/\r\n?/g, '\n');
    return top.map(render).map(s => s.replace(/^\n+|\n+$/g, '')).filter(Boolean).join('\n\n');
  }
  root.BridgeExtractor = { extract, render };
  if (typeof module !== 'undefined') module.exports = root.BridgeExtractor;
})(typeof globalThis !== 'undefined' ? globalThis : this);
