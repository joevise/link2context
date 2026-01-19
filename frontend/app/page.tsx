'use client'

import { useState, useMemo, useCallback } from 'react'
import { Link, Loader2, Copy, Download, Check, Github, Sparkles, FileText, FileImage, Settings, Wand2, X, CheckCircle2, Globe, Package, FileArchive, Layers } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const loadingStages = [
  'Fetching page...',
  'Downloading images...',
  'Detecting videos...',
  'Formatting Markdown...',
]

interface MediaInfo {
  images: Record<string, string>
  videos: Array<{ url: string; thumbnail?: string }>
}

interface ConvertResult {
  status: string
  title?: string
  markdown?: string
  markdown_with_images?: string
  strategy_used?: string
  media?: MediaInfo
  error?: string
}

interface AIConfig {
  provider: string
  base_url: string
  api_key: string
  model: string
  prompt: string
}

interface PageInfo {
  url: string
  title: string
}

interface CrawledPage {
  url: string
  title: string
  filename: string
  success: boolean
  error?: string
}

const DEFAULT_OCR_CONFIG: AIConfig = {
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o',
  prompt: '请识别这张图片中的所有文字内容。保持原有的格式和结构，用Markdown格式输出。'
}

const DEFAULT_ANALYZER_CONFIG: AIConfig = {
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o-mini',
  prompt: '分析这个网页的HTML，找出导航栏/侧边栏中所有的文档链接，返回JSON格式。'
}

