/* Geometry stays in local coordinates; projection happens only at the boundary. */
const clone = value => JSON.parse(JSON.stringify(value));
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const point = (value, n) => Array.isArray(value) && value.length === n && value.every(Number.isFinite);
const clean = value => Number(value.toFixed(10));
function validate(value) {
  const g = clone(value); // Reject cyclic YAML aliases; never retain parser-owned objects.
  if (!plain(g) || !Array.isArray(g.floors) || !g.floors.length) throw Error('A nonempty floors list is required.');
  if (!Array.isArray(g.bounds) || g.bounds.length !== 2 || !g.bounds.every(p => point(p, 2)) || ![0, 1].every(i => g.bounds[1][i] > g.bounds[0][i])) throw Error('Bounds must be two increasing [x, y] points.');
  const ids = new Set(), nodes = new Set();
  for (const f of g.floors) {
    if (!plain(f) || typeof f.id !== 'string' || !f.id || ids.has(f.id)) throw Error('Floor ids must be unique strings.');
    ids.add(f.id);
    if ('name' in f && typeof f.name !== 'string') throw Error('Floor name must be a string.');
    if (!point(f.z, 2) || f.z[1] <= f.z[0]) throw Error('Floor z must be [base, ceiling].');
    if (!plain(f.local) || !['w', 'h'].every(k => Number.isFinite(f.local[k]) && f.local[k] > 0)) throw Error('Local width and height must be positive.');
    f.place ??= {};
    if (!plain(f.place)) throw Error('Placement must be a mapping.');
    for (const [k, fallback] of Object.entries({flip_h: false, flip_v: false, dx: 0, dy: 0})) f.place[k] ??= fallback;
    if (!['flip_h', 'flip_v'].every(k => typeof f.place[k] === 'boolean') || !['dx', 'dy'].every(k => Number.isFinite(f.place[k]))) throw Error('Invalid placement values.');
    f.rooms ??= {}; f.nodes ??= {};
    if (!plain(f.rooms) || !plain(f.nodes)) throw Error('Rooms and nodes must be mappings.');
    for (const [id, points] of Object.entries(f.rooms)) if (!id || !Array.isArray(points) || points.length < 3 || !points.every(p => point(p, 2))) throw Error('Room polygons need at least three [x, y] points.');
    for (const [id, p] of Object.entries(f.nodes)) {
      if (!id || nodes.has(id) || !point(p, 3)) throw Error('Nodes need unique ids and finite [x, y, relative_z] points.');
      if (p[2] < 0 || p[2] > f.z[1] - f.z[0]) throw Error('Node height must be inside its floor.');
      nodes.add(id);
    }
    if ('image' in f && (!plain(f.image) || typeof f.image.file !== 'string' || !point(f.image.origin_px, 2) || !Number.isFinite(f.image.px_per_m) || f.image.px_per_m <= 0)) throw Error('Image requires file, origin_px and positive px_per_m.');
  }
  return g;
}
function house(f, p) {
  return [(f.place.flip_h ? f.local.w - p[0] : p[0]) + f.place.dx,
          (f.place.flip_v ? f.local.h - p[1] : p[1]) + f.place.dy];
}
function houseBounds(g) {
  const pts = g.bounds.map(p => [...p]);
  for (const f of g.floors) {
    const local = [[0, 0], [f.local.w, f.local.h], ...Object.values(f.nodes), ...Object.values(f.rooms).flat()];
    pts.push(...local.map(p => house(f, p)));
  }
  return [[0, 1].map(i => clean(Math.min(...pts.map(p => p[i])))),
          [0, 1].map(i => clean(Math.max(...pts.map(p => p[i]))))];
}
function companion(g) {
  const result = {floors: [], nodes: []}, bounds = houseBounds(g);
  const name = id => id.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  for (const f of g.floors) {
    result.floors.push({id: f.id, name: f.name ?? f.id,
      bounds: [[...bounds[0], f.z[0]], [...bounds[1], f.z[1]]],
      rooms: Object.entries(f.rooms).map(([id, pts]) => ({id, name: name(id), points: pts.map(p => house(f, p).map(clean))}))});
    for (const [id, p] of Object.entries(f.nodes)) {
      const node = {id, name: name(id), point: [...house(f, p), f.z[0] + p[2]].map(clean), floors: [f.id]};
      if (Object.hasOwn(f.rooms, id)) node.room = id;
      result.nodes.push(node);
    }
  }
  return result;
}
const yaml = value => jsyaml.dump(value, {noRefs: true, lineWidth: 110, schema: jsyaml.JSON_SCHEMA});
