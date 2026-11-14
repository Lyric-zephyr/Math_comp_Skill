import { useEffect, useRef, useState } from 'react'
import { ArrowRight, BookOpen, Check, CheckCircle2, ChevronDown, Circle, FileText, FolderOpen, Gauge, GraduationCap, LoaderCircle, Play, Settings2, ShieldCheck, Sparkles, Wrench, XCircle } from 'lucide-react'
import { Button } from './components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from './components/ui/sheet'
import { api, terminal, type Job, type Options, type Settings } from './api'

const storageKey = 'math-comp-settings-v1'
const names: Record<string, string> = { waiting: '等待中', running: '进行中', succeeded: '已完成', partial: '部分完成', failed: '失败' }
const formats: Record<string, string> = { pdf: 'PDF 文档', word: 'Word 文档', md: 'Markdown', html: 'HTML 网页' }
function restore(defaults: Settings): Settings {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '{}')
    return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, typeof saved[key] === 'string' ? saved[key] : value])) as Settings
  } catch { return defaults }
}
export default function App() {
  const [options, setOptions] = useState<Options | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const [openedPath, setOpenedPath] = useState('')
  const [pending, setPending] = useState(false)
  const [key, setKey] = useState('')
  const [configured, setConfigured] = useState<Record<string, boolean>>({})
  const [models, setModels] = useState<string[]>([])
  const [reading, setReading] = useState(false)
  const [logsOpen, setLogsOpen] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [connection, setConnection] = useState('')
  const [answering, setAnswering] = useState(false)
  const requestVersion = useRef(0)
  const modelMemory = useRef<Record<string, string>>({})
  const modeMemory = useRef<Record<string, string>>({})
  const chapterMemory = useRef<Record<string, string>>({})
  const logEnd = useRef<HTMLDivElement>(null)
  useEffect(() => {
    history.replaceState(null, '', '/')
    let mounted = true
    Promise.all([api<Options>('options'), api<Job | null>('jobs/current')]).then(([o, j]) => {
      if (!mounted) return
      const s = restore(o.defaults)
      if (!o.subjects.includes(s.subject)) s.subject = o.defaults.subject
      if (!o.providers[s.ai]) s.ai = o.defaults.ai
      if (!o.providers[s.ai].includes(s.run_mode)) s.run_mode = o.providers[s.ai][0]
      if (![...o.subject_modules[s.subject], 'all'].includes(s.chapter)) s.chapter = o.subject_modules[s.subject][0]
      if (!formats[s.output_format]) s.output_format = 'pdf'
      if (!['browser', 'latex'].includes(s.pdf_engine)) s.pdf_engine = 'browser'
      if (!['总结知识点', '练习'].includes(s.mode)) s.mode = '总结知识点'
      try {
        const memory = JSON.parse(localStorage.getItem('math-comp-models-v1') || '{}')
        if (memory && typeof memory === 'object') modelMemory.current = Object.fromEntries(Object.entries(memory).filter(([,v]) => typeof v === 'string')) as Record<string, string>
        const modes = JSON.parse(localStorage.getItem('math-comp-modes-v1') || '{}')
        if (modes && typeof modes === 'object') modeMemory.current = Object.fromEntries(Object.entries(modes).filter(([,v]) => typeof v === 'string')) as Record<string, string>
      } catch { /* Invalid saved preferences are discarded. */ }
      try {
        const chapters = JSON.parse(localStorage.getItem('course-skill-chapters-v1') || '{}')
        if (chapters && typeof chapters === 'object') chapterMemory.current = Object.fromEntries(Object.entries(chapters).filter(([,v]) => typeof v === 'string')) as Record<string, string>
      } catch { /* Ignore invalid saved module preferences. */ }
      setOptions(o); setSettings(s); setConfigured(o.configured); setJob(j)
    }).catch(e => mounted && setError(e.message))
    return () => { mounted = false }
  }, [])
  useEffect(() => { if (settings) { try { localStorage.setItem(storageKey, JSON.stringify(settings)) } catch { /* Storage may be disabled. */ } } }, [settings])
  useEffect(() => {
    if (!job || terminal(job)) return
    const source = new EventSource(`/api/jobs/${job.id}/events`)
    let refreshRunning = false
    const refresh = async () => {
      if (refreshRunning) return
      refreshRunning = true
      try { const next = await api<Job>(`jobs/${job.id}`); setJob(next); if (terminal(next)) source.close() }
      catch { setConnection('连接暂时中断，正在恢复…') }
      finally { refreshRunning = false }
    }
    const snapshot = (event: MessageEvent) => { const next = JSON.parse(event.data) as Job; setJob(next); setConnection(''); if (terminal(next)) source.close() }
    source.addEventListener('snapshot', snapshot)
    for (const kind of ['progress', 'module', 'artifact', 'log', 'ask', 'finished']) source.addEventListener(kind, refresh)
    source.onopen = () => { setConnection(''); void refresh() }
    source.onerror = () => { setConnection('连接暂时中断，正在恢复…'); void refresh() }
    const poll = window.setInterval(refresh, 3000)
    return () => { source.close(); clearInterval(poll) }
  }, [job?.id, job?.status])
  useEffect(() => {
    if (job?.status === 'failed' || job?.status === 'partial' || job?.logs.some(line => line.includes('[ERR]') || line.includes('[-]'))) setLogsOpen(true)
  }, [job?.status, job?.logs])
  useEffect(() => { if (logsOpen) logEnd.current?.scrollIntoView({ block: 'nearest' }) }, [job?.logs.length, logsOpen])
  const busy = pending || !terminal(job)
  const update = (patch: Partial<Settings>) => setSettings(s => s && ({ ...s, ...patch }))
  const changeSubject = (subject: string) => {
    if (!settings || !options) return
    chapterMemory.current[settings.subject] = settings.chapter
    try { localStorage.setItem('course-skill-chapters-v1', JSON.stringify(chapterMemory.current)) } catch { /* Preferences remain in memory. */ }
    const remembered = chapterMemory.current[subject]
    const chapter = [...options.subject_modules[subject], 'all'].includes(remembered) ? remembered : options.subject_modules[subject][0]
    update({ subject, chapter })
  }
  const saveKey = async () => {
    if (!settings || !key) return
    await api('session/settings', { ...settings, api_key: key }, 'PUT')
    setConfigured(c => ({ ...c, [settings.ai]: true })); setKey(current => current === key ? '' : current)
  }
  const changeContext = async (ai: string, run_mode?: string) => {
    if (!settings || !options) return
    try { await saveKey() } catch (e) { setError((e as Error).message); return }
    requestVersion.current++; setReading(false); setModels([])
    modelMemory.current[`${settings.ai}:${settings.run_mode}`] = settings.model
    modeMemory.current[settings.ai] = settings.run_mode
    const available = options.providers[ai]
    const remembered = modeMemory.current[ai]
    const mode = run_mode || (available.includes(remembered) ? remembered : available.includes('CLI') ? 'CLI' : available[0])
    const model = modelMemory.current[`${ai}:${mode}`] ?? (mode === 'API' ? options.api_defaults[ai] : options.cli_models[0])
    try { localStorage.setItem('math-comp-models-v1', JSON.stringify(modelMemory.current)); localStorage.setItem('math-comp-modes-v1', JSON.stringify(modeMemory.current)) } catch { /* Preferences remain in memory. */ }
    update({ ai, run_mode: mode, model }); setKey(current => current === key ? '' : current)
  }
  const submit = async (kind: string) => {
    if (!settings) return
    setPending(true); setError('')
    try {
      await saveKey()
      const next = await api<Job>('jobs', { kind, settings })
      setLogsOpen(false); setJob(next)
    } catch (e) {
      setError((e as Error).message)
      try { setJob(await api<Job | null>('jobs/current')) } catch { /* Preserve the last known state. */ }
    } finally { setPending(false) }
  }
  const readModels = async () => {
    if (!settings) return
    const version = ++requestVersion.current
    setReading(true); setError('')
    try {
      await saveKey()
      const result = await api<{models: string[]}>('models', settings)
      if (version === requestVersion.current) setModels(result.models)
    } catch (e) { if (version === requestVersion.current) setError(`${(e as Error).message}；仍可手动输入模型 ID。`) }
    finally { if (version === requestVersion.current) setReading(false) }
  }
  const answer = async (keep: boolean) => {
    if (!job) return
    setAnswering(true); setError('')
    try { setJob(await api<Job>(`jobs/${job.id}/answer`, { keep })) }
    catch (e) { setError((e as Error).message) }
    finally { setAnswering(false) }
  }
  const open = async (path: string, body = {}) => {
    setError(''); setOpenedPath('')
    try { const result = await api<{path: string}>(path, body); setOpenedPath(result.path) }
    catch (e) { setError((e as Error).message) }
  }
  if (!settings || !options) return <main className="mx-auto max-w-3xl p-12"><h1 className="text-2xl font-semibold">Course_Skill 课程复习工作台</h1><p className="mt-6" role="status">{error || '正在连接本机服务…'}</p></main>
  const practice = settings.mode === '练习'
  const competition = settings.subject === options.defaults.subject
  const modules = options.subject_modules[settings.subject]
  const batchCount = options.batch_counts[settings.subject][settings.mode]
  return <div className="min-h-screen">
    <header className="border-b border-slate-200/80 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-5">
        <div className="flex min-w-0 items-center gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white"><GraduationCap size={23}/></span><div><div className="font-semibold tracking-tight">课程复习<span className="ml-2 font-normal text-slate-400">/ 学习工作台</span></div><div className="mt-0.5 text-[12px] tracking-widest text-slate-400">Course_Skill</div></div></div>
        <span className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-500 sm:flex"><span className="size-1.5 rounded-full bg-emerald-500"/>本机运行</span>
      </div>
    </header>
    <main className="mx-auto max-w-6xl px-5 py-9 sm:px-6">
      <div className="mb-7"><div className="eyebrow mb-2">YOUR STUDY SPACE</div><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">让备考，从容一点</h1></div>
      {error && <div role="alert" className="mb-5 flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800"><span>{error}</span><button aria-label="关闭提示" className="shrink-0 underline" onClick={() => setError('')}>关闭</button></div>}
      <div className="grid items-stretch gap-6 lg:grid-cols-2">
        <section className="card flex min-w-0 flex-col p-6 sm:p-7" aria-labelledby="task-title">
          <div className="mb-6 flex items-center gap-2"><BookOpen size={22} className="text-blue-600"/><h2 id="task-title" className="text-xl font-semibold sm:text-2xl">创建学习内容</h2><span className="ml-auto text-xs text-slate-400">01</span></div>
          <div className="mb-6"><label htmlFor="subject">科目</label><select id="subject" value={settings.subject} disabled={busy} onChange={e => changeSubject(e.target.value)}>{options.subjects.map(subject => <option key={subject}>{subject}</option>)}</select></div>
          <fieldset className="mb-6"><legend>学习任务</legend><div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">{['总结知识点', '练习'].map((mode, i) => <button key={mode} type="button" aria-pressed={settings.mode === mode} onClick={() => update({ mode })} className={`flex h-9 items-center justify-center gap-2 rounded-lg px-2 text-base transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 ${settings.mode === mode ? 'bg-white font-semibold text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}>{i ? <FileText size={16}/> : <Sparkles size={16}/ >}{i ? '题目练习' : '知识点总结'}</button>)}</div></fieldset>
          <div className="mb-6"><label htmlFor="chapter">学习模块</label><select id="chapter" disabled={busy} value={settings.chapter} onChange={e => update({ chapter: e.target.value })}>{modules.map(module => <option key={module}>{module}</option>)}<option value="all">全部模块（一键生成 {batchCount} 份）</option></select></div>
          <div className="mb-6"><label htmlFor="format">输出格式</label><select id="format" value={settings.output_format} onChange={e => update({ output_format: e.target.value })}>{Object.entries(formats).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select>{settings.output_format === 'pdf' && <div className="mt-4"><label htmlFor="engine">PDF 排版引擎</label><select id="engine" value={settings.pdf_engine} onChange={e => update({ pdf_engine: e.target.value })}><option value="browser">浏览器（推荐）</option><option value="latex">LaTeX（专业排版）</option></select></div>}</div>
          <Sheet open={sheetOpen} onOpenChange={next => { if (!next) void saveKey().catch(e => setError(e.message)); setSheetOpen(next) }}>
            <div className="mb-6 flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50/70 p-3.5"><div className="min-w-0"><div className="field-label">当前 AI 服务</div><div className="mt-1 text-sm font-medium">{settings.ai} <span className="font-normal text-slate-400">· {settings.run_mode}</span></div><p className="mt-1 truncate text-xs text-slate-500">{settings.run_mode === 'GUI' ? '在登录网页中选择模型' : settings.model || '请先设置模型 ID'}</p></div><SheetTrigger asChild><Button variant="ghost" size="sm"><Settings2/>设置</Button></SheetTrigger></div>
            <SheetContent><SheetTitle className="pr-10 text-xl font-semibold">AI 服务设置</SheetTitle><SheetDescription className="mt-2 mb-8 text-sm leading-6 text-slate-500">选择生成方式。修改设置仅影响下一次任务。</SheetDescription>
              <div className="space-y-6"><div><label htmlFor="ai">AI 服务</label><select id="ai" value={settings.ai} onChange={e => void changeContext(e.target.value)}>{Object.keys(options.providers).map(ai => <option key={ai}>{ai}</option>)}</select></div>
                <div><label htmlFor="run-mode">运行方式</label><select id="run-mode" value={settings.run_mode} onChange={e => void changeContext(settings.ai, e.target.value)}>{options.providers[settings.ai].map(mode => <option key={mode}>{mode}</option>)}</select></div>
                {settings.run_mode === 'API' && <><div><label htmlFor="api-key">API 密钥 {configured[settings.ai] && <span className="ml-2 font-normal text-emerald-600">已配置</span>}</label><input id="api-key" type="password" autoComplete="off" value={key} placeholder={configured[settings.ai] ? '输入新密钥以替换' : '粘贴服务商 API 密钥'} onChange={e => setKey(e.target.value)}/><p className="hint mt-2">仅保留在本机服务内存，重启服务后需重新输入。</p></div><div><label htmlFor="model">{settings.ai === '豆包' ? '模型 / 推理接入点 ID' : 'API 模型 ID'}</label><input id="model" list="model-options" value={settings.model} onChange={e => update({ model: e.target.value })} placeholder="选择或手动输入模型 ID"/><datalist id="model-options">{models.map(model => <option key={model} value={model}/>)}</datalist><Button variant="outline" className="mt-3" onClick={() => void readModels()} disabled={reading}>{reading && <LoaderCircle className="animate-spin"/>}{reading ? '读取中…' : '读取模型'}</Button><p className="hint mt-2">查询失败时可直接填写模型 ID；密钥本身不指定模型。</p></div></>}
                {settings.run_mode === 'CLI' && <div><label htmlFor="cli-model">CLI 模型</label><select id="cli-model" value={settings.model} onChange={e => update({ model: e.target.value })}>{Array.from(new Set([...options.cli_models, settings.model])).map(model => <option key={model}>{model}</option>)}</select><p className="hint mt-2">首次使用请配置环境，并在终端完成 codex login。</p></div>}
                {settings.run_mode === 'GUI' && <p className="rounded-xl bg-blue-50 p-4 text-sm leading-7 text-blue-800">生成时会打开独立 ChatGPT 浏览器。请在该窗口登录、完成验证并选择模型。任务结束后窗口会保留。</p>}
                {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
                <Button className="w-full" onClick={async () => { try { await saveKey(); setSheetOpen(false) } catch (e) { setError((e as Error).message) } }}><Check/>完成设置</Button>
              </div>
            </SheetContent>
          </Sheet>
          <div className="mt-auto">
            <Button variant="outline" className="mb-2 w-full" disabled={busy} onClick={() => void submit('setup')}><Wrench/>一键配置环境</Button>
            <Button className="h-12 w-full text-base" disabled={busy} onClick={() => void submit('generate')}>{busy ? <LoaderCircle className="animate-spin"/> : <Play/>}{busy ? '任务执行中' : '开始生成'}{!busy && <ArrowRight className="ml-auto"/>}</Button>
            <p className="hint mt-2 text-center">首次使用：点击“一键配置环境”，即可安装并检查所需工具。</p>
          </div>
        </section>
        <div className="flex min-w-0 flex-col gap-5">
          <section className="card flex min-w-0 flex-1 flex-col p-6 sm:p-7" aria-labelledby="progress-title">
            <div className="flex items-center justify-between gap-3"><h2 id="progress-title" className="flex items-center gap-2 text-xl font-semibold sm:text-2xl"><Gauge size={22} className="shrink-0 text-blue-600" aria-hidden="true"/>任务进度</h2><span className={`rounded-full px-2.5 py-1 text-xs ${job?.status === 'failed' || job?.status === 'partial' ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>{job ? names[job.status] : '准备就绪'}</span></div>
            {!job ? <div className="flex min-h-64 flex-1 flex-col items-center justify-center px-4 text-center"><div className="mb-5 flex size-16 items-center justify-center rounded-2xl border border-blue-100 bg-blue-50 text-blue-500"><BookOpen size={27} strokeWidth={1.5}/></div><h3 className="font-medium text-slate-700">为下一次进步，做好准备</h3><p className="mt-2 text-sm leading-6 text-slate-400">选择左侧任务后开始生成，<br/>进度和学习文件会显示在这里。</p></div> : <div className="mt-7"><div className="mb-3 flex items-center justify-between gap-3"><p className="text-sm text-slate-600" role="status">{job.stage}</p><span className="text-xl font-semibold tabular-nums text-blue-600">{Math.round(job.percent)}<span className="ml-0.5 text-sm">%</span></span></div><div role="progressbar" aria-label="整体进度" aria-valuenow={job.percent} aria-valuemin={0} aria-valuemax={100} className="h-2 overflow-hidden rounded-full bg-slate-100"><div style={{ width: `${job.percent}%` }} className="h-full rounded-full bg-blue-600 transition-[width]"/></div><p className="hint mt-3">阶段进度会在实际步骤完成后更新；刷新或关闭网页不影响执行。</p>
              <div className="mt-5 space-y-3">{Object.entries(job.modules).map(([chapter, status]) => <div key={chapter} className="flex items-start gap-2 text-sm">{status === 'succeeded' ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-600"/> : status === 'failed' ? <XCircle size={17} className="mt-0.5 shrink-0 text-red-500"/> : status === 'running' ? <LoaderCircle size={17} className="mt-0.5 shrink-0 animate-spin text-blue-600"/> : <Circle size={17} className="mt-0.5 shrink-0 text-slate-300"/>}<span className="min-w-0 flex-1 text-slate-600">{chapter}</span><span className="shrink-0 text-xs leading-5 text-slate-400">{names[status]}</span></div>)}</div>
              {job.question && <div role="alertdialog" aria-labelledby="ask-title" aria-describedby="ask-body" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
                <p id="ask-title" className="font-medium text-amber-800">发现重复题</p>
                <p id="ask-body" className="mt-1 leading-6 text-amber-800">{job.question.chapter} 重试三轮后仍有 {job.question.count} 道题与历史题目重复或高度相似。要保留这份练习吗？</p>
                <div className="mt-3 flex gap-2"><Button size="sm" disabled={answering} className="bg-emerald-600 hover:bg-emerald-700" onClick={() => void answer(true)}>保留</Button><Button size="sm" disabled={answering} className="bg-red-600 hover:bg-red-700" onClick={() => void answer(false)}>放弃</Button></div>
              </div>}
              {terminal(job) && <div className="mt-5 border-t border-slate-100 pt-4 text-sm text-slate-500">成功 <strong className="font-medium text-emerald-600">{job.successes}</strong> 项<span className="mx-3 text-slate-200">/</span>失败 <strong className={job.failures ? 'font-medium text-red-600' : 'font-medium'}>{job.failures}</strong> 项</div>}
            </div>}
            {connection && <p role="status" className="hint mt-3 text-amber-700">{connection}</p>}
            {!!job?.artifacts.length && <div className="mt-5 space-y-3 border-t border-slate-100 pt-5"><h3 className="text-xs font-semibold text-slate-500">学习文件</h3>{job.artifacts.map(file => <div key={file.id} className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5"><div className="flex items-start gap-2"><FileText size={18} className="mt-0.5 shrink-0 text-blue-500"/><div className="min-w-0"><p className="break-all text-sm font-medium">{file.name}</p>{file.kind === 'recovery' && <p className="mt-1 text-xs text-amber-700">导出未完成，原始 Markdown 已保留</p>}{file.usage && <p className="mt-1 text-xs text-violet-600">API 用量：输入 {file.usage.input.toLocaleString()} · 输出 {file.usage.output.toLocaleString()} tokens（{file.usage.calls} 次调用）</p>}</div></div><div className="mt-3 flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => void open(`artifacts/${file.id}/open`)}>打开文件</Button><Button variant="ghost" size="sm" onClick={() => void open(`artifacts/${file.id}/open`, { folder: true })}><FolderOpen/>所在文件夹</Button></div></div>)}</div>}
            {job && <details open={logsOpen} onToggle={event => setLogsOpen(event.currentTarget.open)} className="mt-5 border-t border-slate-100 pt-4"><summary className="flex list-none items-center justify-between text-xs font-medium text-slate-500">详细日志<span className="flex items-center gap-2">{job.logs.length} 条<ChevronDown size={14}/></span></summary><div className="mt-3 max-h-64 overflow-auto px-1 py-2 font-mono text-xs leading-6 text-emerald-700" tabIndex={0} aria-label="任务日志">{job.logs.map((line, i) => <div key={i} className={`whitespace-pre-wrap break-all ${line.includes('[ERR]') || line.includes('[-]') ? 'text-red-600' : line.includes('[WARN]') || line.includes('[!]') ? 'text-amber-700' : ''}`}>{line}</div>)}<div ref={logEnd}/></div></details>}
          </section>
          <section className="card p-5"><h2 className="mb-3 text-xs font-semibold text-slate-500">文件与参考资料</h2><div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => void open('resources/textbook/open')}><FolderOpen/>教材文件夹</Button><Button variant="outline" size="sm" onClick={() => void open('resources/output/open')}><FolderOpen/>输出文件夹</Button></div><p className="hint mt-3">{practice ? (competition ? '优先改编 Assistant_course 对应习题库，缺少资料再读取真题与开放参考。' : '优先改编 Assistant_course 复变习题，缺少资料时参考 MIT OCW。') : '优先读取用户 PDF，再参考 Assistant_course 对应课程库，不足部分由 AI 知识补齐。'}</p><div className="mt-4 flex items-start gap-2 border-t border-slate-100 pt-4 text-xs leading-6 text-slate-400"><ShieldCheck size={15} className="mt-1 shrink-0"/><p>文件和教材保存在本机。生成时相关内容会发送至所选 AI 服务；AI 生成的数学内容请复核后使用。</p></div></section>
        </div>
      </div>
      {openedPath && <p role="status" className="mt-4 break-all rounded-xl bg-blue-50 p-4 text-sm text-blue-800">已请求系统打开：{openedPath}。请查看文件管理器或对应应用窗口。</p>}
      <footer className="mt-10 border-t border-slate-200/70 pt-5 text-xs text-slate-400">Course_Skill <span className="mx-2 text-slate-300">·</span> 专注每一步理解</footer>
    </main>
  </div>
}