export default function Home() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStage, setLoadingStage] = useState(0)
  const [result, setResult] = useState<ConvertResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [showPreview, setShowPreview] = useState(true)
  
  // OCR states
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set())
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrResults, setOcrResults] = useState<Record<string, string>>({})
  
  // Settings
  const [showSettings, setShowSettings] = useState(false)
  const [ocrConfig, setOcrConfig] = useState<AIConfig>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('ocrConfig')
      if (saved) try { return { ...DEFAULT_OCR_CONFIG, ...JSON.parse(saved) } } catch {}
    }
    return DEFAULT_OCR_CONFIG
  })
  const [analyzerConfig, setAnalyzerConfig] = useState<AIConfig>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('analyzerConfig')
      if (saved) try { return { ...DEFAULT_ANALYZER_CONFIG, ...JSON.parse(saved) } } catch {}
    }
    return DEFAULT_ANALYZER_CONFIG
  })
  
  // Site crawl states
  const [siteMode, setSiteMode] = useState(false)
  const [maxPages, setMaxPages] = useState(30)
  const [discoveredPages, setDiscoveredPages] = useState<PageInfo[]>([])
  const [selectedPages, setSelectedPages] = useState<Set<string>>(new Set())
  const [crawledPages, setCrawledPages] = useState<CrawledPage[]>([])
  const [crawlProgress, setCrawlProgress] = useState({ current: 0, total: 0, status: '', currentTitle: '' })
  const [showPageList, setShowPageList] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState<string | null>(null) // 'zip' | 'merged' | null
  const [crawledMarkdowns, setCrawledMarkdowns] = useState<Record<string, string>>({}) // url -> markdown

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return

    if (siteMode) {
      await handleSiteAnalyze()
    } else {
      await handleSinglePage()
    }
  }

  const handleSinglePage = async () => {
    setLoading(true)
    setResult(null)
    setLoadingStage(0)
    setSelectedImages(new Set())
    setOcrResults({})

    const stageInterval = setInterval(() => {
      setLoadingStage((prev) => (prev + 1) % loadingStages.length)
    }, 1200)

    try {
      const response = await fetch(`${API_URL}/api/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      const data = await response.json()
      setResult(data)
    } catch (error) {
      setResult({ status: 'error', error: 'Failed to connect to server.' })
    } finally {
      clearInterval(stageInterval)
      setLoading(false)
    }
  }

  const handleSiteAnalyze = async () => {
    setLoading(true)
    setDiscoveredPages([])
    setSelectedPages(new Set())
    setCrawledPages([])
    setCrawlProgress({ current: 0, total: 0, status: 'analyzing' })

    try {
      const response = await fetch(`${API_URL}/api/analyze-site`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url.trim(),
          config: analyzerConfig
        }),
      })
      const data = await response.json()
      
      if (data.status === 'success' && data.pages.length > 0) {
        setDiscoveredPages(data.pages)
        setSelectedPages(new Set(data.pages.map((p: PageInfo) => p.url)))
        setShowPageList(true)
        setCrawlProgress({ current: 0, total: data.pages.length, status: 'discovered' })
      } else {
        alert(data.error || '未发现文档页面')
      }
    } catch (error) {
      alert('分析失败，请检查网络连接')
    } finally {
      setLoading(false)
    }
  }

  const handleStartCrawl = async () => {
    const pagesToCrawl = discoveredPages.filter(p => selectedPages.has(p.url)).slice(0, maxPages)
    if (pagesToCrawl.length === 0) return

    setLoading(true)
    setCrawlProgress({ current: 0, total: pagesToCrawl.length, status: 'crawling', currentTitle: '' })
    setCrawledPages([])
    setCrawledMarkdowns({})

    try {
      const response = await fetch(`${API_URL}/api/crawl-site-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pages: pagesToCrawl,
          max_pages: maxPages
        }),
      })

      if (!response.body) {
        throw new Error('No response body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const tempPages: CrawledPage[] = []
      const tempMarkdowns: Record<string, string> = {}

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (data.type === 'progress') {
                setCrawlProgress({
                  current: data.current,
                  total: data.total,
                  status: 'crawling',
                  currentTitle: data.title
                })
              } else if (data.type === 'page') {
                tempPages.push({
                  url: data.url,
                  title: data.title,
                  filename: data.filename,
                  success: data.success,
                  error: data.error
                })
                setCrawledPages([...tempPages])
              } else if (data.type === 'complete') {
                // Store markdowns for download
                data.pages.forEach((p: any) => {
                  if (p.success && p.markdown) {
                    tempMarkdowns[p.url] = p.markdown
                  }
                })
                setCrawledMarkdowns(tempMarkdowns)
                setCrawlProgress({
                  current: data.total,
                  total: data.total,
                  status: 'done',
                  currentTitle: ''
                })
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('Crawl error:', error)
      alert('抓取失败，请检查网络连接')
      setCrawlProgress({ current: 0, total: 0, status: '', currentTitle: '' })
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadSite = async (format: 'zip' | 'merged') => {
    // Check if we have cached markdowns from the crawl
    const successfulPages = crawledPages.filter(p => p.success)
    if (successfulPages.length === 0) {
      alert('没有可下载的内容')
      return
    }

    setDownloadLoading(format)
    
    try {
      // If we have cached markdowns, use them directly (much faster)
      if (Object.keys(crawledMarkdowns).length > 0) {
        if (format === 'merged') {
          // Create merged markdown locally
          let merged = '# 完整文档\n\n'
          merged += `共 ${successfulPages.length} 个页面\n\n---\n\n`
          
          successfulPages.forEach((page, i) => {
            const md = crawledMarkdowns[page.url] || ''
            if (md) {
              merged += `## 第${i + 1}章: ${page.title}\n\n`
              merged += `*来源: ${page.url}*\n\n`
              // Remove first heading if exists
              const content = md.replace(/^# .+\n/, '').trim()
              merged += content + '\n\n---\n\n'
            }
          })
          
          const blob = new Blob([merged], { type: 'text/markdown' })
          const downloadUrl = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = downloadUrl
          a.download = 'complete_docs.md'
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          URL.revokeObjectURL(downloadUrl)
        } else {
          // Create ZIP using JSZip or fallback to server
          // For simplicity, use server API for ZIP
          const response = await fetch(`${API_URL}/api/download-site`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              pages: successfulPages.map(p => ({ url: p.url, title: p.title })),
              max_pages: maxPages,
              format: 'zip'
            }),
          })

          const blob = await response.blob()
          const downloadUrl = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = downloadUrl
          a.download = 'docs.zip'
          document.body.appendChild(a)
          a.click()
          document.body.removeChild(a)
          URL.revokeObjectURL(downloadUrl)
        }
      } else {
        // No cached data, need to crawl again
        const pagesToDownload = discoveredPages.filter(p => selectedPages.has(p.url)).slice(0, maxPages)
        const response = await fetch(`${API_URL}/api/download-site`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pages: pagesToDownload,
            max_pages: maxPages,
            format
          }),
        })

        const blob = await response.blob()
        const downloadUrl = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = downloadUrl
        a.download = format === 'zip' ? 'docs.zip' : 'complete_docs.md'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(downloadUrl)
      }
    } catch (error) {
      alert('下载失败')
    } finally {
      setDownloadLoading(null)
    }
  }

  const handleCopy = async () => {
    const content = getProcessedMarkdown()
    if (content) {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadMd = () => {
    const content = getProcessedMarkdown()
    if (content) {
      const blob = new Blob([content], { type: 'text/markdown' })
      const downloadUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `${result?.title || 'context'}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(downloadUrl)
    }
  }

  const handleDownloadPdf = async () => {
    if (!result?.markdown_with_images) return
    setPdfLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/generate-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown: result.markdown_with_images, title: result.title || 'Document' }),
      })
      if (!response.ok) throw new Error('PDF generation failed')
      const blob = await response.blob()
      const downloadUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `${result.title || 'document'}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(downloadUrl)
    } catch { alert('PDF generation failed') }
    finally { setPdfLoading(false) }
  }

  const toggleImageSelection = useCallback((imagePath: string) => {
    setSelectedImages(prev => {
      const newSet = new Set(prev)
      newSet.has(imagePath) ? newSet.delete(imagePath) : newSet.add(imagePath)
      return newSet
    })
  }, [])

  const handleOCR = async () => {
    if (selectedImages.size === 0 || !ocrConfig.api_key) {
      if (!ocrConfig.api_key) { setShowSettings(true); alert('请先配置OCR模型的API Key') }
      return
    }
    setOcrLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/ocr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_paths: Array.from(selectedImages), config: ocrConfig }),
      })
      const data = await response.json()
      if (data.status === 'success') {
        const newResults: Record<string, string> = { ...ocrResults }
        data.results.forEach((r: any) => { if (r.success && r.text) newResults[r.image_path] = r.text })
        setOcrResults(newResults)
        setSelectedImages(new Set())
      } else { alert(`OCR failed: ${data.error}`) }
    } catch { alert('OCR recognition failed') }
    finally { setOcrLoading(false) }
  }

  const saveConfig = (type: 'ocr' | 'analyzer', config: AIConfig) => {
    if (type === 'ocr') {
      setOcrConfig(config)
      localStorage.setItem('ocrConfig', JSON.stringify(config))
    } else {
      setAnalyzerConfig(config)
      localStorage.setItem('analyzerConfig', JSON.stringify(config))
    }
  }

  const getProcessedMarkdown = useCallback(() => {
    if (!result?.markdown_with_images) return ''
    let content = result.markdown_with_images
    Object.entries(ocrResults).forEach(([imagePath, text]) => {
      const imageRegex = new RegExp(`!\\[[^\\]]*\\]\\(${imagePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\)`, 'g')
      content = content.replace(imageRegex, `\n${text}\n`)
    })
    return content
  }, [result?.markdown_with_images, ocrResults])

  const allImagePaths = useMemo(() => {
    if (!result?.markdown_with_images) return []
    const matches = result.markdown_with_images.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)
    return Array.from(matches).map(m => m[1]).filter(p => p.includes('/api/images/'))
  }, [result?.markdown_with_images])

  const renderedContent = useMemo(() => {
    if (!result?.markdown_with_images) return null
    const content = result.markdown_with_images
    const lines = content.split('\n')
    const elements: JSX.Element[] = []
    
    lines.forEach((line, index) => {
      const imgMatch = line.match(/!\[([^\]]*)\]\(([^)]+)\)/)
      if (imgMatch) {
        const alt = imgMatch[1]
        let src = imgMatch[2]
        const imagePath = src
        
        if (ocrResults[imagePath]) {
          elements.push(
            <div key={index} className="my-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="text-xs text-green-600 mb-2 font-medium">✓ AI识别结果</div>
              <div className="text-slate-700 whitespace-pre-wrap">{ocrResults[imagePath]}</div>
            </div>
          )
          return
        }
        
        if (src.startsWith('/api/images/')) src = `${API_URL}${src}`
        const isSelected = selectedImages.has(imagePath)
        
        elements.push(
          <div key={index} className={`my-4 relative group cursor-pointer transition-all ${isSelected ? 'ring-4 ring-blue-500 rounded-lg' : ''}`} onClick={() => toggleImageSelection(imagePath)}>
            <img src={src} alt={alt} className="max-w-full h-auto rounded-lg shadow-md" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
            <div className={`absolute inset-0 rounded-lg transition-all ${isSelected ? 'bg-blue-500/20' : 'bg-black/0 group-hover:bg-black/10'}`}>
              <div className={`absolute top-2 right-2 w-6 h-6 rounded-full flex items-center justify-center transition-all ${isSelected ? 'bg-blue-500 text-white' : 'bg-white/80 text-slate-400 opacity-0 group-hover:opacity-100'}`}>
                {isSelected ? <Check className="w-4 h-4" /> : <div className="w-3 h-3 border-2 border-slate-400 rounded" />}
              </div>
            </div>
          </div>
        )
        return
      }
      
      if (line.startsWith('# ')) { elements.push(<h1 key={index} className="text-2xl font-bold mt-6 mb-4">{line.slice(2)}</h1>); return }
      if (line.startsWith('## ')) { elements.push(<h2 key={index} className="text-xl font-semibold mt-5 mb-3">{line.slice(3)}</h2>); return }
      if (line.startsWith('### ')) { elements.push(<h3 key={index} className="text-lg font-medium mt-4 mb-2">{line.slice(4)}</h3>); return }
      if (line.includes('🎬')) {
        const linkMatch = line.match(/\[([^\]]+)\]\(([^)]+)\)/)
        if (linkMatch) { elements.push(<div key={index} className="my-2 p-3 bg-slate-100 rounded-lg"><span className="mr-2">🎬</span><a href={linkMatch[2]} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">{linkMatch[1]}</a></div>); return }
      }
      if (line.trim() === '---') { elements.push(<hr key={index} className="my-6 border-slate-300" />); return }
      if (line.trim()) { elements.push(<p key={index} className="my-2 leading-relaxed">{line}</p>) }
      else { elements.push(<div key={index} className="h-2" />) }
    })
    return elements
  }, [result?.markdown_with_images, selectedImages, ocrResults, toggleImageSelection])

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="w-full px-6 py-4 flex items-center justify-between max-w-5xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-black flex items-center justify-center">
            <Link className="w-4 h-4 text-white" />
          </div>
          <span className="text-xl font-semibold tracking-tight">Link2Context</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSettings(true)} className="p-2 rounded-full hover:bg-slate-200 transition-colors" title="AI Settings">
            <Settings className="w-5 h-5 text-slate-600" />
          </button>
          <a href="https://github.com/futur-x/link2context" target="_blank" rel="noopener noreferrer" className="p-2 rounded-full hover:bg-slate-200 transition-colors">
            <Github className="w-5 h-5 text-slate-600" />
          </a>
        </div>
      </header>

      {/* Hero */}
      <div className="flex flex-col items-center justify-center px-6 pt-12 pb-6">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-amber-500" />
          <span className="text-sm font-medium text-slate-500">AI-Ready Context with OCR & Site Crawl</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-center mb-4 bg-gradient-to-b from-slate-900 to-slate-600 bg-clip-text text-transparent">From Link to Context.</h1>
        <p className="text-lg text-slate-500 text-center max-w-md mb-8">Turn any webpage or entire documentation site into clean Markdown.</p>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="w-full max-w-2xl space-y-3">
          <div className="relative flex items-center gap-3 p-2 bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/80">
            <div className="flex-1 flex items-center">
              <Link className="w-5 h-5 text-slate-400 ml-4 mr-3 flex-shrink-0" />
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste URL here..." className="w-full py-3 pr-4 bg-transparent outline-none text-slate-900 placeholder:text-slate-400" disabled={loading} />
            </div>
            <button type="submit" disabled={loading || !url.trim()} className="px-6 py-3 bg-black text-white font-medium rounded-xl hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 flex-shrink-0">
              {loading ? (<><Loader2 className="w-4 h-4 animate-spin" /><span className="hidden sm:inline">{siteMode ? '分析中...' : loadingStages[loadingStage]}</span></>) : (siteMode ? '分析站点' : 'Generate Context')}
            </button>
          </div>
          
          {/* Site Mode Toggle */}
          <div className="flex items-center justify-between px-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <div className={`relative w-12 h-6 rounded-full transition-colors ${siteMode ? 'bg-blue-500' : 'bg-slate-300'}`} onClick={() => setSiteMode(!siteMode)}>
                <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${siteMode ? 'translate-x-7' : 'translate-x-1'}`} />
              </div>
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-slate-500" />
                <span className="text-sm font-medium text-slate-600">整站模式</span>
              </div>
            </label>
            {siteMode && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500">最大页面:</span>
                <select value={maxPages} onChange={(e) => setMaxPages(Number(e.target.value))} className="px-2 py-1 border border-slate-300 rounded-lg text-sm">
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={30}>30</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
            )}
          </div>
        </form>
      </div>

      {/* Site Crawl Results */}
      {showPageList && discoveredPages.length > 0 && (
        <div className="w-full max-w-4xl mx-auto px-6 py-4">
          <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/80 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">发现 {discoveredPages.length} 个页面</h3>
                <p className="text-sm text-slate-500">已选择 {selectedPages.size} 个页面</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setSelectedPages(new Set(discoveredPages.map(p => p.url)))} className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">全选</button>
                <button onClick={() => setSelectedPages(new Set())} className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">取消全选</button>
              </div>
            </div>
            
            <div className="max-h-64 overflow-auto p-4 space-y-2">
              {discoveredPages.slice(0, maxPages).map((page, i) => (
                <label key={i} className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded-lg cursor-pointer">
                  <input type="checkbox" checked={selectedPages.has(page.url)} onChange={() => {
                    const newSet = new Set(selectedPages)
                    newSet.has(page.url) ? newSet.delete(page.url) : newSet.add(page.url)
                    setSelectedPages(newSet)
                  }} className="w-4 h-4 text-blue-600 rounded" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 truncate">{page.title}</div>
                    <div className="text-xs text-slate-500 truncate">{page.url}</div>
                  </div>
                </label>
              ))}
            </div>

            {/* Progress */}
            {crawlProgress.status === 'crawling' && (
              <div className="px-6 py-3 bg-blue-50 border-t border-blue-100">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                    <span className="text-sm text-blue-700">正在抓取: {crawlProgress.current}/{crawlProgress.total}</span>
                  </div>
                  {crawlProgress.currentTitle && (
                    <span className="text-xs text-blue-500 truncate max-w-[200px]">{crawlProgress.currentTitle}</span>
                  )}
                </div>
                <div className="mt-2 h-2 bg-blue-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-600 transition-all duration-300" style={{ width: `${(crawlProgress.current / crawlProgress.total) * 100}%` }} />
                </div>
              </div>
            )}

            {/* Crawl Results */}
            {crawledPages.length > 0 && (
              <div className="px-6 py-3 bg-green-50 border-t border-green-100">
                <div className="text-sm text-green-700 mb-2">
                  ✅ 抓取完成: {crawledPages.filter(p => p.success).length} 成功, {crawledPages.filter(p => !p.success).length} 失败
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="px-6 py-4 border-t border-slate-100 flex flex-wrap gap-3">
              {crawledPages.length === 0 ? (
                <button onClick={handleStartCrawl} disabled={loading || selectedPages.size === 0} className="flex items-center gap-2 px-4 py-2 bg-black text-white font-medium rounded-lg hover:bg-slate-800 disabled:opacity-50">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />}
                  开始抓取 ({Math.min(selectedPages.size, maxPages)} 页)
                </button>
              ) : (
                <>
                  <button onClick={() => handleDownloadSite('zip')} disabled={loading || downloadLoading !== null} className="flex items-center gap-2 px-4 py-2 bg-black text-white font-medium rounded-lg hover:bg-slate-800 disabled:opacity-50">
                    {downloadLoading === 'zip' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileArchive className="w-4 h-4" />}
                    {downloadLoading === 'zip' ? '正在打包...' : '下载压缩包'}
                  </button>
                  <button onClick={() => handleDownloadSite('merged')} disabled={loading || downloadLoading !== null} className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white font-medium rounded-lg hover:from-purple-700 hover:to-blue-700 disabled:opacity-50">
                    {downloadLoading === 'merged' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Package className="w-4 h-4" />}
                    {downloadLoading === 'merged' ? '正在合并...' : '合并成一个Markdown'}
                  </button>
                </>
              )}
              <button onClick={() => { setShowPageList(false); setDiscoveredPages([]); setCrawledPages([]) }} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* Single Page Result */}
      {result && !siteMode && (
        <div className="w-full max-w-4xl mx-auto px-6 py-8">
          {result.error ? (
            <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
              <p className="text-red-600 font-medium">❌ {result.error}</p>
            </div>
          ) : (
            <div className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200/80 overflow-hidden">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-6 py-4 border-b border-slate-100 gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-slate-900 truncate">{result.title || 'Extracted Content'}</h3>
                  <div className="flex items-center gap-3 text-sm text-slate-400">
                    <span>Strategy: {result.strategy_used || 'unknown'}</span>
                    {allImagePaths.length > 0 && <><span>•</span><span>{allImagePaths.length} images</span></>}
                    {Object.keys(ocrResults).length > 0 && <><span>•</span><span className="text-green-600">{Object.keys(ocrResults).length} recognized</span></>}
                  </div>
                </div>
                <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
                  <button onClick={() => setShowPreview(true)} className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${showPreview ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}><FileImage className="w-4 h-4 inline mr-1" />Preview</button>
                  <button onClick={() => setShowPreview(false)} className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${!showPreview ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}><FileText className="w-4 h-4 inline mr-1" />Raw</button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 px-6 py-3 bg-slate-50 border-b border-slate-100">
                <button onClick={handleCopy} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200">
                  {copied ? <><Check className="w-4 h-4 text-green-500" />Copied!</> : <><Copy className="w-4 h-4" />Copy</>}
                </button>
                <button onClick={handleDownloadMd} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200"><FileText className="w-4 h-4" />Download .md</button>
                <button onClick={handleDownloadPdf} disabled={pdfLoading} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg transition-colors border border-transparent hover:border-slate-200 disabled:opacity-50">
                  {pdfLoading ? <><Loader2 className="w-4 h-4 animate-spin" />Generating...</> : <><Download className="w-4 h-4" />Download PDF</>}
                </button>
                <button onClick={handleOCR} disabled={ocrLoading || selectedImages.size === 0} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-auto">
                  {ocrLoading ? <><Loader2 className="w-4 h-4 animate-spin" />识别中...</> : <><Wand2 className="w-4 h-4" />AI识别 {selectedImages.size > 0 && `(${selectedImages.size})`}</>}
                </button>
              </div>

              {showPreview && allImagePaths.length > 0 && selectedImages.size === 0 && Object.keys(ocrResults).length === 0 && (
                <div className="px-6 py-2 bg-blue-50 text-blue-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />点击图片选中，然后点击"AI识别"按钮识别图片中的文字</div>
              )}

              <div className="p-6 max-h-[700px] overflow-auto">
                {showPreview ? <div className="prose prose-slate max-w-none">{renderedContent}</div> : <pre className="markdown-output text-slate-700 bg-slate-50 p-4 rounded-lg whitespace-pre-wrap">{getProcessedMarkdown()}</pre>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h2 className="text-lg font-semibold">AI模型配置</h2>
              <button onClick={() => setShowSettings(false)} className="p-1 hover:bg-slate-100 rounded-full"><X className="w-5 h-5" /></button>
            </div>
            
            <div className="p-6 space-y-8">
              {/* OCR Config */}
              <div>
                <h3 className="text-md font-semibold text-slate-800 mb-4 flex items-center gap-2"><Wand2 className="w-5 h-5 text-purple-500" />图片OCR模型</h3>
                <div className="space-y-3 pl-7">
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="block text-sm font-medium text-slate-700 mb-1">Provider</label><select value={ocrConfig.provider} onChange={(e) => saveConfig('ocr', { ...ocrConfig, provider: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg"><option value="openai">OpenAI</option><option value="claude">Claude</option><option value="custom">Custom</option></select></div>
                    <div><label className="block text-sm font-medium text-slate-700 mb-1">Model</label><input type="text" value={ocrConfig.model} onChange={(e) => saveConfig('ocr', { ...ocrConfig, model: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  </div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">Base URL</label><input type="text" value={ocrConfig.base_url} onChange={(e) => saveConfig('ocr', { ...ocrConfig, base_url: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">API Key</label><input type="password" value={ocrConfig.api_key} onChange={(e) => saveConfig('ocr', { ...ocrConfig, api_key: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">Prompt</label><textarea value={ocrConfig.prompt} onChange={(e) => saveConfig('ocr', { ...ocrConfig, prompt: e.target.value })} rows={2} className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" /></div>
                </div>
              </div>

              {/* Analyzer Config */}
              <div>
                <h3 className="text-md font-semibold text-slate-800 mb-4 flex items-center gap-2"><Globe className="w-5 h-5 text-blue-500" />页面结构分析模型</h3>
                <div className="space-y-3 pl-7">
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="block text-sm font-medium text-slate-700 mb-1">Provider</label><select value={analyzerConfig.provider} onChange={(e) => saveConfig('analyzer', { ...analyzerConfig, provider: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg"><option value="openai">OpenAI</option><option value="claude">Claude</option><option value="custom">Custom</option></select></div>
                    <div><label className="block text-sm font-medium text-slate-700 mb-1">Model</label><input type="text" value={analyzerConfig.model} onChange={(e) => saveConfig('analyzer', { ...analyzerConfig, model: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  </div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">Base URL</label><input type="text" value={analyzerConfig.base_url} onChange={(e) => saveConfig('analyzer', { ...analyzerConfig, base_url: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">API Key</label><input type="password" value={analyzerConfig.api_key} onChange={(e) => saveConfig('analyzer', { ...analyzerConfig, api_key: e.target.value })} className="w-full px-3 py-2 border border-slate-300 rounded-lg" /></div>
                  <div><label className="block text-sm font-medium text-slate-700 mb-1">Prompt</label><textarea value={analyzerConfig.prompt} onChange={(e) => saveConfig('analyzer', { ...analyzerConfig, prompt: e.target.value })} rows={2} className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" /></div>
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3">
              <button onClick={() => { saveConfig('ocr', DEFAULT_OCR_CONFIG); saveConfig('analyzer', DEFAULT_ANALYZER_CONFIG) }} className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900">恢复默认</button>
              <button onClick={() => setShowSettings(false)} className="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg hover:bg-slate-800">保存</button>
            </div>
          </div>
        </div>
      )}

      <footer className="w-full px-6 py-8 text-center text-sm text-slate-400"><p>Built for LLMs. Single page or entire site.</p></footer>
    </main>
  )
}
