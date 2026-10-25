/**
 * A choropleth drawn as plain SVG from a prebuilt file of projected paths (tools/build_shapes.py).
 * Shapes are keyed by an id (state "sp", municipality TSE code); fill and tooltip come from callbacks.
 */
export class ChoroplethMap {
  constructor({ svg, tooltip }, describe) {
    this.svg = svg;
    this.tooltip = tooltip;
    this.describe = describe; // id -> tooltip HTML, or '' for none
    this.shapes = new Map();
    for (const type of ['mousemove', 'click']) svg.addEventListener(type, event => this.#showTooltip(event));
    svg.addEventListener('mouseleave', () => (tooltip.hidden = true));
  }

  async load(url, { idOf, labelOf = () => '' }) {
    const { viewBox, shapes } = await (await fetch(url)).json();
    this.fullView = viewBox.join(' ');
    this.svg.setAttribute('viewBox', this.fullView);
    this.svg.innerHTML =
      shapes.map(s => `<path data-id="${idOf(s)}" d="${s.d}"/>`).join('') +
      shapes.filter(labelOf).map(s => `<text x="${s.label[0]}" y="${s.label[1]}">${labelOf(s)}</text>`).join('');
    for (const path of this.svg.querySelectorAll('path')) this.shapes.set(path.dataset.id, path);
    return shapes;
  }

  paint(fillOf) {
    for (const [id, path] of this.shapes) path.style.fill = fillOf(id);
  }

  /** Frames one bounding box [x0, y0, x1, y1] with a margin, or the whole country with none. */
  zoom(box) {
    if (!box) return this.svg.setAttribute('viewBox', this.fullView);
    const [x0, y0, x1, y1] = box;
    const pad = Math.max(x1 - x0, y1 - y0) * 0.05;
    this.svg.setAttribute('viewBox', `${x0 - pad} ${y0 - pad} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad}`);
  }

  #showTooltip(event) {
    const html = event.target.dataset?.id ? this.describe(event.target.dataset.id) : '';
    this.tooltip.hidden = !html;
    if (!html) return;
    this.tooltip.innerHTML = html;
    const { offsetWidth: width, offsetHeight: height } = this.tooltip;
    this.tooltip.style.left = `${Math.min(event.clientX + 14, innerWidth - width - 8)}px`;
    this.tooltip.style.top = `${Math.min(event.clientY + 14, innerHeight - height - 8)}px`;
  }
}
