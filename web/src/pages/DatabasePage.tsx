import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'

const PG_RUN =
  'docker run -d --name uav-postgres -e POSTGRES_USER=uav -e POSTGRES_PASSWORD=uav -e POSTGRES_DB=uav -p 5433:5432 -v uav-pgdata:/var/lib/postgresql/data postgres:17'
const PG_URL = 'set DATABASE_URL=postgresql+psycopg://uav:uav@127.0.0.1:5433/uav'
const BACKEND = '.venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000'
const NOCO_RUN =
  'docker run -d --name uav-nocodb -p 8082:8080 -e NC_ALLOW_LOCAL_EXTERNAL_DBS=true -v uav-nocodb-data:/usr/app/data nocodb/nocodb:latest'
const NOCO_URL = 'set DATABASE_UI_URL=http://localhost:8082'

/** A command in a box with a Copy button. Clipboard access can be refused: the text stays selectable then. */
function Command({ text }: { text: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'select'>('idle')
  const pre = useRef<HTMLPreElement>(null)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      // The browser refused: select the command so that Ctrl+C copies it.
      const range = document.createRange()
      if (pre.current) range.selectNodeContents(pre.current)
      const selection = window.getSelection()
      selection?.removeAllRanges()
      selection?.addRange(range)
      setState('select')
    }
    window.setTimeout(() => setState('idle'), 2500)
  }
  return (
    <div className="dbhelp-cmd">
      <pre tabIndex={0} ref={pre}>
        {text}
      </pre>
      <button type="button" className="link-button" onClick={copy}>
        {state === 'copied' ? 'Copied' : state === 'select' ? 'Press Ctrl+C' : 'Copy'}
      </button>
      <span className="sr-only" role="status">
        {state === 'copied' ? 'Copied to the clipboard' : state === 'select' ? 'Selected: press Ctrl+C to copy' : ''}
      </span>
    </div>
  )
}

/** How to try PostgreSQL on this PC, for supervisors who have not set it up. Instructions only: nothing here installs
 * or starts anything. */
export function DatabasePage() {
  const { user } = useAuth()
  const [running, setRunning] = useState<string | null>(null)
  useEffect(() => {
    api<{ database?: string }>('/api/health')
      .then((h) => setRunning(h.database ?? null))
      .catch(() => setRunning(null))
  }, [])
  const label = running === 'postgresql' ? 'PostgreSQL' : running === 'sqlite' ? 'SQLite' : null

  return (
    <main className="page dbhelp">
      <h1>Database</h1>

      <p className="dbhelp-now" role="status">
        {label ? (
          <>
            This server is running on <strong>{label}</strong>.
          </>
        ) : (
          'Checking which database this server runs on…'
        )}
      </p>
      <p>
        By default the data is kept in <code>backend\uav.db</code> (SQLite), a file on the PC that runs the backend: no
        account and nothing to install. To try <strong>PostgreSQL</strong> on your own PC, follow the steps below. They
        change nothing in your existing data: SQLite stays as it is, and you can go back to it at any time.
      </p>
      {user?.database_ui_url && (
        <p>
          <a className="button" href={user.database_ui_url} target="_blank" rel="noreferrer">
            Open the database page (new tab)
          </a>
        </p>
      )}

      <section className="card card-pad dbhelp-note" role="note">
        <h2>Before you start</h2>
        <p>
          You need <strong>Docker Desktop</strong> installed and running:{' '}
          <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noreferrer">
            download it here
          </a>
          . Run the commands in a <strong>cmd</strong> window. The first start downloads about 150 MB.
        </p>
      </section>

      <ol className="dbhelp-steps">
        <li className="card card-pad">
          <h2>1. Start PostgreSQL (once)</h2>
          <Command text={PG_RUN} />
          <p className="small">
            Later, after a restart of the PC: <code>docker start uav-postgres</code>
          </p>
        </li>
        <li className="card card-pad">
          <h2>2. Start the backend on it</h2>
          <p>
            Stop the backend (<kbd>Ctrl</kbd>+<kbd>C</kbd> in its window). In a new <strong>cmd</strong> window, go to the
            project's <code>backend</code> folder, then run these two commands, one after the other:
          </p>
          <Command text={PG_URL} />
          <Command text={BACKEND} />
          <p className="small">
            Use <code>127.0.0.1</code>, not <code>localhost</code>: on some PCs <code>localhost</code> makes the
            connection hang.
          </p>
        </li>
        <li className="card card-pad">
          <h2>3. Check that it works</h2>
          <p>
            Reload this page: the line at the top should say <strong>PostgreSQL</strong>. The tables are created and
            the demo accounts added on the first start; the database starts empty, and your old missions stay in
            SQLite.
          </p>
        </li>
        <li className="card card-pad">
          <h2>4. Optional: look at the tables in the browser</h2>
          <p>Start NocoDB, a web tool for browsing a database like a spreadsheet:</p>
          <Command text={NOCO_RUN} />
          <p>
            Open <code>http://localhost:8082</code> and register a local account (it stays on your PC). Choose{' '}
            <strong>Create base</strong>, then <strong>Connect to external database</strong>, <strong>PostgreSQL</strong>,
            and fill in: host <code>host.docker.internal</code>, port <code>5433</code>, user <code>uav</code>, database{' '}
            <code>uav</code>, and the password from the command in step 1 (the word after{' '}
            <code>POSTGRES_PASSWORD=</code>). Press <strong>Test</strong>, then <strong>Create</strong>.
          </p>
          <p>
            To make the <strong>Database</strong> link in the menu open it, run this before starting the backend in step
            2:
          </p>
          <Command text={NOCO_URL} />
        </li>
      </ol>

      <section className="card card-pad dbhelp-note" role="note">
        <h2>Going back to SQLite</h2>
        <p>
          Stop the backend (<kbd>Ctrl</kbd>+<kbd>C</kbd>) and start it in a new <strong>cmd</strong> window{' '}
          <em>without</em> the <code>set DATABASE_URL</code> command. Nothing is lost on either side.
        </p>
        <h2>Good to know</h2>
        <ul>
          <li>The password in these commands is for a trial on your own PC only; do not use it on a shared server.</li>
          <li>
            The <code>users</code> table holds the accounts' password hashes: do not show it to others, and do not edit
            tables while a mission is flying.
          </li>
          <li>
            These are instructions only: nothing on this page installs or starts anything, and it cannot check that
            Docker or PostgreSQL are installed on your PC.
          </li>
        </ul>
      </section>
    </main>
  )
}
