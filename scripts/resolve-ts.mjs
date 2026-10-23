/**
 * Node's type stripper does not add `.ts` the way Vite does.
 * Test scripts import the app graph, which uses extensionless relative paths.
 */
import { register } from 'node:module'

register('./resolve-ts-hooks.mjs', { parentURL: import.meta.url })
