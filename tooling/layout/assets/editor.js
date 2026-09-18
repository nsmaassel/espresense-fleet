const $ = id => document.getElementById(id);
let source = validate(initial.geometry), geometry = clone(source), images = initial.images;
let storageKey = 'espresense-layout-v1:' + initial.key;
const selected = new Map();
let drag = null;
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function persist() {
  if (!$('persist').checked) return;
  try { localStorage.setItem(storageKey, JSON.stringify(geometry)); }
  catch { $('persist').checked = false; status('Browser storage is unavailable or full. Download geometry.yaml to save your edits.', true); }
}
function restore() {
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) { geometry = validate(JSON.parse(saved)); $('persist').checked = true; status('Restored your saved draft. Download geometry.yaml to keep a portable copy.'); }
  } catch { status('Saved draft could not be restored. Loaded the original source.', true); }
}
function element(tag, text, attrs = {}) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  for (const [k, value] of Object.entries(attrs)) el.setAttribute(k, value);
  return el;
}
function svgElement(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, value] of Object.entries(attrs)) el.setAttribute(k, value);
  return el;
}
function viewBounds() {
  const [[left, bottom], [right, top]] = houseBounds(geometry);
  return [left - .6, -top - .6, right - left + 1.2, top - bottom + 1.2];
}
function transform(f) {
  const sx = f.place.flip_h ? -1 : 1, sy = f.place.flip_v ? -1 : 1;
  return `matrix(${sx} 0 0 ${-sy} ${f.place.dx + (sx < 0 ? f.local.w : 0)} ${-f.place.dy - (sy < 0 ? f.local.h : 0)})`;
}
function update() {
  $('yaml').value = yaml(companion(geometry));
  for (const [index, f] of geometry.floors.entries()) {
    const card = $('floor-' + index), map = card.querySelector('svg');
    map.setAttribute('viewBox', viewBounds().join(' '));
    card.querySelector('.local').setAttribute('transform', transform(f));
    for (const dot of card.querySelectorAll('.node')) {
      const p = f.nodes[dot.dataset.node];
      dot.setAttribute('cx', p[0]); dot.setAttribute('cy', p[1]);
      dot.classList.toggle('selected', selected.get(f.id) === dot.dataset.node);
      const hp = house(f, p), label = dot.label;
      label.setAttribute('x', hp[0] + .2); label.setAttribute('y', -hp[1] - .15);
      dot.setAttribute('aria-label', `${dot.dataset.node}; house x ${hp[0].toFixed(2)}, y ${hp[1].toFixed(2)}, z ${(f.z[0] + p[2]).toFixed(2)} metres. Arrow keys move.`);
    }
    const id = selected.get(f.id), p = f.nodes[id];
    if (p) {
      card.querySelector('.node-select').value = id;
      card.querySelector('.height').value = p[2];
      const hp = house(f, p);
      card.querySelector('.coords').textContent = `House: ${hp[0].toFixed(2)}, ${hp[1].toFixed(2)}, ${(f.z[0] + p[2]).toFixed(2)} m`;
    }
  }
}
function changed(message) { update(); persist(); if (message) status(message); }
function addControl(container, title, type, value, onChange, attrs = {}) {
  const label = element('label', title + ' '), input = element('input', undefined, {type, 'aria-label': title, ...attrs});
  if (type === 'checkbox') input.checked = value; else input.value = value;
  input.addEventListener('change', () => {
    const next = type === 'checkbox' ? input.checked : input.valueAsNumber;
    if (type === 'number' && (!Number.isFinite(next) || !input.checkValidity())) { input.value = value; update(); status('Enter a valid number within the allowed range.', true); return; }
    onChange(next); value = next;
  });
  label.append(input); container.append(label); return input;
}
function render() {
  $('floors').replaceChildren();
  geometry.floors.forEach((f, index) => {
    const card = element('section', undefined, {class: 'floor', id: 'floor-' + index, 'aria-label': String(f.name ?? f.id)});
    card.append(element('h2', String(f.name ?? f.id)));
    const controls = element('div', undefined, {class: 'controls'});
    for (const [key, title] of [['flip_h', 'Flip horizontal'], ['flip_v', 'Flip vertical']]) addControl(controls, title, 'checkbox', f.place[key], value => { f.place[key] = value; changed('Floor alignment updated.'); });
    for (const key of ['dx', 'dy']) addControl(controls, key === 'dx' ? 'Offset X' : 'Offset Y', 'number', f.place[key], value => { f.place[key] = value; changed('Floor alignment updated.'); }, {step: 'any'});
    card.append(controls);
    const map = svgElement('svg', {class: 'map', role: 'group', 'aria-label': `${f.name ?? f.id} node map`});
    const [[x1, y1], [x2, y2]] = geometry.bounds;
    map.append(svgElement('rect', {x: x1, y: -y2, width: x2 - x1, height: y2 - y1, class: 'house-bound'}));
    const group = svgElement('g', {class: 'local'}); map.append(group);
    if (images[f.id] && f.image) {
      const img = images[f.id], {px_per_m: scale, origin_px: [ox, oy]} = f.image;
      group.append(svgElement('image', {href: img.url, x: -ox / scale, y: -oy / scale, width: img.width / scale, height: img.height / scale, transform: 'scale(1 -1)', opacity: '.8'}));
    } else if (f.image) card.append(element('p', 'Plan image not loaded. Rebuild this page with the CLI to embed the referenced PNG.', {class: 'hint'}));
    for (const pts of Object.values(f.rooms)) group.append(svgElement('polygon', {points: pts.map(p => p.join(',')).join(' '), class: 'room'}));
    const nodeIds = Object.keys(f.nodes);
    if (!nodeIds.includes(selected.get(f.id))) selected.set(f.id, nodeIds[0]);
    for (const [id, p] of Object.entries(f.nodes)) {
      const dot = svgElement('circle', {cx: p[0], cy: p[1], r: '.15', class: 'node', tabindex: '0', role: 'button', 'data-node': id});
      const label = svgElement('text', {class: 'node-label'}); label.textContent = id; dot.label = label;
      dot.addEventListener('focus', () => { selected.set(f.id, id); update(); });
      dot.addEventListener('pointerdown', event => {
        event.preventDefault(); selected.set(f.id, id); dot.focus();
        const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(group.getScreenCTM().inverse());
        drag = {dot, group, f, id, offset: [p[0] - local.x, p[1] - local.y]}; dot.setPointerCapture(event.pointerId); update();
      });
      dot.addEventListener('pointermove', event => {
        if (drag?.dot !== dot) return;
        const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(group.getScreenCTM().inverse());
        p[0] = clean(local.x + drag.offset[0]); p[1] = clean(local.y + drag.offset[1]);
        // Keep the viewport stable during the drag; a full update happens on release.
        dot.setAttribute('cx', p[0]); dot.setAttribute('cy', p[1]);
        const hp = house(f, p); label.setAttribute('x', hp[0] + .2); label.setAttribute('y', -hp[1] - .15);
      });
      const finishDrag = () => { if (drag?.dot === dot) { drag = null; changed(`${id} moved. Download geometry.yaml to keep the edit.`); } };
      dot.addEventListener('pointerup', finishDrag); dot.addEventListener('pointercancel', finishDrag);
      dot.addEventListener('keydown', event => {
        const move = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1]}[event.key];
        if (!move) return; event.preventDefault();
        const step = event.shiftKey ? .25 : .05;
        p[0] = clean(p[0] + move[0] * step * (f.place.flip_h ? -1 : 1));
        p[1] = clean(p[1] + move[1] * step * (f.place.flip_v ? -1 : 1)); changed(`${id} nudged.`);
      });
      group.append(dot); map.append(label);
    }
    card.append(map);
    const nodeControls = element('div', undefined, {class: 'node-controls'});
    if (nodeIds.length) {
      const label = element('label', 'Node '), select = element('select', undefined, {class: 'node-select', 'aria-label': 'Selected node'});
      for (const id of nodeIds) select.append(element('option', id, {value: id}));
      select.addEventListener('change', () => { selected.set(f.id, select.value); update(); }); label.append(select); nodeControls.append(label);
      const height = addControl(nodeControls, 'Height above floor', 'number', f.nodes[selected.get(f.id)][2], value => { f.nodes[selected.get(f.id)][2] = value; changed('Node height updated.'); }, {min: 0, max: f.z[1] - f.z[0], step: 'any', class: 'height'});
      height.title = 'Metres above this floor; the floor base is added for Companion.';
      nodeControls.append(element('span', '', {class: 'coords'}));
    } else nodeControls.append(element('p', 'No nodes on this floor. Add named nodes in geometry.yaml and import it again.'));
    card.append(nodeControls); $('floors').append(card);
  });
  update();
}
function download(filename, value) {
  const url = URL.createObjectURL(new Blob([yaml(value)], {type: 'application/yaml;charset=utf-8'}));
  const link = element('a', undefined, {href: url, download: filename}); link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); status(`Downloaded ${filename}.`);
}
$('geometry').onclick = () => download('geometry.yaml', geometry);
$('companion').onclick = () => download('companion-floors-and-nodes.yaml', companion(geometry));
$('copy').onclick = async () => {
  try { await navigator.clipboard.writeText($('yaml').value); status('Companion YAML copied.'); }
  catch { $('yaml').focus(); $('yaml').select(); status('Clipboard unavailable. The YAML is selected; press Ctrl+C or download it.'); }
};
$('persist').onchange = () => {
  if ($('persist').checked) { persist(); if ($('persist').checked) status('Draft saving enabled for this source file.'); }
  else { try { localStorage.removeItem(storageKey); status('Saved draft removed. Download geometry.yaml to keep changes.'); } catch { status('Browser storage is unavailable.', true); } }
};
$('reset').onclick = () => { geometry = clone(source); render(); persist(); status('Restored the imported source.'); };
$('import').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    const text = await file.text(), next = validate(jsyaml.load(text, {schema: jsyaml.JSON_SCHEMA}));
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(next)));
    const nextKey = 'espresense-layout-v1:' + Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
    // A filename is not image identity; a new import must never reuse an old plan.
    images = {}; source = next; geometry = clone(next); storageKey = nextKey;
    $('persist').checked = false; selected.clear(); status(`Imported ${file.name}.`); restore(); render();
  } catch (error) { status('Import failed: ' + error.message, true); }
  event.target.value = '';
};
restore(); render();
