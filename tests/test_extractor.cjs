const test=require('node:test');
const assert=require('node:assert/strict');
const {extract}=require('../extension/extractor.js');
function txt(s){return {nodeType:3,textContent:s};}
function el(tag,children=[],attrs={}){
  const node={nodeType:1,tagName:tag.toUpperCase(),childNodes:children,
    getAttribute:k=>attrs[k]||null, contains(other){return this===other||children.some(x=>x.contains?.(other))},
    querySelector(selector){return selector==='code'?children.find(x=>x.tagName==='CODE')||null:null},
    get textContent(){return children.map(x=>x.textContent||'').join('')}
  };return node;
}
function message(section){return {querySelectorAll:()=>section,innerText:'fallback'};}
test('multiline code, paragraph boundaries, interface buttons and whitespace preserved',()=>{
  const code=el('code',[txt('import random\nzahlen = [1, 2]\n    print(zahlen)\n')],{class:'language-python'});
  const pre=el('pre',[code]);
  const markdown=el('div',[el('p',[txt('Einleitung')]),el('button',[txt('Ausführen')]),pre,el('p',[txt('Erklärung 1')]),el('p',[txt('Erklärung 2')])]);
  const result=extract(message([markdown,pre]));
  assert.equal(result,'Einleitung\n\n```python\nimport random\nzahlen = [1, 2]\n    print(zahlen)\n```\n\nErklärung 1\n\nErklärung 2');
  assert.ok(!result.includes('Ausführen'));
});
test('separate markdown and pre blocks are extracted in source order',()=>{
  const first=el('p',[txt('Vorher')]),pre=el('pre',[el('code',[txt('a\nb')])]),last=el('p',[txt('Nachher')]);
  assert.equal(extract(message([first,pre,last])),'Vorher\n\n```\na\nb\n```\n\nNachher');
});
test('fallback preserves existing fixtures without structured DOM',()=>{
  assert.equal(extract({querySelectorAll:()=>[],innerText:'A\nB'}),'A\nB');
});
test('fences expand when code itself contains backticks',()=>{
  const pre=el('pre',[el('code',[txt('```\nexample')])]);
  assert.ok(extract(message([pre])).startsWith('````\n'));
});

test('preserves literal newlines in non-pre text nodes instead of collapsing whitespace',()=>{
  const container=el('div',[txt('Zeile 1\n    Zeile 2\nZeile 3')]);
  assert.equal(extract(message([container])),'Zeile 1\n    Zeile 2\nZeile 3');
});
test('emphasis and inline code stay distinguishable in transported message',()=>{
  const p=el('p',[el('strong',[txt('Erklärung:')]),txt(' Nutze '),el('code',[txt('divmod()')]),txt(' für die Zeit.')]);
  assert.equal(extract(message([p])),'**Erklärung:** Nutze `divmod()` für die Zeit.');
});
test('structure probe reports only bounded tags, counts and newline metadata',()=>{
  const {inspectStructure}=require('../extension/extractor.js');
  const root=el('div',[el('p',[txt('PRIVATER TEXT\nweiter')]),el('pre',[el('code',[txt('SECRET CODE')])])]);
  const result=inspectStructure(root);
  assert.equal(result.counts.pre,1);
  assert.equal(result.counts.code,1);
  assert.equal(result.outline.find(x=>x.tag==='p').directNewlines,1);
  assert.ok(!JSON.stringify(result).includes('PRIVATER TEXT'));
  assert.ok(!JSON.stringify(result).includes('SECRET CODE'));
});

test('modern editor-style code lines retain indentation and order',()=>{
  const lines=[
    el('div',[txt('def countdown(n):')]),
    el('div',[txt('    for i in range(n):')]),
    el('div',[txt('        print(i)')])
  ];
  const editor=el('div',lines,{'data-code-block':'true','data-language':'python'});
  editor.querySelectorAll=selector=>selector.includes('.cm-line')?lines:[];
  const result=extract(message([editor]));
  assert.equal(result,'```python\ndef countdown(n):\n    for i in range(n):\n        print(i)\n```');
});
test('pre code prefers rendered line boundaries if textContent flattened',()=>{
  const code=el('code',[txt('a=1b=2')]);
  code.innerText='a=1\nb=2';
  const pre=el('pre',[code]);
  assert.equal(extract(message([pre])),'```\na=1\nb=2\n```');
});
