import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// @fontsource ships every face twice: .woff2 and a .woff fallback. Both get bundled because the
// stylesheet names both, which is ~13 MB of the build for nothing - woff2 has been supported by
// every browser that can run this app for a decade. Dropping the fallback URL before Vite resolves
// it means those files are never emitted. Same glyphs, half the size.
let stripped = 0
const woff2Only = {
  name: 'fontsource-woff2-only',
  enforce: 'pre',
  transform(code, id) {
    if (!id.includes('@fontsource') || !id.split('?')[0].endsWith('.css')) return null
    // The quotes around the url are optional, so that a future @fontsource release that adds them
    // does not quietly stop matching and put 15 MB of fallbacks back into the build.
    const out = code.replace(/,\s*url\((['"]?)[^)'"]*\.woff\1\)\s*format\((['"])woff\2\)/g, () => {
      stripped += 1
      return ''
    })
    return out === code ? null : out
  },
  buildEnd() {
    if (stripped === 0) {
      this.warn('fontsource-woff2-only stripped nothing - the .woff fallbacks are still in the build. '
        + 'Check whether @fontsource changed how it writes its src: url() list.')
    }
  },
}

export default defineConfig({
  plugins: [woff2Only, react()],
  server: {
    port: 5173,
    // Proxy all /api calls to Flask running on port 5000
    proxy: {
      '/api': 'http://127.0.0.1:5000',
    },
  },
})
