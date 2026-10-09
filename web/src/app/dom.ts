export function element<T extends Element>(
  root: ParentNode,
  selector: string,
  type: abstract new () => T,
): T {
  const found = root.querySelector(selector);
  if (!(found instanceof type)) {
    throw new Error(`the page has no ${type.name} at ${selector}`);
  }
  return found;
}
