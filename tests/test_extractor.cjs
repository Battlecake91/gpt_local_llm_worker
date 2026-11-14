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
