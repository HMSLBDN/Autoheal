import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — Routes, Navigation & Layout Responsiveness', () => {
  const rootDir = process.cwd()

  it('dashboard-view.tsx correctly maps URL slugs to respective view pages', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('<OverviewView'), 'Must render OverviewView')
    assert(dashboardViewCode.includes('page === \'services\''), 'Must handle services page')
    assert(dashboardViewCode.includes('page === \'incidents\''), 'Must handle incidents page')
    assert(dashboardViewCode.includes('page === \'recovery\' || page === \'recoveries\''), 'Must handle recoveries approval queue')
    assert(dashboardViewCode.includes('page === \'history\''), 'Must handle recovery history')
    assert(dashboardViewCode.includes('page === \'analytics\''), 'Must handle analytics page')
    assert(dashboardViewCode.includes('page === \'reports\''), 'Must handle reports page')
    assert(dashboardViewCode.includes('page === \'monitoring\''), 'Must handle monitoring page')
    assert(dashboardViewCode.includes('page === \'intelligence\''), 'Must handle intelligence page')
    assert(dashboardViewCode.includes('page === \'settings\''), 'Must handle settings page')
  })

  it('app directory has matching Next.js App Router routes', () => {
    assert(fs.existsSync(path.join(rootDir, 'app/page.tsx')), 'Home route must exist')
    assert(fs.existsSync(path.join(rootDir, 'app/login/page.tsx')), 'Login route must exist')
    assert(fs.existsSync(path.join(rootDir, 'app/register/page.tsx')), 'Register route must exist')
    assert(fs.existsSync(path.join(rootDir, 'app/dashboard/[[...slug]]/page.tsx')), 'Dashboard catch-all route must exist')
  })

  it('globals.css includes responsive breakpoints for desktop, tablet, and mobile layouts', () => {
    const globalsCss = fs.readFileSync(path.join(rootDir, 'app/globals.css'), 'utf8')
    assert(globalsCss.includes('@media (max-width: 1200px)'), 'Desktop-to-tablet breakpoint (1200px) must exist')
    assert(globalsCss.includes('@media (max-width: 900px)'), 'Tablet breakpoint (900px) must exist')
    assert(globalsCss.includes('@media (max-width: 760px)'), 'Small tablet / landscape mobile (760px) must exist')
    assert(globalsCss.includes('@media (max-width: 500px)'), 'Mobile portrait breakpoint (500px) must exist')
    assert(globalsCss.includes('@media (max-width: 420px)'), 'Narrow mobile breakpoint (420px) must exist')
  })
})
