const SUFFIXES = ['.ts', '.tsx', '.mts', '.js', '.mjs', '.json']

function withExtensions(specifier) {
  if (SUFFIXES.some((suffix) => specifier.endsWith(suffix))) return [specifier]
  return [`${specifier}.ts`, `${specifier}.tsx`, `${specifier}/index.ts`, `${specifier}/index.tsx`]
}

export async function resolve(specifier, context, nextResolve) {
  if (!specifier.startsWith('.') && !specifier.startsWith('/')) return nextResolve(specifier, context)
  let lastError
  for (const candidate of withExtensions(specifier)) {
    try {
      return await nextResolve(candidate, context)
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}
