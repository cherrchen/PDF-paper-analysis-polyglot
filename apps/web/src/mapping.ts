/** Mapping helpers for the M2 source/target PDF viewer. */

export type Rect = { kind: "rect"; x: number; y: number; width: number; height: number };
export type Fragment = { pageIndex: number; geometry: Rect };
export type SourceFragment = { fragmentType: "layoutRegion"; layoutRegionId: string };
export type SourceRegion = Fragment & { id: string };
export type MappingBundle = {
  viewerDataVersion: number;
  sourceSemanticBindings: { semanticNodeId: string; sourceAnchorIds: string[] }[];
  sourceAnchors: { id: string; fragments: SourceFragment[] }[];
  semanticNodes: { id: string; kind: string }[];
  sourceRegions: SourceRegion[];
  renderAnchors: { id: string; semanticNodeId: string; fragments: Fragment[] }[];
};
export type Pair = { sources: Fragment[]; target: Fragment };

export function buildPairs(mappings: MappingBundle): Map<string, Pair> {
  if (mappings.viewerDataVersion !== 1) {
    throw new Error(`unsupported viewer data version: ${mappings.viewerDataVersion}`);
  }
  const sourceRegionById = new Map(mappings.sourceRegions.map((region) => [region.id, region]));
  const sourceAnchorById = new Map(mappings.sourceAnchors.map((anchor) => [anchor.id, anchor]));
  const targetByNodeId = new Map(
    mappings.renderAnchors.map((anchor) => [anchor.semanticNodeId, anchor.fragments[0]]),
  );
  const pairs = new Map<string, Pair>();
  for (const binding of mappings.sourceSemanticBindings) {
    const sources: Fragment[] = [];
    for (const anchorId of binding.sourceAnchorIds) {
      const anchor = sourceAnchorById.get(anchorId);
      if (!anchor) continue;
      for (const fragment of anchor.fragments) {
        const region = sourceRegionById.get(fragment.layoutRegionId);
        if (region) sources.push(region);
      }
    }
    const target = targetByNodeId.get(binding.semanticNodeId);
    if (sources.length > 0 && target) {
      pairs.set(binding.semanticNodeId, { sources, target });
    }
  }
  return pairs;
}

export function fragmentsForSide(pair: Pair, side: "source" | "target"): Fragment[] {
  return side === "source" ? pair.sources : [pair.target];
}
