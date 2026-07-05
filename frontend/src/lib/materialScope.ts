import type { Material } from "@/types";

interface ReadyMaterialScopeInput {
  materials: Material[];
  currentScope: string[];
  previousReadyNames: Set<string> | null;
}

export function getNextReadyMaterialScope({
  materials,
  currentScope,
  previousReadyNames,
}: ReadyMaterialScopeInput) {
  const readyNames = materials
    .filter((material) => material.processing_status === "ready")
    .map((material) => material.original_filename);
  const readyNameSet = new Set(readyNames);
  const validScope = currentScope.filter((filename) =>
    readyNameSet.has(filename),
  );
  let nextScope = validScope;

  if (previousReadyNames === null) {
    if (validScope.length === 0 && readyNames.length === 1) {
      nextScope = [readyNames[0]];
    }
  } else {
    const newlyReadyNames = readyNames.filter(
      (filename) => !previousReadyNames.has(filename),
    );
    if (newlyReadyNames.length > 0) {
      nextScope = [
        ...nextScope,
        ...newlyReadyNames.filter((filename) => !nextScope.includes(filename)),
      ];
    }
  }

  return { nextScope, readyNames: readyNameSet };
}

export function sameStringList(left: string[], right: string[]) {
  return (
    left.length === right.length &&
    left.every((item, index) => item === right[index])
  );
}
