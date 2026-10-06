// Dev tool: screenshot a page with the local Chrome and report console errors / failed requests.
// node scripts/screenshot.mjs --url URL --out PNG [--width 1600] [--height 1000] [--wait 1500] [--full]
//                             [--hover CSS] [--click CSS ...] [--cookie name=value]
import puppeteer from 'puppeteer-core'

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

function parseArgs(argv) {
  const args = { width: 1600, height: 1000, wait: 1500, click: [], full: false, cookie: null }
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i].replace(/^--/, '')
    if (key === 'full') args.full = true
    else if (key === 'click') args.click.push(argv[++i])
    else args[key] = argv[++i]
  }
  if (!args.url || !args.out) throw new Error('usage: --url URL --out PNG')
  return args
}

const args = parseArgs(process.argv.slice(2))
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--hide-scrollbars'] })
const problems = []
try {
  const page = await browser.newPage()
  await page.setViewport({ width: Number(args.width), height: Number(args.height), deviceScaleFactor: 1 })
  page.on('console', (m) => ['error', 'warn'].includes(m.type()) && problems.push(`console.${m.type()}: ${m.text()}`))
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
  if (args.cookie) {
    const [name, ...rest] = args.cookie.split('=')
    await page.setCookie({ name, value: rest.join('='), url: args.url })
  }
  page.on('requestfailed', (r) => !r.url().includes('/api/events') && problems.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`))
  await page.goto(args.url, { waitUntil: 'networkidle2', timeout: 30_000 }).catch(() => {})
  await new Promise((r) => setTimeout(r, Number(args.wait)))
  for (const selector of args.click) {
    await page.click(selector)
    await new Promise((r) => setTimeout(r, 900))
  }
  if (args.hover) {
    await page.hover(args.hover)
    await new Promise((r) => setTimeout(r, 400))
  }
  await page.screenshot({ path: args.out, fullPage: args.full })
  console.log(`saved ${args.out}`)
} finally {
  await browser.close()
}
for (const p of problems) console.log(p)
process.exit(problems.some((p) => p.startsWith('pageerror')) ? 1 : 0)
