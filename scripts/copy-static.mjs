import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const rootDir = resolve(__dirname, '..')

const sourceDir = resolve(rootDir, 'frontend', '.output', 'public')
const targetDir = resolve(rootDir, 'backend', 'static')

if (!existsSync(sourceDir)) {
  throw new Error(`Nuxt static output not found at ${sourceDir}. Run \"npm run generate\" in frontend/ first.`)
}

rmSync(targetDir, { recursive: true, force: true })
mkdirSync(targetDir, { recursive: true })
cpSync(sourceDir, targetDir, { recursive: true })

console.log(`Copied static frontend from ${sourceDir} to ${targetDir}`)
